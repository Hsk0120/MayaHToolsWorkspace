デフォーマとスキニング
============================================================

cluster・blendShape・skinClusterと、スキン変形を保持した編集を説明します。

例は Maya の Script Editor で実行します。既存ノード名は使用するシーンに合わせてください。
最初に ``import hlib`` を実行してください。

ウェイトを変えずにinfluenceを追加する
------------------------------------------

.. code-block:: python

   skin = hlib.node("skinCluster1")
   skin.add_influences("extra_joint")
   skin.add_influences(["extra_joint2", hlib.node("extra_joint3")])

Jointをウェイト0で登録します。既存ウェイトの正規化・再配分は行いません。
既存influenceと重複指定は無視し、空リストは何もしません。
Joint以外の対象は追加前に例外にします。操作は1回のUndo/Redoに対応し、
``SkinClusters`` からも同名メソッドを一括実行できます。

cluster と locator
--------------------

.. code-block:: python

   import maya.cmds as cmds
   from hlib.nodes import Node

   mesh = hlib.node("pCube1")
   cluster_name, handle_name = cmds.cluster(mesh.full_name + ".vtx[0:2]")
   cluster = Node(cluster_name)

   print(cluster.weighted_node())   # cluster1Handle（ハンドル transform）
   print(cluster.geometry())        # [Mesh(...)]（変形対象の shape）

   loc_transform = cmds.spaceLocator(name="myLocator")[0]
   loc_shape_name = cmds.listRelatives(loc_transform, shapes=True)[0]
   locator = Node(loc_shape_name)

   print(locator.get_position())         # Translate(0.0, 0.0, 0.0)
   locator.set_position((1.0, 2.0, 3.0))

``cluster`` ノードは自動的に ``Cluster`` ラッパーへ解決されます。``weighted_node``
はクラスタのハンドル transform（デフォーマ本体とは別ノード）、``geometry`` は
変形対象の shape を返します。``locator`` シェイプは ``Locator`` ラッパーへ解決され、
``get_position``/``set_position`` は ``localPosition`` 属性を ``Translate`` として
扱います。

blendShape のターゲット操作
------------------------------

.. code-block:: python

   from hlib.nodes import Node

   base = hlib.node("pCube1")
   target = hlib.node("pCube2")   # base と同じトポロジーの別メッシュ

   bs = Node(cmds.blendShape(target.full_name, base.full_name, name="myBlendShape")[0])
   print(bs.targets())            # ['pCube2']（既定ではターゲット名がエイリアスになる）
   print(bs.weights())            # [0.0]
   bs.weight_plugs()[0].set(1.0)

   new_target = hlib.node("pCube3")
   weight_plug = bs.add_target(new_target)   # 空いている weight インデックスへ追加
   weight_plug.set(0.5)
   print(bs.targets())            # ['pCube2', 'pCube3']

``targets``/``weight_plugs``/``weights`` は ``aliases()`` をそのまま利用しており、
weight 配列のインデックス順ではなく ``cmds.aliasAttr`` が返す順序に従います。
``add_target`` は ``base`` を省略すると既存の base geometry の先頭を使い、
``weight_index`` を省略すると ``plug("weight").next_available()`` で空きインデックス
を自動的に選びます。追加したターゲットには既定でその名前がエイリアスとして
設定されるため、戻り値のプラグの ``full_name`` は ``weight[N]`` ではなく
ターゲット名を含む表記になります（``attribute`` プロパティは常に ``"weight"``）。

skinCluster ウェイトのバックアップ・復元
------------------------------------------

.. code-block:: python

   from hlib.nodes.skinCluster import SkinCluster

   skin = SkinCluster("hlibExampleMeshSkinCluster")
   skin.dump_weights("C:/tmp/hlibExampleWeights.json")

   # ... 別シーンで読み込み直す、または同じシーンで何か変更した後に復元する場合 ...
   skin.load_weights("C:/tmp/hlibExampleWeights.json")

``dump_weights``/``load_weights`` は ``influences()`` と同じ並びの全 influence の
頂点ウェイトを単純な JSON 形式でファイルへ書き出し・読み込みます。
``load_weights`` は、書き出し時の頂点数が現在の mesh と一致し、記録された
influence がすべて現在の skinCluster に存在することを要求します。
一致しない場合はウェイトを変更せず ``ValueError`` を送出します
（influence 名が異なる、mesh のトポロジーが変わった状態への読み込みは
このメソッドの対象外です）。

スキン変形を保ったままjointの姿勢を編集する
--------------------------------------------------

.. code-block:: python

   from hlib.decorators import preserved_skin_shape
   from hlib.nodes.joint import Joint

   joint = Joint("hlibExampleJoint")
   with preserved_skin_shape([joint]):
       # ここで jointOrient/rotate/rotateAxis や階層をどう変更しても、
       # ブロックを抜けた時点でメッシュの見た目は変わらない。
       joint.plug("jointOrientZ").set(45.0)

``preserved_skin_shape`` は Maya標準の ``skinCluster -moveJointsMode`` /
``-recacheBindMatrices`` を使い、ブロック内での joint 姿勢変更を
「新しいバインド姿勢」として扱います。関節の向きを付け直す、
リグを組み替えるといった作業で、既存のスキニングを壊したくない場合に使います。
ブロック全体(モード切り替え・編集・bind行列の再計算)は一回の Undo にまとまります。

頂点位置の編集(``hlib.components`` の ``Vertex``/``CV`` の ``set_position()``)は
``cmds.xform`` 経由でtweakノードを介して書き込むため、このデコレータなしでも
既にスキニングを崩しません。
