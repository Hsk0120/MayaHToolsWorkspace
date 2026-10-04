"""Maya 同梱の Python で、コードを実行せずに構文エラー・コンパイラの警告・未定義の名前を調べる(静的解析)。

C++(hedit.mll)が、入力が止まってから 0.8 秒後に :func:`analyze` を呼び、結果を問題一覧に出す。
"""
import ast
import builtins
import json
import symtable
import sys
import warnings

#: モジュールで最初から使える名前(組み込みの名前には含まれない)。
_MODULE_NAMES = frozenset([
    '__name__', '__file__', '__doc__', '__builtins__', '__spec__', '__loader__', '__package__',
    '__annotations__', '__path__', '__cached__', '__dict__',
])

#: 未定義の名前を報告する上限。
_MAXIMUM_UNDEFINED = 50


def analyze(source):
    """本文を ``compile()`` だけで確かめ、構文エラー・``SyntaxWarning``・未定義の名前を返す。

    コードは実行も import もしない。型などは調べない。
    100万文字を超える、または2万行以上の本文は調べずに省略する。

    Args:
        source (str): 調べる本文。

    Returns:
        str: JSON の文字列。``{"diagnostics": [{"severity": "error" | "warning", "line": 行番号,
        "message": 理由, "column": 桁(1始まり。無ければ0), "length": 文字数}]}``(最大100件)。
        調べなかった場合は ``{"diagnostics": [], "skipped": 理由}``。
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
                                    'message': str(warning.message), 'column': 0, 'length': 0})
    except SyntaxError as exc:
        diagnostics.append({'severity': 'error', 'line': exc.lineno or 1, 'message': exc.msg,
                            'column': exc.offset or 0, 'length': 1 if exc.offset else 0})
    except (ValueError, RecursionError, MemoryError) as exc:
        return json.dumps({'diagnostics': [], 'skipped': 'Analysis unavailable: ' + str(exc)})
    if not diagnostics or all(item['severity'] == 'warning' for item in diagnostics):
        try:
            diagnostics.extend(undefined_names(source))
        except (SyntaxError, ValueError, RecursionError, MemoryError):
            pass
    return json.dumps({'diagnostics': diagnostics[:100]}, ensure_ascii=True)


def undefined_names(source):
    """どこにも定義されていない名前の使用箇所を返す(pyflakes の「undefined name」に近いもの)。

    Python 標準の ``symtable`` で、各スコープの名前がグローバル(モジュールか組み込み)を探すものかを調べ、
    モジュールのどこにも定義が無く、組み込みの名前でもないものを報告する。誤検知を避けるため、次の場合は報告しない:

    * ``from X import *`` がある(どの名前が入るか分からない)
    * Maya の ``__main__`` に既にある名前(Script Editor や hedit で前に実行して定義した変数)
    * ``global`` で宣言して関数の中で代入している名前
    * スコープの対応が取れない書き方(対応が取れないスコープの中は調べない)

    Args:
        source (str): 構文エラーの無い本文。

    Returns:
        list[dict]: ``analyze`` と同じ形の指摘(``severity`` は ``warning``)。
    """
    tree = ast.parse(source, '<hedit>')
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(alias.name == '*' for alias in node.names):
            return []
    top = symtable.symtable(source, '<hedit>', 'exec')
    defined = set(dir(builtins)) | _MODULE_NAMES | set(_main_names())
    for symbol in top.get_symbols():
        if symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace() or symbol.is_parameter():
            defined.add(symbol.get_name())
    _collect_global_assignments(top, defined)
    results = []
    _check_scope(tree, top, defined, results)
    # ast の col_offset は UTF-8 のバイト数なので、文字数(C++ の桁)に直す。
    lines = source.split('\n')
    for item in results:
        text = lines[item['line'] - 1] if item['line'] <= len(lines) else ''
        prefix = text.encode('utf-8')[:item['column'] - 1].decode('utf-8', 'ignore')
        item['column'] = len(prefix) + 1
    results.sort(key=lambda item: (item['line'], item['column']))
    return results[:_MAXIMUM_UNDEFINED]


def _main_names():
    """Maya の ``__main__`` に今ある名前を返す。

    Returns:
        list[str]: 名前。``__main__`` が無ければ空。
    """
    main = sys.modules.get('__main__')
    return list(vars(main)) if main is not None else []


def _collect_global_assignments(table, defined):
    """関数の中で ``global x`` と宣言して代入している名前を、定義済みとして加える。

    Args:
        table (symtable.SymbolTable): 調べるスコープ。
        defined (set[str]): 加える先。
    """
    for child in table.get_children():
        for symbol in child.get_symbols():
            if symbol.is_declared_global() and symbol.is_assigned():
                defined.add(symbol.get_name())
        _collect_global_assignments(child, defined)


#: 新しいスコープを作る ast のノード(symtable の子テーブルに対応する)。
_SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda,
                ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _scope_name(node):
    """ノードに対応する symtable の子テーブルの名前を返す。

    Args:
        node (ast.AST): スコープを作るノード。

    Returns:
        str: ``FunctionDef`` などは関数名、ラムダは ``lambda``、内包表記は ``listcomp`` など。
    """
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    return {ast.Lambda: 'lambda', ast.ListComp: 'listcomp', ast.SetComp: 'setcomp',
            ast.DictComp: 'dictcomp', ast.GeneratorExp: 'genexpr'}[type(node)]


def _child_table(table, node, used):
    """ノードに対応する子テーブルを、名前と行番号で探す。

    Args:
        table (symtable.SymbolTable): 親のスコープ。
        node (ast.AST): スコープを作るノード。
        used (set[int]): 既に対応させた子テーブルの ``id``。

    Returns:
        symtable.SymbolTable | None: 見つかった子テーブル。対応が取れなければ None。
    """
    name = _scope_name(node)
    candidates = [child for child in table.get_children()
                  if child.get_name() == name and id(child) not in used]
    lines = {getattr(node, 'lineno', 0)}
    for decorator in getattr(node, 'decorator_list', []):
        lines.add(decorator.lineno)  # Python 3.7 の関数の行番号は、デコレーターの行のことがある。
    for child in candidates:
        if child.get_lineno() in lines:
            used.add(id(child))
            return child
    if len(candidates) == 1:
        used.add(id(candidates[0]))
        return candidates[0]
    return None


def _check_scope(node, table, defined, results):
    """スコープの中の名前の読み出しを調べ、未定義の名前を results に加える。

    Args:
        node (ast.AST): スコープのノード(モジュール・関数など)。
        table (symtable.SymbolTable): そのスコープのテーブル。
        defined (set[str]): モジュールで定義されている名前。
        results (list[dict]): 加える先。
    """
    used = set()
    pending = list(ast.iter_child_nodes(node))
    while pending:
        current = pending.pop(0)
        inlined = isinstance(current, (ast.ListComp, ast.SetComp, ast.DictComp)) and not any(
            child.get_name() == _scope_name(current) for child in table.get_children())
        if isinstance(current, _SCOPE_NODES) and not inlined:
            # デコレーター・既定値・親クラスは外側のスコープで評価される。
            # (Python 3.12 以降のリスト・集合・辞書の内包表記は、外側のスコープに含まれる(PEP 709)。)
            for outer in _outer_expressions(current):
                _check_scope_expression(outer, table, defined, results)
            child = _child_table(table, current, used)
            if child is not None and len(results) < _MAXIMUM_UNDEFINED:
                _check_scope(current, child, defined, results)
            continue
        if isinstance(current, ast.Name) and isinstance(current.ctx, ast.Load):
            _report_if_undefined(current, table, defined, results)
        pending.extend(ast.iter_child_nodes(current))


def _outer_expressions(node):
    """スコープを作るノードのうち、外側のスコープで評価される式を返す。

    Args:
        node (ast.AST): スコープを作るノード。

    Returns:
        list[ast.AST]: デコレーター・引数の既定値・親クラスなど。内包表記は最初の ``in`` の右辺。
    """
    expressions = list(getattr(node, 'decorator_list', []))
    if isinstance(node, ast.ClassDef):
        expressions += node.bases + [keyword.value for keyword in node.keywords]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        arguments = node.args
        expressions += [value for value in arguments.defaults if value is not None]
        expressions += [value for value in arguments.kw_defaults if value is not None]
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
        expressions.append(node.generators[0].iter)
    return expressions


def _check_scope_expression(expression, table, defined, results):
    """外側のスコープで評価される式の中の名前を調べる(中のラムダ・内包表記は調べない)。

    Args:
        expression (ast.AST): 式。
        table (symtable.SymbolTable): 外側のスコープのテーブル。
        defined (set[str]): モジュールで定義されている名前。
        results (list[dict]): 加える先。
    """
    pending = [expression]
    while pending:
        current = pending.pop()
        if isinstance(current, _SCOPE_NODES):
            continue
        if isinstance(current, ast.Name) and isinstance(current.ctx, ast.Load):
            _report_if_undefined(current, table, defined, results)
        pending.extend(ast.iter_child_nodes(current))


def _report_if_undefined(name_node, table, defined, results):
    """名前がグローバルを探すもので、どこにも定義が無ければ results に加える。

    Args:
        name_node (ast.Name): 読み出している名前。
        table (symtable.SymbolTable): その名前が使われているスコープ。
        defined (set[str]): モジュールで定義されている名前。
        results (list[dict]): 加える先。
    """
    name = name_node.id
    if name in defined or len(results) >= _MAXIMUM_UNDEFINED:
        return
    try:
        symbol = table.lookup(name)
    except KeyError:
        return
    if table.get_type() == 'module':
        unresolved = not (symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace())
    else:
        unresolved = symbol.is_global() and not symbol.is_local()
    if unresolved:
        results.append({'severity': 'warning', 'line': name_node.lineno,
                        'message': '"{}" is not defined'.format(name),
                        'column': name_node.col_offset + 1, 'length': len(name)})
