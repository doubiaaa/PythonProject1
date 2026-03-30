import io
import json
import os
import re
import time
from contextlib import redirect_stdout
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import akshare as ak
import pandas as pd
from requests.exceptions import ChunkedEncodingError, ConnectionError, Timeout
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import data_source_config as _dsc
from app.services.data_source_errors import DataSourceExhaustedError, DataSourceInvalidError
from app.utils.disk_cache import df_to_payload, payload_to_df
from app.utils.logger import get_logger

# 板块接口为「今日」行业资金流，与复盘日无关；缓存键勿绑定 date，避免误判
SECTOR_LIVE_CACHE_KEY = "sector_fund_flow_rank_live"
# 昨日涨停溢价：超过该数量则走全市场 spot，避免过多单股请求
YEST_PREMIUM_HIST_MAX_CODES = 100
# 同一请求内可能多次拉全市场行情，短 TTL 复用
SPOT_EM_CACHE_TTL_SEC = 90
# 财联社要闻接口为「最新」列表，短缓存减轻重复请求
FINANCE_NEWS_CACHE_KEY = "finance_news_main_cx"
FINANCE_NEWS_CACHE_TTL_SEC = 600
# 个股主力净流入排名（今日）
INDIVIDUAL_FUND_FLOW_CACHE_KEY = "individual_fund_flow_rank_today"
INDIVIDUAL_FUND_FLOW_CACHE_TTL_SEC = 120
# 概念板块成分（按板块名缓存）
CONCEPT_CONS_CACHE_TTL_SEC = 600
# 分笔探测（按代码短缓存）
INTRADAY_TICK_CACHE_TTL_SEC = 60

_log = get_logger(__name__)

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))


def _data_source_cfg() -> dict:
    try:
        from app.utils.config import ConfigManager

        ds = ConfigManager().get("data_source")
        return ds if isinstance(ds, dict) else {}
    except Exception:
        return {}


def _cache_dir() -> str:
    base = _data_source_cfg().get("cache_dir") or "data_cache"
    if os.path.isabs(base):
        p = base
    else:
        p = os.path.join(_PROJECT_ROOT, str(base).replace("/", os.sep))
    os.makedirs(p, exist_ok=True)
    return p


def _cache_ttl_sec() -> int:
    days = float(_data_source_cfg().get("cache_expire_days", 1))
    return max(60, int(days * 86400))


