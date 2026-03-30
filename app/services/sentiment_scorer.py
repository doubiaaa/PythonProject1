# -*- coding: utf-8 -*-
"""
情绪周期量化评分：基于多个市场指标计算情绪分值（0-10分）
"""

from typing import Dict, Any, Optional, Tuple
import pandas as pd


class SentimentScorer:
    """情绪周期量化评分器"""
    
    # 评分权重配置
    WEIGHTS = {
        'yest_zt_premium': 0.30,  # 昨日涨停溢价权重 30%
        'max_lb_height': 0.30,    # 连板高度权重 30%
        'zhaban_rate': 0.20,      # 炸板率权重 20%
        'up_down_ratio': 0.20,    # 涨跌家数比权重 20%
    }
    
    def __init__(self):
        self.score = 0.0
        self.details = {}
    
    def calculate_yest_zt_premium_score(self, premium: float) -> float:
        """
        计算昨日涨停溢价得分
        
        Args:
            premium: 昨日涨停溢价百分比
            
        Returns:
            0-10 的得分
        """
        if premium >= 5:
            return 10.0
        elif premium >= 3:
            return 8.0 + (premium - 3) * 1.0  # 3-5% 映射到 8-10
        elif premium >= 1:
            return 5.0 + (premium - 1) * 1.5  # 1-3% 映射到 5-8
        elif premium >= 0:
            return 3.0 + premium * 2.0  # 0-1% 映射到 3-5
        elif premium >= -2:
            return 1.0 + (premium + 2) * 1.0  # -2-0% 映射到 1-3
        else:
            return max(0.0, 1.0 + (premium + 2) * 0.5)  # <-2% 递减
    
    def calculate_max_lb_height_score(self, max_lb: int) -> float:
        """
        计算连板高度得分
        
        Args:
            max_lb: 最高连板数
            
        Returns:
            0-10 的得分
        """
        if max_lb >= 7:
            return 10.0
        elif max_lb >= 5:
            return 8.0 + (max_lb - 5) * 1.0  # 5-7板 映射到 8-10
        elif max_lb >= 3:
            return 5.0 + (max_lb - 3) * 1.5  # 3-5板 映射到 5-8
        elif max_lb >= 2:
            return 3.0 + (max_lb - 2) * 2.0  # 2-3板 映射到 3-5
        elif max_lb >= 1:
            return 1.0 + (max_lb - 1) * 2.0  # 1-2板 映射到 1-3
        else:
            return 0.0
    
    def calculate_zhaban_rate_score(self, zhaban_rate: float) -> float:
        """
        计算炸板率得分（炸板率越低得分越高）
        
        Args:
            zhaban_rate: 炸板率百分比
            
        Returns:
            0-10 的得分
        """
        if zhaban_rate <= 20:
            return 10.0
        elif zhaban_rate <= 30:
            return 8.0 + (30 - zhaban_rate) * 0.2  # 20-30% 映射到 8-10
        elif zhaban_rate <= 40:
            return 5.0 + (40 - zhaban_rate) * 0.3  # 30-40% 映射到 5-8
        elif zhaban_rate <= 50:
            return 3.0 + (50 - zhaban_rate) * 0.2  # 40-50% 映射到 3-5
        elif zhaban_rate <= 60:
            return 1.0 + (60 - zhaban_rate) * 0.2  # 50-60% 映射到 1-3
        else:
            return max(0.0, 1.0 - (zhaban_rate - 60) * 0.05)  # >60% 递减
    
    def calculate_up_down_ratio_score(self, up_count: int, down_count: int) -> float:
        """
        计算涨跌家数比得分
        
        Args:
            up_count: 上涨家数
            down_count: 下跌家数
            
        Returns:
            0-10 的得分
        """
        if down_count == 0:
            return 10.0 if up_count > 0 else 5.0
        
        ratio = up_count / (up_count + down_count)
        
        if ratio >= 0.7:
            return 10.0
        elif ratio >= 0.6:
            return 8.0 + (ratio - 0.6) * 20  # 0.6-0.7 映射到 8-10
        elif ratio >= 0.5:
            return 5.0 + (ratio - 0.5) * 30  # 0.5-0.6 映射到 5-8
        elif ratio >= 0.4:
            return 3.0 + (ratio - 0.4) * 20  # 0.4-0.5 映射到 3-5
        elif ratio >= 0.3:
            return 1.0 + (ratio - 0.3) * 20  # 0.3-0.4 映射到 1-3
        else:
            return max(0.0, ratio * 3.33)  # <0.3 递减
    
    def calculate_total_score(
        self,
        yest_zt_premium: float = 0,
        max_lb_height: int = 0,
        zhaban_rate: float = 50,
        up_count: int = 0,
        down_count: int = 0,
    ) -> Tuple[float, Dict[str, Any]]:
        """
        计算综合情绪得分
        
        Args:
            yest_zt_premium: 昨日涨停溢价
            max_lb_height: 最高连板数
            zhaban_rate: 炸板率
            up_count: 上涨家数
            down_count: 下跌家数
            
        Returns:
            (综合得分, 详细评分项)
        """
        # 计算各项得分
        premium_score = self.calculate_yest_zt_premium_score(yest_zt_premium)
        lb_score = self.calculate_max_lb_height_score(max_lb_height)
        zhaban_score = self.calculate_zhaban_rate_score(zhaban_rate)
        ratio_score = self.calculate_up_down_ratio_score(up_count, down_count)
        
        # 加权计算总分
        total_score = (
            premium_score * self.WEIGHTS['yest_zt_premium'] +
            lb_score * self.WEIGHTS['max_lb_height'] +
            zhaban_score * self.WEIGHTS['zhaban_rate'] +
            ratio_score * self.WEIGHTS['up_down_ratio']
        )
        
        # 确保得分在 0-10 范围内
        total_score = max(0.0, min(10.0, total_score))
        
        # 生成详细评分项
        self.details = {
            'total_score': round(total_score, 1),
            'components': {
                '昨日涨停溢价': {
                    'raw_value': f"{yest_zt_premium:.2f}%",
                    'score': round(premium_score, 1),
                    'weight': f"{self.WEIGHTS['yest_zt_premium']*100:.0f}%",
                    'weighted_score': round(premium_score * self.WEIGHTS['yest_zt_premium'], 2),
                },
                '连板高度': {
                    'raw_value': f"{max_lb_height}板",
                    'score': round(lb_score, 1),
                    'weight': f"{self.WEIGHTS['max_lb_height']*100:.0f}%",
                    'weighted_score': round(lb_score * self.WEIGHTS['max_lb_height'], 2),
                },
                '炸板率': {
                    'raw_value': f"{zhaban_rate:.1f}%",
                    'score': round(zhaban_score, 1),
                    'weight': f"{self.WEIGHTS['zhaban_rate']*100:.0f}%",
                    'weighted_score': round(zhaban_score * self.WEIGHTS['zhaban_rate'], 2),
                },
                '涨跌家数比': {
                    'raw_value': f"{up_count}/{down_count}",
                    'score': round(ratio_score, 1),
                    'weight': f"{self.WEIGHTS['up_down_ratio']*100:.0f}%",
                    'weighted_score': round(ratio_score * self.WEIGHTS['up_down_ratio'], 2),
                },
            },
            'interpretation': self._interpret_score(total_score),
        }
        
        self.score = total_score
        return total_score, self.details
    
    def _interpret_score(self, score: float) -> str:
        """根据得分生成解读"""
        if score >= 8:
            return "情绪高涨，赚钱效应强，可积极参与"
        elif score >= 6:
            return "情绪较好，赚钱效应中等，可适度参与"
        elif score >= 4:
            return "情绪中性，赚钱效应一般，谨慎参与"
        elif score >= 2:
            return "情绪低迷，亏钱效应显现，控制仓位"
        else:
            return "情绪冰点，亏钱效应强，建议观望"
    
    def format_markdown(self) -> str:
        """格式化评分为 Markdown"""
        if not self.details:
            return ""
        
        lines = ["\n### 【情绪周期量化评分】\n"]
        lines.append(f"**情绪评分：{self.details['total_score']}/10**（{self.details['interpretation']}）\n")
        lines.append("\n评分构成：\n")
        lines.append("| 指标 | 原始值 | 单项得分 | 权重 | 加权得分 |\n")
        lines.append("|------|--------|----------|------|----------|\n")
        
        for name, data in self.details['components'].items():
            lines.append(
                f"| {name} | {data['raw_value']} | {data['score']} | {data['weight']} | {data['weighted_score']} |\n"
            )
        
        lines.append("\n> *评分规则：昨日涨停溢价权重30%、连板高度权重30%、炸板率权重20%、涨跌家数比权重20%*\n")
        
        return "".join(lines)


def calculate_sentiment_score(
    yest_zt_premium: float = 0,
    max_lb_height: int = 0,
    zhaban_rate: float = 50,
    up_count: int = 0,
    down_count: int = 0,
) -> Tuple[float, str]:
    """
    便捷函数：计算情绪评分并返回 Markdown 格式
    
    Returns:
        (得分, Markdown格式字符串)
    """
    scorer = SentimentScorer()
    score, details = scorer.calculate_total_score(
        yest_zt_premium=yest_zt_premium,
        max_lb_height=max_lb_height,
        zhaban_rate=zhaban_rate,
        up_count=up_count,
        down_count=down_count,
    )
    markdown = scorer.format_markdown()
    return score, markdown
