# -*- coding: utf-8 -*-
"""
离线回测权重策略：网格搜索平滑系数 / 上限 / 保底等参数，评估不同参数组合的累计收益表现。

用法：
  python scripts/backtest_weights.py --start 2025-01-01 --end 2025-12-31
  python scripts/backtest_weights.py --param-file config/backtest_params.json
  python scripts/backtest_weights.py --plot
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.services.strategy_preference import (  # noqa: E402
    BUCKETS,
    DEFAULT_WEIGHTS,
    tag_to_bucket,
    _smooth,
    _penalize_large_shift,
    _apply_floor_cap,
    _limit_weight_delta_vs_old,
)
from app.services.weekly_performance import (  # noqa: E402
    compute_returns_for_records,
    records_for_iso_week,
)
from app.services.watchlist_store import load_all_records  # noqa: E402


def get_trade_days() -> List[str]:
    """获取交易日历"""
    import akshare as ak
    try:
        df = ak.tool_trade_date_hist_sina()
        df['trade_date'] = pd.to_datetime(df['trade_date']).dt.strftime('%Y%m%d')
        return df['trade_date'].tolist()
    except Exception:
        return []


def weeks_between(start_date: str, end_date: str) -> List[Tuple[int, int]]:
    """获取起止日期之间的所有自然周（ISO周）"""
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    weeks = []
    current = start
    while current <= end:
        y, w, _ = current.isocalendar()
        weeks.append((y, w))
        current += pd.Timedelta(days=7)
    # 去重
    unique_weeks = []
    seen = set()
    for week in weeks:
        if week not in seen:
            seen.add(week)
            unique_weeks.append(week)
    return unique_weeks


def calculate_bucket_returns(
    week: Tuple[int, int], 
    trade_days: List[str],
    records: List[Dict[str, Any]],
    as_of_trade: str
) -> Dict[str, float]:
    """计算某周每个风格桶的实际收益"""
    iso_year, iso_week = week
    week_recs = records_for_iso_week(records, iso_year, iso_week)
    rows = compute_returns_for_records(week_recs, trade_days, as_of_trade)
    
    # 按风格桶分组计算收益
    bucket_returns = {k: [] for k in BUCKETS}
    for r in rows:
        if r.ret_pct is not None and r.note == "ok":
            bucket = tag_to_bucket(r.tag)
            bucket_returns[bucket].append(float(r.ret_pct))
    
    # 计算每个桶的平均收益
    avg_returns = {}
    for bucket, returns in bucket_returns.items():
        if returns:
            avg_returns[bucket] = sum(returns) / len(returns)
        else:
            avg_returns[bucket] = 0.0  # 无数据时默认为0
    
    return avg_returns


def update_weights(
    old_weights: Dict[str, float],
    bucket_returns: Dict[str, float],
    params: Dict[str, Any]
) -> Dict[str, float]:
    """根据参数更新权重"""
    # 计算建议权重（基于收益）
    scores = {k: max(bucket_returns.get(k, 0) + 5.0, 0.1) for k in BUCKETS}
    tot = sum(scores.values())
    if tot <= 0:
        suggested = dict(DEFAULT_WEIGHTS)
    else:
        suggested = {k: scores[k] / tot for k in BUCKETS}
    
    # 应用平滑
    merged = _smooth(old_weights, suggested, params.get('smooth_factor', 0.3))
    
    # 应用大变化惩罚
    merged = _penalize_large_shift(
        merged, 
        old_weights, 
        max_change=params.get('max_change_per_week', 0.25), 
        pullback=params.get('shift_pullback', 0.5)
    )
    
    # 应用上下限
    merged = _apply_floor_cap(
        merged, 
        max_single=params.get('max_single_weight', 0.55), 
        min_each=params.get('min_each_weight', 0.08)
    )
    
    # 应用权重变化限制
    merged = _limit_weight_delta_vs_old(
        merged, 
        old_weights, 
        max_delta=params.get('max_weight_delta_per_update', 0.15)
    )
    
    return merged


def run_backtest(
    start_date: str, 
    end_date: str, 
    param_grid: List[Dict[str, Any]],
    trade_days: List[str],
    records: List[Dict[str, Any]]
) -> List[Tuple[Dict[str, Any], float]]:
    """运行回测"""
    weeks = weeks_between(start_date, end_date)
    results = []
    
    for params in param_grid:
        current_weights = dict(DEFAULT_WEIGHTS)
        weekly_returns = []
        
        for week in weeks:
            # 计算当周最后一个交易日作为锚点
            iso_year, iso_week = week
            week_start = datetime.fromisocalendar(iso_year, iso_week, 1)
            week_end = week_start + pd.Timedelta(days=6)
            week_end_str = week_end.strftime('%Y%m%d')
            
            # 找到不超过week_end_str的最后一个交易日
            valid_trade_days = [d for d in trade_days if d <= week_end_str]
            if not valid_trade_days:
                continue
            as_of_trade = valid_trade_days[-1]
            
            # 计算桶收益
            bucket_returns = calculate_bucket_returns(week, trade_days, records, as_of_trade)
            
            # 计算当周收益
            week_return = sum(bucket_returns.get(b, 0) * current_weights.get(b, 0) for b in BUCKETS)
            weekly_returns.append(week_return)
            
            # 更新权重
            current_weights = update_weights(current_weights, bucket_returns, params)
        
        # 计算累计收益
        if weekly_returns:
            cumulative_return = (1 + pd.Series(weekly_returns) / 100).prod() - 1
            results.append((params, cumulative_return))
    
    # 按累计收益排序
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def plot_results(results: List[Tuple[Dict[str, Any], float]], output_path: str) -> bool:
    """绘制回测结果"""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    
    if not results:
        return False
    
    # 准备数据
    param_labels = []
    returns = []
    
    for params, ret in results[:10]:  # 只显示前10个结果
        label = f"smooth={params.get('smooth_factor', 0.3)}, max={params.get('max_single_weight', 0.55)}"
        param_labels.append(label)
        returns.append(ret * 100)  # 转换为百分比
    
    # 绘图
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(range(len(returns)), returns)
    ax.set_xticks(range(len(returns)))
    ax.set_xticklabels(param_labels, rotation=45, ha='right', fontsize=8)
    ax.set_ylabel('累计收益 (%)')
    ax.set_title('不同参数组合的累计收益')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=120)
    plt.close()
    return True


def load_param_grid(param_file: Optional[str]) -> List[Dict[str, Any]]:
    """加载参数网格"""
    if param_file and os.path.isfile(param_file):
        with open(param_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    # 默认参数网格
    return [
        {
            'smooth_factor': sf,
            'max_single_weight': ms,
            'min_each_weight': 0.08,
            'max_change_per_week': 0.25,
            'shift_pullback': 0.5,
            'max_weight_delta_per_update': 0.15
        }
        for sf in [0.2, 0.3, 0.4]
        for ms in [0.5, 0.55, 0.6]
    ]


def main() -> int:
    p = argparse.ArgumentParser(description="权重策略离线回测")
    p.add_argument(
        "--start",
        default="2025-01-01",
        help="回测开始日期 (YYYY-MM-DD)"
    )
    p.add_argument(
        "--end",
        default="2025-12-31",
        help="回测结束日期 (YYYY-MM-DD)"
    )
    p.add_argument(
        "--param-file",
        help="参数网格配置文件路径"
    )
    p.add_argument(
        "--plot",
        action="store_true",
        help="绘制回测结果"
    )
    args = p.parse_args()
    
    # 加载数据
    print("加载数据...")
    trade_days = get_trade_days()
    if not trade_days:
        print("无法获取交易日历", file=sys.stderr)
        return 1
    
    records = load_all_records()
    if not records:
        print("无法加载龙头池记录", file=sys.stderr)
        return 1
    
    # 加载参数网格
    param_grid = load_param_grid(args.param_file)
    print(f"参数网格大小: {len(param_grid)}")
    
    # 运行回测
    print("运行回测...")
    results = run_backtest(args.start, args.end, param_grid, trade_days, records)
    
    # 输出结果
    print("\n回测结果（按累计收益排序）:")
    print("-" * 80)
    for i, (params, ret) in enumerate(results[:10], 1):
        print(f"{i}. 累计收益: {ret*100:.2f}%")
        print(f"   参数: smooth={params.get('smooth_factor', 0.3)}, max_single={params.get('max_single_weight', 0.55)}")
        print("-" * 80)
    
    # 绘制结果
    if args.plot:
        output_path = os.path.join(_ROOT, "data", "backtest_results.png")
        if plot_results(results, output_path):
            print(f"回测结果已保存至: {output_path}")
        else:
            print("绘制失败，可能缺少matplotlib")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
