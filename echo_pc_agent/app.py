import sys
import os

# 确保当前目录在 sys.path 中
agent_dir = os.path.dirname(os.path.abspath(__file__))
if agent_dir not in sys.path:
    sys.path.insert(0, agent_dir)

from server import AgentServer
from tray import TrayApp

def main():
    print("========================================")
    print("   Echo PC Agent - 智能桌面感知代理     ")
    print("========================================")

    server = AgentServer(host="0.0.0.0", port=8766)
    server.start()

    def on_exit():
        print("[App] Shutting down...")
        server.stop()

    tray = TrayApp(on_exit_callback=on_exit)
    try:
        tray.run()
    except KeyboardInterrupt:
        on_exit()

if __name__ == "__main__":
    main()
