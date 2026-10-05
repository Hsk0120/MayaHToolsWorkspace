cymelに合わせたメソッド
==========================

所有ノード・名前・階層
------------------------

``hasAttr``、``parent``、``children``、``isFromReferencedFile``、``mnode``、``mpath``、
``Plug.longName``、``Plug.delete``、``Vector.lengthSq`` を正式名とします。
旧 ``hasAttribute/parentNode/childTransforms/isReferenced/mobject/dagPath/attributeName/deleteAttribute/lengthSquared``
の互換別名はありません。所有ノードは ``plug.node()`` で取得します。

.. code-block:: python

   node = hlib.createNode("transform", name="control")
   plug = node.plug("tx")
   print(plug.node())       # control
   print(plug.name())       # control.tx
   print(plug.longName())   # translateX
   print(plug.attrName())   # .tx
   print(node.fullPath())   # |control
   node.hide()
   node.show()

``children()`` はShapeと中間ノードを除きます。``shapes=True``、``intermediates=True``
で含められます。従来の全子取得 ``childNodes()`` も使用できます。
``parent(step=1)`` は親階層を遡り、ルートを越えるとNoneです。
``shape(idx=0)`` は対象がなければNoneです。
``isVisible()`` は親を含むDAGの表示判定、``getVisibility()`` は自身のvisibility値です。

接続照会
----------

``source()`` と ``destinations()`` はunitConversion系を飛ばします。
直結先が必要な場合は ``sourceWithConversion()`` と ``destinationsWithConversions()`` を使います。
既存の内製ツールは直結探索へ移行し、処理対象を維持しています。
NodeとPlugの ``connections/inputs/outputs`` は ``asNode/asPair/index/type/t/et/scn`` 等を扱います。

.. code-block:: python

   upstream = plug.source()
   immediate = plug.sourceWithConversion()
   nodes = node.inputs(asNode=True, scn=True)
   pairs = node.connections(asPair=True)

フラグ・enum・変換
------------------

``setLocked/setKeyable/setChannelBox`` は ``leaf=True`` で複合アトリビュートの末端へ適用できます。
``unlock(below=True)`` は上位と下位のロックを解除し、変更したPlugのリストを返します。
``mute/unmute`` と ``show/hide`` も利用できます。通常のsetterは自身を返します。
``getEnumName()`` は現在値、``enumName(val)`` は指定値の名前を返します。

Transformには ``getT/setT``、``getQ/setQ``、``getS/setS``、``getSh/setSh``、``getM/setM``
を用意しています。``getJOQ(ws=False)`` は ``getQuaternion(ws=False, r=False)`` に相当します。
``getRotation/getEuler`` は既存のhlib独自の行列由来Euler取得を維持します。

配列と対応範囲
----------------

``nextAvailable(start=-1, asPlug=False, checkLocked=True, checkChildren=True)`` は
入力接続・ロックを避けた空き番号を返します。startが負の場合は最後の接続の次から探します。
同梱cymelには、startより小さい既存要素があると接続済み番号を返すケースがありますが、
hlibはその番号も避けます。配列親がロックされている場合は探索を続けず例外を返します。

``addElement(idx=None)`` は指定要素と必要な上位要素を実体化し、新規要素を下位からリストで返します。
既存要素は空リストです。要素自身に呼ぶ場合はidxを省略できます。
Maya標準の評価を利用するため、追加自体のUndoは未対応です。
messageやMaya内部型の実体化はNotImplementedErrorで拒否します。
独自Undoプラグインは追加しません。message配列は取得した参照へ接続してください。

``element(index, create=False)`` は従来の論理インデックス指定を維持しています。
cymelの物理インデックス指定 ``element(idx)`` とは異なります。
Transformation値型とgetX/setXは :doc:`transformation` を参照してください。

便利メソッドと角括弧アクセス
----------------------------

``plug.setAlias("alias")`` は別名を設定し、``setAlias()`` は解除します。
``plug.setKey(t=1, v=10)`` はmaya.cmds.setKeyframeを呼び、値と時間はUI単位です。
どちらも自身を返し、Undoできます。
``plug.animLayers(selected=False, exact=False)`` は入力チェーンのレイヤー名を
上位から返し、末尾にベースレイヤーを含めます。selected=Trueで選択レイヤーに限定し、
exact=Trueも指定するとベースも選択状態で絞ります。proxy・mute・pairBlendを経由して調べます。

``node.instances(noSelf=False)`` は各DAGパスのNodeリスト、
``parents(indirect=False)`` は直接の親リストを返します。
``iterBreadthFirst()`` と ``iterDepthFirst()`` は自身から幅優先・深さ優先で反復します。
``shapes/intermediates/underWorld`` で探索範囲を指定します。

配列要素の取得は ``array[3]`` を使います。
未作成の配列要素も参照でき、取得だけでは実体化しません。
値設定・接続で要素を作成します。``for element in array`` は既存要素だけを論理番号順に返します。
``array.get()`` は論理番号をキーにした辞書のままです。
既存の ``element(index, create=False)`` の明示的な存在検査・実体化機能は維持します。

.. code-block:: python

   node.samples[3].set(12)
   for element in node.samples:
       value = element.get()

全API互換は対象外です。
複合アトリビュートの子も ``compound[0]``、``compound["translateX"]`` で取得します。
旧 ``child()`` は使用しません。``node.target[0]["weight"]`` のように連続指定できます。
複合PlugとArrayPlugをmaya.cmdsへ渡す場合は ``str(plug)`` または ``plug.fullName()`` を使います。
hlibのコマンドにはそのまま渡せます。
``addAttr()`` の既定Plug返却・既存数学型のOpenMaya継承・内部単位も維持しています。
