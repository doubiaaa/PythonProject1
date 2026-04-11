# -*- coding: utf-8 -*-
"""
情绪周期量化评分：规则来自 config/strategy.json（当前 profile），与历史硬编码数值一致。
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


class SentimentScorer:
    """情绪周期量化评分器（配置驱动）。"""

    def __init__(self, score_config: Optional[dict[str, Any]] = None) -> None:
        from app.services.strategy_engine import get_strategy_engine

        self._cfg: dict[str, Any] = score_config or get_strategy_engine().get_sentiment_score_config()

    @property
    def WEIGHTS(self) -> dict[str, float]:
        w = self._cfg.get("weights") or {}
        return {
            "yest_zt_premium": float(w.get("yest_zt_premium", 0.3)),
            "max_lb_height": float(w.get("max_lb_height", 0.3)),
            "zhaban_rate": float(w.get("zhaban_rate", 0.2)),
            "up_down_ratio": float(w.get("up_down_ratio", 0.2)),
        }

    def calculate_yest_zt_premium_score(self, premium: float) -> float:
        p = self._cfg.get("premium") or {}
        if premium >= float(p.get("t_ge_5", 5)):
            return float(p.get("score_ge_5", 10))
        if premium >= float(p.get("t_ge_3", 3)):
            r = p.get("lin_ge_3") or {}
            return float(r.get("base", 8)) + (premium - float(r.get("from", 3))) * float(
                r.get("k", 1)
            )
        if premium >= float(p.get("t_ge_1", 1)):
            r = p.get("lin_ge_1") or {}
            return float(r.get("base", 5)) + (premium - float(r.get("from", 1))) * float(
                r.get("k", 1.5)
            )
        if premium >= float(p.get("t_ge_0", 0)):
            r = p.get("lin_ge_0") or {}
            return float(r.get("base", 3)) + premium * float(r.get("k", 2))
        if premium >= float(p.get("t_ge_-2", -2)):
            r = p.get("lin_ge_-2") or {}
            return float(r.get("base", 1)) + (premium + 2) * float(r.get("k", 1))
        r = p.get("else_neg") or {}
        return max(
            float(r.get("floor", 0)),
            float(r.get("base", 1)) + (premium + 2) * float(r.get("k", 0.5)),
        )

    def calculate_max_lb_height_score(self, max_lb: int) -> float:
        p = self._cfg.get("max_lb") or {}
        if max_lb >= int(p.get("t_ge_7", 7)):
            return float(p.get("score_ge_7", 10))
        if max_lb >= int(p.get("t_ge_5", 5)):
            r = p.get("lin_ge_5") or {}
            return float(r.get("base", 8)) + (max_lb - int(r.get("from", 5))) * float(
                r.get("k", 1)
            )
        if max_lb >= int(p.get("t_ge_3", 3)):
            r = p.get("lin_ge_3") or {}
            return float(r.get("base", 5)) + (max_lb - int(r.get("from", 3))) * float(
                r.get("k", 1.5)
            )
        if max_lb >= int(p.get("t_ge_2", 2)):
            r = p.get("lin_ge_2") or {}
            return float(r.get("base", 3)) + (max_lb - int(r.get("from", 2))) * float(
                r.get("k", 2)
            )
        if max_lb >= int(p.get("t_ge_1", 1)):
            r = p.get("lin_ge_1") or {}
            return float(r.get("base", 1)) + (max_lb - int(r.get("from", 1))) * float(
                r.get("k", 2)
            )
        return float(p.get("else", 0))

    def calculate_zhaban_rate_score(self, zhaban_rate: float) -> float:
        p = self._cfg.get("zhaban") or {}
        if zhaban_rate <= float(p.get("t_le_20", 20)):
            return float(p.get("score_le_20", 10))
        if zhaban_rate <= float(p.get("t_le_30", 30)):
            r = p.get("lin_le_30") or {}
            return float(r.get("base", 8)) + (
                float(r.get("ref", 30)) - zhaban_rate
            ) * float(r.get("k", 0.2))
        if zhaban_rate <= float(p.get("t_le_40", 40)):
            r = p.get("lin_le_40") or {}
            return float(r.get("base", 5)) + (
                float(r.get("ref", 40)) - zhaban_rate
            ) * float(r.get("k", 0.3))
        if zhaban_rate <= float(p.get("t_le_50", 50)):
            r = p.get("lin_le_50") or {}
            return float(r.get("base", 3)) + (
                float(r.get("ref", 50)) - zhaban_rate
            ) * float(r.get("k", 0.2))
        if zhaban_rate <= float(p.get("t_le_60", 60)):
            r = p.get("lin_le_60") or {}
            return float(r.get("base", 1)) + (
                float(r.get("ref", 60)) - zhaban_rate
            ) * float(r.get("k", 0.2))
        r = p.get("else_hi") or {}
        return max(
            float(r.get("floor", 0)),
            float(r.get("base", 1)) - (zhaban_rate - float(r.get("ref", 60))) * float(
                r.get("k", 0.05)
            ),
        )

    def calculate_up_down_ratio_score(self, up_count: int, down_count: int) -> float:
        p = self._cfg.get("up_down_ratio") or {}
        if down_count == 0:
            return float(p.get("down_zero_up", 10)) if up_count > 0 else float(
                p.get("down_zero_flat", 5)
            )
        ratio = up_count / (up_count + down_count)
        if ratio >= float(p.get("r_ge_0.7", 0.7)):
            return float(p.get("score_ge_0.7", 10))
        if ratio >= float(p.get("r_ge_0.6", 0.6)):
            r = p.get("lin_ge_0.6") or {}
            return float(r.get("base", 8)) + (ratio - float(r.get("from", 0.6))) * float(
                r.get("k", 20)
            )
        if ratio >= float(p.get("r_ge_0.5", 0.5)):
            r = p.get("lin_ge_0.5") or {}
            return float(r.get("base", 5)) + (ratio - float(r.get("from", 0.5))) * float(
                r.get("k", 30)
            )
        if ratio >= float(p.get("r_ge_0.4", 0.4)):
            r = p.get("lin_ge_0.4") or {}
            return float(r.get("base", 3)) + (ratio - float(r.get("from", 0.4))) * float(
                r.get("k", 20)
            )
        if ratio >= float(p.get("r_ge_0.3", 0.3)):
            r = p.get("lin_ge_0.3") or {}
            return float(r.get("base", 1)) + (ratio - float(r.get("from", 0.3))) * float(
                r.get("k", 20)
            )
        r = p.get("else_low") or {}
        return max(float(r.get("floor", 0)), ratio * float(r.get("k", 3.33)))

    def calculate_total_score(
        self,
        yest_zt_premium: float = 0,
        max_lb_height: int = 0,
        zhaban_rate: float = 50,
        up_count: int = 0,
        down_count: int = 0,
    ) -> Tuple[float, Dict[str, Any]]:
        W = self.WEIGHTS
        premium_score = self.calculate_yest_zt_premium_score(yest_zt_premium)
        lb_score = self.calculate_max_lb_height_score(max_lb_height)
        zhaban_score = self.calculate_zhaban_rate_score(zhaban_rate)
        ratio_score = self.calculate_up_down_ratio_score(up_count, down_count)

        total_score = (
            premium_score * W["yest_zt_premium"]
            + lb_score * W["max_lb_height"]
            + zhaban_score * W["zhaban_rate"]
            + ratio_score * W["up_down_ratio"]
        )
        total_score = max(0.0, min(10.0, total_score))

        self.details = {
            "total_score": round(total_score, 1),
            "components": {
                "昨日涨停溢价": {
                    "raw_value": f"{yest_zt_premium:.2f}%",
                    "score": round(premium_score, 1),
                    "weight": f"{W['yest_zt_premium']*100:.0f}%",
                    "weighted_score": round(premium_score * W["yest_zt_premium"], 2),
                },
                "连板高度": {
                    "raw_value": f"{max_lb_height}板",
                    "score": round(lb_score, 1),
                    "weight": f"{W['max_lb_height']*100:.0f}%",
                    "weighted_score": round(lb_score * W["max_lb_height"], 2),
                },
                "炸板率": {
                    "raw_value": f"{zhaban_rate:.1f}%",
                    "score": round(zhaban_score, 1),
                    "weight": f"{W['zhaban_rate']*100:.0f}%",
                    "weighted_score": round(zhaban_score * W["zhaban_rate"], 2),
                },
                "涨跌家数比": {
                    "raw_value": f"{up_count}/{down_count}",
                    "score": round(ratio_score, 1),
                    "weight": f"{W['up_down_ratio']*100:.0f}%",
                    "weighted_score": round(ratio_score * W["up_down_ratio"], 2),
                },
            },
            "interpretation": self._interpret_score(total_score),
        }
        self.score = total_score
        return total_score, self.details

    def _interpret_score(self, score: float) -> str:
        rows = sorted(
            self._cfg.get("interpretation") or [],
            key=lambda x: -float(x.get("min", 0)),
        )
        for row in rows:
            if score >= float(row.get("min", 0)):
                return str(row.get("text", ""))
        return "情绪冰点，亏钱效应强，建议观望"

    def format_markdown(self) -> str:
        if not self.details:
            return ""
        lines = ["\n### 【情绪周期量化评分】（辅助）\n"]
        lines.append(
            "> **主轴**：请以市场数据中 **§1.2 情绪温度、市场阶段、建议仓位** 为准；"
            "本块为 0～10 分刻度，用于交叉验证，勿与主轴矛盾叙述。\n\n"
        )
        lines.append(
            f"**情绪评分：{self.details['total_score']}/10**（{self.details['interpretation']}）\n"
        )
        lines.append("\n评分构成：\n")
        lines.append("| 指标 | 原始值 | 单项得分 | 权重 | 加权得分 |\n")
        lines.append("|------|--------|----------|------|----------|\n")
        for name, data in self.details["components"].items():
            lines.append(
                f"| {name} | {data['raw_value']} | {data['score']} | {data['weight']} | {data['weighted_score']} |\n"
            )
        footer = self._cfg.get(
            "markdown_footer_rule_text",
            "评分规则：昨日涨停溢价权重30%、连板高度权重30%、炸板率权重20%、涨跌家数比权重20%",
        )
        lines.append(f"\n> *{footer}*\n")
        return "".join(lines)


def calculate_sentiment_score(
    yest_zt_premium: float = 0,
    max_lb_height: int = 0,
    zhaban_rate: float = 50,
    up_count: int = 0,
    down_count: int = 0,
) -> Tuple[float, str]:
    scorer = SentimentScorer()
    score, _ = scorer.calculate_total_score(
        yest_zt_premium=yest_zt_premium,
        max_lb_height=max_lb_height,
        zhaban_rate=zhaban_rate,
        up_count=up_count,
        down_count=down_count,
    )
    markdown = scorer.format_markdown()
    return score, markdown
