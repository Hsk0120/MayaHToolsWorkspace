"""Maya 同梱の Python で、コードを実行せずに構文エラーとコンパイラの警告を調べる(静的解析)。

C++(hedit.mll)が、入力が止まってから 0.8 秒後に :func:`analyze` を呼び、結果を問題一覧に出す。
"""
import json
import warnings


def analyze(source):
    """本文を ``compile()`` だけで確かめ、構文エラーと ``SyntaxWarning`` を返す。

    コードは実行も import もしない。型・未定義の名前などは調べない。
    100万文字を超える、または2万行以上の本文は調べずに省略する。

    Args:
        source (str): 調べる本文。

    Returns:
        str: JSON の文字列。``{"diagnostics": [{"severity": "error" | "warning", "line": 行番号, "message": 理由}]}``
        (最大100件)。調べなかった場合は ``{"diagnostics": [], "skipped": 理由}``。
    """
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
