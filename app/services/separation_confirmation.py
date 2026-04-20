# -*- coding: utf-8 -*-
"""
分离确认功能：利用分钟级分时数据，在总龙头出现炸板或跳水时，筛选逆势拉升或抗跌的个股
"""

import os
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple

import pandas as pd
import akshare as ak

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
TICK_CACHE_DIR = os.path.join(DATA_DIR, "tick_cache")


def _ensure_tick_cache_dir() -> None:
    """确保分时数据缓存目录存在"""
    os.makedirs(TICK_CACHE_DIR, exist_ok=True)


def _infer_limit_ratio(code: object, name: object = "") -> float:
    c = str(code or "").zfill(6)[:6]
    nm = str(name or "")
    un = nm.upper()
    if "ST" in un or nm.startswith("*"):
        return 0.05
    if c.startswith(("300", "688")):
        return 0.20
    if c and (c[0] in ("8", "4") or c[:2] in ("43", "83", "87", "88", "92")):
        return 0.30
    return 0.10


def _limit_and_pre_close(stock_info: Dict[str, Any]) -> Tuple[float, float]:
    """依据快照涨跌幅估计昨收，并给出理论涨停价（用于炸板/跳水启发式）。"""
    px = float(stock_info.get("price") or stock_info.get("close") or 0)
    code = str(stock_info.get("code", ""))
    name = str(stock_info.get("name", ""))
    ratio = _infer_limit_ratio(code, name)
    pct = stock_info.get("pct_chg")
    try:
        pcf = float(pct)
    except (TypeError, ValueError):
        pcf = None
    if px <= 0:
        return 0.0, 0.0
    if pcf is not None and abs(pcf) > 1e-6:
        pre = px / (1.0 + pcf / 100.0)
    else:
        pre = px / (1.0 + ratio)
    lim = pre * (1.0 + ratio)
    return lim, pre


def get_tick_cache_file_path(stock_code: str, date: str) -> str:
    """获取分时数据缓存文件路径"""
    _ensure_tick_cache_dir()
    return os.path.join(TICK_CACHE_DIR, f"{stock_code}_{date}.json")


def get_tick_data(stock_code: str, date: str) -> Optional[pd.DataFrame]:
    """
    获取某只股票某日的分钟级数据（腾讯源）
    返回 DataFrame: 时间、价格、成交量等
    """
    # 规范化代码
    stock_code = stock_code.strip()
    if not stock_code:
        return None
    
    # 生成缓存文件路径
    cache_file = get_tick_cache_file_path(stock_code, date)
    
    # 尝试从缓存读取
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            df = pd.DataFrame(data)
            df['time'] = pd.to_datetime(df['time'])
            return df
        except Exception:
            pass
    
    # 从 AKShare 获取
    try:
        df = ak.stock_zh_a_tick_tx(code=stock_code, trade_date=date)
        if df is None or df.empty:
            return None
        
        # 保存到缓存
        data = df.to_dict('records')
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return df
    except Exception:
        return None


