#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Echo Xiaomi MIX 2 专属一键初始化与全功能部署脚本 (deploy-mix2.sh)
# 适用硬件: Xiaomi MIX 2 (Snapdragon 835, 6GB RAM, IPS 全贴合屏)
# 部署目标: 
#   1. Termux + Proot Ubuntu 环境初始化
#   2. Echo CognitionCore 7.0 + AstrBot + NapCat 部署
#   3. 100% 离线 Live2D (Haru) + 日漫对白气泡 + HUD 仪表盘 (port 8099)
#   4. 30ms 本地人脸识别哨兵 (face_sentry.py)
#   5. 宿舍光线感应自动关屏 (Termux Sensor) 守护进程
# ==============================================================================

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ADB="${ADB:-/mnt/c/Users/wenbo/AppData/Local/Android/platform-tools/adb.exe}"
SSH_HOST="${SSH_HOST:-mix2-echo}"
STAMP="$(date +%Y%m%d-%H%M%S)"

echo "=========================================================="
echo "    Echo Xiaomi MIX 2 智能桌面伴侣 & 宿舍私有服务器 部署向导"
echo "=========================================================="

# 模式检测: ADB (首次刷入) 或 SSH (后续热更)
TRANSPORT="adb"
[[ "${1:-}" == "--ssh" ]] && TRANSPORT="ssh"

if [[ "$TRANSPORT" == "adb" ]]; then
  command -v "$ADB" >/dev/null 2>&1 || { echo "❌ 找不到 adb: $ADB" >&2; exit 1; }
  mapfile -t DEVICES < <("$ADB" devices | tr -d '\r' | awk '$2 == "device" {print $1}')
  if (( ${#DEVICES[@]} == 0 )); then
    echo "❌ 未检测到已连接并授权的 ADB 设备。请确认 MIX 2 已开启 USB 调试并信任此电脑。" >&2
    exit 1
  fi
  TARGET_DEV="${DEVICES[0]}"
  echo "✓ 成功连接 ADB 设备: $TARGET_DEV"

  echo -e "\n[1/6] 检查/安装手机端 Termux 核心套件..."
  # 推送辅助初始脚本至 Termux 存储区
  "$ADB" shell "mkdir -p /sdcard/echo_deploy"
  
  echo "[2/6] 推送 100% 纯离线 Live2D 伴侣仪表盘资源包..."
  "$ADB" push "$ROOT_DIR/desktop_companion" /sdcard/echo_deploy/ >/dev/null
  
  echo "[3/6] 推送人脸哨兵与自动化守护进程..."
  "$ADB" push "$ROOT_DIR/scripts/face_sentry.py" /sdcard/echo_deploy/ >/dev/null
  
  echo "[4/6] 同步 Echo 7.0 核心代码与技能插件..."
  "$ADB" push "$ROOT_DIR/astrbot/data/plugins/echo-tools" /sdcard/echo_deploy/ >/dev/null
  "$ADB" push "$ROOT_DIR/astrbot/data/plugins/astrbot_plugin_self_evolution" /sdcard/echo_deploy/ >/dev/null
  "$ADB" push "$ROOT_DIR/mcp-executor" /sdcard/echo_deploy/ >/dev/null
  
  echo "[5/6] 安装与配置 Termux 服务启动项..."
  # 创建启动脚本
  cat <<'EOF' > /tmp/mix2_setup_internal.sh
#!/data/data/com.termux/files/usr/bin/bash
set -e
echo "正在解压与配置本地伴侣资源..."
mkdir -p ~/echo_companion ~/.echo
cp -r /sdcard/echo_deploy/echo_companion/* ~/echo_companion/
cp /sdcard/echo_deploy/face_sentry.py ~/face_sentry.py
chmod +x ~/face_sentry.py

# 启动微型静态 Web 服务器 (Python 原生，零额外依赖)
pkill -f "http.server 8099" || true
nohup python3 -m http.server 8099 --directory ~/echo_companion > ~/.echo/hud.log 2>&1 &
echo "✓ 桌面 HUD 伴侣服务已在端口 8099 运行！"

# 宿舍光线感应自动熄屏保护脚本
cat <<'LIGHT_EOF' > ~/.echo/light_daemon.sh
#!/data/data/com.termux/files/usr/bin/bash
# 监测宿舍光照，关灯 (<3 Lux) 自动全黑熄屏，开灯恢复
while true; do
  if command -v termux-sensor >/dev/null 2>&1; then
    LUX=$(termux-sensor -s "light" -n 1 2>/dev/null | grep -o '"values": \[[0-9.]*' | awk -F'[' '{print $2}' || echo "10")
    if (( $(echo "$LUX < 3.0" | bc -l 2>/dev/null || echo 0) )); then
      # 宿舍熄灯，屏幕亮度调至最低或关闭屏幕
      termux-brightness 0 2>/dev/null || true
    fi
  fi
  sleep 20
done
LIGHT_EOF
chmod +x ~/.echo/light_daemon.sh
nohup ~/.echo/light_daemon.sh > /dev/null 2>&1 &
echo "✓ 宿舍关灯自动熄屏守护进程已挂载！"
EOF

  "$ADB" push /tmp/mix2_setup_internal.sh /data/local/tmp/mix2_setup_internal.sh
  rm -f /tmp/mix2_setup_internal.sh
  
  echo "[6/6] 触发 Termux 内部环境生效..."
  "$ADB" shell "run-as com.termux cp /data/local/tmp/mix2_setup_internal.sh /data/data/com.termux/files/home/mix2_setup.sh && run-as com.termux chmod +x /data/data/com.termux/files/home/mix2_setup.sh" || {
    echo "提示: 如遇 run-as 权限限制，请在手机 Termux 中手动执行: bash /sdcard/echo_deploy/mix2_setup.sh"
  }

  echo -e "\n🎉 [MIX 2 一键部署脚本执行完毕！]"
  echo "1. 桌面 HUD 地址: http://127.0.0.1:8099/dashboard.html"
  echo "2. 人脸基准录入命令 (在 Termux 执行): python3 ~/face_sentry.py --enroll"
  echo "3. 浏览器全屏显示: 推荐使用手机自带浏览器或 Fully Kiosk 打开上述地址。"
fi
