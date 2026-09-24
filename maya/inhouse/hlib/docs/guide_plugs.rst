アトリビュートとPlug
============================================================

アトリビュートの取得には ``node.plug()`` を使います。接続・メタ情報・配列要素の操作を説明します。

例は Maya の Script Editor で実行します。既存ノード名は使用するシーンに合わせてください。
最初に ``import hlib`` を実行してください。

接続の絞り込みと属性の列挙・エイリアス
----------------------------------------

.. code-block:: python

   source = hlib.createNode("transform", name="connSource")
   target = hlib.createNode("transform", name="connTarget")
   source.plug("translateX").connect(target.plug("translateX"))

   print(len(target.inputs()))                    # 1
   print(target.inputs(type="transform"))          # 同じ1件（接続元が transform）
   print(target.inputs(type="mesh"))               # []（一致なし）
   print(len(source.connections(type="transform")))  # 1

   plugs = target.plugs(keyable=True)              # cmds.listAttr(keyable=True) 相当
   print(any(plug.attribute == "translateX" for plug in plugs))   # True

   cmds.aliasAttr("myAlias", target.plug("translateY").full_name)
   for alias_name, plug in target.aliases():
       print(alias_name, plug.full_name)           # myAlias connTarget.myAlias

``inputs``/``outputs``/``connections`` の ``type`` 引数は接続先ノードの nodeType を
``is_type`` と同じ継承チェーンで絞り込みます（例: ``type="animCurve"``）。
``plugs`` は ``cmds.listAttr`` にキーワード引数をそのまま渡して属性を Plug として
列挙します。listAttr が報告する名前の一部（未確保の要素を持つ配列複合属性の子など、
``publishedNodeInfo`` のような組み込み属性でよく見られます）は実際には評価できず
黙ってスキップされるため、件数は listAttr の結果と必ずしも一致しません。
``aliases`` は ``cmds.aliasAttr`` のクエリ結果を ``(エイリアス名, Plug)`` の
タプル列として返します。エイリアスを設定すると Maya API の ``MPlug.name()``
自体がロング名ではなくエイリアス名で表示されるようになるため、
戻り値の ``Plug.full_name`` もロング名(``translateY``)ではなく
エイリアス名(``myAlias``)を含む表記になります。

属性のメタ情報
--------------

.. code-block:: python

   import maya.cmds as cmds

   node = hlib.createNode("transform", name="attrMetaExample")
   cmds.addAttr(node.name(), longName="strength", attributeType="double",
                min=0, max=10, defaultValue=5, hidden=True)
   cmds.addAttr(node.name(), longName="mode", attributeType="enum",
                enumName="Off:Low:High", defaultValue=1)

   plug = node.plug("strength")
   print(plug.is_dynamic)   # True（addAttr で追加したカスタム属性）
   print(plug.is_hidden)    # True
   print(plug.has_min, plug.min)   # True 0.0
   print(plug.has_max, plug.max)   # True 10.0
   print(plug.default)             # 5.0

   mode_plug = node.plug("mode")
   print(mode_plug.enum_name())    # "Low"（既定値 1 に対応する名前）

``min``/``max``/``default`` は数値属性では ``float`` をそのまま返しますが、
``rotateX`` のような角度・距離・時間属性では Maya API 2.0 の単位付きオブジェクト
（``MAngle``/``MDistance``/``MTime``）をそのまま返します。誤った単位換算を
避けるため、hlib 内部では変換を行いません。必要な単位は呼び出し側で
``.value`` や ``.asUnits(...)`` を使って変換してください。
``enum_name`` は enum 属性以外に使うと ``TypeError`` になります。
``is_readable``/``is_writable``/``is_storable`` で読み取り・書き込み・保存可否を、
``has_soft_min``/``soft_min``/``has_soft_max``/``soft_max`` で UI スライダーの
ソフトレンジ（値の入力自体は制限しない）を取得できます。
``enum_value(name)`` は ``enum_name()`` の逆引きで、フィールド名から enum 値を
取得します（一致しなければ ``ValueError``）。``nice_name()`` は Attribute Editor
などで使われる表示名を返します（``translateX`` → ``"Translate X"``）。

チャンネルボックス表示とプラグ接続の判定
------------------------------------------

.. code-block:: python

   node = hlib.createNode("transform", name="channelBoxExample")
   plug = node.plug("translateX")

   plug.set_keyable(False)          # キー不可（チャンネルボックスからも隠れる）
   plug.set_channel_box(True)       # キー不可のままチャンネルボックスにのみ表示

   other = hlib.createNode("transform", name="channelBoxOther")
   plug.connect(other.plug("translateX"))
   print(plug.is_connected_to(other.plug("translateX")))   # True
   print(other.plug("translateX").is_connected_to(plug))   # True（向き不問）

``set_keyable``/``set_channel_box`` は ``cmds.setAttr(keyable=...)``/
``cmds.setAttr(channelBox=...)`` のラッパーです。``is_connected_to`` は入力・出力
どちらの向きの接続でも一致すれば ``True`` を返します。

animCurve とミュート
---------------------

.. code-block:: python

   node = hlib.createNode("transform", name="animExample")
   plug = node.plug("translateX")
   print(plug.anim_curve())   # None（まだキーが無い）

   import maya.cmds as cmds
   cmds.setKeyframe(plug.full_name, time=1, value=0.0)
   cmds.setKeyframe(plug.full_name, time=24, value=10.0)
   print(plug.anim_curve())   # animExample_translateX（接続された animCurve ノード）

   print(plug.is_muted)   # False
   plug.mute()
   print(plug.is_muted)   # True
   plug.unmute()

``anim_curve`` は直接接続された animCurve ノードのみを解決します。
``pairBlend`` やアニメーションレイヤーを介した間接的な接続は対象外で、
その場合は接続の有無にかかわらず ``None`` を返します。
``mute``/``unmute`` は ``cmds.mute`` のラッパーで、現在の出力値のまま
アトリビュートの評価を一時的に固定・解除します。

配列プラグの要素追加・削除
----------------------------

.. code-block:: python

   node = hlib.createNode("transform", name="arrayPlugExample")
   array_plug = node.plug("worldMatrix")

   print(array_plug.next_available())   # 0（既存要素が無ければ）

   element = array_plug.add_element()   # 空きインデックスへ要素を作成
   print(element.full_name)             # arrayPlugExample.worldMatrix[0]

   array_plug.remove_element(0)         # 要素を削除

``next_available`` は ``getExistingArrayAttributeIndices()`` に含まれない
最初のインデックスを返す単純な実装です。cymel の同名メソッドと異なり、
ロック状態や子要素の再帰チェックは行いません。``add_element`` は
``next_available()`` の位置へ要素を作成して返し、``remove_element`` は
指定インデックスの要素を削除します（存在しなければ ``IndexError``）。

アニメーションカーブそのものの操作は :doc:`animation_nodes` を参照してください。
