"""アトリビュート名やMPlugから、型に対応するPlug参照を取得する。

値の取得は ``plug.get()`` で行う。未作成のマルチアトリビュートの要素も参照でき、
参照取得だけでは要素を実体化しない。既存Plugを渡した場合は同じインスタンスを返す。

.. code-block:: python

    import mlib

    translate_x = mlib.getPlug("pCube1.translateX")
    value = translate_x.get()
"""


def getPlug(value):
    """アトリビュート名またはAPI参照からプラグを取得する。シーンは変更しない。

    未作成のマルチアトリビュートの要素も参照でき、参照取得だけでは要素を実体化しない。
    ラッパーの型はアトリビュート定義から選び、型選択のために値を評価しない。

    Args:
        value (str | Plug | MPlug): アトリビュート名、mlibプラグ、またはMaya API 2.0の参照。

    Returns:
        Plug: アトリビュート型に対応する参照。既存Plugは有効性を再検証せず同じインスタンスを返す。
            文字列・MPlugからは新しいラッパーを作る。値やアトリビュートを複製する操作ではない。

    Raises:
        TypeError: 対応しない型を指定した場合。
        ValueError: 空の名前または空のMPlugを指定した場合。
        RuntimeError: アトリビュートを解決できない場合。
    """
    from ..plugs.plug import Plug as _InputPlug

    return _InputPlug._resolve_input(value)
