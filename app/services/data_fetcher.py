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
# 财联社要闻接口为「最新」列表，短缓存减轻重复请求
FINANCE_NEWS_CACHE_KEY = "finance_news_main_cx"
FINANCE_NEWS_CACHE_TTL_SEC = 600


def _finance_news_enabled() -> bool:
    try:
        from app.utils.config import ConfigManager

        return bool(ConfigManager().get("enable_finance_news", True))
    except Exception:
        return True


def _expand_stock_name_keywords(name: str) -> list[str]:
    """名称及去常见后缀后的简称，用于新闻文本匹配。"""
    name = str(name).strip()
    if not name:
        return []
    out = [name]
    for suf in (
        "股份有限公司",
        "有限公司",
        "股份",
        "集团",
        "控股",
        "科技",
        "技术",
        "电子",
        "药业",
        "银行",
    ):
        if name.endswith(suf) and len(name) > len(suf) + 1:
            out.append(name[: -len(suf)])
    return list(dict.fromkeys(out))


def _news_keywords_from_meta(ah_meta: dict) -> tuple[set[str], list[str]]:
    codes: set[str] = set()
    names: list[str] = []
    for p in ah_meta.get("top_pool") or []:
        c = str(p.get("code") or "").strip()
        if c:
            codes.add(c.zfill(6)[:6])
            if c.isdigit():
                codes.add(str(int(c)))
        nm = str(p.get("name") or "").strip()
        if nm:
            names.extend(_expand_stock_name_keywords(nm))
    for sec in ah_meta.get("main_sectors") or []:
        s = str(sec).strip()
        if len(s) >= 2:
            names.append(s)
    seen: set[str] = set()
    uniq_names: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            uniq_names.append(n)
    return codes, uniq_names


def _truncate_news_line(s: str, n: int) -> str:
    s = str(s).strip().replace("\n", " ")
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def _news_row_matches(
    summary: str, codes: set[str], names: list[str]
) -> tuple[bool, str]:
    if not summary:
        return False, ""
    matched: list[str] = []
    for c in codes:
        if c in summary:
            matched.append(c)
    for n in names:
        if len(n) >= 2 and n in summary:
            matched.append(n[:12])
    if not matched:
        return False, ""
    return True, "、".join(dict.fromkeys(matched))


