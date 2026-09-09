#!/data/data/com.termux/files/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Echo 桌面伴侣 - 事件驱动型在席感知与黑屏休眠仲裁守护 (Presence Arbiter v2.0)
- 零死循环相机开销：平时 100% 深度休眠，杜绝 45s 定时满载与硬件磨损
- 四大关键事件驱动异步验视 (Event-Driven Vision Sentry):
    1. 事件 A (离开电脑锁屏 Win+L): 单次验视检测 wenbo 是否真不在；看书则留亮，真不在则黑屏休眠
    2. 事件 B (电脑闲置达 5 分钟): 单次验视检测 wenbo 是否在桌前自习；看书自习则续期留亮，离席则黑屏休眠
    3. 事件 C (回到电脑前动键鼠): 0ms 瞬间亮屏 (固定舒适亮度 190)，后台异步验视“是不是我”
    4. 事件 D (手动点击手机开黑屏): 立即黑屏熄灭，后台单次验视记录操作身份
- 熄灯断光协同 (Light Sentry < 3.0 Lux 持续 10s) -> 夜间纯黑断光休眠
"""

import os
import sys
import time
import json
import logging
import threading
import subprocess
import urllib.request
from typing import Optional, Dict, Any

LOG_FILE = "/data/data/com.termux/files/home/scripts/presence_arbiter.log"
STATE_FILE = "/data/data/com.termux/files/home/.echo/presence_state.json"
AMBIENT_FILE = "/data/data/com.termux/files/home/echo_companion/ambient_state.json"
SILENCE_STATE_FILE = "/data/data/com.termux/files/home/echo_companion/silence_state.json"

SILENCE_API = "http://127.0.0.1:8099/api/silence"
SILENCE_TOGGLE_API = "http://127.0.0.1:8099/api/silence/toggle"
BUBBLE_API = "http://127.0.0.1:8099/api/chat/bubble"

PC_AGENT_URLS = [
    "http://10.144.232.236:8766/api/pc/activity?level=summary",
    "http://127.0.0.1:8766/api/pc/activity?level=summary"
]

# 参数门限
PC_ACTIVE_THRESHOLD_SEC = 180      # 电脑闲置低于 180 秒认定常规在席
PC_IDLE_TIMEOUT_SEC = 300         # 闲置达 300 秒 (5 分钟) 触发离席事件验视
LOCK_CONFIRM_GRACE_SEC = 10       # 锁屏后确认延时 (秒)
READING_BUFFER_SEC = 300          # 人脸确认在桌前看书后，延期留亮时间 (5 分钟)
MANUAL_AWAKE_BUFFER_SEC = 900     # 手动点击手机唤醒后，免休眠自习保障期 (15 分钟)
MIN_CAMERA_INTERVAL_SEC = 15.0    # 两次摄像头验视之间最短防抖间隔 (15 秒)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)


def get_pc_activity() -> dict:
    token = os.environ.get("ECHO_PC_TOKEN", "").strip()
    headers = {"User-Agent": "EchoArbiter/2.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for url in PC_AGENT_URLS:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception:
            continue
    return {"status": "offline", "idle_seconds": 999999, "is_locked": True}


def get_ambient_light() -> dict:
    if os.path.exists(AMBIENT_FILE):
        try:
            with open(AMBIENT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"is_dark": False, "lux": 100.0, "mode": "active"}


def get_hud_silence() -> dict:
    try:
        req = urllib.request.Request(SILENCE_API, headers={"User-Agent": "EchoArbiter/2.0"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        pass
    if os.path.exists(SILENCE_STATE_FILE):
        try:
            with open(SILENCE_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"silenced": False, "mode": "active", "updated_at": 0}


def set_hud_silence(silenced: bool, screen_dim: bool = True, manual: bool = False):
    payload = json.dumps({
        "silenced": bool(silenced),
        "screen_dim": bool(screen_dim),
        "manual": bool(manual)
    }).encode("utf-8")
    req = urllib.request.Request(
        SILENCE_TOGGLE_API,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "EchoArbiter/2.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logging.error("设置 HUD 静默状态失败: %s", exc)
        return None


def push_wake_bubble(text: str, motion: int = 1):
    payload = json.dumps({"text": text, "motion": motion}).encode("utf-8")
    req = urllib.request.Request(
        BUBBLE_API,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "EchoArbiter/2.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=2.0):
            pass
    except Exception:
        pass


def execute_face_verify() -> dict:
    """底层调用 echo-face --verify 执行单次快速快照比对。"""
    cmd = ["/data/data/com.termux/files/home/echo-face", "--verify"]
    try:
        t0 = time.time()
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=16)
        dt = time.time() - t0
        if res.returncode == 0:
            out = res.stdout.strip()
            idx_start = out.find("{")
            idx_end = out.rfind("}")
            if idx_start != -1 and idx_end != -1:
                data = json.loads(out[idx_start:idx_end + 1])
                logging.info("单次验视完成 (耗时 %.2fs): %s", dt, data.get("message"))
                return data
    except Exception as exc:
        logging.warning("单次验视异常: %s", exc)
    return {"detected": False, "is_wenbo": False, "status": "away"}


def save_presence_state(state: dict):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_FILE)
    except Exception:
        pass


class EventDrivenArbiter:
    def __init__(self):
        self.camera_lock = threading.Lock()
        self.last_camera_check_time = 0.0
        self.desk_reading_until = 0.0
        self.manual_awake_until = 0.0

        # 上一周期的状态快照
        self.prev_is_locked = False
        self.prev_idle_seconds = 0
        self.prev_pc_online = True
        self.prev_silenced = False
        self.prev_manual_at = 0

        # 当前在席状态
        self.presence_status = "unknown"
        self.last_face_result: Dict[str, Any] = {}

    def trigger_face_verify_async(self, reason: str, callback):
        """异步触发单次快照验视，不阻塞主仲裁循环。"""
        now = time.time()
        if (now - self.last_camera_check_time) < MIN_CAMERA_INTERVAL_SEC:
            logging.info("跳过重复验视 (冷却中，距上次 %.1fs): reason=%s", now - self.last_camera_check_time, reason)
            return

        def _worker():
            if not self.camera_lock.acquire(blocking=False):
                logging.info("摄像头已在工作中，跳过并发触发: %s", reason)
                return
            try:
                self.last_camera_check_time = time.time()
                logging.info("【事件驱动快照触发】reason=%s", reason)
                res = execute_face_verify()
                self.last_face_result = res
                if callback:
                    callback(reason, res)
            finally:
                self.camera_lock.release()

        th = threading.Thread(target=_worker, daemon=True)
        th.start()

    def handle_verify_result(self, reason: str, res: dict):
        now = time.time()
        is_wenbo = res.get("is_wenbo", False)
        detected = res.get("detected", False)

        logging.info("【验视结果结算】reason=%s, is_wenbo=%s, detected=%s", reason, is_wenbo, detected)

        if reason in ("pc_locked", "pc_idle_5min"):
            if is_wenbo:
                # 人在桌前自习/看书，续期保持点亮
                self.desk_reading_until = now + READING_BUFFER_SEC
                self.presence_status = "desk_reading"
                logging.info("确认 wenbo 在桌前专注自习，屏幕保持点亮 (续期 %ds)", READING_BUFFER_SEC)
                push_wake_bubble("wenbo 正在专注自习呢～伴读陪着你", motion=3)
            else:
                # 确认人真的不在桌前 -> 离席黑屏休眠
                self.presence_status = "away_sleep"
                logging.info("确认 wenbo 已离席不在工位，进入【离席黑屏休眠】")
                set_hud_silence(True, screen_dim=True)
                self.prev_silenced = True

        elif reason == "pc_woken":
            if is_wenbo:
                self.presence_status = "desk_active"
                logging.info("唤醒验视：确认是 wenbo 本人，推送专属欢迎气泡！")
                push_wake_bubble("欢迎回来，wenbo~ 伴读已就绪！", motion=1)
            elif detected and not is_wenbo:
                self.presence_status = "visitor_detected"
                logging.info("唤醒验视：检测到访客靠近，启动防社死护盾！")
                push_wake_bubble("（检测到访客靠近，已启动防社死护盾）", motion=2)
            else:
                self.presence_status = "desk_active"
                logging.info("唤醒验视：未捕捉到正面清晰人脸，维持正常点亮状态")

        elif reason == "manual_sleep":
            if is_wenbo:
                logging.info("手动熄屏验视：确认是 wenbo 本人主动操作，祝休息愉快~")
            else:
                logging.info("手动熄屏验视：非本人操作或快速离席，保持黑屏防护")

    def run_loop(self):
        logging.info("Echo 在席感知与事件驱动仲裁守护 (v2.0) 已启动...")

        # 初始化状态
        initial_hud = get_hud_silence()
        self.prev_silenced = bool(initial_hud.get("silenced", False))
        self.prev_manual_at = int(initial_hud.get("manual_at", 0))

        initial_pc = get_pc_activity()
        self.prev_is_locked = bool(initial_pc.get("is_locked", False))
        self.prev_idle_seconds = int(initial_pc.get("idle_seconds", 0))
        self.prev_pc_online = (initial_pc.get("status") == "online")

        while True:
            try:
                now = time.time()
                pc = get_pc_activity()
                ambient = get_ambient_light()
                hud = get_hud_silence()

                curr_silenced = bool(hud.get("silenced", False))
                curr_manual_at = int(hud.get("manual_at", 0))

                pc_online = (pc.get("status") == "online")
                is_locked = bool(pc.get("is_locked", False))
                idle_sec = int(pc.get("idle_seconds", 0))

                # ── 0. 手动触控事件捕获 ──
                if curr_manual_at > self.prev_manual_at:
                    self.prev_manual_at = curr_manual_at
                    if curr_silenced:
                        # 【事件 D：手动点手机开黑屏】
                        logging.info("【事件 D 捕获】检测到手动点击手机切入黑屏静默！")
                        self.trigger_face_verify_async("manual_sleep", self.handle_verify_result)
                    else:
                        # 手动点击手机唤醒 -> 赋予 15 分钟自习保护
                        self.manual_awake_until = now + MANUAL_AWAKE_BUFFER_SEC
                        self.presence_status = "manual_study"
                        logging.info("检测到手动点击手机唤醒，已开启 15 分钟免休眠自习保护")

                # ── 1. 环境光真·断光判定 (宿舍整屋关灯就寝) ──
                if ambient.get("is_dark", False):
                    self.presence_status = "night_sleep"
                    if not curr_silenced:
                        logging.info("宿舍熄灯 (整屋极暗持续 10s)，进入夜间纯黑休眠")
                        set_hud_silence(True, screen_dim=True)
                        curr_silenced = True
                        self.prev_silenced = True

                # ── 2. 电脑锁屏中 ──
                elif is_locked:
                    if not self.prev_is_locked:
                        logging.info("【事件 A 捕获】电脑初次锁屏 (Win+L)，触发单次验视确认是否真不在...")
                        self.trigger_face_verify_async("pc_locked", self.handle_verify_result)
                    elif not curr_silenced and (now >= self.desk_reading_until) and (now >= self.manual_awake_until):
                        logging.info("电脑持续锁屏且自习留亮期满，再次验视确认是否仍在桌前...")
                        self.trigger_face_verify_async("pc_locked", self.handle_verify_result)

                # ── 3. 电脑闲置达 5 分钟 (300s) ──
                elif idle_sec >= PC_IDLE_TIMEOUT_SEC:
                    if not curr_silenced and (now >= self.desk_reading_until) and (now >= self.manual_awake_until):
                        logging.info("【事件 B 捕获】电脑闲置满 5 分钟，触发单次验视确认是否离席...")
                        self.trigger_face_verify_async("pc_idle_5min", self.handle_verify_result)

                # ── 4. 电脑活跃恢复唤醒 (动鼠标 / 敲键盘) ──
                elif pc_online and not is_locked and (idle_sec < 15):
                    # 判断是否是从锁屏、长闲置(>=60s)或休眠状态恢复过来
                    was_pc_inactive = self.prev_is_locked or (self.prev_idle_seconds >= 60) or not self.prev_pc_online or (curr_silenced and not hud.get("manual", False))
                    if was_pc_inactive:
                        logging.info("【事件 C 捕获】电脑重回活跃 (idle=%ds)，执行 0ms 瞬间亮屏！", idle_sec)
                        if curr_silenced:
                            set_hud_silence(False, screen_dim=False)
                            curr_silenced = False
                            self.prev_silenced = False
                        self.desk_reading_until = 0.0  # 重置看书自习缓冲
                        self.trigger_face_verify_async("pc_woken", self.handle_verify_result)
                    else:
                        self.presence_status = "desk_active"

                # ── 5. 自习保护期检查 ──
                elif (now < self.desk_reading_until) or (now < self.manual_awake_until):
                    self.presence_status = "desk_reading"
                    if curr_silenced:
                        set_hud_silence(False, screen_dim=False)
                        curr_silenced = False
                        self.prev_silenced = False

                # ── 保存上周期状态 ──
                self.prev_is_locked = is_locked
                self.prev_idle_seconds = idle_sec
                self.prev_pc_online = pc_online
                self.prev_silenced = curr_silenced

                # ── 状态快照持久化 ──
                save_presence_state({
                    "presence": self.presence_status,
                    "silenced": curr_silenced,
                    "pc_status": pc.get("status"),
                    "pc_idle_seconds": idle_sec,
                    "pc_is_locked": is_locked,
                    "ambient_lux": ambient.get("lux"),
                    "ambient_is_dark": ambient.get("is_dark"),
                    "camera_busy": self.camera_lock.locked(),
                    "desk_reading_remain": max(0, int(self.desk_reading_until - now)),
                    "manual_awake_remain": max(0, int(self.manual_awake_until - now)),
                    "last_face_status": self.last_face_result.get("status"),
                    "updated_at": int(now)
                })

            except Exception as e:
                logging.error("仲裁主循环异常: %s", e)

            time.sleep(2.0)


def main():
    arbiter = EventDrivenArbiter()
    arbiter.run_loop()


if __name__ == "__main__":
    main()
