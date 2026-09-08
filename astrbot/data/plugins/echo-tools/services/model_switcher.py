"""大模型动态列表展示与运行时热切换服务 (ModelSwitcher)。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.compat import AstrMessageEvent, Context, logger

from core.config import PluginConfig


class ModelSwitcher:
    """管理 /模型 指令的解析、菜单呈现与 Provider 实例热切换。"""

    # Go 计划实测 100% 可用、零边际成本的专属大模型目录（27款）
    GO_MODELS = [
        "deepseek/deepseek-v4-pro",
        "deepseek/deepseek-v4-flash",
        "deepseek/deepseek-v4-flash-vision-exp",
        "moonshotai/Kimi-K2.7-Code",
        "moonshotai/Kimi-K2.7-Code-Highspeed",
        "moonshotai/Kimi-K2.6",
        "moonshotai/Kimi-K2.5",
        "z-ai/glm-5.3-flash",
        "zai-org/GLM-5.3",
        "zai-org/GLM-5.2",
        "zai-org/GLM-5.2-Fast",
        "zai-org/GLM-5.1",
        "MiniMaxAI/MiniMax-M3",
        "minimax/minimax-m3-free",
        "minimax/minimax-m2.7-free",
        "MiniMaxAI/MiniMax-M2.5",
        "xiaomi/mimo-v2.5-pro",
        "xiaomi/mimo-v2.5",
        "Qwen/Qwen3.8-Max",
        "Qwen/Qwen3.8-27B",
        "Qwen/Qwen3.8-Flash",
        "Qwen/Qwen3.7-Max",
        "Qwen/Qwen3.7-Plus",
        "Qwen/Qwen3.7-Flash",
        "Qwen/Qwen3.6-Max-Preview",
        "Qwen/Qwen3.6-Plus",
        "stepfun/Step-3.5-Flash",
    ]

    def __init__(self, context: Context, config: PluginConfig) -> None:
        self.context = context
        self.config = config

    def handle_command(self, event: AstrMessageEvent) -> str:
        """处理 /模型 指令请求。"""
        sender_id = str(event.get_sender_id() or "")
        owner_ids = self.config.get_owner_ids()
        if owner_ids and sender_id not in owner_ids:
            return "🔒 权限受限：只有 Owner 可以查询与切换大模型。"

        parts = str(getattr(event, "message_str", "") or "").split(maxsplit=1)
        query = parts[1].strip() if len(parts) > 1 else ""

        try:
            cfg_file = self.config.find_data_file("cmd_config.json")
            cfg_data = json.loads(cfg_file.read_text(encoding="utf-8"))
        except Exception as exc:
            return f"❌ 读取配置文件失败: {exc}"

        providers = cfg_data.get("provider", [])
        cc_provider = next(
            (p for p in providers if p.get("id") == "commandcode_deepseek_v4_flash"),
            None,
        )
        if not cc_provider and providers:
            cc_provider = providers[0]
        current_model = cc_provider.get("model", "") if cc_provider else ""

        models_list = self.GO_MODELS

        # 1. 呈现菜单
        if not query or query in {"列表", "list", "help", "帮助"}:
            lines = [f"🤖 Go 计划当前可用大模型列表 (共 {len(models_list)} 个)：\n"]
            for idx, m_id in enumerate(models_list, 1):
                is_curr = " (当前使用 🌟)" if m_id == current_model else ""
                lines.append(f"[{idx}] {m_id}{is_curr}")
            lines.append(
                "\n💡 切换方法：\n• 回复「/模型 序号」（如 /模型 1）\n• 回复「/模型 模型名」（如 /模型 glm-5.3-flash）"
            )
            return "\n".join(lines)

        # 2. 匹配目标模型
        target_model = None
        if query.isdigit():
            idx = int(query)
            if 1 <= idx <= len(models_list):
                target_model = models_list[idx - 1]
            else:
                return f"❌ 序号超出范围：请输入 1 ~ {len(models_list)} 之间的数字。"
        else:
            q_lower = query.lower()
            for m_id in models_list:
                if m_id.lower() == q_lower:
                    target_model = m_id
                    break
            if not target_model:
                for m_id in models_list:
                    if q_lower in m_id.lower():
                        target_model = m_id
                        break

        if not target_model:
            return f"❌ 未找到匹配的模型「{query}」，请发送 /模型 查看最新的可用模型列表。"

        # 3. 持久化到配置文件
        if cc_provider:
            cc_provider["model"] = target_model
        cfg_file.write_text(json.dumps(cfg_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        # 4. 实时热重载内存中的 Provider 实例
        switched_in_memory = False
        try:
            pm = getattr(self.context, "provider_manager", None)
            if pm:
                for p_cfg in getattr(pm, "providers_config", []):
                    target_id = cc_provider.get("id") if cc_provider else "commandcode_deepseek_v4_flash"
                    if p_cfg.get("id") == target_id:
                        p_cfg["model"] = target_model
                inst = pm.inst_map.get(cc_provider.get("id") if cc_provider else "commandcode_deepseek_v4_flash")
                if inst and hasattr(inst, "set_model"):
                    inst.set_model(target_model)
                    switched_in_memory = True
                elif inst:
                    setattr(inst, "model", target_model)
                    if hasattr(inst, "provider_config") and isinstance(inst.provider_config, dict):
                        inst.provider_config["model"] = target_model
                    switched_in_memory = True
        except Exception as exc:
            logger.warning(f"[ModelSwitcher] 实时热重载 Provider 实例异常: {exc}")

        status_tip = "🚀 即刻生效，无需重启！" if switched_in_memory else "💾 配置已持久化保存！"
        return f"✨ 主力大模型已实时切换为：\n📌 {target_model}\n{status_tip}"
