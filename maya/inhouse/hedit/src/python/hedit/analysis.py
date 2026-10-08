"""Maya 同梱の Python で、コードを実行せずに構文エラー・コンパイラの警告・未定義の名前を調べる(静的解析)。

C++(hedit.mll)が、入力が止まってから 0.8 秒後に :func:`analyze` を呼び、結果を問題一覧に出す。
"""
import ast
import builtins
import collections
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
    tree = None
    try:
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter('always', SyntaxWarning)
            tree = _compile(source, captured)
        for warning in captured:
            if issubclass(warning.category, SyntaxWarning):
                diagnostics.append({'severity': 'warning', 'line': warning.lineno,
                                    'message': str(warning.message), 'column': 0, 'length': 0})
    except SyntaxError as exc:
        diagnostics.append({'severity': 'error', 'line': exc.lineno or 1, 'message': exc.msg,
                            'column': exc.offset or 0, 'length': 1 if exc.offset else 0})
    except (ValueError, RecursionError, MemoryError) as exc:
        return json.dumps({'diagnostics': [], 'skipped': 'Analysis unavailable: ' + str(exc)})
    # 構文木を作れなかった(入れ子が深すぎる)本文は、以前と同じく未定義の名前を調べない。
    if tree is not None and (not diagnostics or all(item['severity'] == 'warning' for item in diagnostics)):
        try:
            diagnostics.extend(undefined_names(source, tree))
        except (SyntaxError, ValueError, RecursionError, MemoryError):
            pass
    return json.dumps({'diagnostics': diagnostics[:100]}, ensure_ascii=True)


def _compile(source, captured):
    """本文の構文木を作り、それをコンパイルする(生成した code オブジェクトは実行しない)。

    構文木は1回だけ作り、コンパイルと未定義の名前の確認(:func:`undefined_names`)の両方に使う。
    パーサーの警告(不正なエスケープなど)は構文木を作るときに、コンパイラーの警告(定数との ``is`` など)は
    構文木からコンパイルするときに出るので、本文から直接コンパイルしたときと同じ警告が集まる。

    入れ子が深すぎて、構文木を Python のオブジェクトにできない、または構文木からコンパイルできない
    (Python 3.9・3.10 は、本文からならコンパイルできる深さでも失敗する)ときは、以前と同じく本文から直接コンパイルする。
    同じ警告が二重にならないよう、それまでに集めた警告は捨てる。

    Args:
        source (str): 調べる本文。
        captured (list): ``warnings.catch_warnings(record=True)`` が集めている警告。

    Returns:
        ast.Module | None: 構文木。作れなかったら None。

    Raises:
        SyntaxError: 構文エラー。
        ValueError: 本文に NUL 文字がある(Python 3.11 以前)。
        RecursionError: 本文から直接コンパイルしても、入れ子が深すぎた。
        MemoryError: 同上。
    """
    try:
        # ast.parse と同じだが、呼出し元の ``from __future__`` を引き継がない(dont_inherit)。
        tree = compile(source, '<hedit>', 'exec', ast.PyCF_ONLY_AST, dont_inherit=True)
    except (RecursionError, MemoryError):
        tree = None
    else:
        try:
            compile(tree, '<hedit>', 'exec', dont_inherit=True)
            return tree
        except (RecursionError, MemoryError):
            pass
    del captured[:]
    compile(source, '<hedit>', 'exec', dont_inherit=True)
    return tree


