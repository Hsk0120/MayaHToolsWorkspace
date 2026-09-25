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

influenceを取り除き、親へウェイトを加算する
------------------------------------------------

.. code-block:: python

   skin = hlib.node("skinCluster1")
   joint = hlib.node("extra_joint")
   skin.remove_influence(joint)
   # またはjoint側から、接続する全skinClusterを対象にする
   # joint.remove_influence()
   # 対象を一つに限定する場合
   # joint.remove_influence(skin)

同じskinClusterに登録された最も近い祖先influenceへ元ウェイトを加算し、
指定jointのinfluence登録だけを外します。jointノードや子階層は変更しません。
親が直接登録されていなければさらに祖先を探し、移送先がなければMaya標準の
removeInfluenceによる再配分に任せます。最後の一つのinfluenceはエラーにします。
``transfer_to_parent=False`` をSkinCluster側へ渡すと標準除去のみ行います。
``Joint.remove_influence()`` は未スキニングなら何もしません。

ウェイトの正規化と最大influence数
-----------------------------------

.. code-block:: python

   skin.normalize_weights()            # 各頂点の合計を1にする
   skin.normalize_weights(decimals=3)  # 小数3桁へ丸め、端数を配分して合計1にする
   skin.set_max_influences(4)          # 設定のみ。既存ウェイトは変更しない
   skin.set_max_influences(4, prune=True)  # 大きい4個を残し、残りを0にして正規化
   print(skin.max_influences())

正規化とpruneは先頭meshの全頂点が対象です。小数桁数は0〜15を指定できます。
例えば同じ重みが3つなら、小数2桁では0.34、0.33、0.33とし、同率時は登録順を
優先します。浮動小数点の保存値には機械精度の誤差があり得ます。
合計0・負値・非有限値、ロック・入力接続・スキニングレイヤーは編集前に拒否します。
``normalize_weights`` は ``normalizeWeights`` 設定を変えません。
``set_max_influences`` は既定で ``maintainMaxInfluences`` も有効にします。
``maintain=False`` で無効にできます。設定だけでは既存の非ゼロ数は制限されません。
これらの変更は一回のUndoで戻せます。実行途中の例外は通知し、自動ロールバックはしません。

cluster と locator
--------------------

.. code-block:: python

   import maya.cmds as cmds
   from hlib.nodes import Node

   mesh = hlib.node("pCube1")
   cluster_name, handle_name = cmds.cluster(mesh.full_name() + ".vtx[0:2]")
   cluster = Node(cluster_name)

   print(cluster.weighted_node())   # cluster1Handle（ハンドル transform）
   print(cluster.geometry())        # [Mesh(...)]（変形対象の shape）

   loc_transform = cmds.spaceLocator(name="myLocator")[0]
   loc_shape_name = cmds.listRelatives(loc_transform, shapes=True)[0]
   locator = Node(loc_shape_name)

   print(locator.get_position())         # Translation(0.0, 0.0, 0.0)
   locator.set_position((1.0, 2.0, 3.0))

``cluster`` ノードは自動的に ``Cluster`` ラッパーへ解決されます。``weighted_node``
はクラスタのハンドル transform（デフォーマ本体とは別ノード）、``geometry`` は
変形対象の shape を返します。``locator`` シェイプは ``Locator`` ラッパーへ解決され、
``get_position``/``set_position`` は ``localPosition`` 属性を ``Translation`` として
扱います。

blendShape のターゲット操作
------------------------------

.. code-block:: python

   from hlib.nodes import Node

   base = hlib.node("pCube1")
   target = hlib.node("pCube2")   # base と同じトポロジーの別メッシュ

   bs = Node(cmds.blendShape(target.full_name(), base.full_name(), name="myBlendShape")[0])
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
ターゲット名を含む表記になります（``attribute()`` メソッドは常に ``"weight"``）。

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
（influence 名が異なる、頂点数が変わった状態への読み込みは
このメソッドの対象外です。同じ頂点数での接続順序変更は検出しません）。

スキン変形を保ったままjointの姿勢を編集する
--------------------------------------------------

.. code-block:: python

   from hlib.decorators import preserved_skin_shape
   from hlib.nodes.joint import Joint

   joint = Joint("hlibExampleJoint")
   with preserved_skin_shape([joint]):
       # 現在のjoint姿勢をスキニング基準へ反映する。
       joint.plug("jointOrientZ").set(45.0)

``preserved_skin_shape`` は Maya標準の ``skinCluster -moveJointsMode`` /
``-recacheBindMatrices`` を使い、ブロック内での joint 姿勢変更を
「新しいバインド姿勢」として扱います。関節の向きを付け直す、
リグを組み替えるといった作業で、既存のスキニングを壊したくない場合に使います。
ブロック全体(モード切り替え・編集・bind行列の再計算)は一回の Undo にまとまります。

任意の階層変更・influence削除や全フレームの変形保持を保証する機能ではありません。
モード変更・再キャッシュ・復元のRuntimeErrorは実装上抑制されるため、
処理後の形状とモードは呼び出し側でも確認してください。
頂点・CVの座標編集はjointのバインド基準変更とは別の処理です。

このページのUndoの説明は通常モード（``fast=False``）を前提とします。
対応する値更新メソッドの ``fast=True`` はUndo対象外です。対応範囲と制限は :doc:`fast_edit` を参照してください。
