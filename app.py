"""Flask application for code review agent."""
import os
import json
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from analyzer import get_analyzer
from analyzer.tools import is_tool_available, get_tool_version
from analyzer.llm import get_llm_client
from analyzer.prompts import (
    SYSTEM_PROMPT,
    PROMPT_SUMMARY,
    PROMPT_SMART_SUGGESTION,
    PROMPT_CHAT,
    PROMPT_EXPLAIN
)

app = Flask(__name__)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/tools', methods=['GET'])
def api_tools():
    """Return available analysis tools and their status."""
    tools = {}
    for tool in ['ruff', 'semgrep']:
        avail = is_tool_available(tool)
        tools[tool] = {
            'available': avail,
            'version': get_tool_version(tool) if avail else None,
        }
    return jsonify(tools)


@app.route('/api/analyze', methods=['POST'])
def analyze():
    """Original analyze endpoint - backward compatible."""
    data = request.get_json()
    project_path = data.get('path', '').strip()
    language = data.get('language', 'python')

    if not project_path:
        return jsonify({'error': '请输入项目目录路径'}), 400

    if not os.path.isdir(project_path):
        return jsonify({'error': f'目录不存在: {project_path}'}), 400

    analyzer = get_analyzer(language)
    if not analyzer:
        return jsonify({'error': f'不支持的语言: {language}'}), 400

    try:
        result = analyzer.analyze(project_path)
    except Exception as e:
        return jsonify({'error': f'分析出错: {str(e)}'}), 500

    # Get tool status from analyzer
    tools_status = getattr(analyzer, 'tools_status', {})

    return jsonify({
        'total_score': result.total_score,
        'language': result.language,
        'file_count': result.file_count,
        'total_lines': result.total_lines,
        'tools_status': tools_status,
        'analyzed_files': [os.path.relpath(f, project_path) for f in result.analyzed_files],
        'dimensions': [
            {
                'name': d.name,
                'score': round(d.score, 1),
                'weight': d.weight,
                'details': d.details,
                'issues': [
                    {
                        'severity': iss.severity,
                        'icon': {'critical': '🔴', 'warning': '🟡', 'info': '🔵'}.get(iss.severity, '⚪'),
                        'file': os.path.relpath(iss.file_path, project_path) if iss.file_path else '',
                        'line': iss.line_number,
                        'description': iss.description,
                        'suggestion': iss.suggestion,
                        'metric': iss.metric,
                    }
                    for iss in d.issues
                ]
            }
            for d in result.dimensions
        ],
        'all_issues': [
            {
                'severity': iss.severity,
                'icon': {'critical': '🔴', 'warning': '🟡', 'info': '🔵'}.get(iss.severity, '⚪'),
                'file': os.path.relpath(iss.file_path, project_path) if iss.file_path else '',
                'line': iss.line_number,
                'description': iss.description,
                'suggestion': iss.suggestion,
                'metric': iss.metric,
            }
            for iss in result.all_issues
        ]
    })


@app.route('/api/llm/status', methods=['GET'])
def llm_status():
    """Get LLM status and configuration info."""
    llm = get_llm_client()
    return jsonify({
        'available': llm.available,
        'provider': llm.provider,
        'model': llm.model,
    })


