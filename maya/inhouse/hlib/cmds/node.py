"""
Synopsis
--------

.. code-block:: python

    hlib.node(value)

既存ノードを取得し、Maya のノード型に対応するラッパーを返します。
ノードの作成や選択状態の変更は行いません。
``import hlib`` の後に ``hlib.node(value)`` として呼び出します。

Return value
------------

``Node``
    Joint、Transform、Mesh など、登録済みの型に対応するラッパー。
    専用ラッパーがないノード型は Node を返します。

Related commands
----------------

:doc:`createNode <../createNode/index>` / :doc:`ls <../ls/index>`

Flags
-----

.. list-table::
   :header-rows: 1

   * - 引数
     - 型
     - 説明
   * - ``value``
     - str | MObject | MDagPath
     - 既存ノードの名前、または Maya API 2.0 のノード参照。必須。

Examples
--------

.. code-block:: python

    import hlib

    jnt = hlib.node("leg_RF_knee_IK_jnt")
    print(jnt)
"""


def node(value):
    """既存ノードを型に対応するラッパーとして取得する。

    Args:
        value (str | om2.MObject | om2.MDagPath): ノード名または Maya API 2.0 の参照。

    Returns:
        Node: 実際のノード型に対応するラッパー。

    Raises:
        TypeError: 未対応の入力型の場合。
        RuntimeError: ノードを解決できない場合。
    """
    from ..nodes import Node

    return Node(value)