def undefined_names(source, tree=None):
    """どこにも定義されていない名前の使用箇所を返す(pyflakes の「undefined name」に近いもの)。

    Python 標準の ``symtable`` で、各スコープの名前がグローバル(モジュールか組み込み)を探すものかを調べ、
    モジュールのどこにも定義が無く、組み込みの名前でもないものを報告する。誤検知を避けるため、次の場合は報告しない:

    * ``from X import *`` がある(どの名前が入るか分からない)
    * Maya の ``__main__`` に既にある名前(Script Editor や hedit で前に実行して定義した変数)
    * ``global`` で宣言して関数の中で代入している名前
    * スコープの対応が取れない書き方(対応が取れないスコープの中は調べない)

    Args:
        source (str): 構文エラーの無い本文。
        tree (ast.Module | None): ``source`` の構文木(:func:`analyze` が作ったもの)。None なら作る。

    Returns:
        list[dict]: ``analyze`` と同じ形の指摘(``severity`` は ``warning``)。
    """
    if tree is None:
        tree = ast.parse(source, '<hedit>')
    if _has_star_import(tree):
        return []
    # 標準の symtable は構文木を受け取れないので、本文をもう一度解析する。
    # そのとき analyze で集めた警告(不正なエスケープなど)がもう一度出る。Python 3.12 以降は既定で
    # 表示されて Script Editor へ流れるため、ここでは捨てる。
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        top = symtable.symtable(source, '<hedit>', 'exec')
    # get_symbols() より前にまとめ、名前ごとの lookup() が子テーブルを毎回全部調べないようにする。
    children = _ChildTables(top)
    defined = set(dir(builtins)) | _MODULE_NAMES | set(_main_names())
    for symbol in top.get_symbols():
        if symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace() or symbol.is_parameter():
            defined.add(symbol.get_name())
    _collect_global_assignments(top, defined)
    results = []
    _check_scope(tree, top, defined, results, children)
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


class _ChildTables(object):
    """1つのスコープの子テーブルを、名前と行番号で引けるようにまとめたもの。

    ``get_children()`` は呼ぶたびに一覧を作り直し、``lookup()`` も名前ごとに子テーブルを全部調べる。
    ノードや名前ごとにそれらを呼ぶと、子の多いスコープ(トップレベルに内包表記の多いスクリプトなど)で
    行数の2乗に比例して遅くなるので、スコープごとに1回だけまとめる。
    子テーブルのオブジェクトはこのクラスが持ち続ける(symtable は弱参照で使い回すため、手放すと作り直される)。
    """

    def __init__(self, table):
        """子テーブルをまとめる。

        Args:
            table (symtable.SymbolTable): 親のスコープ。
        """
        #: 名前 → 子テーブル(``get_children()`` の順)。
        self._by_name = {}
        #: 名前 → {番号: 子テーブル}。まだノードに対応させていないもの(番号は ``get_children()`` の順)。
        self._unused = {}
        #: (名前, 行番号) → 子テーブルの番号(小さい順)。対応させたものは、先頭に来たときに取り除く。
        self._by_line = {}
        for index, child in enumerate(table.get_children()):
            name = child.get_name()
            self._by_name.setdefault(name, []).append(child)
            self._unused.setdefault(name, {})[index] = child
            self._by_line.setdefault((name, child.get_lineno()), collections.deque()).append(index)
        # 標準の symtable の lookup() は、名前ごとに子テーブルを全部調べる(非公開のメソッド)。同じ結果を
        # 名前から直接返す関数に差し替える。非公開の名前が将来変わっても、差し替えが使われないだけで結果は同じ。
        if hasattr(table, '_SymbolTable__check_children'):
            table._SymbolTable__check_children = self.namespaces

    def __contains__(self, name):
        """同じ名前の子テーブルがあるか(対応させ済みのものも含む)。

        Args:
            name (str): 子テーブルの名前。

        Returns:
            bool: あれば True。
        """
        return name in self._by_name

    def namespaces(self, name):
        """名前と同じ名前の子テーブルを返す(symtable の ``lookup()`` が使う)。

        Args:
            name (str): 名前。

        Returns:
            list[symtable.SymbolTable]: 子テーブル(``get_children()`` の順)。無ければ空。
        """
        return list(self._by_name.get(name, ()))

    def take(self, name, lines):
        """ノードに対応する子テーブルを取り出す。一度取り出した子テーブルは、もう返さない。

        Args:
            name (str): 子テーブルの名前(:func:`_scope_name`)。
            lines (set[int]): ノードの行番号(デコレーターの行を含む)。

        Returns:
            symtable.SymbolTable | None: まだ取り出していない同じ名前の子テーブルのうち、行番号が合う最初のもの。
            合うものが無く、同じ名前の子テーブルが1つだけ残っていればそれ。どちらでもなければ None。
        """
        unused = self._unused.get(name)
        if not unused:
            return None
        found = None
        for line in lines:
            indices = self._by_line.get((name, line))
            while indices and indices[0] not in unused:
                indices.popleft()  # 取り出し済みの子テーブル(取り出したときではなく、先頭に来たときに除く)。
            if indices and (found is None or indices[0] < found):
                found = indices[0]
        if found is None:
            if len(unused) != 1:
                return None
            found = next(iter(unused))
        return unused.pop(found)


