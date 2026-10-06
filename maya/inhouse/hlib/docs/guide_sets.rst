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

   layer.addMembers(a)
   print(layer.getMembers())        # [Transform('layerMemberA')]

   layer.setCurrent()           # 以降の新規ノードの追加先レイヤーになる
   layer.removeMembers(a)       # defaultLayer へ戻す（除外に相当）
   print(layer.getMembers())        # []

``displayLayer`` ノードは自動的に ``DisplayLayer`` ラッパーへ解決されます。
Maya の displayLayer メンバーシップは常に単一のレイヤーに限られ、
``addMembers`` は既に他のレイヤーに属するノードもこのレイヤーへ排他的に
移動します。``editDisplayLayerMembers`` に明示的な削除フラグは無いため、
``removeMembers`` は ``defaultLayer`` へ戻すことで除外を実現しています。

objectSet の基本操作
----------------------

.. code-block:: python

   import maya.cmds as cmds
   from hlib.nodes import Node

   a = hlib.createNode("transform", name="setMemberA")
   b = hlib.createNode("transform", name="setMemberB")
   object_set = Node(cmds.sets(name="controlSet", empty=True))

   object_set.addMembers(a, b)
   print(object_set.getMembers())          # [Transform('setMemberA'), Transform('setMemberB')]
   print(object_set.isMember(a))       # True

   object_set.addMembers(a.getFullName() + ".tx")  # コンポーネント/プラグ文字列も追加可能
   object_set.removeMembers(b)
   print(object_set.getMembers())          # [Transform('setMemberA'), 'setMemberA.translateX']

``objectSet`` ノードは自動的に ``ObjectSet`` ラッパーへ解決されます。``getMembers()``
はコンポーネント文字列（例: ``"mesh1.vtx[0:2]"``）をそのまま文字列として返し、
それ以外はノードのラッパーとして返します。``addMembers``/``removeMembers`` はNode列または文字列列を
受け取り、両者の混在は拒否します。和集合・積集合・差集合の演算は現時点では未対応です
（このバージョンの ``cmds.sets`` の union/intersection/subtract フラグの挙動が
安定して確認できなかったため、安全のため見送っています）。
