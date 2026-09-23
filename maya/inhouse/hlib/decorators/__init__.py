"""デコレータ関連ユーティリティを公開するパッケージ。"""

from .selection import preserved_selection
from .undo import undo_chunk, undoable

__all__ = [
    "preserved_selection",
    "undo_chunk",
    "undoable",
]
