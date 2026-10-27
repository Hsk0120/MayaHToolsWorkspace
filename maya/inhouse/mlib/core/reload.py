"""パッケージ内の参照関係に従ってモジュールを再読み込みする。"""

import importlib
import pkgutil
import sys
import types

__all__ = ["reload_package"]


def reload_package(package_name):
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
    # 新規ファイルの発見をimport machineryへ通知する。各モジュール所有の
    # キャッシュはreload時に再生成し、ここに個別のキャッシュ一覧は持たない。
    importlib.invalidate_caches()
    module_names = _discover_module_names(package_name)
    loaded_names = {
        name
        for name in sys.modules
        if name == package_name or name.startswith(f"{package_name}.")
    }
    for stale_name in loaded_names - set(module_names):
        stale_module = sys.modules.pop(stale_name, None)
        parent_name, _, child_name = stale_name.rpartition(".")
        parent = sys.modules.get(parent_name)
        if (isinstance(stale_module, types.ModuleType) and parent is not None
                and getattr(parent, child_name, None) is stale_module):
            delattr(parent, child_name)
    for module_name in module_names:
        importlib.import_module(module_name)
    module_names = _reload_order(module_names)
    reloaded = []
    for module_name in module_names:
        module = sys.modules.get(module_name)
        if module is None:
            continue
        reloaded.append(importlib.reload(module))

    return tuple(reloaded)


def _discover_module_names(package_name):
    """パッケージ配下の現在存在する Python module 名を取得する。

    Args:
        package_name (str): module を走査する package の完全修飾名。

    Returns:
        tuple[str]: package 自身を含む検出済み module 名。
    """
    package = sys.modules[package_name]
    names = {package_name}
    for module_info in pkgutil.walk_packages(package.__path__, f"{package_name}."):
        names.add(module_info.name)
    return tuple(sorted(names))


def _reload_order(module_names):
    """module 内の参照から依存先を推定し、reload 順を作る。

    Args:
        module_names (iterable[str]): reload 対象の完全修飾 module 名。

    Returns:
        list[str]: 依存先が先になる reload 順の module 名。
    """
    module_set = set(module_names)
    dependencies = {
        name: _module_dependencies(sys.modules[name], module_set)
        for name in module_names
    }
    order = []
    visited = set()
    visiting = set()

    def visit(name):
        """依存先から再帰的に訪問し、再読み込み順を組み立てる。

        訪問済み、または現在訪問中なら処理を打ち切り、循環依存による無限再帰を避ける。

        Args:
            name (str): 訪問するモジュールの完全修飾名。

        Returns:
            None: 値を返さない。
        """
        if name in visited:
            return
        if name in visiting:
            return
        visiting.add(name)
        for dependency in sorted(dependencies[name]):
            visit(dependency)
        visiting.remove(name)
        visited.add(name)
        order.append(name)

    for name in sorted(module_names):
        visit(name)
    return order


def _module_dependencies(module, module_names):
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
    dependencies = set()
    for value in vars(module).values():
        if isinstance(value, types.ModuleType):
            owner = value.__name__
        else:
            owner = getattr(value, "__module__", None)
        if owner in module_names and owner != module.__name__:
            dependencies.add(owner)
            # `from ..maths import Matrix` のようにパッケージ経由で取り込んだ名前は、
            # 定義 module だけでなくその親パッケージ(__init__)も先に読み直す必要がある。
            package = owner.rpartition(".")[0]
            while package and package in module_names:
                if package != module.__name__ and not module.__name__.startswith(package + "."):
                    dependencies.add(package)
                package = package.rpartition(".")[0]
    return dependencies
