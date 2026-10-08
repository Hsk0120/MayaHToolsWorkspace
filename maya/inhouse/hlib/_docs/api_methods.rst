メソッド仕様
==========================

接続を保護してノードを削除する
--------------------------------

``Node.delete(*, safe=False)`` は既定で従来どおりMaya標準削除を行います。
``safe=True`` では自身またはDAG子孫にDG接続が一つでもあれば、削除せずNoneを返します。
入力・出力の両方とmessage、Set所属、マテリアル接続を含みます。
DAGの親子関係自体は接続に数えません。無効ノードや削除時のエラーは従来どおり送出し、
ロック解除や例外の抑制は行いません。

.. code-block:: python

   node = hlib.getNode("multiplyDivide1")
   node.delete(safe=True)   # 接続がある場合は残す
   node.delete()           # 既定safe=False。従来の削除

``Joint.delete`` と ``Nodes.delete`` / ``Joints.delete`` も同じフラグを受け付けます。
コレクションは接続を持つ対象を残し、削除可能な対象だけを処理します。
JointでスキニングやinverseScale等の接続を検出した場合は、ウェイト移送や子の再親付けも
行いません。safe=FalseのJoint専用削除は従来の仕様を維持します。戻り値は全てNoneです。
削除はUndoに対応します。safe=Falseが従来の削除に相当するためforceは追加していません。

このフラグはノードのメソッド用です。``hlib.delete()``、PlugやUIのdeleteには追加していません。
``deleteUnusedIntermediateShapes()`` は標準のマテリアル所属を許容する専用判定のため、
このsafeモードとは判定条件が異なります。

形状のスキニング関係
--------------------

Shape/Transform共通の ``getSkinClusters()`` は、対象Shapeを変形するSkinClusterの
重複なしリストを返します。Transformでは直下の非中間Shapeを対象にします。
``getBindPoses()`` はそれらが参照するDagPoseを重複・未接続を除いて返します。
どちらも引数はなく、対象なしは空リストです。Mesh・NURBS等で共通に使用できます。
Jointの既存 ``getSkinClusters()`` はinfluence接続照会を維持します。
具体例・探索範囲は :doc:`dag_pose` を参照してください。

所有ノード・名前・階層
------------------------

``hasAttr``、``getParent``、``getChildren``、``isFromReferencedFile``、``mnode``、``mpath``、
``Plug.getLongName``、``Plug.delete``、``Vector.lengthSq`` を正式名とします。
旧 ``hasAttribute/parentNode/childTransforms/isReferenced/mobject/dagPath/attributeName/deleteAttribute/lengthSquared``
の互換別名はありません。所有ノードは ``plug.getNode()`` で取得します。

.. code-block:: python

   node = hlib.createNode("transform", name="control")
   plug = node.getPlug("tx")
   print(plug.getNode())       # control
   print(plug.getName())       # control.tx
   print(plug.getLongName())   # translateX
   print(plug.getAttrName())   # .tx
   print(node.getFullPath())   # |control
   node.hide()
   node.show()

``getChildren()`` はShapeと中間ノードを除きます。``shapes=True``、``intermediates=True``
で含められます。従来の全子取得 ``getChildNodes()`` も使用できます。
``getParent(step=1)`` は親階層を遡り、ルートを越えるとNoneです。
``getShape(idx=0)`` は対象がなければNoneです。
``isVisible()`` は親を含むDAGの表示判定、``getVisibility()`` は自身のvisibility値です。

接続照会
----------

``getSource()`` と ``getDestinations()`` はunitConversion系を飛ばします。
直結先が必要な場合は ``getSourceWithConversion()`` と ``getDestinationsWithConversions()`` を使います。
既存の内製ツールは直結探索へ移行し、処理対象を維持しています。
NodeとPlugの ``getConnections/getInputs/getOutputs`` は ``asNode/asPair/index/type/t/et/scn`` 等を扱います。

