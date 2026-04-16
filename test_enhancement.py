#!/usr/bin/env python3
"""Test script to verify the enhanced code review agent."""

import sys
import os

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
