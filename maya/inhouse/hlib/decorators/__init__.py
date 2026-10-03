"""デコレータ関連ユーティリティを公開するパッケージ。"""

from .nativeUnits import nativeUnits
from .selection import preservedSelection
from .skin import preservedSkinShape
from .undo import undoChunk, undoTransaction
from .viewport import viewportOff

__all__ = [
    "preservedSelection",
    "preservedSkinShape",
    "undoChunk",
    "undoTransaction",
    "viewportOff",
    "nativeUnits",
]

# 再読み込み時も旧デコレータ名を公開しない。
globals().pop("undoable", None)

# reload時にも廃止した公開名を残さない。
for _obsolete_name in ('native_units', 'preserved_selection', 'preserved_skin_shape', 'undo_chunk', 'undo_transaction', 'viewport_off'):
    globals().pop(_obsolete_name, None)
