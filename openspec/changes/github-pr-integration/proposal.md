# Proposal: GitHub PR 集成

## 背景
当前 code-review-agent 只支持本地分析（手动输入路径或 git diff）。在实际团队开发中，代码审查最常发生在 PR/MR 阶段。需要一个机制让 PR 提交时自动触发分析，结果直接评论到 PR 上。

## 目标
1. **GitHub Webhook 接收**：监听 PR 事件（opened, synchronize, reopened）
2. **自动触发分析**：收到 Webhook 后自动 clone 代码、跑分析
3. **PR 评论**：分析完成后将结果以评论形式发到 PR
4. **Web 管理界面**：配置 Webhook Secret、仓库绑定、查看集成状态

## 范围
- 后端：新增 Webhook 接收端点、GitHub API 集成、异步任务处理
- 前端：新增「集成配置」Tab
- 不涉及：分析引擎核心逻辑

## Delta Spec
- ADDED: `POST /api/github/webhook` — 接收 GitHub Webhook
- ADDED: `GET /api/github/config` — 获取集成配置
- ADDED: `POST /api/github/config` — 保存集成配置（repo, secret, token）
- ADDED: `POST /api/github/test` — 测试集成连通性
- ADDED: `analyzer/github_integration.py` — GitHub API 交互模块
- MODIFIED: `app.py` — 注册新路由
- MODIFIED: `templates/index.html` — 新增集成配置 Tab
- MODIFIED: `config.yaml` — 新增 github 配置段
- MODIFIED: `requirements.txt` — 新增 PyGithub 依赖
