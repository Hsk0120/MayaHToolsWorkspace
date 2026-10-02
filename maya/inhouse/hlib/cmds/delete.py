"""
Synopsis
--------

.. code-block:: python

    hlib.delete(nodes)

指定したノード・コンポーネントを削除します。Component は一意な名前に変換して渡し、
その扱いは ``maya.cmds.delete`` に従います(面を削除するなど)。受け付ける型は
:doc:`/cmds_interop` を参照してください。

Plug(``ArrayPlug`` を含む)と ``om2.MPlug`` は ``TypeError`` です。``maya.cmds.delete`` へ
アトリビュート名を渡してもエラーを表示するだけで何も削除しないためです。動的アトリビュートの削除は
``plug.delete_attribute()``、配列要素の削除は ``array_plug.remove_element(i)``、接続の解除は
``plug.disconnect()``、アトリビュートの所有ノードの削除は ``hlib.delete(plug.node)`` を使ってください。
文字列は解決せずにそのまま渡すため、``"node.attribute"`` 形式の文字列は ``maya.cmds.delete`` と
同じ扱いです。

削除操作です。Maya の Undo に対応します。照会・編集用コマンドではありません。
各ノードを具象クラスへ解決し、その ``delete()`` を呼び出します。
``Joint.delete()`` ではウェイト移送・子階層保持などの専用動作を使用します。
入力順に処理し、先行する削除で無効になった対象はスキップします。
コンポーネントは所有ノードを削除せず、Maya標準コマンドで処理します。

Return value
------------

``None``
    値を返しません。

Related commands
----------------

:doc:`duplicate <../duplicate/index>` / ``maya.cmds.objExists``

Flags
-----

位置引数のみです。括弧内は Maya に渡せる短縮名です（該当なし）。

.. list-table::
   :header-rows: 1
   :widths: 20 25 15 40

   * - 引数
     - 型
     - 既定値
     - 説明
   * - ``nodes``
     - ``Node | Component | Components | Selection | str | MObject | MDagPath | Iterable``
     - 必須
     - 削除する対象、またはその列。Plug・MPlug(列の要素、Selection の要素を含む)は ``TypeError``。

Examples
--------

.. code-block:: python

    import hlib

    node = hlib.createNode("transform", name="example")
    hlib.delete(node)
"""

from ..decorators.undo import undo_chunk

import maya.cmds as cmds


@undo_chunk("hlib.cmds.delete.delete")
def delete(nodes):
    """指定したノード・コンポーネントを削除する。

    Args:
        nodes (Node | Component | Components | Selection | str | om2.MObject | om2.MDagPath | Iterable):
            削除する対象、またはその列(入れ子のコレクションも展開する)。

    Returns:
        None: 値を返さない。

    Raises:
        ValueError: nodes が空、または要素が空文字列・削除済みの対象の場合。
        TypeError: 要素が対応しない型の場合。要素に Plug(ArrayPlug を含む)・om2.MPlug が
            含まれる場合(maya.cmds.delete はアトリビュートを削除せずエラーを表示するだけのため。
            何も削除しない)。
        RuntimeError: Maya が削除を拒否した場合。
    """
    from hlib.object import Object as _InputObject
    from ..nodes.node import Node

    names = _InputObject._input_names(nodes, allow_plugs=False)
    if not names:
        raise ValueError("nodes には1つ以上のノードを指定してください")
    # アトリビュート・コンポーネント文字列は所有ノードへ変換せず、標準の扱いを維持する。
    node_names = [name for name in names if "." not in name]
    components = [name for name in names if "." in name]
    nodes = []
    for name in node_names:
        # Maya標準のワイルドカード指定を実ノードへ展開してから検証する。
        resolved = cmds.ls(name, long=True) if any(char in name for char in "*?[") else [name]
        nodes.extend(Node(value) for value in (resolved or [name]))
    if components:
        cmds.delete(*components)
    for node in nodes:
        # 親・所有コンテナの削除や重複指定で既に消えた対象は再削除しない。
        if node.is_valid():
            node.delete()
