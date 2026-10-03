"""既存Channel Boxを取得する。

Examples
--------
.. code-block:: python

    for plug in hlib.getChannelBox().selectedPlugs():
        print(plug.fullName())
"""


def getChannelBox(control=None):
    """既存のChannel Boxを参照する。UIは生成しない。

    Args:
        control (str | None): 既存UI名。省略時は標準Channel Box。
    Returns:
        ChannelBox: 対象UIのラッパー。
    Raises:
        RuntimeError: GUIがない、または対象UIが存在しない場合。"""
    from hlib.ui.channelBox import ChannelBox

    return ChannelBox(control)
