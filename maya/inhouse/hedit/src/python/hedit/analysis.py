"""Maya同梱Pythonでコードを実行せずに構文・コンパイラ警告を調べる。"""
import json
import warnings


def analyze(source):
    """100万文字超/2万行以上を省略。型推論・外部import・ユーザーコード実行なし。"""
    if len(source) > 1_000_000 or source.count('\n') >= 20_000:
        return json.dumps({'diagnostics': [], 'skipped': 'File too large (limit: 1,000,000 characters / 20,000 lines)'})
    diagnostics = []
    try:
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter('always', SyntaxWarning)
            # コンパイルだけ行う。生成したcodeオブジェクトは実行しない。
            compile(source, '<hedit>', 'exec', dont_inherit=True)
        for warning in captured:
            if issubclass(warning.category, SyntaxWarning):
                diagnostics.append({'severity': 'warning', 'line': warning.lineno,
                                    'message': str(warning.message)})
    except SyntaxError as exc:
        diagnostics.append({'severity': 'error', 'line': exc.lineno or 1,
                            'message': exc.msg})
    except (ValueError, RecursionError, MemoryError) as exc:
        return json.dumps({'diagnostics': [], 'skipped': 'Analysis unavailable: ' + str(exc)})
    return json.dumps({'diagnostics': diagnostics[:100]}, ensure_ascii=True)
