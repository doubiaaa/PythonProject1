# -*- coding: utf-8 -*-
"""
策略引擎：从 config/strategy.json 加载多套 profile，驱动市场阶段、仓位、情绪温度、情绪评分、竞价半路参数。
数值默认与历史硬编码一致；可通过 active_profile 或环境变量 STRATEGY_PROFILE 切换。
"""

from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from typing import Any, Optional

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)
_STRATEGY_JSON = os.path.join(_PROJECT_ROOT, "config", "strategy.json")
_KEBI_STRATEGY_JSON = os.path.join(_PROJECT_ROOT, "config", "92kebi_strategy.json")

_lock = threading.Lock()
_engine_singleton: Optional["StrategyEngine"] = None


def get_strategy_engine() -> "StrategyEngine":
    global _engine_singleton
    with _lock:
        if _engine_singleton is None:
            _engine_singleton = StrategyEngine()
        return _engine_singleton


def reset_strategy_engine_for_tests() -> None:
    """仅测试：强制下次重新加载配置。"""
    global _engine_singleton
    with _lock:
        _engine_singleton = None


class StrategyEngine:
    """加载 strategy.json，解析 active_profile，提供与原硬编码一致的业务计算。"""

    def __init__(self, strategy_path: Optional[str] = None) -> None:
        self._path = strategy_path or _STRATEGY_JSON
        self._raw: dict[str, Any] = {}
        self._profile_name = "default"
        self._profile: dict[str, Any] = {}
        self._kebi_raw: dict[str, Any] = {}
        self._kebi_profile: dict[str, Any] = {}
        self._load()
        self._load_kebi()

    def _load(self) -> None:
        if os.path.isfile(self._path):
            with open(self._path, "r", encoding="utf-8") as f:
                self._raw = json.load(f)
        else:
            self._raw = {}
        prof = (
            os.environ.get("STRATEGY_PROFILE", "").strip()
            or (self._raw.get("active_profile") or "default")
        )
        profiles = self._raw.get("profiles") or {}
        if prof not in profiles:
            prof = "default"
        self._profile_name = prof
        self._profile = deepcopy(profiles.get(prof) or {})

    def reload(self) -> None:
        self._load()
        self._load_kebi()

    def _load_kebi(self) -> None:
        path = os.environ.get("KEBI_STRATEGY_PATH") or _KEBI_STRATEGY_JSON
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._kebi_raw = json.load(f)
            except Exception:
                self._kebi_raw = {}
        else:
            self._kebi_raw = {}
        meta = self._kebi_raw.get("meta") or {}
        if meta.get("enabled") is False:
            self._kebi_profile = {}
            return
        prof = (
            os.environ.get("KEBI_PROFILE", "").strip()
            or (self._kebi_raw.get("active_profile") or "default")
        )
        profiles = self._kebi_raw.get("profiles") or {}
        if prof not in profiles:
            prof = "default"
        self._kebi_profile = deepcopy(profiles.get(prof) or {})

    def get_kebi_stage_bundle(self, legacy_market_phase: str) -> dict[str, Any]:
        """由程序原四象限阶段名映射到 92科比 四阶段配置块。"""
        mp = self._kebi_profile
        m = mp.get("legacy_phase_to_kebi_stage") or {}
        stages = mp.get("stages") or {}
        sid = m.get(legacy_market_phase) or mp.get("fallback_stage")
        if not sid or sid not in stages:
            sid = mp.get("fallback_stage")
        if not sid or sid not in stages:
            sid = next(iter(stages), "")
        st = stages.get(sid) or {}
        return {
            "stage_id": sid,
            "stage": st,
            "report": mp.get("report") or {},
        }

    def format_kebi_conclusion_markdown(
        self,
        legacy_market_phase: str,
        program_position_suggestion: str,
    ) -> str:
        """复盘报告尾部：92科比标准结论（全文来自配置，无硬编码）。"""
        meta = self._kebi_raw.get("meta") or {}
        if meta.get("enabled") is False or not self._kebi_profile:
            return ""
        b = self.get_kebi_stage_bundle(legacy_market_phase)
        st = b.get("stage") or {}
        rep = b.get("report") or {}
        if not st:
            return ""
        rows = rep.get("row_labels") or {}
        tmpl = rep.get("strategy_line_template") or ""
        strat = tmpl.format(
            primary=st.get("primary_operation", ""),
            secondary=st.get("secondary_operation", ""),
            note=st.get("operation_note", ""),
        )
        lo = st.get("position_cap_pct_lo", 0)
        hi = st.get("position_cap_pct_hi", 0)
        lines: list[str] = [
            str(rep.get("section_title", "## 【92科比·策略结论】")) + "\n\n",
            str(rep.get("intro_line") or "") + "\n\n",
            f"| {rows.get('cycle', '周期')} | **{st.get('title', '')}** — {st.get('market_state', '')} |\n",
            f"| {rows.get('strategy', '策略')} | {strat} |\n",
            f"| {rows.get('position', '仓位')} | {st.get('position_words', '')}（约 {lo}%～{hi}%） |\n",
            f"| {rows.get('risk', '风险')} | **{st.get('risk_level', '')}** — {st.get('risk_control', '')} |\n",
            f"| {rows.get('tomorrow', '明日')} | {st.get('tomorrow_direction', '')} |\n",
        ]
        out = self._kebi_profile.get("output") or {}
        if out.get("show_program_position_line", True):
            lines.append(
                f"| {rows.get('program_position', '程序仓位')} | {program_position_suggestion} |\n"
            )
        lines.append("\n**选股与买卖点**\n\n")
        lines.append(f"- 方向：{st.get('selection_focus', '')}\n")
        lines.append(f"- 买卖点：{st.get('buy_sell_rules', '')}\n\n")
        lines.append("**科比要点**\n\n")
        for x in st.get("standard_bullets") or []:
            lines.append(f"- {x}\n")
        wv = self._kebi_profile.get("worldview") or {}
        lines.append("\n---\n\n")
        lines.append("> **世界观摘录**：" + str(wv.get("market_essence", "")) + "\n")
        return "".join(lines)

    @property
    def profile_name(self) -> str:
        return self._profile_name

    def get_auction_halfway(self) -> dict[str, Any]:
        return deepcopy(self._profile.get("auction_halfway") or {})

    def get_ai_prompt_context(self) -> dict[str, Any]:
        return deepcopy(self._profile.get("ai_prompt_context") or {})

    def compute_sentiment_temperature(
        self,
        zt_count: int,
        dt_count: int,
        premium: float,
        premium_analysis: dict[str, Any],
        zhaban_rate: float,
    ) -> int:
        st = self._profile.get("sentiment_temperature") or {}
        temp = 0
        for band in st.get("zt_count_bands") or []:
            if zt_count > int(band.get("above", 0)):
                temp += int(band.get("add", 0))
                break
        for band in st.get("dt_count_bands") or []:
            if dt_count < int(band.get("below", 999999)):
                temp += int(band.get("add", 0))
                break

        miss = float(st.get("premium_missing_sentinel", -99))
        m5_cfg = st.get("m5_vs_mean5") or {}
        m5 = premium_analysis.get("mean_5")
        past_n = int(premium_analysis.get("past_sample_n") or 0)
        if premium != miss and m5 is not None and past_n >= int(
            m5_cfg.get("min_past_sample_n", 2)
        ):
            diff = float(premium) - float(m5)
            band = max(
                float(m5_cfg.get("band_floor", 0.4)),
                abs(float(m5)) * float(m5_cfg.get("band_abs_m5_factor", 0.12)),
            )
            if diff > band:
                temp += int(m5_cfg.get("diff_gt_band", 25))
            elif diff > 0:
                temp += int(m5_cfg.get("diff_gt_zero", 15))
            elif float(premium) > 0:
                temp += int(m5_cfg.get("premium_gt_zero", 5))
        else:
            for band in st.get("premium_only_bands") or []:
                if premium > float(band.get("above", -999)):
                    temp += int(band.get("add", 0))
                    break

        for band in st.get("zhaban_bands") or []:
            if zhaban_rate < float(band.get("below", 999)):
                temp += int(band.get("add", 0))
                break

        cap = int(st.get("cap", 100))
        return min(temp, cap)

    def compute_market_phase(
        self,
        sentiment_temp: int,
        zt_count: int,
        dt_count: int,
        zhaban_rate: float,
        max_lb: int,
        premium: float,
    ) -> tuple[str, str]:
        mp = self._profile.get("market_phase") or {}
        miss = float(mp.get("premium_missing_sentinel", -99))
        prem_ok = premium != miss
        prem = float(premium) if prem_ok else 0.0

        leg = mp.get("legacy_position") or {}

        if sentiment_temp < int(mp.get("ice_sentiment_temp_below", 32)):
            name = mp.get("phase_ice", "退潮·冰点期")
            return name, str(leg.get(name, "0-10%"))
        if zt_count < int(mp.get("ice_zt_below", 14)) and dt_count > zt_count + int(
            mp.get("ice_dt_excess_over_zt", 15)
        ):
            name = mp.get("phase_ice", "退潮·冰点期")
            return name, str(leg.get(name, "0-10%"))
        if (
            max_lb <= int(mp.get("ice_max_lb_at_most", 2))
            and zt_count < int(mp.get("ice_zt_below_for_premium_rule", 20))
            and prem_ok
            and prem < float(mp.get("ice_premium_below", -0.8))
        ):
            name = mp.get("phase_ice", "退潮·冰点期")
            return name, str(leg.get(name, "0-10%"))

        nm = mp.get("phase_main_rise", "主升期")
        if sentiment_temp >= int(mp.get("main_sentiment_temp_at_least", 80)):
            return nm, str(leg.get(nm, "80%"))
        if zt_count >= int(mp.get("main_zt_at_least_a", 25)) and max_lb >= int(
            mp.get("main_max_lb_at_least_a", 6)
        ):
            return nm, str(leg.get(nm, "80%"))
        if (
            max_lb >= int(mp.get("main_max_lb_at_least_b", 5))
            and zhaban_rate <= float(mp.get("main_zhaban_at_most", 36))
            and zt_count >= int(mp.get("main_zt_at_least_b", 32))
        ):
            return nm, str(leg.get(nm, "80%"))

        nc = mp.get("phase_chaos", "混沌·试错期")
        if int(mp.get("chaos_sentiment_low", 36)) <= sentiment_temp <= int(
            mp.get("chaos_sentiment_high", 74)
        ) and zhaban_rate >= float(mp.get("chaos_zhaban_at_least", 44)):
            return nc, str(leg.get(nc, "15-25%"))
        chaos2_lb = set(mp.get("chaos2_max_lb_values") or [2, 3])
        if (
            int(mp.get("chaos2_sentiment_low", 34)) <= sentiment_temp
            <= int(mp.get("chaos2_sentiment_high", 70))
            and prem_ok
            and float(mp.get("chaos2_premium_low", -0.3))
            <= prem
            <= float(mp.get("chaos2_premium_high", 1.0))
            and max_lb in chaos2_lb
            and zt_count >= int(mp.get("chaos2_zt_at_least", 18))
        ):
            return nc, str(leg.get(nc, "15-25%"))

        nd = mp.get("phase_range", "高位震荡期")
        return nd, str(leg.get(nd, "30%"))

    def calc_position(
        self,
        cycle: str,
        zhaban_rate: float,
        zt_count: int,
        *,
        zt_percentile: Optional[float] = None,
        zb_percentile: Optional[float] = None,
    ) -> str:
        pos = self._profile.get("position") or {}
        c = (cycle or "").strip()
        zb = float(zhaban_rate)
        zt_pct = zt_percentile
        if zt_pct is None:
            zt_pct = float(pos.get("zt_percentile_default", 30))
            for row in sorted(
                pos.get("zt_percentile_fallback") or [],
                key=lambda x: -int(x.get("zt_at_least", 0)),
            ):
                if zt_count >= int(row.get("zt_at_least", 0)):
                    zt_pct = float(row.get("pct", zt_pct))
                    break

        lo, hi = 20.0, 40.0
        matched_c = False
        for cy in pos.get("cycles") or []:
            kws = cy.get("keywords") or []
            if any(k in c for k in kws):
                lo, hi = float(cy.get("lo", 20)), float(cy.get("hi", 40))
                matched_c = True
                break
        if not matched_c:
            dc = pos.get("default_cycle") or {}
            lo, hi = float(dc.get("lo", 20)), float(dc.get("hi", 40))

        ztl = float(pos.get("zt_pct_low_threshold", 25))
        if zt_pct is not None and zt_pct < ztl:
            lo = max(0.0, lo + float(pos.get("zt_pct_low_lo_delta", -5)))
            hi = max(lo, hi + float(pos.get("zt_pct_low_hi_delta", -10)))
        elif zt_pct is not None and zt_pct > float(pos.get("zt_pct_high_threshold", 80)):
            hi = min(
                float(pos.get("zt_pct_high_hi_cap", 95)),
                hi + float(pos.get("zt_pct_high_hi_delta", 5)),
            )

        lo, hi = self._clamp_position_pct(lo, hi, zb, zb_percentile, pos)
        if lo >= hi:
            hi = lo + float(pos.get("min_hi_above_lo", 5))
        return f"{int(round(lo))}-{int(round(hi))}%"

    def _clamp_position_pct(
        self,
        lo: float,
        hi: float,
        zhaban_rate: float,
        zb_pctile: Optional[float],
        pos: dict[str, Any],
    ) -> tuple[float, float]:
        zh1 = float(pos.get("clamp_zhaban_high_first", 30))
        pmin = float(pos.get("clamp_zhaban_pctile_min", 60))
        if zhaban_rate > zh1 and (zb_pctile is None or zb_pctile >= pmin):
            hi = max(lo, hi - float(pos.get("clamp_zhaban_hi_drop", 10)))
        zh2 = float(pos.get("clamp_zhaban_high_second", 40))
        if zhaban_rate > zh2:
            hi = max(lo, hi - float(pos.get("clamp_zhaban_hi_drop_second", 5)))
        return lo, hi

    def get_sentiment_score_config(self) -> dict[str, Any]:
        return deepcopy(self._profile.get("sentiment_score") or {})

    def get_auction_scoring_params(self) -> dict[str, Any]:
        """
        与历史 `_load_strategy_params` 一致：auction_halfway 内权重可被 replay_config.json 覆盖。
        """
        from app.utils.config import ConfigManager

        ah = self.get_auction_halfway()
        wdef = ah.get("weights") or {}
        cm = ConfigManager()

        def gf(key: str, default: float) -> float:
            try:
                return float(cm.get(key, default))
            except (TypeError, ValueError):
                return default

        w_main = gf("w_main", float(wdef.get("w_main", 0.22)))
        w_dragon = gf("w_dragon", float(wdef.get("w_dragon", 0.18)))
        w_kline = gf("w_kline", float(wdef.get("w_kline", 0.18)))
        w_liq = gf("w_liq", float(wdef.get("w_liq", 0.14)))
        w_tech = gf("w_tech", float(wdef.get("w_tech", 0.28)))
        s = w_main + w_dragon + w_kline + w_liq + w_tech
        if abs(s - 1.0) > 0.02:
            w_main = float(wdef.get("w_main", 0.22))
            w_dragon = float(wdef.get("w_dragon", 0.18))
            w_kline = float(wdef.get("w_kline", 0.18))
            w_liq = float(wdef.get("w_liq", 0.14))
            w_tech = float(wdef.get("w_tech", 0.28))
        try:
            topn = int(cm.get("tech_eval_topn", ah.get("tech_eval_topn", 12)))
        except (TypeError, ValueError):
            topn = int(ah.get("tech_eval_topn", 12))
        topn = max(3, min(48, topn))
        en = cm.get("enable_tech_momentum", ah.get("enable_tech_momentum", True))
        if isinstance(en, str):
            enable_tech = en.strip().lower() in ("1", "true", "yes")
        else:
            enable_tech = bool(en)
        return {
            "w_main": w_main,
            "w_dragon": w_dragon,
            "w_kline": w_kline,
            "w_liq": w_liq,
            "w_tech": w_tech,
            "tech_eval_topn": topn,
            "enable_tech": enable_tech,
        }
