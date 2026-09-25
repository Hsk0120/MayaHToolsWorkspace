"""メインペインの表示を一時停止する共通コンテキスト。"""
from contextlib import contextmanager

import maya.cmds as cmds


@contextmanager
def viewport_off():
    """メインペインを非表示にし、終了時に以前の表示状態へ戻す。

    ``@viewport_off()`` と ``with viewport_off():`` の両方で使用できる。
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
    from ..editors.viewport import Viewport

    with Viewport.suspend():
        yield
