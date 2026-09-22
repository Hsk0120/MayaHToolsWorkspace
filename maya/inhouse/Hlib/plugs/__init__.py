"""属性ラッパーを検出して公開する。"""

from ..core.discovery import discover_plug_package
from .plug import Plug
from .array_plug import ArrayPlug
from .compound_plug import CompoundPlug

# Plug/ArrayPlug/CompoundPlug は他モジュールからの型参照（isinstance 判定や基底クラス
# としての利用）が多いため明示 import する。bool/double3/matrix などの具象 wrapper は
# 明示 import せず、discover_plug_package の pkgutil スキャンだけで検出・公開する
# （新規ファイル追加時に __init__.py の編集が不要という設計のため）。
for _export_name in globals().get("_discovered_exports", {}):
    globals().pop(_export_name, None)
_discovered_wrappers, _discovered_exports = discover_plug_package(__name__)
globals().update(_discovered_exports)

__all__ = [
    "Plug",
    "ArrayPlug",
    "CompoundPlug",
    *sorted(_discovered_exports),
]
