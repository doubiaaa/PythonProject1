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
    "cache_expire": 3600,  # 缓存过期时间（秒）
    "retry_times": 1,  # 网络请求重试次数
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
