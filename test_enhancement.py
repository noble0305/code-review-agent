#!/usr/bin/env python3
"""Test script to verify the enhanced code review agent."""

import sys
import os
import tempfile

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test all module imports."""
    print("Testing module imports...")
    try:
        from app import app
        from analyzer.llm import get_llm_client
        from analyzer.prompts import SYSTEM_PROMPT, PROMPT_SUMMARY
        from config import config
        print("✓ All modules imported successfully!")
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False

def test_llm_client():
    """Test LLM client."""
    print("\nTesting LLM client...")
    try:
        from analyzer.llm import get_llm_client
        llm = get_llm_client()
        print(f"✓ LLM client created")
        print(f"  - Available: {llm.available}")
        print(f"  - Provider: {llm.provider}")
        print(f"  - Model: {llm.model}")
        return True
    except Exception as e:
        print(f"✗ LLM client test failed: {e}")
        return False

def test_config():
    """Test configuration."""
    print("\nTesting configuration...")
    try:
        from config import config
        llm_config = config.get_llm_config()
        print("✓ Configuration loaded")
        print(f"  - Provider: {llm_config['provider']}")
        print(f"  - Model: {llm_config['model']}")
        print(f"  - Features: smart_suggestion={llm_config['features'].get('smart_suggestion')}")
        return True
    except Exception as e:
        print(f"✗ Configuration test failed: {e}")
        return False

def test_prompts():
    """Test prompt templates."""
    print("\nTesting prompt templates...")
    try:
        from analyzer.prompts import SYSTEM_PROMPT, PROMPT_SUMMARY
        print("✓ Prompt templates loaded")
        print(f"  - SYSTEM_PROMPT length: {len(SYSTEM_PROMPT)} chars")
        print(f"  - PROMPT_SUMMARY length: {len(PROMPT_SUMMARY)} chars")
        return True
    except Exception as e:
        print(f"✗ Prompt templates test failed: {e}")
        return False

def test_flask_endpoints():
    """Test Flask endpoints."""
    print("\nTesting Flask endpoints...")
    try:
        from app import app
        with app.test_client() as client:
            # Test LLM status
            response = client.get('/api/llm/status')
            data = response.get_json()
            print(f"✓ /api/llm/status: {response.status_code}")
            print(f"  - Available: {data.get('available')}")
            print(f"  - Provider: {data.get('provider')}")

            # Test main page
            response = client.get('/')
            print(f"✓ / (main page): {response.status_code}")

            # Test tools endpoint
            response = client.get('/api/tools')
            print(f"✓ /api/tools: {response.status_code}")

            return True
    except Exception as e:
        print(f"✗ Flask endpoints test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_issue_endpoints():
    """Test issue explanation/fix endpoints with project-relative paths."""
    print("\nTesting issue endpoints...")
    try:
        import app as app_module

        class DummyLLM:
            available = True

            def chat(self, system_prompt, prompt):
                if 'fixed_code' in prompt:
                    return '{"analysis":"发现问题","fix_description":"直接修复","fixed_code":"def demo():\\n    return 2"}'
                return '这里是解释结果'

        original_get_llm_client = app_module.get_llm_client
        app_module.get_llm_client = lambda: DummyLLM()

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                src_dir = os.path.join(tmpdir, 'src')
                os.makedirs(src_dir, exist_ok=True)
                file_path = os.path.join(src_dir, 'demo.py')
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write('def demo():\n    return 1\n')

                with app_module.app.test_client() as client:
                    response = client.post('/api/issue/explain', json={
                        'project_path': tmpdir,
                        'file_path': 'src/demo.py',
                        'line': 1,
                        'description': '返回值错误',
                        'language': 'python',
                    })
                    data = response.get_json()
                    print(f"✓ /api/issue/explain: {response.status_code}")
                    assert response.status_code == 200, data
                    assert 'def demo()' in (data.get('code_context') or '')

                    response = client.post('/api/issue/fix', json={
                        'project_path': tmpdir,
                        'file_path': 'src/demo.py',
                        'line': 1,
                        'description': '返回值错误',
                        'language': 'python',
                        'severity': 'warning',
                    })
                    data = response.get_json()
                    print(f"✓ /api/issue/fix: {response.status_code}")
                    assert response.status_code == 200, data
                    assert data.get('fixed_code') == 'def demo():\n    return 2'

                    response = client.post('/api/issue/explain', json={
                        'project_path': tmpdir,
                        'file_path': '../etc/passwd',
                        'line': 1,
                        'description': '非法路径',
                        'language': 'python',
                    })
                    print(f"✓ /api/issue/explain path guard: {response.status_code}")
                    assert response.status_code == 400
        finally:
            app_module.get_llm_client = original_get_llm_client

        print("✓ Issue endpoints work with project-relative paths!")
        return True
    except Exception as e:
        print(f"✗ Issue endpoints test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests."""
    print("=" * 50)
    print("Code Review Agent - LLM Enhancement Tests")
    print("=" * 50)

    tests = [
        test_imports,
        test_llm_client,
        test_config,
        test_prompts,
        test_flask_endpoints,
        test_issue_endpoints,
    ]

    results = []
    for test in tests:
        result = test()
        results.append(result)

    print("\n" + "=" * 50)
    print(f"Test Results: {sum(results)}/{len(results)} passed")
    print("=" * 50)

    if all(results):
        print("\n✓ All tests passed! The enhanced code review agent is ready.")
        return 0
    else:
        print("\n✗ Some tests failed. Please check the errors above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
