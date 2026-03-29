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
