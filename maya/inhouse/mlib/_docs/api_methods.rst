メソッド仕様
==========================

接続を保護してノードを削除する
--------------------------------

``Node.delete(*, safe=False, fast=False)`` は既定で従来どおりMaya標準削除を行います。
``safe=True`` では自身またはDAG子孫にDG接続が一つでもあれば、削除せずNoneを返します。
入力・出力の両方とmessage、Set所属、マテリアル接続を含みます。
DAGの親子関係自体は接続に数えません。無効ノードや削除時のエラーは従来どおり送出し、
ロック解除や例外の抑制は行いません。

.. code-block:: python

   node = mlib.getNode("multiplyDivide1")
   node.delete(safe=True)   # 接続がある場合は残す
   node.delete()           # 既定safe=False。従来の削除

``Joint.delete`` と ``Nodes.delete`` / ``Joints.delete`` も同じフラグを受け付けます。
コレクションは接続を持つ対象を残し、削除可能な対象だけを処理します。
Joint/JointsもNode/Nodesの標準削除を継承します。ウェイト移送・子の保持は行わず、
DAGの子階層もMaya標準の規則で削除します。戻り値は全てNoneです。
ウェイト移送と子の再親付けを伴う削除は ``mlrig.setups.JointHierarchy.delete`` を使います。
通常削除はUndoに対応し、fast=TrueはOM2で直接削除します。safe=Falseが標準削除で、force指定はありません。

このフラグはノードのメソッド用です。``mlib.delete()``、PlugやUIのdeleteには追加していません。
``deleteUnusedIntermediateShapes()`` は標準のマテリアル所属を許容する専用判定のため、
このsafeモードとは判定条件が異なります。

追加アトリビュートの並び順
------------------------------

``moveAttrOrder(name, offset)`` は対象範囲の定義と値・フラグ・別名・接続を保存し、
アトリビュートを作り直してChannel Boxの順序を変更します。
全定義を復元してから接続を復元するため、同じ範囲内のアトリビュート同士の接続も扱います。
数値・enum・文字列のトップレベル非複合・非配列に対応し、範囲内に未対応型があれば変更前に拒否します。
短名・既定値・min/max・softMin/softMax・表示やロック等の設定も保持します。

通常は一回のUndoで戻せます。変更途中の失敗では、この処理の変更だけをUndoして復元します。
実際の並び替えが必要な場合、Undo無効時はRuntimeError、fast文脈ではNotImplementedErrorとして、
削除前に拒否します。既に端にある等の変更不要な呼出しは自身を返します。

形状のスキニング関係
--------------------

Shape/Transform共通の ``getSkinClusters()`` は、対象Shapeを変形するSkinClusterの
重複なしリストを返します。Transformでは直下の非中間Shapeを対象にします。
``getBindPoses()`` はそれらが参照するDagPoseを重複・未接続を除いて返します。
どちらも引数はなく、対象なしは空リストです。Mesh・NURBS等で共通に使用できます。
Jointの既存 ``getSkinClusters()`` はinfluence接続照会を維持します。
具体例・探索範囲は :doc:`dag_pose` を参照してください。

``collectSkinClusters()`` は単数DAGノード・DagNodesで、重複を除いた
``SkinClusters`` コレクションを返します。そのまま ``removeUnusedInfluences()``
などの一括操作へ渡せます。従来の単数 ``getSkinClusters()`` のリスト、
DagNodesの形状ごとのリスト、Jointsの専用集約の返却は変更しません。

コンポーネントの参照と現在の有効性
----------------------------------

Meshの ``getVertex/getVertices/getEdge/getEdges/getFace/getFaces/getUV/getUVs`` と
カーブの ``getCV/getCVs`` を使用します。番号・idx別名・返却型は維持します。
``components[0]`` の0はコレクション内の位置で、実頂点番号は ``component.index`` です。

``valid()`` は保持するshapeの生存・種類と、現在の番号範囲を照会します。
削除やトポロジー縮小で参照が無効になった場合はFalseです。空のコレクションも
適合するshapeが生存していればTrueです。番号が有効でも、トポロジー変更前の
同じ頂点・UVであることまで保証しません。
具体例は :doc:`guide_geometry` を参照してください。

所有ノード・名前・階層
------------------------

``hasAttr``、``getParent``、``getChildren``、``fromReferencedFile``、``mnode``、``mpath``、
``Plug.getLongName``、``Plug.delete``、``Vector.lengthSq`` を正式名とします。
旧 ``hasAttribute/parentNode/childTransforms/isReferenced/mobject/dagPath/attributeName/deleteAttribute/lengthSquared``
の互換別名はありません。所有ノードは ``plug.getNode()`` で取得します。

.. code-block:: python

   node = mlib.createNode("transform", name="control")
   plug = node.getPlug("tx")
   print(plug.getNode())       # control
   print(plug.getName())       # control.tx
   print(plug.getLongName())   # translateX
   print(plug.getAttrName())   # .tx
   print(node.getFullPath())   # |control
   node.hide()
   node.show()

``getChildren()`` はShapeと中間ノードを除きます。``shapes=True``、``intermediates=True``
で含められます。全子取得は ``getChildren(shapes=True, intermediates=True)`` です。
``getParent(step=1)`` は親階層を遡り、ルートを越えるとNoneです。
``getShape(idx=0)`` は対象がなければNoneです。
``getVisible()`` は親を含むDAGの表示判定、``getVisibility()`` は自身のvisibility値です。

接続照会
----------

