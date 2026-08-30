#!/usr/bin/env bash
set -euo pipefail

# Deploy source-controlled Echo components to the Ubuntu proot instance on the phone.
# QQ state, dynamic memory, knowledge data and Obsidian vault are never overwritten.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ADB="${ADB:-/mnt/c/Users/wenbo/AppData/Local/Android/platform-tools/adb.exe}"
SSH_HOST="${SSH_HOST:-phone-echo}"
TERMUX_PREFIX="/data/data/com.termux/files/usr"
TERMUX_HOME="/data/data/com.termux/files/home"
UBUNTU_ROOT="$TERMUX_PREFIX/var/lib/proot-distro/containers/ubuntu/rootfs"
PHONE_ROOT="$UBUNTU_ROOT/opt/echo"
STAMP="$(date +%Y%m%d-%H%M%S)"

TRANSPORT="ssh"
[[ "${1:-}" == "--usb" ]] && TRANSPORT="usb"

if [[ "${1:-}" == "--help" ]]; then
  cat <<'EOF'
用法：scripts/deploy-phone.sh [--usb]

默认通过 SSH（phone-echo）同步手机端 Echo 插件和 Skill；--usb 仅用于 SSH 不可用时的救援。
会应用仓库定义的非敏感运行配置；不会覆盖动态记忆、知识数据、QQ/NapCat 状态或 Obsidian 笔记。
EOF
  exit 0
fi

