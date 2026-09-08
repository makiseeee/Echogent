import json
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import threading
from typing import Optional

from modules.activity import tracker

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>Echo PC Agent · 控制中心</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        :root {
            --bg-color: #121316;
            --card-bg: #1a1b20;
            --border-color: #2a2c34;
            --text-main: #e6e8ee;
            --text-sub: #8b8f9e;
            --accent: #5e81ac;
            --accent-green: #a3be8c;
            --accent-yellow: #ebcb8b;
            --accent-red: #bf616a;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif; }
        body { background: var(--bg-color); color: var(--text-main); padding: 30px 20px; display: flex; justify-content: center; }
        .container { max-width: 680px; width: 100%; }
        header { margin-bottom: 24px; display: flex; justify-content: space-between; align-items: center; }
        h1 { font-size: 20px; font-weight: 600; letter-spacing: 0.5px; }
        .badge { background: #2e3440; color: var(--accent-green); padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; border: 1px solid rgba(163, 190, 140, 0.3); }
        .card { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
        .card-title { font-size: 14px; color: var(--text-sub); text-transform: uppercase; margin-bottom: 14px; font-weight: 600; letter-spacing: 1px; }
        .hero-status { display: flex; align-items: baseline; gap: 10px; margin-bottom: 8px; }
        .hero-app { font-size: 24px; font-weight: 700; color: #eceff4; }
        .hero-category { font-size: 13px; color: var(--accent); background: rgba(94, 129, 172, 0.15); padding: 2px 8px; border-radius: 6px; }
        .hero-title { font-size: 14px; color: var(--text-sub); word-break: break-all; margin-bottom: 12px; line-height: 1.5; }
        .stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 15px; border-top: 1px solid var(--border-color); padding-top: 15px; }
        .stat-item { text-align: center; }
        .stat-value { font-size: 18px; font-weight: 600; color: var(--text-main); margin-bottom: 4px; }
        .stat-label { font-size: 12px; color: var(--text-sub); }
        .controls { display: flex; gap: 10px; margin-top: 10px; }
        button { background: #2e3440; color: var(--text-main); border: 1px solid var(--border-color); padding: 8px 16px; border-radius: 8px; cursor: pointer; font-size: 13px; transition: all 0.2s; }
        button:hover { background: #3b4252; border-color: var(--accent); }
        button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
        button.primary:hover { background: #81a1c1; }
        pre { background: #15161b; border: 1px solid var(--border-color); border-radius: 8px; padding: 14px; font-size: 12px; color: #d8dee9; overflow-x: auto; margin-top: 10px; max-height: 240px; }
        .footer { text-align: center; font-size: 12px; color: var(--text-sub); margin-top: 30px; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🖥️ Echo PC Agent · 驻留控制中心</h1>
            <span class="badge" id="badge-status">● 运行中 (8766)</span>
        </header>

        <div class="card">
            <div class="card-title">当前电脑前台焦点感知</div>
            <div class="hero-status">
                <span class="hero-app" id="app-name">加载中...</span>
                <span class="hero-category" id="app-category">-</span>
            </div>
            <div class="hero-title" id="window-title">检测中...</div>
            <div id="summary-text" style="font-size: 13px; color: var(--accent-green); margin-bottom: 8px;">-</div>

            <div class="stats-grid">
                <div class="stat-item">
                    <div class="stat-value" id="duration-val">-</div>
                    <div class="stat-label">持续时长</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value" id="idle-val">-</div>
                    <div class="stat-label">闲置秒数</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value" id="visual-val">-</div>
                    <div class="stat-label">视觉采集许可</div>
                </div>
            </div>
        </div>

        <div class="card">
            <div class="card-title">宏观工作流与会话统计</div>
            <div style="font-size: 14px; color: var(--text-main); margin-bottom: 10px;" id="macro-theme">宏观主题: -</div>
            <div style="font-size: 12px; color: var(--text-sub);" id="macro-breakdown">-</div>
        </div>

        <div class="card">
            <div class="card-title">接口交互与快捷测试</div>
            <div class="controls">
                <button onclick="testApi('summary')">测试 ?level=summary</button>
                <button onclick="testApi('detail')">测试 ?level=detail</button>
                <button onclick="testApi('visual')">测试 ?level=visual</button>
                <button onclick="togglePrivacy()" id="privacy-btn">切换隐私模式</button>
            </div>
            <pre id="api-output">// 点击上方按钮实时查看 API 报文返回</pre>
        </div>

        <div class="footer">
            Echo 智能桌面伴侣系统 · PC 侧无缝感知基座 · ZeroTier 内部私网专供
        </div>
    </div>

    <script>
        async function fetchStatus() {
            try {
                const res = await fetch('/api/pc/activity?level=detail');
                const data = await res.json();
                document.getElementById('app-name').innerText = data.app || '未知应用';
                document.getElementById('app-category').innerText = data.category || 'other';
                document.getElementById('window-title').innerText = data.window_title || '(无标题)';
                document.getElementById('summary-text').innerText = data.summary || '';
                document.getElementById('duration-val').innerText = (data.duration_minutes || 0) + ' 分钟';
                document.getElementById('idle-val').innerText = (data.idle_seconds || 0) + ' 秒';
                
                const vSafe = data.visual_safe ? '✅ 允许' : '❌ 阻断';
                document.getElementById('visual-val').innerText = vSafe;
                document.getElementById('visual-val').style.color = data.visual_safe ? 'var(--accent-green)' : 'var(--accent-red)';

                if (data.privacy_mode) {
                    document.getElementById('badge-status').innerText = '🛡️ 隐私保护中';
                    document.getElementById('badge-status').style.color = 'var(--accent-yellow)';
                } else {
                    document.getElementById('badge-status').innerText = '● 正常运行中';
                    document.getElementById('badge-status').style.color = 'var(--accent-green)';
                }

                if (data.macro_session) {
                    document.getElementById('macro-theme').innerText = '宏观主题: ' + (data.macro_session.theme || '-');
                    const b = data.macro_session.breakdown || {};
                    const items = Object.entries(b).map(([k, v]) => `${k}: ${v}%`);
                    document.getElementById('macro-breakdown').innerText = '近半小时时间片: ' + (items.join(' | ') || '采样中');
                }
            } catch (e) {
                document.getElementById('badge-status').innerText = '⚠️ 连接断开';
                document.getElementById('badge-status').style.color = 'var(--accent-red)';
            }
        }

        async function testApi(level) {
            try {
                const res = await fetch('/api/pc/activity?level=' + level);
                const data = await res.json();
                document.getElementById('api-output').innerText = JSON.stringify(data, null, 2);
            } catch (e) {
                document.getElementById('api-output').innerText = '请求失败: ' + e;
            }
        }

        async function togglePrivacy() {
            const res = await fetch('/api/pc/privacy/toggle', { method: 'POST' });
            const data = await res.json();
            alert('隐私模式已切换为: ' + (data.privacy_mode ? '开启' : '关闭'));
            fetchStatus();
        }

        fetchStatus();
        setInterval(fetchStatus, 3000);
    </script>
</body>
</html>
"""

class EchoRequestHandler(BaseHTTPRequestHandler):
    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/":
            body = DASHBOARD_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/pc/health":
            self._send_json({"status": "ok", "service": "echo-pc-agent", "version": "2.0.0"})
            return

        try:
            if path == "/api/pc/activity":
                params = urllib.parse.parse_qs(parsed.query)
                level = params.get("level", ["summary"])[0]
                report = tracker.get_report(level=level)
                self._send_json(report)
                return

            self._send_json({"error": "Not Found"}, status=404)
        except Exception as e:
            self._send_json({"error": "Internal Server Error", "detail": str(e)}, status=500)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/pc/privacy/toggle":
            tracker.privacy_mode = not tracker.privacy_mode
            self._send_json({"status": "ok", "privacy_mode": tracker.privacy_mode})
            return

        self._send_json({"error": "Not Found"}, status=404)

    def log_message(self, format, *args):
        # 静默日志，避免刷屏
        pass

class AgentServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8766):
        self.host = host
        self.port = port
        self.server: Optional[HTTPServer] = None
        self.thread: Optional[threading.Thread] = None

    def start(self):
        self.server = ThreadingHTTPServer((self.host, self.port), EchoRequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        print(f"[Server] Echo PC Agent HTTP Server running on http://{self.host}:{self.port}")

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            print("[Server] Echo PC Agent HTTP Server stopped.")
