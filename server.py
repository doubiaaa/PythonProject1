from flask import Flask, jsonify, request
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)

@app.route('/api/health')
def health_check():
    return jsonify({"status": "ok"})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if username == 'admin' and password == 'admin123':
        return jsonify({"success": True, "token": "test-token"})
    else:
        return jsonify({"success": False, "message": "用户名或密码错误"})

@app.route('/api/config', methods=['GET', 'POST'])
def config():
    if request.method == 'GET':
        return jsonify({
            "deepseek_api_key": "",
            "smtp_host": "",
            "smtp_port": 587,
            "smtp_user": "",
            "smtp_password": "",
            "smtp_from": "",
            "mail_to": ""
        })
    elif request.method == 'POST':
        data = request.json
        return jsonify({"success": True, "message": "配置保存成功"})

@app.route('/api/replay', methods=['POST'])
def replay():
    return jsonify({"success": True, "message": "复盘任务已启动"})

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=8000)