def _child_table(children, node):
    """ノードに対応する子テーブルを、名前と行番号で探す。

    Args:
        children (_ChildTables): 親のスコープの子テーブル。
        node (ast.AST): スコープを作るノード。

    Returns:
        symtable.SymbolTable | None: 見つかった子テーブル。対応が取れなければ None。
    """
    lines = {getattr(node, 'lineno', 0)}
    for decorator in getattr(node, 'decorator_list', []):
        lines.add(decorator.lineno)  # Python 3.7 の関数の行番号は、デコレーターの行のことがある。
    return children.take(_scope_name(node), lines)


def _check_scope(node, table, defined, results, children=None):
    """スコープの中の名前の読み出しを調べ、未定義の名前を results に加える。

    Args:
        node (ast.AST): スコープのノード(モジュール・関数など)。
        table (symtable.SymbolTable): そのスコープのテーブル。
        defined (set[str]): モジュールで定義されている名前。
        results (list[dict]): 加える先。
        children (_ChildTables | None): ``table`` の子テーブル。None なら作る。
    """
    if children is None:
        children = _ChildTables(table)
    # 幅優先で順にたどる。list.pop(0) は要素数に比例して遅いので deque を使う。
    pending = collections.deque(_child_nodes(node))
    while pending:
        current = pending.popleft()
        inlined = isinstance(current, (ast.ListComp, ast.SetComp, ast.DictComp)) and \
            _scope_name(current) not in children
        if isinstance(current, _SCOPE_NODES) and not inlined:
            # デコレーター・既定値・親クラスは外側のスコープで評価される。
            # (Python 3.12 以降のリスト・集合・辞書の内包表記は、外側のスコープに含まれる(PEP 709)。)
            for outer in _outer_expressions(current):
                _check_scope_expression(outer, table, defined, results)
            child = _child_table(children, current)
            if child is not None and len(results) < _MAXIMUM_UNDEFINED:
                _check_scope(current, child, defined, results)
            continue
        if isinstance(current, ast.Name) and isinstance(current.ctx, ast.Load):
            _report_if_undefined(current, table, defined, results)
        pending.extend(_child_nodes(current))


#: 子ノードとしてたどらないフィールド(読み書きの別・演算子)。中に名前もスコープも無い。
_LEAF_FIELDS = frozenset(['ctx', 'op', 'ops'])


def _child_nodes(node):
    """``ast.iter_child_nodes`` と同じ順で子ノードを返す。ただし読み書きの別・演算子のノードは除く。

    名前の読み出しを探すだけなので、``Load``・``Add`` などの中身の無いノードはたどらなくてよい
    (たどるノードが約3割減る)。

    Args:
        node (ast.AST): ノード。

    Returns:
        list[ast.AST]: 子ノード。
    """
    children = []
    for field in node._fields:
        if field in _LEAF_FIELDS:
            continue
        value = getattr(node, field, None)
        if isinstance(value, ast.AST):
            children.append(value)
        elif isinstance(value, list):
            children.extend(item for item in value if isinstance(item, ast.AST))
    return children


def _has_star_import(tree):
    """``from X import *`` があるかを返す。

    コンパイルできる本文では ``import *`` はモジュールの直下(``if``・``try`` などの中を含む)にしか書けない
    (関数・クラスの中は構文エラー)。そのため文だけをたどり、式・関数・クラスの中は見ない。

    Args:
        tree (ast.Module): 構文木。

    Returns:
        bool: あれば True。
    """
    pending = [tree]
    while pending:
        node = pending.pop()
        if isinstance(node, ast.ImportFrom):
            if any(alias.name == '*' for alias in node.names):
                return True
            continue
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, (ast.expr, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                pending.append(child)
    return False


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
        pending.extend(_child_nodes(current))


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
