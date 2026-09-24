"""既存Channel Boxを取得する。

Examples
--------
.. code-block:: python

    for plug in hlib.channelBox().selected_plugs():
        print(plug.full_name)
"""


def channelBox(control=None):
    """ChannelBoxを返す。controlは既存UI名。省略時は標準UI、GUIなしはRuntimeError。"""
    from ..editors.channelBox import ChannelBox

    return ChannelBox(control)
