"""C++(hedit.mll)の補完が使う、Pythonでしか分からない情報の窓口。

補完の判断・ファイルの読み取り・候補の絞り込みはC++(src/core/completion_engine.cpp)が行う。
ここは、実行中のPythonの状態(sys.path・sys.modules・組み込みの名前)と、ホバーに出す
ソースの無い名前のdocstring(:func:`describe`)をJSONで返すだけ。
Mayaのメインスレッドから呼ばれる。対象のモジュールをimport・reload・実行することはない。
"""
import builtins
import inspect
import json
import keyword
import os
import sys
import types


def safe_call(function, *args):
    """関数を呼び、例外が起きたら理由を JSON で返す(C++ からの呼出しは全てこれを通す)。

    例外を Script Editor へ流すと、補完のたびに同じエラーが出続けるうえ、hedit からは失敗が分からない。
    ここで受け止めて ``{"error": "..."}`` を返し、C++ がステータスバーに出す。

    Args:
        function (callable): 呼ぶ関数(``hedit.bridge.module_info`` など)。
        *args: 関数へ渡す引数。

    Returns:
        str: 関数の戻り値(JSON)。例外が起きたら ``{"error": "例外の型: 内容"}``。
    """
    try:
        return function(*args)
    except Exception as error:  # noqa: BLE001 (理由を C++ へ返すため、全ての例外を受け止める)
        return json.dumps({'error': '%s: %s' % (type(error).__name__, error)})


def _search_paths():
    """list[str]: sys.pathの各フォルダー(絶対パス)。"""
    return [os.path.abspath(path or os.curdir) for path in sys.path if isinstance(path, str)]


def _class_namespace(cls):
    """クラスの名前を、親クラスから受け継いだものも含めて集める(``dir()`` と同じ順の優先度)。

    ``vars()`` を親クラスから順に重ねるだけで、属性を取得しない(property などは実行しない)。
    ``object`` 自身の名前は含めない。

    Args:
        cls (type): クラス。

    Returns:
        dict: 名前 → 値。子クラスの名前を優先する。
    """
    namespace = {}
    for klass in reversed(getattr(cls, '__mro__', (cls,))):
        if klass is object:
            continue
        namespace.update(vars(klass))
    return namespace


def _members(mapping, depth=0):
    """モジュールやクラスの公開名を、補完用の辞書にする。

    Args:
        mapping (dict): ``vars(module)``や``vars(cls)``。
        depth (int): クラスの中身をたどった深さ。クラスの中のクラスはたどらない。

    Returns:
        dict: 名前 → ``{'target': モジュール名}``・``{'members': {...}, 'detail': 'class 名前'}``・``{}``。
    """
    result = {}
    for key, value in list(mapping.items()):
        if key.startswith('_'):
            continue
        if isinstance(value, types.ModuleType):
            result[key] = {'target': vars(value).get('__name__', '')}
        elif isinstance(value, type) and depth < 1:
            result[key] = {'members': _members(_class_namespace(value), depth + 1), 'detail': 'class ' + key}
        else:
            result[key] = {}
    return result


def _signature(module, namespace):
    """公開名が変わったかを見分けるための印を作る。

    名前・値の同一性(id)・クラスの中身の数から作る。公開名の辞書を作ってJSONにするより軽いので、
    C++は前回と同じ印なら前回の結果を使う(maya.cmdsは約4,700個の名前がある)。

    Args:
        module (module): モジュール。
        namespace (dict): ``vars(module)``。

    Returns:
        str: 印。
    """
    parts = []
    for key, value in list(namespace.items()):
        if key.startswith('_'):
            continue
        parts.append((key, id(value), len(vars(value)) if isinstance(value, type) else -1))
    return '%d:%d' % (id(module), hash(tuple(parts)))


def module_info(name, known_signature=''):
    """読み込み済みのモジュールの今の公開名とファイルを返す。

    getattr を使わず ``vars()`` だけを読むので、属性の取得で動く処理は実行しない。

    Args:
        name (str): モジュール名。
        known_signature (str): C++が前回受け取った印。今の印と同じなら公開名を送らない。

    Returns:
        str: 読み込み済みなら ``{"loaded": true, "signature": "...", "members": {...}, "file": "..."}``。
        印が同じなら ``{"loaded": true, "unchanged": true}``。まだなら ``{"loaded": false}``。
    """
    module = sys.modules.get(name)
    if not isinstance(module, types.ModuleType):
        return json.dumps({'loaded': False})
    namespace = vars(module)
    signature = _signature(module, namespace)
    if signature == known_signature:
        return json.dumps({'loaded': True, 'unchanged': True})
    filename = namespace.get('__file__') or ''
    return json.dumps({'loaded': True, 'signature': signature, 'members': _members(namespace), 'file': filename},
                      ensure_ascii=True)


