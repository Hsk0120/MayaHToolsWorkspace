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
また、Transformation値型とgetX/setX、アニメーションレイヤー探索などの全API互換は対象外です。
``addAttr()`` の既定Plug返却・既存数学型のOpenMaya継承・内部単位も維持しています。
