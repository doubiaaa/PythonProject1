-- 创建数据库
CREATE DATABASE IF NOT EXISTS python_project1 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE python_project1;

-- 配置表
CREATE TABLE IF NOT EXISTS configurations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    `key` VARCHAR(255) NOT NULL UNIQUE,
    `value` TEXT NOT NULL,
    description VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 复盘报告表
CREATE TABLE IF NOT EXISTS replay_reports (
    id INT AUTO_INCREMENT PRIMARY KEY,
    trade_date DATE NOT NULL,
    report_content TEXT NOT NULL,
    status VARCHAR(50) DEFAULT 'completed',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 观察池记录表
CREATE TABLE IF NOT EXISTS watchlist_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    trade_date DATE NOT NULL,
    stock_code VARCHAR(20) NOT NULL,
    stock_name VARCHAR(100) NOT NULL,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_stock_date (trade_date, stock_code)
);

-- 初始化默认配置
INSERT INTO configurations (`key`, `value`, description) VALUES
('deepseek_api_key', '', 'DeepSeek API Key'),
('smtp_host', '', 'SMTP 服务器地址'),
('smtp_port', '587', 'SMTP 服务器端口'),
('smtp_user', '', 'SMTP 用户名'),
('smtp_password', '', 'SMTP 密码'),
('smtp_from', '', '发件人邮箱'),
('mail_to', '', '收件人邮箱'),
('enable_email', 'false', '是否启用邮件通知');

-- 初始化默认用户
INSERT INTO users (username, password_hash, role) VALUES
('admin', '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', 'admin');
-- 密码: admin123
