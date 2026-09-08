import ctypes
from ctypes import wintypes
import os
import re
import time
from collections import deque
from typing import Dict, Any, Optional

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("dwTime", wintypes.DWORD),
    ]

# Level 1 专属应用直接映射表
PROCESS_MAP = {
    "code.exe": {"category": "coding", "sub": "vscode", "app_name": "Visual Studio Code", "visual_safe": True},
    "cursor.exe": {"category": "coding", "sub": "cursor", "app_name": "Cursor", "visual_safe": True},
    "antigravity.exe": {"category": "coding", "sub": "antigravity", "app_name": "Antigravity", "visual_safe": True},
    "idea64.exe": {"category": "coding", "sub": "intellij", "app_name": "IntelliJ IDEA", "visual_safe": True},
    "pycharm64.exe": {"category": "coding", "sub": "pycharm", "app_name": "PyCharm", "visual_safe": True},
    "windowsterminal.exe": {"category": "coding", "sub": "terminal", "app_name": "Windows Terminal", "visual_safe": True},
    "zotero.exe": {"category": "research", "sub": "zotero", "app_name": "Zotero", "visual_safe": True},
    "acrord32.exe": {"category": "research", "sub": "acrobat", "app_name": "Adobe Acrobat", "visual_safe": True},
    "cajviewer.exe": {"category": "research", "sub": "cajviewer", "app_name": "CAJViewer", "visual_safe": True},
    "obsidian.exe": {"category": "writing", "sub": "obsidian", "app_name": "Obsidian", "visual_safe": True},
    "typora.exe": {"category": "writing", "sub": "typora", "app_name": "Typora", "visual_safe": True},
    "winword.exe": {"category": "writing", "sub": "word", "app_name": "Microsoft Word", "visual_safe": True},
    "steam.exe": {"category": "gaming", "sub": "steam", "app_name": "Steam", "visual_safe": True},
    "endfield.exe": {"category": "gaming", "sub": "endfield", "app_name": "明日方舟：终末地", "visual_safe": True},
    "genshinimpact.exe": {"category": "gaming", "sub": "genshin", "app_name": "原神", "visual_safe": True},
    "yuanshen.exe": {"category": "gaming", "sub": "genshin", "app_name": "原神", "visual_safe": True},
    "starrail.exe": {"category": "gaming", "sub": "starrail", "app_name": "崩坏：星穹铁道", "visual_safe": True},
    "zenlesszonezero.exe": {"category": "gaming", "sub": "zzz", "app_name": "绝区零", "visual_safe": True},
    "wutheringwaves.exe": {"category": "gaming", "sub": "wuthering", "app_name": "鸣潮", "visual_safe": True},
    "cs2.exe": {"category": "gaming", "sub": "cs2", "app_name": "Counter-Strike 2", "visual_safe": True},
    "dota2.exe": {"category": "gaming", "sub": "dota2", "app_name": "Dota 2", "visual_safe": True},
    "potplayer64.exe": {"category": "video_leisure", "sub": "local_video", "app_name": "PotPlayer", "visual_safe": False},
    "vlc.exe": {"category": "video_leisure", "sub": "local_video", "app_name": "VLC", "visual_safe": False},
    "wechat.exe": {"category": "chatting", "sub": "wechat", "app_name": "微信", "visual_safe": False},
    "qq.exe": {"category": "chatting", "sub": "qq", "app_name": "QQ", "visual_safe": False},
    "telegram.exe": {"category": "chatting", "sub": "telegram", "app_name": "Telegram", "visual_safe": False},
    "discord.exe": {"category": "chatting", "sub": "discord", "app_name": "Discord", "visual_safe": False},
}

# 浏览器多标签页标题特征正则
BROWSER_RULES = [
    {"pattern": r"(arXiv|Overleaf|IEEE|PapersWithCode|OpenReview|ScienceDirect|Springer)", "category": "research", "sub": "paper_reading", "visual_safe": True},
    {"pattern": r"(GitHub|GitLab|Stack Overflow|LeetCode|docs\.|developer\.|CS231|PyTorch)", "category": "coding", "sub": "dev_docs", "visual_safe": True},
    {"pattern": r"(教程|公开课|算法讲解|论文研读|架构解析|教学|课程)", "category": "video_learning", "sub": "course", "visual_safe": True},
    {"pattern": r"(哔哩哔哩|bilibili|YouTube|爱奇艺|Netflix|动漫|番剧|游戏解说|新番)", "category": "video_leisure", "sub": "video_stream", "visual_safe": False},
]

