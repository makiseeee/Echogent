import ctypes
import os
import re
import time
from collections import deque
from typing import Dict, Any, Optional

from .app_registry import registry

try:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    from ctypes import wintypes
except (AttributeError, Exception):
    user32 = None
    kernel32 = None
    wintypes = None

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

if wintypes:
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.UINT),
            ("dwTime", wintypes.DWORD),
        ]
else:
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_uint),
            ("dwTime", ctypes.c_ulong),
        ]

# 浏览器多标签页标题特征正则
BROWSER_RULES = [
    {"pattern": r"(arXiv|Overleaf|IEEE|PapersWithCode|OpenReview|ScienceDirect|Springer)", "category": "research_simulation", "sub": "paper_reading", "visual_safe": True, "dnd_inhibit": False},
    {"pattern": r"(GitHub|GitLab|Stack Overflow|LeetCode|docs\.|developer\.|CS231|PyTorch)", "category": "coding", "sub": "dev_docs", "visual_safe": True, "dnd_inhibit": False},
    {"pattern": r"(教程|公开课|算法讲解|论文研读|架构解析|教学|课程)", "category": "research_simulation", "sub": "course_learning", "visual_safe": True, "dnd_inhibit": False},
    {"pattern": r"(哔哩哔哩|bilibili|YouTube|爱奇艺|Netflix|动漫|番剧|游戏解说|新番)", "category": "video_leisure", "sub": "video_stream", "visual_safe": False, "dnd_inhibit": False},
]

