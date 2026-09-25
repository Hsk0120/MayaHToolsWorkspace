表示レイヤーとセット
============================================================

displayLayerとobjectSetの作成・メンバー操作を説明します。

例は Maya の Script Editor で実行します。既存ノード名は使用するシーンに合わせてください。
最初に ``import hlib`` を実行してください。

displayLayer の基本操作
--------------------------

.. code-block:: python

   import maya.cmds as cmds
   from hlib.nodes import Node

   a = hlib.createNode("transform", name="layerMemberA")
   layer = Node(cmds.createDisplayLayer(name="myLayer", empty=True))

   layer.add_members(a)
   print(layer.members())        # [Transform('layerMemberA')]

   layer.set_current()           # 以降の新規ノードの追加先レイヤーになる
   layer.remove_members(a)       # defaultLayer へ戻す（除外に相当）
   print(layer.members())        # []

``displayLayer`` ノードは自動的に ``DisplayLayer`` ラッパーへ解決されます。
Maya の displayLayer メンバーシップは常に単一のレイヤーに限られ、
``add_members`` は既に他のレイヤーに属するノードもこのレイヤーへ排他的に
移動します。``editDisplayLayerMembers`` に明示的な削除フラグは無いため、
``remove_members`` は ``defaultLayer`` へ戻すことで除外を実現しています。

objectSet の基本操作
----------------------

.. code-block:: python

   import maya.cmds as cmds
   from hlib.nodes import Node

   a = hlib.createNode("transform", name="setMemberA")
   b = hlib.createNode("transform", name="setMemberB")
   object_set = Node(cmds.sets(name="controlSet", empty=True))

   object_set.add(a, b)
   print(object_set.members())          # [Transform('setMemberA'), Transform('setMemberB')]
   print(object_set.is_member(a))       # True

   object_set.add(a.full_name() + ".tx")  # コンポーネント/プラグ文字列も追加可能
   object_set.remove(b)
   print(object_set.members())          # [Transform('setMemberA'), 'setMemberA.translateX']

``objectSet`` ノードは自動的に ``ObjectSet`` ラッパーへ解決されます。``members()``
はコンポーネント文字列（例: ``"mesh1.vtx[0:2]"``）をそのまま文字列として返し、
それ以外はノードのラッパーとして返します。``add``/``remove`` は Node と文字列を
混在して受け取れます。和集合・積集合・差集合の演算は現時点では未対応です
（このバージョンの ``cmds.sets`` の union/intersection/subtract フラグの挙動が
安定して確認できなかったため、安全のため見送っています）。
