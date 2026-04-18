# Proposal: 自定义规则引擎

## 背景
当前审查规则硬编码在各 analyzer 中。用户希望能自定义规则（启用/禁用、调整权重、添加自定义检查）。

## 目标
1. 规则管理 API（CRUD）
2. 规则存储在数据库
3. 前端规则配置面板（开关+权重调节）
4. 分析时读取用户规则覆盖默认值

## 范围
- 后端：新增 rules API，修改 analyzer 读取规则
- 前端：新增「⚙️ 规则配置」Tab
- 数据库：新增 rules 表

## Delta Spec
- ADDED: `POST /api/rules` — 创建规则
- ADDED: `GET /api/rules` — 列出规则
- ADDED: `PATCH /api/rules/<id>` — 更新规则（启用/权重）
- ADDED: `DELETE /api/rules/<id>` — 删除规则
- ADDED: rules 表
- MODIFIED: analyzer — 读取自定义规则覆盖默认维度权重

## 状态
⏳ 实现中
