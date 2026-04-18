# Design: 自动测试 + 智能修复

## 数据模型

### test_plans 表
```sql
CREATE TABLE test_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_path TEXT NOT NULL,
    language TEXT NOT NULL,
    files_json TEXT,          -- 被测文件列表
    test_code TEXT,           -- 生成的测试代码
    framework TEXT,           -- pytest/jest/go test/junit
    status TEXT DEFAULT 'pending',  -- pending/generated/running/completed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### test_results 表
```sql
CREATE TABLE test_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER REFERENCES test_plans(id),
    total INTEGER DEFAULT 0,
    passed INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    errors TEXT,              -- 失败详情 JSON
    coverage REAL,
    fix_attempts INTEGER DEFAULT 0,
    fix_code TEXT,            -- 修复后的代码
    final_status TEXT DEFAULT 'pending',  -- pending/passed/failed/fixed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 模块架构

### test_engine.py
```python
class TestEngine:
    def generate_plan(project_path, language) -> dict
        # 扫描源码 → 提取函数/类 → 生成测试代码

    def run_tests(project_path, language, test_code) -> dict
        # subprocess 执行 → 解析结果

    def analyze_failure(source_code, error_output) -> dict
        # LLM 分析失败原因

    def generate_fix(source_code, test_error) -> str
        # LLM 生成修复代码

    def auto_fix_loop(project_path, language, max_rounds=3) -> dict
        # 生成 → 测试 → 修复 → 重测 循环
```

### 测试模板策略
- **Python**: pytest，每个函数生成 test_{name} 用例
- **JavaScript**: Jest，describe/it 结构
- **Go**: testing.T，TestXxx 函数
- **Java**: JUnit 5，@Test 方法

### 安全
- subprocess 执行，限制 60s 超时
- 禁止网络访问（环境变量 NO_PROXY）
- 工作目录隔离（/tmp/test-{uuid}/）

## API 流程

```
POST /api/test/plan
  → 扫描项目 → 生成测试代码 → 返回计划

POST /api/test/run
  → 执行测试 → 返回通过/失败

POST /api/test/auto-fix
  → 生成计划 → 执行 → 失败则修复 → 重新执行 → 最多3轮

GET /api/test/results
  → 历史记录列表

GET /api/test/<id>/report
  → 完整报告（计划+结果+修复记录）
```

## 前端 Tab: 🧪 测试
1. 输入区：项目路径 + 语言选择 + 开始按钮
2. 测试计划预览（代码编辑器风格）
3. 执行结果：通过/失败/总数 + 进度条
4. 修复记录：每轮修复的 diff 展示
5. 历史列表
