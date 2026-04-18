# Design: GitHub PR 集成

## 架构决策

### 整体流程
```
GitHub PR Event → Webhook Endpoint → 验证签名 → Clone PR 分支
    → 跑分析（复用现有 analyzer） → 格式化结果 → GitHub API 评论到 PR
```

### 1. Webhook 接收
- **端点**：`POST /api/github/webhook`
- **签名验证**：HMAC-SHA256，使用配置的 Webhook Secret
- **支持事件**：`pull_request` (opened, synchronize, reopened)
- **处理**：收到后创建异步任务，立即返回 200（不阻塞 GitHub）

### 2. 分析执行
- **Clone**：使用 `git clone --depth=1 --branch=<head_branch>` 到临时目录
- **分析**：复用现有 `analyzer.analyze()` 方法，mode=full
- **LLM**：如果可用，调用 `/api/analyze/enhanced` 逻辑生成摘要

### 3. PR 评论
- **格式**：Markdown 表格，包含总分、各维度评分、Top Issues
- **API**：通过 PyGithub 调用 `pr.create_issue_comment()`
- **评论标签**：带 `<!-- code-review-agent -->` 标记，便于后续更新而非重复创建

### 4. 配置管理
```yaml
github:
  webhook_secret: ""      # GitHub Webhook Secret
  token: ""               # GitHub Personal Access Token（需要 repo 权限）
  repos:                   # 绑定的仓库列表
    - owner/repo
  auto_comment: true       # 是否自动评论
  fail_on_critical: false  # critical 超过阈值时是否设置 commit status 为 failure
```

### 5. 安全考虑
- Webhook Secret 必填，防止伪造请求
- GitHub Token 存储在 config.yaml（后续可改为加密存储）
- Clone 使用浅克隆（--depth=1），减少磁盘占用
- 临时目录分析完成后清理

### 6. 数据模型
```sql
CREATE TABLE IF NOT EXISTS github_integrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_full_name TEXT NOT NULL UNIQUE,
    webhook_secret TEXT NOT NULL,
    github_token TEXT NOT NULL,
    auto_comment INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pr_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    integration_id INTEGER REFERENCES github_integrations(id),
    pr_number INTEGER NOT NULL,
    commit_sha TEXT NOT NULL,
    total_score REAL,
    comment_id INTEGER,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 验证标准
- [ ] Webhook 端点能正确验证 HMAC-SHA256 签名
- [ ] 收到 PR 事件后能自动触发分析
- [ ] 分析结果能以 Markdown 评论发到 PR
- [ ] 重复 push 到同一 PR 时更新评论而非重复创建
- [ ] 配置页面能保存和读取 GitHub Token / Webhook Secret
- [ ] 测试按钮能验证 Token 和 Webhook 连通性
- [ ] 临时 clone 的代码在分析完成后被清理
