"""Flask application for code review agent."""
import os
import json
from flask import Flask, render_template, request, jsonify
from analyzer import get_analyzer
from analyzer.tools import is_tool_available, get_tool_version

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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
