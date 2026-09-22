"""Maya の操作を Undo チャンクでまとめる。"""
import contextlib
import functools

import maya.cmds as cmds


@contextlib.contextmanager
def undo_chunk(name=None):
    """複数の Maya 操作を 1 回の Undo チャンクにまとめる。

    チャンクを開いた場合は finally で閉じる。閉じる際の例外は抑制する。コンテキスト内部の例外は抑制せず、自動ロールバックもしない。

    Args:
        name (str | None): Maya Undo キューに表示するチャンク名。

    Yields:
        None: コンテキスト内で実行した Maya 操作を同じ Undo として扱う。
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
    """関数を Maya の単一 Undo チャンクで実行するデコレータを返す。

    Args:
        name (str | None): Undo チャンク名。省略時は関数名を使用する。

    Returns:
        Callable: 対象関数をラップするデコレータ。
    """

    def decorator(func):
        """関数を単一 Undo チャンクで呼び出すラッパーを作成する。

        Args:
            func (Callable): ラップする関数。

        Returns:
            Callable: 元の関数情報を functools.wraps で保持した関数。
        """
        chunk_name = name or getattr(func, "__name__", "UndoChunk")

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            """Undo チャンク内で元の関数を実行する。

            元の関数の例外は呼び出し元へ伝播する。完了済みの操作を自動で Undo する処理はない。

            Args:
                *args (object): 元の関数に渡す位置引数。
                **kwargs (object): 元の関数に渡すキーワード引数。

            Returns:
                object: 元の関数の戻り値。
            """
            with undo_chunk(chunk_name):
                return func(*args, **kwargs)

        return wrapper

    return decorator