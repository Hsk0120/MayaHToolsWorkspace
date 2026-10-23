アトリビュートとPlug
============================================================

アトリビュートの取得には ``node.getPlug()`` を使います。接続・メタ情報・配列要素の操作を説明します。
ノードを含むアトリビュート名からは ``mlib.getPlug("node.attr")`` でPlug参照を取得できます。
``node.getPlug()`` はアトリビュート名(ロング名・ショート名・エイリアス)のほか、``input1D[3]``・
``worldMatrix[0]``・``pnts[2].pntx`` のような配列要素と子アトリビュートを含むアトリビュートパス
(``str(plug)`` の ``.`` 以降と同じ表記)も受け付けます。

例は Maya の Script Editor で実行します。既存ノード名は使用するシーンに合わせてください。
最初に ``import mlib`` を実行してください。

接続の絞り込みとアトリビュートの列挙・エイリアス
----------------------------------------------------

.. code-block:: python

   import maya.cmds as cmds

   source = mlib.createNode("transform", name="connSource")
   target = mlib.createNode("transform", name="connTarget")
   source.getPlug("translateX").connectTo(target.getPlug("translateX"))

   print(len(target.getConnections(True, False)))                    # 1
   print(target.getConnections(True, False, type="transform"))          # 同じ1件（接続元が transform）
   print(target.getConnections(True, False, type="mesh"))               # []（一致なし）
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
使う(``MPlug.getName()`` と同じ表記)ため、戻り値の Plug の ``getFullName()`` も
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

   grp1 = mlib.createNode("transform", name="plugNameGrp1")
   grp2 = mlib.createNode("transform", name="plugNameGrp2")
   dup = mlib.createNode("transform", name="plugNameDup", parent=grp1)
   mlib.createNode("transform", name="plugNameDup", parent=grp2)

   plug = dup.getPlug("tx")
   print(plug)               # plugNameGrp1|plugNameDup.translateX
   print(plug.getName())        # plugNameGrp1|plugNameDup.tx
   cmds.setAttr(plug, 2.0)   # 同名ノードがあっても一意に解決できる

受け付ける入力と ``maya.cmds`` へ渡せないオブジェクトは :doc:`cmds_interop` を参照してください。

アトリビュートのメタ情報
----------------------------

.. code-block:: python

   import maya.cmds as cmds

   node = mlib.createNode("transform", name="attrMetaExample")
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

``getMin()``/``getMax()``/``getDefault()`` は数値アトリビュートでは ``float`` をそのまま返しますが、
``rotateX`` のような角度・距離・時間アトリビュートでは Maya API 2.0 の単位付きオブジェクト
（``MAngle``/``MDistance``/``MTime``）をそのまま返します。誤った単位換算を
避けるため、mlib 内部では変換を行いません。必要な単位は呼び出し側で
``.value`` や ``.asUnits(...)`` を使って変換してください。
``getEnumName()`` は enum アトリビュート以外に使うと ``TypeError`` になります。
``isValid()`` は所有ノードとアトリビュートの参照が有効かを判定します。
値の読み書きが成功することまでは保証しません。
``isReadable``/``isWritable``/``isStorable`` はアトリビュート定義の各フラグを返し、
ロックや入力接続を含む現在の編集可否を判定するものではありません。
現在の値の編集可否は ``isSettable()`` で照会します。

.. code-block:: python

   control = mlib.createNode("transform", name="settableExample")
   translate_x = control.getPlug("translateX")
   print(translate_x.isWritable())  # アトリビュート定義の書込み可否
   if translate_x.isSettable():     # 現在のロック・入力接続を含むMayaの判定
       translate_x.set(10.0)      # 内部距離単位cm

``isSettable()`` は値の型・範囲や、その後の状態変化による成功までは保証しません。
設定自体のエラーは ``set()`` の契約に従います。
``hasSoftMin``/``getSoftMin``/``hasSoftMax``/``getSoftMax`` で UI スライダーの
ソフトレンジ（値の入力自体は制限しない）を取得できます。
``getEnumValue(name)`` は ``getEnumFieldName(val)`` の逆引きで、フィールド名から enum 値を
取得します（一致しなければ ``ValueError``）。``getNiceName()`` は Attribute Editor
などで使われる表示名を返します（``translateX`` → ``"Translate X"``）。

チャンネルボックス表示とプラグ接続の判定
------------------------------------------

