"""Maya の操作を Undo チャンクでまとめる。"""

import contextlib
from contextvars import ContextVar

import maya.cmds as cmds

from ._fast import is_fast

# importlib.reloadでも廃止した公開名を残さない。
globals().pop("undoable", None)
_chunk_active = ContextVar("hlib_undo_chunk_active", default=False)


@contextlib.contextmanager
def undoChunk(name=None):
    """複数の Maya 操作を 1 回の Undo チャンクにまとめる。

    ``with undoChunk("処理名"):`` と ``@undoChunk("処理名")`` の両方で使用できる。
    デコレータには括弧が必要。関数の戻り値・メタデータを保持し、反復呼び出しも可能。

    チャンクを開いた場合は finally で閉じる。閉じる際の例外は抑制する。コンテキスト内部の例外は抑制せず、自動ロールバックもしない。

    入れ子の通常チャンクは外側へまとめ、名前も外側を使う。
    undoTransaction の独立したチャンクは省略しない。
    Undo非対応の操作やfast=Trueの直接更新を取り消せるようにはしない。

    Args:
        name (str | None): Maya Undo キューに表示するチャンク名。省略時は
            関数名を自動設定せず、Mayaの既定表示を使う。

    Yields:
        None: コンテキスト内で実行した Maya 操作を同じ Undo として扱う。
    """
    if is_fast() or _chunk_active.get():
        yield
        return
    opened = False
    token = None
    try:
        kwargs = {"openChunk": True}
        if name:
            kwargs["chunkName"] = str(name)
        cmds.undoInfo(**kwargs)
        opened = True
        token = _chunk_active.set(True)
        yield
    finally:
        if token is not None:
            _chunk_active.reset(token)
        if opened:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception as exc:
                from ..utils import logger
                logger.warning("Undo chunk close failed: %s", exc)


@contextlib.contextmanager
def undoTransaction(name=None):
    """例外発生時に自動でロールバックする Undo トランザクション。

    ``with undoTransaction("処理名"):`` と ``@undoTransaction("処理名")`` の
    両方で使用できる。デコレータには括弧が必要。

    ブロック内で例外が発生した場合、チャンクを閉じたうえで ``cmds.undo()`` を
    1回実行してブロック内のUndo対象操作を巻き戻してから、元の例外をそのまま
    再送出する。正常終了時はロールバックせず、undoChunk と同様に1回の
    Undo にまとまったチャンクとして履歴に残る。

    Undoが有効であることが前提。fast=True・ファイル操作等は巻き戻せない。
    ガード作成・チャンク終了・undoの失敗は警告し、元の例外を優先するため、
    ロールバック完了を保証するものではない。

    チャンク内で実際の変更が一件も無いまま例外になった場合、``cmds.undo()``
    は空のチャンクを素通りして本トランザクションと無関係な直前の操作を
    巻き戻してしまう(Maya の undo キューの既定挙動)。これを避けるため、
    ロールバック直前に軽量なダミーノードを作成・削除してチャンクへ必ず
    1件の Undo エントリを積んでから閉じる。ガード作成またはチャンク終了が
    失敗した場合、無関係な履歴の巻き戻しを避けるためundoは実行しない。

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
        guard_created = False
        closed = False
        try:
            guard = cmds.createNode("network", skipSelect=True)
            guard_created = True
            cmds.delete(guard)
        except Exception as exc:
            from ..utils import logger
            logger.warning("Undo guard creation failed: %s", exc)
        try:
            cmds.undoInfo(closeChunk=True)
            closed = True
        except Exception as exc:
            from ..utils import logger
            logger.warning("Undo chunk close failed: %s", exc)
        if guard_created and closed:
            try:
                cmds.undo()
            except Exception as exc:
                from ..utils import logger
                logger.warning("Undo rollback failed: %s", exc)
        else:
            from ..utils import logger
            logger.warning("Undo rollback skipped: guard creation or chunk close did not succeed")
        raise
    else:
        cmds.undoInfo(closeChunk=True)


# reload時にも廃止した公開名を残さない。
for _obsolete_name in ('undo_chunk', 'undo_transaction'):
    globals().pop(_obsolete_name, None)