@app.route('/api/analyze/enhanced', methods=['POST'])
def analyze_enhanced():
    """Enhanced analysis with LLM suggestions and summary."""
    data = request.get_json()
    project_path = data.get('path', '').strip()
    language = data.get('language', 'python')

    if not project_path:
        return jsonify({'error': '请输入项目目录路径'}), 400

    if not os.path.isdir(project_path):
        return jsonify({'error': f'目录不存在: {project_path}'}), 400

    analyzer = get_analyzer(language)
    if not analyzer:
        return jsonify({'error': f'不支持的语言: {language}'}), 400

    try:
        result = analyzer.analyze(project_path)
    except Exception as e:
        return jsonify({'error': f'分析出错: {str(e)}'}), 500

    # Get tool status
    tools_status = getattr(analyzer, 'tools_status', {})

    # Get LLM client
    llm = get_llm_client()
    llm_available = llm.available

    llm_summary = None
    enhanced_issues = []

    if llm_available:
        # Generate LLM summary
        try:
            dimension_scores = '\n'.join([
                f"- {d.name}: {d.score}分 - {d.details}"
                for d in result.dimensions
            ])
            top_issues = '\n'.join([
                f"- [{iss.severity}] {os.path.relpath(iss.file_path, project_path)}:{iss.line_number} - {iss.description}"
                for iss in result.all_issues[:10]
            ])
            summary_prompt = PROMPT_SUMMARY.format(
                file_count=result.file_count,
                total_lines=result.total_lines,
                total_score=result.total_score,
                dimension_scores=dimension_scores,
                top_issues=top_issues
            )
            llm_summary = llm.chat(SYSTEM_PROMPT, summary_prompt)
        except Exception as e:
            llm_summary = None

        # Generate smart suggestions for top issues
        try:
            context_lines = 10
            for iss in result.all_issues[:10]:
                if not iss.file_path or not os.path.exists(iss.file_path):
                    continue
                try:
                    with open(iss.file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    start = max(0, iss.line_number - context_lines - 1)
                    end = min(len(lines), iss.line_number + context_lines - 1)
                    code_context = ''.join(lines[start:end])

                    suggestion_prompt = PROMPT_SMART_SUGGESTION.format(
                        file_path=os.path.relpath(iss.file_path, project_path),
                        line=iss.line_number,
                        issue_type=iss.metric or '代码质量',
                        severity=iss.severity,
                        description=iss.description,
                        code_context=code_context
                    )
                    smart_suggestion = llm.chat(SYSTEM_PROMPT, suggestion_prompt)
                    enhanced_issues.append({
                        'file': os.path.relpath(iss.file_path, project_path),
                        'line': iss.line_number,
                        'severity': iss.severity,
                        'description': iss.description,
                        'smart_suggestion': smart_suggestion
                    })
                except Exception:
                    continue
        except Exception:
            pass

    return jsonify({
        'total_score': result.total_score,
        'language': result.language,
        'file_count': result.file_count,
        'total_lines': result.total_lines,
        'tools_status': tools_status,
        'llm_available': llm_available,
        'llm_summary': llm_summary,
        'enhanced_issues': enhanced_issues,
        'analyzed_files': [os.path.relpath(f, project_path) for f in result.analyzed_files],
        'dimensions': [
            {
                'name': d.name,
                'score': round(d.score, 1),
                'weight': d.weight,
                'details': d.details,
                'issues': [
                    {
                        'severity': iss.severity,
                        'icon': {'critical': '🔴', 'warning': '🟡', 'info': '🔵'}.get(iss.severity, '⚪'),
                        'file': os.path.relpath(iss.file_path, project_path) if iss.file_path else '',
                        'line': iss.line_number,
                        'description': iss.description,
                        'suggestion': iss.suggestion,
                        'metric': iss.metric,
                    }
                    for iss in d.issues
                ]
            }
            for d in result.dimensions
        ],
        'all_issues': [
            {
                'severity': iss.severity,
                'icon': {'critical': '🔴', 'warning': '🟡', 'info': '🔵'}.get(iss.severity, '⚪'),
                'file': os.path.relpath(iss.file_path, project_path) if iss.file_path else '',
                'line': iss.line_number,
                'description': iss.description,
                'suggestion': iss.suggestion,
                'metric': iss.metric,
            }
            for iss in result.all_issues
        ]
    })


@app.route('/api/analyze/stream', methods=['POST'])
def analyze_stream():
    """Streaming analysis with SSE."""
    data = request.get_json()
    project_path = data.get('path', '').strip()
    language = data.get('language', 'python')

    if not project_path:
        return jsonify({'error': '请输入项目目录路径'}), 400

    if not os.path.isdir(project_path):
        return jsonify({'error': f'目录不存在: {project_path}'}), 400

    analyzer = get_analyzer(language)
    if not analyzer:
        return jsonify({'error': f'不支持的语言: {language}'}), 400

    def generate():
        try:
            # Step 1: Rule analysis
            yield f"data: {json.dumps({'step': 'rules', 'status': 'started'})}\n\n"

            result = analyzer.analyze(project_path)
            tools_status = getattr(analyzer, 'tools_status', {})

            yield f"data: {json.dumps({'step': 'rules', 'status': 'completed', 'result': {
                'total_score': result.total_score,
                'language': result.language,
                'file_count': result.file_count,
                'total_lines': result.total_lines,
                'tools_status': tools_status,
                'analyzed_files': [os.path.relpath(f, project_path) for f in result.analyzed_files],
                'dimensions': [
                    {
                        'name': d.name,
                        'score': round(d.score, 1),
                        'weight': d.weight,
                        'details': d.details,
                        'issues': [
                            {
                                'severity': iss.severity,
                                'icon': {'critical': '🔴', 'warning': '🟡', 'info': '🔵'}.get(iss.severity, '⚪'),
                                'file': os.path.relpath(iss.file_path, project_path) if iss.file_path else '',
                                'line': iss.line_number,
                                'description': iss.description,
                                'suggestion': iss.suggestion,
                                'metric': iss.metric,
                            }
                            for iss in d.issues
                        ]
                    }
                    for d in result.dimensions
                ],
                'all_issues': [
                    {
                        'severity': iss.severity,
                        'icon': {'critical': '🔴', 'warning': '🟡', 'info': '🔵'}.get(iss.severity, '⚪'),
                        'file': os.path.relpath(iss.file_path, project_path) if iss.file_path else '',
                        'line': iss.line_number,
                        'description': iss.description,
                        'suggestion': iss.suggestion,
                        'metric': iss.metric,
                    }
                    for iss in result.all_issues
                ]
            }})}\n\n"

            # Step 2: LLM summary
            llm = get_llm_client()
            if llm.available:
                yield f"data: {json.dumps({'step': 'llm', 'status': 'started'})}\n\n"

                dimension_scores = '\n'.join([
                    f"- {d.name}: {d.score}分 - {d.details}"
                    for d in result.dimensions
                ])
                top_issues = '\n'.join([
                    f"- [{iss.severity}] {os.path.relpath(iss.file_path, project_path)}:{iss.line_number} - {iss.description}"
                    for iss in result.all_issues[:10]
                ])
                summary_prompt = PROMPT_SUMMARY.format(
                    file_count=result.file_count,
                    total_lines=result.total_lines,
                    total_score=result.total_score,
                    dimension_scores=dimension_scores,
                    top_issues=top_issues
                )

                for chunk in llm.chat_stream(SYSTEM_PROMPT, summary_prompt):
                    yield f"data: {json.dumps({'step': 'llm', 'status': 'streaming', 'text': chunk})}\n\n"

                yield f"data: {json.dumps({'step': 'llm', 'status': 'completed'})}\n\n"
            else:
                yield f"data: {json.dumps({'step': 'llm', 'status': 'skipped'})}\n\n"

            # Step 3: Done
            yield f"data: {json.dumps({'step': 'done'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'step': 'error', 'message': str(e)})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@app.route('/api/chat', methods=['POST'])
