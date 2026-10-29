# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""サブパッケージ・公開コマンドと再読み込みの入口を提供する。"""

from . import logger
from . import util, core, common, decorator, cmds, nodes, plugs, components, maths
from .core.registry import NodeRegistry as _NodeRegistry
from .core.reload import reload_package as _reload_package
from .cmds import createNode, delete, duplicate, getNode, getPlug, ls, select
from .core import extensions as _extensions
from typing import Any
from types import ModuleType

_node_registry: Any
_plug_registry: Any
__all__ = ['cmds', 'common', 'components', 'core', 'createNode', 'decorator', 'delete', 'duplicate', 'getNode', 'getPlug', 'logger', 'ls', 'maths', 'nodes', 'plugs', 'reload', 'select', 'util']
__version__: str

def reload() -> tuple[ModuleType]:
    """本体を再読み込みし、拡張を再探索して型登録を作り直す。

    宣言済み・読込み失敗の拡張モジュールを先に解除し、本体の再読込み中に拡張を再初期化する。
    外部SDKやMayaプラグイン自体は解除対象にしない。保持済みのクラス・関数・ラッパーは取り直す。
    拡張単位の読込み/登録失敗はcore.extensions.status()で確認する。途中状態の自動復元は保証しない。

    Returns:
        tuple[module]: 本体側で再読み込みしたモジュール群。拡張モジュールの一覧ではない。

    Raises:
        RuntimeError: 拡張初期化中の再入で、再読み込みを開始できない場合。
    """
    ...
