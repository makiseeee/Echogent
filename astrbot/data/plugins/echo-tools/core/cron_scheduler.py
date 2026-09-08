"""Proactive 主动定时任务与定时唤醒调度器 (CronScheduler)。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from core.compat import AstrMessageEvent, Context, logger

from core.config import PluginConfig


class CronScheduler:
    """管理晨报、晚报与自主定时唤醒任务。"""

    DAILY_CRON_SPECS = (
        {
            "name": "EchoDaily_MorningDispatch",
            "cron_expression": "30 8 * * *",
            "description": "Echo 每日晨间任务出库与晨报",
            "note": (
                "【每日晨间任务调度】这是固定晨报任务。先调用 daily_dispatch 获取今日真实任务，"
                "再根据 DDL、轻重和数量自然安排先后顺序，严禁机械套用固定时段。"
                "【自动挂载定时提醒】检查今日已出库任务（包含一次性待办与循环习惯）中是否有带具体时分（如 20:00、15:30 等）的任务；"
                "若该时间在今天尚未到来，计算距离当前时刻的分钟数，调用 schedule_wakeup(delay_minutes, future_prompt) 为其自动挂载今日的定时私聊提醒！"
                "有硬截止任务时优先说明；任务很少时保持精炼。询问 wenbo 昨晚睡眠和今天精力，"
                "说明可随时调整或削减任务。日常称呼使用 wenbo。最后必须调用 send_message_to_user，"
                "向当前 QQ 私聊发送简短晨报。"
            ),
        },
        {
            "name": "EchoDaily_EveningRecap",
            "cron_expression": "20 23 * * *",
            "description": "Echo 每日晚间复盘问询与超时回流",
            "note": (
                "【每日晚间复盘报告】这是每天 23:20 发给 wenbo 的专属晚间总结。你的核心职责是复盘今日任务完成度与灵感收获，向 wenbo 发送一条温暖且傲娇的晚间总结。日常称呼必须且只能使用五个小写英文字母 wenbo。严禁输出任何系统 Emoji（如 ✨、😊、🎉 等）。\\n"
                "【必须严格遵守的纪律】\\n"
                "1. 这是正式的【日终复盘】，严禁写成催促超时的赌气追问（严禁说“半天没动静/当我没说过/账我不记/随你”之类赌气生硬的话）！\\n"
                "2. 唯一事实标准：调用 obsidian_read(path='2. Areas/日记/YYYY-MM-DD.md') 读取今日日记。日记里 ## Tasks 下的勾选框（- [x] 为已完成，- [ ] 为未完成）是今日进度的唯一绝对事实！只要日记里打了勾即代表已完成，严禁怀疑！读取一次即可，严禁调用 daily_list_inventory 或 daily_recap，严禁重复调用 obsidian 工具！\\n"
                "3. 【排版与分段绝对规范】晚报必须层次分明，每个部分之间必须留出空行（使用 \\n\\n 换行）清晰分段，绝对禁止挤成密不透风的一大坨话！按以下三个段落组织：\\n"
                "   - 【第一段·任务盘点】：傲娇地盘点搞定的任务（如见导师、学籍注册、读书、日记等）；如果全部打勾，要别扭地肯定与夸奖（如“今天居然把待办全清空了，算你没偷懒，还挺利索的”）；若有未完成才提醒早点休息；\\n"
                "   - 【第二段·灵感与碎碎念共鸣】：日记的 ## Thino 里有 wenbo 记录的灵感思考（比如今天关于可乐奖励、GAN/Diffusion生成与自由意志的哲学发散），务必提取出来认真共鸣、聊上两句；\\n"
                "   - 【第三段·晚安道别】：提醒早点休息，晚安。\\n"
                "4. 组织好后，调用 send_message_to_user 发送到 QQ 私聊，然后调用 schedule_wakeup(delay_minutes=40, future_prompt='40分钟超时回流检查') 设定深夜超时兜底。"
            ),
        },
    )

    def __init__(self, context: Context, config: PluginConfig) -> None:
        self.context = context
        self.config = config

    async def ensure_daily_cron_jobs(self) -> None:
        """注册或更新持久化主动日程（晨报、晚报）。"""
        cron_manager = getattr(self.context, "cron_manager", None)
        if cron_manager is None:
            raise RuntimeError("AstrBot Cron 服务不可用")

        session = self.config.get_daily_cron_session()
        sender_id = session.rsplit(":", 1)[-1]
        jobs = await cron_manager.list_jobs(job_type="active_agent")

        for spec in self.DAILY_CRON_SPECS:
            matching = [job for job in jobs if job.name == spec["name"]]
            payload = {
                "session": session,
                "sender_id": sender_id,
                "note": spec["note"],
                "origin": "echo-tools",
            }
            if matching:
                current = matching[0]
                if (
                    current.cron_expression != spec["cron_expression"]
                    or current.timezone != "Asia/Shanghai"
                    or current.payload != payload
                    or current.description != spec["description"]
                    or not current.enabled
                    or not current.persistent
                    or current.run_once
                ):
                    await cron_manager.update_job(
                        current.job_id,
                        cron_expression=spec["cron_expression"],
                        timezone="Asia/Shanghai",
                        payload=payload,
                        description=spec["description"],
                        enabled=True,
                        persistent=True,
                        run_once=False,
                    )
                for duplicate in matching[1:]:
                    await cron_manager.delete_job(duplicate.job_id)
            else:
                await cron_manager.add_active_job(
                    name=spec["name"],
                    cron_expression=spec["cron_expression"],
                    payload=payload,
                    description=spec["description"],
                    timezone="Asia/Shanghai",
                    enabled=True,
                    persistent=True,
                    run_once=False,
                )

    async def schedule_wakeup(
        self,
        event: AstrMessageEvent,
        delay_minutes: int,
        future_prompt: str,
    ) -> str:
        """设置一次性未来自主唤醒定时任务。"""
        if event.get_group_id():
            return "设置失败：自主唤醒仅允许本人私聊。"
        try:
            delay_minutes = int(delay_minutes)
        except (TypeError, ValueError):
            return "设置失败：延迟时间必须是整数分钟。"

        future_prompt = str(future_prompt or "").strip()
        if delay_minutes <= 0:
            return "设置失败：延迟时间必须大于 0 分钟。"
        if delay_minutes > 7 * 24 * 60:
            return "设置失败：单次唤醒最多只能设置 7 天内。"
        if not future_prompt:
            return "设置失败：未来唤醒提示不能为空。"

        cron_manager = getattr(self.context, "cron_manager", None)
        if cron_manager is None:
            return "设置失败：AstrBot Cron 服务不可用。"

        session = str(getattr(event, "unified_msg_origin", "") or "")
        if not session:
            return "设置失败：无法确定当前会话。"

        run_at = datetime.now().astimezone() + timedelta(minutes=delay_minutes)
        try:
            job = await cron_manager.add_active_job(
                name="Echo_ScheduledWakeup",
                cron_expression=None,
                payload={
                    "session": session,
                    "sender_id": str(event.get_sender_id() or ""),
                    "note": (
                        "【自我唤醒】\n"
                        + future_prompt
                        + "\n【重要约束】调用 send_message_to_user 发送 1 条消息后立即结束，严禁重复发送。"
                    ),
                    "origin": "echo-tools",
                },
                description=f"Echo 自主唤醒：{future_prompt[:80]}",
                timezone=None,
                run_once=True,
                run_at=run_at,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("[CronScheduler] schedule_wakeup failed")
            return f"设置失败：{exc}"
        return f"已设置自主唤醒，将在约 {delay_minutes} 分钟后触发（任务 ID：{job.job_id}）。"

    async def cancel_wakeup(self, event: AstrMessageEvent, job_id: str) -> str:
        """取消当前私聊中已设置的自主唤醒任务。"""
        if event.get_group_id():
            return "取消失败：自主唤醒仅允许本人私聊。"

        cron_manager = getattr(self.context, "cron_manager", None)
        if cron_manager is None:
            return "取消失败：AstrBot Cron 服务不可用。"

        try:
            jobs = await cron_manager.list_jobs(job_type="active_agent")
            target = next(
                (
                    job
                    for job in jobs
                    if job.job_id == str(job_id)
                    and (job.payload or {}).get("session") == getattr(event, "unified_msg_origin", "")
                ),
                None,
            )
            if target is None:
                return "取消失败：找不到属于当前会话的唤醒任务。"
            await cron_manager.delete_job(target.job_id)
            return f"已取消自主唤醒（任务 ID：{target.job_id}）。"
        except Exception as exc:  # noqa: BLE001
            logger.exception("[CronScheduler] cancel_wakeup failed")
            return f"取消失败：{exc}"
