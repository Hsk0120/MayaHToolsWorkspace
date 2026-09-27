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
     - ``str | Node | Plug | Component | Components | MObject | MDagPath | MPlug``
     - 既存ノードの名前、hlib のラッパー、または Maya API 2.0 の参照。Plug・MPlug と ``"node.attribute"`` は所有ノード、Component・Components と ``"pCube1.vtx[0]"`` は所有シェイプを返します。名前が存在しない、または複数の対象に一致する場合は ``RuntimeError``。必須。

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
        value (str | Node | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug):
            ノード名、hlib のラッパー、または Maya API 2.0 の参照。Plug・MPlug は
            所有ノード、Component・Components は所有シェイプとして解決する。

    Returns:
        Node: 実際のノード型に対応するラッパー。

    Raises:
        TypeError: 未対応の入力型、または依存ノード以外(属性など)を指す MObject の場合。
        RuntimeError: ノードを解決できない(存在しない、または複数の対象に一致する)場合、
            または空・削除済みのラッパーや om2 オブジェクトを指定した場合。
    """
    from ..nodes import Node

    return Node(value)