def _append_ai_context(
    meta: dict,
    *,
    zt_count: int,
    dt_count: int,
    zb_count: int,
    premium: float,
    premium_note: str,
    sector_empty: bool,
    north_value: float,
    north_status: str,
) -> str:
    """根据程序 meta 与当日基础指标，追加给大模型的「须回应」提示块。"""
    lines = ["\n## 【AI 提示】数据质量、程序状态与须回应点\n"]
    bullets: list[str] = []
    prem_bad = premium == -99.0 or ("非交易日" in str(premium_note))
    if prem_bad:
        bullets.append(
            "昨日涨停溢价**不可用或异常**，涉及溢价的结论须标注**置信度低**。"
        )
    if zt_count < 10:
        bullets.append(
            f"涨停家数仅 **{zt_count}**，情绪指标参考价值下降，结论须谨慎。"
        )
    if dt_count > 25:
        bullets.append(
            f"跌停家数 **{dt_count}** 偏高，须强调退潮风险与仓位克制。"
        )
    if zb_count > 80:
        bullets.append(f"炸板数 **{zb_count}** 较多，须强调分歧与模式风险。")
    if sector_empty:
        bullets.append("板块资金流向块缺失，**主线叙事须以程序选股第一节为准**。")
    if north_status == "fetch_failed":
        bullets.append(
            "北向资金接口**获取失败**，**勿将北向作为核心依据**。"
        )
    elif north_status == "empty_df":
        bullets.append(
            "北向资金返回**空表**，北向相关表述须标注**置信度低**。"
        )
    elif north_status == "ok_zero":
        bullets.append(
            "北向资金净流入为 **0**（接口口径），须结合其它维度判断，**勿单独依赖**。"
        )
    ar = meta.get("abort_reason")
    if ar:
        bullets.append(
            f"程序选股**未完整产出龙头池**：{ar}。报告须说明今日无法按完整池展开，并降低置信度。"
        )
    mss = meta.get("main_sectors") or []
    if meta.get("program_completed") and mss:
        bullets.append(
            "程序认定的主线板块（**分析必须与下列名称对齐或解释为何不采纳**）：**"
            + "、".join(mss[:3])
            + "**"
        )
    for p in meta.get("top_pool") or []:
        ts = float(p.get("tech_score") or 0)
        s1 = int(p.get("s1_main") or 0)
        if ts >= 4.0 and s1 <= 2:
            bullets.append(
                f"**冲突须单独回应**：{p['name']}（{p['code']}）技术面 **{ts:.1f}/5** 较高，"
                f"但主线强度分 **s1={s1}**（板块成交额排名偏弱）。须写清是否仍参与次日竞价。"
            )
    if not bullets:
        bullets.append("未发现额外异常标记；仍须遵守用户要求中的输出结构、字数与表格格式。")
    for b in bullets:
        lines.append(f"- {b}\n")
    lines.append("\n")
    return "".join(lines)


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
        # get_market_summary 内写入，供复盘任务在推送/邮件正文顶部附加要闻摘要
        self._last_news_push_prefix: str = ""
        # 程序选股 meta（龙头池等），供存档与周度统计
        self._last_auction_meta: dict = {}

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

    def get_north_money(self, date) -> tuple[float, str]:
        """
        北向净流入（亿元）与状态。
        状态：ok / ok_zero / empty_df / fetch_failed
        """
        try:
            df = ak.stock_hsgt_north_net_flow_sina(date=date)
            if df is None or df.empty:
                return 0.0, "empty_df"
            if "北向资金净流入" in df.columns:
                net_flow = df["北向资金净流入"].iloc[0]
            elif "净流入" in df.columns:
                net_flow = df["净流入"].iloc[0]
            else:
                return 0.0, "empty_df"
            val = round(float(net_flow) / 1e8, 2)
            if val == 0.0:
                return 0.0, "ok_zero"
            return val, "ok"
        except Exception as e:
            print(f"获取北向资金数据失败: {e}")
            return 0.0, "fetch_failed"

    def get_lhb_snippet_for_codes(self, date: str, codes: list[str]) -> str:
        """新浪龙虎榜日表与龙头池代码交集，失败则返回说明行。"""
        if not codes:
            return ""
        cache_key = f"lhb_daily_{date}"
        if self._is_cache_valid(cache_key):
            df = self._get_cache(cache_key)
        else:
            try:
                df = self.fetch_with_retry(ak.stock_lhb_detail_daily_sina, date=date)
                if df is None:
                    df = pd.DataFrame()
            except Exception as e:
                print(f"龙虎榜日表获取失败: {e}")
                df = pd.DataFrame()
            self._set_cache(cache_key, df)
        if df is None or df.empty:
            return (
                "\n## （可选）龙虎榜\n"
                "- 当日龙虎榜明细**未获取到或为空**（网络/接口原因），勿臆测上榜情况。\n\n"
            )
        want = {str(c).zfill(6)[:6] for c in codes}
        if "股票代码" not in df.columns:
            return "\n## （可选）龙虎榜\n- 返回表结构异常，已跳过。\n\n"
        df = df.copy()
        df["股票代码"] = df["股票代码"].astype(str).str.zfill(6).str[:6]
        sub = df[df["股票代码"].isin(want)]
        if sub.empty:
            return (
                "\n## （可选）龙虎榜\n"
                "- 龙头池标的在**当日龙虎榜明细中未出现**（或未覆盖），不代表优劣，仅作资金关注度参考。\n\n"
            )
        lines = ["\n## （可选）龙虎榜·与龙头池交集\n"]
        lines.append(
            "- 数据来源：新浪财经日表；与东财口径可能不一致，**仅供参考**。\n"
        )
        for _, row in sub.head(12).iterrows():
            nm = row.get("股票名称", "")
            cd = row.get("股票代码", "")
            ind = row.get("指标", "")
            lines.append(f"- {nm}（{cd}）{ind}\n")
        lines.append("\n")
        return "".join(lines)

    def get_finance_news_bundle(self, date: str, ah_meta: dict) -> tuple[str, str]:
        """
        财联社等公开要闻：与龙头池代码/名称、主线板块做关键词匹配。
        返回 (写入市场摘要的 Markdown 块, 推送/报告顶部用的短文本)。
        """
        if not _finance_news_enabled():
            return "", ""
        df = None
        if FINANCE_NEWS_CACHE_KEY in self.cache:
            ts, data = self.cache[FINANCE_NEWS_CACHE_KEY]
            if time.time() - ts < FINANCE_NEWS_CACHE_TTL_SEC:
                df = data
        if df is None:
            try:
                df = self.fetch_with_retry(ak.stock_news_main_cx)
            except Exception as e:
                print(f"财经要闻获取失败: {e}")
                df = pd.DataFrame()
            self._set_cache(FINANCE_NEWS_CACHE_KEY, df)
        if df is None or df.empty:
            line = (
                "\n## 【财经要闻·与程序观察标的】\n"
                "- 要闻接口暂不可用或为空，今日不复述外围消息。\n\n"
            )
            return line, ""

        codes, names = _news_keywords_from_meta(ah_meta or {})
        related: list[tuple[str, str, str]] = []
        general: list[tuple[str, str]] = []
        for _, row in df.head(100).iterrows():
            tag = str(row.get("tag") or "").strip()
            summary = str(row.get("summary") or "").strip()
            if not summary:
                continue
            ok, hint = _news_row_matches(summary, codes, names)
            if ok:
                related.append((tag, summary, hint))
            else:
                general.append((tag, summary))

        lines = ["\n## 【财经要闻·与程序观察标的】\n"]
        lines.append(
            "> **说明**：摘要来自公开财经快讯；**个股/板块关联**为名称、代码关键词匹配，"
            "可能存在误判或遗漏，仅供参考。\n\n"
        )
        push_lines: list[str] = [
            f"📰 要闻速览（交易日 {date}）",
            "（以下为快讯摘要，完整复盘见下文）",
            "",
        ]

        if related:
            lines.append("### 与龙头池 / 主线可能相关\n")
            for tag, summary, hint in related[:10]:
                ts = _truncate_news_line(summary, 160)
                lines.append(f"- **〔{hint}〕** {tag}：{ts}\n")
                if len(push_lines) < 22:
                    push_lines.append(
                        f"【关联·{hint}】{_truncate_news_line(summary, 100)}"
                    )
            lines.append("\n")

        if general:
            lines.append("### 宏观与市场要闻（摘录）\n")
            for tag, summary in general[:8]:
                ts = _truncate_news_line(summary, 160)
                lines.append(f"- {tag}：{ts}\n")
                if len(push_lines) < 22:
                    push_lines.append(
                        f"【要闻】{_truncate_news_line(summary, 100)}"
                    )
            lines.append("\n")

        block = "".join(lines)
        push_text = "\n".join(push_lines).strip()
        if len(push_text) > 2400:
            push_text = push_text[:2380] + "\n…（要闻已截断）"
        if not related and not general:
            block = (
                "\n## 【财经要闻·与程序观察标的】\n"
                "- 今日未解析到有效要闻条目。\n\n"
            )
            return block, ""
        return block, push_text + "\n\n---\n\n"

    def get_market_summary(self, date):
        """获取完整市场摘要（文本形式）"""
        self._last_news_push_prefix = ""
        self._last_auction_meta = {}
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
        north_money, north_status = self.get_north_money(date)

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
        if north_status == "fetch_failed":
            summary += "- 北向资金净流入：**获取失败**（网络或接口原因，勿作为核心依据）\n"
        elif north_status == "empty_df":
            summary += "- 北向资金：**返回空表**（可信度低）\n"
        elif north_status == "ok_zero":
            summary += (
                "- 北向资金净流入：**0 亿**（接口口径；可能为当日无成交或统计为零，请结合其它指标）\n"
            )
        else:
            summary += f"- 北向资金净流入：{north_money}亿\n"
        summary += f"- 情绪温度：{sentiment_temp}°C\n"
        summary += f"- 市场阶段：{market_phase}\n"
        summary += f"- 建议仓位：{position_suggestion}\n\n"

        # 板块排名
        if not df_sector.empty:
            summary += "## 板块资金流向排名（前五）\n"
            summary += (
                f"> **口径说明**：以下为东财等行业资金流相关接口的快照，与复盘日 **{date}** "
                "的严格对齐可能存在偏差，仅作板块强弱结构参考。\n\n"
            )
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

            ah_text, ah_meta = build_auction_halfway_report(date, trade_days, self, df_zt)
            self._last_auction_meta = dict(ah_meta) if isinstance(ah_meta, dict) else {}
            summary += ah_text
            tp = ah_meta.get("top_pool") or []
            if tp:
                summary += self.get_lhb_snippet_for_codes(
                    date, [p["code"] for p in tp[:5]]
                )
            nb_block, nb_push = self.get_finance_news_bundle(date, ah_meta)
            summary += nb_block
            self._last_news_push_prefix = nb_push
            summary += _append_ai_context(
                ah_meta,
                zt_count=zt_count,
                dt_count=dt_count,
                zb_count=zb_count,
                premium=premium,
                premium_note=str(premium_note),
                sector_empty=df_sector.empty,
                north_value=north_money,
                north_status=north_status,
            )
        except Exception as e:
            summary += f"\n## 【次日竞价半路模式】选股\n- 执行异常：{e!s}\n\n"
            self._last_news_push_prefix = ""
            self._last_auction_meta = {}

        return summary, date  # 返回可能调整后的日期
