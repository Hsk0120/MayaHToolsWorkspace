アトリビュートとPlug
============================================================

アトリビュートの取得には ``node.getPlug()`` を使います。接続・メタ情報・配列要素の操作を説明します。
ノードを含むアトリビュート名からは ``hlib.getAttr("node.attr")`` または
``hlib.getPlug("node.attr")`` で型付きPlugを取得できます。
``node.getPlug()`` はアトリビュート名(ロング名・ショート名・エイリアス)のほか、``input1D[3]``・
``worldMatrix[0]``・``pnts[2].pntx`` のような配列要素と子アトリビュートを含むアトリビュートパス
(``str(plug)`` の ``.`` 以降と同じ表記)も受け付けます。

例は Maya の Script Editor で実行します。既存ノード名は使用するシーンに合わせてください。
最初に ``import hlib`` を実行してください。

接続の絞り込みとアトリビュートの列挙・エイリアス
----------------------------------------------------

.. code-block:: python

   import maya.cmds as cmds

   source = hlib.createNode("transform", name="connSource")
   target = hlib.createNode("transform", name="connTarget")
   source.getPlug("translateX").connectTo(target.getPlug("translateX"))

   print(len(target.getInputs()))                    # 1
   print(target.getInputs(type="transform"))          # 同じ1件（接続元が transform）
   print(target.getInputs(type="mesh"))               # []（一致なし）
   print(len(source.getConnections(type="transform")))  # 1

   plugs = target.getPlugs(keyable=True)              # cmds.listAttr(keyable=True) 相当
   print(any(plug.getLongName() == "translateX" for plug in plugs))   # True

   cmds.aliasAttr("myAlias", target.getPlug("translateY").getFullName())
   for alias_name, plug in target.getAliases():
       print(alias_name, plug.getFullName())           # myAlias connTarget.myAlias

``inputs``/``outputs``/``connections`` の ``type`` 引数は接続先ノードの nodeType を
``isType`` と同じ継承チェーンで絞り込みます（例: ``type="animCurve"``）。
``plugs`` は ``cmds.listAttr`` にキーワード引数をそのまま渡してアトリビュートを Plug として
列挙します。listAttr が報告する名前の一部（未確保の要素を持つ配列複合アトリビュートの子など、
``publishedNodeInfo`` のような組み込みアトリビュートでよく見られます）は実際には評価できず
黙ってスキップされるため、件数は listAttr の結果と必ずしも一致しません。
``aliases`` は OpenMaya で取得したエイリアスを ``(エイリアス名, Plug)`` の
タプル列として返します。``Plug.getFullName()`` はアトリビュートにエイリアスがあればエイリアス名を
使う(``MPlug.name()`` と同じ表記)ため、戻り値の Plug の ``getFullName()`` も
ロング名(``translateY``)ではなくエイリアス名(``myAlias``)を含む表記になります。
``cmds.listConnections(plugs=True)`` の表記はアトリビュートによって異なり、配列要素のエイリアス
(blendShape の ``weight[0]`` の ``smile`` など)はエイリアス名、配列でないアトリビュートの
エイリアス(``translateY`` の ``myAlias`` など)はロング名を返します。名前を文字列で
比較せず、Plug・MPlug 同士で比較してください(``plug.mplug() == other.mplug()``)。

プラグ名
--------

``str(plug)`` と ``plug.getFullName()`` は、maya.cmds で一意に解決できる
``<ノードの最短一意名>.<アトリビュートパス>`` を返します。同じ短い名前のノードが複数あっても
``grp1|dup.translateX`` のようにパスを含むため、``cmds.getAttr(plug)`` のように
Plug を maya.cmds へそのまま渡せます。名前は呼び出すたびに求め直すため、
名前変更・親子付け替えにも追従します。所有ノードが削除済み、または動的アトリビュートが
``deleteAttr`` で削除済みなら空文字列です(``plug.isValid()`` が ``False``。
このとき ``get()``/``set()`` と、アトリビュートの情報・接続の問い合わせは ``RuntimeError`` になります)。
``plug.getName()`` はノード名を含む短いPlug名を返します。短名のみは ``getShortName()``、
長名のみは ``getLongName()``、要素番号や階層を含む先頭ドット付きパスは ``getAttrName()`` です。

.. code-block:: python

   import maya.cmds as cmds

   grp1 = hlib.createNode("transform", name="plugNameGrp1")
   grp2 = hlib.createNode("transform", name="plugNameGrp2")
   dup = hlib.createNode("transform", name="plugNameDup", parent=grp1)
   hlib.createNode("transform", name="plugNameDup", parent=grp2)

   plug = dup.getPlug("tx")
   print(plug)               # plugNameGrp1|plugNameDup.translateX
   print(plug.getName())        # plugNameGrp1|plugNameDup.tx
   cmds.setAttr(plug, 2.0)   # 同名ノードがあっても一意に解決できる

受け付ける入力と ``maya.cmds`` へ渡せないオブジェクトは :doc:`cmds_interop` を参照してください。

アトリビュートのメタ情報
----------------------------

