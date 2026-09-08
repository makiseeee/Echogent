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
  echo "[1/4] 检查 SSH 与手机 Ubuntu 环境"
  ssh -o BatchMode=yes -o ConnectTimeout=8 "$SSH_HOST" 'command -v proot-distro >/dev/null && proot-distro login ubuntu -- test -d /opt/echo'

  echo "[2/4] 打包并流式同步 echo-tools 微模块及配套组件"
  # 排除数据库、备份与 pycache，通过单个 tar 流极速解包至目标目录
  tar -C "$ROOT_DIR/astrbot/data/plugins/echo-tools" --exclude="*.db" --exclude="*.bak" --exclude="__pycache__" -czf - . | \
    ssh "$SSH_HOST" 'proot-distro login ubuntu -- tar -xzf - -C /opt/echo/data/plugins/echo-tools'

  scp -q "$ROOT_DIR/astrbot/data/plugins/astrbot_plugin_self_evolution/scheduler/register.py" "$SSH_HOST:$remote_tmp/self-evolution-register.py"
  scp -q "$ROOT_DIR/astrbot/data/plugins/astrbot_plugin_self_evolution/scheduler/tasks.py" "$SSH_HOST:$remote_tmp/self-evolution-tasks.py"
  scp -q "$ROOT_DIR/astrbot/data/plugins/astrbot_plugin_self_evolution/engine/nightly_batch.py" "$SSH_HOST:$remote_tmp/self-evolution-nightly-batch.py"
  scp -q "$ROOT_DIR/astrbot/data/skills/daily-task-manager/SKILL.md" "$SSH_HOST:$remote_tmp/daily-task-SKILL.md"
  scp -q "$ROOT_DIR/scripts/phone-echo-service.sh" "$SSH_HOST:$remote_tmp/echo-service.new"

  echo "[3/4] 更新自进化与守护脚本"
  ssh "$SSH_HOST" "
    cp '$remote_tmp/echo-service.new' '$remote_tmp/echo-service' 2>/dev/null || true
    chmod 700 '$remote_tmp/echo-service'
    proot-distro login --bind '$TERMUX_HOME:/mnt/termux-home' ubuntu -- /bin/bash -lc '
      cp /mnt/termux-home/self-evolution-register.py /opt/echo/data/plugins/astrbot_plugin_self_evolution/scheduler/register.py
      cp /mnt/termux-home/self-evolution-tasks.py /opt/echo/data/plugins/astrbot_plugin_self_evolution/scheduler/tasks.py
      cp /mnt/termux-home/self-evolution-nightly-batch.py /opt/echo/data/plugins/astrbot_plugin_self_evolution/engine/nightly_batch.py
      cp /mnt/termux-home/daily-task-SKILL.md /opt/echo/data/skills/daily-task-manager/SKILL.md
    '
  "

  echo "[4/4] 轻量重启 echo 守护会话 (不触碰 NapCat/QQ)"
  ssh "$SSH_HOST" '
    tmux send-keys -t echo C-c 2>/dev/null || true
    sleep 3
    tmux kill-session -t echo 2>/dev/null || true
    proot-distro login ubuntu -- rm -f /opt/echo/astrbot.lock

    SECRETS_FILE="$HOME/.echo-secrets"
    [ -r "$SECRETS_FILE" ] && . "$SECRETS_FILE"
    PROOT="/data/data/com.termux/files/usr/bin/proot-distro"
    COMMAND=(
      "$PROOT" login
      --bind "$HOME:/mnt/termux-home"
      --work-dir /opt/echo
      ubuntu --
      /usr/bin/env TZ=Asia/Shanghai PYTHONUNBUFFERED=1
      "ECHO_HAJIMI_API_KEY=${ECHO_HAJIMI_API_KEY:-}"
      "ECHO_SILICONFLOW_API_KEY=${ECHO_SILICONFLOW_API_KEY:-}"
      "ECHO_STT_MODEL=${ECHO_STT_MODEL:-FunAudioLLM/SenseVoiceSmall}"
      /opt/echo-astrbot/bin/astrbot run
    )
    printf -v cmd "%q " "${COMMAND[@]}"
    tmux new-session -d -s echo "$cmd"

    echo "等待 AstrBot 绑定 6185 端口..."
    for i in $(seq 1 60); do
      if curl -fsS --max-time 2 http://127.0.0.1:6185/ >/dev/null 2>&1; then
        echo "AstrBot 已就绪 (${i}x2s)"
        exit 0
      fi
      sleep 2
    done
    echo "警告：AstrBot 启动超时，请检查 tmux 日志" >&2
    exit 1
  '
  echo "部署验证完成"
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
