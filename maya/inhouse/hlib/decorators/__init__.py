"""デコレータ関連ユーティリティを公開するパッケージ。"""

from .selection import preserved_selection
from .undo import undo_chunk

__all__ = [
    "preserved_selection",
    "undo_chunk",
]

# 再読み込み時も旧デコレータ名を公開しない。
globals().pop("undoable", None)
