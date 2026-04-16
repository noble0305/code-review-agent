#!/usr/bin/env python3
"""CLI 入口 - 命令行模式运行代码审查。"""
import argparse
import json
import os
import sys

# 添加项目根目录到 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def cmd_analyze(args):
    """分析项目。"""
    from analyzer import get_analyzer
    from analyzer.storage import save_analysis, init_db
    from analyzer.rules import load_project_rules
    from analyzer.export import export_markdown, export_html

    project_path = os.path.abspath(args.path)
    if not os.path.isdir(project_path):
        print(f"错误: 目录不存在: {project_path}", file=sys.stderr)
        return 1

    analyzer = get_analyzer(args.lang)
    if not analyzer:
        print(f"错误: 不支持的语言: {args.lang}", file=sys.stderr)
        return 1

    # 加载自定义规则
    rules = load_project_rules(project_path)

    # Diff 模式
    if args.mode in ('diff', 'pr'):
        from analyzer.git_diff import get_changed_files
        base = args.base or 'HEAD~1'
        head = args.head or 'HEAD'
        changed = get_changed_files(project_path, base, head)
        if changed is None:
            print("警告: 不是 git 仓库，降级为全量分析", file=sys.stderr)
        elif not changed:
            print("没有检测到变更文件")
            return 0
        else:
            print(f"检测到 {len(changed)} 个变更文件", file=sys.stderr)
            result = analyzer.analyze(project_path, file_list=changed)
            _output_result(result, project_path, args)
            if args.save:
                try:
                    init_db()
                    result_dict = _result_to_dict(result, project_path)
                    aid = save_analysis(project_path, args.lang, result_dict)
                    print(f"已保存分析记录 (ID: {aid})", file=sys.stderr)
                except Exception as e:
                    print(f"保存失败: {e}", file=sys.stderr)
            return _check_threshold(result.total_score, args.threshold)

    result = analyzer.analyze(project_path)
    _output_result(result, project_path, args)

    # 保存到数据库
    if args.save:
        try:
            init_db()
            result_dict = _result_to_dict(result, project_path)
            aid = save_analysis(project_path, args.lang, result_dict)
            print(f"已保存分析记录 (ID: {aid})", file=sys.stderr)
        except Exception as e:
            print(f"保存失败: {e}", file=sys.stderr)

    return _check_threshold(result.total_score, args.threshold)


def _result_to_dict(result, project_path):
    """将 AnalysisResult 转为字典。"""
    return {
        'total_score': result.total_score,
        'file_count': result.file_count,
        'total_lines': result.total_lines,
        'language': result.language,
        'dimensions': [
            {'name': d.name, 'score': round(d.score, 1), 'weight': d.weight, 'details': d.details,
             'issues': [{'severity': i.severity, 'file': os.path.relpath(i.file_path, project_path) if i.file_path else '',
                         'line': i.line_number, 'description': i.description, 'suggestion': i.suggestion,
                         'metric': i.metric} for i in d.issues]}
            for d in result.dimensions
        ],
        'all_issues': [
            {'severity': i.severity, 'file': os.path.relpath(i.file_path, project_path) if i.file_path else '',
             'line': i.line_number, 'description': i.description, 'suggestion': i.suggestion,
             'metric': i.metric}
            for i in result.all_issues
        ]
    }


def _output_result(result, project_path, args):
    """输出结果。"""
    result_dict = _result_to_dict(result, project_path)

    if args.output == 'json':
        print(json.dumps(result_dict, ensure_ascii=False, indent=2))
    elif args.output == 'markdown':
        result_dict['project_path'] = project_path
        print(export_markdown(result_dict))
    else:
        # 表格模式
        print(f"\n{'='*50}")
        print(f"  总分: {result.total_score}/100")
        print(f"  文件: {result.file_count}  行数: {result.total_lines}")
        print(f"{'='*50}")
        for d in result.dimensions:
            print(f"  {d.name:20s} {d.score:6.1f}  ({len(d.issues)} 个问题)")
        print(f"{'='*50}")
        if result.all_issues:
            print(f"\n  问题总数: {len(result.all_issues)}")
            critical = sum(1 for i in result.all_issues if i.severity == 'critical')
            warning = sum(1 for i in result.all_issues if i.severity == 'warning')
            print(f"  🔴 严重: {critical}  🟡 警告: {warning}")


