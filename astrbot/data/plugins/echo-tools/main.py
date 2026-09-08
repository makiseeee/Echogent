"""Echo 工具集：分层微模块架构 Facade 声明与路由入口。

包含：全局 API Token 拦截计费、主动日程唤醒、Obsidian 知识库与任务管理、
PC 活动感知、Live2D 伴侣屏协同、模型动态热切及 AST 白名单安全计算器。
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any

# 确保本插件目录及子包在 sys.path 中
_plugin_dir = str(Path(__file__).resolve().parent)
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)

from core.compat import (
    AstrMessageEvent,
    Context,
    ProviderRequest,
    Star,
    TextPart,
    filter,
    logger,
    register,
)

# 子模块导入
from core.config import PluginConfig
from core.cron_scheduler import CronScheduler
from core.persona_compiler import PersonaCompiler
from core.token_interceptor import TokenInterceptor
from obsidian.obsidian_facade import ObsidianFacade
from sentries.companion_hud import CompanionHUD
from sentries.supervisor import SentrySupervisor
from services.model_switcher import ModelSwitcher
from services.safe_calculator import SafeCalculator
from services.usage_reporter import UsageReporter
from services.voice_transcriber import VoiceTranscriber
from services.web_fetcher import WebFetcher


@register("echo-tools", "echo", "Echo 个人专属工具集 (微模块分层架构)", "2.0.0")
class EchoTools(Star):
    """EchoTools 插件入口 Facade。业务逻辑均下沉至子服务模块。"""

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.config = PluginConfig()

        # 1. 核心与拦截
        TokenInterceptor.install(self.config.usage_db)
        self.cron_scheduler = CronScheduler(context, self.config)

        # 2. 独立业务服务
        self.usage_reporter = UsageReporter(self.config.usage_db)
        self.model_switcher = ModelSwitcher(context, self.config)
        self.calculator = SafeCalculator()
        self.voice_transcriber = VoiceTranscriber()
        self.web_fetcher = WebFetcher()

        # 3. 知识库与日常任务门面
        self.obsidian = ObsidianFacade(self.config)

        # 4. 状态与硬件感知哨兵
        self.sentries = SentrySupervisor(context, self.config)

    @property
    def _data_file(self):
        """兼容旧版测试与调用的数据文件解析器。"""
        return self.config.find_data_file

    @_data_file.setter
    def _data_file(self, func):
        self.config.find_data_file = func

    async def initialize(self) -> None:
        """插件初始化：编译人设、挂载主动日程与启动后台哨兵。"""
        PersonaCompiler.compile_if_needed(self.config)
        await self.sentries.start_all()
        try:
            await self.cron_scheduler.ensure_daily_cron_jobs()
        except Exception:  # noqa: BLE001
            logger.exception("[EchoTools] 注册每日主动定时任务异常")

    async def terminate(self) -> None:
        """插件优雅停机：取消所有后台异步守护与释放连接池。"""
        await self.sentries.stop_all()
        await self.web_fetcher.close()

    # ==========================================
    # 指令处理层 (Commands)
    # ==========================================

    @filter.command("用量")
    async def usage_command(self, event: AstrMessageEvent):
        """查询本地记录的 Token 用量：/用量、/用量 今日、/用量 本月、/用量 全部。"""
        report = await self.usage_reporter.get_report_async(str(event.message_str or ""))
        yield event.plain_result(report)

    @filter.command("模型")
    async def model_command(self, event: AstrMessageEvent):
        """动态查询云端可用模型并支持按序号或名称即时切换主力模型：/模型、/模型 1、/模型 glm-5.3-flash"""
        yield event.plain_result(self.model_switcher.handle_command(event))

    @filter.command("电脑状态")
    async def computer_status_command(self, event: AstrMessageEvent):
        """立即探测 PC 连通性与前台活动状态。"""
        online, detail = await self.sentries.pc.probe_computer(timeout_sec=1.5)
        yield event.plain_result(f"电脑在线，可用：{detail}" if online else "电脑当前离线，电脑工具和 Obsidian 暂不可用")

    @filter.command("开机")
    async def wol_command(self, event: AstrMessageEvent):
        """局域网唤醒台式机：向 Realtek 有线网卡广播 WOL Magic Packet。"""
        sender_id = str(event.get_sender_id() or "")
        if sender_id not in self.config.get_owner_ids():
            yield event.plain_result("🔒 权限受限：只有 Owner 可以唤醒台式机。")
            return
        _, msg = self.sentries.pc.send_wol()
        yield event.plain_result(msg)

    @filter.command("电量")
    async def battery_command(self, event: AstrMessageEvent):
        """查询手机当前真实电量、充电状态、电池温度与健康度。"""
        info = await self.sentries.battery.fetch_battery_info()
        yield event.plain_result(self.sentries.battery.format_command_report(info))

    # ==========================================
    # 消息与推理事件钩子 (LLM Hooks)
    # ==========================================

    @filter.on_llm_request()
    async def transcribe_qq_voice(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        """在文本大模型处理前将原生 QQ 语音消息转写为文本。"""
        await self.voice_transcriber.handle_qq_voice(
            event=event,
            req=req,
            owner_ids=self.config.get_owner_ids(),
            text_part_cls=TextPart,
        )

    @filter.on_llm_request(priority=40)
    async def route_model_for_task_types(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        """任务类型模型分流：Obsidian 操作、待办打勾、日程调度等工具调用使用 deepseek/deepseek-v4-flash。"""
        user_msg = ""
        if hasattr(event, "message_str") and event.message_str:
            user_msg = str(event.message_str).strip().lower()
        elif req.prompt:
            user_msg = str(req.prompt).strip().lower()

        tool_kws = ["待办", "任务", "打勾", "勾选", "完成", "日记", "obsidian", "笔记", "备忘", "记录", "dispatch", "创建", "链接", "日程", "开机", "电脑状态"]
        sys_prompt_str = str(getattr(req, "system_prompt", "") or "")
        is_tool_intent = (
            bool(req.tool_calls_result)
            or any(kw in user_msg for kw in tool_kws)
            or "【每日晨间任务调度】" in sys_prompt_str
            or "【每日晚间复盘问询与总结】" in sys_prompt_str
            or "【每日晚间复盘报告】" in sys_prompt_str
        )
        if is_tool_intent:
            req.model = "deepseek/deepseek-v4-flash"
            logger.info(f"[EchoTools] 识别到工具/调度任务，路由至高可靠模型: {req.model}")

    @filter.on_llm_request(priority=30)
    async def inject_computer_status(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        """实时捕获 PC 状态，根据对话意图向 System Prompt 注入桌面情境。"""
        user_msg = ""
        if hasattr(event, "message_str") and event.message_str:
            user_msg = str(event.message_str).strip()
        elif req.prompt:
            user_msg = str(req.prompt).strip()
        self.sentries.pc.inject_status_to_prompt(req, user_msg, text_part_cls=TextPart)

    @filter.on_decorating_result()
    async def mirror_reply_to_companion_screen(self, event: AstrMessageEvent) -> None:
        """跨屏气泡共振：在私聊 QQ 时同步打字与动作至 MIX 2 伴侣屏幕。"""
        await self.sentries.hud.mirror_reply(event)

    # ==========================================
    # Obsidian 笔记与两阶段提交工具 (LLM Tools)
    # ==========================================

    @filter.llm_tool(name="obsidian_prepare_create")
    async def obsidian_prepare_create(
        self,
        event: AstrMessageEvent,
        path: str,
        title: str,
        content: str,
        links: list[str] | None = None,
        metadata: dict | None = None,
    ) -> str:
        """预览创建一篇新的 Obsidian 笔记；只允许本人私聊，绝不直接写入。"""
        return await self.obsidian.prepare_create(event, path, title, content, links, metadata)

    @filter.llm_tool(name="obsidian_commit_create")
    async def obsidian_commit_create(self, event: AstrMessageEvent, operation_id: str = "") -> str:
        """提交上一轮已预览的 Obsidian 新笔记；仅在用户当前消息明确确认时调用。"""
        return await self.obsidian.commit_create(event, operation_id)

    async def obsidian_cancel_create(self, event: AstrMessageEvent, operation_id: str = "") -> str:
        """取消上一轮尚未提交的 Obsidian 创建预览。"""
        return await self.obsidian.cancel_create(event, operation_id)

    @filter.llm_tool(name="obsidian_prepare_link")
    async def obsidian_prepare_link(self, event: AstrMessageEvent, path: str, link_path: str, placement_hint: str = "") -> str:
        """预览在已有普通笔记的合适章节插入一个指向新笔记的链接；不会立即修改文件。"""
        return await self.obsidian.prepare_link(event, path, link_path, placement_hint)

    @filter.llm_tool(name="obsidian_commit_link")
    async def obsidian_commit_link(self, event: AstrMessageEvent, operation_id: str = "") -> str:
        """提交上一轮已预览的旧笔记链接修改；仅在当前消息明确确认时调用。"""
        return await self.obsidian.commit_link(event, operation_id)

    async def obsidian_cancel_link(self, event: AstrMessageEvent, operation_id: str = "") -> str:
        """取消上一轮尚未提交的旧笔记链接修改。"""
        return await self.obsidian.cancel_link(event, operation_id)

    @filter.llm_tool(name="obsidian_search")
    async def obsidian_search(self, event: AstrMessageEvent, query: str, scope: str = "standard") -> str:
        """搜索用户的 Obsidian 笔记，仅限本人 QQ 私聊使用。"""
        return await self.obsidian.search(event, query, scope)

    @filter.llm_tool(name="obsidian_list")
    async def obsidian_list(self, event: AstrMessageEvent, path: str, scope: str = "standard") -> str:
        """列出 Obsidian 允许目录内的笔记，仅限本人 QQ 私聊使用。"""
        return await self.obsidian.list_notes(event, path, scope)

    @filter.llm_tool(name="obsidian_read")
    async def obsidian_read(self, event: AstrMessageEvent, path: str, query: str = "", scope: str = "standard") -> str:
        """读取一篇 Obsidian 笔记的有限片段，仅限本人 QQ 私聊使用。"""
        return await self.obsidian.read_note(event, path, query, scope)

    # ==========================================
    # 待办日程与任务仓库工具 (LLM Tools)
    # ==========================================

    @filter.llm_tool(name="daily_add_task")
    async def daily_add_task(
        self,
        event: AstrMessageEvent,
        name: str,
        ddl: str = "",
        remarks: str = "",
        is_recurring: bool = False,
        cycle_rule: str = "",
    ) -> str:
        """【核心待办与循环任务工具】录入待办事项、日程安排或【循环习惯】。"""
        return await self.obsidian.add_task(event, name, ddl, remarks, is_recurring, cycle_rule)

    @filter.llm_tool(name="daily_dispatch")
    async def daily_dispatch(self, event: AstrMessageEvent, date: str = "", max_tasks: int = 3) -> str:
        """执行指定日期的晨间任务出库并生成日记任务清单。"""
        return await self.obsidian.dispatch(event, date, max_tasks)

    @filter.llm_tool(name="daily_list_inventory")
    async def daily_list_inventory(self, event: AstrMessageEvent) -> str:
        """查询尚未出库的任务库存池列表。"""
        return await self.obsidian.list_inventory(event)

    @filter.llm_tool(name="daily_manage_recent_task")
    async def daily_manage_recent_task(
        self,
        event: AstrMessageEvent,
        operation: str = "cancel",
        keyword: str = "",
        task_id: str = "",
        name: str = "",
        ddl: str = "",
        remarks: str = "",
        cycle_rule: str = "",
    ) -> str:
        """【修改或撤销待办】从任务库存池及今日日记中修改或撤销/删除某个待办。"""
        return await self.obsidian.manage_recent_task(event, operation, keyword, task_id, name, ddl, remarks, cycle_rule)

    @filter.llm_tool(name="daily_toggle_task")
    async def daily_toggle_task(self, event: AstrMessageEvent, keyword: str, completed: bool = True, date: str = "") -> str:
        """【当天任务打勾/取消打勾】当用户表明某项任务已完成或取消打勾时调用。"""
        return await self.obsidian.toggle_task(event, keyword, completed, date)

    @filter.llm_tool(name="daily_append_thino")
    async def daily_append_thino(self, event: AstrMessageEvent, content: str, date: str = "") -> str:
        """把用户明确要记录的碎片内容追加到当天 Thino。"""
        return await self.obsidian.append_thino(event, content, date)

    @filter.llm_tool(name="daily_recap")
    async def daily_recap(self, event: AstrMessageEvent, reflection: str = "", date: str = "", progress_notes: dict | None = None) -> str:
        """执行晚间复盘和未完成一次性任务回流。"""
        return await self.obsidian.recap(event, reflection, date, progress_notes)

    # ==========================================
    # 自主唤醒与定时提醒工具 (LLM Tools)
    # ==========================================

    @filter.llm_tool(name="schedule_wakeup")
    async def schedule_wakeup(self, event: AstrMessageEvent, delay_minutes: int, future_prompt: str) -> str:
        """设置一次性未来自主唤醒定时任务。"""
        return await self.cron_scheduler.schedule_wakeup(event, delay_minutes, future_prompt)

    @filter.llm_tool(name="cancel_wakeup")
    async def cancel_wakeup(self, event: AstrMessageEvent, job_id: str) -> str:
        """取消当前私聊中已设置的自主唤醒任务。"""
        return await self.cron_scheduler.cancel_wakeup(event, job_id)

    # ==========================================
    # 实用工具类 (Utility LLM Tools)
    # ==========================================

    async def web_search(self, event: AstrMessageEvent, query: str) -> str:
        """搜索互联网获取最新信息。"""
        return await self.web_fetcher.web_search(query)

    @filter.llm_tool(name="web_fetch")
    async def web_fetch(self, event: AstrMessageEvent, url: str) -> str:
        """抓取一个网页并返回纯文本内容。"""
        return await self.web_fetcher.web_fetch(url)

    @filter.llm_tool(name="calculator")
    async def calculator(self, event: AstrMessageEvent, expression: str) -> str:
        """精确计算数学表达式。"""
        return self.calculator.evaluate(expression)

    @filter.llm_tool(name="get_battery_status")
    async def get_battery_status(self, event: AstrMessageEvent) -> str:
        """获取手机当前真实电池电量百分比、充电状态与温度。"""
        info = await self.sentries.battery.fetch_battery_info()
        return self.sentries.battery.format_tool_status(info)


# 模块装载时自动安装全局 Token 拦截器
TokenInterceptor.install(PluginConfig().usage_db)
