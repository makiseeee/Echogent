#!/data/data/com.termux/files/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Echo Ambient Light Sentry (v2.0)
小米 MIX 2 环境光传感器 (BH1745) 监控哨兵
- 仅负责环境光采样与夜间熄灯状态写出 (~/echo_companion/ambient_state.json)
- 彻底剥离底层亮度控制 (termux-brightness 由 PresenceArbiter 统一仲裁，消除双写竞争)
- 防误判：需连续 10 秒 (5次采样) 照度低于 3.0 Lux 才确认真·宿舍关灯断光；照度 >= 10.0 Lux 确认开灯
"""

import os
import sys
import time
import json
import re
import subprocess

STATE_FILE = os.path.expanduser("~/echo_companion/ambient_state.json")
SENSOR_CMD = 'termux-sensor -c >/dev/null 2>&1; termux-sensor -s "BH1745 BH1745 ALS DEVICE"'

# 熄灯门限
DARK_LUX_THRESHOLD = 3.0       # 低于 3.0 Lux 视作整屋熄灯
BRIGHT_LUX_THRESHOLD = 10.0    # 高于 10.0 Lux 视作室内开灯
CONSECUTIVE_DARK_REQUIRED = 5  # 连续 5 次采样 (约 10 秒) 确认熄灯
CONSECUTIVE_BRIGHT_REQUIRED = 2 # 连续 2 次采样 (约 4 秒) 确认开灯


def get_current_lux():
    """读取小米 MIX 2 下巴处的 BH1745 传感器瞬态照度值 (Lux)。"""
    try:
        p = subprocess.Popen(
            SENSOR_CMD,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        out = ""
        for line in p.stdout:
            out += line
            m = re.search(r'"values":\s*\[\s*([\d\.]+)\s*\]', out)
            if m:
                p.kill()
                p.wait()
                return float(m.group(1))
    except Exception:
        pass
    return None


def update_ambient_state(is_dark: bool, lux: float):
    """原子化安全写出环境光状态 JSON。"""
    state = {
        "is_dark": bool(is_dark),
        "lux": round(lux, 2),
        "updated_at": int(time.time()),
        "mode": "sleep" if is_dark else "active",
    }
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
        os.replace(tmp, STATE_FILE)
    except Exception:
        pass


def main():
    is_dark = False
    consecutive_dark = 0
    consecutive_bright = 0

    while True:
        lux = get_current_lux()
        if lux is not None:
            if lux < DARK_LUX_THRESHOLD:
                consecutive_dark += 1
                consecutive_bright = 0
                if consecutive_dark >= CONSECUTIVE_DARK_REQUIRED:
                    is_dark = True
            elif lux >= BRIGHT_LUX_THRESHOLD:
                consecutive_bright += 1
                consecutive_dark = 0
                if consecutive_bright >= CONSECUTIVE_BRIGHT_REQUIRED:
                    is_dark = False
            else:
                # 3.0 ~ 10.0 Lux 处于弱光过渡带，保持现有状态，不重置计数
                pass

            update_ambient_state(is_dark, lux)

        time.sleep(2.0)


if __name__ == "__main__":
    main()