class ActivityTracker:
    def __init__(self, history_len: int = 60):
        self.history_len = history_len
        self.history = deque(maxlen=history_len)
        self.current_session_start = time.time()
        self.current_app = ""
        self.privacy_mode = False

    def _ensure_desktop(self):
        try:
            hdesk = user32.OpenDesktopW("default", 0, False, 0x01FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)
                user32.CloseDesktop(hdesk)
        except Exception:
            pass

    def get_system_idle_seconds(self) -> int:
        self._ensure_desktop()
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if user32.GetLastInputInfo(ctypes.byref(lii)):
            millis = kernel32.GetTickCount() - lii.dwTime
            return max(0, int(millis / 1000))
        return 0

    def get_raw_foreground_window(self) -> Dict[str, Any]:
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
        if proc in ["lockapp.exe", "logonui.exe"] or idle_sec >= 600:
            return {
                "category": "idle_away",
                "subcategory": "locked" if proc in ["lockapp.exe", "logonui.exe"] else "away",
                "app_name": "系统锁屏",
                "summary": "离开电脑小憩中",
                "visual_safe": False,
                "is_locked": proc in ["lockapp.exe", "logonui.exe"],
                "idle_seconds": idle_sec,
            }

        title_lower = title.lower()
        if any(kw in title_lower for kw in ["inprivate", "incognito", "无痕", "隐私浏览", "密码", "网银", "login - "]):
            return {
                "category": "private_safe",
                "subcategory": "private",
                "app_name": "私密事务",
                "summary": "正在处理私密事务",
                "visual_safe": False,
                "is_locked": False,
                "idle_seconds": idle_sec,
            }

        if proc in PROCESS_MAP:
            m = PROCESS_MAP[proc]
            category = m["category"]
            sub = m["sub"]
            app_name = m["app_name"]
            visual_safe = m["visual_safe"]
            
            detail_tag = ""
            if category == "coding" and " - " in title:
                parts = title.split(" - ")
                if parts:
                    detail_tag = f" ({parts[0].strip()})"
            elif category == "research" and " - " in title:
                parts = title.split(" - ")
                if parts:
                    detail_tag = f" ({parts[0].strip()[:25]})"

            summary = f"正在用 {app_name}{detail_tag}"
            if category == "coding":
                summary += " 编写调试代码"
            elif category == "research":
                summary += " 研读学术资料"
            elif category == "writing":
                summary += " 整理笔记手帐"
            elif category == "gaming":
                summary = f"正在玩 {app_name} 放松"

            return {
                "category": category,
                "subcategory": sub,
                "app_name": app_name,
                "summary": summary,
                "visual_safe": visual_safe,
                "is_locked": False,
                "idle_seconds": idle_sec,
            }

        if proc in ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe"]:
            for r in BROWSER_RULES:
                if re.search(r["pattern"], title, re.IGNORECASE):
                    cat = r["category"]
                    clean_title = title.split(" - ")[0].strip()
                    if cat == "research":
                        summ = f"正在阅读论文/文献: {clean_title[:30]}"
                    elif cat == "coding":
                        summ = f"正在查阅开发文档: {clean_title[:30]}"
                    elif cat == "video_learning":
                        summ = f"正在观看学习视频: {clean_title[:30]}"
                    else:
                        summ = f"正在观看下饭视频: {clean_title[:30]}"

                    return {
                        "category": cat,
                        "subcategory": r["sub"],
                        "app_name": "网页浏览器",
                        "summary": summ,
                        "visual_safe": r["visual_safe"],
                        "is_locked": False,
                        "idle_seconds": idle_sec,
                    }

            return {
                "category": "browsing",
                "subcategory": "web",
                "app_name": "网页浏览器",
                "summary": "正在浏览网页",
                "visual_safe": False,
                "is_locked": False,
                "idle_seconds": idle_sec,
            }

        clean_proc = proc.replace(".exe", "")
        return {
            "category": "other",
            "subcategory": "general",
            "app_name": clean_proc,
            "summary": f"前台正在使用 {clean_proc}",
            "visual_safe": False,
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

        self.history.append({
            "timestamp": now,
            "category": res["category"],
            "app": res["app_name"],
        })

        return res

    def get_macro_summary(self) -> Dict[str, Any]:
        if not self.history:
            return {"theme": "balanced", "dominant_category": "unknown", "breakdown": {}}

        counts = {}
        for h in self.history:
            c = h["category"]
            counts[c] = counts.get(c, 0) + 1
        
        total = len(self.history)
        breakdown = {k: round((v / total) * 100) for k, v in counts.items()}
        dominant = max(counts, key=counts.get)
        
        if "coding" in counts and ("video_leisure" in counts or "gaming" in counts):
            theme = "coding_with_chilling_wait"
        elif dominant in ["video_leisure", "gaming"]:
            theme = "cozy_watch_party"
        elif dominant in ["coding", "research"]:
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
                "app": curr["app_name"],
                "summary": curr["summary"],
                "duration_minutes": curr["duration_minutes"],
                "idle_seconds": curr["idle_seconds"],
                "is_locked": curr["is_locked"],
                "privacy_mode": self.privacy_mode,
            }

        elif level == "detail":
            return {
                "status": "online",
                "category": curr["category"],
                "subcategory": curr["subcategory"],
                "app": curr["app_name"],
                "window_title": curr["window_title"],
                "summary": curr["summary"],
                "duration_minutes": curr["duration_minutes"],
                "idle_seconds": curr["idle_seconds"],
                "is_locked": curr["is_locked"],
                "visual_safe": curr["visual_safe"],
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
