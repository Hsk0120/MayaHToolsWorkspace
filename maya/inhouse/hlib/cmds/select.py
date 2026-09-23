"""
Synopsis
--------

.. code-block:: python

    hlib.select(nodes=None, **kwargs)

指定したノードを選択します。``nodes`` を省略すると ``**kwargs`` だけで
``maya.cmds.select`` を呼びます（``clear=True`` など）。

選択状態を変更する操作です。Maya の Undo に対応します。

Return value
------------

``None``
    値を返しません。

Related commands
----------------

:doc:`ls <../ls/index>`

Flags
-----

位置引数も含めた入力一覧です。括弧内は Maya に渡せる短縮名です。

.. list-table::
   :header-rows: 1
   :widths: 20 25 15 40

   * - 引数 / フラグ
     - 型
     - 既定値
     - 説明
   * - ``nodes``
     - ``Node | str | Iterable[Node | str] | None``
     - None
     - 選択するノード。None は kwargs だけで maya.cmds.select を呼ぶ。
   * - ``replace (r)``
     - ``bool``
     - True
     - 既存の選択を置き換えます（Maya の既定動作）。
   * - ``add (add)``
     - ``bool``
     - False
     - 既存の選択に追加します。
   * - ``clear (cl)``
     - ``bool``
     - False
     - 選択を解除します（nodes と併用不可）。
   * - ``**kwargs``
     - ``object``
     - 省略可
     - その他の select フラグをそのまま渡します。

Examples
--------

.. code-block:: python

    import hlib

    a = hlib.createNode("transform", name="a")
    b = hlib.createNode("transform", name="b")
    hlib.select([a, b])
    print(hlib.ls(selection=True))
    hlib.select(clear=True)
"""

import maya.cmds as cmds


def select(nodes=None, **kwargs):
    """指定したノードを選択する。

    Args:
        nodes (Node | str | Iterable[Node | str] | None): 選択するノード。
            None は kwargs だけで maya.cmds.select を呼ぶ（clear=True など）。
        **kwargs (object): maya.cmds.select に渡すキーワード引数。

    Returns:
        None: 値を返さない。

    Raises:
        TypeError: nodes の要素が Node/str 以外の場合。
        RuntimeError: Maya が選択を拒否した場合。
    """
    from .._core.coerce import to_names

    if nodes is None:
        cmds.select(**kwargs)
        return
    names = to_names(nodes)
    cmds.select(*names, **kwargs)