def chat():
    """Interactive chat based on analysis context."""
    data = request.get_json()
    message = data.get('message', '').strip()
    analysis_context = data.get('analysis_context', {})
    history = data.get('history', [])
    stream = data.get('stream', True)

    if not message:
        return jsonify({'error': '请输入消息'}), 400

    llm = get_llm_client()
    if not llm.available:
        return jsonify({'error': 'LLM 不可用'}), 400

    # Build chat history
    chat_history = '\n'.join([
        f"Q: {h.get('question', '')}\nA: {h.get('answer', '')}"
        for h in history[-5:]  # Last 5 messages
    ])

    # Build prompt
    chat_prompt = PROMPT_CHAT.format(
        language=analysis_context.get('language', 'unknown'),
        total_score=analysis_context.get('total_score', 0),
        file_count=analysis_context.get('file_count', 0),
        chat_history=chat_history if chat_history else '无',
        user_question=message
    )

    if stream:
        def generate():
            try:
                for chunk in llm.chat_stream(SYSTEM_PROMPT, chat_prompt):
                    yield f"data: {json.dumps({'text': chunk})}\n\n"
                yield f"data: {json.dumps({'done': True})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return Response(stream_with_context(generate()), mimetype='text/event-stream')
    else:
        try:
            response = llm.chat(SYSTEM_PROMPT, chat_prompt)
            return jsonify({'answer': response})
        except Exception as e:
            return jsonify({'error': f'LLM 调用出错: {str(e)}'}), 500


@app.route('/api/issue/explain', methods=['POST'])
def explain_issue():
    """Get detailed LLM explanation for a specific issue."""
    data = request.get_json()
    file_path = data.get('file_path', '').strip()
    line = data.get('line', 0)
    description = data.get('description', '').strip()
    rule_id = data.get('rule_id', '').strip()
    language = data.get('language', 'python')

    if not file_path or not description:
        return jsonify({'error': '缺少必要参数'}), 400

    llm = get_llm_client()
    if not llm.available:
        return jsonify({'error': 'LLM 不可用'}), 400

    # Read code context
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        return jsonify({'error': f'读取文件失败: {str(e)}'}), 400

    start = max(0, line - 11)  # 0-indexed
    end = min(len(lines), line + 9)
    code_block = ''.join(lines[start:end])

    # Generate explanation
    explain_prompt = PROMPT_EXPLAIN.format(
        file_path=os.path.basename(file_path),
        rule_id=rule_id or '代码质量',
        description=description,
        language=language,
        code_block=code_block
    )

    try:
        explanation = llm.chat(SYSTEM_PROMPT, explain_prompt)
        return jsonify({
            'explanation': explanation,
            'code_context': code_block
        })
    except Exception as e:
        return jsonify({'error': f'LLM 调用出错: {str(e)}'}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
