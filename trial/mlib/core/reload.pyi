# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""パッケージ内の参照関係に従ってモジュールを再読み込みする。"""

import importlib
import pkgutil
import sys
import types
from typing import Iterable
from types import ModuleType

__all__ = ['reload_package']

def reload_package(package_name: str) -> tuple[ModuleType]:
    """読み込み済みパッケージの現存モジュールを再探索し、推定した依存順で再読み込みする。

    新規モジュールを取り込み、削除済みはsys.modulesと親の同一モジュール属性から除く。
    依存順はglobalsのモジュール/クラス/関数参照から推定し、関数内の遅延importは検出しない。
    利用側のfrom-importや保持済みインスタンスは差し替えない。再読込み後は必要な参照を取り直す。
    既存モジュール辞書に残る削除済み定義まで一律に消す処理ではなく、途中失敗の自動復元も行わない。

    Args:
        package_name (str): 読み込み済みパッケージの完全修飾名。

    Returns:
        tuple[module]: 再読み込みしたモジュールを処理順に格納したtuple。
    """
    ...

def _discover_module_names(package_name: str) -> tuple[str]:
    """パッケージ配下の現在存在する Python module 名を取得する。

    Args:
        package_name (str): module を走査する package の完全修飾名。

    Returns:
        tuple[str]: package 自身を含む検出済み module 名。
    """
    ...

def _reload_order(module_names: Iterable[str]) -> list[str]:
    """module 内の参照から依存先を推定し、reload 順を作る。

    Args:
        module_names (iterable[str]): reload 対象の完全修飾 module 名。

    Returns:
        list[str]: 依存先が先になる reload 順の module 名。
    """
    ...

def _module_dependencies(module: types.ModuleType, module_names: set[str]) -> set[str]:
    """module の globals から mlib 内の依存 module 名を抽出する。

    循環依存を避けるために関数内で遅延 import している参照(例: nodes.node と
    plugs.plug の相互参照)は module の globals に現れないため、ここでは検出でき
    ない。これらは reload 順序に影響しないが、実行時には呼び出しの都度その時点の
    sys.modules から解決されるため、reload 漏れにはならない。

    Args:
        module (types.ModuleType): 依存関係を調べる module。
        module_names (set[str]): reload 対象として許可する module 名。

    Returns:
        set[str]: module が参照している mlib module 名。
    """
    ...
