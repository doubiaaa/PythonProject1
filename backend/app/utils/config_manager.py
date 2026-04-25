from backend.app.utils.database import db
import json

class ConfigManager:
    def __init__(self):
        self.db = db

    def get_config(self, key, default=None):
        """从数据库获取配置"""
        try:
            # 先从 Redis 缓存获取
            redis_client = self.db.get_redis_client()
            cached_value = redis_client.get(f"config:{key}")
            if cached_value:
                return json.loads(cached_value)

            # 从 MySQL 数据库获取
            connection = self.db.get_mysql_connection()
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT value FROM configurations WHERE `key` = %s", (key,))
            result = cursor.fetchone()
            cursor.close()

            if result:
                value = result['value']
                # 缓存到 Redis
                redis_client.set(f"config:{key}", json.dumps(value))
                return value
            return default
        except Exception as e:
            print(f"获取配置错误: {e}")
            return default

    def set_config(self, key, value):
        """设置配置到数据库"""
        try:
            # 更新 MySQL 数据库
            connection = self.db.get_mysql_connection()
            cursor = connection.cursor()
            cursor.execute(
                "INSERT INTO configurations (`key`, `value`) VALUES (%s, %s) ON DUPLICATE KEY UPDATE `value` = %s",
                (key, value, value)
            )
            connection.commit()
            cursor.close()

            # 更新 Redis 缓存
            redis_client = self.db.get_redis_client()
            redis_client.set(f"config:{key}", json.dumps(value))
            return True
        except Exception as e:
            print(f"设置配置错误: {e}")
            return False

    def get_all_configs(self):
        """获取所有配置"""
        try:
            connection = self.db.get_mysql_connection()
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT `key`, `value`, description FROM configurations")
            results = cursor.fetchall()
            cursor.close()
            return {row['key']: {'value': row['value'], 'description': row['description']} for row in results}
        except Exception as e:
            print(f"获取所有配置错误: {e}")
            return {}

# 创建配置管理器实例
config_manager = ConfigManager()
