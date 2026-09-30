"""ファイル名と同名の関数を自動公開する hlib コマンドパッケージ。

直下の公開 Python モジュールを対象とし、そのモジュールで定義された
同名の関数を公開する。非公開モジュールとサブパッケージは対象外。
"""

import importlib as _importlib
import inspect as _inspect
import pkgutil as _pkgutil
from typing import TYPE_CHECKING

# reload 時には、削除・改名されたコマンドの公開名も取り除く。
for _name in globals().get("__all__", ()):
    globals().pop(_name, None)

_importlib.invalidate_caches()
__all__ = []
for _info in sorted(_pkgutil.iter_modules(__path__), key=lambda item: item.name):
    if _info.ispkg or _info.name.startswith("_"):
        continue
    _module = _importlib.import_module(f"{__name__}.{_info.name}")
    # 同名関数が未定義でも reload の依存順を維持する。
    globals()["_command_module_" + _info.name] = _module
    _function = getattr(_module, _info.name, None)
    if _inspect.isfunction(_function) and _function.__module__ == _module.__name__:
        globals()[_info.name] = _function
        __all__.append(_info.name)
    else:
        # import が親パッケージに設定したモジュールアトリビュートも公開しない。
        globals().pop(_info.name, None)

# 静的解析(Pylance/pyright)向けの宣言。実行時には評価されず、上記の動的公開が実体。
# 公開名の一覧との一致は test_typing_exports.py が検証する。
if TYPE_CHECKING:
    from .createNurbs import createNurbs
    from .createCurve import createCurve
    from .addAttr import addAttr
    from .executeDeferred import executeDeferred
    from .getAttr import getAttr
    from .createIkHandle import createIkHandle
    from .makeIdentity import makeIdentity
    from .createPolygon import createPolygon
    from .reorder import reorder
    from .createSet import createSet
    from .bakeResults import bakeResults
    from .captureSelection import captureSelection
    from .getChannelBox import getChannelBox
    from .addConstraint import addConstraint
    from .createNode import createNode
    from .delete import delete
    from .getDrivenKey import getDrivenKey
    from .duplicate import duplicate
    from .createGroup import createGroup
    from .ls import ls
    from .getNode import getNode
    from .getOutliner import getOutliner
    from .getPlug import getPlug
    from .requirePlugins import requirePlugins
    from .getScene import getScene
    from .select import select
    from .getTimeSlider import getTimeSlider
    from .getViewport import getViewport


def _prepare_reload():
    """再読み込み前に前回公開した関数の定義を取り除く。

    importlib.reload はモジュール辞書を保持するため、ソースから削除された
    関数が残らないようにする。公開済みの参照は依存順の判定まで保持する。

    Returns:
        None: 値を返さない。
    """
    for name in __all__:
        function = globals()[name]
        module = _importlib.import_module(function.__module__)
        module.__dict__.pop(name, None)
