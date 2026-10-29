"""既存のMayaノードを参照する新しいラッパーを、登録されたノード型に応じて返す。

ノードの作成や複製は行わない。Plug入力は所有ノード、Component入力は
所有シェイプへ解決する。複数のノードを探す場合は ``mlib.ls()`` を使う。

.. code-block:: python

    import mlib

    node = mlib.getNode("pCube1")  # シーンに存在するノード
"""


def getNode(value):
    """既存のMayaノードを参照する新しいラッパーを取得する。

    入力がNodeでも同じMayaノードへの参照を作り、シーンのノードを複製しない。
    ラッパー型はnodeTypeの登録、無ければMayaの継承に沿って生成したクラス(基底は最寄りの登録クラス)、Mayaが認識しない型名だけNodeの順に選ぶ。

    Args:
        value (str | Node | Plug | Component | Components | om2.MObject | om2.MDagPath | om2.MPlug):
            ノード名、mlib のラッパー、または Maya API 2.0 の参照。Plug・MPlug は
            所有ノード、Component・Components は所有シェイプとして解決する。

    Returns:
        Node: 実際のノード型に対応するラッパー。

    Raises:
        TypeError: 未対応の入力型、または依存ノード以外(アトリビュートなど)を指す MObject の場合。
        ValueError: 所有ノードは有効で、アトリビュートが ``deleteAttr`` で削除済みの Plug・MPlug の場合
            (``mlib.plugs.plug.DeletedAttributeError``。RuntimeError の派生でもある)。
        RuntimeError: ノードを解決できない(存在しない、または ``"bulk*"`` のようなパターンを
            含めて複数の対象に一致する)場合、または空・削除済みのラッパーや om2 オブジェクトを
            指定した場合。
    """
    from ..nodes.node import Node

    if isinstance(value, str):
        # Node(value) と同じ解決・型選択を、生成の入口の再判定なしで行う。
        return Node._from_name(value)
    return Node(value)