.. code-block:: python

   import maya.cmds as cmds

   node = hlib.createNode("transform", name="attrMetaExample")
   cmds.addAttr(node.getName(), longName="strength", attributeType="double",
                min=0, max=10, defaultValue=5, hidden=True)
   cmds.addAttr(node.getName(), longName="mode", attributeType="enum",
                enumName="Off:Low:High", defaultValue=1)

   plug = node.getPlug("strength")
   print(plug.isDynamic())   # True（addAttr で追加したカスタムアトリビュート）
   print(plug.isHidden())    # True
   print(plug.hasMin(), plug.getMin())   # True 0.0
   print(plug.hasMax(), plug.getMax())   # True 10.0
   print(plug.getDefault())             # 5.0

   mode_plug = node.getPlug("mode")
   print(mode_plug.getEnumName())    # "Low"（既定値 1 に対応する名前）

``min``/``max``/``default`` は数値アトリビュートでは ``float`` をそのまま返しますが、
``rotateX`` のような角度・距離・時間アトリビュートでは Maya API 2.0 の単位付きオブジェクト
（``MAngle``/``MDistance``/``MTime``）をそのまま返します。誤った単位換算を
避けるため、hlib 内部では変換を行いません。必要な単位は呼び出し側で
``.value`` や ``.asUnits(...)`` を使って変換してください。
``enumName`` は enum アトリビュート以外に使うと ``TypeError`` になります。
``isValid()`` は所有ノードとアトリビュートの参照が有効かを判定します。
値の読み書きが成功することまでは保証しません。
``isReadable``/``isWritable``/``isStorable`` はアトリビュート定義の各フラグを返し、
ロックや入力接続を含む現在の編集可否を判定するものではありません。
``hasSoftMin``/``softMin``/``hasSoftMax``/``softMax`` で UI スライダーの
ソフトレンジ（値の入力自体は制限しない）を取得できます。
``getEnumValue(name)`` は ``getEnumFieldName(val)`` の逆引きで、フィールド名から enum 値を
取得します（一致しなければ ``ValueError``）。``getNiceName()`` は Attribute Editor
などで使われる表示名を返します（``translateX`` → ``"Translate X"``）。

チャンネルボックス表示とプラグ接続の判定
------------------------------------------

.. code-block:: python

   node = hlib.createNode("transform", name="channelBoxExample")
   plug = node.getPlug("translateX")

   plug.setFlags(keyable=False)          # キー不可（チャンネルボックスからも隠れる）
   plug.setFlags(channelBox=True)       # キー不可のままチャンネルボックスにのみ表示

   other = hlib.createNode("transform", name="channelBoxOther")
   plug.connectTo(other.getPlug("translateX"))
   print(plug.isConnectedTo(other.getPlug("translateX")))   # True
   print(other.getPlug("translateX").isConnectedTo(plug))   # True（向き不問）

``setFlags(locked=..., keyable=..., channelBox=...)`` はアトリビュートの状態をまとめて設定します。
省略したフラグは変更せず、bool以外の状態は更新前に拒否します。``isConnectedTo`` は入力・出力
どちらの向きの接続でも一致すれば ``True`` を返します。

animCurve とミュート
---------------------

.. code-block:: python

   node = hlib.createNode("transform", name="animExample")
   plug = node.getPlug("translateX")
   print(plug.getAnimCurve())   # None（まだキーが無い）

   import maya.cmds as cmds
   cmds.setKeyframe(plug.getFullName(), time=1, value=0.0)
   cmds.setKeyframe(plug.getFullName(), time=24, value=10.0)
   print(plug.getAnimCurve())   # animExample_translateX（接続された animCurve ノード）

   print(plug.isMuted())   # False
   plug.setMuted(True)
   print(plug.isMuted())   # True
   plug.setMuted(False)

``animCurve`` は直接接続された animCurve ノードのみを解決します。
``pairBlend`` やアニメーションレイヤーを介した間接的な接続は対象外で、
その場合は接続の有無にかかわらず ``None`` を返します。
``setMuted(state)`` は ``cmds.mute`` のラッパーで、現在の出力値のまま
アトリビュートの評価を一時的に固定・解除します。

配列プラグの要素追加・削除
----------------------------

.. code-block:: python

   node = hlib.createNode("network", name="arrayPlugExample")
   node.addAttr("values", attributeType="double", multi=True)
   array_plug = node.getPlug("values")

   print(array_plug.getNextAvailableIndex())   # 0（既存要素が無ければ）

   element = array_plug.addElement(0)[0]   # 指定要素を実体化し、新規要素リストを返す
   print(element.getFullName())             # arrayPlugExample.values[0]

   element.set(1.0)                    # 要素に値を設定
   array_plug.removeElement(0)         # 要素を削除

``getNextAvailable(start=0, asPlug=True)`` は入力接続とロックを避けた要素参照を返します。
``getNextAvailableIndex()`` はhlib独自の「まだ存在しない番号」を探す操作で、判定条件が異なります。
``addElement(idx)`` は指定要素と必要な上位要素を実体化し、新規要素を下位から返します。
既存なら空リストです。追加自体のUndoとmessage要素の実体化には対応しません。
message配列では ``getNextAvailable(asPlug=True)`` で取得した参照へ接続してください。
``getElement(create=True)`` も評価による実体化なのでUndo対象外です。

