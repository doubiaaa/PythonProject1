from flask import render_template, request, jsonify
from datetime import datetime
import threading
from app import app
from app.utils.config import ConfigManager
from app.services.data_fetcher import DataFetcher
from app.services.replay_task import ReplayTask

# 全局实例
config_mgr = ConfigManager()
data_fetcher = DataFetcher(
    cache_expire=config_mgr.get("cache_expire", 3600),
    retry_times=config_mgr.get("retry_times", 1)
)

# 全局任务实例
task = ReplayTask()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/start_replay', methods=['POST'])
def start_replay():
    data = request.get_json(silent=True) or {}
    date = data.get('date')
    api_key = data.get('api_key')
    serverchan_sendkey = (data.get('serverchan_sendkey') or '').strip()

    if not date or len(date) != 8:
        return jsonify({"error": "日期格式应为YYYYMMDD，如20260309"}), 400

    if not api_key:
        return jsonify({"error": "请输入智谱API Key"}), 400

    if not task.try_begin():
        return jsonify({"error": "复盘任务进行中，请稍后再试"}), 409

    config_mgr.set("zhipu_api_key", api_key)
    config_mgr.set("serverchan_sendkey", serverchan_sendkey)

    def run_task():
        task.run(date, api_key, data_fetcher, serverchan_sendkey=serverchan_sendkey)

    thread = threading.Thread(target=run_task, daemon=True)
    thread.start()

    return jsonify({"status": "started"})


@app.route('/api/task_status')
def task_status():
    s = task.snapshot()
    return jsonify(s)


@app.route('/api/get_defaults')
def get_defaults():
    return jsonify({
        "default_date": datetime.now().strftime("%Y%m%d"),
        "default_api_key": config_mgr.get("zhipu_api_key"),
        "default_serverchan_sendkey": config_mgr.get("serverchan_sendkey", ""),
        "mode_name": "次日竞价半路模式",
    })
