# Proposal: 多项目对比仪表盘

## 背景
用户已有多个项目的分析历史数据，需要一个视图对比不同项目的代码质量趋势，识别薄弱环节。

## 目标
1. 项目评分横向对比柱状图
2. 多项目评分趋势叠加折线图
3. 项目选择器（复选框多选）
4. 对比详情表格

## 范围
- 前端：`templates/index.html`（在 History Tab 中增加对比面板）
- 后端：无需新 API，复用 `GET /api/history` 和 `GET /api/history/compare`
- 不涉及：分析引擎

## Delta Spec
- MODIFIED: `templates/index.html` — History Tab 增加项目对比区

## 状态
⏳ 实现中
