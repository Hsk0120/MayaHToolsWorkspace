アトリビュートとPlug
============================================================

アトリビュートの取得には ``node.plug()`` を使います。接続・メタ情報・配列要素の操作を説明します。
``node.plug()`` はアトリビュート名(ロング名・ショート名・エイリアス)のほか、``input1D[3]``・
``worldMatrix[0]``・``pnts[2].pntx`` のような配列要素と子アトリビュートを含むアトリビュートパス
(``str(plug)`` の ``.`` 以降と同じ表記)も受け付けます。

例は Maya の Script Editor で実行します。既存ノード名は使用するシーンに合わせてください。
最初に ``import hlib`` を実行してください。

接続の絞り込みとアトリビュートの列挙・エイリアス
----------------------------------------------------

.. code-block:: python

   from maya.api.OpenMaya import MSpace
   import maya.cmds as cmds

   source = hlib.createNode("transform", name="connSource")
   target = hlib.createNode("transform", name="connTarget")
   source.plug("translateX").connect(target.plug("translateX"))

   print(len(target.inputs()))                    # 1
   print(target.inputs(type="transform"))          # 同じ1件（接続元が transform）
   print(target.inputs(type="mesh"))               # []（一致なし）
   print(len(source.connections(type="transform")))  # 1

   plugs = target.plugs(keyable=True)              # cmds.listAttr(keyable=True) 相当
   print(any(plug.attributeName() == "translateX" for plug in plugs))   # True

   cmds.aliasAttr("myAlias", target.plug("translateY").fullName())
   for alias_name, plug in target.aliases():
       print(alias_name, plug.fullName())           # myAlias connTarget.myAlias

``inputs``/``outputs``/``connections`` の ``type`` 引数は接続先ノードの nodeType を
``isType`` と同じ継承チェーンで絞り込みます（例: ``type="animCurve"``）。
``plugs`` は ``cmds.listAttr`` にキーワード引数をそのまま渡してアトリビュートを Plug として
列挙します。listAttr が報告する名前の一部（未確保の要素を持つ配列複合アトリビュートの子など、
``publishedNodeInfo`` のような組み込みアトリビュートでよく見られます）は実際には評価できず
黙ってスキップされるため、件数は listAttr の結果と必ずしも一致しません。
``aliases`` は ``cmds.aliasAttr`` のクエリ結果を ``(エイリアス名, Plug)`` の
タプル列として返します。``Plug.fullName()`` はアトリビュートにエイリアスがあればエイリアス名を
使う(``MPlug.name()`` と同じ表記)ため、戻り値の Plug の ``fullName()`` も
ロング名(``translateY``)ではなくエイリアス名(``myAlias``)を含む表記になります。
``cmds.listConnections(plugs=True)`` の表記はアトリビュートによって異なり、配列要素のエイリアス
(blendShape の ``weight[0]`` の ``smile`` など)はエイリアス名、配列でないアトリビュートの
エイリアス(``translateY`` の ``myAlias`` など)はロング名を返します。名前を文字列で
比較せず、Plug・MPlug 同士で比較してください(``plug.mplug() == other.mplug()``)。

プラグ名
--------

``str(plug)`` と ``plug.fullName()`` は、maya.cmds で一意に解決できる
``<ノードの最短一意名>.<アトリビュートパス>`` を返します。同じ短い名前のノードが複数あっても
``grp1|dup.translateX`` のようにパスを含むため、``cmds.getAttr(plug)`` のように
Plug を maya.cmds へそのまま渡せます。名前は呼び出すたびに求め直すため、
名前変更・親子付け替えにも追従します。所有ノードが削除済み、または動的アトリビュートが
``deleteAttr`` で削除済みなら空文字列です(``plug.isValid()`` が ``False``。
このとき ``get()``/``set()`` と、アトリビュートの情報・接続の問い合わせは ``RuntimeError`` になります)。
``plug.name()`` はノード名を含まない短いアトリビュート名(``tx`` など。無効な Plug では空文字列)を返します。

