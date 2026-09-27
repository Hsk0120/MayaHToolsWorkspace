"""
Synopsis
--------

.. code-block:: python

    hlib.objExists(name)

指定した名前のノード・属性・コンポーネントが現在のシーンに存在するか判定します。
文字列は ``maya.cmds.objExists`` と同じ規則で判定します(同じ短い名前のノードが
複数ある ``"dup"`` のような一意でない名前も、一致するものがあれば ``True``)。
Node・Plug・Component・MObject・MDagPath・MPlug も指定でき、削除済みの対象は
``False`` になります。受け付ける型は :doc:`/cmds_interop` を参照してください。

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
     - ``Node | Plug | Component | str | MObject | MDagPath | MPlug``
     - 必須
     - 存在確認する対象。文字列はノード名・属性名・コンポーネント名。

Examples
--------

.. code-block:: python

    import hlib

    print(hlib.objExists("persp"))
    print(hlib.objExists("doesNotExist"))
"""

import maya.cmds as cmds


def objExists(name):
    """指定した対象がシーンに存在するか判定する。

    Args:
        name (Node | Plug | Component | str | om2.MObject | om2.MDagPath | om2.MPlug): 存在確認する対象。
            文字列はノード名・属性名・コンポーネント名として ``maya.cmds.objExists`` へ
            そのまま渡す(一意でない名前も一致があれば True)。

    Returns:
        bool: 存在すれば True。削除済みの Node・Plug・Component・MObject 等は False。

    Raises:
        TypeError: name が対応しない型の場合。
        ValueError: name が空文字列の場合。
    """
    from .._core.coerce import to_name

    if isinstance(name, str):
        name = to_name(name)
    else:
        try:
            name = to_name(name)
        except ValueError:
            # 削除済み・範囲外になった hlib/om2 オブジェクトは存在しない扱いにする。
            return False
    return bool(cmds.objExists(name))
