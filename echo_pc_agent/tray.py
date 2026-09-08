import ctypes
from ctypes import wintypes
import webbrowser
import threading
import winreg
import os
import sys

from modules.activity import tracker

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32

LRESULT = ctypes.c_ssize_t
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL

WM_USER = 0x0400
WM_TRAYICON = WM_USER + 20
WM_COMMAND = 0x0111
WM_DESTROY = 0x0002
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205

NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002

MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
MF_CHECKED = 0x00000008
MF_UNCHECKED = 0x00000000
MF_GRAYED = 0x00000001

TPM_RIGHTBUTTON = 0x0002
TPM_LEFTALIGN = 0x0000

IDI_APPLICATION = 32512

# 菜单 ID
ID_STATUS = 1001
ID_PRIVACY = 1002
ID_DASHBOARD = 1003
ID_AUTOSTART = 1004
ID_EXIT = 1005

REG_RUN_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "EchoPCAgent"

class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
    ]

WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]

class TrayApp:
    def __init__(self, on_exit_callback=None):
        self.hwnd = None
        self.nid = None
        self.on_exit_callback = on_exit_callback
        self.is_running = True
        self.wnd_proc_ref = WNDPROC(self._wnd_proc)

    def is_autostart_enabled(self) -> bool:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_PATH, 0, winreg.KEY_READ) as key:
                winreg.QueryValueEx(key, APP_NAME)
                return True
        except FileNotFoundError:
            return False

    def toggle_autostart(self):
        enabled = self.is_autostart_enabled()
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_PATH, 0, winreg.KEY_SET_VALUE) as key:
                if enabled:
                    winreg.DeleteValue(key, APP_NAME)
                else:
                    # 注册 run.vbs
                    agent_dir = os.path.dirname(os.path.abspath(__file__))
                    vbs_path = os.path.join(agent_dir, "run.vbs")
                    cmd = f'wscript.exe "{vbs_path}"'
                    winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
        except Exception as e:
            print("[Tray] Autostart toggle error:", e)

    def _show_menu(self):
        hMenu = user32.CreatePopupMenu()
        
        # 1. 当前活动预览
        curr = tracker.poll_activity()
        status_text = f"📌 当前: {curr['app_name']} ({curr['category']})"
        user32.AppendMenuW(hMenu, MF_STRING | MF_GRAYED, ID_STATUS, status_text)
        user32.AppendMenuW(hMenu, MF_SEPARATOR, 0, None)

        # 2. 隐私模式切换
        priv_flags = MF_CHECKED if tracker.privacy_mode else MF_UNCHECKED
        priv_text = "🛡️ 隐私保护模式 (已开启)" if tracker.privacy_mode else "🛡️ 隐私保护模式 (已关闭)"
        user32.AppendMenuW(hMenu, MF_STRING | priv_flags, ID_PRIVACY, priv_text)

        # 3. 监控看板
        user32.AppendMenuW(hMenu, MF_STRING, ID_DASHBOARD, "🌐 打开控制中心看板...")

        # 4. 开机自启
        auto_flags = MF_CHECKED if self.is_autostart_enabled() else MF_UNCHECKED
        auto_text = "⚙️ 开机自动启动 (已启用)" if self.is_autostart_enabled() else "⚙️ 开机自动启动 (未启用)"
        user32.AppendMenuW(hMenu, MF_STRING | auto_flags, ID_AUTOSTART, auto_text)

        user32.AppendMenuW(hMenu, MF_SEPARATOR, 0, None)
        # 5. 退出
        user32.AppendMenuW(hMenu, MF_STRING, ID_EXIT, "❌ 退出 Echo PC Agent")

        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self.hwnd)
        user32.TrackPopupMenuEx(hMenu, TPM_RIGHTBUTTON | TPM_LEFTALIGN, pt.x, pt.y, self.hwnd, None)
        user32.DestroyMenu(hMenu)

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAYICON:
            if lparam == WM_RBUTTONUP:
                self._show_menu()
                return 0
            elif lparam == WM_LBUTTONDBLCLK:
                webbrowser.open("http://127.0.0.1:8766/")
                return 0

        elif msg == WM_COMMAND:
            cmd_id = wparam & 0xFFFF
            if cmd_id == ID_PRIVACY:
                tracker.privacy_mode = not tracker.privacy_mode
            elif cmd_id == ID_DASHBOARD:
                webbrowser.open("http://127.0.0.1:8766/")
            elif cmd_id == ID_AUTOSTART:
                self.toggle_autostart()
            elif cmd_id == ID_EXIT:
                self.stop()
            return 0

        elif msg == WM_DESTROY:
            self._cleanup()
            user32.PostQuitMessage(0)
            return 0

        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _cleanup(self):
        if self.nid:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.nid))
            self.nid = None

    def run(self):
        hInst = kernel32.GetModuleHandleW(None)
        cls_name = "EchoPCAgentTrayClass"

        wc = WNDCLASSW()
        wc.style = 0
        wc.lpfnWndProc = self.wnd_proc_ref
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = hInst
        wc.hIcon = user32.LoadIconW(None, IDI_APPLICATION)
        wc.hCursor = None
        wc.hbrBackground = None
        wc.lpszMenuName = None
        wc.lpszClassName = cls_name

        user32.RegisterClassW(ctypes.byref(wc))

        self.hwnd = user32.CreateWindowExW(
            0, cls_name, "Echo PC Agent Tray Window",
            0, 0, 0, 0, 0,
            None, None, hInst, None
        )

        hIcon = user32.LoadIconW(None, IDI_APPLICATION)
        self.nid = NOTIFYICONDATAW()
        self.nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        self.nid.hWnd = self.hwnd
        self.nid.uID = 1
        self.nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP
        self.nid.uCallbackMessage = WM_TRAYICON
        self.nid.hIcon = hIcon
        self.nid.szTip = "Echo PC Agent · 智能桌面感知中"

        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self.nid))
        print("[Tray] Windows System Tray Icon created successfully.")

        # 启动后台心跳更新 Tooltip 线程
        def update_tooltip_loop():
            while self.is_running:
                try:
                    curr = tracker.poll_activity()
                    tip = f"Echo PC Agent: {curr['app_name']} ({curr['category']})"
                    if len(tip) >= 64:
                        tip = tip[:63]
                    self.nid.szTip = tip
                    self.nid.uFlags = NIF_TIP
                    shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self.nid))
                except Exception:
                    pass
                time.sleep(5)

        import time
        t = threading.Thread(target=update_tooltip_loop, daemon=True)
        t.start()

        # 消息循环
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def stop(self):
        self.is_running = False
        self._cleanup()
        if self.on_exit_callback:
            self.on_exit_callback()
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_DESTROY, 0, 0)
        sys.exit(0)
