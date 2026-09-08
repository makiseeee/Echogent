"""QQ 语音消息转文字服务 (VoiceTranscriber)。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import aiohttp
from core.compat import AstrMessageEvent, ProviderRequest, logger


class VoiceTranscriber:
    """使用 SiliconFlow SenseVoice 将 QQ 语音消息听写为纯文本。"""

    @staticmethod
    async def transcribe_audio(audio_path: str) -> str:
        """调用 SenseVoiceSmall 接口转写本地语音文件。"""
        api_key = os.environ.get("ECHO_SILICONFLOW_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("未配置 ECHO_SILICONFLOW_API_KEY")

        path = Path(audio_path)
        if not path.is_file():
            raise RuntimeError(f"语音文件不存在：{path.name}")

        max_bytes = int(os.environ.get("ECHO_STT_MAX_BYTES", str(25 * 1024 * 1024)))
        if path.stat().st_size > max_bytes:
            raise RuntimeError("语音文件过大")

        form = aiohttp.FormData()
        audio_file = path.open("rb")
        try:
            form.add_field("file", audio_file, filename=path.name, content_type="application/octet-stream")
            form.add_field("model", os.environ.get("ECHO_STT_MODEL", "FunAudioLLM/SenseVoiceSmall"))
            timeout = aiohttp.ClientTimeout(total=float(os.environ.get("ECHO_STT_TIMEOUT", "90")))
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    "https://api.siliconflow.cn/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    data=form,
                ) as resp:
                    body = await resp.text()
                    if resp.status != 200:
                        raise RuntimeError(f"SenseVoice 请求失败（HTTP {resp.status}）：{body[:200]}")
        finally:
            audio_file.close()

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("SenseVoice 返回了无法解析的响应") from exc

        text = str(payload.get("text", "") or "").strip()
        if not text:
            raise RuntimeError("SenseVoice 未识别出文字")
        return text

    async def handle_qq_voice(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
        owner_ids: set[str],
        text_part_cls: Any = None,
    ) -> None:
        """在 LLM 文本请求前将 QQ 语音链接转写为文字 prompt。"""
        audio_urls = list(getattr(req, "audio_urls", None) or [])
        if not audio_urls:
            return

        # 仅限 Owner 私聊识别语音，防止群聊消耗 Token
        if event.get_group_id() or str(event.get_sender_id() or "") not in owner_ids:
            req.audio_urls = []
            if text_part_cls is not None:
                req.extra_user_content_parts.append(text_part_cls(text="[语音消息未转写：仅本人私聊可用]").mark_as_temp())
            return

        transcripts = []
        try:
            for audio_path in audio_urls[:3]:
                transcripts.append(await self.transcribe_audio(audio_path))
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[VoiceTranscriber] QQ 语音转写失败: {exc}")
            if text_part_cls is not None:
                req.extra_user_content_parts.append(text_part_cls(text=f"[语音识别失败：{exc}]").mark_as_temp())
        else:
            joined = "\n".join(transcripts)
            voice_text = f"[用户通过 QQ 语音说]\n{joined}"
            if req.prompt and req.prompt.strip():
                req.prompt = f"{req.prompt.strip()}\n\n{voice_text}"
            else:
                req.prompt = voice_text
            logger.info(f"[VoiceTranscriber] 成功转写 {len(transcripts)} 条 QQ 语音消息")
        finally:
            req.audio_urls = []
