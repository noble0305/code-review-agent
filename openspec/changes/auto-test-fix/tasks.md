# Tasks: 自动测试 + 智能修复

## Phase 1: 数据层
- [ ] T1: storage.py 新增 test_plans / test_results 表 + CRUD 函数
- [ ] T2: 数据库自动迁移（启动时检查表是否存在）

## Phase 2: 测试引擎
- [ ] T3: analyzer/test_engine.py — TestEngine 基类
- [ ] T4: Python 测试生成器（pytest 模板）
- [ ] T5: JavaScript 测试生成器（Jest 模板）
- [ ] T6: Go 测试生成器（go test 模板）
- [ ] T7: 测试执行器（subprocess + 超时 + 结果解析）
- [ ] T8: 失败分析器（LLM 分析错误堆栈）
- [ ] T9: 自动修复循环（最多 3 轮）
- [ ] T10: 覆盖率收集（pytest-cov / jest --coverage）

## Phase 3: API
- [ ] T11: POST /api/test/plan — 生成测试计划
- [ ] T12: POST /api/test/run — 执行测试
- [ ] T13: POST /api/test/auto-fix — 自动修复循环（SSE 流式）
- [ ] T14: GET /api/test/results — 测试历史
- [ ] T15: GET /api/test/<id>/report — 详细报告

## Phase 4: 前端
- [ ] T16: 新增「🧪 测试」Tab
- [ ] T17: 测试计划预览（代码高亮）
- [ ] T18: 执行结果展示（通过/失败/总数）
- [ ] T19: 修复记录（diff 展示）
- [ ] T20: 测试历史列表

## Phase 5: 集成
- [ ] T21: 与现有分析流程串联（分析完可一键测试）
- [ ] T22: 端到端验证
