"""Maya の操作を Undo チャンクでまとめる。"""
import contextlib

import maya.cmds as cmds

# importlib.reloadでも廃止した公開名を残さない。
globals().pop("undoable", None)


@contextlib.contextmanager
def undo_chunk(name=None):
    """複数の Maya 操作を 1 回の Undo チャンクにまとめる。

    ``with undo_chunk("処理名"):`` と ``@undo_chunk("処理名")`` の両方で使用できる。
    デコレータには括弧が必要。関数の戻り値・メタデータを保持し、反復呼び出しも可能。

    チャンクを開いた場合は finally で閉じる。閉じる際の例外は抑制する。コンテキスト内部の例外は抑制せず、自動ロールバックもしない。

    Args:
        name (str | None): Maya Undo キューに表示するチャンク名。省略時は
            関数名を自動設定せず、Mayaの既定表示を使う。

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
