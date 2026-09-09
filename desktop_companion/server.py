#!/usr/bin/env python3
"""Echo Companion HUD HTTP Server & Task API.

Provides:
- Static file serving for ~/echo_companion (dashboard.html, assets, live2d, etc.)
- POST /api/task/toggle: Toggles daily task in Obsidian vault via Echo's DailyTaskManager
- GET /api/tasks: Returns current task state and regenerates tasks.json
- GET /api/health: Health check endpoint
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
LOG = logging.getLogger("echo-hud-server")

WEB_DIR = Path(__file__).resolve().parent
SILENCE_STATE_FILE = WEB_DIR / "silence_state.json"
TOOLS_DIR = Path("/data/data/com.termux/files/usr/var/lib/proot-distro/containers/ubuntu/rootfs/opt/echo/data/plugins/echo-tools")
VAULT_DIR = Path("/data/data/com.termux/files/usr/var/lib/proot-distro/containers/ubuntu/rootfs/root/obsidiangit")

# Lazy-loaded tool handles
_task_mgr = None
_git_sync = None


def get_daily_manager():
    global _task_mgr, _git_sync
    if _task_mgr is not None:
        return _task_mgr

    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))

    try:
        from daily_task_manager import DailyTaskManager
        from obsidian_git import VaultGitSync

        _git_sync = VaultGitSync(VAULT_DIR)
        _task_mgr = DailyTaskManager(_git_sync)
        LOG.info("DailyTaskManager initialized with vault: %s", VAULT_DIR)
        return _task_mgr
    except Exception as exc:
        LOG.exception("Failed to initialize DailyTaskManager: %s", exc)
        return None


def export_tasks_json() -> dict:
    """Read daily note tasks and export tasks.json for frontend consumption."""
    mgr = get_daily_manager()
    if mgr is None:
        return {"error": "DailyTaskManager unavailable"}

    today = mgr._today(None)
    daily_text = mgr._daily_text(today)
    tasks = mgr._managed_tasks(daily_text)

    total = len(tasks)
    done_count = sum(1 for t in tasks if t.completed)
    pct = round(done_count / total * 100) if total > 0 else 0

    task_list = [
        {"id": t.id, "name": t.name, "done": t.completed}
        for t in tasks
    ]

    data = {
        "date": today.isoformat(),
        "total": total,
        "done": done_count,
        "percent": pct,
        "focus": task_list,
    }

    out_file = WEB_DIR / "tasks.json"
    try:
        out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        LOG.warning("Failed to write tasks.json: %s", exc)

    return data


def toggle_daily_task(keyword: str, completed: bool) -> tuple[bool, dict]:
    """Toggle a task in Obsidian vault, committing and pushing in background."""
    mgr = get_daily_manager()
    if mgr is None:
        raise RuntimeError("DailyTaskManager not available")

    res = mgr.toggle_daily_task(keyword, completed=completed)
    changed = res.get("changed", False) if isinstance(res, dict) else bool(res)
    data = export_tasks_json()
    return changed, data


def get_silence_state() -> dict:
    if SILENCE_STATE_FILE.exists():
        try:
            return json.loads(SILENCE_STATE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            LOG.warning("Failed to read silence_state.json: %s", e)
    return {"silenced": False, "mode": "active", "updated_at": 0}


def set_silence_state(silenced: bool, screen_dim: bool = True, manual: bool = False) -> dict:
    now_ts = int(time.time())
    state = {
        "silenced": bool(silenced),
        "mode": "silence" if silenced else "active",
        "screen_dim": bool(screen_dim),
        "manual": bool(manual),
        "updated_at": now_ts,
    }
    if manual:
        state["manual_at"] = now_ts
    try:
        tmp = str(SILENCE_STATE_FILE) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, str(SILENCE_STATE_FILE))
    except Exception as exc:
        LOG.warning("Failed to write silence_state.json: %s", exc)

    if screen_dim:
        try:
            cfg_path = Path("/data/data/com.termux/files/home/.echo/brightness_config.json")
            active_val = 190
            if cfg_path.exists():
                try:
                    active_val = int(json.loads(cfg_path.read_text(encoding="utf-8")).get("active_brightness", 190))
                except Exception:
                    pass
            val = "0" if silenced else str(active_val)
            subprocess.run(["termux-brightness", val], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    return state


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


_latest_bubble = {
    "text": "",
    "motion": 0,
    "timestamp": 0.0,
}


class CompanionRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def _send_json(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        url_path = self.path.split("?")[0]
        if url_path == "/api/health":
            self._send_json(200, {"status": "ok", "service": "echo-hud-server"})
            return

        if url_path == "/api/tasks":
            try:
                data = export_tasks_json()
                self._send_json(200, {"success": True, **data})
            except Exception as exc:
                LOG.exception("GET /api/tasks error: %s", exc)
                self._send_json(500, {"success": False, "error": str(exc)})
            return

        if url_path == "/api/silence":
            try:
                state = get_silence_state()
                self._send_json(200, {"success": True, **state})
            except Exception as exc:
                LOG.exception("GET /api/silence error: %s", exc)
                self._send_json(500, {"success": False, "error": str(exc)})
            return

        if url_path == "/api/brightness":
            try:
                cfg_path = Path("/data/data/com.termux/files/home/.echo/brightness_config.json")
                val = 140
                if cfg_path.exists():
                    val = int(json.loads(cfg_path.read_text(encoding="utf-8")).get("active_brightness", 140))
                self._send_json(200, {"success": True, "active_brightness": val})
            except Exception as exc:
                self._send_json(500, {"success": False, "error": str(exc)})
            return

        if url_path == "/api/chat/bubble":
            self._send_json(200, {"success": True, **_latest_bubble})
            return

        super().do_GET()

    def do_POST(self):
        url_path = self.path.split("?")[0]
        if url_path == "/api/chat/bubble":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
                payload = json.loads(raw_body)
                text = str(payload.get("text", "")).strip()
                motion = int(payload.get("motion", 2))
                if text:
                    _latest_bubble["text"] = text
                    _latest_bubble["motion"] = motion
                    _latest_bubble["timestamp"] = time.time()
                    LOG.info("Pushed speech bubble to Live2D screen: %s", text[:40])
                self._send_json(200, {"success": True, **_latest_bubble})
            except Exception as exc:
                LOG.exception("POST /api/chat/bubble error: %s", exc)
                self._send_json(500, {"success": False, "error": str(exc)})
            return
        if url_path == "/api/silence/toggle":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else ""
                payload = json.loads(raw_body) if raw_body else {}

                current = get_silence_state()
                target_silence = payload.get("silenced")
                if target_silence is None:
                    new_val = not current.get("silenced", False)
                else:
                    new_val = bool(target_silence)

                screen_dim = bool(payload.get("screen_dim", True))
                manual = bool(payload.get("manual", False))
                updated = set_silence_state(new_val, screen_dim=screen_dim, manual=manual)
                LOG.info("Toggled silence state: silenced=%s, screen_dim=%s, manual=%s", updated["silenced"], screen_dim, manual)
                self._send_json(200, {"success": True, **updated})
            except Exception as exc:
                LOG.exception("POST /api/silence/toggle error: %s", exc)
                self._send_json(500, {"success": False, "error": str(exc)})
            return

        if url_path == "/api/brightness":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
                payload = json.loads(raw_body)
                new_val = int(payload.get("brightness", 190))
                new_val = max(10, min(255, new_val))
                cfg_path = Path("/data/data/com.termux/files/home/.echo/brightness_config.json")
                cfg = {"active_brightness": new_val, "sleep_brightness": 0}
                cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
                if not get_silence_state().get("silenced", False):
                    subprocess.run(["termux-brightness", str(new_val)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                LOG.info("Updated active brightness to %d", new_val)
                self._send_json(200, {"success": True, "active_brightness": new_val})
            except Exception as exc:
                self._send_json(500, {"success": False, "error": str(exc)})
            return

        if url_path == "/api/task/toggle":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(content_length).decode("utf-8")
                payload = json.loads(raw_body) if raw_body else {}

                name = payload.get("name", "").strip()
                task_id = payload.get("id", "").strip()
                keyword = task_id or name
                done = bool(payload.get("done", True))

                if not keyword:
                    self._send_json(400, {"success": False, "error": "Missing task name or id"})
                    return

                LOG.info("Toggling task '%s' (done=%s)", keyword, done)
                changed, data = toggle_daily_task(keyword, done)
                self._send_json(200, {
                    "success": True,
                    "changed": changed,
                    "task": {"name": name, "id": task_id, "done": done},
                    **data,
                })
            except Exception as exc:
                LOG.exception("POST /api/task/toggle error: %s", exc)
                self._send_json(500, {"success": False, "error": str(exc)})
            return

        self._send_json(404, {"error": f"Endpoint not found: {self.path}"})


def run_server(port: int = 8099):
    # Ensure tasks.json is fresh on startup
    try:
        export_tasks_json()
    except Exception as e:
        LOG.warning("Initial export of tasks.json failed: %s", e)

    server_address = ("0.0.0.0", port)
    httpd = ThreadedHTTPServer(server_address, CompanionRequestHandler)
    LOG.info("Echo Companion HUD Server listening on http://0.0.0.0:%d", port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        LOG.info("Shutting down HUD server...")
        httpd.shutdown()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8099
    run_server(port)
