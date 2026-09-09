"""工位桌边多模态偷瞄与破壁生活共振服务 (DeskGlanceService)。"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

import aiohttp
from core.compat import logger
from core.http_client import HttpClient


class DeskGlanceService:
    """结合手机前置摄像头与 PC Agent 前台活动，调用多模态大模型进行工位生活共振。"""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or os.environ.get(
            "ECHO_PHONE_CONFIG", "/opt/echo/data/cmd_config.json"
        )
        self.last_glance_ts: float = 0.0
        self.cooldown_seconds: float = 10.0  # 主动触发最小防抖冷却 (10s)

    def _get_zhipu_key(self) -> str:
        """优先从环境变量或 cmd_config.json 读取智谱多模态 API Key。"""
        env_key = os.environ.get("ZHIPUAI_API_KEY", "").strip() or os.environ.get(
            "ECHO_ZHIPU_API_KEY", ""
        ).strip()
        if env_key:
            return env_key

        p = Path(self.config_path)
        if not p.exists():
            # 尝试回退查找 termux-home
            alt = Path("/data/data/com.termux/files/home/cmd_config.json")
            if alt.exists():
                p = alt

        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                for source in data.get("provider_sources", []):
                    if "zhipu" in source.get("id", "").lower() or "bigmodel" in source.get("api_base", "").lower():
                        keys = source.get("key", [])
                        if keys and keys[0]:
                            return str(keys[0]).strip()
            except Exception as e:
                logger.warning(f"[DeskGlance] 读取 cmd_config.json 密钥失败: {e}")

        return ""

    def take_transient_photo(self, output_path: str = "/tmp/echo_desk_glance.jpg") -> tuple[bool, str]:
        """
        前置摄像头瞬态抓拍 (0.2s) 并即刻转 Base64，随后物理销毁磁盘文件 (0 留存)。
        """
        camera_bins = [
            "/data/data/com.termux/files/usr/bin/termux-camera-photo",
            "termux-camera-photo",
        ]
        cam_bin = next((b for b in camera_bins if os.path.exists(b) or os.system(f"which {b} >/dev/null 2>&1") == 0), "termux-camera-photo")

        # MIX 2 横屏右下角前置镜头固定为 camera_id 1
        cmd = [cam_bin, "-c", "1", output_path]
        try:
            res = subprocess.run(cmd, capture_output=True, timeout=8)
            if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                with open(output_path, "rb") as f:
                    b64_data = base64.b64encode(f.read()).decode("utf-8")
                # 物理立即销毁原始照片文件
                try:
                    os.remove(output_path)
                except Exception:
                    pass
                return True, b64_data
        except Exception as exc:
            logger.error(f"[DeskGlance] 相机瞬态抓拍异常: {exc}")
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except Exception:
                    pass
        return False, ""

    async def observe_desk(
        self,
        pc_activity: Optional[dict[str, Any]] = None,
    ) -> tuple[bool, str]:
        """
        仅获取纯视觉现实观察描述 (用于对话提示词注入)。
        返回: (是否成功, 现实观察要点文本)
        """
        now = time.time()
        if (now - self.last_glance_ts) < self.cooldown_seconds:
            return False, "冷却中"

        if pc_activity and pc_activity.get("privacy_mode"):
            return False, "隐私模式已开启"

        api_key = self._get_zhipu_key()
        if not api_key:
            return False, "未配置 API Key"

        self.last_glance_ts = now
        loop = asyncio.get_running_loop()
        snap_ok, b64_img = await loop.run_in_executor(None, self.take_transient_photo)
        if not snap_ok or not b64_img:
            return False, "拍照未成功"

        prompt = (
            "请用简短客观的中文描述这张工位仰视照片里的现实细节（限40字以内）："
            "文博的神态动作（是否戴耳机、托腮、揉眼等）、穿着特征、桌上摆的物品（水杯、饮料、零食等）。"
            "不要评价，只罗列观察到的关键特征。"
        )

        payload = {
            "model": "glm-4v-flash",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"},
                        },
                    ],
                }
            ],
            "temperature": 0.2,
            "max_tokens": 80,
        }

        try:
            session = await HttpClient.get_session()
            timeout = aiohttp.ClientTimeout(total=12.0)
            async with session.post(
                "https://open.bigmodel.cn/api/paas/v4/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            ) as resp:
                if resp.status == 200:
                    res_json = await resp.json(content_type=None)
                    obs = str(
                        res_json.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    ).strip()
                    if obs:
                        return True, obs
        except Exception as exc:
            logger.warning(f"[DeskGlance] observe_desk 异常: {exc}")

        return False, ""

    async def glance_desk(
        self,
        pc_activity: Optional[dict[str, Any]] = None,
        reason: str = "user_inquiry",
    ) -> str:
        """
        执行多模态桌边偷瞄，生成完整口语化傲娇对白 (用于指令响应与 HUD 气泡)。
        """
        now = time.time()
        if (now - self.last_glance_ts) < self.cooldown_seconds:
            remain = int(self.cooldown_seconds - (now - self.last_glance_ts))
            return f"刚瞄过你呢，别老让我猜啦（歇 {remain} 秒再看）~"

        # 检查隐私模式
        if pc_activity and pc_activity.get("privacy_mode"):
            return "文博开启了隐私模式，伴读不偷看哦~"

        api_key = self._get_zhipu_key()
        if not api_key:
            return "（多模态视觉模型密钥未配置，无法进行工位偷瞄）"

        self.last_glance_ts = now

        # 1. 异步执行瞬态快照
        loop = asyncio.get_running_loop()
        snap_ok, b64_img = await loop.run_in_executor(None, self.take_transient_photo)
        if not snap_ok or not b64_img:
            # 相机未成功则基于纯电脑活动自然降级回答
            return self._fallback_reply_without_camera(pc_activity)

        # 2. 组装情境提示词
        app = str(pc_activity.get("app", "") or "") if pc_activity else "电脑"
        category = str(pc_activity.get("category", "") or "") if pc_activity else "general"
        title = str(pc_activity.get("window_title", "") or "") if pc_activity else ""
        dur = int(pc_activity.get("duration_minutes", 0) or 0) if pc_activity else 0
        summary = str(pc_activity.get("summary", "") or "") if pc_activity else ""

        system_instruction = (
            "你叫 Echo，是住在文博书桌旁日系手帐看板里的小伴读（傲娇、嘴硬心软、观察敏锐的小女友口吻）。\n"
            "你正在通过工位手机前置摄像头偷瞄桌前的文博，并结合了他电脑前台的实时活动。\n"
            f"【电脑状态】：应用={app}，类别={category}，专注时长={dur}分钟，窗口摘要={summary or title}。\n"
            "【输出硬性要求】：\n"
            "1. 必须根据照片中的真实视觉细节（如文博的姿态：托腮、戴耳机、揉眼、靠椅背；桌上物品：水杯、可乐、外卖盒、零食；穿着：蓝衬衫等）直接调侃；\n"
            "2. 结合电脑正在做的事（写代码、看视频、摸鱼等）自然融合，给出贴近生活的真实互动；\n"
            "3. 严格限制在 1~2 句话以内（45 字以内），口语化，严禁书面腔；\n"
            "4. 称呼他为文博，严禁出现任何'图片中'、'照片显示'、'分析显示'等机械生硬字眼！直接像肉眼看见一样说出来。"
        )

        user_content = [
            {
                "type": "text",
                "text": "偷瞄一眼文博现在的工位状态，用你的口吻直接说他现在在干嘛：",
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"},
            },
        ]

        payload = {
            "model": "glm-4v-flash",
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.4,
            "max_tokens": 128,
        }

        try:
            session = await HttpClient.get_session()
            timeout = aiohttp.ClientTimeout(total=15.0)
            async with session.post(
                "https://open.bigmodel.cn/api/paas/v4/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            ) as resp:
                if resp.status == 200:
                    res_json = await resp.json(content_type=None)
                    reply = str(
                        res_json.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    ).strip()
                    if reply:
                        logger.info(f"[DeskGlance] 多模态偷瞄对白产出: {reply}")
                        return reply
                else:
                    err_text = await resp.text()
                    logger.warning(f"[DeskGlance] GLM-4V 请求失败 (HTTP {resp.status}): {err_text[:200]}")
        except Exception as exc:
            logger.error(f"[DeskGlance] 调用 GLM-4V 异常: {exc}")

        return self._fallback_reply_without_camera(pc_activity)

    @staticmethod
    def _fallback_reply_without_camera(pc_activity: Optional[dict[str, Any]]) -> str:
        """相机不可用时的纯电脑状态口语回退。"""
        if not pc_activity or pc_activity.get("status") != "online":
            return "电脑都关着呢，当我看不见呀？快老实交代在干嘛~"
        app = str(pc_activity.get("app", "") or "用电脑")
        summ = str(pc_activity.get("summary", "") or "")
        return f"电脑上明明正开着【{app}】呢，少让我猜了，当我不知道呀~"
