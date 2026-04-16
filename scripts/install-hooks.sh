#!/bin/bash
# 安装 Git pre-commit hook
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOKS_DIR="$SCRIPT_DIR/../hooks"
GIT_DIR="$(git rev-parse --git-dir 2>/dev/null || true)"

if [ -z "$GIT_DIR" ]; then
    echo "❌ 不在 git 仓库中"
    exit 1
fi

HOOK_TARGET="$GIT_DIR/hooks/pre-commit"

cp "$HOOKS_DIR/pre-commit" "$HOOK_TARGET"
chmod +x "$HOOK_TARGET"

echo "✅ pre-commit hook 已安装到: $HOOK_TARGET"
