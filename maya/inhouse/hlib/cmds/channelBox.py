"""既存Channel Boxを取得する。

Examples
--------
.. code-block:: python

    for plug in hlib.channelBox().selected_plugs():
        print(plug.full_name())
"""


def channelBox(control=None):
    """既存のChannel Boxを参照する。UIは生成しない。

    Args:
        control (str | None): 既存UI名。省略時は標準Channel Box。
    Returns:
        ChannelBox: 対象UIのラッパー。
    Raises:
        RuntimeError: GUIがない、または対象UIが存在しない場合。"""
    from ..editors.channel_box import ChannelBox

    return ChannelBox(control)
