import os
import json

# config.py 位于 app/utils/，项目根需上溯三级
_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)
CONFIG_FILE = os.path.join(_PROJECT_ROOT, "replay_config.json")

# 默认配置
DEFAULT_CONFIG = {
    "zhipu_api_key": "",
    "serverchan_sendkey": "",  # Server酱 SendKey；多个用英文逗号分隔，空则不发微信
    "smtp_host": "",
    "smtp_port": 587,
    "smtp_user": "",
    "smtp_password": "",
    "smtp_from": "",
    "mail_to": "",  # 收件人，多个英文逗号分隔
    "smtp_ssl": False,  # True 时用 SMTPS（如 465）
    # 邮件正文是否套统一 HTML 模板（false 时退回旧版简单 HTML 外壳 + 纯文本备选）
    "email_html_template_enabled": True,
    # 长文邮件是否增加「报告标题区 + 摘要高亮 + 报告说明」前缀（false 则仅渲染裸 Markdown）
    "email_content_prefix": True,
    # 邮件顶部要闻推送块最多展示条数（超出则提示回系统查看全文）
    "email_news_max_items": 3,
    # 要闻摘要中需剔除的固定前缀（正则字面替换）
    "email_news_filter_prefix": "【本文系数据通用户提前专享】",
    "email_app_version": "1.0",
    # 周报邮件是否尝试内嵌项目根目录下的权重/净值图（需先生成 png）
    "weekly_email_attach_charts": True,
    "cache_expire": 3600,  # 缓存过期时间（秒）
    "retry_times": 2,  # AKShare 等网络请求重试次数（含首次）
    # 策略权重（须约等于 1.0）；异常时程序回退默认
    "w_main": 0.22,
    "w_dragon": 0.18,
    "w_kline": 0.18,
    "w_liq": 0.14,
    "w_tech": 0.28,
    "tech_eval_topn": 12,  # 技术面精算队列长度（3～48）
    "enable_tech_momentum": True,
    # 财联社等公开要闻：拉取摘要并与龙头池/主线做关键词关联；关闭则不请求、不推送要闻块
    "enable_finance_news": True,
    # 东财个股主力净流入排名（今日）；关闭则不请求
    "enable_individual_fund_flow_rank": True,
    "individual_fund_flow_top_n": 12,
    # 概念板块成分股快照（东财）；名称为空列表则跳过（可在 replay_config.json 中配置，如 ["人工智能","固态电池"]）
    "enable_concept_cons_snapshot": True,
    "concept_board_symbols": [],
    # 腾讯分笔（稳定性一般，默认关闭）；仅用于调试「分离确认」类分析
    "enable_intraday_tick_probe": False,
    "intraday_tick_probe_symbol": "",  # 6 位代码，如 000001；空则不请求
    # 龙头池周度邮件：周末脚本汇总涨跌；关闭则只跑脚本不寄信（或手动 --dry-run）
    "enable_weekly_performance_email": True,
    # 周报复盘末尾是否调用智谱生成「风格诊断+下周侧重」（需 ZHIPU_API_KEY）
    "enable_weekly_ai_insight": True,
    # 周报中是否拉取本周交易日市场快照（涨停家数、溢价、锚点日涨幅前20市值等）
    "enable_weekly_market_snapshot": True,
    # 复盘成功后将打板/趋势/低吸三指数写入 data/market_style_indices.json
    "enable_daily_style_indices_persist": True,
    # 周报是否计算「自然周」严格涨幅前 20（全市场抽样，较慢）
    "enable_strict_weekly_top20": True,
    "weekly_strict_top20_max_universe": 2800,
    # 周报后根据龙头池风格收益更新 strategy_preference.json，供次日复盘 prompt 侧重
    "enable_strategy_feedback_loop": True,
    "strategy_weight_smoothing": 0.3,
    "strategy_weight_max_single": 0.55,
    "strategy_weight_min_each": 0.08,
    # 某风格桶样本数不足则不单独跟数据走（单周模式）
    "min_trades_per_style_for_weight": 3,
    # 多周衰减：最近 multi_week_lookback 周，越近权重越高
    "use_multi_week_decay_for_strategy": True,
    "multi_week_lookback": 4,
    "strategy_week_decay_factor": 0.75,
    # 多周合计每桶至少几条才参与该桶数据更新
    "min_total_trades_per_bucket_multiweek": 3,
    "strategy_max_change_per_week": 0.25,
    "strategy_shift_pullback": 0.5,
    # 每日复盘前轻量探测市场风格是否切换（多一次智谱调用）
    "enable_style_stability_probe": True,
    # 周报权重更新后异常时额外发一封提醒邮件
    "enable_weekly_weight_anomaly_email": True,
    # 模拟账户：按程序龙头池与收盘价撮合（data/simulated_account.json）
    "enable_simulated_account": True,
    "simulated_account_path": "data/simulated_account.json",
    "simulated_config_path": "data/simulated_config.json",
    # 模拟买入价格：close_of_recommendation_day=当日收盘撮合；next_day_open=仅写 pending，次日开盘脚本买入
    "simulated_buy_price_type": "next_day_open",
    # 模拟账户每笔买卖成交通知（与复盘共用 SMTP / MAIL_TO）
    "enable_simulated_trade_notification": False,
}


class ConfigManager:
    """配置管理类（持久化）"""

    def __init__(self, config_file=CONFIG_FILE):
        self.config_file = config_file
        self.config = self.load_config()

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                    # 合并默认配置
                    merged = DEFAULT_CONFIG.copy()
                    merged.update(user_config)
                    return merged
            except Exception:
                return DEFAULT_CONFIG.copy()
        else:
            return DEFAULT_CONFIG.copy()

    def save_config(self):
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save_config()
