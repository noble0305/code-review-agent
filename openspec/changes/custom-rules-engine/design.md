# Design: 自定义规则引擎

## 数据模型
```sql
CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    dimension TEXT NOT NULL,          -- 对应维度 (maintainability, security, etc.)
    severity TEXT DEFAULT 'warning',  -- critical / warning / info
    pattern TEXT,                     -- 正则或关键词匹配
    description TEXT,
    enabled INTEGER DEFAULT 1,
    weight REAL DEFAULT 1.0,          -- 影响该维度权重
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 架构
1. **默认规则**：从 analyzer 内置维度中提取，首次启动时自动写入 rules 表
2. **用户规则**：用户可新增自定义规则（pattern 匹配）
3. **权重调节**：调整维度权重，影响总分计算
4. **开关**：启用/禁用单条规则

## 验证标准
- [ ] 默认规则自动初始化
- [ ] 用户可新增自定义规则
- [ ] 权重修改后重新分析生效
- [ ] 禁用规则后该规则不参与分析
