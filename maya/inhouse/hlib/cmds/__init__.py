"""ファイル名と同名の関数を自動公開する hlib コマンドパッケージ。

直下の公開 Python モジュールを対象とし、そのモジュールで定義された
同名の関数を公開する。非公開モジュールとサブパッケージは対象外。
"""

import importlib as _importlib
import inspect as _inspect
import pkgutil as _pkgutil

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
        # import が親パッケージに設定したモジュール属性も公開しない。
        globals().pop(_info.name, None)


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
