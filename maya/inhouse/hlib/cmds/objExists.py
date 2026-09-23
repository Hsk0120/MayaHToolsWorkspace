"""
Synopsis
--------

.. code-block:: python

    hlib.objExists(name)

指定した名前のノードが現在のシーンに存在するか判定します。

照会操作です。シーンを変更しません。

Return value
------------

``bool``
    存在すれば True。

Related commands
----------------

:doc:`ls <../ls/index>` / :doc:`node <../node/index>`

Flags
-----

.. list-table::
   :header-rows: 1
   :widths: 20 25 15 40

   * - 引数
     - 型
     - 既定値
     - 説明
   * - ``name``
     - ``Node | str``
     - 必須
     - 存在確認するノード名。

Examples
--------

.. code-block:: python

    import hlib

    print(hlib.objExists("persp"))
    print(hlib.objExists("doesNotExist"))
"""

import maya.api.OpenMaya as om2


def objExists(name):
    """指定した名前のノードがシーンに存在するか判定する。

    Args:
        name (Node | str): 存在確認するノード名。

    Returns:
        bool: 存在すれば True。

    Raises:
        TypeError: name が Node/str 以外の場合。
        ValueError: name が空文字列の場合。
    """
    from .._core.coerce import to_name

    name = to_name(name)
    selection = om2.MSelectionList()
    try:
        selection.add(name)
    except RuntimeError:
        return False
    return True
