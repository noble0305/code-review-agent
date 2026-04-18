# Tasks: UI 增强 V1

## Phase 1: 一键修复（后端）
- [x] 新增 `POST /api/issue/apply-fix` 端点（app.py 第 839 行）
  - 路径校验复用 `_resolve_project_file_path`
  - shutil.copy2 备份原文件为 .bak
  - 读取文件，替换 context_start 到 context_end 的行
  - 写入失败时从备份恢复
- [x] 验证：curl 测试 API 可达

## Phase 2: 一键修复（前端）
- [x] fixIssue 函数中增加「应用修复」按钮
- [x] 新增 applyFix JS 函数（confirm 确认 → 调 API → 状态反馈）
- [x] fixed_code 通过 data-fixed-code 属性传递（encodeURIComponent）

## Phase 3: 趋势仪表盘
- [x] panelHistory HTML 增加统计卡片区、雷达图容器、饼图容器
- [x] renderTrendChart 增强：统计卡片 + 改进折线图样式
- [x] 新增 loadRadarChart 函数（取最新分析详情 → 雷达图）
- [x] 新增 renderSeverityDistribution 函数（环形图）

## Phase 4: 界面美化
- [x] SVG 评分圆环替代 border 方案
- [x] renderScoreCircle + scoreGradient 函数
- [x] 动画：requestAnimationFrame 触发 stroke-dashoffset transition
- [x] 维度进度条 `::after` 发光效果
- [x] 卡片 hover 上浮 + 阴影
- [x] 按钮 active scale 按压感