.. code-block:: python

   upstream = plug.getSource()
   immediate = plug.getSourceWithConversion()
   nodes = node.getInputs(asNode=True, scn=True)
   pairs = node.getConnections(asPair=True)

フラグ・enum・変換
------------------

``setLocked/setKeyable/setChannelBox`` は ``leaf=True`` で複合アトリビュートの末端へ適用できます。
``unlock(below=True)`` は上位と下位のロックを解除し、変更したPlugのリストを返します。
``mute/unmute`` と ``show/hide`` も利用できます。通常のsetterは自身を返します。
``getEnumName()`` は現在値、``getEnumFieldName(val)`` は指定値の名前を返します。

Transformの ``getT/setT`` 等の短縮アクセサーは廃止しました。
取得の正式本体 ``getTranslation()`` 等と、そのget省略入口は使えます。
``getJointOrientQuaternion(ws=False)`` は ``getQuaternion(ws=False, r=False)`` に相当します。
``getRotation/getEuler`` は既存のhlib独自の行列由来Euler取得を維持します。

配列と対応範囲
----------------

``getNextAvailable(start=-1, asPlug=False, checkLocked=True, checkChildren=True)`` は
入力接続・ロックを避けた空き番号を返します。startが負の場合は最後の接続の次から探します。
startより小さい既存要素がある場合も、接続済み番号を避けます。配列親がロックされている場合は探索を続けず例外を返します。

``addElement(idx=None)`` は指定要素と必要な上位要素を実体化し、新規要素を下位からリストで返します。
既存要素は空リストです。要素自身に呼ぶ場合はidxを省略できます。
Maya標準の評価を利用するため、追加自体のUndoは未対応です。
messageやMaya内部型の実体化はNotImplementedErrorで拒否します。
独自Undoプラグインは追加しません。message配列は取得した参照へ接続してください。

``getElement(index, create=False)`` は従来の論理インデックス指定を維持しています。
要素の格納順を表す物理インデックスではありません。
Transformation値型とgetTransformation/setTransformationは :doc:`transformation` を参照してください。

便利メソッドと角括弧アクセス
----------------------------

``plug.setAlias("alias")`` は別名を設定し、``setAlias()`` は解除します。
``plug.setKey(t=1, v=10)`` はmaya.cmds.setKeyframeを呼び、値と時間はUI単位です。
どちらも自身を返し、Undoできます。
``plug.getAnimLayers(selected=False, exact=False)`` は入力チェーンのレイヤー名を
上位から返し、末尾にベースレイヤーを含めます。selected=Trueで選択レイヤーに限定し、
exact=Trueも指定するとベースも選択状態で絞ります。proxy・mute・pairBlendを経由して調べます。

``node.getInstances(noSelf=False)`` は各DAGパスのNodeリスト、
``getParents(indirect=False)`` は直接の親リストを返します。
``iterBreadthFirst()`` と ``iterDepthFirst()`` は自身から幅優先・深さ優先で反復します。
``shapes/intermediates/underWorld`` で探索範囲を指定します。

配列要素の取得は ``array[3]`` を使います。
未作成の配列要素も参照でき、取得だけでは実体化しません。
値設定・接続で要素を作成します。``for element in array`` は既存要素だけを論理番号順に返します。
``array.get()`` は論理番号をキーにした辞書のままです。
既存の ``getElement(index, create=False)`` の明示的な存在検査・実体化機能は維持します。

.. code-block:: python

   node.samples[3].set(12)
   for element in node.samples:
       value = element.get()

全API互換は対象外です。
複合アトリビュートの子も ``compound[0]``、``compound["translateX"]`` で取得します。
旧 ``child()`` は使用しません。``node.getPlug("target")[0]["weight"]`` のように連続指定できます。
複合PlugとArrayPlugをmaya.cmdsへ渡す場合は ``str(plug)`` または ``plug.getFullName()`` を使います。
hlibのコマンドにはそのまま渡せます。
``addAttr()`` の既定Plug返却・既存数学型のOpenMaya継承・内部単位も維持しています。
