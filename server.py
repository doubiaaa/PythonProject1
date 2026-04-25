from flask import Flask, send_from_directory
import os

app = Flask(__name__)

# 静态文件目录
STATIC_FOLDER = os.path.join(os.path.dirname(__file__), 'frontend', 'dist')

@app.route('/')
def index():
    return send_from_directory(STATIC_FOLDER, 'index.html')

@app.route('/assets/<path:path>')
def send_assets(path):
    return send_from_directory(os.path.join(STATIC_FOLDER, 'assets'), path)

@app.route('/api/health')
def health_check():
    return {'status': 'ok'}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
