"""パッケージ内の参照関係に従ってモジュールを再読み込みする。"""

import importlib
import pkgutil
import sys
import types


def reload_package(package_name):
    """package_name 配下の Python module を検出し、依存順に再読み込みする。

    現在存在する module を package から走査するため、新しい wrapper の追加や
    既存 module の削除も反映できる。依存関係は各 module の globals にある
    class / function / module 参照から推定する。

    Args:
        package_name (str): 再読み込みする package の完全修飾名。

    Returns:
        tuple[module]: 再読み込みした module の tuple。
    """
    module_names = _discover_module_names(package_name)
    loaded_names = {
        name
        for name in sys.modules
        if name == package_name or name.startswith(package_name + ".")
    }
    for stale_name in loaded_names - set(module_names):
        sys.modules.pop(stale_name, None)
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
    for module_info in pkgutil.walk_packages(package.__path__, package_name + "."):
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
    """module の globals から Hlib 内の依存 module 名を抽出する。

    循環依存を避けるために関数内で遅延 import している参照（例: nodes.node と
    plugs.plug の相互参照）は module の globals に現れないため、ここでは検出でき
    ない。これらは reload 順序に影響しないが、実行時には呼び出しの都度その時点の
    sys.modules から解決されるため、reload 漏れにはならない。

    Args:
        module (types.ModuleType): 依存関係を調べる module。
        module_names (set[str]): reload 対象として許可する module 名。

    Returns:
        set[str]: module が参照している Hlib module 名。
    """
    dependencies = set()
    for value in vars(module).values():
        if isinstance(value, types.ModuleType):
            owner = value.__name__
        else:
            owner = getattr(value, "__module__", None)
        if owner in module_names and owner != module.__name__:
            dependencies.add(owner)
    return dependencies


__all__ = ["reload_package"]
