"""测试 GLM 返回的 JSON 解析修复"""
import json, re

# GLM 实际返回的真实数据（裸换行 + fixed_code 嵌套代码块）
raw = """{
  "analysis": "函数参数过多，导致函数签名复杂，难以理解和维护。建议使用参数对象来减少参数数量，使函数更加清晰和易于使用。",
  "fix_description": "将多个参数封装到一个字典或自定义类中，作为函数的单一参数接收，从而简化函数签名。",
  "fixed_code": "```python
def process_data(data_dict):
    result = data_dict['a'] + data_dict['b'] + data_dict['c']
    return result
```"
}"""

print("=== 原始 (repr 前300字) ===")
print(repr(raw[:300]))
print()

# 直接解析
try:
    json.loads(raw)
    print("直接解析: OK")
except Exception as e:
    print(f"直接解析: FAILED ({e})")

def fix_newlines_in_json_strings(text):
    """修复 JSON 字符串值中的裸换行符（替换为 \\n）。"""
    result = []
    in_string = False
    escaped = False
    for char in text:
        if escaped:
            result.append(char)
            escaped = False
            continue
        if char == '\\':
            result.append(char)
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            result.append(char)
            continue
        if in_string and char == '\n':
            result.append('\\n')
            continue
        if in_string and char == '\t':
            result.append('\\t')
            continue
        result.append(char)
    return ''.join(result)


def clean_code_blocks_in_values(text):
    """清理 JSON 字符串值中嵌套的 ```lang\\n...``` 标记。"""
    result = []
    in_string = False
    escaped = False
    i = 0
    while i < len(text):
        char = text[i]
        if escaped:
            result.append(char)
            escaped = False
            i += 1
            continue
        if char == '\\':
            result.append(char)
            escaped = True
            i += 1
            continue
        if char == '"':
            in_string = not in_string
            result.append(char)
            i += 1
            continue
        # 在字符串内，检测 ``` 标记
        if in_string and text[i:i+3] == '```':
            # 看是开头还是结尾
            # 跳过 ```lang\n 部分
            j = i + 3
            # 跳过语言标记（如 python）
            while j < len(text) and text[j].isalpha():
                j += 1
            # 跳过换行
            if j < len(text) and text[j] == '\n':
                j += 1
            # 现在光标在代码内容开始处
            # 找到结尾的 ```
            end = text.find('```', j)
            if end != -1:
                # 提取代码内容
                code = text[j:end]
                # 如果结尾前有换行，去掉
                if code.endswith('\n'):
                    code = code[:-1]
                # 写入转义后的代码
                result.append(code.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n'))
                i = end + 3
                continue
        result.append(char)
        i += 1
    return ''.join(result)


# 策略 1：先修复裸换行
fixed_nl = fix_newlines_in_json_strings(raw)
try:
    p = json.loads(fixed_nl)
    print("\n策略1 (fix newlines): OK")
    print(f"  analysis: {p['analysis'][:60]}")
    print(f"  fixed_code: {p['fixed_code'][:80]}")
except Exception as e:
    print(f"\n策略1 (fix newlines): FAILED ({e})")
    print(f"  repr: {repr(fixed_nl[:200])}")

# 策略 2：清理代码块标记
cleaned = clean_code_blocks_in_values(raw)
try:
    p = json.loads(cleaned)
    print("\n策略2 (clean code blocks): OK")
    print(f"  analysis: {p['analysis'][:60]}")
    print(f"  fixed_code: {p['fixed_code'][:80]}")
except Exception as e:
    print(f"\n策略2 (clean code blocks): FAILED ({e})")
    print(f"  repr: {repr(cleaned[:300])}")

# 策略 3：先清理代码块，再修复裸换行
combined = fix_newlines_in_json_strings(clean_code_blocks_in_values(raw))
try:
    p = json.loads(combined)
    print("\n策略3 (clean + fix): OK")
    print(f"  analysis: {p['analysis'][:60]}")
    print(f"  fixed_code: {p['fixed_code'][:80]}")
except Exception as e:
    print(f"\n策略3 (clean + fix): FAILED ({e})")
