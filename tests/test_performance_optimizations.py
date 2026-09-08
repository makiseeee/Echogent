import asyncio
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

plugin_path = Path("/home/wenbo/aaage/astrbot/data/plugins/echo-tools")
if str(plugin_path) not in sys.path:
    sys.path.insert(0, str(plugin_path))

from core.config import PluginConfig
from core.http_client import HttpClient
from obsidian.obsidian_access import AccessMode, VaultAccessPolicy
from obsidian.obsidian_git import VaultGitSync
from obsidian.obsidian_search import clear_search_cache, read_note_excerpt, search_vault


class TestPerformanceOptimizations(unittest.IsolatedAsyncioTestCase):
    async def test_http_client_singleton_and_close(self):
        """测试全局 HttpClient 连接池复用与安全关闭。"""
        session1 = await HttpClient.get_session()
        session2 = await HttpClient.get_session()
        self.assertIs(session1, session2)
        self.assertFalse(session1.closed)

        await HttpClient.close()
        self.assertTrue(session1.closed)

        # 再次获取时自动重新建立
        session3 = await HttpClient.get_session()
        self.assertIsNot(session1, session3)
        self.assertFalse(session3.closed)
        await HttpClient.close()
        self.assertTrue(session3.closed)

    def test_config_owner_ids_mtime_cache(self):
        """测试 PluginConfig.get_owner_ids 的 mtime 缓存与修改即时感知。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            cfg_file = data_dir / "cmd_config.json"
            cfg_file.write_text(json.dumps({"admins_id": ["12345", "67890"]}), encoding="utf-8")

            config = PluginConfig(data_root=data_dir)
            admins1 = config.get_owner_ids()
            self.assertEqual(admins1, {"12345", "67890"})

            # 第二次调用命中 mtime 缓存，返回相同 set 对象
            admins2 = config.get_owner_ids()
            self.assertIs(admins1, admins2)

            # 更新配置文件并推进 mtime
            time.sleep(0.05)
            cfg_file.write_text(json.dumps({"admins_id": ["12345", "99999"]}), encoding="utf-8")
            # 确保 mtime 更新
            stat = cfg_file.stat()

            admins3 = config.get_owner_ids()
            self.assertEqual(admins3, {"12345", "99999"})
            self.assertIsNot(admins1, admins3)

    def test_obsidian_search_mtime_cache(self):
        """测试 search_vault 与 read_note_excerpt 的内存缓存与即时刷新。"""
        clear_search_cache()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            projects_dir = root / "1. Projects"
            projects_dir.mkdir(parents=True)
            note_file = projects_dir / "demo.md"
            note_file.write_text("# 架构设计\n高性能微模块分层设计", encoding="utf-8")

            policy = VaultAccessPolicy(root)
            results = search_vault(policy, "微模块")
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].title, "架构设计")

            # 修改文件内容
            time.sleep(0.05)
            note_file.write_text("# 架构重构2.0\n全面启用连接池复用", encoding="utf-8")

            # 自动感知修改并返回最新内容
            results2 = search_vault(policy, "连接池")
            self.assertEqual(len(results2), 1)
            self.assertEqual(results2[0].title, "架构重构2.0")
            self.assertIn("连接池", results2[0].context)

            # 旧关键词不应命中
            results_old = search_vault(policy, "微模块")
            self.assertEqual(len(results_old), 0)

            # read_note_excerpt 同样复用最新缓存
            excerpt = read_note_excerpt(policy, "1. Projects/demo.md")
            self.assertEqual(excerpt.title, "架构重构2.0")
            self.assertIn("全面启用连接池复用", excerpt.context)

    def test_obsidian_git_pull_if_stale(self):
        """测试 VaultGitSync.pull_if_stale 频率节流防抖。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "EchoTest"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "echo@test.local"], cwd=repo, check=True, capture_output=True)
            (repo / "init.txt").write_text("hello", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

            sync = VaultGitSync(vault=repo)
            # 设置最近一次 pull 发生在 5 秒前
            sync._last_pull_time = time.time() - 5.0

            # max_age_sec=30.0 时未过期，直接返回成功，不执行真实网络/子进程操作
            res = sync.pull_if_stale(max_age_sec=30.0)
            self.assertTrue(res.success)
            self.assertEqual(res.pull_warning, "")

            # 强制设置 _last_pull_time 发生在 40 秒前（已过期）
            sync._last_pull_time = time.time() - 40.0
            # 此时会触发 git pull，因为没有 remote，_pull_unlocked 会优雅返回 warning
            res_stale = sync.pull_if_stale(max_age_sec=30.0)
            # 离线回退保护：失败时记录 warning
            self.assertFalse(res_stale.success)
            self.assertTrue(len(res_stale.pull_warning) > 0)


if __name__ == "__main__":
    unittest.main()
