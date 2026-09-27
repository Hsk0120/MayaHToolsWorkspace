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

Mayaの長名・短名を受け付けます。同じフラグの長名と短名を同時に渡すと、
処理前に ``TypeError`` になります。戻り値は表記によって変わりません。

.. list-table::
   :header-rows: 1
   :widths: 20 25 15 40

   * - 引数 / フラグ
     - 型
     - 既定値
     - 説明
   * - ``target``
     - ``Node | Plug | Component | Components | Selection | str | MObject | MDagPath | MPlug | Iterable | None``
     - None
     - キーを設定するノード・プラグ、またはその列。None は現在の選択が対象（kwargs だけで呼ぶ）。受け付ける型は :doc:`/cmds_interop` を参照。
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

from .._core.flags import flag_aliases

import maya.cmds as cmds


@flag_aliases("setKeyframe")
@undo_chunk("hlib.cmds.setKeyframe.setKeyframe")
def setKeyframe(target=None, **kwargs):
    """指定したノードまたはプラグにキーフレームを設定する。

    Args:
        target (Node | Plug | Component | Components | Selection | str | om2.MObject | om2.MDagPath | om2.MPlug | Iterable | None):
            キーを設定するノード・プラグ、またはその列。None は現在の選択を対象に
            kwargs だけで maya.cmds.setKeyframe を呼ぶ。
        **kwargs (object): maya.cmds.setKeyframe に渡すキーワード引数。

    Returns:
        int: 設定したキー数。

    Raises:
        TypeError: target が対応しない型、空文字列、または空の列の場合
            (空の列で現在の選択へキーを打たないよう、呼び出し前に拒否する)。
        ValueError: target に削除済みの対象が含まれる場合。
        RuntimeError: Maya がキー設定を拒否した場合。
    """
    from .._core.coerce import to_names

    if target is None:
        return cmds.setKeyframe(**kwargs)
    if isinstance(target, str) and not target:
        raise TypeError("target には空でない名前、Node、または Plug を指定してください")
    names = to_names(target)
    if not names:
        raise TypeError("target には1つ以上の対象を指定してください")
    return cmds.setKeyframe(names, **kwargs)
