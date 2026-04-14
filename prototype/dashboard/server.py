"""
可观测性 Dashboard - 基于 Flask + watchdog 的实时状态展示
"""
import json
import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import threading
import time

from flask import Flask, render_template_string, jsonify, Response
from werkzeug.serving import make_server
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class SystemMonitor(FileSystemEventHandler):
    """监听 system_root 目录的变化"""

    def __init__(self, system_root: str):
        self.system_root = Path(system_root)
        self.events = []
        self.lock = threading.Lock()

    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith(".json"):
            with self.lock:
                self.events.append(
                    {
                        "type": "created",
                        "path": event.src_path,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

    def on_moved(self, event):
        if not event.is_directory and event.dest_path.endswith(".json"):
            with self.lock:
                self.events.append(
                    {
                        "type": "moved",
                        "from": event.src_path,
                        "to": event.dest_path,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

    def get_recent_events(self, limit: int = 20) -> list:
        """获取最近的事件"""
        with self.lock:
            return self.events[-limit:]

    def clear_events(self):
        """清空事件列表"""
        with self.lock:
            self.events.clear()


class DashboardServer:
    """Dashboard 服务器"""

    def __init__(self, system_root: str, port: int = 5000):
        self.system_root = Path(system_root)
        self.port = port
        self.app = Flask(__name__)
        self.monitor = SystemMonitor(str(self.system_root))
        self.observer = None
        self._setup_routes()

    def _setup_routes(self):
        """设置 Flask 路由"""

        @self.app.route("/")
        def index():
            return render_template_string(self._get_html_template())

        @self.app.route("/api/status")
        def get_status():
            """获取系统状态"""
            status = {
                "agents": self._get_agents_status(),
                "messages": self._get_messages_status(),
                "errors": self._get_errors_status(),
                "timestamp": datetime.now().isoformat(),
            }
            return jsonify(status)

        @self.app.route("/api/events")
        def stream_events():
            """SSE 流推送事件"""

            def event_generator():
                last_count = 0
                while True:
                    events = self.monitor.get_recent_events()
                    if len(events) > last_count:
                        new_events = events[last_count:]
                        for event in new_events:
                            yield f"data: {json.dumps(event)}\n\n"
                        last_count = len(events)
                    time.sleep(1)

            return Response(event_generator(), mimetype="text/event-stream")

    def _get_agents_status(self) -> dict:
        """获取所有 Agent 的状态"""
        agents_status = {}
        registry_dir = self.system_root / "registry"

        if registry_dir.exists():
            for registry_file in registry_dir.glob("*.json"):
                try:
                    with open(registry_file) as f:
                        agent_data = json.load(f)
                    agent_name = agent_data["name"]
                    inbox_dir = (
                        self.system_root / "agents" / agent_name / "inbox"
                    )
                    inbox_count = (
                        len(list(inbox_dir.glob("*.json")))
                        if inbox_dir.exists()
                        else 0
                    )
                    agents_status[agent_name] = {
                        "status": agent_data.get("status", "unknown"),
                        "pid": agent_data.get("pid", 0),
                        "last_seen": agent_data.get("last_seen", ""),
                        "inbox_count": inbox_count,
                        "capabilities": agent_data.get("capabilities", []),
                    }
                except Exception as e:
                    print(f"Error reading registry {registry_file}: {e}")

        return agents_status

    def _get_messages_status(self) -> dict:
        """获取消息统计"""
        status = {
            "total_processed": 0,
            "in_progress": 0,
            "pending": 0,
            "recent_messages": [],
        }

        # 统计 archive 中的消息
        archive_dir = self.system_root / "archive"
        if archive_dir.exists():
            status["total_processed"] = len(list(archive_dir.glob("*.json")))

        # 统计 processing 消息
        agents_dir = self.system_root / "agents"
        if agents_dir.exists():
            for agent_dir in agents_dir.iterdir():
                if agent_dir.is_dir():
                    workspace_dir = agent_dir / "workspace"
                    if workspace_dir.exists():
                        status["in_progress"] += len(
                            list(workspace_dir.glob("*.processing"))
                        )

        # 统计 pending 消息
        bus_pending_dir = self.system_root / "bus" / "pending"
        if bus_pending_dir.exists():
            status["pending"] = len(list(bus_pending_dir.glob("*.json")))

        # 获取最近的消息
        recent_events = self.monitor.get_recent_events(10)
        for event in recent_events:
            if "to" in event:
                path = event["to"]
            else:
                path = event.get("path", "")
            if path.endswith(".json"):
                status["recent_messages"].append(
                    {
                        "path": path,
                        "timestamp": event["timestamp"],
                        "type": event["type"],
                    }
                )

        return status

    def _get_errors_status(self) -> dict:
        """获取错误统计"""
        status = {"dead_letter_count": 0, "recent_errors": []}

        dead_letter_dir = self.system_root / "bus" / "dead_letter"
        if dead_letter_dir.exists():
            error_files = list(dead_letter_dir.glob("*.json"))
            status["dead_letter_count"] = len(error_files)

            # 获取最近的错误
            for error_file in sorted(error_files, reverse=True)[:5]:
                try:
                    with open(error_file) as f:
                        error_data = json.load(f)
                    status["recent_errors"].append(
                        {
                            "message_id": error_data.get("message_id", ""),
                            "sender": error_data.get("sender", ""),
                            "timestamp": error_data.get("timestamp", ""),
                        }
                    )
                except Exception as e:
                    print(f"Error reading error file {error_file}: {e}")

        return status

    def _get_html_template(self) -> str:
        """获取 HTML 模板"""
        return """
<!DOCTYPE html>
<html>
<head>
    <title>Agent Communication Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; }
        .header h1 { color: #333; }
        .lang-btn { padding: 6px 14px; border: 1px solid #ccc; border-radius: 6px; background: white; cursor: pointer; font-size: 13px; color: #555; transition: all 0.2s; }
        .lang-btn:hover { background: #f0f0f0; border-color: #999; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .card { background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .card h2 { font-size: 14px; color: #666; margin-bottom: 10px; text-transform: uppercase; }
        .card .value { font-size: 32px; font-weight: bold; color: #333; }
        .card .detail { font-size: 12px; color: #999; margin-top: 10px; }
        .agents { background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 30px; }
        .agents h2 { margin-bottom: 15px; }
        .agent-item { padding: 10px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; }
        .agent-item:last-child { border-bottom: none; }
        .agent-name { font-weight: 500; }
        .agent-status { display: flex; gap: 15px; font-size: 12px; color: #666; }
        .status-badge { display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }
        .status-running { background: #d4edda; color: #155724; }
        .status-error { background: #f8d7da; color: #721c24; }
        .messages { background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .messages h2 { margin-bottom: 15px; }
        .message-item { padding: 10px; border-left: 3px solid #007bff; background: #f8f9fa; margin-bottom: 10px; font-size: 12px; }
        .message-item .timestamp { color: #999; }
        .error-item { border-left-color: #dc3545; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 <span data-i18n="title"></span></h1>
            <button class="lang-btn" id="lang-toggle" onclick="toggleLang()"></button>
        </div>

        <div class="grid">
            <div class="card">
                <h2 data-i18n="total_processed"></h2>
                <div class="value" id="total-processed">0</div>
                <div class="detail" data-i18n="total_processed_detail"></div>
            </div>
            <div class="card">
                <h2 data-i18n="in_progress"></h2>
                <div class="value" id="in-progress">0</div>
                <div class="detail" data-i18n="in_progress_detail"></div>
            </div>
            <div class="card">
                <h2 data-i18n="pending"></h2>
                <div class="value" id="pending">0</div>
                <div class="detail" data-i18n="pending_detail"></div>
            </div>
            <div class="card">
                <h2 data-i18n="errors"></h2>
                <div class="value" id="errors">0</div>
                <div class="detail" data-i18n="errors_detail"></div>
            </div>
        </div>

        <div class="agents">
            <h2 data-i18n="active_agents"></h2>
            <div id="agents-list"></div>
        </div>

        <div class="messages">
            <h2 data-i18n="recent_activity"></h2>
            <div id="messages-list"></div>
        </div>
    </div>

    <script>
        const i18n = {
            en: {
                title: 'Agent Communication Dashboard',
                lang_btn: '中文',
                total_processed: 'Total Processed',
                total_processed_detail: 'messages in archive',
                in_progress: 'In Progress',
                in_progress_detail: 'messages being processed',
                pending: 'Pending',
                pending_detail: 'messages in bus',
                errors: 'Errors',
                errors_detail: 'messages in dead_letter',
                active_agents: 'Active Agents',
                recent_activity: 'Recent Activity',
                loading: 'Loading...',
                pid: 'PID',
                inbox: 'Inbox',
            },
            zh: {
                title: 'Agent 通信监控台',
                lang_btn: 'English',
                total_processed: '已处理消息',
                total_processed_detail: '归档中的消息数',
                in_progress: '处理中',
                in_progress_detail: '正在处理的消息数',
                pending: '待路由',
                pending_detail: '总线中等待路由的消息数',
                errors: '错误',
                errors_detail: '死信队列中的消息数',
                active_agents: '活跃 Agent',
                recent_activity: '最近动态',
                loading: '加载中...',
                pid: '进程号',
                inbox: '待处理',
            }
        };

        let lang = localStorage.getItem('dashboard_lang') || 'zh';

        function t(key) {
            return i18n[lang][key] || key;
        }

        function applyLang() {
            document.querySelectorAll('[data-i18n]').forEach(el => {
                el.textContent = t(el.dataset.i18n);
            });
            document.getElementById('lang-toggle').textContent = t('lang_btn');
            document.title = t('title');
        }

        function toggleLang() {
            lang = lang === 'zh' ? 'en' : 'zh';
            localStorage.setItem('dashboard_lang', lang);
            applyLang();
        }

        function updateStatus() {
            fetch('/api/status')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('total-processed').textContent = data.messages.total_processed;
                    document.getElementById('in-progress').textContent = data.messages.in_progress;
                    document.getElementById('pending').textContent = data.messages.pending;
                    document.getElementById('errors').textContent = data.errors.dead_letter_count;

                    const agentsList = document.getElementById('agents-list');
                    if (Object.keys(data.agents).length === 0) {
                        agentsList.innerHTML = `<div style="color:#999;padding:10px">${t('loading')}</div>`;
                    } else {
                        agentsList.innerHTML = '';
                        for (const [name, status] of Object.entries(data.agents)) {
                            agentsList.innerHTML += `
                                <div class="agent-item">
                                    <div class="agent-name">${name}</div>
                                    <div class="agent-status">
                                        <span class="status-badge status-running">${status.status}</span>
                                        <span>${t('pid')}: ${status.pid}</span>
                                        <span>${t('inbox')}: ${status.inbox_count}</span>
                                    </div>
                                </div>`;
                        }
                    }

                    const messagesList = document.getElementById('messages-list');
                    if (data.messages.recent_messages.length === 0) {
                        messagesList.innerHTML = `<div style="color:#999;padding:10px">${t('loading')}</div>`;
                    } else {
                        messagesList.innerHTML = '';
                        for (const msg of data.messages.recent_messages) {
                            messagesList.innerHTML += `
                                <div class="message-item">
                                    <div>${msg.path.split(/[\\/]/).pop()}</div>
                                    <div class="timestamp">${msg.timestamp} — ${msg.type}</div>
                                </div>`;
                        }
                    }
                });
        }

        // 初始化语言
        applyLang();
        updateStatus();
        setInterval(updateStatus, 2000);

        const eventSource = new EventSource('/api/events');
        eventSource.onmessage = () => updateStatus();
    </script>
</body>
</html>
        """

    def start(self):
        """启动 Dashboard 服务器"""
        # 启动文件监听
        self.observer = Observer()
        self.observer.schedule(
            self.monitor, str(self.system_root), recursive=True
        )
        self.observer.start()

        print(f"Dashboard server starting on http://localhost:{self.port}")
        self.app.run(host="0.0.0.0", port=self.port, debug=False, use_reloader=False)

    def start_in_thread(self):
        """在线程中启动 Dashboard 服务器（非阻塞）"""
        # 启动文件监听
        self.observer = Observer()
        self.observer.schedule(
            self.monitor, str(self.system_root), recursive=True
        )
        self.observer.start()

        print(f"Dashboard server starting on http://localhost:{self.port}")
        # 使用 werkzeug 的 make_server 来避免阻塞
        server = make_server("0.0.0.0", self.port, self.app, threaded=True)
        server.serve_forever()

    def stop(self):
        """停止 Dashboard 服务器"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