.. code-block:: python

   from maya.api.OpenMaya import MSpace
   import maya.cmds as cmds

   grp1 = hlib.createNode("transform", name="plugNameGrp1")
   grp2 = hlib.createNode("transform", name="plugNameGrp2")
   dup = hlib.createNode("transform", name="plugNameDup", parent=grp1)
   hlib.createNode("transform", name="plugNameDup", parent=grp2)

   plug = dup.plug("tx")
   print(plug)               # plugNameGrp1|plugNameDup.translateX
   print(plug.name())        # tx
   cmds.setAttr(plug, 2.0)   # 同名ノードがあっても一意に解決できる

受け付ける入力と ``maya.cmds`` へ渡せないオブジェクトは :doc:`cmds_interop` を参照してください。

アトリビュートのメタ情報
----------------------------

.. code-block:: python

   from maya.api.OpenMaya import MSpace
   import maya.cmds as cmds

   node = hlib.createNode("transform", name="attrMetaExample")
   cmds.addAttr(node.name(), longName="strength", attributeType="double",
                min=0, max=10, defaultValue=5, hidden=True)
   cmds.addAttr(node.name(), longName="mode", attributeType="enum",
                enumName="Off:Low:High", defaultValue=1)

   plug = node.plug("strength")
   print(plug.isDynamic())   # True（addAttr で追加したカスタムアトリビュート）
   print(plug.isHidden())    # True
   print(plug.hasMin(), plug.min())   # True 0.0
   print(plug.hasMax(), plug.max())   # True 10.0
   print(plug.default())             # 5.0

   mode_plug = node.plug("mode")
   print(mode_plug.enumName())    # "Low"（既定値 1 に対応する名前）

``min``/``max``/``default`` は数値アトリビュートでは ``float`` をそのまま返しますが、
``rotateX`` のような角度・距離・時間アトリビュートでは Maya API 2.0 の単位付きオブジェクト
（``MAngle``/``MDistance``/``MTime``）をそのまま返します。誤った単位換算を
避けるため、hlib 内部では変換を行いません。必要な単位は呼び出し側で
``.value`` や ``.asUnits(...)`` を使って変換してください。
``enumName`` は enum アトリビュート以外に使うと ``TypeError`` になります。
``isReadable``/``isWritable``/``isStorable`` で読み取り・書き込み・保存可否を、
``hasSoftMin``/``softMin``/``hasSoftMax``/``softMax`` で UI スライダーの
ソフトレンジ（値の入力自体は制限しない）を取得できます。
``enumValue(name)`` は ``enumName()`` の逆引きで、フィールド名から enum 値を
取得します（一致しなければ ``ValueError``）。``niceName()`` は Attribute Editor
などで使われる表示名を返します（``translateX`` → ``"Translate X"``）。

チャンネルボックス表示とプラグ接続の判定
------------------------------------------

.. code-block:: python

   from maya.api.OpenMaya import MSpace
   node = hlib.createNode("transform", name="channelBoxExample")
   plug = node.plug("translateX")

   plug.setFlags(keyable=False)          # キー不可（チャンネルボックスからも隠れる）
   plug.setFlags(channelBox=True)       # キー不可のままチャンネルボックスにのみ表示

   other = hlib.createNode("transform", name="channelBoxOther")
   plug.connect(other.plug("translateX"))
   print(plug.isConnectedTo(other.plug("translateX")))   # True
   print(other.plug("translateX").isConnectedTo(plug))   # True（向き不問）

``setFlags(locked=..., keyable=..., channelBox=...)`` はアトリビュートの状態をまとめて設定します。
省略したフラグは変更せず、bool以外の状態は更新前に拒否します。``isConnectedTo`` は入力・出力
どちらの向きの接続でも一致すれば ``True`` を返します。

animCurve とミュート
---------------------

