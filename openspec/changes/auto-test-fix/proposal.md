# Proposal: 自动测试 + 智能修复

## 背景
代码审查后发现问题，用户需要手动写测试、跑测试、修复、再验证。整个流程可以自动化。

## 目标
1. 分析源码自动生成测试计划（基于函数/类签名 + 模板）
2. 沙箱执行测试，收集通过率、覆盖率、错误信息
3. 测试失败时调用 LLM 分析根因并生成修复代码
4. 自动应用修复 → 重新测试 → 最多 3 轮迭代
5. 前端「🧪 测试」Tab 展示全流程

## 范围
- 后端：新增 `analyzer/test_engine.py` 模块
- 后端：扩展 `storage.py`（test_plans / test_results 表）
- 后端：新增 API 端点
- 前端：新增测试 Tab
- 支持语言：Python（pytest）、JavaScript（Jest）、Go（go test）、Java（JUnit）

## Delta Spec
- ADDED: `analyzer/test_engine.py`
- ADDED: `test_plans` / `test_results` 数据库表
- ADDED: `POST /api/test/plan` — 生成测试计划
- ADDED: `POST /api/test/run` — 执行测试
- ADDED: `POST /api/test/auto-fix` — 自动修复循环
- ADDED: `GET /api/test/results` — 测试历史
- ADDED: `GET /api/test/<id>/report` — 详细报告
- MODIFIED: `templates/index.html` — 新增测试 Tab

## 状态
⏳ 实现中