.. code-block:: python

   node = mlib.createNode("transform", name="channelBoxExample")
   plug = node.getPlug("translateX")

   plug.setFlags(keyable=False)          # キー不可（チャンネルボックスからも隠れる）
   plug.setFlags(channelBox=True)       # キー不可のままチャンネルボックスにのみ表示

   other = mlib.createNode("transform", name="channelBoxOther")
   plug.connectTo(other.getPlug("translateX"))
   print(plug.isConnectedTo(other.getPlug("translateX")))   # True
   print(other.getPlug("translateX").isConnectedTo(plug))   # True（向き不問）
   print(plug.isConnected(src=True, dst=False))            # False（入力なし）
   print(plug.isConnected(src=False, dst=True))            # True（出力あり）
   print(plug.isConnectedTo(other.getPlug("translateX"), src=False, dst=True))  # True
   print(plug.isConnectedTo(other.getPlug("translateX"), src=True, dst=False))  # False
   print(plug.getConnections(src=False, dst=True))         # 出力先Plugのリスト

``setFlags(locked=..., keyable=..., channelBox=...)`` はアトリビュートの状態をまとめて設定します。
省略したフラグは変更せず、bool以外の状態は更新前に拒否します。

``isConnected`` と ``isConnectedTo`` は既定で入力・出力を両方調べます。
``src=True, dst=False`` は自身への入力、``src=False, dst=True`` は自身からの出力だけを調べます。
``source/destination`` も同じ意味の別名です。両FalseならFalseを返し、bool以外や別名との重複は
``TypeError`` になります。``isConnectedTo`` は変換ノードの先や子・配列要素の独立接続を展開しません。
``isConnected`` はMPlugの従来の接続状態判定を維持し、子・配列要素の列挙は行いません。

``getConnections`` でも同じ ``src/source``・``dst/destination`` を使えます。
既存の ``s/d`` とANDで評価し、両Falseなら通常は空リストです。
子や配列要素まで調べるかは従来どおり ``checkChildren/checkElements`` で指定します。
入力・出力の列挙は同じメソッドの方向フラグで選びます。
直接または変換ノードを飛ばした接続元・接続先は ``getSource/getDestinations`` で取得します。

animCurve とミュート
---------------------

.. code-block:: python

   node = mlib.createNode("transform", name="animExample")
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

   node = mlib.createNode("network", name="arrayPlugExample")
   node.addAttr("values", attributeType="double", multi=True)
   array_plug = node.getPlug("values")

   print(array_plug.getNextAvailableIndex())   # 0（既存要素が無ければ）

   element = array_plug[0]             # 未作成要素の参照。まだ実体化しない
   print(element.getFullName())             # arrayPlugExample.values[0]

   element.set(1.0)                    # 要素に値を設定
   array_plug.removeElement(0)         # 要素を削除

``getNextAvailable(start=0, asPlug=True)`` は入力接続とロックを避けた要素参照を返します。
``getNextAvailableIndex()`` はmlib独自の「まだ存在しない番号」を探す操作で、判定条件が異なります。
未作成番号の参照は ``array_plug[index]`` で取得し、値設定または接続で要素を作成します。
message配列は値を持たないため、取得した参照へ接続します。

Plug を作る・取得する操作そのもの(``Plug._resolve_input("pma1.input1D[10]")`` や
``Selection([...])`` など)は、存在しない要素の Plug でも要素を作りません。
``worldMatrix`` などのインスタンスごとのアトリビュートは、評価前でもインスタンス番号の要素
(作成直後のノードの ``worldMatrix[0]`` など)を ``getElement()``/``getElements()`` で取得できます。
インスタンス番号には、インスタンス化された祖先による間接インスタンスも含みます。
削除済みノード・削除済みの動的アトリビュートの配列 Plug の要素は取得できません(``RuntimeError``)。

``array_plug[0]`` は未作成番号でも要素参照だけを返します。
``getElement(0)`` は既存要素がなければ ``IndexError`` です。
参照の取得に作成フラグはありません。値設定・接続が要素を作成する操作です。
``getIndices()`` は既存要素の論理番号を昇順のlistで返します。
値の評価や要素の作成は行わず、ワールド空間アトリビュートはインスタンス番号も含みます。
要素のPlug一覧は ``getElements()``、評価値の辞書は ``get()`` で取得します。

.. code-block:: python

   node = mlib.createNode("network", name="arrayReferenceExample")
   values = node.addAttr("values", attributeType="double", multi=True)
   element = values[3]               # 参照の取得だけ。番号3は未作成
   print(values.getElements())          # []
   element.set(2.0)                  # 値を書くと実体化。通常モードはUndo対応
   print(values.getIndices())           # [3]
   print(values.getElement(3).get())     # 2.0（既存要素なので取得できる）

この ``[]`` があるため、
ArrayPlug オブジェクト自体を ``maya.cmds`` へ渡すとシーケンスとして展開されて失敗します。
配列アトリビュート全体を渡す場合は ``str(array_plug)`` か ``array_plug.getFullName()`` を渡してください。
要素の Plug と mlib のコマンド(``mlib.select`` など)は、そのまま渡せます。

アニメーションカーブそのものの操作は :doc:`animation_nodes` を参照してください。

