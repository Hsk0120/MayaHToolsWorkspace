# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""OpenMayaのメッセージコールバックを所有者単位でまとめて登録・解除する。"""

import maya.api.OpenMaya as om2
from .. import logger
from typing import Callable
from mlib.nodes.node import Node

_SCENE_EVENTS: tuple


class Callbacks:
    """複数のOpenMayaコールバックを所有者単位で管理する。GC時には自動解除しない。

    登録したコールバックはMayaが保持するため、このオブジェクトを捨てても解除されない。
    :meth:`remove` を呼ぶか、``with Callbacks() as cb:`` で使う。登録した関数の中の例外は
    警告として通知して握りつぶし、Mayaへ伝えない。バッチ(mayapy)でも登録できる。

    .. code-block:: python

        from mlib.common import Callbacks

        with Callbacks() as cb:
            cb.addSceneCallback("afterOpen", refresh)
            cb.addEventCallback("timeChanged", refresh)
            ...  # with を抜けると解除する
    """
    def __init__(self) -> None:
        """登録を伴わない空のグループを作る。"""
        ...
    def __enter__(self) -> Callbacks:
        """``with`` の開始。登録はしない。

        Returns:
            Callbacks: 自身。

        Raises:
            RuntimeError: 同じインスタンスで入れ子にした場合。
        """
        ...
    def __exit__(self, *excInfo: object) -> bool:
        """``with`` の終了時に、このグループが持つコールバックをすべて解除する。

        本文が失敗した場合は、解除時の例外で本文の例外を置き換えない。

        Args:
            *excInfo (object): 本文の例外型・例外・トレースバック(正常終了ならすべてNone)。

        Returns:
            bool: 常にFalse(本文の例外は再送出する)。

        Raises:
            RuntimeError: 本文が正常終了し、解除が失敗した場合。
        """
        ...
    def addSceneCallback(self, event: str, function: Callable) -> int:
        """シーンのイベント(``om2.MSceneMessage``)のコールバックを登録する。

        Args:
            event (str): イベント名。``"afterOpen"``・``"beforeSave"``・``"afterNew"`` のように
                ``MSceneMessage.k*`` の ``k`` を除いたlowerCamelCase。Check系とPluginLoad系は扱わない。
            function (Callable): 引数なしで呼ぶ処理。

        Returns:
            int: 登録したコールバックの識別子。

        Raises:
            TypeError: eventが文字列でない、またはfunctionが呼び出せない場合。
            ValueError: 未知のイベント名、またはこのMayaに無いイベントの場合。
        """
        ...
    def addEventCallback(self, eventName: str, function: Callable) -> int:
        """Mayaのイベント(``om2.MEventMessage``)のコールバックを登録する。

        Args:
            eventName (str): Mayaのイベント名そのまま(``"timeChanged"``・``"SelectionChanged"`` 等。
                ``cmds.scriptJob(listEvents=True)`` と同じ一覧。大文字小文字を区別する)。
            function (Callable): 引数なしで呼ぶ処理。

        Returns:
            int: 登録したコールバックの識別子。

        Raises:
            TypeError: eventNameが文字列でない、またはfunctionが呼び出せない場合。
            ValueError: Mayaに無いイベント名の場合。
        """
        ...
    def addAttributeChangedCallback(self, node: Node | str, function: Callable) -> int:
        """ノードのアトリビュート変更(``om2.MNodeMessage.addAttributeChangedCallback``)のコールバックを登録する。

        値の設定だけでなく、接続・接続解除・アトリビュートの追加/削除などでも呼ばれる。
        どの変更かはmessageの ``om2.MNodeMessage.k*`` のビットで判定する。

        Args:
            node (Node | str): 監視するノード。
            function (Callable): ``function(message, plug)`` で呼ぶ処理。messageは
                ``om2.MNodeMessage.AttributeMessage`` のビット(int)、plugは変更された
                アトリビュートの :class:`~mlib.plugs.plug.Plug`。

        Returns:
            int: 登録したコールバックの識別子。

        Raises:
            TypeError: nodeが対応しない型、またはfunctionが呼び出せない場合。
            RuntimeError: nodeを解決できない場合。
        """
        ...
    def remove(self) -> None:
        """このグループが登録した全コールバックの解除を試み、成功分だけを保持表から除く。

        解除の例外は警告して残りも処理し、失敗したものは後からremove()で再試行できる。
        他の所有者のコールバックは解除しない。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: 解除失敗が一つ以上ある場合。最初の原因例外を__cause__に保持する。
        """
        ...
    def _register(self, callback_id: int) -> int:
        """登録したコールバックの識別子を保持する。

        Args:
            callback_id (int): Mayaが返した識別子。

        Returns:
            int: callback_id。
        """
        ...

def _require_callable(function: object):
    """関数が呼び出せるか検証する。

    Args:
        function (object): 検証対象。

    Raises:
        TypeError: 呼び出せない場合。
    """
    ...

def _guarded(function: Callable, label: str) -> Callable:
    """例外を警告にして握りつぶすom2用のコールバックを作る。

    Args:
        function (Callable): 実際の処理。
        label (str): 警告に表示する登録先の名前。

    Returns:
        Callable: om2へ渡すコールバック。sceneとeventではclientDataだけを受け取る。
    """
    ...
