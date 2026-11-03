"""OpenMayaのメッセージコールバックを所有者単位でまとめて登録・解除する。"""

import maya.api.OpenMaya as om2

from .. import logger

# MSceneMessage.addCallbackで登録できる(引数なしで呼ばれる)シーンのイベント名。
# 戻り値を判定に使うCheck系と、プラグイン名の配列を受け取るPluginLoad系は扱わない。
_SCENE_EVENTS = (
    "beforeNew", "afterNew",
    "beforeOpen", "afterOpen",
    "beforeImport", "afterImport",
    "beforeFileRead", "afterFileRead", "afterSceneReadAndRecordEdits",
    "beforeSave", "afterSave",
    "beforeExport", "exportStarted", "afterExport",
    "beforeReference", "afterReference",
    "beforeCreateReference", "afterCreateReference",
    "beforeRemoveReference", "afterRemoveReference",
    "beforeImportReference", "afterImportReference",
    "beforeExportReference", "afterExportReference",
    "beforeLoadReference", "afterLoadReference",
    "beforeUnloadReference", "afterUnloadReference",
    "beforeSoftwareRender", "afterSoftwareRender",
    "beforeSoftwareFrameRender", "afterSoftwareFrameRender", "softwareRenderInterrupted",
    "sceneUpdate", "mayaInitialized", "mayaExiting",
)


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

    def __init__(self):
        """登録を伴わない空のグループを作る。"""
        self._ids = []
        self._context_active = False

    def __enter__(self):
        """``with`` の開始。登録はしない。

        Returns:
            Callbacks: 自身。

        Raises:
            RuntimeError: 同じインスタンスで入れ子にした場合。
        """
        if self._context_active:
            raise RuntimeError("Callbacks cannot be nested on the same instance")
        self._context_active = True
        return self

    def __exit__(self, *excInfo):
        """``with`` の終了時に、このグループが持つコールバックをすべて解除する。

        本文が失敗した場合は、解除時の例外で本文の例外を置き換えない。

        Args:
            *excInfo (object): 本文の例外型・例外・トレースバック(正常終了ならすべてNone)。

        Returns:
            bool: 常にFalse(本文の例外は再送出する)。

        Raises:
            RuntimeError: 本文が正常終了し、解除が失敗した場合。
        """
        try:
            self.remove()
        except Exception:
            if excInfo[0] is None:
                raise
        finally:
            self._context_active = False
        return False

    def addSceneCallback(self, event, function):
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
        if not isinstance(event, str):
            raise TypeError("event must be a str")
        _require_callable(function)
        message = None
        if event in _SCENE_EVENTS:
            message = getattr(om2.MSceneMessage, "k" + event[:1].upper() + event[1:], None)
        if message is None:
            raise ValueError(f"Unknown scene event: {event!r}")
        return self._register(om2.MSceneMessage.addCallback(message, _guarded(function, event)))

    def addEventCallback(self, eventName, function):
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
        if not isinstance(eventName, str):
            raise TypeError("eventName must be a str")
        _require_callable(function)
        # scriptJob(listEvents=True)はバッチでNoneを返すため、同じ一覧をom2から取得する。
        if eventName not in om2.MEventMessage.getEventNames():
            raise ValueError(f"Unknown event name: {eventName!r}")
        return self._register(om2.MEventMessage.addEventCallback(eventName, _guarded(function, eventName)))

    def addAttributeChangedCallback(self, node, function):
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
        # commonの初期化時にnodes・plugsを読み込まないよう、使用時に読み込む。
        from ..nodes.node import Node
        from ..plugs.plug import Plug

        _require_callable(function)
        target = Node._resolve_input(node)
        label = target.getName()

        def forward(message, plug, other_plug, client_data):
            function(message, Plug._resolve_input(plug))

        return self._register(om2.MNodeMessage.addAttributeChangedCallback(
            target.mnode(), _guarded(forward, label)))

    def remove(self):
        """このグループが登録した全コールバックの解除を試み、成功分だけを保持表から除く。

        解除の例外は警告して残りも処理し、失敗したものは後からremove()で再試行できる。
        他の所有者のコールバックは解除しない。

        Returns:
            None: 値を返さない。

        Raises:
            RuntimeError: 解除失敗が一つ以上ある場合。最初の原因例外を__cause__に保持する。
        """
        failures = []
        for callback_id in list(self._ids):
            try:
                om2.MMessage.removeCallback(callback_id)
            except Exception as exc:
                failures.append((callback_id, exc))
                logger.warning("Callback cleanup failed for %r: %s", callback_id, exc)
            else:
                self._ids.remove(callback_id)
        if failures:
            raise RuntimeError(
                f"Failed to remove callbacks: {', '.join(repr(key) for key, _ in failures)}") from failures[0][1]

    def _register(self, callback_id):
        """登録したコールバックの識別子を保持する。

        Args:
            callback_id (int): Mayaが返した識別子。

        Returns:
            int: callback_id。
        """
        self._ids.append(callback_id)
        return callback_id


def _require_callable(function):
    """関数が呼び出せるか検証する。

    Args:
        function (object): 検証対象。

    Raises:
        TypeError: 呼び出せない場合。
    """
    if not callable(function):
        raise TypeError("function must be callable")


def _guarded(function, label):
    """例外を警告にして握りつぶすom2用のコールバックを作る。

    Args:
        function (Callable): 実際の処理。
        label (str): 警告に表示する登録先の名前。

    Returns:
        Callable: om2へ渡すコールバック。sceneとeventではclientDataだけを受け取る。
    """
    def callback(*args):
        try:
            # scene・eventのコールバックは末尾のclientDataだけを受け取るため、引数なしで呼ぶ。
            if len(args) <= 1:
                function()
            else:
                function(*args)
        except Exception as exc:
            logger.warning("Callback for %s failed: %s: %s", label, type(exc).__name__, exc)
    return callback
