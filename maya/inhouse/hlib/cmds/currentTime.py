"""
Synopsis
--------

.. code-block:: python

    hlib.cmds.currentTime(time=None, **kwargs)

現在のタイムラインの時間を取得、または設定します。

``time`` を省略すると照会のみでシーンを変更しません。指定すると編集操作に
なり、Maya の Undo に対応します。

Return value
------------

``float``
    設定後、または照会した現在の時間。

Related commands
----------------

:doc:`setKeyframe <../setKeyframe/index>`

Flags
-----

.. list-table::
   :header-rows: 1
   :widths: 20 25 15 40

   * - 引数 / フラグ
     - 型
     - 既定値
     - 説明
   * - ``time``
     - ``float | None``
     - None
     - 設定する時間。None は現在の時間を照会するだけ。
   * - ``**kwargs``
     - ``object``
     - 省略可
     - その他の currentTime フラグをそのまま渡します（time 指定時のみ）。

Examples
--------

.. code-block:: python

    import hlib

    print(hlib.cmds.currentTime())
    hlib.cmds.currentTime(24)
"""

import maya.cmds as cmds


def currentTime(time=None, **kwargs):
    """現在のタイムラインの時間を取得、または設定する。

    Args:
        time (float | None): 設定する時間。None は現在の時間を照会する。
        **kwargs (object): time 指定時に maya.cmds.currentTime へ渡すキーワード引数。

    Returns:
        float: 設定後、または照会した現在の時間。
    """
    if time is None:
        return float(cmds.currentTime(query=True))
    return float(cmds.currentTime(time, **kwargs))
