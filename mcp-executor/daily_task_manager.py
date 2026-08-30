"""Deterministic task warehouse and daily journal workflow for Echo."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
import re
import uuid
from typing import Callable, Optional

from obsidian_git import VaultGitSync


TASKS_PATH = Path("2. Areas/日程与作息/Tasks.md")
DAILY_DIR = Path("2. Areas/日记")
TEMPLATE_PATH = Path("Templates/日记模板.md")
ONE_TIME_HEADING = "## 📌 一次性待办 (One-time Tasks)"
RECURRING_HEADING = "## 🔁 循环任务 (Recurring Habits)"
TASK_META_RE = re.compile(r"<!--\s*echo-task:(.*?)\s*-->")
CHECKBOX_RE = re.compile(r"^- \[([ xX])\]\s+(.*)$")
DAILY_STATE_RE = re.compile(r"<!--\s*echo-daily:date=([^;]+);dispatched=(true|false);recapped=(true|false)\s*-->")


@dataclass(frozen=True)
class Task:
    id: str
    name: str
    type: str
    created: str = ""
    ddl: str = ""
    remarks: str = ""
    rule: str = ""
    completed: bool = False
    streak: int = 0


class TaskAmbiguityError(ValueError):
    def __init__(self, matches: list[Task]):
        self.matches = matches
        super().__init__("关键词匹配到多个任务，请进一步确认")


class DailyTaskManager:
    def __init__(self, git_sync: VaultGitSync):
        self.git_sync = git_sync
        self.vault = git_sync.vault

    @staticmethod
    def _today(date_str: Optional[str]) -> date:
        return date.fromisoformat(date_str) if date_str else datetime.now().astimezone().date()

    @staticmethod
    def _new_id() -> str:
        return uuid.uuid4().hex[:12].upper()

    @staticmethod
    def _compact_task(task: Task) -> dict:
        """Keep meaningful values only; retain false/zero and stable identity fields."""
        raw = asdict(task)
        result = {key: value for key, value in raw.items() if value not in ("", None)}
        for key in ("id", "name", "type"):
            if key in raw:
                result.setdefault(key, raw[key])
        return result

    @staticmethod
    def _meta(text: str) -> dict[str, str]:
        match = TASK_META_RE.search(text)
        if not match:
            return {}
        result = {}
        for item in match.group(1).split(";"):
            if "=" in item:
                key, value = item.split("=", 1)
                result[key.strip()] = value.strip()
        return result

    @classmethod
    def _parse_task(cls, line: str) -> Task | None:
        match = CHECKBOX_RE.match(line.strip())
        if not match:
            return None
        body = TASK_META_RE.sub("", match.group(2)).strip()
        meta = cls._meta(line)
        parts = [part.strip() for part in body.split("|")]
        name = parts[0]
        fields: dict[str, str] = {}
        remarks = []
        for part in parts[1:]:
            if ":" in part:
                key, value = part.split(":", 1)
                fields[key.strip()] = value.strip()
            elif part and "连续" not in part and "连胜" not in part:
                remarks.append(part)
        task_type = meta.get("type", "recurring" if "周期" in fields else "one_time")
        raw_streak = meta.get("streak", "")
        if not raw_streak:
            for part in parts:
                if "连续" in part or "连胜" in part:
                    num_match = re.search(r"\d+", part)
                    if num_match:
                        raw_streak = num_match.group(0)
        streak_val = int(raw_streak) if raw_streak.isdigit() else 0
        return Task(
            id=meta.get("id", cls._new_id()), name=name, type=task_type,
            created=meta.get("created", fields.get("创建", "")),
            ddl=meta.get("ddl", fields.get("DDL", "")),
            remarks=" | ".join(remarks), rule=meta.get("rule", fields.get("周期", "")),
            completed=match.group(1).lower() == "x",
            streak=streak_val,
        )

    @staticmethod
    def _render_task(task: Task, daily: bool = False) -> str:
        if daily:
            source = "warehouse" if task.type == "one_time" else "recurring"
            return f"- [{'x' if task.completed else ' '}] {task.name} <!-- echo-task:id={task.id};type={task.type};source={source};ddl={task.ddl} -->"
        if task.type == "recurring":
            visible = f"{task.name} | 周期: {task.rule}"
            if task.streak > 0:
                visible += f" | 🔥 连续 {task.streak} 天"
            if task.remarks:
                visible += f" | {task.remarks}"
            meta = f"id={task.id};type=recurring;rule={task.rule};streak={task.streak}"
        else:
            visible = f"{task.name} | 创建: {task.created}"
            if task.ddl:
                visible += f" | DDL: {task.ddl}"
            if task.remarks:
                visible += f" | {task.remarks}"
            meta = f"id={task.id};type=one_time;created={task.created};ddl={task.ddl}"
        return f"- [ ] {visible} <!-- echo-task:{meta} -->"

    @staticmethod
    def _section(text: str, heading: str) -> tuple[int, int]:
        lines = text.splitlines()
        try:
            start = lines.index(heading) + 1
        except ValueError:
            lines.extend(([""] if lines and lines[-1] else []) + [heading])
            start = len(lines)
            text = "\n".join(lines) + "\n"
        end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
        return start, end

    @staticmethod
    def _replace_managed(text: str, name: str, lines: list[str], append: bool = False) -> str:
        start_marker = f"<!-- echo-{name}:start -->"
        end_marker = f"<!-- echo-{name}:end -->"
        if start_marker not in text or end_marker not in text:
            heading = {"tasks": "## Tasks", "thino": "## Thino", "reflection": "## Reflection"}[name]
            if heading not in text:
                text = text.rstrip() + f"\n\n{heading}\n"
            text = text.replace(heading, f"{heading}\n{start_marker}\n{end_marker}", 1)
        before, rest = text.split(start_marker, 1)
        current, after = rest.split(end_marker, 1)
        existing = [line for line in current.strip("\n").splitlines() if line] if append else []
        body = "\n".join(existing + lines)
        return before + start_marker + (f"\n{body}\n" if body else "\n") + end_marker + after

    def _ensure_tasks_text(self) -> str:
        path = self.vault / TASKS_PATH
        if path.exists():
            return path.read_text(encoding="utf-8")
        return f"# 📦 任务库存池 (Task Warehouse)\n\n{ONE_TIME_HEADING}\n\n{RECURRING_HEADING}\n"

    def _daily_text(self, day: date) -> str:
        path = self.vault / DAILY_DIR / f"{day.isoformat()}.md"
        if path.exists():
            text = path.read_text(encoding="utf-8")
        else:
            text = (self.vault / TEMPLATE_PATH).read_text(encoding="utf-8")
            text = text.replace("{{date:YYYY-MM-DD}}", day.isoformat())
        return self._normalize_daily(text, day)

    @staticmethod
    def _normalize_daily(text: str, day: date) -> str:
        state = f"<!-- echo-daily:date={day.isoformat()};dispatched=false;recapped=false -->"
        if not DAILY_STATE_RE.search(text) and "---" in text:
            second = text.find("---", text.find("---") + 3)
            text = text[:second + 3] + "\n" + state + text[second + 3:]
        elif not DAILY_STATE_RE.search(text):
            text = state + "\n" + text
        for name in ("tasks", "thino", "reflection"):
            start_marker = f"<!-- echo-{name}:start -->"
            end_marker = f"<!-- echo-{name}:end -->"
            if start_marker not in text or end_marker not in text:
                heading = {"tasks": "## Tasks", "thino": "## Thino", "reflection": "## Reflection"}[name]
                if heading not in text:
                    text = text.rstrip() + f"\n\n{heading}\n"
                text = text.replace(heading, f"{heading}\n{start_marker}\n{end_marker}", 1)
        return text

    @staticmethod
    def _set_state(text: str, *, dispatched: bool | None = None, recapped: bool | None = None) -> str:
        match = DAILY_STATE_RE.search(text)
        if not match:
            raise ValueError("日记缺少 echo-daily 状态")
        d = match.group(2) == "true" if dispatched is None else dispatched
        r = match.group(3) == "true" if recapped is None else recapped
        return DAILY_STATE_RE.sub(
            f"<!-- echo-daily:date={match.group(1)};dispatched={str(d).lower()};recapped={str(r).lower()} -->",
            text, count=1,
        )

    @classmethod
    def _tasks_in_section(cls, text: str, heading: str) -> list[Task]:
        lines = text.splitlines()
        if heading not in lines:
            return []
        start = lines.index(heading) + 1
        end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
        return [task for line in lines[start:end] if (task := cls._parse_task(line))]

    @staticmethod
    def _replace_section_tasks(text: str, heading: str, tasks: list[Task]) -> str:
        lines = text.splitlines()
        if heading not in lines:
            if lines and lines[-1]:
                lines.append("")
            lines.append(heading)
        start = lines.index(heading) + 1
        end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
        rendered = [DailyTaskManager._render_task(task) for task in tasks]
        lines[start:end] = ([""] + rendered + [""]) if rendered else [""]
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _recurs_today(rule: str, day: date) -> bool:
        weekdays = "一二三四五六日"
        rule = rule.replace("、", ",").replace("，", ",").strip()
        if rule == "每天":
            return True
        if rule == "工作日":
            return day.weekday() < 5
        if rule.startswith("每周"):
            selected = rule[2:].replace("周", "").replace(",", "")
            return weekdays[day.weekday()] in selected
        match = re.fullmatch(r"每月(\d{1,2})日", rule)
        return bool(match and day.day == int(match.group(1)))

    @classmethod
    def _normalize_ddl(cls, ddl: Optional[str], today: date) -> str:
        if not ddl:
            return ""
        ddl = ddl.strip()
        if not ddl:
            return ""
        
        time_part = ""
        date_part = ddl
        if " " in ddl:
            date_part, time_part = ddl.split(" ", 1)
        elif "T" in ddl:
            date_part, time_part = ddl.split("T", 1)

        # 凌晨 4 点前生物钟作息：尚未就寝，“明天”代表睡醒后的白天（即当前公历日 today）
        now_hour = datetime.now().astimezone().hour
        is_late_night = now_hour < 4

        norm_date = ""
        if date_part in ("今天", "今日"):
            norm_date = (today - timedelta(days=1)).isoformat() if is_late_night else today.isoformat()
        elif date_part in ("明天", "次日", "明儿"):
            norm_date = today.isoformat() if is_late_night else (today + timedelta(days=1)).isoformat()
        elif date_part in ("后天", "后儿"):
            norm_date = (today + timedelta(days=1)).isoformat() if is_late_night else (today + timedelta(days=2)).isoformat()
        elif date_part == "大后天":
            norm_date = (today + timedelta(days=2)).isoformat() if is_late_night else (today + timedelta(days=3)).isoformat()
        else:
            try:
                norm_date = date.fromisoformat(date_part.replace("/", "-").replace(".", "-")).isoformat()
            except ValueError:
                return ddl

        return f"{norm_date} {time_part.strip()}".strip()

    def ingest_task(self, name: str, ddl: Optional[str] = None, remarks: str = "", is_recurring: bool = False, cycle_rule: str = "") -> str:
        name = name.strip()
        if not name:
            raise ValueError("任务名称不能为空")
        today = self._today(None)
        norm_ddl = self._normalize_ddl(ddl, today)
        if is_recurring and not cycle_rule.strip():
            raise ValueError("循环任务必须提供周期")
        task = Task(self._new_id(), name, "recurring" if is_recurring else "one_time", today.isoformat(), norm_ddl, remarks.strip(), cycle_rule.strip())

        def action() -> None:
            text = self._ensure_tasks_text()
            heading = RECURRING_HEADING if is_recurring else ONE_TIME_HEADING
            tasks = self._tasks_in_section(text, heading)
            tasks.append(task)
            target = self.vault / TASKS_PATH
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self._replace_section_tasks(text, heading, tasks), encoding="utf-8")

        self.git_sync.atomic_transaction(action, f"add task {name}")
        return task.id

    def list_inventory(self) -> dict:
        """Return warehouse tasks without modifying the vault."""
        self.git_sync.pull_latest()
        text = self._ensure_tasks_text()
        one_time = self._tasks_in_section(text, ONE_TIME_HEADING)
        recurring = self._tasks_in_section(text, RECURRING_HEADING)
        return {"one_time": [self._compact_task(task) for task in one_time], "recurring": [self._compact_task(task) for task in recurring]}

    def manage_inventory_task(
        self,
        task_id: Optional[str] = None,
        action: str = "cancel",
        *,
        keyword: Optional[str] = None,
        name: Optional[str] = None,
        ddl: Optional[str] = None,
        remarks: Optional[str] = None,
        cycle_rule: Optional[str] = None,
    ) -> dict:
        """Modify or cancel one warehouse task by its hidden ID or keyword."""
        action = action.strip().lower()
        if action not in {"modify", "cancel"}:
            raise ValueError("action 只能是 modify 或 cancel")
        if ddl:
            ddl = self._normalize_ddl(ddl, self._today(None))
        result: dict = {}

        def write() -> None:
            nonlocal result
            text = self._ensure_tasks_text()
            all_tasks = self._tasks_in_section(text, ONE_TIME_HEADING) + self._tasks_in_section(text, RECURRING_HEADING)
            
            target_id = (task_id or "").strip()
            if not target_id and keyword:
                kw = keyword.strip().lower()
                matches = [t for t in all_tasks if kw in t.name.lower() or kw in t.remarks.lower()]
                if not matches:
                    raise ValueError(f"库存中找不到包含关键词 '{keyword}' 的任务")
                if len(matches) > 1:
                    raise TaskAmbiguityError(matches)
                target_id = matches[0].id
            elif not target_id:
                raise ValueError("必须提供 task_id 或 keyword")

            for heading in (ONE_TIME_HEADING, RECURRING_HEADING):
                tasks = self._tasks_in_section(text, heading)
                target = next((task for task in tasks if task.id == target_id), None)
                if target is None:
                    continue
                if action == "cancel":
                    updated = [task for task in tasks if task.id != target_id]
                    result = {"action": "cancelled", "task": asdict(target)}
                else:
                    new_task = Task(
                        id=target.id,
                        name=name.strip() if name is not None and name.strip() else target.name,
                        type=target.type,
                        created=target.created,
                        ddl=ddl if ddl is not None else target.ddl,
                        remarks=remarks.strip() if remarks is not None else target.remarks,
                        rule=cycle_rule.strip() if cycle_rule is not None else target.rule,
                        completed=target.completed,
                        streak=target.streak,
                    )
                    if new_task.type == "recurring" and not new_task.rule:
                        raise ValueError("循环任务的周期不能为空")
                    updated = [new_task if task.id == target_id else task for task in tasks]
                    result = {"action": "modified", "before": asdict(target), "after": asdict(new_task)}
                text = self._replace_section_tasks(text, heading, updated)
                (self.vault / TASKS_PATH).write_text(text, encoding="utf-8")
                return
            raise ValueError(f"库存中找不到该任务（ID: {target_id}）")

        self.git_sync.atomic_transaction(write, f"{action} inventory task {task_id or keyword}")
        return result

    def morning_dispatch(self, date_str: Optional[str] = None, max_tasks: int = 3) -> dict:
        day = self._today(date_str)
        result: dict = {}

        def action() -> None:
            nonlocal result
            warehouse = self._ensure_tasks_text()
            daily = self._daily_text(day)
            state = DAILY_STATE_RE.search(daily)
            if state and state.group(2) == "true":
                existing = self._managed_tasks(daily)
                result = {"date": day.isoformat(), "tasks": [self._compact_task(t) for t in existing], "already_dispatched": True}
                return
            one_time = self._tasks_in_section(warehouse, ONE_TIME_HEADING)
            recurring = self._tasks_in_section(warehouse, RECURRING_HEADING)

            def urgency(task: Task) -> tuple[int, str, str]:
                if not task.ddl:
                    return (4, "9999-12-31", task.created)
                due_str = task.ddl.split(" ")[0].split("T")[0]
                try:
                    due = date.fromisoformat(due_str)
                    if due <= day:
                        rank = 0
                    elif due == day + timedelta(days=1):
                        rank = 1
                    else:
                        rank = 2
                except ValueError:
                    rank = 3
                return (rank, task.ddl, task.created)

            def is_due_or_overdue(task: Task) -> bool:
                if not task.ddl:
                    return False
                due_str = task.ddl.split(" ")[0].split("T")[0]
                try:
                    return date.fromisoformat(due_str) <= day
                except ValueError:
                    return False

            sorted_tasks = sorted(one_time, key=urgency)
            mandatory = [t for t in sorted_tasks if is_due_or_overdue(t)]
            extras = [t for t in sorted_tasks if t not in mandatory][:max(0, max_tasks - len(mandatory))]
            selected = mandatory + extras
            selected_ids = {task.id for task in selected}
            recurring_today = [task for task in recurring if self._recurs_today(task.rule, day)]
            warehouse = self._replace_section_tasks(warehouse, ONE_TIME_HEADING, [task for task in one_time if task.id not in selected_ids])
            daily = self._replace_managed(daily, "tasks", [self._render_task(task, daily=True) for task in selected + recurring_today])
            daily = self._set_state(daily, dispatched=True)
            tasks_target = self.vault / TASKS_PATH
            daily_target = self.vault / DAILY_DIR / f"{day.isoformat()}.md"
            tasks_target.parent.mkdir(parents=True, exist_ok=True)
            daily_target.parent.mkdir(parents=True, exist_ok=True)
            tasks_target.write_text(warehouse, encoding="utf-8")
            daily_target.write_text(daily, encoding="utf-8")
            result = {
                "date": day.isoformat(), "one_time": [self._compact_task(t) for t in selected],
                "recurring": [self._compact_task(t) for t in recurring_today], "mandatory_count": len(mandatory),
                "already_dispatched": False,
            }

        self.git_sync.atomic_transaction(action, f"dispatch daily tasks {day.isoformat()}")
        return result

    @classmethod
    def _managed_tasks(cls, daily: str) -> list[Task]:
        start, rest = daily.split("<!-- echo-tasks:start -->", 1)
        body = rest.split("<!-- echo-tasks:end -->", 1)[0]
        return [task for line in body.splitlines() if (task := cls._parse_task(line))]

    def toggle_daily_task(self, keyword: str, completed: bool = True, date_str: Optional[str] = None) -> bool:
        day = self._today(date_str)
        changed = False

        def action() -> None:
            nonlocal changed
            path = self.vault / DAILY_DIR / f"{day.isoformat()}.md"
            daily = self._daily_text(day)
            tasks = self._managed_tasks(daily)
            matches = [task for task in tasks if keyword.casefold() in task.name.casefold() or keyword == task.id]
            if len(matches) > 1:
                raise TaskAmbiguityError(matches)
            if not matches:
                return
            target = matches[0]
            updated = [Task(**{**asdict(task), "completed": completed}) if task.id == target.id else task for task in tasks]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self._replace_managed(daily, "tasks", [self._render_task(task, daily=True) for task in updated]), encoding="utf-8")
            changed = target.completed != completed

        self.git_sync.atomic_transaction(action, f"toggle daily task {keyword}")
        return changed

    def append_thino(self, content: str, date_str: Optional[str] = None) -> None:
        day = self._today(date_str)
        content = content.strip()
        if not content:
            raise ValueError("随手记内容不能为空")

        def action() -> None:
            path = self.vault / DAILY_DIR / f"{day.isoformat()}.md"
            daily = self._daily_text(day)
            line = f"- {datetime.now().astimezone().strftime('%H:%M')} {content}"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self._replace_managed(daily, "thino", [line], append=True), encoding="utf-8")

        self.git_sync.atomic_transaction(action, f"append Thino {day.isoformat()}")

    def evening_recap_and_requeue(self, date_str: Optional[str] = None, reflection_text: str = "", progress_notes: Optional[dict[str, str]] = None) -> dict:
        day = self._today(date_str)
        progress_notes = progress_notes or {}
        result: dict = {}

        def action() -> None:
            nonlocal result
            warehouse = self._ensure_tasks_text()
            daily = self._daily_text(day)
            state = DAILY_STATE_RE.search(daily)
            if state and state.group(3) == "true":
                tasks = self._managed_tasks(daily)
                done = sum(task.completed for task in tasks)
                result = {"date": day.isoformat(), "completed": done, "total": len(tasks), "requeued": 0, "completion_rate": done / len(tasks) if tasks else 1.0, "already_recapped": True}
                return
            daily_tasks = self._managed_tasks(daily)
            # 1. Update recurring habits streaks
            recurring_warehouse = self._tasks_in_section(warehouse, RECURRING_HEADING)
            daily_recurring = [t for t in daily_tasks if t.type == "recurring"]
            streak_updates = []
            if daily_recurring and recurring_warehouse:
                updated_recurring = []
                for rh in recurring_warehouse:
                    match_today = next((t for t in daily_recurring if t.id == rh.id or t.name == rh.name), None)
                    if match_today:
                        new_streak = (rh.streak + 1) if match_today.completed else 0
                        updated_task = Task(
                            id=rh.id, name=rh.name, type=rh.type, created=rh.created,
                            ddl=rh.ddl, remarks=rh.remarks, rule=rh.rule,
                            completed=rh.completed, streak=new_streak,
                        )
                        updated_recurring.append(updated_task)
                        streak_updates.append({"name": rh.name, "completed": match_today.completed, "streak": new_streak, "rule": rh.rule})
                    else:
                        updated_recurring.append(rh)
                warehouse = self._replace_section_tasks(warehouse, RECURRING_HEADING, updated_recurring)

            # 2. Requeue unfinished one-time tasks
            unfinished = [task for task in daily_tasks if not task.completed and task.type == "one_time"]
            warehouse_tasks = self._tasks_in_section(warehouse, ONE_TIME_HEADING)
            existing_ids = {task.id for task in warehouse_tasks}
            def progress_for(task: Task) -> str:
                for key, note in progress_notes.items():
                    if key == task.id or key.casefold() in task.name.casefold():
                        return note.strip()
                return ""

            requeued = []
            for task in unfinished:
                if task.id in existing_ids:
                    continue
                progress = progress_for(task)
                remarks = task.remarks
                if progress:
                    remarks = f"{remarks} | 当前进度: {progress}".strip(" |")
                requeued.append(Task(task.id, task.name, "one_time", task.created or day.isoformat(), task.ddl, remarks))
            warehouse = self._replace_section_tasks(warehouse, ONE_TIME_HEADING, warehouse_tasks + requeued)
            if reflection_text.strip():
                daily = self._replace_managed(daily, "reflection", [reflection_text.strip()])
            daily = self._set_state(daily, recapped=True)
            (self.vault / TASKS_PATH).write_text(warehouse, encoding="utf-8")
            (self.vault / DAILY_DIR / f"{day.isoformat()}.md").write_text(daily, encoding="utf-8")
            completed = sum(task.completed for task in daily_tasks)
            result = {
                "date": day.isoformat(), "completed": completed, "total": len(daily_tasks),
                "requeued": len(requeued), "completion_rate": completed / len(daily_tasks) if daily_tasks else 1.0,
                "streak_updates": streak_updates, "already_recapped": False,
            }

        self.git_sync.atomic_transaction(action, f"recap daily tasks {day.isoformat()}")
        return result
