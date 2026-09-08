# 文档索引

本文档库为 **Echogent (Echo 7.0)** 伴侣智能体工程的唯一权威技术知识库。

## 当前架构与技术规范

- [系统详细架构与消息流](architecture.md)：MIX 2 硬件底座、PRoot 容器、PC 活动探针、消息流转与分层解耦架构
- [核心能力与工具边界](capabilities.md)：Obsidian 2PC 写入、有界读取、心流发言机制、动态切模与不可逾越的安全红线
- [日常运维与排障手册](operations.md)：USB-First 调试准则、服务监控、平滑重载流程与常见故障处置
- [网络拓扑与接口安全](security.md)：网络端口映射、防火墙策略、ADB 转发配置与鉴权管理
- [演进路线与待办清单](roadmap.md)：当前阶段稳定性检验、记忆备份闭环与后续演进目标
- [未来架构演进规划 v2.0](future_architecture_and_roadmap.md)：从陪伴工具到原生自主共生体的长期演化设计蓝图
- [Obsidian 深度集成方案](obsidian-integration-plan.md)：Git 异步同步、两阶段安全提交与双向任务流水线

## 历史归档

- [历史迁移与设计归档](archive/README.md)：保留早期 Docker 单机方案、旧手机迁移过程及演进日志，仅供回溯参考。

## 文档维护规则

1. **单一真实事实原则 (SSOT)**：系统的最新工程事实必须直接更新在对应的技术文档中，严禁在多个文档中散落矛盾的说明。
2. **私密信息安全防线**：严禁在任何文档中记录明文密码、API Token、QQ 登录凭据、私钥或个人敏感数据（私密手册仅存入已被 Git 忽略的 `docs/private/`）。
3. **架构与操作联动更新**：底层实现变动时同步修订 `architecture.md`，涉及运维指令时同步修订 `operations.md`。
