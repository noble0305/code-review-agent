# Design: UI 增强 V1

## 架构决策

### 1. 趋势仪表盘
- **方案**：在现有 History Tab 中增强，使用 Chart.js（已引入）
- **组件**：
  - 统计卡片（分析次数/平均分/最高分/最低分）
  - 评分趋势折线图（`GET /api/history` 数据）
  - 维度雷达图（`GET /api/history/<id>` 取最新详情）
  - 问题严重程度环形图（从 dimensions 中统计）
- **不新增后端 API**，复用现有 `/api/history` 和 `/api/history/<id>`

### 2. 一键修复
- **后端**：新增 `POST /api/issue/apply-fix`
  - 接收：project_path, file_path, fixed_code, context_start, context_end
  - 逻辑：shutil.copy2 备份 → 读取文件 → 替换指定行范围 → 写入
  - 安全：复用 `_resolve_project_file_path` 路径校验
  - 回滚：写入失败时从 .bak 恢复
- **前端**：在 fixIssue 的 diff 面板底部增加「应用修复」按钮
  - confirm 确认 → 调 API → 状态反馈（应用中/已应用/失败）

### 3. SVG 评分圆环
- **方案**：用 SVG circle + stroke-dasharray/dashoffset 替代 border 方案
- **动画**：初始 dashoffset = circumference，通过 CSS transition 过渡到目标值
- **颜色**：<60 红色渐变，60-80 黄色渐变，>80 绿色渐变

### 4. 微动效
- 维度进度条：添加 `::after` 伪元素发光效果
- 卡片 hover：`transform: translateY(-2px)` + `box-shadow`
- 按钮 active：`transform: scale(0.97)`

## 验证标准
- [ ] 趋势折线图能正确渲染历史数据
- [ ] 雷达图能展示最新分析的维度评分
- [ ] apply-fix API 能正确替换代码并备份
- [ ] apply-fix 失败时自动从备份恢复
- [ ] SVG 圆环动画从 0 过渡到目标值
- [ ] 现有分析、聊天、导出功能不受影响
