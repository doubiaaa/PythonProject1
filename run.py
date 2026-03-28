# -*- coding: utf-8 -*-
"""
次日竞价半路模式（BS 架构）
功能：收盘后按策略选股 + 智谱 GLM 生成次日竞价预案
依赖：pip install akshare pandas requests flask
"""

from app import app

if __name__ == "__main__":
    # 检查依赖
    try:
        import akshare
        import flask
        import pandas
        import requests
    except ImportError as e:
        print(f"缺少依赖库：{e}")
        print("请执行：pip install akshare pandas requests flask")
        exit(1)

    app.run(debug=False, host='0.0.0.0', port=5000)
