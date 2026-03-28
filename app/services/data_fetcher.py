import time
import re
import io
from contextlib import redirect_stdout
from concurrent.futures import ThreadPoolExecutor, as_completed

import akshare as ak
import pandas as pd

# 板块接口为「今日」行业资金流，与复盘日无关；缓存键勿绑定 date，避免误判
SECTOR_LIVE_CACHE_KEY = "sector_fund_flow_rank_live"
# 昨日涨停溢价：超过该数量则走全市场 spot，避免过多单股请求
YEST_PREMIUM_HIST_MAX_CODES = 100
# 同一请求内可能多次拉全市场行情，短 TTL 复用
SPOT_EM_CACHE_TTL_SEC = 90


class DataFetcher:
    """数据获取类（含冗余、重试、缓存）"""

    def __init__(self, cache_expire=3600, retry_times=1):
        self.cache = {}  # 缓存 {key: (timestamp, data)}
        self.cache_expire = cache_expire
        self.retry_times = retry_times
        self.progress_callback = None
        self.current_task = None
        self._spot_em_cache_ts: float = 0.0
        self._spot_em_df = None

    def _is_cache_valid(self, key):
        if key in self.cache:
            ts, _ = self.cache[key]
            if time.time() - ts < self.cache_expire:
                return True
            else:
                del self.cache[key]
        return False

    def _get_cache(self, key):
        return self.cache[key][1] if key in self.cache else None

    def _set_cache(self, key, data):
        self.cache[key] = (time.time(), data)

    def set_progress_callback(self, callback):
        self.progress_callback = callback

    def set_current_task(self, task):
        self.current_task = task

    def get_stock_zh_a_spot_em_cached(self):
        """全 A 行情（东财）短缓存，避免溢价计算与选股两次全量拉取。"""
        now = time.time()
        if (
            self._spot_em_df is not None
            and now - self._spot_em_cache_ts < SPOT_EM_CACHE_TTL_SEC
        ):
            return self._spot_em_df
        df = ak.stock_zh_a_spot_em()
        self._spot_em_df = df
        self._spot_em_cache_ts = now
        return df

    def fetch_with_retry(self, fetch_func, *args, **kwargs):
        """带重试的获取函数（用 redirect_stdout，避免多线程下全局替换 sys.stdout）"""
        for attempt in range(self.retry_times + 1):
            try:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    result = fetch_func(*args, **kwargs)
                self._parse_progress(buf.getvalue())
                return result
            except Exception as e:
                print(f"尝试 {attempt + 1}/{self.retry_times + 1} 失败: {e}")
                if attempt == self.retry_times:
                    raise
                time.sleep(2)  # 等待2秒后重试
        return None

    def _parse_progress(self, output):
        """解析akshare的进度输出"""
        if not self.current_task:
            return
        
        # 匹配进度模式，如 "8/58"
        match = re.search(r'(\d+)/(\d+)', output)
        if match:
            current = int(match.group(1))
            total = int(match.group(2))
            if total > 0:
                # 计算百分比
                percentage = int((current / total) * 100)
                # 更新任务进度
                # 只在当前进度基础上增加，避免覆盖其他步骤的进度
                if hasattr(self.current_task, 'progress'):
                    # 假设数据获取阶段占总进度的80%
                    data_progress = percentage * 0.8
                    # 加上基础进度10%
                    new_progress = 10 + data_progress
                    if new_progress > self.current_task.progress:
                        self.current_task.progress = min(int(new_progress), 90)

    # ---------- 辅助函数：金额单位转换 ----------
    def _convert_money_to_float(self, money_str):
        """将带单位的金额字符串转换为以亿元为单位的浮点数"""
        if isinstance(money_str, (int, float)):
            return money_str / 1e8  # 如果已经是数值，假设单位为元，转为亿元
        try:
            s = str(money_str).strip()
            if '亿' in s:
                return float(s.replace('亿', ''))
            elif '万' in s:
                return float(s.replace('万', '')) / 10000
            else:
                return float(s) / 1e8  # 假设单位为元，转为亿元
        except Exception:
            return 0.0

    # ---------- 核心数据获取 ----------
    def get_trade_cal(self):
        """获取交易日历"""
        cache_key = "trade_cal"
        if self._is_cache_valid(cache_key):
            return self._get_cache(cache_key)
        try:
            cal = ak.tool_trade_date_hist_sina()
            trade_days = sorted(
                pd.to_datetime(cal["trade_date"]).dt.strftime("%Y%m%d").tolist()
            )
            self._set_cache(cache_key, trade_days)
            return trade_days
        except Exception as e:
            print(f"获取交易日历失败: {e}")
            return []

    def get_last_trade_day(self, date_str, trade_days=None):
        """获取指定日期最近的一个交易日（<=该日期）"""
        trade_days = trade_days if trade_days is not None else self.get_trade_cal()
        if not trade_days:
            return date_str  # 无数据时返回原日期
        valid_days = [d for d in trade_days if d <= date_str]
        return valid_days[-1] if valid_days else date_str

    def get_zt_pool(self, date):
        """获取涨停股票池（主用AKShare，失败返回空DataFrame）"""
        cache_key = f"zt_pool_{date}"
        if self._is_cache_valid(cache_key):
            return self._get_cache(cache_key)
        try:
            df = self.fetch_with_retry(ak.stock_zt_pool_em, date=date)
            if df is None or df.empty:
                self._set_cache(cache_key, pd.DataFrame())
                return pd.DataFrame()
            # 重命名列
            df = df.rename(columns={
                '代码': 'code', '名称': 'name', '最新价': 'price', '涨跌幅': 'pct_chg',
                '连板数': 'lb', '炸板次数': 'zb_count', '所属行业': 'industry',
                '涨停原因': 'reason', '最后封板时间': 'fb_time', '首次封板时间': 'first_time'
            })
            df['lb'] = pd.to_numeric(df['lb'], errors='coerce').fillna(1).astype(int)
            self._set_cache(cache_key, df)
            return df
        except Exception as e:
            print(f"获取涨停数据失败: {e}")
            self._set_cache(cache_key, pd.DataFrame())
            return pd.DataFrame()

    def get_dt_pool(self, date):
        """跌停股票池"""
        cache_key = f"dt_pool_{date}"
        if self._is_cache_valid(cache_key):
            return self._get_cache(cache_key)
        try:
            df = self.fetch_with_retry(ak.stock_zt_pool_dtgc_em, date=date)
            if df is not None and not df.empty and '代码' in df.columns:
                df = df.rename(columns={'代码': 'code', '名称': 'name'})
            else:
                df = pd.DataFrame()
            self._set_cache(cache_key, df)
            return df
        except Exception:
            self._set_cache(cache_key, pd.DataFrame())
            return pd.DataFrame()

    def get_zb_pool(self, date):
        """炸板股票池"""
        cache_key = f"zb_pool_{date}"
        if self._is_cache_valid(cache_key):
            return self._get_cache(cache_key)
        try:
            df = self.fetch_with_retry(ak.stock_zt_pool_zbgc_em, date=date)
            if df is not None and not df.empty and '代码' in df.columns:
                df = df.rename(columns={'代码': 'code', '名称': 'name'})
            else:
                df = pd.DataFrame()
            self._set_cache(cache_key, df)
            return df
        except Exception:
            self._set_cache(cache_key, pd.DataFrame())
            return pd.DataFrame()

    def get_sector_rank(self, date):
        """
        获取板块资金流向排名（成交额、涨幅）。
        注意：接口为当日「今日」行业资金流，非历史某日切片；参数 date 仅保留调用兼容。
        """
        cache_key = SECTOR_LIVE_CACHE_KEY
        if self._is_cache_valid(cache_key):
            return self._get_cache(cache_key)

        try:
            # 使用正确的板块资金流向排名接口
            # indicator: "今日"、"3日"、"5日"、"10日"、"20日"
            # sector_type: "行业资金流"、"概念资金流"、"地域资金流"
            df = ak.stock_sector_fund_flow_rank(
                indicator="今日",
                sector_type="行业资金流"
            )

            if df.empty:
                print("获取板块资金流向数据为空")
                self._set_cache(cache_key, pd.DataFrame())
                return pd.DataFrame()

            # 根据实际返回的列名进行调整（基于日志）
            # 常见列名：'名称', '今日涨跌幅', '今日主力净流入-净额'
            if all(col in df.columns for col in ['名称', '今日涨跌幅', '今日主力净流入-净额']):
                df_result = df[['名称', '今日涨跌幅', '今日主力净流入-净额']].rename(
                    columns={
                        '名称': 'sector',
                        '今日涨跌幅': 'pct',
                        '今日主力净流入-净额': 'money'
                    }
                )

                # 转换数据格式：涨跌幅去除%，并转为浮点数
                df_result['pct'] = df_result['pct'].astype(str).str.replace('%', '').astype(float)

                # 转换主力净流入为亿元
                df_result['money'] = df_result['money'].apply(self._convert_money_to_float)

                # 按净流入金额排序，取前5
                df_result = df_result.sort_values('money', ascending=False).head(5)

                self._set_cache(cache_key, df_result)
                return df_result
            else:
                print(f"标准列名不存在，可用列: {df.columns.tolist()}")
                # 尝试模糊匹配（简单处理）
                # 查找包含'名称'、'涨跌幅'、'主力净流入'的列
                name_col = next((col for col in df.columns if '名称' in col), None)
                pct_col = next((col for col in df.columns if '涨跌幅' in col), None)
                money_col = next((col for col in df.columns if '主力净流入' in col and '净额' in col), None)

                if name_col and pct_col and money_col:
                    df_result = df[[name_col, pct_col, money_col]].rename(
                        columns={name_col: 'sector', pct_col: 'pct', money_col: 'money'}
                    )
                    df_result['pct'] = df_result['pct'].astype(str).str.replace('%', '').astype(float)
                    df_result['money'] = df_result['money'].apply(self._convert_money_to_float)
                    df_result = df_result.sort_values('money', ascending=False).head(5)
                    self._set_cache(cache_key, df_result)
                    return df_result
                else:
                    self._set_cache(cache_key, pd.DataFrame())
                    return pd.DataFrame()

        except Exception as e:
            print(f"获取板块排名失败: {e}")
            # 尝试备用接口：stock_fund_flow_industry
            try:
                print("尝试备用接口: stock_fund_flow_industry")
                df = ak.stock_fund_flow_industry(symbol="今日")
                if not df.empty:
                    # 尝试模糊匹配列名
                    # 查找包含'行业'或'名称'的列
                    name_col = next((col for col in df.columns if '行业' in col or '名称' in col), None)
                    # 查找包含'涨跌幅'的列
                    pct_col = next((col for col in df.columns if '涨跌幅' in col), None)
                    # 查找包含'净额'或'资金'的列
                    money_col = next((col for col in df.columns if '净额' in col or '资金' in col), None)
                    
                    if name_col and pct_col and money_col:
                        df_result = df[[name_col, pct_col, money_col]].rename(
                            columns={name_col: 'sector', pct_col: 'pct', money_col: 'money'}
                        )
                        # 转换数据格式
                        try:
                            df_result['pct'] = df_result['pct'].astype(str).str.replace('%', '').astype(float)
                            df_result['money'] = df_result['money'].apply(self._convert_money_to_float)
                            df_result = df_result.sort_values('money', ascending=False).head(5)
                            self._set_cache(cache_key, df_result)
                            return df_result
                        except Exception as e3:
                            print(f"数据转换失败: {e3}")
            except Exception as e2:
                print(f"备用接口也失败: {e2}")

            self._set_cache(cache_key, pd.DataFrame())
            return pd.DataFrame()

    def _pct_chg_for_codes_on_date(self, codes, date_str):
        """按交易日拉取单日 K 线涨跌幅，避免 stock_zh_a_spot_em 全市场分页。"""
        if not codes:
            return []

        def one(code):
            c = re.sub(r"[^0-9]", "", str(code))[:6].zfill(6)
            try:
                df = ak.stock_zh_a_hist(
                    symbol=c,
                    period="daily",
                    start_date=date_str,
                    end_date=date_str,
                    adjust="",
                )
                if df is not None and not df.empty and "涨跌幅" in df.columns:
                    return float(df["涨跌幅"].iloc[-1])
            except Exception:
                pass
            return None

        max_workers = min(10, max(1, len(codes)))
        out = []
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(one, c) for c in codes]
            for fut in as_completed(futures):
                v = fut.result()
                if v is not None:
                    out.append(v)
        return out

    def _yest_premium_from_full_spot(self, yest_codes):
        """全市场行情过滤（涨停家数过多时的回退方案）"""
        norm = [re.sub(r"[^0-9]", "", str(x))[:6].zfill(6) for x in yest_codes]
        all_df = self.get_stock_zh_a_spot_em_cached()
        if all_df.empty:
            all_df = ak.stock_zh_a_spot()
        all_df["code"] = all_df["代码"].apply(
            lambda x: re.sub(r"[^0-9]", "", str(x))[:6]
        )
        today_data = all_df[all_df["code"].isin(norm)]
        if today_data.empty:
            return None
        return float(today_data["涨跌幅"].mean())

    def get_yest_zt_premium(self, date, trade_days=None):
        """计算昨日涨停股票在当日（date）的平均溢价"""
        trade_days = trade_days if trade_days is not None else self.get_trade_cal()
        if not trade_days or date not in trade_days:
            return -99.0, "非交易日"
        idx = trade_days.index(date)
        if idx == 0:
            return -99.0, "无昨日数据"
        yest_date = trade_days[idx - 1]

        yest_zt = self.get_zt_pool(yest_date)
        if yest_zt.empty:
            return -99.0, "昨日无涨停"

        yest_codes = yest_zt["code"].tolist()

        try:
            chgs = None
            if len(yest_codes) <= YEST_PREMIUM_HIST_MAX_CODES:
                chgs = self._pct_chg_for_codes_on_date(yest_codes, date)
                if chgs and len(chgs) >= max(1, len(yest_codes) // 2):
                    avg_premium = sum(chgs) / len(chgs)
                    return round(avg_premium, 2), "正常"
            # 样本过少或股票过多：回退全市场 spot
            avg_premium = self._yest_premium_from_full_spot(yest_codes)
            if avg_premium is None:
                return 0.0, "无匹配数据"
            return round(avg_premium, 2), "正常"
        except Exception as e:
            print(f"计算溢价异常: {e}")
            return -99.0, f"异常:{str(e)[:20]}"

    def get_north_money(self, date):
        """获取北向资金数据"""
        try:
            # 尝试使用正确的接口获取北向资金数据
            # 先尝试 stock_hsgt_north_net_flow_sina 接口
            df = ak.stock_hsgt_north_net_flow_sina(date=date)
            if not df.empty:
                # 检查列名是否存在
                if '北向资金净流入' in df.columns:
                    net_flow = df['北向资金净流入'].iloc[0]
                    return round(net_flow / 1e8, 2)  # 转为亿元
                elif '净流入' in df.columns:
                    net_flow = df['净流入'].iloc[0]
                    return round(net_flow / 1e8, 2)  # 转为亿元
        except Exception as e:
            print(f"获取北向资金数据失败: {e}")
        return 0.0

    def get_market_summary(self, date):
        """获取完整市场摘要（文本形式）"""
        summary = ""
        trade_days = self.get_trade_cal()
        if not trade_days:
            summary += "## 基础数据\n- 无法获取交易日历，请检查网络或数据源。\n\n"
            return summary, date
        if date not in trade_days:
            print(f"{date} 非交易日，将自动调整")
            date = self.get_last_trade_day(date, trade_days)
            print(f"调整为最近交易日: {date}")

        # 获取基础数据
        df_zt = self.get_zt_pool(date)
        df_dt = self.get_dt_pool(date)
        df_zb = self.get_zb_pool(date)
        df_sector = self.get_sector_rank(date)
        premium, premium_note = self.get_yest_zt_premium(date, trade_days)
        north_money = self.get_north_money(date)

        zt_count = len(df_zt)
        dt_count = len(df_dt)
        zb_count = len(df_zb)
        total = zt_count + zb_count
        zhaban_rate = round(zb_count / total * 100, 2) if total > 0 else 0

        # 计算情绪温度
        sentiment_temp = 0
        if zt_count > 30:
            sentiment_temp += 30
        elif zt_count > 20:
            sentiment_temp += 20
        elif zt_count > 10:
            sentiment_temp += 10

        if dt_count < 5:
            sentiment_temp += 20
        elif dt_count < 10:
            sentiment_temp += 10

        if premium > 3:
            sentiment_temp += 25
        elif premium > 1:
            sentiment_temp += 15
        elif premium > 0:
            sentiment_temp += 5

        if zhaban_rate < 25:
            sentiment_temp += 25
        elif zhaban_rate < 40:
            sentiment_temp += 15

        sentiment_temp = min(sentiment_temp, 100)

        # 市场阶段判断
        market_phase = "震荡期"
        position_suggestion = "30%"
        if sentiment_temp > 80:
            market_phase = "主升期"
            position_suggestion = "80%"
        elif sentiment_temp < 30:
            market_phase = "退潮期"
            position_suggestion = "0-10%"

        summary += f"## 基础数据\n"
        summary += f"- 涨停数：{zt_count}\n"
        summary += f"- 跌停数：{dt_count}\n"
        summary += f"- 炸板数：{zb_count}\n"
        summary += f"- 炸板率：{zhaban_rate}%\n"
        summary += f"- 昨日涨停溢价：{premium if premium != -99 else premium_note}\n"
        summary += f"- 北向资金净流入：{north_money}亿\n"
        summary += f"- 情绪温度：{sentiment_temp}°C\n"
        summary += f"- 市场阶段：{market_phase}\n"
        summary += f"- 建议仓位：{position_suggestion}\n\n"

        # 板块排名
        if not df_sector.empty:
            summary += f"## 板块资金流向排名（前五，当前接口为行业资金流实时快照）\n"
            for _, row in df_sector.iterrows():
                summary += f"- {row['sector']}：涨幅 {row['pct']}%，主力净流入 {row['money']:.2f}亿\n"
            summary += "\n"
        else:
            summary += "## 板块资金流向\n- 暂无板块资金流向数据\n\n"

        # 连板梯队
        if not df_zt.empty:
            lb_stats = df_zt['lb'].value_counts().sort_index()
            summary += f"## 连板梯队\n"
            for lb, cnt in lb_stats.items():
                summary += f"- {lb}连板：{cnt}只\n"
            max_lb = df_zt['lb'].max()
            summary += f"最高连板：{max_lb}板\n\n"

            # 核心龙头（连板≥2）
            df_top = df_zt[df_zt['lb'] >= 2].sort_values(['lb', 'first_time'], ascending=[False, True])
            if not df_top.empty:
                summary += f"## 核心龙头\n"
                for _, row in df_top.head(5).iterrows():
                    industry = row.get('industry', '未知')
                    first_time = row.get('first_time', '')
                    summary += f"- {row['name']}（{row['code']}）{row['lb']}连板，行业：{industry}，首封：{first_time}\n"
                summary += "\n"

            # 行业分布
            if 'industry' in df_zt.columns:
                industry_stats = df_zt['industry'].value_counts().head(5)
                summary += f"## 涨停行业分布\n"
                for industry, cnt in industry_stats.items():
                    summary += f"- {industry}：{cnt}家\n"
                summary += "\n"

        try:
            from app.services.auction_halfway_strategy import build_auction_halfway_report

            summary += build_auction_halfway_report(date, trade_days, self, df_zt)
        except Exception as e:
            summary += f"\n## 【次日竞价半路模式】选股\n- 执行异常：{e!s}\n\n"

        return summary, date  # 返回可能调整后的日期
