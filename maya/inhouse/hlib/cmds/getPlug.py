"""既存の属性を型に対応するPlugとして取得する。"""


def getPlug(value):
    """属性名またはAPI参照からプラグを取得する。シーンは変更しない。

    Args:
        value (str | Plug | MPlug): 属性名、hlibプラグ、またはMaya API 2.0の参照。

    Returns:
        Plug: 属性型に対応するラッパー。既存Plugは有効性を再検証せずそのまま返す。

    Raises:
        TypeError: 対応しない型を指定した場合。
        ValueError: 空の名前または空のMPlugを指定した場合。
        RuntimeError: 属性を解決できない場合。
    """
    from .._core.coerce import to_plug

    return to_plug(value)
