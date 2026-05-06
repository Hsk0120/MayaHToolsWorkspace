import contextlib
import functools

import maya.cmds as cmds


@contextlib.contextmanager
def undo_chunk(name=None):
    """複数の Maya 操作を 1 回の Undo チャンクにまとめます。"""
    opened = False
    try:
        kwargs = {"openChunk": True}
        if name:
            kwargs["chunkName"] = str(name)
        cmds.undoInfo(**kwargs)
        opened = True
        yield
    finally:
        if opened:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass


def undoable(name=None):
    """`undo_chunk` のデコレータ版を返します。"""

    def decorator(func):
        chunk_name = name or getattr(func, "__name__", "UndoChunk")

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with undo_chunk(chunk_name):
                return func(*args, **kwargs)

        return wrapper

    return decorator