def _function_signature(name, function, drop_first=False):
    """関数の見出し(``def name(a, b=1)``)を作る。

    Args:
        name (str): 表示する名前。
        function (object): 関数。
        drop_first (bool): True なら最初の引数(``self``)を除く(クラスの ``__init__`` 用)。

    Returns:
        str: 見出し。引数が分からなければ ``def name(...)``。
    """
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return 'def %s(...)' % name
    if drop_first:
        parameters = list(signature.parameters.values())[1:]
        signature = signature.replace(parameters=parameters)
    return 'def %s%s' % (name, signature)


def describe(module_name, path):
    """読み込み済みのモジュールの中の名前の、見出しとdocstringを返す(ホバー用)。

    ``vars()`` で名前をたどるだけで、属性の取得で動く処理(property など)は実行しない。
    ソースの無い名前(C の拡張・``maya.cmds`` など)の説明に使う。

    Args:
        module_name (str): モジュール名。
        path (list[str]): モジュールの中の位置(``["Class", "method"]``)。空ならモジュール自身。

    Returns:
        str: 見つかれば ``{"found": true, "signature": "...", "doc": "..."}``、無ければ ``{"found": false}`` の JSON。
    """
    value = sys.modules.get(module_name)
    if not isinstance(value, types.ModuleType):
        return json.dumps({'found': False})
    for part in path:
        # クラスは親クラスから受け継いだ名前もたどる(推論した変数のメソッドが、親クラスにある場合)。
        namespace = _class_namespace(value) if isinstance(value, type) else (
            vars(value) if isinstance(value, types.ModuleType) else {})
        if part not in namespace:
            return json.dumps({'found': False})
        value = namespace[part]
    name = path[-1] if path else module_name
    if isinstance(value, (staticmethod, classmethod)):
        value = value.__func__
    signature = ''
    doc = None
    if isinstance(value, types.ModuleType):
        signature = 'module ' + module_name
        doc = vars(value).get('__doc__')
    elif isinstance(value, type):
        signature = 'class ' + name
        doc = vars(value).get('__doc__')
        init = vars(value).get('__init__')
        if isinstance(init, types.FunctionType):
            signature = 'class ' + _function_signature(name, init, drop_first=True)[4:]
    elif isinstance(value, property):
        signature = 'property ' + name
        doc = value.__doc__
    elif isinstance(value, (types.FunctionType, types.BuiltinFunctionType, types.MethodDescriptorType)):
        signature = _function_signature(name, value)
        doc = value.__doc__
    else:
        return json.dumps({'found': False})
    doc = inspect.cleandoc(doc) if isinstance(doc, str) else ''
    return json.dumps({'found': True, 'signature': signature, 'doc': doc}, ensure_ascii=True)


_MISSING = object()
_saved_main_files = []


def push_main_file(path):
    """``__main__.__file__`` を一時的にスクリプトのパスにする(保存済みのタブを実行する前に C++ が呼ぶ)。

    Args:
        path (str): 実行するスクリプトのパス。

    Returns:
        str: 常に ``"{}"``(C++ への戻り値の形をそろえるため)。
    """
    import __main__
    _saved_main_files.append(vars(__main__).get('__file__', _MISSING))
    __main__.__file__ = path
    return '{}'


def pop_main_file():
    """``push_main_file`` で変えた ``__main__.__file__`` を元に戻す(実行の後に C++ が呼ぶ)。

    Returns:
        str: 常に ``"{}"``。
    """
    import __main__
    if not _saved_main_files:
        return '{}'
    previous = _saved_main_files.pop()
    if previous is _MISSING:
        vars(__main__).pop('__file__', None)
    else:
        __main__.__file__ = previous
    return '{}'


def search_paths():
    """str: sys.pathの各フォルダー(JSONの配列)。"""
    return json.dumps(_search_paths(), ensure_ascii=True)


def environment():
    """str: 名前の補完に使う、組み込みの名前と予約語(JSON)。"""
    return json.dumps({'builtins': sorted(vars(builtins)), 'keywords': list(keyword.kwlist)}, ensure_ascii=True)


def module_names():
    """str: C++のimport補完へ渡す検索パスと、組み込み・読み込み済みのトップレベル名(JSON)。

    sys.pathのフォルダー走査はC++(src/core/module_scanner.cpp)がGILを取らないスレッドで行う。
    """
    names = set(sys.builtin_module_names)
    names.update(name.split('.')[0] for name in list(sys.modules))
    return json.dumps({'paths': _search_paths(), 'names': sorted(names)}, ensure_ascii=True)
