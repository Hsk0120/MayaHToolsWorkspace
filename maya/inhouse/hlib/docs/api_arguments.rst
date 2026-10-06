引数仕様
====================

接続と切断
----------

``connect`` は接続先から呼びます。接続元からは ``connectTo`` を使います。
``force/f``、``lock/l``、``nextAvailable/na`` の長短名はORで評価します。

.. code-block:: python

   dst.connect(src, f=True)
   src.connectTo(dst, f=True)  # 同じ接続方向
   dst.disconnect()           # 入力だけを切断し、入力元Plugを返す
   dst.disconnectInput()      # 未接続でもエラーにせず、自身を返す
   dst.disconnectAll()        # 入力と全出力を明示的に切断
   element = array.connect(src, na=True)
   array.disconnect(src, na=True)

``force=True`` は一時的にロックを解除して接続します。
hlib拡張の ``unlock=False`` を併用するとロック解除を禁止できます。

位置・回転・行列
----------------

空間は ``ws=True`` を基本表記とし、``worldSpace=True`` も使えます。
長短名の同時指定は拒否します。

``getTranslation`` / ``setTranslation`` の ``at`` は
0=親原点、1=translate、2=回転ピボット、3=スケールピボット、4以上=行列原点です。
既定値は2です。以前のhlibの行列原点指定は ``at=4`` へ移行してください。
``setTranslation`` はtranslateだけを書き込み、ピボット自体は動かしません。

.. code-block:: python

   position = node.getTranslation(ws=True)
   origin = node.getTranslation(ws=True, at=4)
   channels = node.setTranslation((10, 2, 3), ws=True, get=True)
   node.setTranslation((10, 2, 3), ws=True, safe=True)
   parent_inverse = node.getMatrix(ws=True, p=True, inv=True)

``getQuaternion`` / ``setQuaternion`` は ``ra`` (rotateAxis)、``r`` (rotate)、
``jo`` (jointOrient)で合成対象を選びます。既定は ``ra=False, r=True, jo=True`` です。
ワールド指定などで未対応の組合せはValueErrorになります。

``getScaling`` / ``setScaling``、``getShearing`` / ``setShearing`` は
ローカル指定でscale/shearチャンネルそのものを扱い、jointのinverseScaleを含めません。
ワールド指定はOpenMayaの分解規約を使います。負スケールの符号は行列から一意に
決まらないため、ワールドの指定値と取得値の符号が一致しない場合があります。
以前の ``getScale/setScale/getShear/setShear`` は廃止しました。

``get=True`` は書き込まず設定すべき値を返します。
位置・回転・スケール・シアーは数値リスト、``setMatrix`` は
``translate/rotate/scale/shear`` をキーとする辞書を返します。
後者の辞書にはhlibの値型を格納します。
コレクションの ``get=True`` も各対象の計算結果のリストを返します。

単位とsafe
----------

Plugの ``get/set`` は内部単位(cm/rad/秒)、``getu/setu`` は現在のUI単位です。
``safe=True`` は書込み失敗を抑制し、複合値では書ける子だけを書き込みます。
Plugのsafe指定は失敗数を返します。Transformのsafe指定は自身を返します。
``fast=True`` はhlib固有のUndoなし直接更新であり、safeとは別の指定です。

.. code-block:: python

   node.getPlug("ry").setu(90)  # UIがdegの場合90度
   failed = node.getPlug("translate").set((1, 2, 3), safe=True)
   node.setRotation((0, 90, 0), ws=True, unit="deg")

``setRotation`` の第2位置引数は空間になりました。``unit`` は名前付きで指定します。
回転double3の ``set`` も第2位置引数はsafe、unitは名前付きです。
通常のsetterが自身を返すhlibの規則と、om2派生の数学型は維持します。
引数・戻り値の対応範囲は、このページに記載した仕様に従います。

アトリビュートの追加
--------------------

正式名を ``addAttr`` に変更しました。旧 ``addAttribute`` は残していません。
typeを省略するとdoubleです。``at:/dt:`` 接頭辞やMayaの ``at/dt`` も使えます。
``childNames/childShortNames/childSuffixes/subType`` で子を自動生成できます。
hlibでは既定で追加したPlugを返します。``getPlug=False`` を明示した場合のみNoneを返します。

.. code-block:: python

   label = node.addAttr("label", "string", dv="control")
   offset = node.addAttr("offset", "double3", subType="doubleLinear")
   node.addAttr("weight", min=0, max=1, dv=1, k=True)
   node.rename("control", ignoreShape=True)

``rename`` の旧 ``ignore_shape`` 引数も ``ignoreShape`` へ移行しました。

ここでの ``addAttr`` はNodeのメソッドです。``hlib.addAttr(node, ...)`` は
Mayaコマンド用の入口で、従来どおり常にPlugを返し、getPlug引数は受け取りません。
