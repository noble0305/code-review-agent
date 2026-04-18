# Tasks: GitHub PR 集成

## Phase 1: 后端基础设施 ✅
- [x] 新增 `analyzer/github_integration.py` 模块
  - verify_webhook_signature(secret, payload_body, signature_header) -> bool
  - clone_pr_repo(clone_url, branch, target_dir) -> str
  - format_review_comment(analysis_result) -> Markdown
  - post_pr_comment(token, repo_full_name, pr_number, body) -> int
  - run_pr_analysis(token, repo, pr, clone_url, branch, ...) -> dict
- [x] 验证：模块可导入，方法签名正确

## Phase 2: 数据库扩展 ✅
- [x] storage.py 新增 github_integrations 表
- [x] storage.py 新增 pr_reviews 表
- [x] CRUD: save_integration, get_integration, get_integration_by_id, list_integrations, delete_integration
- [x] CRUD: save_pr_review, update_pr_review_status, list_pr_reviews
- [x] 验证：init_db() 后表存在

## Phase 3: Webhook API ✅
- [x] POST /api/github/webhook — 接收 GitHub Webhook
  - 验证 X-Hub-Signature-256
  - 解析 PR 事件
  - 异步执行分析
  - 立即返回 200
- [x] 验证：API 可达，返回 []

## Phase 4: 配置 API ✅
- [x] GET /api/github/config — 获取所有集成配置（token 脱敏）
- [x] POST /api/github/config — 保存/更新集成配置
- [x] DELETE /api/github/config/<id> — 删除配置
- [x] POST /api/github/test — 测试 Token 和连通性
- [x] GET /api/github/reviews — PR 审查历史
- [x] 验证：配置 API 返回空列表正常

## Phase 5: 分析执行 + PR 评论 ✅
- [x] run_pr_analysis 完整流程（clone → analyze → comment → cleanup）
- [x] 自动检测已有评论并更新（不重复创建）
- [x] 状态管理（pending → running → completed/failed）

## Phase 6: 前端集成配置页 ✅
- [x] 新增「🔗 GitHub集成」Tab
- [x] 配置表单：仓库、Webhook Secret、GitHub Token
- [x] 保存/删除配置
- [x] 测试连通性按钮
- [x] PR 审查历史列表
- [x] 配置指南说明

## Phase 7: 依赖更新 ✅
- [x] requirements.txt 新增 PyGithub
- [x] PyGithub 2.9.1 + PyNaCl 1.6.2 已安装
- [x] 验证：服务启动无报错
