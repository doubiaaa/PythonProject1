import io
import json
import os
import re
import threading
import time
from contextlib import redirect_stdout
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Tuple

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
from app.services.data_source_errors import (
    DataSourceCircuitOpenError,
    DataSourceExhaustedError,
    DataSourceInvalidError,
)
from app.utils.disk_cache import df_to_payload, payload_to_df
from app.utils.ladder_utils import ladder_level_count, max_lb_from_ladder_dict
from app.utils.logger import get_logger

# 板块接口为「今日」行业资金流，与复盘日无关；缓存键勿绑定 date，避免误判
SECTOR_LIVE_CACHE_KEY = "sector_fund_flow_rank_live"
CONCEPT_FLOW_CACHE_KEY = "sector_fund_flow_concept_live"
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
# 东财炸板股池 stock_zt_pool_zbgc_em 仅支持「当前时点」最近约 30 个交易日，更早勿请求（避免反复报错）
ZB_POOL_EM_LOOKBACK_TRADING_DAYS = 30

_log = get_logger(__name__)


def _parallel_fetch_workers() -> int:
    """并行拉取涨跌停池等时的线程数上限（配置 fetch_parallel_max_workers）。"""
    try:
        from app.utils.config import ConfigManager

        w = int(ConfigManager().get("fetch_parallel_max_workers", 8) or 8)
        return max(2, min(16, w))
    except Exception:
        return 8


def _market_summary_parallel_enabled() -> bool:
    try:
        from app.utils.config import ConfigManager

        return bool(ConfigManager().get("market_summary_parallel_fetch", True))
    except Exception:
        return True

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


def compute_short_term_market_phase(
    sentiment_temp: int,
    zt_count: int,
    dt_count: int,
    zhaban_rate: float,
    max_lb: int,
    premium: float,
) -> tuple[str, str]:
    """
    短线复盘四象限：主升 / 高位震荡 / 退潮·冰点 / 混沌·试错。
    premium 为 -99 表示昨日涨停溢价不可用，内部不按溢价判冰点。
    """
    prem_ok = premium != -99
    prem = float(premium) if prem_ok else 0.0

    if sentiment_temp < 32:
        return "退潮·冰点期", "0-10%"
    if zt_count < 14 and dt_count > zt_count + 15:
        return "退潮·冰点期", "0-10%"
    if max_lb <= 2 and zt_count < 20 and prem_ok and prem < -0.8:
        return "退潮·冰点期", "0-10%"

    if sentiment_temp >= 80:
        return "主升期", "80%"
    if max_lb >= 6 and zt_count >= 25:
        return "主升期", "80%"
    if max_lb >= 5 and zhaban_rate <= 36 and zt_count >= 32:
        return "主升期", "80%"

    if 36 <= sentiment_temp <= 74 and zhaban_rate >= 44:
        return "混沌·试错期", "15-25%"
    if (
        34 <= sentiment_temp <= 70
        and prem_ok
        and -0.3 <= prem <= 1.0
        and max_lb in (2, 3)
        and zt_count >= 18
    ):
        return "混沌·试错期", "15-25%"

    return "高位震荡期", "30%"


