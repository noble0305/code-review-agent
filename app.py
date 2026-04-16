"""Flask application for code review agent."""
import os
import json
import threading
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
from analyzer.git_diff import get_changed_files
from analyzer.tasks import task_manager
from analyzer.export import export_markdown, export_html
from notifier.feishu import send_analysis_result

app = Flask(__name__)


def create_app():
    """应用工厂函数。"""
    return app


def _handle_mode_params(data, project_path, language, analyzer):
    """处理分析模式参数，返回 file_list 或 None（降级全量），或抛出提前返回。"""
    mode = data.get('mode', 'full')
    base = data.get('base', 'HEAD~1')
    head = data.get('head', 'HEAD')
    incremental = data.get('incremental', False)
    file_list = None
    
    if mode in ('diff', 'pr'):
        file_list = get_changed_files(project_path, base, head)
        if file_list is None:
            # 不是 git 仓库，降级到全量
            pass
        elif not file_list:
            return 'empty', None
    elif mode == 'full' and incremental:
        # 增量分析
        from analyzer.storage import get_changed_files_since_last, compute_file_md5
        all_files = analyzer.collect_files(project_path)
        current_hashes = {f: compute_file_md5(f) for f in all_files}
        changed = get_changed_files_since_last(project_path, current_hashes)
        if changed is not None:
            file_list = changed if changed else []
            if not file_list:
                # 没有变更，返回上次结果
                from analyzer.storage import list_analyses
                last = list_analyses(limit=1, project_path=project_path)
                if last:
                    from analyzer.storage import get_analysis
                    last_detail = get_analysis(last[0]['id'])
                    if last_detail:
                        return 'cached', last_detail
    
    return 'ok', file_list


def _save_analysis_to_db(project_path, language, result):
    """保存分析结果到数据库。"""
    try:
        from analyzer.storage import save_analysis, save_file_hashes, compute_file_md5, init_db
        init_db()
        result_dict = {
            'total_score': result.total_score,
            'file_count': result.file_count,
            'total_lines': result.total_lines,
            'dimensions': [{'name': d.name, 'score': d.score, 'weight': d.weight, 'details': d.details,
                           'issues': [{'severity': i.severity, 'file': os.path.relpath(i.file_path, project_path),
                                      'line': i.line_number, 'description': i.description} for i in d.issues]}
                          for d in result.dimensions]
        }
        aid = save_analysis(project_path, language, result_dict)
        # 保存文件哈希
        hashes = {f: compute_file_md5(f) for f in result.analyzed_files}
        save_file_hashes(aid, project_path, hashes)
    except Exception:
        pass


def _notify_webhooks(response_data):
    """异步发送 webhook 通知。"""
    try:
        from analyzer.storage import list_webhooks, init_db
        init_db()
        webhooks = list_webhooks()
        if webhooks:
            def _notify():
                import urllib.request
                for wh in webhooks:
                    try:
                        req = urllib.request.Request(
                            wh['url'],
                            data=json.dumps(response_data, ensure_ascii=False).encode('utf-8'),
                            headers={'Content-Type': 'application/json'}
                        )
                        urllib.request.urlopen(req, timeout=10)
                    except Exception:
                        pass
            threading.Thread(target=_notify, daemon=True).start()
    except Exception:
        pass


def _build_response_data(result, project_path, tools_status):
    """构建分析响应数据。"""
    return {
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
    }


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

    # 处理分析模式
    status, file_list_or_data = _handle_mode_params(data, project_path, language, analyzer)
    if status == 'empty':
        return jsonify({'total_score': 100, 'language': language, 'file_count': 0,
                      'total_lines': 0, 'dimensions': [], 'all_issues': [],
                      'analyzed_files': [], 'tools_status': {}})
    elif status == 'cached':
        return jsonify(file_list_or_data)
    file_list = file_list_or_data

    try:
        result = analyzer.analyze(project_path, file_list=file_list)
    except Exception as e:
        return jsonify({'error': f'分析出错: {str(e)}'}), 500

    # Get tool status from analyzer
    tools_status = getattr(analyzer, 'tools_status', {})
    response_data = _build_response_data(result, project_path, tools_status)

    # 保存到数据库
    _save_analysis_to_db(project_path, language, result)

    # 异步发送 webhook 通知
    _notify_webhooks(response_data)

    return jsonify(response_data)


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

    # 处理分析模式
    status, file_list_or_data = _handle_mode_params(data, project_path, language, analyzer)
    if status == 'empty':
        return jsonify({'total_score': 100, 'language': language, 'file_count': 0,
                      'total_lines': 0, 'dimensions': [], 'all_issues': [],
                      'analyzed_files': [], 'tools_status': {}})
    elif status == 'cached':
        return jsonify(file_list_or_data)
    file_list = file_list_or_data

    try:
        result = analyzer.analyze(project_path, file_list=file_list)
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

    response_data = {
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
    }

    # 保存到数据库
    _save_analysis_to_db(project_path, language, result)

    # 异步发送 webhook 通知
    _notify_webhooks(response_data)

    return jsonify(response_data)


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

            yield f"data: {json.dumps({'step': 'rules', 'status': 'completed', 'result': _build_response_data(result, project_path, tools_status)})}\n\n"

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