class ActivityTracker:
    def __init__(self, history_len: int = 60):
        self.history_len = history_len
        self.history = deque(maxlen=history_len)
        self.current_session_start = time.time()
        self.current_app = ""
        self.privacy_mode = False

    def _ensure_desktop(self):
        if not user32:
            return
        try:
            hdesk = user32.OpenDesktopW("default", 0, False, 0x01FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)
                user32.CloseDesktop(hdesk)
        except Exception:
            pass

    def get_system_idle_seconds(self) -> int:
        if not user32 or not kernel32:
            return 0
        self._ensure_desktop()
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if user32.GetLastInputInfo(ctypes.byref(lii)):
            millis = kernel32.GetTickCount() - lii.dwTime
            return max(0, int(millis / 1000))
        return 0

    def get_raw_foreground_window(self) -> Dict[str, Any]:
        if not user32 or not kernel32:
            return {"hwnd": 0, "title": "", "process_name": "unknown", "pid": 0}
        self._ensure_desktop()
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return {"hwnd": 0, "title": "", "process_name": "unknown", "pid": 0}

        length = user32.GetWindowTextLengthW(hwnd)
        title_buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buf, length + 1)
        title = title_buf.value

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        
        proc_name = "unknown"
        h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if h_proc:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
                proc_name = os.path.basename(buf.value)
            kernel32.CloseHandle(h_proc)

        return {
            "hwnd": hwnd,
            "title": title,
            "process_name": proc_name.lower(),
            "pid": pid.value,
        }

    def sanitize_title(self, title: str) -> str:
        title = re.sub(r"[A-Za-z]:\\[Uu]sers\\[^\\]+\\", r"~\\", title)
        title = re.sub(r"(token|key|secret|password)[=:]\s*[A-Za-z0-9_\-]{8,}", r"\1=***", title, flags=re.I)
        return title.strip()

    def classify(self, proc: str, title: str, idle_sec: int) -> Dict[str, Any]:
        # 1. 锁屏与长闲置
        if proc in ["lockapp.exe", "logonui.exe"] or idle_sec >= 600:
            return {
                "category": "idle_away",
                "subcategory": "locked" if proc in ["lockapp.exe", "logonui.exe"] else "away",
                "app_name": "系统锁屏",
                "summary": "离开电脑小憩中",
                "visual_safe": False,
                "dnd_inhibit": False,
                "is_locked": proc in ["lockapp.exe", "logonui.exe"],
                "idle_seconds": idle_sec,
            }

        # 2. 隐私与无痕特征
        title_lower = title.lower()
        if any(kw in title_lower for kw in ["inprivate", "incognito", "无痕", "隐私浏览", "密码", "网银", "login - "]):
            return {
                "category": "private_safe",
                "subcategory": "private",
                "app_name": "私密事务",
                "summary": "正在处理私密事务",
                "visual_safe": False,
                "dnd_inhibit": False,
                "is_locked": False,
                "idle_seconds": idle_sec,
            }

        # 3. 浏览器动态多标签页标题匹配
        if proc in ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe"]:
            for r in BROWSER_RULES:
                if re.search(r["pattern"], title, re.IGNORECASE):
                    cat = r["category"]
                    clean_title = title.split(" - ")[0].strip()
                    if cat == "research_simulation":
                        summ = f"正在阅读论文文献: {clean_title[:30]}"
                    elif cat == "coding":
                        summ = f"正在查阅开发文档: {clean_title[:30]}"
                    else:
                        summ = f"正在观看下饭视频: {clean_title[:30]}"

                    return {
                        "category": cat,
                        "subcategory": r["sub"],
                        "app_name": "网页浏览器",
                        "summary": summ,
                        "visual_safe": r["visual_safe"],
                        "dnd_inhibit": r["dnd_inhibit"],
                        "is_locked": False,
                        "idle_seconds": idle_sec,
                    }

            return {
                "category": "productivity_system",
                "subcategory": "web_browsers",
                "app_name": "网页浏览器",
                "summary": "正在浏览网页",
                "visual_safe": True,
                "dnd_inhibit": False,
                "is_locked": False,
                "idle_seconds": idle_sec,
            }

        # 4. 查询 AppRegistry 数据库与预设
        app_info = registry.get(proc)
        if app_info:
            category = app_info["category"]
            subcategory = app_info["subcategory"]
            app_name = app_info["app_name"]
            visual_safe = app_info["visual_safe"]
            dnd_inhibit = app_info["dnd_inhibit"]

            # 提取标题中的关键工程/文档名
            detail_tag = ""
            if " - " in title:
                parts = title.split(" - ")
                if parts and len(parts[0].strip()) > 0:
                    detail_tag = f" ({parts[0].strip()[:30]})"

            # 智能生成自然摘要
            summary = app_info.get("custom_summary", "")
            if not summary:
                if category == "coding":
                    summary = f"正在用 {app_name}{detail_tag} 编写调试代码"
                elif category == "hardware_embedded":
                    summary = f"正在用 {app_name}{detail_tag} 进行单片机与电路设计"
                elif category == "research_simulation":
                    summary = f"正在用 {app_name}{detail_tag} 开展科学计算与论文研读"
                elif category == "creative_design":
                    summary = f"正在用 {app_name}{detail_tag} 制作数字音影创作"
                elif category == "gaming":
                    summary = f"正在玩 {app_name} 放松"
                elif category == "communication_meeting":
                    summary = f"正在使用 {app_name} 沟通或开会"
                else:
                    summary = f"前台正在使用 {app_name}{detail_tag}"

            return {
                "category": category,
                "subcategory": subcategory,
                "app_name": app_name,
                "summary": summary,
                "visual_safe": visual_safe,
                "dnd_inhibit": dnd_inhibit,
                "is_locked": False,
                "idle_seconds": idle_sec,
            }

        # 5. 未收录的外部新进程：动态注册为 unseen 并返回
        clean_proc = proc.replace(".exe", "")
        registry.register_unseen(proc, title)
        return {
            "category": "other",
            "subcategory": "unseen",
            "app_name": clean_proc,
            "summary": f"前台正在使用 {clean_proc}",
            "visual_safe": True,
            "dnd_inhibit": False,
            "is_locked": False,
            "idle_seconds": idle_sec,
        }

    def poll_activity(self) -> Dict[str, Any]:
        if self.privacy_mode:
            return {
                "category": "private_safe",
                "subcategory": "user_paused",
                "app_name": "隐私模式",
                "summary": "文博已主动开启隐私保护模式",
                "visual_safe": False,
                "dnd_inhibit": False,
                "is_locked": False,
                "idle_seconds": 0,
                "duration_minutes": 0,
                "duration_seconds": 0,
                "window_title": "隐私保护中",
                "process_name": "privacy_shield",
                "hwnd": 0,
            }

        raw = self.get_raw_foreground_window()
        idle = self.get_system_idle_seconds()
        sanitized_title = self.sanitize_title(raw["title"])
        res = self.classify(raw["process_name"], sanitized_title, idle)
        
        now = time.time()
        current_identity = f"{res['category']}:{res['app_name']}"
        if current_identity != self.current_app:
            self.current_app = current_identity
            self.current_session_start = now

        duration_sec = int(now - self.current_session_start)
        res["duration_seconds"] = duration_sec
        res["duration_minutes"] = max(1, duration_sec // 60)
        res["window_title"] = sanitized_title
        res["process_name"] = raw["process_name"]
        res["hwnd"] = raw["hwnd"]

        # 滑动窗口历史记录
        self.history.append({
            "timestamp": now,
            "category": res["category"],
            "subcategory": res.get("subcategory", "general"),
            "app": res["app_name"],
        })

        return res

    def get_macro_summary(self) -> Dict[str, Any]:
        if not self.history:
            return {
                "theme": "idle_dormant",
                "dominant_category": "other",
                "breakdown": {}
            }

        counts = {}
        for item in self.history:
            c = item["category"]
            counts[c] = counts.get(c, 0) + 1

        total = len(self.history)
        breakdown = {k: round((v / total) * 100) for k, v in counts.items()}
        dominant = max(counts, key=counts.get)
        
        if "coding" in counts and ("video_leisure" in counts or "gaming" in counts):
            theme = "coding_with_chilling_wait"
        elif dominant in ["video_leisure", "gaming"]:
            theme = "cozy_watch_party"
        elif dominant in ["coding", "hardware_embedded", "research_simulation"]:
            theme = "deep_focus_work"
        else:
            theme = "general_companion"

        return {
            "theme": theme,
            "dominant_category": dominant,
            "breakdown": breakdown,
        }

    def get_report(self, level: str = "summary") -> Dict[str, Any]:
        curr = self.poll_activity()
        macro = self.get_macro_summary()

        if level == "summary":
            return {
                "status": "online",
                "category": curr["category"],
                "subcategory": curr.get("subcategory", "general"),
                "app": curr["app_name"],
                "summary": curr["summary"],
                "duration_minutes": curr["duration_minutes"],
                "idle_seconds": curr["idle_seconds"],
                "is_locked": curr["is_locked"],
                "dnd_inhibit": curr.get("dnd_inhibit", False),
                "privacy_mode": self.privacy_mode,
            }

        elif level == "detail":
            return {
                "status": "online",
                "category": curr["category"],
                "subcategory": curr.get("subcategory", "general"),
                "app": curr["app_name"],
                "process_name": curr["process_name"],
                "window_title": curr["window_title"],
                "summary": curr["summary"],
                "duration_minutes": curr["duration_minutes"],
                "duration_seconds": curr["duration_seconds"],
                "idle_seconds": curr["idle_seconds"],
                "is_locked": curr["is_locked"],
                "visual_safe": curr["visual_safe"],
                "dnd_inhibit": curr.get("dnd_inhibit", False),
                "privacy_mode": self.privacy_mode,
                "macro_session": macro,
            }

        elif level == "visual":
            if not curr["visual_safe"] or self.privacy_mode:
                return {
                    "status": "online",
                    "visual_safe": False,
                    "message": "当前前台窗口处于隐私保护状态，已阻断视觉采集",
                    "category": curr["category"],
                    "app": curr["app_name"],
                }
            
            return {
                "status": "online",
                "visual_safe": True,
                "category": curr["category"],
                "app": curr["app_name"],
                "window_title": curr["window_title"],
                "message": "视觉采集已授权 (允许局部客户区 OCR/截屏)",
            }

        return {"error": f"Unknown level: {level}"}

tracker = ActivityTracker()