def _check_threshold(score, threshold):
    """检查是否低于阈值。"""
    if threshold and score < threshold:
        print(f"\n⚠️ 分数 {score} 低于阈值 {threshold}", file=sys.stderr)
        return 1
    return 0


def cmd_history(args):
    """查看分析历史。"""
    from analyzer.storage import list_analyses, init_db
    init_db()
    records = list_analyses(limit=args.limit)
    if not records:
        print("暂无分析历史")
        return 0
    print(f"{'ID':>5}  {'分数':>6}  {'文件':>5}  {'语言':<10}  {'时间':<20}  {'路径'}")
    print("-" * 80)
    for r in records:
        print(f"{r['id']:>5}  {r['total_score']:>6.1f}  {r['file_count']:>5}  {r['language']:<10}  {r['created_at'] or 'N/A':<20}  {r['project_path']}")


def cmd_compare(args):
    """对比两次分析。"""
    from analyzer.storage import compare_analyses, init_db
    init_db()
    result = compare_analyses(args.id1, args.id2)
    if not result:
        print("未找到分析记录", file=sys.stderr)
        return 1
    print(f"对比: #{args.id1} vs #{args.id2}")
    print(f"总分变化: {result['before']['total_score']:.1f} → {result['after']['total_score']:.1f} ({result['score_change']:+.1f})")
    print(f"文件变化: {result['file_count_change']:+d}  行数变化: {result['lines_change']:+d}")
    print("\n维度对比:")
    for name, diff in result['dimension_diff'].items():
        change = diff['change']
        icon = '↑' if change > 0 else '↓' if change < 0 else '→'
        print(f"  {name:20s} {diff['before']:6.1f} → {diff['after']:6.1f} ({icon}{abs(change):.1f})")


def cmd_export(args):
    """导出报告。"""
    from analyzer.storage import get_analysis, init_db
    from analyzer.export import export_markdown, export_html
    init_db()
    record = get_analysis(args.id)
    if not record:
        print(f"未找到分析记录: {args.id}", file=sys.stderr)
        return 1

    fmt = args.format or 'markdown'
    if fmt == 'html':
        content = export_html(record)
    else:
        content = export_markdown(record)

    if args.output_file:
        with open(args.output_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"已导出到: {args.output_file}")
    else:
        print(content)


def cmd_serve(args):
    """启动 Web 服务。"""
    from app import app
    port = args.port or 5001
    print(f"启动代码审查服务: http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=args.debug)


def main():
    parser = argparse.ArgumentParser(description='🔍 代码审查智能体 CLI')
    sub = parser.add_subparsers(dest='command', help='可用命令')

    # analyze
    p = sub.add_parser('analyze', help='分析项目代码')
    p.add_argument('path', help='项目路径')
    p.add_argument('--lang', default='python', choices=['python', 'javascript', 'java', 'go'], help='编程语言')
    p.add_argument('--mode', default='full', choices=['full', 'diff', 'pr'], help='分析模式')
    p.add_argument('--base', help='基准 commit/分支 (diff/pr 模式)')
    p.add_argument('--head', help='目标 commit/分支 (diff/pr 模式)')
    p.add_argument('--output', default='table', choices=['json', 'markdown', 'table'], help='输出格式')
    p.add_argument('--threshold', type=float, help='最低分数阈值，低于此值返回退出码 1')
    p.add_argument('--save', action='store_true', help='保存结果到数据库')

    # history
    p = sub.add_parser('history', help='查看分析历史')
    p.add_argument('--limit', type=int, default=20, help='显示条数')

    # compare
    p = sub.add_parser('compare', help='对比两次分析')
    p.add_argument('id1', type=int, help='第一次分析 ID')
    p.add_argument('id2', type=int, help='第二次分析 ID')

    # export
    p = sub.add_parser('export', help='导出报告')
    p.add_argument('id', type=int, help='分析记录 ID')
    p.add_argument('--format', choices=['markdown', 'html'], default='markdown', help='导出格式')
    p.add_argument('--output-file', '-o', help='输出文件路径')

    # serve
    p = sub.add_parser('serve', help='启动 Web 服务')
    p.add_argument('--port', type=int, default=5001, help='端口号')
    p.add_argument('--debug', action='store_true', help='调试模式')

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 0

    commands = {
        'analyze': cmd_analyze,
        'history': cmd_history,
        'compare': cmd_compare,
        'export': cmd_export,
        'serve': cmd_serve,
    }
    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main() or 0)
