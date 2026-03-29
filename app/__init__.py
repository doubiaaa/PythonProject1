from flask import Flask
import os

# 获取项目根目录（app/__init__.py 上溯两级）
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 初始化 Flask 应用，显式指定模板文件夹路径
app = Flask(__name__, template_folder=os.path.join(project_root, "templates"))
app.json.ensure_ascii = False
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024


@app.after_request
def _security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


from app.routes import main
