"""デコレータ関連ユーティリティを公開するパッケージ。"""

from .selection import preserved_selection
from .skin import preserved_skin_shape
from .undo import undo_chunk, undo_transaction

__all__ = [
    "preserved_selection",
    "preserved_skin_shape",
    "undo_chunk",
    "undo_transaction",
]

# 再読み込み時も旧デコレータ名を公開しない。
globals().pop("undoable", None)
