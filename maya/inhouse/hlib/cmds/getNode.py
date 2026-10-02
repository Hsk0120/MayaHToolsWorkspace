"""
Synopsis
--------

.. code-block:: python

    hlib.getNode(value)

既存ノードを取得し、Maya のノード型に対応するラッパーを返します。
ノードの作成や選択状態の変更は行いません。
``import hlib`` の後に ``hlib.getNode(value)`` として呼び出します。

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
     - 既存ノードの名前、hlib のラッパー、または Maya API 2.0 の参照。Plug・MPlug と ``"node.attribute"`` は所有ノード、Component・Components と ``"pCube1.vtx[0]"`` は所有シェイプを返します。名前が存在しない、または複数の対象に一致する場合(``"bulk*"`` のように複数のノードに一致するパターンを含む。パターンは ``hlib.ls`` を使います)と、空・削除済みの対象は ``RuntimeError``。``deleteAttr`` でアトリビュートが削除された Plug・MPlug は ``ValueError`` (``RuntimeError`` としても捕捉できます)。必須。

Examples
--------

.. code-block:: python

    import hlib

    jnt = hlib.getNode("leg_RF_knee_IK_jnt")
    print(jnt)
"""


def getNode(value):
    """既存ノードを型に対応するラッパーとして取得する。

    Args:
        value (str | Node | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug):
            ノード名、hlib のラッパー、または Maya API 2.0 の参照。Plug・MPlug は
            所有ノード、Component・Components は所有シェイプとして解決する。

    Returns:
        Node: 実際のノード型に対応するラッパー。

    Raises:
        TypeError: 未対応の入力型、または依存ノード以外(アトリビュートなど)を指す MObject の場合。
        ValueError: 所有ノードは有効で、アトリビュートが ``deleteAttr`` で削除済みの Plug・MPlug の場合
            (``hlib.plugs.plug.DeletedAttributeError``。RuntimeError の派生でもある)。
        RuntimeError: ノードを解決できない(存在しない、または ``"bulk*"`` のようなパターンを
            含めて複数の対象に一致する)場合、または空・削除済みのラッパーや om2 オブジェクトを
            指定した場合。
    """
    from ..nodes import Node

    return Node(value)
