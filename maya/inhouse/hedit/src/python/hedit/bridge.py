"""Mayaメインスレッド専用。補完のためのeval/importは行わない。"""
import json
import os
import sys
import types
from .completion import Index

_index = None


def runtime_module(name):
    """対象モジュールの現在の公開名だけ取得。import/reload/getattrは行わない。"""
    module = sys.modules.get(name)
    if not isinstance(module, types.ModuleType):
        return None
    def members(mapping, depth=0):
        result = {}
        for key, value in list(mapping.items()):
            if key.startswith('_'):
                continue
            if isinstance(value, types.ModuleType):
                result[key] = {'target': vars(value).get('__name__', '')}
            elif isinstance(value, type) and depth < 1:
                result[key] = {'members': members(vars(value), depth + 1), 'detail': 'class ' + key}
            else:
                result[key] = {}
        return result
    return members(vars(module)), vars(module).get('__file__', '')


def configuration():
    """有効な検索パスとロード済みモジュールの実在する名前を渡す。"""
    global _index
    # 全モジュールの全属性をJSON化しない。公開名は補完対象だけを取得する。
    modules = {name: {} for name in sys.modules}
    data = {
        "paths": [os.path.abspath(p or os.curdir) for p in sys.path if isinstance(p, str)],
        "modules": modules,
    }
    # 過去の公開名を固定せず、補完対象ごとに現在の状態を読む。
    _index = Index(data["paths"], modules=modules, runtime=runtime_module)
    return json.dumps({'ready': True})


def module_names():
    """str: C++のimport補完へ渡す検索パスと、組み込み・読み込み済みのトップレベル名(JSON)。

    sys.pathのフォルダー走査はC++(src/core/module_scanner.cpp)がGILを取らないスレッドで行う。
    """
    paths = [os.path.abspath(p or os.curdir) for p in sys.path if isinstance(p, str)]
    names = set(sys.builtin_module_names)
    names.update(name.split('.')[0] for name in list(sys.modules))
    return json.dumps({'paths': paths, 'names': sorted(names)}, ensure_ascii=True)


def complete(source):
    """Mayaの同一プロセス内で候補を返す。補完対象はimportしない。"""
    try:
        if _index is None:
            configuration()
        if _index.runtime:
            _index.paths = [os.path.abspath(p or os.curdir) for p in sys.path if isinstance(p, str)]
            _index.modules = {name: {} for name in sys.modules}
        items = _index.complete(source)
        return json.dumps({'items': items, 'pending': False}, ensure_ascii=True)
    except Exception as exc:
        return json.dumps({'error': str(exc)}, ensure_ascii=True)