def _cache_key(prefix: str, date: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", f"{prefix}_{str(date)[:12]}")
    return os.path.join(_cache_dir(), f"{safe}.json")


def _read_cache(prefix: str, date: str):
    """读 data_cache 下 JSON；超 TTL 视为未命中。"""
    path = _cache_key(prefix, date)
    if not os.path.isfile(path):
        return None
    if time.time() - os.path.getmtime(path) > _cache_ttl_sec():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_cache(prefix: str, date: str, data) -> None:
    path = _cache_key(prefix, date)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


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


def _code_to_tick_js_symbol(code: str) -> str:
    """腾讯分笔接口用的市场前缀 + 6 位代码。"""
    c = re.sub(r"[^0-9]", "", str(code))[:6].zfill(6)
    if not c or len(c) < 6:
        return "sz000001"
    if c[0] in ("8", "4"):
        return f"bj{c}"
    if c[0] == "6":
        return f"sh{c}"
    return f"sz{c}"


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
        self._last_email_kpi: dict = {}
        self._last_dragon_trader_meta: dict = {}
        self._tick_js_cache: dict[str, tuple[float, Optional[pd.DataFrame]]] = {}

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
        """全 A 行情（东财优先，失败或空表则新浪 stock_zh_a_spot）短缓存。"""
        now = time.time()
        if (
            self._spot_em_df is not None
            and now - self._spot_em_cache_ts < SPOT_EM_CACHE_TTL_SEC
        ):
            return self._spot_em_df
        df = None
        try:
            df = ak.stock_zh_a_spot_em()
        except Exception as e:
            print(f"stock_zh_a_spot_em 失败，将尝试新浪备用源: {e}")
        if df is None or df.empty:
            try:
                df = ak.stock_zh_a_spot()
                if df is not None and not df.empty:
                    print("已使用新浪 stock_zh_a_spot 作为全市场行情备用源")
            except Exception as e2:
                print(f"stock_zh_a_spot 备用源失败: {e2}")
                df = pd.DataFrame()
        self._spot_em_df = df
        self._spot_em_cache_ts = now
        return df

    def get_individual_fund_flow_rank_df(self) -> pd.DataFrame:
        """当日个股主力净流入排名（东财）；独立短 TTL 缓存。"""
        key = INDIVIDUAL_FUND_FLOW_CACHE_KEY
        if key in self.cache:
            ts, data = self.cache[key]
            if time.time() - ts < INDIVIDUAL_FUND_FLOW_CACHE_TTL_SEC:
                return data.copy() if isinstance(data, pd.DataFrame) else pd.DataFrame()
        try:
            df = self.fetch_with_retry(
                ak.stock_individual_fund_flow_rank, indicator="今日"
            )
            if df is None:
                df = pd.DataFrame()
        except Exception as e:
            print(f"个股主力净流入排名获取失败: {e}")
            df = pd.DataFrame()
        self.cache[key] = (time.time(), df)
        return df

    def format_individual_fund_flow_markdown(
        self, df: pd.DataFrame, top_n: int
    ) -> str:
        """将个股资金流表转为 Markdown 表（列名随东财接口略有差异时做模糊匹配）。"""
        if df is None or df.empty or top_n <= 0:
            return ""
        sub = df.head(int(top_n)).copy()
        cols = sub.columns.tolist()
        rank_c = next((c for c in cols if "序号" in str(c)), cols[0] if cols else None)
        code_c = next((c for c in cols if str(c).strip() == "代码"), None)
        if not code_c:
            code_c = next((c for c in cols if "代码" in str(c)), None)
        name_c = next(
            (
                c
                for c in cols
                if "名称" in str(c) and "板块" not in str(c) and "行业" not in str(c)
            ),
            None,
        )
        pct_c = next((c for c in cols if "涨跌幅" in str(c)), None)
        main_c = next(
            (
                c
                for c in cols
                if "主力净流入" in str(c) and "净额" in str(c)
            ),
            None,
        )
        lines = [
            "\n## 个股主力净流入·排名前列（今日·东财）\n",
            "> 观察当日资金集中方向；列口径为东财「今日」快照。\n\n",
        ]
        lines.append(
            "| 排名 | 代码 | 名称 | 涨跌幅 | 主力净流入-净额（元） |\n"
            "|------|------|------|--------|----------------------|\n"
        )
        for _, row in sub.iterrows():
            rk = row[rank_c] if rank_c and rank_c in sub.columns else ""
            cd = row[code_c] if code_c and code_c in sub.columns else ""
            nm = row[name_c] if name_c and name_c in sub.columns else ""
            pc = row[pct_c] if pct_c and pct_c in sub.columns else ""
            mn = row[main_c] if main_c and main_c in sub.columns else ""
            lines.append(f"| {rk} | {cd} | {nm} | {pc} | {mn} |\n")
        lines.append("\n")
        return "".join(lines)

    def get_concept_cons_em(self, board_name: str) -> pd.DataFrame:
        """概念板块成分股（东财）；按板块名单独短 TTL 缓存。"""
        sym = str(board_name).strip()
        if not sym:
            return pd.DataFrame()
        key = f"concept_cons_em_{sym}"
        if key in self.cache:
            ts, data = self.cache[key]
            if time.time() - ts < CONCEPT_CONS_CACHE_TTL_SEC:
                return data.copy() if isinstance(data, pd.DataFrame) else pd.DataFrame()
        try:
            df = self.fetch_with_retry(ak.stock_board_concept_cons_em, symbol=sym)
            if df is None:
                df = pd.DataFrame()
        except Exception as e:
            print(f"概念板块成分获取失败 ({sym}): {e}")
            df = pd.DataFrame()
        self.cache[key] = (time.time(), df)
        return df

    def format_concept_cons_snapshot_markdown(self, symbols: list[str]) -> str:
        """多个概念板块：成分数量与当日涨幅≥5% 家数（快照）。"""
        if not symbols:
            return ""
        lines = [
            "\n## 概念板块·成分股快照（东财）\n",
            "> 用于观察题材覆盖广度；**板块名须与东财概念名称一致**（可在 replay_config.json 的 "
            "`concept_board_symbols` 中配置）。\n\n",
        ]
        for sym in symbols:
            sym = str(sym).strip()
            if not sym:
                continue
            df = self.get_concept_cons_em(sym)
            if df is None or df.empty:
                lines.append(f"### {sym}\n- 未获取到成分或板块名不存在。\n\n")
                continue
            n = len(df)
            pct_col = next((c for c in df.columns if "涨跌幅" in str(c)), None)
            hi = 0
            if pct_col:
                p = pd.to_numeric(df[pct_col], errors="coerce")
                hi = int((p >= 5.0).sum())
            lines.append(
                f"### {sym}\n"
                f"- 成分股约 **{n}** 只；涨跌幅 **≥5%** 约 **{hi}** 只（当日快照口径）\n\n"
            )
        return "".join(lines)

    def fetch_intraday_tick_tx_js_safe(self, code: str) -> Optional[pd.DataFrame]:
        """腾讯历史分笔（akshare：stock_zh_a_tick_tx_js），短缓存；失败返回 None。"""
        sym = _code_to_tick_js_symbol(code)
        now = time.time()
        if sym in self._tick_js_cache:
            ts, prev = self._tick_js_cache[sym]
            if now - ts < INTRADAY_TICK_CACHE_TTL_SEC:
                return prev
        try:
            df = self.fetch_with_retry(ak.stock_zh_a_tick_tx_js, symbol=sym)
        except Exception as e:
            print(f"分笔数据获取失败 ({sym}): {e}")
            df = None
        self._tick_js_cache[sym] = (now, df)
        return df

    def fetch_with_retry(self, fetch_func, *args, **kwargs):
        """带重试：仅对连接/读超时类异常重试；其余一次失败即抛出。"""
        attempts = max(
            int(_data_source_cfg().get("retry_times", _dsc.AK_RETRY_ATTEMPTS)),
            self.retry_times + 1,
        )
        max_w = float(_data_source_cfg().get("timeout", 8))
        max_w = max(2.0, min(max_w, 32.0))

        @retry(
            stop=stop_after_attempt(attempts),
            wait=wait_exponential(multiplier=1, min=2, max=max_w),
            retry=retry_if_exception_type(
                (Timeout, ConnectionError, ChunkedEncodingError)
            ),
            reraise=True,
        )
        def _inner():
            buf = io.StringIO()
            with redirect_stdout(buf):
                res = fetch_func(*args, **kwargs)
            self._parse_progress(buf.getvalue())
            return res

        try:
            return _inner()
        except Exception as e:
            _log.error("AK 调用失败（已重试）: %s", e)
            raise DataSourceExhaustedError(str(e)) from e

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

    def _validate_required_columns(
        self, df: pd.DataFrame, required: tuple[str, ...], label: str
    ) -> None:
        if df is None or getattr(df, "empty", True):
            return
        miss = [c for c in required if c not in df.columns]
        if miss:
            _log.error("%s 缺少列 %s", label, miss)
            raise DataSourceInvalidError(f"{label} 缺少列: {miss}")

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
        disk = _read_cache("trade_cal_sina_v1", "global")
        if isinstance(disk, dict) and isinstance(disk.get("days"), list) and disk["days"]:
            self._set_cache(cache_key, disk["days"])
            return disk["days"]
        try:
            cal = ak.tool_trade_date_hist_sina()
            self._validate_required_columns(cal, _dsc.REQUIRED_TRADE_CAL_COLUMNS, "交易日历")
            trade_days = sorted(
                pd.to_datetime(cal["trade_date"]).dt.strftime("%Y%m%d").tolist()
            )
            self._set_cache(cache_key, trade_days)
            try:
                _write_cache("trade_cal_sina_v1", "global", {"days": trade_days})
            except OSError as ex:
                _log.warning("交易日历磁盘缓存失败: %s", ex)
            return trade_days
        except Exception as e:
            _log.error("获取交易日历失败: %s", e)
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
        disk = _read_cache("zt_pool_em", str(date)[:8])
        if disk is not None:
            df_disk = payload_to_df(disk)
            if df_disk is not None and not df_disk.empty and "code" in df_disk.columns:
                self._set_cache(cache_key, df_disk)
                return df_disk
        try:
            df = self.fetch_with_retry(ak.stock_zt_pool_em, date=date)
            if df is None or df.empty:
                self._set_cache(cache_key, pd.DataFrame())
                return pd.DataFrame()
            self._validate_required_columns(df, _dsc.REQUIRED_ZT_POOL_COLUMNS, "涨停池(原始)")
            # 重命名列
            df = df.rename(columns={
                '代码': 'code', '名称': 'name', '最新价': 'price', '涨跌幅': 'pct_chg',
                '连板数': 'lb', '炸板次数': 'zb_count', '所属行业': 'industry',
                '涨停原因': 'reason', '最后封板时间': 'fb_time', '首次封板时间': 'first_time'
            })
            df['lb'] = pd.to_numeric(df['lb'], errors='coerce').fillna(1).astype(int)
            self._set_cache(cache_key, df)
            try:
                _write_cache("zt_pool_em", str(date)[:8], df_to_payload(df))
            except OSError as ex:
                _log.warning("zt_pool 磁盘缓存失败: %s", ex)
            return df
        except Exception as e:
            _log.error("获取涨停数据失败: %s", e)
            self._set_cache(cache_key, pd.DataFrame())
            return pd.DataFrame()

    def get_dt_pool(self, date):
        """跌停股票池"""
        cache_key = f"dt_pool_{date}"
        if self._is_cache_valid(cache_key):
            return self._get_cache(cache_key)
        disk = _read_cache("dt_pool_em", str(date)[:8])
        if disk is not None:
            df_disk = payload_to_df(disk)
            if df_disk is not None and not df_disk.empty and "code" in df_disk.columns:
                self._set_cache(cache_key, df_disk)
                return df_disk
        try:
            df = self.fetch_with_retry(ak.stock_zt_pool_dtgc_em, date=date)
            if df is not None and not df.empty and "代码" in df.columns:
                self._validate_required_columns(df, _dsc.REQUIRED_DT_POOL_COLUMNS, "跌停池(原始)")
                df = df.rename(columns={"代码": "code", "名称": "name"})
            else:
                df = pd.DataFrame()
            self._set_cache(cache_key, df)
            if not df.empty:
                try:
                    _write_cache("dt_pool_em", str(date)[:8], df_to_payload(df))
                except OSError as ex:
                    _log.warning("dt_pool 磁盘缓存失败: %s", ex)
            return df
        except Exception:
            self._set_cache(cache_key, pd.DataFrame())
            return pd.DataFrame()

    def get_zb_pool(self, date):
        """炸板股票池"""
        cache_key = f"zb_pool_{date}"
        if self._is_cache_valid(cache_key):
            return self._get_cache(cache_key)
        disk = _read_cache("zb_pool_em", str(date)[:8])
        if disk is not None:
            df_disk = payload_to_df(disk)
            if df_disk is not None and not df_disk.empty and "code" in df_disk.columns:
                self._set_cache(cache_key, df_disk)
                return df_disk
        try:
            df = self.fetch_with_retry(ak.stock_zt_pool_zbgc_em, date=date)
            if df is not None and not df.empty and "代码" in df.columns:
                self._validate_required_columns(df, _dsc.REQUIRED_ZB_POOL_COLUMNS, "炸板池(原始)")
                df = df.rename(columns={"代码": "code", "名称": "name"})
            else:
                df = pd.DataFrame()
            self._set_cache(cache_key, df)
            if not df.empty:
                try:
                    _write_cache("zb_pool_em", str(date)[:8], df_to_payload(df))
                except OSError as ex:
                    _log.warning("zb_pool 磁盘缓存失败: %s", ex)
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

    def _norm_code(self, c) -> str:
        return re.sub(r"[^0-9]", "", str(c))[:6].zfill(6)

    def _pct_map_for_codes_on_date(self, codes: list, date_str: str) -> dict[str, float]:
        """按代码拉取当日涨跌幅，返回 code→pct（失败则不含该键）。"""
        out: dict[str, float] = {}
        if not codes:
            return out

        def one(raw):
            c = self._norm_code(raw)
            try:
                df = ak.stock_zh_a_hist(
                    symbol=c,
                    period="daily",
                    start_date=date_str,
                    end_date=date_str,
                    adjust="",
                )
                if df is not None and not df.empty and "涨跌幅" in df.columns:
                    return c, float(df["涨跌幅"].iloc[-1])
            except Exception:
                pass
            return c, None

        max_workers = min(12, max(1, len(codes)))
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(one, c) for c in codes]
            for fut in as_completed(futures):
                c, v = fut.result()
                if v is not None:
                    out[c] = v
        return out

    def _pct_map_from_spot_for_codes(self, codes: list) -> dict[str, float]:
        """用全市场 snapshot 匹配代码（样本过大时替代逐只 hist）。"""
        if not codes:
            return {}
        want = {self._norm_code(c) for c in codes}
        all_df = self.get_stock_zh_a_spot_em_cached()
        if all_df is None or all_df.empty or "代码" not in all_df.columns:
            return {}
        all_df = all_df.copy()
        all_df["code"] = all_df["代码"].apply(
            lambda x: re.sub(r"[^0-9]", "", str(x))[:6].zfill(6)
        )
        pct_col = "涨跌幅" if "涨跌幅" in all_df.columns else None
        if not pct_col:
            return {}
        sub = all_df[all_df["code"].isin(want)]
        out: dict[str, float] = {}
        for _, row in sub.iterrows():
            try:
                out[str(row["code"])] = float(row[pct_col])
            except Exception:
                continue
        return out

    def _spot_red_green_counts(self) -> tuple[Optional[int], Optional[int]]:
        """全 A 涨跌家数（东财 spot），失败返回 (None, None)。"""
        try:
            df = self.get_stock_zh_a_spot_em_cached()
            if df is None or df.empty or "涨跌幅" not in df.columns:
                return None, None
            s = pd.to_numeric(df["涨跌幅"], errors="coerce")
            up = int((s > 0).sum())
            down = int((s < 0).sum())
            return up, down
        except Exception:
            return None, None

    def compute_ladder_history_5d(
        self, date: str, trade_days: list[str]
    ) -> tuple[list[dict], str]:
        """
        近 5 个交易日（含当日）每日涨停连板梯队，用于历史对比与情绪倾向。
        返回 (rows, trend_text)。
        """
        rows: list[dict] = []
        if not trade_days or date not in trade_days:
            return rows, "数据不足（交易日历）"
        idx = trade_days.index(date)
        start = max(0, idx - 4)
        days = trade_days[start : idx + 1]
        multi_series: list[int] = []
        for d in days:
            df = self.get_zt_pool(d)
            if df is None or df.empty or "lb" not in df.columns:
                rows.append(
                    {
                        "date": d,
                        "ladder": {},
                        "total_zt": 0,
                        "max_lb": 0,
                        "multi_board_sum": 0,
                    }
                )
                multi_series.append(0)
                continue
            lb_stats = df["lb"].value_counts().sort_index()
            ladder = {int(k): int(v) for k, v in lb_stats.items()}
            total = len(df)
            max_lb = int(df["lb"].max())
            multi = sum(int(v) for k, v in ladder.items() if int(k) >= 2)
            rows.append(
                {
                    "date": d,
                    "ladder": ladder,
                    "total_zt": total,
                    "max_lb": max_lb,
                    "multi_board_sum": multi,
                }
            )
            multi_series.append(multi)
        if len(multi_series) < 2:
            return rows, "历史样本不足"
        last = multi_series[-1]
        prev_avg = sum(multi_series[:-1]) / max(1, len(multi_series) - 1)
        if prev_avg < 1e-6:
            trend = "梯队震荡（基数过低，仅作参考）"
        elif last > prev_avg * 1.08:
            trend = "梯队加强（≥2 连家数明显高于近几日均值，接力情绪偏强）"
        elif last < prev_avg * 0.92:
            trend = "梯队减弱（≥2 连家数低于近几日均值，接力情绪收敛）"
        else:
            trend = "梯队震荡（连板结构变化不大）"
        return rows, trend

    def _format_ladder_history_markdown(self, rows: list[dict], trend: str) -> str:
        """近 5 日连板梯队 Markdown 表 + 情绪倾向句。"""
        if not rows:
            return ""
        lines = [
            "\n### 【连板梯队·近5交易日对比】\n",
            "| 日期 | 涨停合计 | ≥2连合计 | 2板 | 3板 | 4板 | 5板+ | 最高连板 |\n",
            "|------|----------|----------|-----|-----|-----|------|----------|\n",
        ]
        for r in rows:
            lad = r.get("ladder") or {}
            ge5 = sum(int(lad[k]) for k in lad if int(k) >= 5)
            lines.append(
                f"| {r.get('date','')} | {r.get('total_zt',0)} | {r.get('multi_board_sum',0)} "
                f"| {lad.get(2, 0)} | {lad.get(3, 0)} | {lad.get(4, 0)} | {ge5} | {r.get('max_lb',0)}板 |\n"
            )
        lines.append(f"\n- **情绪倾向（程序口径）**：{trend}\n")
        return "".join(lines)

    def build_dragon_trader_snapshot(
        self,
        date: str,
        trade_days: list[str],
        df_zt: pd.DataFrame,
        df_dt: pd.DataFrame,
    ) -> tuple[str, dict]:
        """
        龙头短线选手所需程序量化：连板梯队、大面、溢价拆分、总龙头、中位断板、分离候选等。
        分离确认无逐笔分时，仅提供同日强弱对比候选。
        """
        meta: dict = {
            "trade_date": date,
            "ladder": {},
            "red_count": None,
            "green_count": None,
            "yest_zt_count": 0,
            "big_face_count": 0,
            "premium_first_board_pct": None,
            "premium_multi_board_pct": None,
            "top_dragon": None,
            "mid_tier_yesterday": [],
            "separation_candidates": [],
            "notes": [],
            "ladder_history_5d": [],
            "ladder_trend": "",
        }
        lines: list[str] = [
            "\n## 【龙头选手·程序量化快照】\n",
            "> 以下由程序按公开日 K / 涨停池计算；**分离确认**无分时数据，"
            "「候选」为同日相对最高连板股的补涨/卡位观察名单，须结合盘面验证。\n\n",
        ]
        if not trade_days or date not in trade_days:
            lines.append("- 交易日历异常，本块跳过。\n\n")
            return "".join(lines), meta

        idx = trade_days.index(date)
        hist_rows, hist_trend = self.compute_ladder_history_5d(date, trade_days)
        meta["ladder_history_5d"] = hist_rows
        meta["ladder_trend"] = hist_trend
        lines.append(self._format_ladder_history_markdown(hist_rows, hist_trend))

        if idx == 0:
            lines.append("- 无上一交易日，昨日涨停衍生指标跳过。\n\n")
            meta["notes"].append("no_prior_trade_day")
            return "".join(lines), meta

        yest_date = trade_days[idx - 1]
        yest_zt = self.get_zt_pool(yest_date)
        if yest_zt is None or yest_zt.empty:
            lines.append("- 昨日涨停池为空，无法计算大面数、溢价拆分、中位股表现。\n\n")
            meta["notes"].append("empty_yest_zt")
            return "".join(lines), meta

        yest_codes = [self._norm_code(c) for c in yest_zt["code"].tolist()]
        meta["yest_zt_count"] = len(yest_codes)

        up_n, down_n = self._spot_red_green_counts()
        meta["red_count"], meta["green_count"] = up_n, down_n
        if up_n is not None and down_n is not None:
            lines.append(f"- **涨跌家数（全 A 快照）**：上涨约 **{up_n}** 家，下跌约 **{down_n}** 家\n")

        if not df_zt.empty and "lb" in df_zt.columns:
            lb_stats = df_zt["lb"].value_counts().sort_index()
            ladder = {int(k): int(v) for k, v in lb_stats.items()}
            meta["ladder"] = ladder
            parts = [f"{k}连板×{v}只" for k, v in sorted(ladder.items())]
            lines.append(f"- **连板梯队（当日涨停池）**：{'，'.join(parts)}\n")
            max_lb = int(df_zt["lb"].max())
            df_m = df_zt[df_zt["lb"] == max_lb].copy()
            if not df_m.empty and "first_time" in df_m.columns:
                dragon = df_m.sort_values("first_time").iloc[0]
            else:
                dragon = df_m.iloc[0]
            td = {
                "code": str(dragon.get("code", "")),
                "name": str(dragon.get("name", "")),
                "lb": int(dragon.get("lb", 0) or 0),
                "industry": str(dragon.get("industry", "")),
            }
            meta["top_dragon"] = td
            try:
                d_pct = float(dragon["pct_chg"])
            except Exception:
                d_pct = None
            lines.append(
                f"- **总龙头（当日最高连板）**：{td['name']}（`{td['code']}`）"
                f" **{td['lb']}连板**，行业：{td['industry']}；"
                f"当日涨跌幅：{d_pct if d_pct is not None else '—'}%\n"
            )
            dcode = self._norm_code(td["code"])
            if (
                not df_zt.empty
                and "pct_chg" in df_zt.columns
                and "code" in df_zt.columns
                and max_lb >= 2
            ):
                alt = df_zt[
                    (df_zt["lb"] >= 2)
                    & (df_zt["code"].astype(str).map(self._norm_code) != dcode)
                ].nlargest(5, "pct_chg")
                cand = []
                for _, r in alt.iterrows():
                    item = {
                        "code": self._norm_code(r.get("code")),
                        "name": str(r.get("name", "")),
                        "lb": int(r.get("lb", 0) or 0),
                        "today_pct": round(float(r.get("pct_chg", 0)), 2)
                        if pd.notna(r.get("pct_chg"))
                        else None,
                    }
                    cand.append(item)
                meta["separation_candidates"] = cand
                if cand:
                    lines.append("- **分离确认·候选（非分时，补涨/卡位观察）**：\n")
                    for it in cand[:5]:
                        lines.append(
                            f"  - {it['name']}（`{it['code']}`）{it['lb']}连板，"
                            f"当日 {it['today_pct']}%\n"
                        )
                else:
                    lines.append("- **分离确认·候选**：无同梯队备选或数据不足。\n")

        pct_map: dict[str, float] = {}
        if len(yest_codes) <= YEST_PREMIUM_HIST_MAX_CODES:
            pct_map = self._pct_map_for_codes_on_date(yest_codes, date)
        if len(pct_map) < max(3, len(yest_codes) // 3):
            pct_map = self._pct_map_from_spot_for_codes(yest_codes)

        big_face = 0
        dt_codes: set[str] = set()
        if df_dt is not None and not df_dt.empty and "code" in df_dt.columns:
            dt_codes = {self._norm_code(x) for x in df_dt["code"].tolist()}
        for c in yest_codes:
            pv = pct_map.get(c)
            in_dt = c in dt_codes
            if in_dt or (pv is not None and float(pv) < -5.0):
                big_face += 1
        meta["big_face_count"] = big_face
        lines.append(
            f"- **大面数（程序口径）**：昨日涨停股中今日 **跌幅 < -5%** 或 **跌停** 计 **{big_face}** 只（每票最多计一次）\n"
        )

        if "lb" in yest_zt.columns:
            y1 = yest_zt[yest_zt["lb"] == 1]
            ym = yest_zt[yest_zt["lb"] >= 2]
            c1 = [self._norm_code(c) for c in y1["code"].tolist()]
            cm_ = [self._norm_code(c) for c in ym["code"].tolist()]
            v1 = [pct_map[c] for c in c1 if c in pct_map]
            vm = [pct_map[c] for c in cm_ if c in pct_map]
            if v1:
                meta["premium_first_board_pct"] = round(sum(v1) / len(v1), 2)
                lines.append(
                    f"- **昨日涨停溢价·首板子样本均值**：**{meta['premium_first_board_pct']}%** "
                    f"（{len(v1)}/{len(c1)} 只有效）\n"
                )
            if vm:
                meta["premium_multi_board_pct"] = round(sum(vm) / len(vm), 2)
                lines.append(
                    f"- **昨日涨停溢价·连板（≥2）子样本均值**：**{meta['premium_multi_board_pct']}%** "
                    f"（{len(vm)}/{len(cm_)} 只有效）\n"
                )

        mid_rows = yest_zt[yest_zt["lb"].isin([3, 4])] if "lb" in yest_zt.columns else pd.DataFrame()
        if not mid_rows.empty:
            lines.append("- **中位股（昨日 3～4 连板）今日表现**：\n")
            for _, row in mid_rows.head(12).iterrows():
                c = self._norm_code(row.get("code"))
                nm = str(row.get("name", ""))
                lb0 = int(row.get("lb", 0) or 0)
                pv = pct_map.get(c)
                in_dt = c in dt_codes
                note = "跌停" if in_dt else (f"{pv:.2f}%" if pv is not None else "—")
                meta["mid_tier_yesterday"].append(
                    {
                        "code": c,
                        "name": nm,
                        "yesterday_lb": lb0,
                        "today_pct": round(pv, 2) if pv is not None else None,
                        "limit_down_today": in_dt,
                    }
                )
                lines.append(f"  - {nm}（`{c}`）昨 {lb0} 连板 → 今日 {note}\n")

        top5_ind = []
        if not df_zt.empty and "industry" in df_zt.columns:
            ic = df_zt["industry"].value_counts().head(5)
            for ind, cnt in ic.items():
                top5_ind.append(f"{ind}（涨停 {cnt} 家）")
        if top5_ind:
            lines.append(
                f"- **板块涨停热度（行业分布 Top）**：{'；'.join(top5_ind)}；"
                f"成分股总数/占比需另行 Level2 数据，此处仅家数。\n"
            )

        lines.append("\n")
        return "".join(lines), meta

    def get_north_money(self, date) -> tuple[float, str]:
        """
        北向净流入（亿元）与状态。
        状态：ok / ok_zero / empty_df / fetch_failed
        """
        ds = str(date)[:8]
        cached = _read_cache("north_net", ds)
        if isinstance(cached, dict) and "value" in cached and "status" in cached:
            return float(cached["value"]), str(cached["status"])
        try:
            df = self.fetch_with_retry(
                ak.stock_hsgt_north_net_flow_sina, date=date
            )
            if df is None or df.empty:
                out = (0.0, "empty_df")
                _write_cache("north_net", ds, {"value": out[0], "status": out[1]})
                return out
            if "北向资金净流入" in df.columns:
                net_flow = df["北向资金净流入"].iloc[0]
            elif "净流入" in df.columns:
                net_flow = df["净流入"].iloc[0]
            else:
                out = (0.0, "empty_df")
                _write_cache("north_net", ds, {"value": out[0], "status": out[1]})
                return out
            val = round(float(net_flow) / 1e8, 2)
            if val == 0.0:
                st = "ok_zero"
            else:
                st = "ok"
            _write_cache("north_net", ds, {"value": val, "status": st})
            return val, st
        except Exception as e:
            _log.error("获取北向资金数据失败: %s", e)
            return 0.0, "fetch_failed"

    def get_lhb_snippet_for_codes(self, date: str, codes: list[str]) -> str:
        """新浪龙虎榜日表与龙头池代码交集，失败则返回说明行。"""
        if not codes:
            return ""
        cache_key = f"lhb_daily_{date}"
        if self._is_cache_valid(cache_key):
            df = self._get_cache(cache_key)
        else:
            df = None
            disk = _read_cache("lhb_daily", str(date)[:8])
            if disk is not None:
                df = payload_to_df(disk)
            if df is None or getattr(df, "empty", True):
                try:
                    df = self.fetch_with_retry(
                        ak.stock_lhb_detail_daily_sina, date=date
                    )
                    if df is None:
                        df = pd.DataFrame()
                except Exception as e:
                    _log.error("龙虎榜日表获取失败: %s", e)
                    df = pd.DataFrame()
            self._set_cache(cache_key, df)
            if df is not None and not df.empty:
                try:
                    _write_cache("lhb_daily", str(date)[:8], df_to_payload(df))
                except OSError as ex:
                    _log.warning("龙虎榜磁盘缓存失败: %s", ex)
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
            disk = _read_cache("finance_news_cx", "latest")
            if disk is not None:
                df = payload_to_df(disk)
                if df is not None and not df.empty:
                    self._set_cache(FINANCE_NEWS_CACHE_KEY, df)
        if df is None or getattr(df, "empty", True):
            try:
                df = self.fetch_with_retry(ak.stock_news_main_cx)
            except Exception as e:
                _log.error("财经要闻获取失败: %s", e)
                df = pd.DataFrame()
            self._set_cache(FINANCE_NEWS_CACHE_KEY, df)
            if df is not None and not df.empty:
                try:
                    _write_cache("finance_news_cx", "latest", df_to_payload(df))
                except OSError as ex:
                    _log.warning("要闻磁盘缓存失败: %s", ex)
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
        self._last_email_kpi = {}
        self._last_dragon_trader_meta = {}
        summary = ""
        trade_days = self.get_trade_cal()
        if not trade_days:
            summary += "## 基础数据\n- 无法获取交易日历，请检查网络或数据源。\n\n"
            self._last_email_kpi = {}
            self._last_dragon_trader_meta = {}
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

        # 个股主力净流入排名、概念板块成分（可选，见 replay_config.json）
        try:
            from app.utils.config import ConfigManager

            cm = ConfigManager()
            if cm.get("enable_individual_fund_flow_rank", True):
                top_n = int(cm.get("individual_fund_flow_top_n", 12) or 12)
                top_n = max(3, min(30, top_n))
                df_ind = self.get_individual_fund_flow_rank_df()
                if df_ind is not None and not df_ind.empty:
                    summary += self.format_individual_fund_flow_markdown(df_ind, top_n)
                else:
                    summary += (
                        "\n## 个股主力净流入（今日）\n"
                        "- 接口暂无数据或获取失败。\n\n"
                    )
            if cm.get("enable_concept_cons_snapshot", True):
                raw_syms = cm.get("concept_board_symbols") or []
                if isinstance(raw_syms, str):
                    raw_syms = [
                        x.strip() for x in raw_syms.replace("，", ",").split(",") if x.strip()
                    ]
                elif not isinstance(raw_syms, list):
                    raw_syms = []
                if raw_syms:
                    summary += self.format_concept_cons_snapshot_markdown(
                        [str(x).strip() for x in raw_syms if str(x).strip()][:8]
                    )
        except Exception as e:
            summary += f"\n## 扩展行情数据\n- 个股资金流/概念快照跳过：{e!s}\n\n"

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
            snap_md, snap_meta = self.build_dragon_trader_snapshot(
                date, trade_days, df_zt, df_dt
            )
            summary += snap_md
            self._last_dragon_trader_meta = snap_meta
        except Exception as e:
            summary += (
                f"\n## 【龙头选手·程序量化快照】\n"
                f"- 程序计算异常（已跳过本块）：{e!s}\n\n"
            )
            self._last_dragon_trader_meta = {"error": str(e)[:300]}

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

        try:
            from app.utils.config import ConfigManager

            cm2 = ConfigManager()
            if cm2.get("enable_intraday_tick_probe", False):
                raw = str(cm2.get("intraday_tick_probe_symbol") or "").strip()
                if raw:
                    tdf = self.fetch_intraday_tick_tx_js_safe(raw)
                    if tdf is not None and not tdf.empty:
                        summary += (
                            "\n## 分时成交探测（腾讯分笔·调试）\n"
                            f"- 标的 `{raw}`：共 **{len(tdf)}** 条分笔记录。"
                            " 仅供调试，接口不稳定，勿单独作为交易依据。\n\n"
                        )
                    else:
                        summary += (
                            "\n## 分时成交探测（腾讯分笔·调试）\n"
                            f"- 标的 `{raw}`：**未取到数据**（非交易时段或接口限制）。\n\n"
                        )
        except Exception as e:
            summary += f"\n## 分时成交探测\n- 跳过：{e!s}\n\n"

        self._last_email_kpi = {
            "zt_count": int(zt_count),
            "dt_count": int(dt_count),
            "zb_count": int(zb_count),
            "zhaban_rate": float(zhaban_rate),
            "premium": float(premium) if premium != -99 else None,
            "premium_note": str(premium_note),
            "position_suggestion": str(position_suggestion),
        }
        return summary, date  # 返回可能调整后的日期
