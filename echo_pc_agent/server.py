import base64
import hashlib
import hmac
import json
import os
import socket
import struct
import threading
import time
from typing import Optional
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

from modules.activity import tracker
from modules.app_registry import registry

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

        <div class="card">
            <div class="card-title" style="display: flex; justify-content: space-between; align-items: center;">
                <span>📱 软件分类与权限管理 (App Registry)</span>
                <span id="apps-count-badge" class="badge" style="background: rgba(94, 129, 172, 0.2); color: var(--accent);">加载中...</span>
            </div>
            <div style="display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap;">
                <input type="text" id="app-search" placeholder="搜索软件名称或进程名..." style="flex: 1; min-width: 140px; background: #15161b; border: 1px solid var(--border-color); color: var(--text-main); padding: 7px 12px; border-radius: 6px; font-size: 12px;" oninput="filterApps()">
                <select id="cat-filter" style="background: #15161b; border: 1px solid var(--border-color); color: var(--text-main); padding: 7px 10px; border-radius: 6px; font-size: 12px;" onchange="filterApps()">
                    <option value="">全部分类</option>
                    <option value="coding">研发与代码工程 (coding)</option>
                    <option value="hardware_embedded">嵌入式与硬件 EDA (hardware_embedded)</option>
                    <option value="research_simulation">科学计算与学术科研 (research_simulation)</option>
                    <option value="creative_design">数字影音制作与设计 (creative_design)</option>
                    <option value="gaming">游戏竞技与泛娱乐 (gaming)</option>
                    <option value="communication_meeting">通讯社交与会议网课 (communication_meeting)</option>
                    <option value="productivity_system">日常生产力与系统工具 (productivity_system)</option>
                    <option value="other">其他未分类 (other)</option>
                </select>
                <button onclick="loadApps()" style="padding: 7px 14px;">刷新</button>
            </div>
            <div id="apps-table-container" style="max-height: 320px; overflow-y: auto; border: 1px solid var(--border-color); border-radius: 8px;">
                <table style="width: 100%; border-collapse: collapse; font-size: 12px; text-align: left;">
                    <thead style="position: sticky; top: 0; background: #202229; color: var(--text-sub); border-bottom: 1px solid var(--border-color);">
                        <tr>
                            <th style="padding: 8px 10px;">进程 / 软件</th>
                            <th style="padding: 8px 10px;">分类</th>
                            <th style="padding: 8px 10px; text-align: center;">视觉许可</th>
                            <th style="padding: 8px 10px; text-align: center;">强免打扰</th>
                        </tr>
                    </thead>
                    <tbody id="apps-tbody">
                        <tr><td colspan="4" style="text-align: center; padding: 20px; color: var(--text-sub);">加载软件清单中...</td></tr>
                    </tbody>
                </table>
            </div>
            <div id="apps-toast" style="font-size: 12px; color: var(--accent-green); margin-top: 8px; display: none;"></div>
        </div>

        <div class="footer">
            Echo 智能桌面伴侣系统 · PC 侧无缝感知基座 · ZeroTier 内部私网专供
        </div>
    </div>

    <script>
        function renderReport(data) {
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
                document.getElementById('badge-status').innerText = '🛡️ 隐私保护中 (WS 实时)';
                document.getElementById('badge-status').style.color = 'var(--accent-yellow)';
            } else {
                document.getElementById('badge-status').innerText = '● 实时推流中 (8766)';
                document.getElementById('badge-status').style.color = 'var(--accent-green)';
            }

            if (data.macro_session) {
                document.getElementById('macro-theme').innerText = '宏观主题: ' + (data.macro_session.theme || '-');
                const b = data.macro_session.breakdown || {};
                const items = Object.entries(b).map(([k, v]) => `${k}: ${v}%`);
                document.getElementById('macro-breakdown').innerText = '近半小时时间片: ' + (items.join(' | ') || '采样中');
            }
        }

        async function fetchStatus() {
            try {
                const res = await fetch('/api/pc/activity?level=detail');
                const data = await res.json();
                renderReport(data);
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

        function connectWS() {
            const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
            const ws = new WebSocket(`${proto}//${location.host}/ws/activity`);
            ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    renderReport(data);
                } catch (e) {}
            };
            ws.onerror = () => {
                fetchStatus();
            };
            ws.onclose = () => {
                document.getElementById('badge-status').innerText = '⚠️ WS 断开，重连中...';
                document.getElementById('badge-status').style.color = 'var(--accent-red)';
                setTimeout(connectWS, 3000);
            };
        }

        let allApps = [];
        async function loadApps() {
            try {
                const res = await fetch('/api/pc/apps');
                const data = await res.json();
                allApps = data.apps || [];
                document.getElementById('apps-count-badge').innerText = `${allApps.length} 款软件就绪`;
                filterApps();
            } catch (e) {
                document.getElementById('apps-tbody').innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--accent-red); padding: 15px;">加载失败: ${e}</td></tr>`;
            }
        }

        function escapeHtml(str) {
            return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        function filterApps() {
            const q = (document.getElementById('app-search').value || '').trim().toLowerCase();
            const cat = document.getElementById('cat-filter').value;
            const filtered = allApps.filter(a => {
                const matchQ = !q || a.exe_name.toLowerCase().includes(q) || (a.app_name || '').toLowerCase().includes(q);
                const matchCat = !cat || a.category === cat;
                return matchQ && matchCat;
            });

            const tbody = document.getElementById('apps-tbody');
            if (filtered.length === 0) {
                tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-sub); padding: 15px;">未找到匹配软件</td></tr>`;
                return;
            }

            tbody.innerHTML = filtered.map(a => `
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                    <td style="padding: 6px 10px;">
                        <div style="font-weight: 500; color: #eceff4;">${escapeHtml(a.app_name || a.exe_name)}</div>
                        <div style="font-size: 11px; color: var(--text-sub); font-family: monospace;">${escapeHtml(a.exe_name)}</div>
                    </td>
                    <td style="padding: 6px 10px; color: var(--accent);">${escapeHtml(a.subcategory || a.category)}</td>
                    <td style="padding: 6px 10px; text-align: center;">
                        <input type="checkbox" ${a.visual_safe ? 'checked' : ''} onchange="updateAppPerm('${a.exe_name}', 'visual_safe', this.checked)">
                    </td>
                    <td style="padding: 6px 10px; text-align: center;">
                        <input type="checkbox" ${a.dnd_inhibit ? 'checked' : ''} onchange="updateAppPerm('${a.exe_name}', 'dnd_inhibit', this.checked)">
                    </td>
                </tr>
            `).join('');
        }

        async function updateAppPerm(exe, field, val) {
            const toast = document.getElementById('apps-toast');
            try {
                const res = await fetch('/api/pc/apps/update', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ exe_name: exe, [field]: val })
                });
                const data = await res.json();
                if (data.status === 'ok') {
                    const item = allApps.find(x => x.exe_name === exe);
                    if (item) item[field] = val;
                    toast.style.display = 'block';
                    toast.innerText = `✓ 已更新 ${exe} 的配置 (${field}=${val})`;
                    setTimeout(() => { toast.style.display = 'none'; }, 2500);
                }
            } catch (e) {
                alert('更新失败: ' + e);
            }
        }

        fetchStatus();
        connectWS();
        loadApps();
    </script>
