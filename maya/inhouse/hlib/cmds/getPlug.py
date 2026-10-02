"""既存のアトリビュートを型に対応するPlugとして取得する。"""


def getPlug(value):
    """アトリビュート名またはAPI参照からプラグを取得する。シーンは変更しない。

    Args:
        value (str | Plug | MPlug): アトリビュート名、hlibプラグ、またはMaya API 2.0の参照。

    Returns:
        Plug: アトリビュート型に対応するラッパー。既存Plugは有効性を再検証せずそのまま返す。

    Raises:
        TypeError: 対応しない型を指定した場合。
        ValueError: 空の名前または空のMPlugを指定した場合。
        RuntimeError: アトリビュートを解決できない場合。
    """
    from hlib.plugs.plug import Plug as _InputPlug

    return _InputPlug._resolve_input(value)
