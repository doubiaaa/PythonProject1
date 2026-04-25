# -*- coding: utf-8 -*-
"""
价格数据缓存：缓存股票历史价格数据，避免重复请求 AKShare
"""

import os
import json
from typing import Optional

import pandas as pd
import akshare as ak

# 尝试导入 Redis 客户端
try:
    from backend.app.utils.database import db
    use_redis = True
except ImportError:
    use_redis = False


_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
CACHE_DIR = os.path.join(DATA_DIR, "price_cache")


def _ensure_cache_dir() -> None:
    """确保缓存目录存在"""
    os.makedirs(CACHE_DIR, exist_ok=True)


def get_cache_file_path(code: str, start_date: str, end_date: str) -> str:
    """获取缓存文件路径"""
    _ensure_cache_dir()
    return os.path.join(CACHE_DIR, f"{code}_{start_date}_{end_date}.json")


def get_redis_cache_key(code: str, start_date: str, end_date: str) -> str:
    """获取 Redis 缓存键"""
    return f"price:{code}:{start_date}:{end_date}"


def fetch_stock_hist_with_cache(
    code: str, 
    start_date: str, 
    end_date: str
) -> Optional[pd.DataFrame]:
    """
    获取股票历史数据，优先使用缓存
    """
    # 规范化代码
    code = code.strip()
    if not code:
        return None
    
    # 生成缓存键
    redis_key = get_redis_cache_key(code, start_date, end_date)
    cache_file = get_cache_file_path(code, start_date, end_date)
    
    # 尝试从 Redis 缓存读取
    if use_redis:
        try:
            redis_client = db.get_redis_client()
            data = redis_client.get(redis_key)
            if data:
                data = json.loads(data)
                df = pd.DataFrame(data)
                df['日期'] = pd.to_datetime(df['日期']).dt.strftime('%Y%m%d')
                for col in ['开盘', '收盘', '最高', '最低', '成交量', '成交额']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                return df
        except Exception:
            pass
    
    # 尝试从磁盘缓存读取
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            df = pd.DataFrame(data)
            df['日期'] = pd.to_datetime(df['日期']).dt.strftime('%Y%m%d')
            for col in ['开盘', '收盘', '最高', '最低', '成交量', '成交额']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            return df
        except Exception:
            pass
    
    # 从 AKShare 获取
    try:
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq"
        )
        if df is None or df.empty:
            return None
        
        # 转换数据格式
        df['日期'] = pd.to_datetime(df['日期']).dt.strftime('%Y%m%d')
        data = df.to_dict('records')
        
        # 保存到 Redis 缓存
        if use_redis:
            try:
                redis_client = db.get_redis_client()
                redis_client.setex(redis_key, 3600 * 24 * 30, json.dumps(data))  # 30天过期
            except Exception:
                pass
        
        # 保存到磁盘缓存
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return df
    except Exception:
        return None


def fetch_open_close_qfq_cached(
    code: str, 
    d_entry: str, 
    d_exit: str
) -> tuple[Optional[float], Optional[float]]:
    """
    带缓存的前复权开盘/收盘价获取
    """
    start = min(d_entry, d_exit)
    end = max(d_entry, d_exit)
    
    df = fetch_stock_hist_with_cache(code, start, end)
    if df is None or df.empty:
        return None, None
    
    row_e = df[df['日期'] == d_entry]
    row_x = df[df['日期'] == d_exit]
    
    if row_e.empty or row_x.empty:
        return None, None
    
    o = row_e['开盘'].iloc[-1]
    cl = row_x['收盘'].iloc[-1]
    
    o = float(pd.to_numeric(o, errors="coerce"))
    cl = float(pd.to_numeric(cl, errors="coerce"))
    
    if pd.isna(o) or pd.isna(cl) or o <= 0:
        return None, None
    
    return o, cl


def clear_cache() -> None:
    """清空缓存"""
    # 清空 Redis 缓存
    if use_redis:
        try:
            redis_client = db.get_redis_client()
            keys = redis_client.keys("price:*")
            if keys:
                redis_client.delete(*keys)
        except Exception:
            pass
    
    # 清空磁盘缓存
    _ensure_cache_dir()
    for file in os.listdir(CACHE_DIR):
        if file.endswith('.json'):
            os.remove(os.path.join(CACHE_DIR, file))


def get_cache_size() -> int:
    """获取缓存大小（文件数）"""
    _ensure_cache_dir()
    return len([f for f in os.listdir(CACHE_DIR) if f.endswith('.json')])
