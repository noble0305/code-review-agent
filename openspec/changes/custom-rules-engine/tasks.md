# Tasks: 自定义规则引擎

## Phase 1: 数据库 ✅
- [x] storage.py 新增 rules 表
- [x] CRUD: save_rule, list_rules, update_rule, delete_rule, get_dimension_weights

## Phase 2: 后端 API ✅
- [x] GET /api/rules — 列出所有规则
- [x] POST /api/rules — 创建自定义规则
- [x] PATCH /api/rules/<id> — 更新（启用/权重）
- [x] DELETE /api/rules/<id> — 删除

## Phase 3: 前端 ✅
- [x] 新增「⚙️ 规则配置」Tab
- [x] 规则列表（开关+权重滑块+删除）
- [x] 新增自定义规则表单（名称/维度/模式/严重程度/描述）
- [x] 删除确认

## Phase 4: 集成 ⏳
- [ ] analyzer 分析时读取 rules 表覆盖默认权重（需修改核心分析器）