deploy_ssh() {
  local remote_tmp="/data/data/com.termux/files/home"
  echo "[1/5] 检查 SSH 与手机 Ubuntu"
  ssh -o BatchMode=yes -o ConnectTimeout=8 "$SSH_HOST" 'command -v proot-distro >/dev/null && proot-distro login ubuntu -- test -d /opt/echo'
  echo "[2/5] 传输源文件"
  scp -q "$ROOT_DIR/astrbot/data/plugins/echo-tools/main.py" "$SSH_HOST:$remote_tmp/echo-tools-main.py"
  scp -q "$ROOT_DIR/astrbot/data/plugins/astrbot_plugin_self_evolution/scheduler/register.py" "$SSH_HOST:$remote_tmp/self-evolution-register.py"
  scp -q "$ROOT_DIR/astrbot/data/plugins/astrbot_plugin_self_evolution/scheduler/tasks.py" "$SSH_HOST:$remote_tmp/self-evolution-tasks.py"
  scp -q "$ROOT_DIR/astrbot/data/plugins/astrbot_plugin_self_evolution/engine/nightly_batch.py" "$SSH_HOST:$remote_tmp/self-evolution-nightly-batch.py"
  scp -q "$ROOT_DIR/astrbot/data/skills/daily-task-manager/SKILL.md" "$SSH_HOST:$remote_tmp/daily-task-SKILL.md"
  scp -q "$ROOT_DIR/mcp-executor/daily_task_manager.py" "$SSH_HOST:$remote_tmp/daily_task_manager.py"
  scp -q "$ROOT_DIR/mcp-executor/obsidian_git.py" "$SSH_HOST:$remote_tmp/obsidian_git.py"
  scp -q "$ROOT_DIR/mcp-executor/obsidian_access.py" "$SSH_HOST:$remote_tmp/obsidian_access.py"
  scp -q "$ROOT_DIR/mcp-executor/obsidian_search.py" "$SSH_HOST:$remote_tmp/obsidian_search.py"
  scp -q "$ROOT_DIR/mcp-executor/obsidian_write.py" "$SSH_HOST:$remote_tmp/obsidian_write.py"
  scp -q "$ROOT_DIR/scripts/memory-daily.sh" "$SSH_HOST:$remote_tmp/memory-daily.sh"
  scp -q "$ROOT_DIR/scripts/memory-daily-loop.sh" "$SSH_HOST:$remote_tmp/memory-daily-loop.sh"
  scp -q "$ROOT_DIR/scripts/memory_manager.py" "$SSH_HOST:$remote_tmp/memory_manager.py"
  scp -q "$ROOT_DIR/scripts/extract_memory_candidates.py" "$SSH_HOST:$remote_tmp/extract_memory_candidates.py"
  scp -q "$ROOT_DIR/scripts/phone-runtime-config.py" "$SSH_HOST:$remote_tmp/phone-runtime-config.py"
  scp -q "$ROOT_DIR/scripts/phone-echo-service.sh" "$SSH_HOST:$remote_tmp/echo-service.new"
  scp -q "$ROOT_DIR/AGENTS.md" "$SSH_HOST:$remote_tmp/AGENTS.md.new"
  echo "[3/5] 备份并安装到 Ubuntu"
  ssh "$SSH_HOST" "mkdir -p '$remote_tmp/echo-memory/scripts'; cp '$remote_tmp/memory-daily.sh' '$remote_tmp/memory-daily-loop.sh' '$remote_tmp/memory_manager.py' '$remote_tmp/extract_memory_candidates.py' '$remote_tmp/echo-memory/scripts/'; cp '$remote_tmp/AGENTS.md.new' '$remote_tmp/echo-memory/AGENTS.md'; chmod 700 '$remote_tmp/echo-memory/scripts/memory-daily.sh' '$remote_tmp/echo-memory/scripts/memory-daily-loop.sh'; cp '$remote_tmp/echo-service' '$remote_tmp/echo-service.before-$STAMP' 2>/dev/null || true; cp '$remote_tmp/echo-service.new' '$remote_tmp/echo-service'; chmod 700 '$remote_tmp/echo-service'; proot-distro login --bind '$TERMUX_HOME:/mnt/termux-home' ubuntu -- /bin/bash -lc 'mkdir -p /opt/echo/.echo-deploy-backups/$STAMP /opt/echo/data/plugins/echo-tools /opt/echo/data/plugins/astrbot_plugin_self_evolution/scheduler /opt/echo/data/plugins/astrbot_plugin_self_evolution/engine /opt/echo/data/skills/daily-task-manager; cp -a /opt/echo/data/plugins/echo-tools/. /opt/echo/.echo-deploy-backups/$STAMP/ 2>/dev/null || true; cp -a /opt/echo/data/plugins/astrbot_plugin_self_evolution/scheduler /opt/echo/.echo-deploy-backups/$STAMP/self-evolution-scheduler 2>/dev/null || true; cp -a /opt/echo/data/plugins/astrbot_plugin_self_evolution/engine/nightly_batch.py /opt/echo/.echo-deploy-backups/$STAMP/self-evolution-nightly-batch.py 2>/dev/null || true; for file in daily_task_manager.py obsidian_git.py obsidian_access.py obsidian_search.py obsidian_write.py; do cp /mnt/termux-home/\$file /opt/echo/data/plugins/echo-tools/\$file; done; cp /mnt/termux-home/echo-tools-main.py /opt/echo/data/plugins/echo-tools/main.py; cp /mnt/termux-home/self-evolution-register.py /opt/echo/data/plugins/astrbot_plugin_self_evolution/scheduler/register.py; cp /mnt/termux-home/self-evolution-tasks.py /opt/echo/data/plugins/astrbot_plugin_self_evolution/scheduler/tasks.py; cp /mnt/termux-home/self-evolution-nightly-batch.py /opt/echo/data/plugins/astrbot_plugin_self_evolution/engine/nightly_batch.py; cp /mnt/termux-home/daily-task-SKILL.md /opt/echo/data/skills/daily-task-manager/SKILL.md; python3 /mnt/termux-home/phone-runtime-config.py'"
  echo "[4/5] 重启手机 Echo 服务"
  ssh "$SSH_HOST" '~/echo-service stop >/dev/null 2>&1 || true; ~/echo-service start'
  echo "[5/5] 验证运行状态"
  ssh "$SSH_HOST" '~/echo-service status; curl -fsS --max-time 5 http://127.0.0.1:6185/ >/dev/null'
  echo "SSH 部署完成"
}

