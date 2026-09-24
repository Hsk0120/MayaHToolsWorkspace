"""
Synopsis
--------

.. code-block:: python

    hlib.setKeyframe(target=None, **kwargs)

指定したノードまたはプラグにキーフレームを設定します。``target`` を省略すると
``**kwargs`` だけで ``maya.cmds.setKeyframe`` を呼びます（現在の選択が対象）。

作成・編集操作です。Maya の Undo に対応します。

Return value
------------

``int``
    設定したキー数。maya.cmds.setKeyframe の戻り値をそのまま返します。

Related commands
----------------

:doc:`currentTime <../currentTime/index>` / :doc:`bakeResults <../bakeResults/index>`

Flags
-----

.. list-table::
   :header-rows: 1
   :widths: 20 25 15 40

   * - 引数 / フラグ
     - 型
     - 既定値
     - 説明
   * - ``target``
     - ``Node | Plug | str | None``
     - None
     - キーを設定するノードまたはプラグ。None は現在の選択が対象（kwargs だけで呼ぶ）。
   * - ``time (t)``
     - ``float``
     - 現在の時間
     - キーを打つ時間。
   * - ``value (v)``
     - ``float``
     - 現在値
     - 設定する値。target がプラグの場合に使用します。
   * - ``**kwargs``
     - ``object``
     - 省略可
     - その他の setKeyframe フラグをそのまま渡します。

Examples
--------

.. code-block:: python

    import hlib

    node = hlib.createNode("transform", name="example")
    hlib.currentTime(1)
    hlib.setKeyframe(node.plug("translateX"), value=0.0)
    hlib.currentTime(24)
    hlib.setKeyframe(node.plug("translateX"), value=10.0)
"""

from ..decorators.undo import undo_chunk

import maya.cmds as cmds


@undo_chunk("hlib.cmds.setKeyframe.setKeyframe")
def setKeyframe(target=None, **kwargs):
    """指定したノードまたはプラグにキーフレームを設定する。

    Args:
        target (Node | Plug | str | None): キーを設定するノードまたはプラグ。
            None は現在の選択を対象に kwargs だけで maya.cmds.setKeyframe を呼ぶ。
        **kwargs (object): maya.cmds.setKeyframe に渡すキーワード引数。

    Returns:
        int: 設定したキー数。

    Raises:
        TypeError: target が Node/Plug/str 以外の場合、または空文字列の場合。
        RuntimeError: Maya がキー設定を拒否した場合。
    """
    from ..nodes import Node
    from ..plugs import Plug

    if target is None:
        return cmds.setKeyframe(**kwargs)
    if isinstance(target, (Node, Plug)):
        target = target.full_name
    if not isinstance(target, str) or not target:
        raise TypeError("target には空でない名前、Node、または Plug を指定してください")
    return cmds.setKeyframe(target, **kwargs)