``getSource()`` と ``getDestinations()`` はunitConversion系を飛ばします。
直結先が必要な場合は ``getSource(skipConversionNodes=False)`` と ``getDestinations(skipConversionNodes=False)`` を使います。
既存の内製ツールは直結探索へ移行し、処理対象を維持しています。
NodeとPlugの ``getConnections`` は ``asNode/asPair/index/type/t/et/scn`` 等を扱います。

Plugの ``getConnections`` は ``src/source`` で入力、``dst/destination`` で出力を選べます。
既存の ``s/d`` は長名とANDで評価します。
``connected``・``connectedTo``・``disconnectAll`` も、boolのキーワード専用引数
``src=True, dst=True`` と別名 ``source/destination`` を受け付けます。
判定はbool、``disconnectAll`` は自身を返し、両Falseでは検索・切断を行いません。
入力のみは ``getConnections(src=True, dst=False)``、出力のみは逆方向を指定します。
解除時の戻り値と既定の違いは :doc:`api_arguments` の「接続と切断」を参照してください。

Plugの ``settable()`` はMaya標準のsettable照会で、現在のロック・入力接続等から
値を設定できる状態かを返します。``writable()`` はアトリビュート定義の書込可否であり、
現在の編集可否とは異なります。値の型・範囲などによる設定成功まで保証する判定ではありません。

.. code-block:: python

   upstream = plug.getSource()
   immediate = plug.getSource(skipConversionNodes=False)
   nodes = node.getConnections(True, False, asNode=True, scn=True)
   pairs = node.getConnections(asPair=True)
   outputs = plug.getConnections(src=False, dst=True)
   has_input = plug.connected(src=True, dst=False)
   sends_to_other = plug.connectedTo(other, src=False, dst=True)

フラグ・enum・変換
------------------

``setLocked/setKeyable/setChannelBox`` は ``leaf=True`` で複合アトリビュートの末端へ適用できます。
``unlock(below=True)`` は上位と下位のロックを解除し、変更したPlugのリストを返します。
``mute/unmute`` と ``show/hide`` も利用できます。通常のsetterは自身を返します。対応する更新は ``fast=True`` でOM2へ直接反映します。
``getEnumName()`` は現在値、``getEnumFieldName(val)`` は指定値の名前を返します。

Transformの ``getT/setT`` 等の短縮アクセサーは廃止しました。
姿勢の取得には ``getTranslate()`` 等を使います。
``getJointOrientQuaternion(ws=False)`` は ``getQuaternion(ws=False, r=False)`` に相当します。
``getRotation/getEuler`` は既存のmlib独自の行列由来Euler取得を維持します。

配列と対応範囲
----------------

``getNextAvailable(start=-1, asPlug=False, checkLocked=True, checkChildren=True)`` は
入力接続・ロックを避けた空き番号を返します。startが負の場合は最後の接続の次から探します。
startより小さい既存要素がある場合も、接続済み番号を避けます。配列親がロックされている場合は探索を続けず例外を返します。

未作成要素は ``array[index]`` で参照し、そのPlugへの値設定・接続で作成します。
message配列も参照への接続で作成します。要素の実体化だけを行うメソッドはありません。

``getElement(index)`` は既存要素だけを論理インデックスで取得し、未作成ならIndexErrorです。
``getIndices()`` は既存要素の論理番号を昇順のlistで返し、値を評価しません。
``getElements()`` と同じく、ワールド空間アトリビュートはDAGインスタンス番号も含みます。
要素の格納順を表す物理インデックスではありません。
Transformation値型とgetTransformation/setTransformationは :doc:`transformation` を参照してください。

便利メソッドと角括弧アクセス
----------------------------

``plug.setAlias("alias")`` は別名を設定し、``setAlias()`` は解除します。
``plug.setKey(t=1, v=10)`` は通常maya.cmds.setKeyframeを呼び、値と時間はUI単位です。
fast=Trueは単一時刻・値・接線型の指定だけを受け付け、OM2でカーブを更新します。
どちらも自身を返します。通常モードはUndo対応、fast=TrueはUndoなしです。
``plug.getAnimLayers(selected=False, exact=False)`` は入力チェーンのレイヤー名を
上位から返し、末尾にベースレイヤーを含めます。selected=Trueで選択レイヤーに限定し、
exact=Trueも指定するとベースも選択状態で絞ります。proxy・mute・pairBlendを経由して調べます。

``node.getInstances(noSelf=False)`` は各DAGパスのNodeリスト、
``getParents(indirect=False)`` は直接の親リストを返します。
``getChildren(allDescendents=True, includeSelf=True, order="breadthFirst")`` は自身から幅優先、
``order="depthFirst"`` は深さ優先で子孫を取得します。
``shapes/intermediates/underWorld`` で探索範囲を指定します。

配列要素の取得は ``array[3]`` を使います。
未作成の配列要素も参照でき、取得だけでは実体化しません。
値設定・接続で要素を作成します。``for element in array`` は既存要素だけを論理番号順に返します。
``array.get()`` は論理番号をキーにした辞書のままです。
``getElement(index)`` は既存要素だけを返します。参照取得に作成フラグはありません。

.. code-block:: python

   node.samples[3].set(12)
   for element in node.samples:
       value = element.get()

全API互換は対象外です。
複合アトリビュートの子も ``compound[0]``、``compound["translateX"]`` で取得します。
旧 ``child()`` は使用しません。``node.getPlug("target")[0]["weight"]`` のように連続指定できます。
複合PlugとArrayPlugをmaya.cmdsへ渡す場合は ``str(plug)`` または ``plug.getFullName()`` を使います。
mlibのコマンドにはそのまま渡せます。
``addAttr()`` の既定Plug返却・既存数学型のOpenMaya継承・内部単位も維持しています。
