# Changelog

All notable changes to Echogent are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Conventional Commits](https://www.conventionalcommits.org/).

---

## [7.0.0] - 2026-08

### 重大变更 / Major Changes

- **refactor(echo-tools)**: 彻底解构 1,951 行单体 God Class，拆解为 `core/` · `sentries/` · `services/` · `obsidian/` 四层微模块架构 ([`7dc029c`](https://github.com/makiseeee/Echogent/commit/7dc029c))
- **docs**: 全面重写 README、架构文档、能力矩阵、运维手册、安全规范与演进路线图 ([`2ac0a3e`](https://github.com/makiseeee/Echogent/commit/2ac0a3e))

### 新功能 / Features

- **feat(security)**: SafeCalculator 增加指数 ≤ 1000 与阶乘 ≤ 100 双重规模熔断，防御 BigInt DoS ([`dc642cb`](https://github.com/makiseeee/Echogent/commit/dc642cb))
- **feat(security)**: WebFetcher 引入递归 IP 解析与私网/回环地址深度拦截，防御 SSRF ([`dc642cb`](https://github.com/makiseeee/Echogent/commit/dc642cb))
- **feat(pc_agent)**: PC Agent 认证加固与部署流优化 ([`dc642cb`](https://github.com/makiseeee/Echogent/commit/dc642cb))

### 性能优化 / Performance

- **perf(echo-tools)**: 实现共享 HTTP Client、Obsidian Git 防抖与 mtime 缓存 ([`f4de694`](https://github.com/makiseeee/Echogent/commit/f4de694))
- **perf(echo-tools)**: 异步 I/O 全面升级 ([`dc642cb`](https://github.com/makiseeee/Echogent/commit/dc642cb))

### Bug 修复 / Bug Fixes

- **fix(pc_prober)**: 修复缺失的 `import os` ([`b1cfc08`](https://github.com/makiseeee/Echogent/commit/b1cfc08))

### 运维 / Chores

- **chore(deploy)**: AstrBot 启动等待超时提升至 120s 以适配骁龙 835 ([`d2c3dbc`](https://github.com/makiseeee/Echogent/commit/d2c3dbc))

### 文档 / Documentation

- **docs(roadmap)**: 集成六阶段全景路线图，涵盖 Live2D 规格、视觉哨兵与 Kiosk APK 封装 ([`4ed047b`](https://github.com/makiseeee/Echogent/commit/4ed047b))
- **docs(roadmap)**: 记录已完成的重构/性能里程碑与架构演进 TODO ([`c73dfed`](https://github.com/makiseeee/Echogent/commit/c73dfed))
- **docs(roadmap)**: 精确标注 WOL 待实测与人脸哨兵待录入状态 ([`e5d2447`](https://github.com/makiseeee/Echogent/commit/e5d2447))

---

## [Pre-7.0] - 2026-08 (初始同步)

- **sync**: 从手机端同步 echo-tools 插件、MIX 2 伴侣屏、PC Agent 与人设全套至 Git 仓库 ([`9462122`](https://github.com/makiseeee/Echogent/commit/9462122))