class DataFetcher:
    """数据获取类（含冗余、重试、缓存）"""

    _disk_cache_sweep_done = False
    _disk_cache_sweep_lock = threading.Lock()

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
        self._last_premium_analysis: dict = {}
        self._last_big_face_count: int = 0
        self._last_sentiment_forecast: str = ""
        self._last_dragon_trader_meta: dict = {}
        self._last_finance_news_related: list = []
        self._last_finance_news_general: list = []
        self._tick_js_cache: dict[str, tuple[float, Optional[pd.DataFrame]]] = {}
        self._north_hist_em_df: Optional[pd.DataFrame] = None
        self._north_hist_em_ts: float = 0.0
        self._cache_lock = threading.Lock()
        self._spot_fetch_lock = threading.Lock()
        with DataFetcher._disk_cache_sweep_lock:
            if not DataFetcher._disk_cache_sweep_done:
                DataFetcher._disk_cache_sweep_done = True
                try:
                    from app.utils.config import ConfigManager
                    from app.utils.disk_cache import cache_dir, sweep_expired_json_files

                    _ttl = int(
                        ConfigManager().get("disk_cache_sweep_ttl_sec", 86400) or 0
                    )
                    if _ttl > 0:
                        sweep_expired_json_files(
                            cache_root=cache_dir(), ttl_sec=_ttl
                        )
                except Exception:
                    pass

    def _is_cache_valid(self, key):
        with self._cache_lock:
            if key in self.cache:
                ts, _ = self.cache[key]
                if time.time() - ts < self.cache_expire:
                    return True
                del self.cache[key]
        return False

    def _get_cache(self, key):
        with self._cache_lock:
            return self.cache[key][1] if key in self.cache else None

    def _set_cache(self, key, data):
        with self._cache_lock:
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
        with self._spot_fetch_lock:
            now = time.time()
            if (
                self._spot_em_df is not None
                and now - self._spot_em_cache_ts < SPOT_EM_CACHE_TTL_SEC
            ):
                return self._spot_em_df
            df = None
            try:
                df = self.fetch_with_retry(ak.stock_zh_a_spot_em)
            except Exception as e:
                _log.warning("stock_zh_a_spot_em 失败，将尝试新浪备用源: %s", e)
            if df is None or getattr(df, "empty", True):
                try:
                    df = self.fetch_with_retry(ak.stock_zh_a_spot)
                    if df is not None and not getattr(df, "empty", True):
                        _log.info("已使用新浪 stock_zh_a_spot 作为全市场行情备用源")
                except Exception as e2:
                    _log.warning("stock_zh_a_spot 备用源失败: %s", e2)
                    df = pd.DataFrame()
            self._spot_em_df = df
            self._spot_em_cache_ts = time.time()
            return df

    def get_individual_fund_flow_rank_df(self) -> pd.DataFrame:
        """当日个股主力净流入排名（东财）；独立短 TTL 缓存。"""
        key = INDIVIDUAL_FUND_FLOW_CACHE_KEY
        with self._cache_lock:
            if key in self.cache:
                ts, data = self.cache[key]
                if time.time() - ts < INDIVIDUAL_FUND_FLOW_CACHE_TTL_SEC:
                    return (
                        data.copy()
                        if isinstance(data, pd.DataFrame)
                        else pd.DataFrame()
                    )
        try:
            df = self.fetch_with_retry(
                ak.stock_individual_fund_flow_rank, indicator="今日"
            )
            if df is None:
                df = pd.DataFrame()
        except Exception as e:
            _log.warning("个股主力净流入排名获取失败: %s", e)
            df = pd.DataFrame()
        with self._cache_lock:
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
        with self._cache_lock:
            if key in self.cache:
                ts, data = self.cache[key]
                if time.time() - ts < CONCEPT_CONS_CACHE_TTL_SEC:
                    return (
                        data.copy()
                        if isinstance(data, pd.DataFrame)
                        else pd.DataFrame()
                    )
        try:
            df = self.fetch_with_retry(ak.stock_board_concept_cons_em, symbol=sym)
            if df is None:
                df = pd.DataFrame()
        except Exception as e:
            _log.warning("概念板块成分获取失败 (%s): %s", sym, e)
            df = pd.DataFrame()
        with self._cache_lock:
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
            _log.warning("分笔数据获取失败 (%s): %s", sym, e)
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

        from app.infrastructure.resilience import get_circuit

        cb = get_circuit("akshare")
        if not cb.allow_request():
            raise DataSourceCircuitOpenError(
                "数据源熔断中（连续失败过多），请稍后重试"
            ) from None
        try:
            out = _inner()
            cb.record_success()
            return out
        except Exception as e:
            cb.record_failure()
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
    def _parse_pct_cell_series(self, ser: pd.Series) -> pd.Series:
        """涨跌幅列：去除 %，'-' / 空 视为缺失 → 0（与东财表缺数据一致）。"""
        s = ser.astype(str).str.replace("%", "", regex=False).str.strip()
        s = s.replace({"-": "", "—": "", "nan": ""})
        return pd.to_numeric(s, errors="coerce").fillna(0.0)

    def _convert_money_to_float(self, money_str):
        """将带单位的金额字符串转换为以亿元为单位的浮点数"""
        if isinstance(money_str, (int, float)):
            return money_str / 1e8  # 如果已经是数值，假设单位为元，转为亿元
        try:
            s = str(money_str).strip()
            if s in ("-", "—", "", "nan", "None"):
                return 0.0
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
            cal = self.fetch_with_retry(ak.tool_trade_date_hist_sina)
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

    def is_zb_pool_em_available(self, date) -> bool:
        """
        东财炸板池接口仅覆盖最近约 ZB_POOL_EM_LOOKBACK_TRADING_DAYS 个交易日（相对当前日历末端）。
        超出范围则不应调用 ak.stock_zt_pool_zbgc_em，否则会触发「只能获取最近 30 个交易日」类错误并刷屏。
        """
        td = self.get_trade_cal()
        if not td:
            return True
        ds = str(date)[:8]
        if ds > td[-1]:
            return False
        valid = [x for x in td if x <= ds]
        if not valid:
            return False
        d_eff = valid[-1]
        if len(td) < ZB_POOL_EM_LOOKBACK_TRADING_DAYS:
            return True
        oldest = td[-ZB_POOL_EM_LOOKBACK_TRADING_DAYS]
        return d_eff >= oldest

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
            # 连板数：缺失→1；≤0 归一为 1（部分源用 0 表示首板，避免「最高连板」被算成 0）
            _lb = pd.to_numeric(df["lb"], errors="coerce").fillna(1).astype(int)
            df["lb"] = _lb.mask(_lb <= 0, 1)
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
        if not self.is_zb_pool_em_available(date):
            empty = pd.DataFrame()
            self._set_cache(cache_key, empty)
            return empty
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

    def _parse_fund_flow_rank_frame(self, df: pd.DataFrame, top_n: int) -> pd.DataFrame:
        """解析东财 stock_sector_fund_flow_rank 返回表，统一为 sector/pct/money。"""
        if df is None or df.empty:
            return pd.DataFrame()
        if all(col in df.columns for col in ["名称", "今日涨跌幅", "今日主力净流入-净额"]):
            df_result = df[["名称", "今日涨跌幅", "今日主力净流入-净额"]].rename(
                columns={
                    "名称": "sector",
                    "今日涨跌幅": "pct",
                    "今日主力净流入-净额": "money",
                }
            )
            df_result["pct"] = self._parse_pct_cell_series(df_result["pct"])
            df_result["money"] = df_result["money"].apply(self._convert_money_to_float)
            return df_result.sort_values("money", ascending=False).head(top_n)
        _log.warning("资金流表标准列名不存在，可用列: %s", df.columns.tolist())
        name_col = next((col for col in df.columns if "名称" in col), None)
        pct_col = next((col for col in df.columns if "涨跌幅" in col), None)
        money_col = next(
            (col for col in df.columns if "主力净流入" in col and "净额" in col),
            None,
        )
        if not (name_col and pct_col and money_col):
            return pd.DataFrame()
        df_result = df[[name_col, pct_col, money_col]].rename(
            columns={name_col: "sector", pct_col: "pct", money_col: "money"}
        )
        df_result["pct"] = self._parse_pct_cell_series(df_result["pct"])
        df_result["money"] = df_result["money"].apply(self._convert_money_to_float)
        return df_result.sort_values("money", ascending=False).head(top_n)

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
            df = self.fetch_with_retry(
                ak.stock_sector_fund_flow_rank,
                indicator="今日",
                sector_type="行业资金流",
            )

            if df is None or df.empty:
                _log.info("获取板块资金流向数据为空")
                self._set_cache(cache_key, pd.DataFrame())
                return pd.DataFrame()

            df_result = self._parse_fund_flow_rank_frame(df, 5)
            if not df_result.empty:
                self._set_cache(cache_key, df_result)
                return df_result
            self._set_cache(cache_key, pd.DataFrame())
            return pd.DataFrame()

        except Exception as e:
            _log.warning("获取板块排名失败: %s", e)
            # 尝试备用接口：stock_fund_flow_industry
            try:
                _log.info("尝试备用接口: stock_fund_flow_industry")
                df = self.fetch_with_retry(
                    ak.stock_fund_flow_industry, symbol="今日"
                )
                if df is not None and not df.empty:
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
                            df_result["pct"] = self._parse_pct_cell_series(df_result["pct"])
                            df_result['money'] = df_result['money'].apply(self._convert_money_to_float)
                            df_result = df_result.sort_values('money', ascending=False).head(5)
                            self._set_cache(cache_key, df_result)
                            return df_result
                        except Exception as e3:
                            _log.warning("数据转换失败: %s", e3)
            except Exception as e2:
                _log.warning("备用接口也失败: %s", e2)

            self._set_cache(cache_key, pd.DataFrame())
            return pd.DataFrame()

    def get_concept_fund_flow_rank(self, top_n: int = 12) -> pd.DataFrame:
        """
        东财「概念资金流」今日排行（与复盘日非严格对齐），用于复盘长图式「题材强弱」块。
        """
        cache_key = CONCEPT_FLOW_CACHE_KEY
        if self._is_cache_valid(cache_key):
            return self._get_cache(cache_key)
        try:
            df = self.fetch_with_retry(
                ak.stock_sector_fund_flow_rank,
                indicator="今日",
                sector_type="概念资金流",
            )
            if df is None or df.empty:
                self._set_cache(cache_key, pd.DataFrame())
                return pd.DataFrame()
            df_result = self._parse_fund_flow_rank_frame(df, top_n)
            self._set_cache(cache_key, df_result)
            return df_result
        except Exception as e:
            _log.warning("概念资金流排名获取失败: %s", e)
            self._set_cache(cache_key, pd.DataFrame())
            return pd.DataFrame()

    def _pct_chg_for_codes_on_date(self, codes, date_str):
        """按交易日拉取单日 K 线涨跌幅，避免 stock_zh_a_spot_em 全市场分页。"""
        if not codes:
            return []

        def one(code):
            c = re.sub(r"[^0-9]", "", str(code))[:6].zfill(6)
            try:
                df = self.fetch_with_retry(
                    ak.stock_zh_a_hist,
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
        if all_df is None or getattr(all_df, "empty", True):
            try:
                all_df = self.fetch_with_retry(ak.stock_zh_a_spot)
            except Exception as e:
                _log.warning("stock_zh_a_spot 备用失败: %s", e)
                return None
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
            _log.warning("计算溢价异常: %s", e)
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
                df = self.fetch_with_retry(
                    ak.stock_zh_a_hist,
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

    def _spot_turnover_rise_rate_flat(self) -> tuple[Optional[float], Optional[float], Optional[int]]:
        """
        全 A 成交额合计（亿元）与上涨家数占比（%）。
        东财 spot 成交额列多为元，合计后 /1e8；失败返回 (None, None, None)。
        """
        try:
            df = self.get_stock_zh_a_spot_em_cached()
            if df is None or df.empty or "涨跌幅" not in df.columns:
                return None, None, None
            s = pd.to_numeric(df["涨跌幅"], errors="coerce")
            up = int((s > 0).sum())
            down = int((s < 0).sum())
            flat = int((s == 0).sum())
            denom = up + down + flat
            rise_pct = round(up / denom * 100, 2) if denom else None
            amt_col = next((c for c in df.columns if "成交额" in str(c)), None)
            turnover_yi = None
            if amt_col:
                total = pd.to_numeric(df[amt_col], errors="coerce").sum()
                if total is not None and not (pd.isna(total)):
                    turnover_yi = float(total) / 1e8
            return turnover_yi, rise_pct, flat
        except Exception:
            return None, None, None

    def _spot_price_distribution_markdown(self) -> str:
        """全 A 涨跌幅区间分布（占当日有涨跌幅样本的比例）。"""
        try:
            df = self.get_stock_zh_a_spot_em_cached()
            if df is None or df.empty or "涨跌幅" not in df.columns:
                return ""
            s = pd.to_numeric(df["涨跌幅"], errors="coerce").dropna()
            n = len(s)
            if n <= 0:
                return ""

            def pct(cond) -> float:
                return round(float(cond.sum()) / n * 100, 2)

            rows = [
                (">7%", pct(s > 7)),
                ("5%~7%", pct((s > 5) & (s <= 7))),
                ("2%~5%", pct((s > 2) & (s <= 5))),
                ("0%~2%", pct((s > 0) & (s <= 2))),
                ("0%", pct(s == 0)),
                ("0%~-2%", pct((s < 0) & (s >= -2))),
                ("-2%~-5%", pct((s < -2) & (s >= -5))),
                ("<-5%", pct(s < -5)),
            ]
            lines = [
                "\n| 涨跌幅区间 | 家数占比（%） |\n",
                "|------------|---------------|\n",
            ]
            for label, p in rows:
                lines.append(f"| {label} | {p} |\n")
            lines.append("\n")
            return "".join(lines)
        except Exception:
            return ""

    def _sentiment_mood_label(self, zt: int, dt: int, multi_ge2: int) -> str:
        """近 5 日表「情绪」列：程序口径简标签。"""
        if dt >= 40 and zt < 20:
            return "低迷"
        if zt >= 50 and dt <= 8:
            return "偏强"
        if zt >= 35 and dt <= 15:
            return "回暖"
        if dt >= 25:
            return "承压"
        if multi_ge2 >= 25:
            return "接力活跃"
        return "中性"

    def _sentiment_tags_line(
        self,
        *,
        zt_count: int,
        dt_count: int,
        zb_count: int,
        zhaban_rate: float,
        turnover_yi: Optional[float],
        rise_pct: Optional[float],
    ) -> str:
        """短标签（与图二「情绪标签」风格一致，可多条）。"""
        tags: list[str] = []
        if rise_pct is not None:
            if rise_pct >= 55:
                tags.append("普涨")
            elif rise_pct <= 35:
                tags.append("涨少跌多")
        if zt_count >= 40:
            tags.append("涨停活跃")
        elif zt_count <= 15:
            tags.append("涨停偏少")
        if dt_count >= 15:
            tags.append("跌停较多")
        if zhaban_rate >= 35:
            tags.append("分歧加大")
        if turnover_yi is not None and rise_pct is not None:
            if turnover_yi < 0.85 and rise_pct >= 50:
                tags.append("缩量上涨")
            elif turnover_yi > 1.3 and rise_pct is not None and rise_pct < 45:
                tags.append("放量整理")
        if not tags:
            tags.append("情绪中性")
        return "、".join(tags[:6])

    def _five_day_market_table_markdown(
        self,
        date: str,
        trade_days: list[str],
        up_n: Optional[int],
        down_n: Optional[int],
    ) -> str:
        """近 5 交易日：涨停/跌停/涨跌家数（仅当日有快照）/连板/情绪。"""
        hist_rows, _ = self.compute_ladder_history_5d(date, trade_days)
        if not hist_rows:
            return ""
        lines = [
            "\n#### 近5交易日对照（程序口径）\n",
            "> 涨跌家数：仅**复盘当日**为全 A 快照；历史日期为「—」（接口无当日收盘快照）。\n\n",
            "| 日期 | 涨停 | 跌停 | 上涨 | 下跌 | ≥2连板 | 情绪 |\n",
            "|------|------|------|------|------|--------|------|\n",
        ]
        for r in hist_rows:
            d = str(r.get("date", ""))
            zt = int(r.get("total_zt", 0) or 0)
            multi = int(r.get("multi_board_sum", 0) or 0)
            try:
                df_dt = self.get_dt_pool(d)
                dt_n = len(df_dt) if df_dt is not None else 0
            except Exception:
                dt_n = 0
            mood = self._sentiment_mood_label(zt, dt_n, multi)
            if d == str(date)[:8] and up_n is not None and down_n is not None:
                uu, dd = str(up_n), str(down_n)
            else:
                uu, dd = "—", "—"
            lines.append(
                f"| {d} | {zt} | {dt_n} | {uu} | {dd} | {multi} | {mood} |\n"
            )
        lines.append("\n")
        return "".join(lines)

    def _index_snapshot_markdown(self) -> str:
        """上证 / 深证 / 创业板指 等快照（东财指数列表，失败则返回说明）。不含章节标题，由 build_professional_report_preface 注入。"""
        try:
            df = self.fetch_with_retry(ak.stock_zh_index_spot_em)
        except Exception as e:
            _log.warning("stock_zh_index_spot_em 失败: %s", e)
            return f"- 指数快照获取失败：{e!s}\n\n"

        if df is None or df.empty:
            return "- 指数快照为空。\n\n"

        name_col = next((c for c in df.columns if str(c) in ("名称", "name")), None)
        pct_col = next((c for c in df.columns if "涨跌幅" in str(c)), None)
        code_col = next((c for c in df.columns if str(c).strip() == "代码"), None)
        if not name_col or not pct_col:
            return "- 指数表结构异常，已跳过。\n\n"

        want_codes = {"000001", "399001", "399006"}
        sub = pd.DataFrame()
        if code_col:
            norm = (
                df[code_col]
                .astype(str)
                .str.replace(r"[^0-9]", "", regex=True)
                .str[-6:]
            )
            sub = df[norm.isin(want_codes)]
        if sub.empty:
            want = ("上证指数", "深证成指", "创业板指")
            sub = df[df[name_col].astype(str).str.contains("|".join(want), regex=True)]
        if sub.empty:
            sub = df.head(5)

        lines: list[str] = [
            "| 指数 | 涨跌幅（%） |\n|------|------------|\n",
        ]
        for _, row in sub.head(12).iterrows():
            nm = str(row.get(name_col, "") or "").strip()[:12]
            try:
                pc = float(row[pct_col])
            except Exception:
                pc = row.get(pct_col)
            lines.append(f"| {nm} | {pc} |\n")
        lines.append("\n")
        return "".join(lines)

    @staticmethod
    def _md_table_cell(val: object, max_len: int = 44) -> str:
        t = str(val if val is not None else "").strip()
        t = t.replace("|", "｜").replace("\n", " ")
        if len(t) > max_len:
            t = t[: max_len - 1] + "…"
        return t

    def _format_zt_lb_distribution_markdown(self, df_zt: pd.DataFrame) -> str:
        """连板数 × 家数 × 占比（涨停池内）。"""
        if df_zt is None or df_zt.empty or "lb" not in df_zt.columns:
            return ""
        vc = df_zt["lb"].value_counts().sort_index()
        total = max(1, len(df_zt))
        lines = [
            "\n#### 连板分布（涨停池内）\n\n",
            "| 连板数 | 家数 | 占涨停池 |\n",
            "|--------|------|----------|\n",
        ]
        for lb, cnt in vc.items():
            pct = round(100.0 * cnt / total, 2)
            lines.append(f"| {int(lb)} 连板 | {int(cnt)} | {pct}% |\n")
        lines.append("\n")
        return "".join(lines)

    def _format_zt_tier_detail_tables_markdown(self, df_zt: pd.DataFrame) -> str:
        """按连板数从高到低，每档一张明细表（图二式）。"""
        if df_zt is None or df_zt.empty or "lb" not in df_zt.columns:
            return ""
        lines: list[str] = ["\n#### 涨停梯队明细（按连板数分组）\n\n"]
        lbs = sorted({int(x) for x in df_zt["lb"].dropna().tolist()}, reverse=True)
        for lb in lbs:
            sub = df_zt[df_zt["lb"] == lb].copy()
            if sub.empty:
                continue
            if "first_time" in sub.columns:
                sub = sub.sort_values("first_time", na_position="last")
            lines.append(f"##### {lb} 连板（{len(sub)} 只）\n\n")
            lines.append(
                "| 代码 | 名称 | 行业 | 连板 | 涨停原因 | 涨跌幅% |\n"
                "|------|------|------|------|----------|--------|\n"
            )
            for _, row in sub.iterrows():
                try:
                    pc = float(row.get("pct_chg", 0))
                    pc_s = f"{pc:.2f}"
                except Exception:
                    pc_s = self._md_table_cell(row.get("pct_chg"), 8)
                lines.append(
                    f"| {self._md_table_cell(row.get('code'), 8)} | "
                    f"{self._md_table_cell(row.get('name'), 10)} | "
                    f"{self._md_table_cell(row.get('industry'), 10)} | "
                    f"{int(row.get('lb') or 0)} | "
                    f"{self._md_table_cell(row.get('reason'), 36)} | "
                    f"{pc_s} |\n"
                )
            lines.append("\n")
        return "".join(lines)

    def _format_zt_industry_top_table_markdown(
        self, df_zt: pd.DataFrame, *, top_n: int = 12
    ) -> str:
        """行业涨停家数一览（单表）。"""
        if df_zt is None or df_zt.empty or "industry" not in df_zt.columns:
            return ""
        vc = df_zt["industry"].value_counts().head(top_n)
        total = len(df_zt)
        lines = [
            "\n#### 行业涨停分布（TOP 行业）\n\n",
            "| 行业 | 涨停家数 | 占涨停池比例 |\n",
            "|------|----------|-------------|\n",
        ]
        for ind, cnt in vc.items():
            pct = round(100.0 * cnt / max(1, total), 2)
            lines.append(
                f"| {self._md_table_cell(ind, 20)} | {int(cnt)} | {pct}% |\n"
            )
        lines.append("\n")
        return "".join(lines)

    def _format_zt_industry_detail_blocks_markdown(
        self,
        df_zt: pd.DataFrame,
        *,
        top_industries: int = 6,
        per_sector: int = 14,
    ) -> str:
        """按行业涨停家数降序，分行业输出带「涨停原因」的明细表。"""
        if df_zt is None or df_zt.empty or "industry" not in df_zt.columns:
            return ""
        vc = df_zt["industry"].value_counts().head(top_industries)
        total = len(df_zt)
        lines = [
            "\n#### 分行业涨停明细（程序按行业汇总）\n\n",
            "> 按当日涨停池「所属行业」聚合，与东财板块资金流命名可能略有差异；"
            "每行业至多列 **{0}** 只（按连板降序、首封升序）。\n\n".format(per_sector),
        ]
        for ind, cnt in vc.items():
            pct = round(100.0 * cnt / max(1, total), 2)
            sub = df_zt[df_zt["industry"] == ind].copy()
            if sub.empty:
                continue
            sort_cols = []
            asc = []
            if "lb" in sub.columns:
                sort_cols.append("lb")
                asc.append(False)
            if "first_time" in sub.columns:
                sort_cols.append("first_time")
                asc.append(True)
            if sort_cols:
                sub = sub.sort_values(sort_cols, ascending=asc)
            sub = sub.head(per_sector)
            lines.append(f"##### {ind}（{cnt} 只，占涨停池 {pct}%）\n\n")
            lines.append(
                "| 代码 | 名称 | 连板 | 涨停原因 | 涨跌幅% |\n"
                "|------|------|------|----------|--------|\n"
            )
            for _, row in sub.iterrows():
                try:
                    pc = float(row.get("pct_chg", 0))
                    pc_s = f"{pc:.2f}"
                except Exception:
                    pc_s = self._md_table_cell(row.get("pct_chg"), 8)
                lines.append(
                    f"| {self._md_table_cell(row.get('code'), 8)} | "
                    f"{self._md_table_cell(row.get('name'), 10)} | "
                    f"{int(row.get('lb') or 0)} | "
                    f"{self._md_table_cell(row.get('reason'), 40)} | "
                    f"{pc_s} |\n"
                )
            lines.append("\n")
        return "".join(lines)

    def build_professional_report_preface(
        self,
        date: str,
        trade_days: list[str],
        *,
        zt_count: int,
        dt_count: int,
        zb_count: int,
        zhaban_rate: float,
        up_n: Optional[int],
        down_n: Optional[int],
        north_money: float,
        north_status: str,
        sentiment_temp: int,
        market_phase: str,
        df_zt: Optional[pd.DataFrame] = None,
    ) -> str:
        """
        图二式纵向结构：一 KPI → 二 指数 → 三 情绪与广度 → 四 题材/行业涨停 → 五 连板梯队。
        与正文「基础数据」衔接，供模型写盘面综述时引用。
        """
        ds = str(date)[:8]
        ds_fmt = f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}"
        turnover_yi, rise_pct, _flat = self._spot_turnover_rise_rate_flat()
        tags = self._sentiment_tags_line(
            zt_count=zt_count,
            dt_count=dt_count,
            zb_count=zb_count,
            zhaban_rate=zhaban_rate,
            turnover_yi=turnover_yi,
            rise_pct=rise_pct,
        )

        north_s = ""
        if north_status == "fetch_failed":
            north_s = "北向：获取失败"
        elif north_status == "empty_df":
            north_s = "北向：空表"
        elif north_status == "ok_zero":
            north_s = "北向净流入：0 亿（口径）"
        else:
            north_s = f"北向净流入：{north_money} 亿"

        max_lb = 0
        if df_zt is not None and not df_zt.empty and "lb" in df_zt.columns:
            try:
                max_lb = int(df_zt["lb"].max())
            except Exception:
                max_lb = 0

        seal_ok = None
        if zt_count + zb_count > 0:
            seal_ok = round(100.0 * zt_count / (zt_count + zb_count), 2)

        zt_in_up_pct = None
        if up_n is not None and up_n > 0 and zt_count >= 0:
            zt_in_up_pct = round(100.0 * zt_count / up_n, 2)

        lines: list[str] = [
            f"## 【程序生成·A股收盘智能复盘简报】（{ds_fmt}）\n",
            "> **图二式结构（程序块顺序）**：一、核心 KPI → 二、主要指数 → 三、情绪与广度 → "
            "四、题材与行业涨停 → 五、涨停梯队与接力。\n"
            "> 以下为程序据公开行情快照汇总，**供全文引用**；若与下文「基础数据」不一致，以本节 KPI 与表格为准。\n\n",
            "### 程序｜一、核心 KPI 与市场标签\n\n",
            "| 项目 | 内容 |\n",
            "|------|------|\n",
            "| 涨跌停 | 涨停 **{0}** 家 / 跌停 **{1}** 家 |\n".format(zt_count, dt_count),
        ]
        if up_n is not None and down_n is not None:
            lines.append(
                f"| 涨跌家数（全 A） | 上涨 **{up_n}** 家 / 下跌 **{down_n}** 家 |\n"
            )
        if max_lb > 0:
            lines.append(f"| 最高连板高度 | **{max_lb}** 板 |\n")
        if zt_in_up_pct is not None:
            lines.append(
                f"| 涨停家数/上涨家数 | **{zt_in_up_pct}%**（情绪集中度参考） |\n"
            )
        if seal_ok is not None:
            lines.append(
                f"| 封板成功率（估） | **{seal_ok}%**（= 涨停 / (涨停+炸板)） |\n"
            )
        if rise_pct is not None:
            lines.append(f"| 上涨率 | **{rise_pct}%**（全 A 快照） |\n")
        if turnover_yi is not None:
            if turnover_yi >= 10000:
                lines.append(
                    f"| 成交额（估） | **{round(turnover_yi / 10000, 2)} 万亿**（全 A 成交额合计） |\n"
                )
            else:
                lines.append(
                    f"| 成交额（估） | **{round(turnover_yi, 2)} 亿**（全 A 成交额合计） |\n"
                )
        lines.append(f"| 北向资金 | {north_s} |\n")
        lines.append(f"| 情绪温度 | **{sentiment_temp}°C** · 市场阶段：**{market_phase}** |\n")
        lines.append(f"| 情绪标签（程序） | {tags} |\n\n")

        lines.append("### 程序｜二、主要指数（当日快照）\n\n")
        lines.append(self._index_snapshot_markdown())

        lines.append("### 程序｜三、情绪与广度（近5日 + 涨跌分布）\n")
        five_d = self._five_day_market_table_markdown(date, trade_days, up_n, down_n)
        lines.append(five_d if five_d else "\n- 近5交易日对照：数据不足。\n\n")
        lines.append("\n#### 涨跌分布（全 A）\n\n")
        dist = self._spot_price_distribution_markdown()
        lines.append(dist if dist else "- 分布表暂不可用。\n\n")

        if df_zt is not None and not df_zt.empty:
            lines.append("### 程序｜四、题材与行业·涨停结构\n")
            lines.append(self._format_zt_industry_top_table_markdown(df_zt))
            lines.append(self._format_zt_industry_detail_blocks_markdown(df_zt))
            lines.append("### 程序｜五、涨停梯队与接力\n")
            lines.append(self._format_zt_lb_distribution_markdown(df_zt))
            lines.append(self._format_zt_tier_detail_tables_markdown(df_zt))

        lines.append("---\n\n")
        return "".join(lines)

    def build_replay_six_section_catalog(
        self,
        date: str,
        trade_days: list[str],
        *,
        zt_count: int,
        dt_count: int,
        zb_count: int,
        zhaban_rate: float,
        up_n: Optional[int],
        down_n: Optional[int],
        north_money: float,
        north_status: str,
        sentiment_temp: int,
        market_phase: str,
        position_suggestion: str,
        df_zt: pd.DataFrame,
        df_zb: pd.DataFrame,
        df_sector: Optional[pd.DataFrame] = None,
    ) -> str:
        """业务约定的六大目录（篇首程序块），见 `replay_catalog.build_six_section_catalog`。"""
        from app.services.replay_catalog import build_six_section_catalog

        df_concept = pd.DataFrame()
        try:
            from app.utils.config import ConfigManager as _Cfg

            if _Cfg().get("enable_replay_concept_fund_snapshot", True):
                df_concept = self.get_concept_fund_flow_rank(top_n=12)
        except Exception:
            df_concept = pd.DataFrame()

        return build_six_section_catalog(
            self,
            date,
            trade_days,
            zt_count=zt_count,
            dt_count=dt_count,
            zb_count=zb_count,
            zhaban_rate=zhaban_rate,
            up_n=up_n,
            down_n=down_n,
            north_money=north_money,
            north_status=north_status,
            sentiment_temp=sentiment_temp,
            market_phase=market_phase,
            position_suggestion=position_suggestion,
            df_zt=df_zt,
            df_zb=df_zb,
            df_sector=df_sector,
            df_concept=df_concept,
        )

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
        pool_by_day: dict[str, pd.DataFrame] = {}
        if len(days) <= 1:
            for d in days:
                pool_by_day[d] = self.get_zt_pool(d)
        else:
            w = min(_parallel_fetch_workers(), len(days))

            def _load_zt(d: str) -> tuple[str, pd.DataFrame]:
                return d, self.get_zt_pool(d)

            with ThreadPoolExecutor(max_workers=max(2, w)) as ex:
                futs = [ex.submit(_load_zt, d) for d in days]
                for fut in as_completed(futs):
                    d, df = fut.result()
                    pool_by_day[d] = df
        for d in days:
            df = pool_by_day.get(d)
            if df is not None and not df.empty and "lb" in df.columns:
                _lb = pd.to_numeric(df["lb"], errors="coerce").fillna(1).astype(int)
                df = df.copy()
                df["lb"] = _lb.mask(_lb <= 0, 1)
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
            # 最高连板 = 当日连板数的最大值（与分档表一致），不用 0/1 类标记
            max_lb = int(df["lb"].max())
            max_lb = max(max_lb, max_lb_from_ladder_dict(ladder))
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
            mx = int(r.get("max_lb") or 0)
            if mx <= 0:
                mx = max_lb_from_ladder_dict(lad)
            lines.append(
                f"| {r.get('date','')} | {r.get('total_zt',0)} | {r.get('multi_board_sum',0)} "
                f"| {ladder_level_count(lad, 2)} | {ladder_level_count(lad, 3)} | {ladder_level_count(lad, 4)} | {ge5} | {mx}板 |\n"
            )
        lines.append(f"\n- **情绪倾向（程序口径）**：{trend}\n")
        return "".join(lines)

    def compute_big_face_count(
        self, date: str, trade_days: list[str], df_dt: pd.DataFrame
    ) -> int:
        """
        大面家数：昨日涨停股中，今日跌幅 < -5% 或 跌停（计入跌停池）。
        与「龙头选手·程序量化快照」口径一致。
        """
        if not trade_days or date not in trade_days:
            return 0
        idx = trade_days.index(date)
        if idx == 0:
            return 0
        yest_date = trade_days[idx - 1]
        yest_zt = self.get_zt_pool(yest_date)
        if yest_zt is None or yest_zt.empty:
            return 0
        yest_codes = [self._norm_code(c) for c in yest_zt["code"].tolist()]
        pct_map: dict[str, float] = {}
        if len(yest_codes) <= YEST_PREMIUM_HIST_MAX_CODES:
            pct_map = self._pct_map_for_codes_on_date(yest_codes, date)
        if len(pct_map) < max(3, len(yest_codes) // 3):
            pct_map = self._pct_map_from_spot_for_codes(yest_codes)
        dt_codes: set[str] = set()
        if df_dt is not None and not df_dt.empty and "code" in df_dt.columns:
            dt_codes = {self._norm_code(x) for x in df_dt["code"].tolist()}
        big_face = 0
        for c in yest_codes:
            pv = pct_map.get(c)
            in_dt = c in dt_codes
            if in_dt or (pv is not None and float(pv) < -5.0):
                big_face += 1
        return int(big_face)

    def _zt_zhaban_percentiles(
        self,
        date: str,
        trade_days: list[str],
        zt_count: int,
        zhaban_rate: float,
        lookback: int = 15,
    ) -> tuple[Optional[float], Optional[float]]:
        """近 lookback 个交易日内，涨停家数与炸板率的经验分位（0～100）。"""
        try:
            from app.utils.config import ConfigManager

            cfg_lb = ConfigManager().get("zhaban_percentile_lookback")
            if cfg_lb is not None:
                lookback = int(cfg_lb)
            lookback = max(5, min(30, lookback))
        except Exception:
            pass
        if not trade_days or date not in trade_days:
            return None, None
        idx = trade_days.index(date)
        start = max(0, idx - lookback)
        past_days = trade_days[start:idx]
        if not past_days:
            return None, None

        def _one_past(d: str) -> tuple[str, int, float]:
            dz = self.get_zt_pool(d)
            db = self.get_zb_pool(d)
            zn = len(dz) if dz is not None and not dz.empty else 0
            bn = len(db) if db is not None and not db.empty else 0
            tot = zn + bn
            zr = round(bn / tot * 100, 2) if tot > 0 else 0.0
            return d, zn, zr

        merged: dict[str, tuple[int, float]] = {}
        if len(past_days) == 1:
            d0, zn0, zr0 = _one_past(past_days[0])
            merged[d0] = (zn0, zr0)
        else:
            w = min(_parallel_fetch_workers(), len(past_days))
            with ThreadPoolExecutor(max_workers=max(2, w)) as ex:
                futs = [ex.submit(_one_past, d) for d in past_days]
                for fut in as_completed(futs):
                    d, zn, zr = fut.result()
                    merged[d] = (zn, zr)
        zts: list[int] = []
        zhrs: list[float] = []
        for d in past_days:
            pair = merged.get(d)
            if pair is None:
                continue
            zts.append(pair[0])
            zhrs.append(pair[1])
        if not zts:
            return None, None
        bz = sum(1 for x in zts if zt_count > x)
        ez = sum(1 for x in zts if zt_count == x)
        zt_pct = round((bz + 0.5 * ez) / len(zts) * 100.0, 0)
        bb = sum(1 for x in zhrs if zhaban_rate > x)
        eb = sum(1 for x in zhrs if zhaban_rate == x)
        zb_pct = round((bb + 0.5 * eb) / len(zhrs) * 100.0, 0)
        return zt_pct, zb_pct

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

        # 涨跌家数已从 get_market_summary 统一获取，这里不再重复调用
        # 使用已存储在实例中的数据
        up_n = getattr(self, '_last_up_count', None)
        down_n = getattr(self, '_last_down_count', None)
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

        big_face = self.compute_big_face_count(date, trade_days, df_dt)
        dt_codes: set[str] = set()
        if df_dt is not None and not df_dt.empty and "code" in df_dt.columns:
            dt_codes = {self._norm_code(x) for x in df_dt["code"].tolist()}
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

    def _north_money_from_hist_em(self, ds: str) -> Optional[Tuple[float, str]]:
        """东财沪深港通历史表（ak.stock_hsgt_hist_em），单位已为亿元。失败返回 None。"""
        fn = getattr(ak, "stock_hsgt_hist_em", None)
        if not callable(fn):
            return None
        now = time.time()
        if (
            self._north_hist_em_df is not None
            and now - self._north_hist_em_ts < 3600
        ):
            df = self._north_hist_em_df
        else:
            try:
                df = self.fetch_with_retry(fn, symbol="北向资金")
            except Exception:
                return None
            self._north_hist_em_df = df
            self._north_hist_em_ts = now
        if df is None or df.empty:
            return 0.0, "empty_df"
        date_col = "日期" if "日期" in df.columns else df.columns[0]
        sdt = pd.to_datetime(df[date_col], errors="coerce")
        sub = df[sdt.dt.strftime("%Y%m%d") == ds]
        if sub.empty:
            return 0.0, "empty_df"
        row = sub.iloc[-1]
        for col in ("当日成交净买额", "当日资金流入"):
            if col not in row.index:
                continue
            v = row[col]
            if pd.isna(v):
                continue
            val = round(float(v), 2)
            st = "ok_zero" if val == 0.0 else "ok"
            return val, st
        return 0.0, "empty_df"

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
            df = None
            sina_fn = getattr(ak, "stock_hsgt_north_net_flow_sina", None)
            if callable(sina_fn):
                df = self.fetch_with_retry(sina_fn, date=date)
            if df is not None and not df.empty:
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
            out = self._north_money_from_hist_em(ds)
            if out is not None:
                _write_cache("north_net", ds, {"value": out[0], "status": out[1]})
                return out[0], out[1]
            return 0.0, "fetch_failed"
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
        with self._cache_lock:
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
            self._last_finance_news_related = []
            self._last_finance_news_general = []
            return line, ""

        codes, names = _news_keywords_from_meta(ah_meta or {})
        related: list[tuple[str, str, str]] = []
        general: list[tuple[str, str]] = []

        # 存储新闻数据到实例变量，供要闻映射使用（原始抓取，供宽匹配）
        news_list_raw: list[str] = []
        for _, row in df.head(20).iterrows():
            summary = str(row.get("summary") or "").strip()
            if summary:
                news_list_raw.append(summary)

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

        try:
            from app.services.news_fetcher import filter_news

            rel_dicts = filter_news(
                [{"tag": t, "summary": s, "hint": h} for t, s, h in related],
                min_score=0.6,
                max_items=10,
                related_boost=True,
            )
            gen_dicts = filter_news(
                [{"tag": t, "summary": s} for t, s in general],
                min_score=0.6,
                max_items=3,
                related_boost=False,
            )
            related = [
                (d["tag"], d["summary"], d.get("hint") or "") for d in rel_dicts
            ]
            general = [(d["tag"], d["summary"]) for d in gen_dicts]
        except Exception as ex:
            _log.warning("要闻相关性过滤失败，使用原始列表：%s", ex)

        fin_list: list[str] = [s for _, s, __ in related] + [s for _, s in general]
        self._last_finance_news = fin_list if fin_list else news_list_raw

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
        self._last_finance_news_related = [
            {"tag": t, "summary": s, "hint": h} for t, s, h in related
        ]
        self._last_finance_news_general = [
            {"tag": t, "summary": s} for t, s in general
        ]
        if not related and not general:
            block = (
                "\n## 【财经要闻·与程序观察标的】\n"
                "- 今日未解析到有效要闻条目。\n\n"
            )
            self._last_finance_news_related = []
            self._last_finance_news_general = []
            return block, ""
        return block, push_text + "\n\n---\n\n"

    def get_market_summary(self, date):
        """获取完整市场摘要（文本形式）"""
        self._last_news_push_prefix = ""
        self._last_auction_meta = {}
        self._last_email_kpi = {}
        self._last_premium_analysis = {}
        self._last_big_face_count = 0
        self._last_sentiment_forecast = ""
        self._last_dragon_trader_meta = {}
        self._last_finance_news_related = []
        self._last_finance_news_general = []
        summary = ""
        trade_days = self.get_trade_cal()
        if not trade_days:
            summary += "## 基础数据\n- 无法获取交易日历，请检查网络或数据源。\n\n"
            self._last_email_kpi = {}
            self._last_premium_analysis = {}
            self._last_big_face_count = 0
            self._last_sentiment_forecast = ""
            self._last_dragon_trader_meta = {}
            return summary, date
        if date not in trade_days:
            _log.info("%s 非交易日，将自动调整", date)
            date = self.get_last_trade_day(date, trade_days)
            _log.info("调整为最近交易日: %s", date)

        # 获取基础数据（默认可并行：涨跌停/板块/北向/溢价/涨跌家数相互独立）
        up_n: Optional[int] = None
        down_n: Optional[int] = None
        if _market_summary_parallel_enabled():
            w = max(7, _parallel_fetch_workers())
            futures_map = {}
            with ThreadPoolExecutor(max_workers=w) as ex:
                futures_map[ex.submit(self.get_zt_pool, date)] = "zt"
                futures_map[ex.submit(self.get_dt_pool, date)] = "dt"
                futures_map[ex.submit(self.get_zb_pool, date)] = "zb"
                futures_map[ex.submit(self.get_sector_rank, date)] = "sector"
                futures_map[ex.submit(self.get_north_money, date)] = "north"
                futures_map[ex.submit(self.get_yest_zt_premium, date, trade_days)] = (
                    "premium"
                )
                futures_map[ex.submit(self._spot_red_green_counts)] = "spot_ud"
                raw: dict = {}
                for fut in as_completed(futures_map):
                    tag = futures_map[fut]
                    try:
                        raw[tag] = fut.result()
                    except Exception as e:
                        _log.warning("并行获取 %s 失败: %s", tag, e)
                        raw[tag] = None
            dz = raw.get("zt")
            df_zt = dz if isinstance(dz, pd.DataFrame) else pd.DataFrame()
            dd = raw.get("dt")
            df_dt = dd if isinstance(dd, pd.DataFrame) else pd.DataFrame()
            dzb = raw.get("zb")
            df_zb = dzb if isinstance(dzb, pd.DataFrame) else pd.DataFrame()
            ds = raw.get("sector")
            df_sector = ds if isinstance(ds, pd.DataFrame) else pd.DataFrame()
            pr = raw.get("premium")
            if isinstance(pr, tuple) and len(pr) >= 2:
                premium, premium_note = float(pr[0]), str(pr[1])
            else:
                premium, premium_note = -99.0, "并行获取失败"
            nr = raw.get("north")
            if isinstance(nr, tuple) and len(nr) >= 2:
                north_money, north_status = float(nr[0]), str(nr[1])
            else:
                north_money, north_status = 0.0, "fetch_failed"
            sud = raw.get("spot_ud")
            if isinstance(sud, tuple) and len(sud) >= 2:
                up_n, down_n = sud[0], sud[1]
        else:
            df_zt = self.get_zt_pool(date)
            df_dt = self.get_dt_pool(date)
            df_zb = self.get_zb_pool(date)
            df_sector = self.get_sector_rank(date)
            premium, premium_note = self.get_yest_zt_premium(date, trade_days)
            north_money, north_status = self.get_north_money(date)

        # 供 replay_task 分离确认等复用（须为当日涨停池 DataFrame）
        self._last_zt_pool = df_zt.copy() if df_zt is not None else pd.DataFrame()
        try:
            from app.services.market_kpi import premium_analysis

            self._last_premium_analysis = premium_analysis(
                premium, premium_note, date, trade_days, self
            )
        except Exception as e:
            _log.warning("premium_analysis 失败: %s", e)
            self._last_premium_analysis = {
                "display_line": (
                    f"{premium if premium != -99 else premium_note}"
                ),
                "premium": premium,
                "premium_note": premium_note,
            }

        zt_count = len(df_zt)
        dt_count = len(df_dt)
        zb_count = len(df_zb)
        total = zt_count + zb_count
        zhaban_rate = round(zb_count / total * 100, 2) if total > 0 else 0

        try:
            self._last_big_face_count = int(
                self.compute_big_face_count(str(date)[:8], trade_days, df_dt)
            )
        except Exception:
            self._last_big_face_count = 0

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

        pa = getattr(self, "_last_premium_analysis", None) or {}
        m5 = pa.get("mean_5")
        past_n = int(pa.get("past_sample_n") or 0)
        if premium != -99 and m5 is not None and past_n >= 2:
            diff = float(premium) - float(m5)
            band = max(0.4, abs(float(m5)) * 0.12)
            if diff > band:
                sentiment_temp += 25
            elif diff > 0:
                sentiment_temp += 15
            elif float(premium) > 0:
                sentiment_temp += 5
        elif premium > 3:
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

        max_lb_phase = (
            int(df_zt["lb"].max())
            if not df_zt.empty and "lb" in df_zt.columns
            else 0
        )
        market_phase, _legacy_position = compute_short_term_market_phase(
            sentiment_temp,
            zt_count,
            dt_count,
            zhaban_rate,
            max_lb_phase,
            float(premium),
        )
        try:
            zt_pct, zb_pct = self._zt_zhaban_percentiles(
                str(date)[:8], trade_days, zt_count, zhaban_rate
            )
        except Exception:
            zt_pct, zb_pct = None, None
        try:
            from app.services.position_sizer import calc_position

            position_suggestion = calc_position(
                market_phase,
                zhaban_rate,
                zt_count,
                zt_percentile=zt_pct,
                zb_percentile=zb_pct,
            )
        except Exception:
            position_suggestion = _legacy_position

        # 存储市场阶段到实例变量，供其他方法使用
        self._last_market_phase = market_phase
        self._last_position_suggestion = position_suggestion

        # 获取涨跌家数（并行阶段已取则复用全 A spot，避免二次请求）
        if up_n is None and down_n is None:
            up_n, down_n = self._spot_red_green_counts()
        # 存储到实例变量，供其他方法使用，确保数据一致性
        self._last_up_count = up_n
        self._last_down_count = down_n

        # 计算情绪周期量化评分
        try:
            from app.services.sentiment_scorer import calculate_sentiment_score

            max_lb = max_lb_phase
            sentiment_score, sentiment_md = calculate_sentiment_score(
                yest_zt_premium=premium if premium != -99 else 0,
                max_lb_height=max_lb,
                zhaban_rate=zhaban_rate,
                up_count=up_n or 0,
                down_count=down_n or 0,
            )
            self._last_sentiment_score = sentiment_score
            self._last_sentiment_markdown = sentiment_md
        except Exception:
            self._last_sentiment_score = None
            self._last_sentiment_markdown = ""

        summary += self.build_replay_six_section_catalog(
            date,
            trade_days,
            zt_count=zt_count,
            dt_count=dt_count,
            zb_count=zb_count,
            zhaban_rate=zhaban_rate,
            up_n=up_n,
            down_n=down_n,
            north_money=north_money,
            north_status=north_status,
            sentiment_temp=sentiment_temp,
            market_phase=market_phase,
            position_suggestion=position_suggestion,
            df_zt=df_zt,
            df_zb=df_zb,
            df_sector=df_sector,
        )

        summary += "## 基础数据（补遗）\n"
        summary += (
            "> **涨跌结构、涨跌停、北向、情绪温度/阶段/建议仓位** 见篇首目录 **§1.2 市场数据概括**；"
            "此处避免重复占用上下文。\n\n"
        )
        _pa_line = (pa.get("display_line") if isinstance(pa, dict) else None) or (
            f"{premium if premium != -99 else premium_note}"
        )
        summary += f"- 昨日涨停溢价：{_pa_line}\n\n"
        if hasattr(self, "_last_sentiment_markdown") and self._last_sentiment_markdown:
            summary += self._last_sentiment_markdown
        summary += (
            "\n> **口径**：正文叙事以目录 **§1.2** 的 **情绪温度、市场阶段、建议仓位** 为主轴；"
            "上表 **情绪周期量化评分（0～10）** 为辅助刻度，勿与主轴打架。\n\n"
        )

        try:
            from app.services.ladder_stats import compute_promotion_rates_md

            summary += compute_promotion_rates_md(self, str(date)[:8], trade_days, df_zt)
        except Exception as ex:
            _log.warning("连板晋级率块跳过：%s", ex)

        try:
            from app.services.cycle_analyzer import sentiment_forecast

            ix = trade_days.index(str(date)[:8])
            zhaban_rate_prev = None
            if ix > 0:
                pd_ = trade_days[ix - 1]
                pzt = self.get_zt_pool(pd_)
                pzb = self.get_zb_pool(pd_)
                zn = len(pzt) if pzt is not None and not getattr(pzt, "empty", True) else 0
                bbn = len(pzb) if pzb is not None and not getattr(pzb, "empty", True) else 0
                totp = zn + bbn
                zhaban_rate_prev = (
                    round(bbn / totp * 100, 2) if totp > 0 else None
                )
            sf = sentiment_forecast(
                zhaban_rate=zhaban_rate,
                zhaban_rate_prev=zhaban_rate_prev,
                premium=float(premium),
                dt_count=int(dt_count),
                market_phase=str(market_phase),
            )
            self._last_sentiment_forecast = sf
            summary += "## 【程序·明日情绪推演】\n\n"
            summary += f"> {sf}\n\n"
        except Exception as ex:
            self._last_sentiment_forecast = ""
            _log.warning("明日情绪推演跳过：%s", ex)

        summary += "## 板块资金流向\n"
        summary += (
            "> 行业 **主力净流入 TOP** 已列于篇首 **§0 盘面总览**；本节不重复展开。\n\n"
        )

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

        summary += (
            "## 核心龙头（摘要）\n"
            "> 连板结构、分行业涨停、首封时段分布、按时间排序个股见篇首 **"
            "【程序生成】复盘数据目录** 第 **1.1 / 1.2 / 6** 节。\n\n"
        )

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

        _ty, _rp, _ = self._spot_turnover_rise_rate_flat()
        _pa = getattr(self, "_last_premium_analysis", None) or {}
        _bf = int(getattr(self, "_last_big_face_count", 0) or 0)
        self._last_email_kpi = {
            "zt_count": int(zt_count),
            "dt_count": int(dt_count),
            "zb_count": int(zb_count),
            "zhaban_rate": float(zhaban_rate),
            "big_loss_count": _bf,
            "big_loss_display": f"大面: {_bf}只（昨涨停今跌超5%或跌停）",
            "premium": float(premium) if premium != -99 else None,
            "premium_note": str(premium_note),
            "premium_display": (_pa.get("display_line") if isinstance(_pa, dict) else None)
            or "",
            "premium_mean_5": _pa.get("mean_5") if isinstance(_pa, dict) else None,
            "premium_percentile": _pa.get("percentile") if isinstance(_pa, dict) else None,
            "premium_rating": (_pa.get("rating") if isinstance(_pa, dict) else None)
            or "",
            "position_suggestion": str(position_suggestion),
            "turnover_yi_est": _ty,
            "rise_rate_pct": _rp,
        }
        return summary, date  # 返回可能调整后的日期
