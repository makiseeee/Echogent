"""Obsidian 知识库操作门面与两阶段提交事务协调器 (ObsidianFacade)。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.compat import AstrMessageEvent, logger

from core.config import PluginConfig
from sentries.companion_hud import CompanionHUD
from obsidian.daily_task_manager import DailyTaskManager, TaskAmbiguityError
from obsidian.obsidian_access import AccessMode, VaultAccessPolicy
from obsidian.obsidian_git import VaultGitSync
from obsidian.obsidian_search import list_notes, read_note_excerpt, search_vault
from obsidian.obsidian_write import NoteWriteService


class ObsidianFacade:
    """统一协调 Obsidian 笔记的检索、两阶段写入 (2PC) 与任务仓库管理。"""

    def __init__(self, config: PluginConfig) -> None:
        self.config = config
        self._obsidian_pending: dict[str, str] = {}
        self._obsidian_link_pending: dict[str, str] = {}
        self._obsidian_local: NoteWriteService | None = None
        self._daily_manager: DailyTaskManager | None = None

    def _get_obsidian_service(self) -> NoteWriteService:
        if self._obsidian_local is None:
            vault = self.config.vault_dir
            policy = VaultAccessPolicy(vault)
            git_sync = VaultGitSync(
                vault,
                remote=self.config.git_remote,
                branch=self.config.git_branch,
                timeout_seconds=self.config.git_timeout,
                username=self.config.git_username,
                token=self.config.git_token,
            )
            self._obsidian_local = NoteWriteService(policy, self.config.audit_db, git_sync)
        return self._obsidian_local

    def _get_daily_manager(self) -> DailyTaskManager:
        if self._daily_manager is None:
            vault = self.config.vault_dir
            git_sync = VaultGitSync(
                vault,
                remote=self.config.git_remote,
                branch=self.config.git_branch,
                timeout_seconds=self.config.git_timeout,
                username=self.config.git_username,
                token=self.config.git_token,
            )
            self._daily_manager = DailyTaskManager(git_sync)
        return self._daily_manager

    async def obsidian_call(self, event: AstrMessageEvent, payload: dict[str, Any]) -> str:
        """底层 Obsidian 动作派发器，含私聊鉴权与 2. Areas 自动提权降级保护。"""
        sender_id = str(event.get_sender_id() or "")
        if event.get_group_id():
            return "隐私保护：群聊禁止访问 Obsidian"
        if sender_id not in self.config.get_owner_ids():
            return "隐私保护：只有 Vault 本人可以访问 Obsidian"

        try:
            service = self._get_obsidian_service()
            policy = service.policy
            action = payload.get("action")
            if action in {"search", "list", "read", "prepare_create", "prepare_link"} and service.git_sync:
                service.git_sync.pull_if_stale(30.0)

            target_path = str(payload.get("path") or "")
            scope_val = payload.get("scope") or "standard"
            if scope_val == "standard":
                if "2. Areas" in target_path or target_path.startswith("2."):
                    scope_val = "private_on_demand"
                elif "4. Archives" in target_path or target_path.startswith("4."):
                    scope_val = "archive_on_demand"

            if action == "search":
                try:
                    results = search_vault(policy, payload["query"], AccessMode(scope_val), payload.get("limit", 20))
                except PermissionError:
                    results = search_vault(policy, payload["query"], AccessMode.PRIVATE_ON_DEMAND, payload.get("limit", 20))
                value = [r.__dict__ for r in results]
            elif action == "list":
                mode = AccessMode(scope_val)
                try:
                    value = list_notes(policy, payload["path"], mode, payload.get("limit", 20))
                except PermissionError:
                    if mode != AccessMode.PRIVATE_ON_DEMAND and ("2. Areas" in target_path or "日记" in target_path):
                        value = list_notes(policy, payload["path"], AccessMode.PRIVATE_ON_DEMAND, payload.get("limit", 20))
                    else:
                        raise
            elif action == "read":
                mode = AccessMode(scope_val)
                try:
                    res = read_note_excerpt(policy, payload["path"], mode, payload.get("query", ""), payload.get("max_chars", 4000))
                except PermissionError:
                    if mode != AccessMode.PRIVATE_ON_DEMAND and ("2. Areas" in target_path or "日记" in target_path):
                        res = read_note_excerpt(policy, payload["path"], AccessMode.PRIVATE_ON_DEMAND, payload.get("query", ""), payload.get("max_chars", 4000))
                    elif mode != AccessMode.ARCHIVE_ON_DEMAND and "4. Archives" in target_path:
                        res = read_note_excerpt(policy, payload["path"], AccessMode.ARCHIVE_ON_DEMAND, payload.get("query", ""), payload.get("max_chars", 4000))
                    else:
                        raise
                value = res.__dict__
            elif action == "prepare_create":
                op = service.prepare(sender_id, payload["path"], payload["title"], payload["content"], payload.get("links", []), payload.get("metadata", {}))
                value = {"operation_id": op.operation_id, "path": op.path, "links": list(op.links), "expires_at": op.expires_at.isoformat(), "preview": op.text}
            elif action == "commit_create":
                op = service.commit(sender_id, payload["operation_id"])
                value = {"created": op.path, "links": list(op.links)}
            elif action == "cancel_create":
                op = service.cancel(sender_id, payload["operation_id"])
                value = {"cancelled": op.path}
            elif action == "prepare_link":
                op = service.prepare_link(sender_id, payload["path"], payload["link_path"], payload.get("placement_hint", ""))
                value = {"operation_id": op.operation_id, "path": op.path, "link_path": op.link_path, "insertion": op.heading, "expires_at": op.expires_at.isoformat()}
            elif action == "commit_link":
                op = service.commit_link(sender_id, payload["operation_id"])
                value = {"updated": op.path, "link": op.link_path, "insertion": op.heading}
            elif action == "cancel_link":
                op = service.cancel_link(sender_id, payload["operation_id"])
                value = {"cancelled": op.path}
            else:
                return "Obsidian 访问失败：未知操作"
            return json.dumps(value, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[ObsidianFacade] Obsidian request error: {exc}")
            return f"Obsidian 访问失败：{exc}"

    async def daily_call(self, event: AstrMessageEvent, payload: dict[str, Any]) -> str:
        """底层每日任务仓库派发器。"""
        if event.get_group_id():
            return "隐私保护：群聊禁止访问日常任务"
        if str(event.get_sender_id() or "") not in self.config.get_owner_ids():
            return "隐私保护：只有本人可以访问日常任务"

        try:
            manager = self._get_daily_manager()
            action = payload.get("action")
            if action == "daily_add_task":
                value = manager.ingest_task(
                    payload["name"],
                    payload.get("ddl") or None,
                    payload.get("remarks", ""),
                    bool(payload.get("is_recurring")),
                    payload.get("cycle_rule", ""),
                )
            elif action == "daily_list_inventory":
                value = manager.list_inventory()
            elif action == "daily_manage_inventory_task":
                value = manager.manage_inventory_task(
                    task_id=payload.get("task_id"),
                    action=payload.get("operation", "cancel"),
                    keyword=payload.get("keyword"),
                    name=payload.get("name"),
                    ddl=payload.get("ddl"),
                    remarks=payload.get("remarks"),
                    cycle_rule=payload.get("cycle_rule"),
                )
            elif action == "daily_dispatch":
                value = manager.morning_dispatch(payload.get("date") or None, int(payload.get("max_tasks", 3)))
            elif action == "daily_toggle":
                value = manager.toggle_daily_task(
                    payload["keyword"],
                    bool(payload.get("completed", True)),
                    payload.get("date") or None,
                )
            elif action == "daily_thino":
                manager.append_thino(payload["content"], payload.get("date") or None)
                value = {"appended": True}
            elif action == "daily_recap":
                value = manager.evening_recap_and_requeue(
                    payload.get("date") or None,
                    payload.get("reflection", ""),
                    payload.get("progress_notes") or {},
                )
            else:
                return "日常任务失败：未知操作"

            # 每次任务变动后自动同步导出伴侣屏任务
            await CompanionHUD.export_companion_tasks_async(self.config.vault_dir)
            return json.dumps(value, ensure_ascii=False)
        except TaskAmbiguityError as exc:
            return json.dumps({"error": str(exc), "matches": [task.__dict__ for task in exc.matches]}, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[ObsidianFacade] local daily task error")
            return f"日常任务失败：{exc}"

    # --- 高级 LLM 工具封装 ---

    async def prepare_create(
        self,
        event: AstrMessageEvent,
        path: str,
        title: str,
        content: str,
        links: list[str] | None = None,
        metadata: dict | None = None,
    ) -> str:
        """预览创建新笔记 (两阶段提交第 1 步)。"""
        result = await self.obsidian_call(
            event,
            {"action": "prepare_create", "path": path, "title": title, "content": content, "links": links or [], "metadata": metadata or {}},
        )
        try:
            payload = json.loads(result)
            if isinstance(payload, dict) and payload.get("operation_id"):
                self._obsidian_pending[str(event.get_sender_id())] = payload["operation_id"]
        except (TypeError, json.JSONDecodeError):
            pass
        return result + "\n请先向用户展示预览，等待用户明确回复“确认创建”或“确认写入”，不要在本轮继续提交。"

    async def commit_create(self, event: AstrMessageEvent, operation_id: str = "") -> str:
        """提交新笔记 (两阶段提交第 2 步)。"""
        message = str(getattr(event, "message_str", "") or "")
        if not any(phrase in message for phrase in ("确认创建", "确认写入", "确认保存")):
            return "写入已暂停：需要用户在当前消息明确说“确认创建”“确认写入”或“确认保存”。"
        sender_id = str(event.get_sender_id() or "")
        expected = self._obsidian_pending.get(sender_id, "")
        if not expected or operation_id != expected:
            return "写入失败：没有属于当前用户的待确认创建操作，或操作已过期。"
        result = await self.obsidian_call(event, {"action": "commit_create", "operation_id": operation_id})
        if not result.startswith("Obsidian 访问失败"):
            self._obsidian_pending.pop(sender_id, None)
        return result

    async def cancel_create(self, event: AstrMessageEvent, operation_id: str = "") -> str:
        """取消新笔记创建。"""
        sender_id = str(event.get_sender_id() or "")
        expected = self._obsidian_pending.get(sender_id, "")
        operation_id = operation_id or expected
        if not operation_id or operation_id != expected:
            return "取消失败：没有属于当前用户的待确认创建操作。"
        result = await self.obsidian_call(event, {"action": "cancel_create", "operation_id": operation_id})
        if not result.startswith("Obsidian 访问失败"):
            self._obsidian_pending.pop(sender_id, None)
        return result

    async def prepare_link(self, event: AstrMessageEvent, path: str, link_path: str, placement_hint: str = "") -> str:
        """预览在已有笔记中插入 Wikilink。"""
        result = await self.obsidian_call(event, {"action": "prepare_link", "path": path, "link_path": link_path, "placement_hint": placement_hint})
        try:
            payload = json.loads(result)
            if isinstance(payload, dict) and payload.get("operation_id"):
                self._obsidian_link_pending[str(event.get_sender_id())] = payload["operation_id"]
        except (TypeError, json.JSONDecodeError):
            pass
        return result + "\n请展示修改文件、插入章节和链接，等待用户下一条消息明确确认，不要在本轮提交。"

    async def commit_link(self, event: AstrMessageEvent, operation_id: str = "") -> str:
        """提交链接插入。"""
        message = str(getattr(event, "message_str", "") or "")
        if not any(phrase in message for phrase in ("确认修改", "确认链接", "确认写入", "确认保存")):
            return "修改已暂停：需要用户在当前消息明确确认。"
        sender = str(event.get_sender_id() or "")
        expected = self._obsidian_link_pending.get(sender, "")
        if not expected or expected != operation_id:
            return "修改失败：没有属于当前用户的待确认链接操作。"
        result = await self.obsidian_call(event, {"action": "commit_link", "operation_id": operation_id})
        if not result.startswith("Obsidian 访问失败"):
            self._obsidian_link_pending.pop(sender, None)
        return result

    async def cancel_link(self, event: AstrMessageEvent, operation_id: str = "") -> str:
        """取消链接插入。"""
        sender = str(event.get_sender_id() or "")
        expected = self._obsidian_link_pending.get(sender, "")
        operation_id = operation_id or expected
        if not operation_id or operation_id != expected:
            return "取消失败：没有属于当前用户的待确认链接操作。"
        result = await self.obsidian_call(event, {"action": "cancel_link", "operation_id": operation_id})
        if not result.startswith("Obsidian 访问失败"):
            self._obsidian_link_pending.pop(sender, None)
        return result

    async def search(self, event: AstrMessageEvent, query: str, scope: str = "standard") -> str:
        """搜索笔记。"""
        return await self.obsidian_call(event, {"action": "search", "query": query, "scope": scope})

    async def list_notes(self, event: AstrMessageEvent, path: str, scope: str = "standard") -> str:
        """列出目录。"""
        return await self.obsidian_call(event, {"action": "list", "path": path, "scope": scope})

    async def read_note(self, event: AstrMessageEvent, path: str, query: str = "", scope: str = "standard") -> str:
        """读取笔记片段。"""
        return await self.obsidian_call(event, {"action": "read", "path": path, "query": query, "scope": scope})

    async def add_task(self, event: AstrMessageEvent, name: str, ddl: str = "", remarks: str = "", is_recurring: bool = False, cycle_rule: str = "") -> str:
        """添加待办或循环习惯。"""
        return await self.daily_call(event, {"action": "daily_add_task", "name": name, "ddl": ddl, "remarks": remarks, "is_recurring": is_recurring, "cycle_rule": cycle_rule})

    async def dispatch(self, event: AstrMessageEvent, date: str = "", max_tasks: int = 3) -> str:
        """晨间任务出库。"""
        return await self.daily_call(event, {"action": "daily_dispatch", "date": date, "max_tasks": max_tasks})

    async def list_inventory(self, event: AstrMessageEvent) -> str:
        """查询任务库存池。"""
        return await self.daily_call(event, {"action": "daily_list_inventory"})

    async def manage_recent_task(self, event: AstrMessageEvent, operation: str = "cancel", keyword: str = "", task_id: str = "", name: str = "", ddl: str = "", remarks: str = "", cycle_rule: str = "") -> str:
        """修改或取消待办。"""
        return await self.daily_call(event, {"action": "daily_manage_inventory_task", "task_id": task_id, "operation": operation, "keyword": keyword, "name": name, "ddl": ddl, "remarks": remarks, "cycle_rule": cycle_rule})

    async def toggle_task(self, event: AstrMessageEvent, keyword: str, completed: bool = True, date: str = "") -> str:
        """标记当天任务打勾或未完成。"""
        return await self.daily_call(event, {"action": "daily_toggle", "keyword": keyword, "completed": completed, "date": date})

    async def append_thino(self, event: AstrMessageEvent, content: str, date: str = "") -> str:
        """追加 Thino 随手记。"""
        return await self.daily_call(event, {"action": "daily_thino", "content": content, "date": date})

    async def recap(self, event: AstrMessageEvent, reflection: str = "", date: str = "", progress_notes: dict | None = None) -> str:
        """晚间复盘与回流。"""
        return await self.daily_call(event, {"action": "daily_recap", "reflection": reflection, "date": date, "progress_notes": progress_notes or {}})