</body>
</html>
"""


def encode_ws_frame(payload_bytes: bytes, opcode: int = 0x1) -> bytes:
    """封装标准 RFC 6455 服务端下发帧（不加掩码）。"""
    length = len(payload_bytes)
    if length < 126:
        header = bytes([0x80 | (opcode & 0x0F), length])
    elif length <= 0xFFFF:
        header = struct.pack("!BBH", 0x80 | (opcode & 0x0F), 126, length)
    else:
        header = struct.pack("!BBQ", 0x80 | (opcode & 0x0F), 127, length)
    return header + payload_bytes


def read_ws_frame(sock: socket.socket) -> tuple[int, bytes]:
    """读取客户端上行 RFC 6455 帧（带掩码解码）。"""
    head = sock.recv(2)
    if not head or len(head) < 2:
        raise ConnectionResetError("Socket closed")
    byte1, byte2 = head[0], head[1]
    opcode = byte1 & 0x0F
    is_masked = (byte2 & 0x80) != 0
    payload_len = byte2 & 0x7F

    if payload_len == 126:
        ext = sock.recv(2)
        if len(ext) < 2:
            raise ConnectionResetError("Socket closed")
        payload_len = struct.unpack("!H", ext)[0]
    elif payload_len == 127:
        ext = sock.recv(8)
        if len(ext) < 8:
            raise ConnectionResetError("Socket closed")
        payload_len = struct.unpack("!Q", ext)[0]

    mask = b""
    if is_masked:
        mask = sock.recv(4)
        if len(mask) < 4:
            raise ConnectionResetError("Socket closed")

    data = bytearray()
    while len(data) < payload_len:
        chunk = sock.recv(min(4096, payload_len - len(data)))
        if not chunk:
            raise ConnectionResetError("Socket closed")
        data.extend(chunk)

    if is_masked:
        for i in range(len(data)):
            data[i] ^= mask[i % 4]

    return opcode, bytes(data)


class WSClient:
    """包装单客户端 WebSocket 线程安全发送与连接状态。"""

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.lock = threading.Lock()
        self.closed = False

    def send_text(self, text: str) -> None:
        if self.closed:
            return
        frame = encode_ws_frame(text.encode("utf-8"), opcode=0x1)
        with self.lock:
            self.sock.sendall(frame)

    def send_pong(self, payload: bytes) -> None:
        if self.closed:
            return
        frame = encode_ws_frame(payload, opcode=0xA)
        with self.lock:
            self.sock.sendall(frame)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            frame = encode_ws_frame(b"", opcode=0x8)
            with self.lock:
                self.sock.sendall(frame)
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


class EchoRequestHandler(BaseHTTPRequestHandler):
    def _apply_cors(self):
        origin = self.headers.get("Origin", "")
        if origin:
            # 仅允许本地与指定网段的 Origin，杜绝公网任意第三方网页跨域窥探活动
            allowed = any(kw in origin for kw in ("localhost", "127.0.0.1", "10.144.", "192.168."))
            if allowed:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, Sec-WebSocket-Key, Sec-WebSocket-Version, Upgrade")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _is_authenticated(self) -> bool:
        expected = os.environ.get("ECHO_PC_TOKEN", "").strip()
        if not expected:
            return True  # 未设置 Token 时兼容放行
        auth_header = self.headers.get("Authorization", "").strip()
        if hmac.compare_digest(auth_header, f"Bearer {expected}"):
            return True
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        token_param = qs.get("token", [""])[0]
        if token_param and hmac.compare_digest(token_param, expected):
            return True
        return False

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._apply_cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._apply_cors()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/":
            body = DASHBOARD_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._apply_cors()
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/pc/health":
            self._send_json({"status": "ok", "service": "echo-pc-agent", "version": "2.1.0", "websocket": True})
            return

        if path == "/ws/activity":
            if not self._is_authenticated():
                self._send_json({"error": "Unauthorized", "detail": "Valid Bearer token required"}, status=401)
                return

            ws_key = self.headers.get("Sec-WebSocket-Key")
            if not ws_key:
                self._send_json({"error": "Bad Request", "detail": "Missing Sec-WebSocket-Key"}, status=400)
                return

            magic = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
            accept_val = base64.b64encode(hashlib.sha1(ws_key.encode("utf-8") + magic).digest()).decode("utf-8")

            self.send_response(101, "Switching Protocols")
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", accept_val)
            self.end_headers()

            # 将底层 Socket 转交至 WSClient 管理并保活
            sock = self.connection
            sock.settimeout(2.0)
            client = WSClient(sock)
            if hasattr(self.server, "register_ws_client"):
                self.server.register_ws_client(client)

            try:
                # 握手建立成功后，即刻下发当前全量详情快照
                initial_report = tracker.get_report(level="detail")
                client.send_text(json.dumps(initial_report, ensure_ascii=False))

                # 挂起工作线程，持续监听 Ping/Pong 与断开控制帧
                while getattr(self.server, "running", True) and not client.closed:
                    try:
                        opcode, payload = read_ws_frame(sock)
                        if opcode == 0x8:  # Close
                            break
                        elif opcode == 0x9:  # Ping -> Pong
                            client.send_pong(payload)
                    except socket.timeout:
                        continue
                    except (ConnectionResetError, BrokenPipeError, OSError):
                        break
            finally:
                if hasattr(self.server, "unregister_ws_client"):
                    self.server.unregister_ws_client(client)
                client.close()
            return

        try:
            if path == "/api/pc/activity":
                if not self._is_authenticated():
                    self._send_json({"error": "Unauthorized", "detail": "Valid Bearer token required"}, status=401)
                    return
                params = urllib.parse.parse_qs(parsed.query)
                level = params.get("level", ["summary"])[0]
                report = tracker.get_report(level=level)
                self._send_json(report)
                return

            if path == "/api/pc/apps":
                if not self._is_authenticated():
                    self._send_json({"error": "Unauthorized", "detail": "Valid Bearer token required"}, status=401)
                    return
                params = urllib.parse.parse_qs(parsed.query)
                category = params.get("category", [None])[0]
                apps = registry.list_apps(category=category)
                self._send_json({"status": "ok", "total": len(apps), "apps": apps})
                return

            self._send_json({"error": "Not Found"}, status=404)
        except Exception as e:
            self._send_json({"error": "Internal Server Error", "detail": str(e)}, status=500)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/pc/privacy/toggle":
            if not self._is_authenticated():
                self._send_json({"error": "Unauthorized", "detail": "Valid Bearer token required"}, status=401)
                return
            tracker.privacy_mode = not tracker.privacy_mode
            self._send_json({"status": "ok", "privacy_mode": tracker.privacy_mode})
            return

        if path == "/api/pc/apps/update":
            if not self._is_authenticated():
                self._send_json({"error": "Unauthorized", "detail": "Valid Bearer token required"}, status=401)
                return
            length = int(self.headers.get("Content-Length", 0))
            if length == 0:
                self._send_json({"error": "Bad Request", "detail": "Missing body"}, status=400)
                return
            body_bytes = self.rfile.read(length)
            try:
                payload = json.loads(body_bytes.decode("utf-8"))
            except Exception as e:
                self._send_json({"error": "Bad Request", "detail": f"Invalid JSON: {e}"}, status=400)
                return

            exe_name = payload.get("exe_name", "").strip().lower()
            if not exe_name:
                self._send_json({"error": "Bad Request", "detail": "Missing exe_name"}, status=400)
                return

            success = registry.update_app(exe_name, payload)
            if success:
                self._send_json({"status": "ok", "app": registry.get(exe_name)})
            else:
                self._send_json({"error": "Internal Server Error", "detail": "Failed to update app"}, status=500)
            return

        self._send_json({"error": "Not Found"}, status=404)

    def log_message(self, format, *args):
        # 静默日志，避免刷屏
        pass


class AgentServer:
    def __init__(self, host: Optional[str] = None, port: Optional[int] = None):
        self.host = host or os.environ.get("ECHO_PC_HOST", "0.0.0.0")
        self.port = port or int(os.environ.get("ECHO_PC_PORT", "8766"))
        self.server: Optional[ThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.broadcaster_thread: Optional[threading.Thread] = None
        self.running = False
        self.ws_clients: set[WSClient] = set()
        self.ws_lock = threading.Lock()

    def register_ws_client(self, client: WSClient) -> None:
        with self.ws_lock:
            self.ws_clients.add(client)
        print(f"[Server] WebSocket client connected. Active clients: {len(self.ws_clients)}")

    def unregister_ws_client(self, client: WSClient) -> None:
        with self.ws_lock:
            self.ws_clients.discard(client)
        print(f"[Server] WebSocket client disconnected. Active clients: {len(self.ws_clients)}")

    def broadcast(self, data: dict) -> None:
        """向所有已连接的 WebSocket 客户端主动广播 JSON 状态帧。"""
        text = json.dumps(data, ensure_ascii=False)
        with self.ws_lock:
            clients = list(self.ws_clients)
        for client in clients:
            try:
                client.send_text(text)
            except Exception:
                with self.ws_lock:
                    self.ws_clients.discard(client)
                client.close()

    def _broadcaster_loop(self) -> None:
        """后台感知检测线程：仅在活动状态变化或心跳超时时主动向客户端推流。"""
        last_snapshot = None
        last_heartbeat = 0.0
        while self.running:
            try:
                time.sleep(1.0)
                with self.ws_lock:
                    has_clients = bool(self.ws_clients)
                if not has_clients:
                    continue

                report = tracker.get_report(level="detail")
                snapshot = (
                    report.get("app"),
                    report.get("category"),
                    report.get("window_title"),
                    report.get("is_locked"),
                    report.get("privacy_mode"),
                    report.get("duration_minutes"),
                    (report.get("idle_seconds", 0) // 60),
                )
                now = time.time()
                if snapshot != last_snapshot or (now - last_heartbeat >= 60.0):
                    last_snapshot = snapshot
                    last_heartbeat = now
                    self.broadcast(report)
            except Exception as exc:
                print(f"[Server] Broadcaster error: {exc}")

    def start(self):
        self.running = True
        self.server = ThreadingHTTPServer((self.host, self.port), EchoRequestHandler)
        self.server.running = True
        self.server.register_ws_client = self.register_ws_client
        self.server.unregister_ws_client = self.unregister_ws_client
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

        self.broadcaster_thread = threading.Thread(target=self._broadcaster_loop, daemon=True)
        self.broadcaster_thread.start()
        print(f"[Server] Echo PC Agent running on http://{self.host}:{self.port} (WebSocket /ws/activity enabled)")

    def stop(self):
        self.running = False
        if self.server:
            self.server.running = False
        with self.ws_lock:
            for c in list(self.ws_clients):
                c.close()
            self.ws_clients.clear()
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            print("[Server] Echo PC Agent HTTP Server stopped.")
