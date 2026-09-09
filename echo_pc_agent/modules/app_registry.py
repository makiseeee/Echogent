import os
import json
import sqlite3
import threading
from typing import Dict, List, Any, Optional

class AppRegistry:
    """
    Echo PC Agent 分层应用分类与权限注册中心
    1. 底盘：software_taxonomy.json（出厂预设，随代码库 Git 维护）
    2. 覆盖层：app_overrides.db（本地 SQLite 数据库，持久化用户自定义配置与本地动态发现）
    3. 运行时：内存字典缓存，提供 O(1) 纳秒级进程查询
    """
    def __init__(self, data_dir: Optional[str] = None, db_path: Optional[str] = None):
        if data_dir is None:
            # 默认位于 echo_pc_agent/data 目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            agent_root = os.path.dirname(current_dir)
            data_dir = os.path.join(agent_root, "data")
        
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.json_path = os.path.join(self.data_dir, "software_taxonomy.json")

        if db_path is not None:
            self.db_path = db_path
        else:
            # Windows 下 UNC 路径 (\\wsl.localhost\...) 会导致 SQLite 文件锁异常
            # 统一将本地用户覆盖库持久化至本地 NTFS 目录 ~/.echo/app_overrides.db
            echo_home = os.path.expanduser("~/.echo")
            os.makedirs(echo_home, exist_ok=True)
            self.db_path = os.path.join(echo_home, "app_overrides.db")
        
        self._lock = threading.Lock()
        self._cache: Dict[str, Dict[str, Any]] = {}
        
        self._init_db()
        self.reload()

    def _get_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._lock:
            with self._get_db() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS app_registry (
                        exe_name        TEXT PRIMARY KEY,
                        app_name        TEXT NOT NULL,
                        category        TEXT NOT NULL,
                        subcategory     TEXT NOT NULL,
                        visual_safe     INTEGER DEFAULT 1,
                        dnd_inhibit     INTEGER DEFAULT 0,
                        custom_summary  TEXT,
                        is_user_defined INTEGER DEFAULT 0,
                        updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()

    def reload(self):
        """重新合流预设 JSON 与 SQLite 覆盖项至内存缓存"""
        new_cache: Dict[str, Dict[str, Any]] = {}

        # 1. 加载只读预设 JSON
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    categories = data.get("categories", {})
                    for cat_key, cat_val in categories.items():
                        subcategories = cat_val.get("subcategories", {})
                        for sub_key, sub_val in subcategories.items():
                            default_visual_safe = sub_val.get("visual_safe", True)
                            default_dnd_inhibit = sub_val.get("dnd_inhibit", False)
                            default_summary = sub_val.get("default_summary", "")

                            for app in sub_val.get("apps", []):
                                exe = app.get("exe", "").strip().lower()
                                if not exe:
                                    continue
                                new_cache[exe] = {
                                    "exe_name": exe,
                                    "app_name": app.get("name", exe),
                                    "category": cat_key,
                                    "subcategory": sub_key,
                                    "visual_safe": bool(app.get("visual_safe", default_visual_safe)),
                                    "dnd_inhibit": bool(app.get("dnd_inhibit", default_dnd_inhibit)),
                                    "custom_summary": app.get("custom_summary", default_summary),
                                    "is_user_defined": False,
                                    "tags": app.get("tags", []),
                                }
            except Exception as e:
                print(f"[AppRegistry] Error loading {self.json_path}: {e}")

        # 2. 加载本地 SQLite 覆盖项 (优先级最高)
        try:
            with self._get_db() as conn:
                cursor = conn.execute("""
                    SELECT exe_name, app_name, category, subcategory, visual_safe, dnd_inhibit, custom_summary, is_user_defined
                    FROM app_registry
                """)
                for row in cursor.fetchall():
                    exe = row["exe_name"].strip().lower()
                    existing = new_cache.get(exe, {})
                    new_cache[exe] = {
                        "exe_name": exe,
                        "app_name": row["app_name"],
                        "category": row["category"],
                        "subcategory": row["subcategory"],
                        "visual_safe": bool(row["visual_safe"]),
                        "dnd_inhibit": bool(row["dnd_inhibit"]),
                        "custom_summary": row["custom_summary"] or existing.get("custom_summary", ""),
                        "is_user_defined": bool(row["is_user_defined"]),
                        "tags": existing.get("tags", []),
                    }
        except Exception as e:
            print(f"[AppRegistry] Error loading SQLite overrides: {e}")

        with self._lock:
            self._cache = new_cache

    def get(self, exe_name: str) -> Optional[Dict[str, Any]]:
        """O(1) 内存查询应用配置"""
        if not exe_name:
            return None
        return self._cache.get(exe_name.strip().lower())

    def list_apps(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取所有已登记软件列表"""
        with self._lock:
            apps = list(self._cache.values())
        if category:
            apps = [a for a in apps if a.get("category") == category]
        return sorted(apps, key=lambda x: (x.get("category", ""), x.get("app_name", "").lower()))

    def update_app(self, exe_name: str, updates: Dict[str, Any]) -> bool:
        """更新某个应用的权限或属性，并持久化到 SQLite"""
        exe = exe_name.strip().lower()
        if not exe:
            return False

        with self._lock:
            current = self._cache.get(exe, {
                "exe_name": exe,
                "app_name": updates.get("app_name", exe),
                "category": updates.get("category", "other"),
                "subcategory": updates.get("subcategory", "generic"),
                "visual_safe": True,
                "dnd_inhibit": False,
                "custom_summary": "",
                "is_user_defined": True,
            })

            # 合并修改项
            app_name = updates.get("app_name", current.get("app_name", exe))
            category = updates.get("category", current.get("category", "other"))
            subcategory = updates.get("subcategory", current.get("subcategory", "generic"))
            visual_safe = 1 if updates.get("visual_safe", current.get("visual_safe", True)) else 0
            dnd_inhibit = 1 if updates.get("dnd_inhibit", current.get("dnd_inhibit", False)) else 0
            custom_summary = updates.get("custom_summary", current.get("custom_summary", ""))

            with self._get_db() as conn:
                conn.execute("""
                    INSERT INTO app_registry (exe_name, app_name, category, subcategory, visual_safe, dnd_inhibit, custom_summary, is_user_defined, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
                    ON CONFLICT(exe_name) DO UPDATE SET
                        app_name = excluded.app_name,
                        category = excluded.category,
                        subcategory = excluded.subcategory,
                        visual_safe = excluded.visual_safe,
                        dnd_inhibit = excluded.dnd_inhibit,
                        custom_summary = excluded.custom_summary,
                        is_user_defined = 1,
                        updated_at = CURRENT_TIMESTAMP
                """, (exe, app_name, category, subcategory, visual_safe, dnd_inhibit, custom_summary))
                conn.commit()

            # 热更新内存缓存
            self._cache[exe] = {
                "exe_name": exe,
                "app_name": app_name,
                "category": category,
                "subcategory": subcategory,
                "visual_safe": bool(visual_safe),
                "dnd_inhibit": bool(dnd_inhibit),
                "custom_summary": custom_summary,
                "is_user_defined": True,
                "tags": current.get("tags", []),
            }

        return True

    def register_unseen(self, exe_name: str, window_title: str) -> None:
        """记录前台偶发未见的新进程为待分类"""
        exe = exe_name.strip().lower()
        if not exe or exe in self._cache:
            return
        
        # 忽略系统核心进程
        if exe in ["explorer.exe", "shellexperiencehost.exe", "searchapp.exe", "taskhostw.exe", "dwm.exe"]:
            return

        with self._lock:
            if exe in self._cache:
                return
            
            clean_title = window_title[:40].strip() if window_title else exe
            with self._get_db() as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO app_registry (exe_name, app_name, category, subcategory, visual_safe, dnd_inhibit, custom_summary, is_user_defined)
                    VALUES (?, ?, 'other', 'unseen', 1, 0, '', 0)
                """, (exe, clean_title))
                conn.commit()

            self._cache[exe] = {
                "exe_name": exe,
                "app_name": clean_title,
                "category": "other",
                "subcategory": "unseen",
                "visual_safe": True,
                "dnd_inhibit": False,
                "custom_summary": "",
                "is_user_defined": False,
                "tags": ["auto_detected"],
            }

# 全局单例
registry = AppRegistry()
