# Proposal: UI 增强 V1

## 背景
code-review-agent 已有基础的 Web UI（暗色主题、分析、聊天面板），但缺少数据可视化、修复能力和视觉吸引力。

## 目标
1. 趋势仪表盘：展示历史分析数据的评分趋势、维度雷达图、问题分布
2. 一键修复：将 AI 生成的修复建议直接应用到源文件
3. 界面美化：SVG 评分圆环、动效、渐变进度条

## 范围
- 前端：`templates/index.html`
- 后端：`app.py`（新增 apply-fix API）
- 不涉及：分析引擎、存储模块

## 状态
✅ 已完成（2026-04-18）

## 影响
- ADDED: `/api/issue/apply-fix` 端点
- ADDED: 历史趋势面板（统计卡片、折线图、雷达图、饼图）
- ADDED: SVG 评分圆环 + 动画
- MODIFIED: issue 修复面板（增加应用修复按钮）
- MODIFIED: CSS（进度条发光、卡片阴影、按钮动效）