.. code-block:: python

   from maya.api.OpenMaya import MSpace
   node = hlib.createNode("transform", name="animExample")
   plug = node.plug("translateX")
   print(plug.animCurve())   # None（まだキーが無い）

   import maya.cmds as cmds
   cmds.setKeyframe(plug.fullName(), time=1, value=0.0)
   cmds.setKeyframe(plug.fullName(), time=24, value=10.0)
   print(plug.animCurve())   # animExample_translateX（接続された animCurve ノード）

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

   from maya.api.OpenMaya import MSpace
   node = hlib.createNode("network", name="arrayPlugExample")
   node.addAttribute("values", attributeType="double", multi=True)
   array_plug = node.plug("values")

   print(array_plug.nextAvailableIndex())   # 0（既存要素が無ければ）

   element = array_plug.addElement()   # 空きインデックスへ要素を作成
   print(element.fullName())             # arrayPlugExample.values[0]

   element.set(1.0)                    # 要素に値を設定
   array_plug.removeElement(0)         # 要素を削除

``nextAvailableIndex`` は ``getExistingArrayAttributeIndices()`` に含まれない
最初のインデックスを返す単純な実装です。cymel の同名メソッドと異なり、
ロック状態や子要素の再帰チェックは行いません。``addElement`` は
``nextAvailableIndex()`` の位置へ要素を作成して返し、``removeElement`` は
指定インデックスの要素を削除します（存在しなければ ``IndexError``）。
``element(index, create=True)`` は要素が無ければ Maya 上に作成してから返します
(``cmds.getAttr`` の問い合わせで作成するため Undo の対象外です)。ただし ``message`` 型の
ように値を持たないアトリビュートの配列では要素を作成できません。返した要素 Plug へ接続した時点で
要素ができるため、``addElement()`` は接続するまで同じ番号の要素 Plug を返します。
Plug を作る・取得する操作そのもの(``Plug._resolve_input("pma1.input1D[10]")`` や
``Selection([...])`` など)は、存在しない要素の Plug でも要素を作りません。
``worldMatrix`` などのインスタンスごとのアトリビュートは、評価前でもインスタンス番号の要素
(作成直後のノードの ``worldMatrix[0]`` など)を ``element()``/``elements()`` で取得できます。
インスタンス番号には、インスタンス化された祖先による間接インスタンスも含みます。
削除済みノード・削除済みの動的アトリビュートの配列 Plug の要素は取得できません(``RuntimeError``)。

``array_plug[0]`` は ``element(0)`` と同じです。この ``[]`` があるため、
ArrayPlug オブジェクト自体を ``maya.cmds`` へ渡すとシーケンスとして展開されて失敗します。
配列アトリビュート全体を渡す場合は ``str(array_plug)`` か ``array_plug.fullName()`` を渡してください。
要素の Plug と hlib のコマンド(``hlib.select`` など)は、そのまま渡せます。

アニメーションカーブそのものの操作は :doc:`animation_nodes` を参照してください。

このページのUndoの説明は通常モード（``fast=False``）を前提とします。
対応する値更新メソッドの ``fast=True`` はUndo対象外です。対応範囲と制限は :doc:`fast_edit` を参照してください。

``Plug.get()`` / ``set()`` は角度rad・距離cm・時間秒で統一しています。
UI単位を変更しても ``set(get())`` は同じ値を維持します。
``hlib.getAttr()`` はコマンド層なので、Mayaコマンドと同じUI単位で返します。


アトリビュートの値とノードの姿勢
------------------------------------

``Plug.get()`` / ``set()`` は対象アトリビュートの値だけを扱い、空間指定 ``space`` は受け付けません。
ワールド空間の値にはTransformの ``getTranslation(space=MSpace.kWorld)`` / ``setRotation(..., space=MSpace.kWorld)``
などを使います。

.. code-block:: python

   from maya.api.OpenMaya import MSpace
   joint = hlib.getNode("joint1")
   rotation = joint.plug("rotate").get()
   joint.plug("rotate").set(rotation)  # チャンネル値をそのまま戻す
   joint.plug("rotate").set((10, 20, 30), unit="deg")
   joint.setRotation((0, 0, 0), space=MSpace.kWorld) # jointOrient等を含む姿勢の操作

``rotate`` の値はラジアン・ノードのrotateOrderを持つ ``EulerRotation`` です。
設定時は数値3成分のrad/deg、またはEulerRotation/Quaternionを使えます。
型付き回転はノードのrotateOrderへ変換します。設定はjointOrientやrotateAxis、
他のチャンネルを変更しません。通常モードはUndo対応、``fast=True`` はUndoなしです。
