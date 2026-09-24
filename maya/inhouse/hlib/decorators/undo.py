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


@contextlib.contextmanager
def undo_transaction(name=None):
    """例外発生時に自動でロールバックする Undo トランザクション。

    ``with undo_transaction("処理名"):`` と ``@undo_transaction("処理名")`` の
    両方で使用できる。デコレータには括弧が必要。

    ブロック内で例外が発生した場合、チャンクを閉じたうえで ``cmds.undo()`` を
    1回実行してブロック内の変更を全て巻き戻してから、元の例外をそのまま
    再送出する。正常終了時はロールバックせず、undo_chunk と同様に1回の
    Undo にまとまったチャンクとして履歴に残る。

    チャンク内で実際の変更が一件も無いまま例外になった場合、``cmds.undo()``
    は空のチャンクを素通りして本トランザクションと無関係な直前の操作を
    巻き戻してしまう(Maya の undo キューの既定挙動)。これを避けるため、
    ロールバック直前に軽量なダミーノードを作成・削除してチャンクへ必ず
    1件の Undo エントリを積んでから閉じる。

    Args:
        name (str | None): Maya Undo キューに表示するチャンク名。省略時は
            関数名を自動設定せず、Mayaの既定表示を使う。

    Yields:
        None: コンテキスト内で実行した Maya 操作を同じ Undo として扱う。

    Raises:
        Exception: ブロック内で送出された例外は、ロールバック後にそのまま再送出する。
    """
    kwargs = {"openChunk": True}
    if name:
        kwargs["chunkName"] = str(name)
    cmds.undoInfo(**kwargs)
    try:
        yield
    except BaseException:
        try:
            guard = cmds.createNode("network", skipSelect=True)
            cmds.delete(guard)
        except Exception:
            pass
        try:
            cmds.undoInfo(closeChunk=True)
        except Exception:
            pass
        try:
            cmds.undo()
        except Exception:
            pass
        raise
    else:
        cmds.undoInfo(closeChunk=True)