@app.route('/api/history', methods=['GET'])
def api_history():
    """分析历史列表。"""
    from analyzer.storage import list_analyses, init_db
    init_db()
    limit = request.args.get('limit', 50, type=int)
    project_path = request.args.get('project_path')
    records = list_analyses(limit=limit, project_path=project_path)
    return jsonify(records)


@app.route('/api/history/<int:analysis_id>', methods=['GET'])
def api_history_detail(analysis_id):
    """单次分析详情。"""
    from analyzer.storage import get_analysis, init_db
    init_db()
    record = get_analysis(analysis_id)
    if not record:
        return jsonify({'error': '记录不存在'}), 404
    return jsonify(record)


@app.route('/api/history/compare', methods=['GET'])
def api_history_compare():
    """对比两次分析。"""
    from analyzer.storage import compare_analyses, init_db
    init_db()
    id1 = request.args.get('id1', type=int)
    id2 = request.args.get('id2', type=int)
    if not id1 or not id2:
        return jsonify({'error': '请提供 id1 和 id2 参数'}), 400
    result = compare_analyses(id1, id2)
    if not result:
        return jsonify({'error': '记录不存在'}), 404
    return jsonify(result)


@app.route('/api/analyze/async', methods=['POST'])
def analyze_async():
    """提交异步分析任务。"""
    data = request.get_json()
    
    def run_analysis(path=data.get('path', ''), language=data.get('language', 'python')):
        analyzer = get_analyzer(language)
        if not analyzer:
            raise ValueError(f'不支持的语言: {language}')
        return analyzer.analyze(path)
    
    task_id = task_manager.submit(run_analysis)
    return jsonify({'task_id': task_id})


@app.route('/api/task/<task_id>', methods=['GET'])
def api_task_status(task_id):
    """查询任务状态。"""
    task = task_manager.get_task(task_id)
    if not task:
        return jsonify({'error': '任务不存在'}), 404
    return jsonify(task)


@app.route('/api/tasks', methods=['GET'])
def api_tasks():
    """列出所有任务。"""
    return jsonify(task_manager.list_tasks())


@app.route('/api/export/<int:analysis_id>', methods=['GET'])
def api_export(analysis_id):
    """导出报告。"""
    from analyzer.storage import get_analysis, init_db
    init_db()
    record = get_analysis(analysis_id)
    if not record:
        return jsonify({'error': '记录不存在'}), 404
    
    fmt = request.args.get('format', 'markdown')
    if fmt == 'html':
        content = export_html(record)
        return Response(content, mimetype='text/html; charset=utf-8')
    else:
        content = export_markdown(record)
        return Response(content, mimetype='text/markdown; charset=utf-8')


@app.route('/api/notify', methods=['POST'])
def api_notify():
    """手动触发飞书通知。"""
    data = request.get_json()
    webhook_url = data.get('webhook_url', '')
    analysis_result = data.get('analysis_result', {})
    
    if not webhook_url:
        # 尝试从配置读取
        from config import config
        webhook_url = config.get('notifier.feishu.webhook_url', '')
    
    if not webhook_url:
        return jsonify({'error': '未配置飞书 webhook URL'}), 400
    
    success = send_analysis_result(webhook_url, analysis_result)
    if success:
        return jsonify({'status': 'ok'})
    return jsonify({'error': '发送失败'}), 500


@app.route('/api/webhook/register', methods=['POST'])
def api_webhook_register():
    """注册 webhook。"""
    data = request.get_json()
    url = data.get('url', '').strip()
    if not url:
        return jsonify({'error': '请提供 webhook URL'}), 400
    from analyzer.storage import register_webhook, init_db
    init_db()
    wid = register_webhook(url, data.get('description', ''))
    return jsonify({'id': wid, 'url': url})


@app.route('/api/webhook/<int:webhook_id>', methods=['DELETE'])
def api_webhook_delete(webhook_id):
    """删除 webhook。"""
    from analyzer.storage import delete_webhook, init_db
    init_db()
    if delete_webhook(webhook_id):
        return jsonify({'status': 'ok'})
    return jsonify({'error': 'webhook 不存在'}), 404


@app.route('/api/webhook', methods=['GET'])
def api_webhook_list():
    """列出 webhooks。"""
    from analyzer.storage import list_webhooks, init_db
    init_db()
    return jsonify(list_webhooks())


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