def identify_leading_stock(df_zt: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """
    识别当日总龙头（最高连板股）
    """
    if df_zt is None or df_zt.empty:
        return None
    
    # 按连板数降序排序
    df_zt_sorted = df_zt.sort_values('lb', ascending=False)
    
    # 取最高连板的股票
    highest_lb = df_zt_sorted['lb'].iloc[0]
    candidates = df_zt_sorted[df_zt_sorted['lb'] == highest_lb]
    
    # 若有多个：优先成交额（若列存在），否则首封时间早的优先
    if len(candidates) > 1:
        if "amount" in candidates.columns:
            candidates = candidates.sort_values("amount", ascending=False)
        elif "first_time" in candidates.columns:
            candidates = candidates.sort_values("first_time", ascending=True, na_position="last")
        else:
            candidates = candidates.sort_values("code", ascending=True)
    
    leading_stock = candidates.iloc[0].to_dict()
    return leading_stock


def detect_volatility_timepoints(df: pd.DataFrame, stock_info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    识别总龙头的异动时间点（炸板或跳水）
    """
    if df is None or df.empty:
        return []
    
    volatility_points = []

    limit_up_price, pre_close = _limit_and_pre_close(stock_info)
    tol = max(limit_up_price * 0.002, 0.02) if limit_up_price > 0 else 0.02

    # 检测炸板
    for i in range(1, len(df)):
        prev_price = df['price'].iloc[i-1]
        curr_price = df['price'].iloc[i]
        
        # 炸板：从涨停价附近快速下跌
        if limit_up_price > 0 and abs(prev_price - limit_up_price) <= tol:
            if curr_price < limit_up_price * 0.99:
                volatility_points.append({
                    'type': '炸板',
                    'time': df['time'].iloc[i],
                    'price': curr_price,
                    'prev_price': prev_price
                })
    
    # 检测跳水
    for i in range(5, len(df)):
        five_min_ago_price = df['price'].iloc[i-5]
        curr_price = df['price'].iloc[i]
        
        # 跳水：5分钟内跌幅超过3%，且当时涨幅仍在7%以上
        if five_min_ago_price > 0:
            drop_pct = (curr_price - five_min_ago_price) / five_min_ago_price * 100
            if drop_pct < -3:
                if pre_close > 0 and curr_price > pre_close * 1.07:
                    volatility_points.append({
                        'type': '跳水',
                        'time': df['time'].iloc[i],
                        'price': curr_price,
                        'five_min_ago_price': five_min_ago_price,
                        'drop_pct': drop_pct
                    })
    
    return volatility_points


def calculate_separation_score(
    candidate_df: pd.DataFrame, 
    volatility_time: datetime, 
    leading_stock_df: pd.DataFrame,
    volatility_type: str = ""
) -> tuple[float, dict]:
    """
    计算候选股的分离确认得分，并返回详细的判断依据
    返回: (得分, 判断依据详情)
    """
    if candidate_df is None or candidate_df.empty:
        return 0.0, {}
    
    # 找到异动时间附近的候选股价格
    candidate_df['time_diff'] = candidate_df['time'].apply(lambda x: abs((x - volatility_time).total_seconds()))
    candidate_point = candidate_df[candidate_df['time_diff'] == candidate_df['time_diff'].min()]
    
    if candidate_point.empty:
        return 0.0, {}
    
    # 找到异动时间附近的龙头股价格
    leading_stock_df['time_diff'] = leading_stock_df['time'].apply(lambda x: abs((x - volatility_time).total_seconds()))
    leading_point = leading_stock_df[leading_stock_df['time_diff'] == leading_stock_df['time_diff'].min()]
    
    if leading_point.empty:
        return 0.0, {}
    
    # 计算5分钟前的价格
    candidate_5min_ago = candidate_df[candidate_df['time'] <= volatility_time - timedelta(minutes=5)]
    leading_5min_ago = leading_stock_df[leading_stock_df['time'] <= volatility_time - timedelta(minutes=5)]
    
    if candidate_5min_ago.empty or leading_5min_ago.empty:
        return 0.0, {}
    
    candidate_prev_price = candidate_5min_ago.iloc[-1]['price']
    leading_prev_price = leading_5min_ago.iloc[-1]['price']
    
    candidate_curr_price = candidate_point.iloc[0]['price']
    leading_curr_price = leading_point.iloc[0]['price']
    
    # 计算涨跌幅
    candidate_change = (candidate_curr_price - candidate_prev_price) / candidate_prev_price * 100
    leading_change = (leading_curr_price - leading_prev_price) / leading_prev_price * 100
    
    # 计算分离得分：逆势拉升或抗跌
    if candidate_change > 0 and leading_change < 0:
        # 逆势拉升
        score = candidate_change - leading_change
        pattern = "逆势拉升"
    elif candidate_change > leading_change:
        # 抗跌
        score = (candidate_change - leading_change) * 0.5
        pattern = "抗跌"
    else:
        # 跟随下跌
        score = 0.0
        pattern = "跟随下跌"
    
    # 构建判断依据详情
    details = {
        'volatility_time': volatility_time.strftime('%H:%M'),
        'volatility_type': volatility_type,
        'pattern': pattern,
        'candidate_change': round(candidate_change, 2),
        'leading_change': round(leading_change, 2),
        'candidate_prev_price': round(candidate_prev_price, 2),
        'candidate_curr_price': round(candidate_curr_price, 2),
        'leading_prev_price': round(leading_prev_price, 2),
        'leading_curr_price': round(leading_curr_price, 2),
    }
    
    return max(0.0, score), details


def get_candidate_stocks(
    leading_stock: Dict[str, Any],
    date: str,
    trade_days: List[str],
    df_zt_all: Optional[pd.DataFrame] = None,
) -> List[Dict[str, Any]]:
    """
    获取候选股列表（同板块或同梯队的个股）
    """
    candidates = []
    
    try:
        # 获取同板块个股（涨停池列为 industry，兼容 sector）
        sector = (
            str(leading_stock.get("sector") or "").strip()
            or str(leading_stock.get("industry") or "").strip()
        )
        if sector:
            cons = ak.stock_board_industry_cons_em(symbol=sector)
            if cons is not None and not cons.empty:
                for _, r in cons.iterrows():
                    code = str(r.get('代码', '')).strip()
                    name = str(r.get('名称', '')).strip()
                    if code and name and code != leading_stock.get('code', ''):
                        candidates.append({
                            'code': code,
                            'name': name,
                            'sector': sector
                        })
        
        if (
            len(candidates) < 3
            and df_zt_all is not None
            and not df_zt_all.empty
            and "lb" in df_zt_all.columns
        ):
            lb = int(leading_stock.get("lb") or 0)
            ind = str(
                leading_stock.get("industry")
                or leading_stock.get("sector")
                or ""
            ).strip()
            code0 = str(leading_stock.get("code") or "").strip()
            sub = df_zt_all[df_zt_all["lb"] == lb].copy()
            if code0 and "code" in sub.columns:
                sub = sub[sub["code"].astype(str).str.strip() != code0]
            if ind and "industry" in sub.columns:
                sub = sub[sub["industry"].astype(str).str.strip() == ind]
            got: set[str] = {str(c["code"]) for c in candidates}
            for _, r in sub.head(25).iterrows():
                code = str(r.get("code") or "").strip()
                name = str(r.get("name") or "").strip()
                if code and code not in got:
                    got.add(code)
                    candidates.append(
                        {"code": code, "name": name, "sector": ind or ""}
                    )
        return candidates[:20]
    except Exception:
        out: list[dict[str, Any]] = []
        if (
            df_zt_all is not None
            and not df_zt_all.empty
            and "lb" in df_zt_all.columns
        ):
            try:
                lb = int(leading_stock.get("lb") or 0)
                ind = str(
                    leading_stock.get("industry")
                    or leading_stock.get("sector")
                    or ""
                ).strip()
                code0 = str(leading_stock.get("code") or "").strip()
                sub = df_zt_all[df_zt_all["lb"] == lb].copy()
                if code0 and "code" in sub.columns:
                    sub = sub[sub["code"].astype(str).str.strip() != code0]
                if ind and "industry" in sub.columns:
                    sub = sub[sub["industry"].astype(str).str.strip() == ind]
                for _, r in sub.head(20).iterrows():
                    code = str(r.get("code") or "").strip()
                    name = str(r.get("name") or "").strip()
                    if code:
                        out.append(
                            {"code": code, "name": name, "sector": ind or ""}
                        )
            except Exception:
                pass
        return out[:20]


def perform_separation_confirmation(
    date: str, 
    df_zt: pd.DataFrame, 
    trade_days: List[str]
) -> Dict[str, Any]:
    """
    执行分离确认分析
    """
    result: Dict[str, Any] = {
        "date": date,
        "leading_stock": None,
        "leading_stock_reason": "",
        "leading_stock_candidates": [],
        "volatility_points": [],
        "candidates": [],
        "notes": [],
    }
    
    # 识别总龙头
    leading_stock = identify_leading_stock(df_zt)
    if not leading_stock:
        return result
    
    result['leading_stock'] = leading_stock
    try:
        ranked = df_zt.sort_values("lb", ascending=False).copy()
        highest_lb = int(ranked["lb"].iloc[0])
        peers = ranked[ranked["lb"] == highest_lb].copy()
        peer_codes = set(str(peers.get("code", pd.Series(dtype=str)).astype(str).tolist()))
        tie_breaker = "code_asc"
        if len(peers) > 1:
            if "amount" in peers.columns:
                tie_breaker = "amount_desc"
            elif "first_time" in peers.columns:
                tie_breaker = "first_time_asc"
        selected_code = str(leading_stock.get("code", ""))
        selected_name = str(leading_stock.get("name", ""))
        selected_lb = int(leading_stock.get("lb") or highest_lb)
        if len(peers) == 1:
            result["leading_stock_reason"] = (
                f"总龙头按最高连板识别：当日空间板为 {selected_lb} 连板，仅 "
                f"{selected_name}({selected_code}) 符合。"
            )
        else:
            if tie_breaker == "amount_desc":
                reason = "同为最高连板时按成交额降序优先"
            elif tie_breaker == "first_time_asc":
                reason = "同为最高连板时按首封时间更早优先"
            else:
                reason = "同为最高连板且无可用成交额/首封时间时按代码升序兜底"
            result["leading_stock_reason"] = (
                f"总龙头按最高连板识别：当日空间板为 {selected_lb} 连板；"
                f"存在同层候选 {len(peers)} 只，{reason}，最终选中 {selected_name}({selected_code})。"
            )
        for _, row in peers.head(10).iterrows():
            result["leading_stock_candidates"].append(
                {
                    "code": str(row.get("code") or ""),
                    "name": str(row.get("name") or ""),
                    "lb": int(row.get("lb") or 0),
                    "industry": str(row.get("industry") or ""),
                    "amount": float(row.get("amount") or 0.0),
                    "first_time": str(row.get("first_time") or ""),
                    "is_selected": str(row.get("code") or "") == selected_code,
                }
            )
    except Exception:
        pass
    
    # 获取总龙头分时数据
    leading_tick_df = get_tick_data(leading_stock.get("code", ""), date)
    if leading_tick_df is None:
        result["notes"].append("总龙头分时数据未获取（接口或缓存为空），跳过分离确认。")
        return result
    
    # 识别异动时间点
    volatility_points = detect_volatility_timepoints(leading_tick_df, leading_stock)
    result['volatility_points'] = volatility_points
    
    if not volatility_points:
        result["notes"].append("未识别到总龙头炸板/跳水异动点（或涨跌停比例与快照不匹配）。")
        return result

    candidates = get_candidate_stocks(
        leading_stock, date, trade_days, df_zt_all=df_zt
    )
    if not candidates:
        result["notes"].append(
            "同板块成分股未取到且无同梯队备选；请检查行业名称与东财板块是否一致。"
        )
    
    # 计算每个候选股的分离得分
    for candidate in candidates:
        candidate_tick_df = get_tick_data(candidate['code'], date)
        if candidate_tick_df is not None:
            # 对每个异动时间点计算得分
            total_score = 0
            all_details = []
            for point in volatility_points:
                score, details = calculate_separation_score(
                    candidate_tick_df, 
                    point['time'], 
                    leading_tick_df,
                    point.get('type', '')
                )
                total_score += score
                if details:
                    all_details.append(details)
            
            candidate['separation_score'] = total_score
            candidate['separation_details'] = all_details
            
            # 生成判断依据备注
            if all_details:
                best_detail = max(all_details, key=lambda x: x.get('candidate_change', 0))
                candidate['remark'] = (
                    f"今日在总龙头{best_detail['volatility_type']}时（{best_detail['volatility_time']}），"
                    f"该股{best_detail['pattern']}，涨跌幅{best_detail['candidate_change']:+.2f}%，"
                    f"而总龙头涨跌幅{best_detail['leading_change']:+.2f}%，确认独立走势。"
                )
            
            result['candidates'].append(candidate)
    
    # 按得分排序
    result['candidates'].sort(key=lambda x: x.get('separation_score', 0), reverse=True)
    
    return result


def clear_tick_cache() -> None:
    """清空分时数据缓存"""
    _ensure_tick_cache_dir()
    for file in os.listdir(TICK_CACHE_DIR):
        if file.endswith('.json'):
            os.remove(os.path.join(TICK_CACHE_DIR, file))


def get_tick_cache_size() -> int:
    """获取分时数据缓存大小（文件数）"""
    _ensure_tick_cache_dir()
    return len([f for f in os.listdir(TICK_CACHE_DIR) if f.endswith('.json')])