このページのUndoの説明は通常モード（``fast=False``）を前提とします。
対応する値更新メソッドの ``fast=True`` はUndo対象外です。対応範囲と制限は :doc:`fast_edit` を参照してください。

参照から値と状態を取得する
----------------------------

アトリビュート参照は ``mlib.getPlug(target)`` または ``node.getPlug(name)`` で取得します。
参照取得や接続列挙は値を評価しません。値はPlugの ``get()`` で読みます。

.. list-table:: 参照と値を使い分ける
   :header-rows: 1

   * - 目的
     - 入口
     - 戻り値
   * - 値・接続を繰り返し操作する
     - ``node.getPlug("tx")`` / ``mlib.getPlug("node.tx")``
     - Plug参照
   * - 内部単位の値を読む
     - ``plug.get()``
     - 値（距離cm・角度rad・時間秒）
   * - UI単位の値を読む
     - ``plug.get(uiUnits=True)``
     - 現在のMaya単位による値
   * - 状態を照会する
     - ``plug.isLocked()`` / ``plug.isSettable()``
     - bool
   * - 特定時刻の値を照会する
     - ``cmds.getAttr(plug.getFullName(), time=10)``
     - Maya標準の値とUI単位

.. code-block:: python

   plug = mlib.getPlug("pCube1.tx")  # DoubleLinearPlug
   value = plug.get()              # 内部単位cm
   ui_value = plug.get(uiUnits=True)  # 現在の距離UI単位
   kind = plug.getDataType()        # Mayaの型名 "doubleLinear"

``Plug.get()`` / ``set()`` は角度rad・距離cm・時間秒で統一しています。
UI単位を変更しても ``set(get())`` は同じ値を維持します。
``get(uiUnits=True)`` / ``set(value, uiUnits=True)`` は現在のUI単位を使います。
単位は呼び出すPlugメソッドで選びます。

generic/kAnyアトリビュートは基底のPlug参照のままです。``get()`` の時点で
現在の値が行列ならMatrix、数値の組ならtupleを返します。choiceのselectorを
切り替えても参照を作り直す必要はありません。値の取得では上流の評価が起こる場合があります。
``mlib.getAttr`` のラッパーはありません。Maya固有の照会には ``maya.cmds.getAttr`` を使います。

アトリビュートの値とノードの姿勢
------------------------------------

``Plug.get()`` / ``set()`` は対象アトリビュートの値だけを扱い、空間指定 ``ws`` / ``worldSpace`` は受け付けません。
ワールド空間の値にはTransformの ``getTranslate(ws=True)`` / ``setRotate(..., ws=True)``
などを使います。

.. code-block:: python

   joint = mlib.getNode("joint1")
   rotation = joint.getPlug("rotate").get()
   joint.getPlug("rotate").set(rotation)  # チャンネル値をそのまま戻す
   joint.getPlug("rotate").set((10, 20, 30), unit="deg")
   joint.setRotate((0, 0, 0), ws=True) # jointOrient等を含む姿勢の操作

``rotate`` の値はラジアン・ノードのrotateOrderを持つ ``EulerRotate`` です。
設定時は数値3成分のrad/deg、またはEulerRotate/Quaternionを使えます。
型付き回転はノードのrotateOrderへ変換します。設定はjointOrientやrotateAxis、
他のチャンネルを変更しません。通常モードはUndo対応、``fast=True`` はUndoなしです。


入力接続だけの解除
------------------

``destination.disconnectInput()`` は直接の入力だけを解除し、自身を返します。
出力接続・子の独立接続・unitConversionノードは保持します。未接続なら何もしません。
親の複合接続を解除するときは親Plugへ呼び出します。通常のUndo/Redoに対応します。
``disconnectAll(*, src=True, dst=True)`` は既定で入出力両方を解除し、自身を返します。
``disconnectAll(src=True, dst=False)`` は入力、``disconnectAll(src=False, dst=True)`` は出力だけです。
``source/destination`` も使用できます。両Falseや未接続では何もせず、bool以外や別名との重複は
``TypeError`` になります。子・配列要素の独立接続と変換ノードは保持し、複数切断も1回のUndo/Redoで戻します。
forceフラグはありません。

``disconnect(sourcePlug)`` は指定入力だけを解除し、``disconnect()`` は現在の入力を
解除します。どちらも入力元Plugを返し、指定接続がない場合はエラーです。
``src``（別名 ``source``）は参照またはNoneだけを受け付けます。
方向のboolや ``dst/destination`` は使わず、``disconnectAll`` で方向を指定します。

配列の編集は番号・値・参照を検証してから書込みまたは接続します。
内部処理は要素を事前に実体化しません。``getElement(index)`` は既存要素の取得だけです。
論理番号はboolを除く整数で、範囲は0〜2147483647です。
型不正はTypeError、範囲外はIndexErrorになります。
