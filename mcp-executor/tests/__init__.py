import sys
from pathlib import Path

_ECHO_TOOLS_DIR = Path(__file__).resolve().parent.parent.parent / "astrbot" / "data" / "plugins" / "echo-tools"
_ECHO_OBSIDIAN_DIR = _ECHO_TOOLS_DIR / "obsidian"

if str(_ECHO_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_ECHO_TOOLS_DIR))
if str(_ECHO_OBSIDIAN_DIR) not in sys.path:
    sys.path.insert(0, str(_ECHO_OBSIDIAN_DIR))
