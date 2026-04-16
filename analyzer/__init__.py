from .base import BaseAnalyzer, AnalysisResult, Issue, DimensionScore
from .python import PythonAnalyzer
from .javascript import JavaScriptAnalyzer
from .java import JavaAnalyzer
from .go import GoAnalyzer

ANALYZERS = {
    'python': PythonAnalyzer,
    'javascript': JavaScriptAnalyzer,
    'java': JavaAnalyzer,
    'go': GoAnalyzer,
}

def get_analyzer(language):
    cls = ANALYZERS.get(language)
    if cls:
        return cls()
    return None