Plug を作る・取得する操作そのもの(``Plug._resolve_input("pma1.input1D[10]")`` や
``Selection([...])`` など)は、存在しない要素の Plug でも要素を作りません。
``worldMatrix`` などのインスタンスごとのアトリビュートは、評価前でもインスタンス番号の要素
(作成直後のノードの ``worldMatrix[0]`` など)を ``getElement()``/``getElements()`` で取得できます。
インスタンス番号には、インスタンス化された祖先による間接インスタンスも含みます。
削除済みノード・削除済みの動的アトリビュートの配列 Plug の要素は取得できません(``RuntimeError``)。

``array_plug[0]`` は ``getElement(0)`` と同じです。この ``[]`` があるため、
ArrayPlug オブジェクト自体を ``maya.cmds`` へ渡すとシーケンスとして展開されて失敗します。
配列アトリビュート全体を渡す場合は ``str(array_plug)`` か ``array_plug.getFullName()`` を渡してください。
要素の Plug と hlib のコマンド(``hlib.select`` など)は、そのまま渡せます。

アニメーションカーブそのものの操作は :doc:`animation_nodes` を参照してください。

このページのUndoの説明は通常モード（``fast=False``）を前提とします。
対応する値更新メソッドの ``fast=True`` はUndo対象外です。対応範囲と制限は :doc:`fast_edit` を参照してください。

getAttrから値を取得する
------------------------

``hlib.getAttr(target, **kwargs)`` は、照会フラグなしならアトリビュート型に対応する
Plugを返します。内部では ``getPlug`` へ委譲し、既存Plugはそのまま返します。
値を読むときは返されたPlugの ``get()`` または ``getu()`` を呼びます。

.. code-block:: python

   plug = hlib.getAttr("pCube1.tx")  # DoubleLinearPlug
   value = hlib.getAttr("pCube1.tx").get()     # 内部単位cm
   ui_value = hlib.getAttr("pCube1.tx").getu()  # 現在の距離UI単位
   kind = hlib.getAttr("pCube1.tx", type=True)  # 従来のMaya状態照会

``Plug.get()`` / ``set()`` は角度rad・距離cm・時間秒で統一しています。
UI単位を変更しても ``set(get())`` は同じ値を維持します。
``getu()`` / ``setu()`` は現在のUI単位を使います。getAttr自体が値を自動変換するのではなく、
値の単位は呼び出すPlugメソッドで選びます。

照会フラグを一つでも指定すると、従来のMaya照会値・状態を返します。
``type=True`` 等の状態フラグだけでなく、``time``・``silent``・Falseの明示指定も
この経路です。Mayaの長短フラグ、値のUI単位、行列のMatrix・3成分のVectorへの変換を維持します。


アトリビュートの値とノードの姿勢
------------------------------------

``Plug.get()`` / ``set()`` は対象アトリビュートの値だけを扱い、空間指定 ``ws`` / ``worldSpace`` は受け付けません。
ワールド空間の値にはTransformの ``getTranslation(ws=True)`` / ``setRotation(..., ws=True)``
などを使います。

.. code-block:: python

   joint = hlib.getNode("joint1")
   rotation = joint.getPlug("rotate").get()
   joint.getPlug("rotate").set(rotation)  # チャンネル値をそのまま戻す
   joint.getPlug("rotate").set((10, 20, 30), unit="deg")
   joint.setRotation((0, 0, 0), ws=True) # jointOrient等を含む姿勢の操作

``rotate`` の値はラジアン・ノードのrotateOrderを持つ ``EulerRotation`` です。
設定時は数値3成分のrad/deg、またはEulerRotation/Quaternionを使えます。
型付き回転はノードのrotateOrderへ変換します。設定はjointOrientやrotateAxis、
他のチャンネルを変更しません。通常モードはUndo対応、``fast=True`` はUndoなしです。


入力接続だけの解除
------------------

``destination.disconnectInput()`` は直接の入力だけを解除し、自身を返します。
出力接続・子の独立接続・unitConversionノードは保持します。未接続なら何もしません。
親の複合接続を解除するときは親Plugへ呼び出します。通常のUndo/Redoに対応します。
``disconnectAll()`` による入出力両方の解除とは用途を区別してください。

``disconnect(src=True, dst=False)`` は入力、
``disconnect(src=False, dst=True)`` は出力、両方Trueなら入出力を切断します。
方向指定では切断した相手Plugのリストを返し、未接続なら空リストです。
入力元Plugを渡す従来の ``disconnect(sourcePlug)`` と、
入力元Plugを返す ``disconnect()`` の仕様も維持します。

配列の編集は番号・値・参照を検証してから書込みまたは接続します。
内部処理は要素を事前に実体化しません。公開 ``getElement(index, create=True)`` の
明示作成は維持します。論理番号はboolを除く整数で、範囲は0〜2147483647です。
型不正はTypeError、範囲外はIndexErrorになります。
