"""C++(hedit.mll)の補完が使う、Pythonでしか分からない情報の窓口。

補完の判断・ファイルの読み取り・候補の絞り込みはC++(src/core/completion_engine.cpp)が行う。
ここは、実行中のPythonの状態(sys.path・sys.modules・組み込みの名前)をJSONで返すだけ。
Mayaのメインスレッドから呼ばれる。対象のモジュールをimport・reload・実行することはない。
"""
import builtins
import json
import keyword
import os
import sys
import types


def _search_paths():
    """list[str]: sys.pathの各フォルダー(絶対パス)。"""
    return [os.path.abspath(path or os.curdir) for path in sys.path if isinstance(path, str)]


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
            result[key] = {'members': _members(vars(value), depth + 1), 'detail': 'class ' + key}
        else:
            result[key] = {}
    return result


def _signature(module, namespace):
    """str: 公開名が変わったかを見分けるための印。

    名前・値の同一性(id)・クラスの中身の数から作る。公開名の辞書を作ってJSONにするより軽いので、
    C++は前回と同じ印なら前回の結果を使う(maya.cmdsは約4,700個の名前がある)。
    """
    parts = []
    for key, value in list(namespace.items()):
        if key.startswith('_'):
            continue
        parts.append((key, id(value), len(vars(value)) if isinstance(value, type) else -1))
    return '%d:%d' % (id(module), hash(tuple(parts)))


def module_info(name, known_signature=''):
    """str: 読み込み済みのモジュールの今の公開名とファイル(JSON)。

    Args:
        name (str): モジュール名。
        known_signature (str): C++が前回受け取った印。今の印と同じなら公開名を送らない。

    Returns:
        str: 読み込み済みなら ``{"loaded": true, "signature": "...", "members": {...}, "file": "..."}``。
        印が同じなら ``{"loaded": true, "unchanged": true}``。まだなら ``{"loaded": false}``。
        getattrを使わず``vars()``だけを読むので、属性の取得で動く処理は実行しない。
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
