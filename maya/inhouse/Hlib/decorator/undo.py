import contextlib
import functools

import maya.cmds as cmds


@contextlib.contextmanager
def undo_chunk(name=None):
    """Group operations into a single Maya undo step.

    Usage:
        with undo_chunk("MyTool"):
            # multiple cmds.* calls
            pass
    """
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
    """Decorator form of :func:`undo_chunk`.

    Usage:
        @undoable()
        def build():
            ...

        @undoable("Build Controller")
        def build2():
            ...
    """

    def decorator(func):
        chunk_name = name or getattr(func, "__name__", "UndoChunk")

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with undo_chunk(chunk_name):
                return func(*args, **kwargs)

        return wrapper

    return decorator