import mysql.connector
import redis
from mysql.connector import Error
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class Database:
    def __init__(self):
        self.mysql_connection = None
        self.redis_client = None
        self.connect()

    def connect(self):
        try:
            # 连接 MySQL
            self.mysql_connection = mysql.connector.connect(
                host=os.getenv('MYSQL_HOST', 'localhost'),
                port=int(os.getenv('MYSQL_PORT', '3306')),
                user=os.getenv('MYSQL_USER', 'python_project1'),
                password=os.getenv('MYSQL_PASSWORD', 'python_project1'),
                database=os.getenv('MYSQL_DATABASE', 'python_project1')
            )
            print("MySQL 连接成功")

            # 连接 Redis
            self.redis_client = redis.Redis(
                host=os.getenv('REDIS_HOST', 'localhost'),
                port=int(os.getenv('REDIS_PORT', '6379')),
                db=int(os.getenv('REDIS_DB', '0'))
            )
            print("Redis 连接成功")
        except Error as e:
            print(f"数据库连接错误: {e}")

    def get_mysql_connection(self):
        if not self.mysql_connection or not self.mysql_connection.is_connected():
            self.connect()
        return self.mysql_connection

    def get_redis_client(self):
        if not self.redis_client:
            self.connect()
        return self.redis_client

    def close(self):
        if self.mysql_connection and self.mysql_connection.is_connected():
            self.mysql_connection.close()
        if self.redis_client:
            self.redis_client.close()

# 创建数据库实例
db = Database()
