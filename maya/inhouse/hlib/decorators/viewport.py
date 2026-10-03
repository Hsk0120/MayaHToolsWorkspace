"""メインペインの表示を一時停止する共通コンテキスト。"""
from contextlib import contextmanager

import maya.cmds as cmds


@contextmanager
def viewportOff():
    """メインペインを非表示にし、終了時に以前の表示状態へ戻す。

    ``@viewportOff()`` と ``with viewportOff():`` の両方で使用できる。
    GUIではViewport.suspendと同じpaneLayoutのmanage方式を使用する。
    バッチ実行では表示操作を行わない。OGS・refresh・評価設定は変更しない。
    入れ子でも元の状態を維持し、処理中の例外は再実行せず伝播する。

    Yields:
        None: 表示を停止している間に処理を実行する。

    Raises:
        RuntimeError: GUIのメインペインを取得・編集できない場合。
    """
    if cmds.about(batch=True):
        yield
        return
    from ..ui.viewport import Viewport

    with Viewport.suspend():
        yield


# reload時にも廃止した公開名を残さない。
for _obsolete_name in ('viewport_off',):
    globals().pop(_obsolete_name, None)