if [[ "$TRANSPORT" == "ssh" ]]; then
  deploy_ssh
  exit $?
fi

command -v "$ADB" >/dev/null 2>&1 || { echo "找不到 adb：$ADB" >&2; exit 1; }
mapfile -t DEVICES < <("$ADB" devices | tr -d '\r' | awk '$2 == "device" {print $1}')
if (( ${#DEVICES[@]} != 1 )); then
  echo "需要恰好一个已授权的 ADB 设备，当前找到 ${#DEVICES[@]} 个" >&2
  "$ADB" devices -l >&2
  exit 1
fi

run_termux() {
  "$ADB" shell run-as com.termux "$@"
}

echo "[1/5] 检查手机 Termux 与 Ubuntu rootfs"
run_termux "$TERMUX_PREFIX/bin/test" -d "$UBUNTU_ROOT/opt/echo"

echo "[2/5] 传输源文件"
"$ADB" push "$ROOT_DIR/astrbot/data/plugins/echo-tools/main.py" /data/local/tmp/echo-tools-main.py >/dev/null
"$ADB" push "$ROOT_DIR/astrbot/data/plugins/astrbot_plugin_self_evolution/scheduler/register.py" /data/local/tmp/self-evolution-register.py >/dev/null
"$ADB" push "$ROOT_DIR/astrbot/data/plugins/astrbot_plugin_self_evolution/scheduler/tasks.py" /data/local/tmp/self-evolution-tasks.py >/dev/null
"$ADB" push "$ROOT_DIR/astrbot/data/plugins/astrbot_plugin_self_evolution/engine/nightly_batch.py" /data/local/tmp/self-evolution-nightly-batch.py >/dev/null
"$ADB" push "$ROOT_DIR/astrbot/data/skills/daily-task-manager/SKILL.md" /data/local/tmp/daily-task-SKILL.md >/dev/null
"$ADB" push "$ROOT_DIR/mcp-executor/daily_task_manager.py" /data/local/tmp/daily_task_manager.py >/dev/null
"$ADB" push "$ROOT_DIR/mcp-executor/obsidian_git.py" /data/local/tmp/obsidian_git.py >/dev/null
"$ADB" push "$ROOT_DIR/mcp-executor/obsidian_access.py" /data/local/tmp/obsidian_access.py >/dev/null
"$ADB" push "$ROOT_DIR/mcp-executor/obsidian_search.py" /data/local/tmp/obsidian_search.py >/dev/null
"$ADB" push "$ROOT_DIR/mcp-executor/obsidian_write.py" /data/local/tmp/obsidian_write.py >/dev/null
"$ADB" push "$ROOT_DIR/scripts/memory-daily.sh" /data/local/tmp/memory-daily.sh >/dev/null
"$ADB" push "$ROOT_DIR/scripts/memory-daily-loop.sh" /data/local/tmp/memory-daily-loop.sh >/dev/null
"$ADB" push "$ROOT_DIR/scripts/memory_manager.py" /data/local/tmp/memory_manager.py >/dev/null
"$ADB" push "$ROOT_DIR/scripts/extract_memory_candidates.py" /data/local/tmp/extract_memory_candidates.py >/dev/null
"$ADB" push "$ROOT_DIR/scripts/phone-runtime-config.py" /data/local/tmp/phone-runtime-config.py >/dev/null
"$ADB" push "$ROOT_DIR/scripts/phone-echo-service.sh" /data/local/tmp/echo-service.new >/dev/null
"$ADB" push "$ROOT_DIR/AGENTS.md" /data/local/tmp/AGENTS.md.new >/dev/null
run_termux "$TERMUX_PREFIX/bin/cp" /data/local/tmp/echo-tools-main.py "$TERMUX_HOME/echo-tools-main.py"
run_termux "$TERMUX_PREFIX/bin/cp" /data/local/tmp/self-evolution-register.py "$TERMUX_HOME/self-evolution-register.py"
run_termux "$TERMUX_PREFIX/bin/cp" /data/local/tmp/self-evolution-tasks.py "$TERMUX_HOME/self-evolution-tasks.py"
run_termux "$TERMUX_PREFIX/bin/cp" /data/local/tmp/self-evolution-nightly-batch.py "$TERMUX_HOME/self-evolution-nightly-batch.py"
run_termux "$TERMUX_PREFIX/bin/cp" /data/local/tmp/daily-task-SKILL.md "$TERMUX_HOME/daily-task-SKILL.md"
run_termux "$TERMUX_PREFIX/bin/cp" /data/local/tmp/daily_task_manager.py "$TERMUX_HOME/daily_task_manager.py"
run_termux "$TERMUX_PREFIX/bin/cp" /data/local/tmp/obsidian_git.py "$TERMUX_HOME/obsidian_git.py"
run_termux "$TERMUX_PREFIX/bin/cp" /data/local/tmp/obsidian_access.py "$TERMUX_HOME/obsidian_access.py"
run_termux "$TERMUX_PREFIX/bin/cp" /data/local/tmp/obsidian_search.py "$TERMUX_HOME/obsidian_search.py"
run_termux "$TERMUX_PREFIX/bin/cp" /data/local/tmp/obsidian_write.py "$TERMUX_HOME/obsidian_write.py"
for file in memory-daily.sh memory-daily-loop.sh memory_manager.py extract_memory_candidates.py phone-runtime-config.py; do
  run_termux "$TERMUX_PREFIX/bin/cp" "/data/local/tmp/$file" "$TERMUX_HOME/$file"
done

echo "[3/5] 备份并安装到 Ubuntu"
run_termux "$TERMUX_PREFIX/bin/mkdir" -p "$PHONE_ROOT/data/plugins/echo-tools" "$PHONE_ROOT/data/plugins/astrbot_plugin_self_evolution/scheduler" "$PHONE_ROOT/data/plugins/astrbot_plugin_self_evolution/engine" "$PHONE_ROOT/data/skills/daily-task-manager" "$PHONE_ROOT/.echo-deploy-backups/$STAMP"
run_termux "$TERMUX_PREFIX/bin/cp" "$PHONE_ROOT/data/plugins/echo-tools/main.py" "$PHONE_ROOT/.echo-deploy-backups/$STAMP/main.py" 2>/dev/null || true
run_termux "$TERMUX_PREFIX/bin/cp" "$PHONE_ROOT/data/skills/daily-task-manager/SKILL.md" "$PHONE_ROOT/.echo-deploy-backups/$STAMP/SKILL.md" 2>/dev/null || true
run_termux "$TERMUX_PREFIX/bin/cp" "$TERMUX_HOME/echo-tools-main.py" "$PHONE_ROOT/data/plugins/echo-tools/main.py"
run_termux "$TERMUX_PREFIX/bin/cp" "$PHONE_ROOT/data/plugins/astrbot_plugin_self_evolution/scheduler/register.py" "$PHONE_ROOT/.echo-deploy-backups/$STAMP/self-evolution-register.py" 2>/dev/null || true
run_termux "$TERMUX_PREFIX/bin/cp" "$PHONE_ROOT/data/plugins/astrbot_plugin_self_evolution/scheduler/tasks.py" "$PHONE_ROOT/.echo-deploy-backups/$STAMP/self-evolution-tasks.py" 2>/dev/null || true
run_termux "$TERMUX_PREFIX/bin/cp" "$PHONE_ROOT/data/plugins/astrbot_plugin_self_evolution/engine/nightly_batch.py" "$PHONE_ROOT/.echo-deploy-backups/$STAMP/self-evolution-nightly-batch.py" 2>/dev/null || true
run_termux "$TERMUX_PREFIX/bin/cp" "$TERMUX_HOME/self-evolution-register.py" "$PHONE_ROOT/data/plugins/astrbot_plugin_self_evolution/scheduler/register.py"
run_termux "$TERMUX_PREFIX/bin/cp" "$TERMUX_HOME/self-evolution-tasks.py" "$PHONE_ROOT/data/plugins/astrbot_plugin_self_evolution/scheduler/tasks.py"
run_termux "$TERMUX_PREFIX/bin/cp" "$TERMUX_HOME/self-evolution-nightly-batch.py" "$PHONE_ROOT/data/plugins/astrbot_plugin_self_evolution/engine/nightly_batch.py"
run_termux "$TERMUX_PREFIX/bin/cp" "$TERMUX_HOME/daily_task_manager.py" "$PHONE_ROOT/data/plugins/echo-tools/daily_task_manager.py"
run_termux "$TERMUX_PREFIX/bin/cp" "$TERMUX_HOME/obsidian_git.py" "$PHONE_ROOT/data/plugins/echo-tools/obsidian_git.py"
run_termux "$TERMUX_PREFIX/bin/cp" "$TERMUX_HOME/obsidian_access.py" "$PHONE_ROOT/data/plugins/echo-tools/obsidian_access.py"
run_termux "$TERMUX_PREFIX/bin/cp" "$TERMUX_HOME/obsidian_search.py" "$PHONE_ROOT/data/plugins/echo-tools/obsidian_search.py"
run_termux "$TERMUX_PREFIX/bin/cp" "$TERMUX_HOME/obsidian_write.py" "$PHONE_ROOT/data/plugins/echo-tools/obsidian_write.py"
run_termux "$TERMUX_PREFIX/bin/cp" "$TERMUX_HOME/daily-task-SKILL.md" "$PHONE_ROOT/data/skills/daily-task-manager/SKILL.md"
run_termux "$TERMUX_PREFIX/bin/mkdir" -p "$TERMUX_HOME/echo-memory/scripts"
for file in memory-daily.sh memory-daily-loop.sh memory_manager.py extract_memory_candidates.py; do
  run_termux "$TERMUX_PREFIX/bin/cp" "$TERMUX_HOME/$file" "$TERMUX_HOME/echo-memory/scripts/$file"
done
run_termux "$TERMUX_PREFIX/bin/chmod" 700 "$TERMUX_HOME/echo-memory/scripts/memory-daily.sh" "$TERMUX_HOME/echo-memory/scripts/memory-daily-loop.sh"
run_termux "$TERMUX_PREFIX/bin/cp" /data/local/tmp/AGENTS.md.new "$TERMUX_HOME/echo-memory/AGENTS.md"
run_termux "$TERMUX_PREFIX/bin/cp" "$TERMUX_HOME/echo-service" "$TERMUX_HOME/echo-service.before-$STAMP" 2>/dev/null || true
run_termux "$TERMUX_PREFIX/bin/cp" /data/local/tmp/echo-service.new "$TERMUX_HOME/echo-service"
run_termux "$TERMUX_PREFIX/bin/chmod" 700 "$TERMUX_HOME/echo-service"
run_termux "$TERMUX_PREFIX/bin/env" PATH="$TERMUX_PREFIX/bin" HOME="$TERMUX_HOME" PREFIX="$TERMUX_PREFIX" "$TERMUX_PREFIX/bin/proot-distro" login --bind "$TERMUX_HOME:/mnt/termux-home" ubuntu -- /usr/bin/python3 /mnt/termux-home/phone-runtime-config.py

echo "[4/5] 重启手机 Echo 服务"
run_termux "$TERMUX_HOME/echo-service" stop >/dev/null || true
run_termux "$TERMUX_HOME/echo-service" start

echo "[5/5] 验证运行状态"
run_termux "$TERMUX_HOME/echo-service" status
if ! run_termux "$TERMUX_PREFIX/bin/curl" -fsS --max-time 5 http://127.0.0.1:6185/ >/dev/null; then
  echo "AstrBot HTTP 探针失败，查看日志：adb shell run-as com.termux $TERMUX_HOME/echo-service logs" >&2
  exit 1
fi
echo "部署完成；手机旧文件备份位于 $PHONE_ROOT/.echo-deploy-backups/$STAMP"
