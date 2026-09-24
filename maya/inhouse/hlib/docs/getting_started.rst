hlib入門
========

実行環境
--------

ワークスペースのバージョン別起動バッチから Maya を起動すると、
``maya/inhouse`` が Python の検索パスに追加されます。
以下は Maya の Script Editor の Python タブで実行する例です。
ノード作成例は現在のシーンにノードを追加します。

使用例では ``import hlib`` を基本とし、コマンドは ``hlib.createNode()`` や
``hlib.ls()`` のように hlib 直下から呼び出します。クラスを直接利用する場合は、
``hlib.nodes.Node`` など所属パッケージから取得します。

ノードと属性
------------

通常の編集はコマンド・メソッドの内部でUndoをまとめるため、外側を
``undo_chunk`` で囲む必要はありません。各呼び出しを個別の操作として扱います。

.. code-block:: python

   import hlib

   node = hlib.createNode("transform", name="hlibExample")
   node.plug("visibility").set(False)

   print(node.name())
   print(node.plug("visibility").get())
   print(hlib.ls(type="transform"))

この例では、属性変更とノード作成は別々のUndoになります。
複数の呼び出し全体を一回で戻すツールを開発する場合のみ、
:ref:`tool-undo-chunk` の方法でまとめます。

``createNode`` は ``maya.cmds.createNode`` にキーワード引数を渡し、
対応するラッパーを返します。既存ノードは ``hlib.node("ノード名")`` で取得できます。
``ls`` は ``maya.cmds.ls`` の引数を受け取り、通常はラッパーのリストを返します。
``type="joint"`` と ``type="skinCluster"`` は、それぞれ ``Joints`` と
``SkinClusters`` コレクションを返します。

シーン編集コマンド
------------------

.. code-block:: python

   import hlib

   a = hlib.createNode("transform", name="a")
   b = hlib.createNode("transform", name="b")

   print(hlib.objExists(a))          # True
   copy = hlib.duplicate(a, name="aCopy")
   parent = hlib.group([a, b], name="grp")
   empty = hlib.group(name="emptyGrp", empty=True)

   hlib.delete(copy)

``duplicate``/``group`` はいずれも作成したノードのラッパーを返します。
``group`` は ``nodes`` を省略すると ``maya.cmds.group`` と同じく現在の選択を
グループ化します。空のグループを作る場合は ``empty=True`` を指定してください
（選択も無く ``empty`` も指定しない場合は Maya がエラーを送出します）。
``delete`` は複数ノードもまとめて受け付けます。

選択とアニメーション
--------------------

.. code-block:: python

   import hlib

   a = hlib.createNode("transform", name="a")
   b = hlib.createNode("transform", name="b")

   hlib.select([a, b])
   print(hlib.ls(selection=True))
   hlib.select(clear=True)

   hlib.currentTime(1)
   hlib.setKeyframe(a.plug("translateX"), value=0.0)
   hlib.currentTime(24)
   hlib.setKeyframe(a.plug("translateX"), value=10.0)

   hlib.bakeResults(a, time=(1, 24), attribute=["translateX"], simulation=True)

``select`` は ``maya.cmds.select`` と同じ引数を受け付けます。``nodes`` を省略すると
``clear=True`` のような選択操作専用のフラグだけで呼び出せます。
``setKeyframe`` はノードまたは ``Plug`` を対象にでき、``target`` を省略すると
現在の選択が対象になります。``currentTime`` は引数を省略すると現在時間を照会します。
``bakeResults`` は ``time=(start, end)`` を省略すると Maya の現在の再生範囲が使われます。

アトリビュートの取得・設定・接続（``getAttr``/``setAttr``/``connectAttr``/``addAttr``）は
コマンドとしては用意していません。``node.plug("attrName")`` が返す ``Plug`` の
``get()``/``set()``/``connect()``、および ``node.add_attr()`` を使ってください。

ノードのアトリビュートは、:meth:`~hlib.nodes.node.Node.plug` で取得した
:class:`~hlib.plugs.plug.Plug` オブジェクトを通して操作します。
本ドキュメントの使用例は ``plug()`` に統一しています。
``attr()`` は既存コードとの互換性のために残している ``plug()`` の別名です。

クラスを直接importして使う
---------------------------

``hlib.createNode``/``hlib.ls``/``hlib.node`` などのコマンドは ``hlib`` 直下で
使える一方、``Node``/``Joint``/``Matrix`` のようなクラス自体は ``hlib`` 直下には
公開されません。所属するサブパッケージから import します。

.. code-block:: python

   import hlib
   from hlib.nodes import Node, Joint
   from hlib.maths import Matrix

   nodes = hlib.ls(sl=True)      # 選択中のノードをラッパーのリストで取得
   joint = Joint("joint1")       # 既存ノードを直接ラップ
   matrix = Matrix()             # 単位行列

``Joint("joint1")`` のように具象クラスを直接呼び出しても、内部は ``Node`` と
同じファクトリパターンで動作します。指定した名前の実際の Maya nodeType が
``joint`` と一致しない場合は、呼び出したクラスではなく実際の型に対応する
ラッパー(例: ``Transform``)が返ります。型を確定させたい場合は
``isinstance()`` で確認するか、素直に ``hlib.node("ノード名")`` /
``Node("ノード名")`` を使ってください。

形状情報
--------

Transform の ``shape()`` は実際のシェイプ型に応じて ``Mesh`` や
``NurbsCurve`` を返します。以下は既存ノード名を指定する例です。

.. code-block:: python

   mesh = hlib.node("pCube1").shape()
   print(mesh.num_vertices, mesh.num_edges, mesh.num_polygons)
   points = mesh.points(ws=True)
   normals = mesh.normals(ws=True, angle_weighted=True)

   curve = hlib.node("curve1").shape()
   print(curve.degree, curve.num_cvs, curve.num_spans)
   print(curve.length())  # オブジェクト空間の弧長
   cvs = curve.cv_positions(ws=True)

   print(curve.get_collocated_cv_groups())  # 重なった CV のグループ（無ければ []）

位置配列は Maya API 2.0 の ``MPointArray``、法線配列は ``MFloatVectorArray`` です。
距離は Maya API の内部単位を使い、``ws=False`` はオブジェクト空間です。
``normals`` の ``angle_weighted=True`` は隣接面の角度で重み付けした法線を返します。
``get_collocated_cv_groups`` はほぼ同じ位置にある CV（クリーンアップ前のカーブの
重複 CV など）を検出し、2個以上重なっているグループのみを CV 番号のリストとして
返します（単独の CV は含みません）。``tolerance`` で同一位置とみなす距離の
許容誤差を調整できます。

形状のミラー
------------

``Mesh`` と ``NurbsCurve`` は共通の ``mirror`` メソッドを持ちます。
頂点または CV を反転し、編集した自身を返します。

.. code-block:: python

   mesh.mirror(axis="x", ws=True)        # ワールドの X=0 平面で反転
   curve.mirror(axis="z", ws=False)      # オブジェクト空間の Z=0 平面で反転
   mesh.mirror(axis="xy", ws=True)       # ワールドの X、Y 座標を両方反転
   curve.mirror(axis="x", ws=True, pivot=(10, 0, 0))  # ワールドの X=10 を中心に反転
   mesh.mirror(axis="x", indices=[0, 1, 2])          # 指定した頂点だけ反転

``axis`` は x、y、z またはその組み合わせを指定します。大文字も使用できます。
``ws`` の既定値は ``False`` です。``pivot`` は指定した空間の座標で、
単位は Maya の現在の距離単位です。既定はその空間の原点で、
Transform のピボット位置は自動では使用しません。
``indices=None`` は全頂点／全 CV、空のリストは変更なしです。

親の移動・回転・スケールを変更せずに形状の座標を編集し、1回の Undo で戻せます。
ほぼゼロのスケールなど、数値的に不安定なワールド変換はエラーにします。
複製・結合や片側から反対側への対称化を行う機能ではありません。
メッシュの面の頂点順は維持するため、奇数軸での反転後は必要に応じて
法線を処理してください。インスタンスでは共有形状全体に影響します。

Transform のピボット
---------------------

.. code-block:: python

   transform = hlib.node("pCube1")
   print(transform.pivot())              # 既定は (0, 0, 0)
   transform.set_pivot((1.0, 2.0, 3.0))  # 回転・スケールピボットをまとめて設定
   print(transform.pivot(ws=True))       # ワールド空間での現在位置

``pivot``/``set_pivot`` は ``MFnTransform`` の回転・スケールピボットを扱います。
``set_pivot`` は常に回転・スケールピボットを同じ位置に揃えて設定するため、
片方だけを個別に動かすことはできません。値・戻り値は Maya API の内部距離単位です。

バウンディングボックス
-----------------------

.. code-block:: python

   mesh_transform = hlib.node("pCube1")
   print(mesh_transform.bounding_box())          # 自身の変換は含むが親の変換は含まない
   print(mesh_transform.bounding_box(ws=True))    # 親の変換も含めたワールド空間

``bounding_box`` は ``MFnDagNode.boundingBox`` をそのまま使うため、
``ws=False``（既定）でも自身の translate/rotate/scale は反映されます。
``cmds.xform(node, query=True, boundingBox=True)`` と同じ考え方で、
親から継承した変換だけを含まない座標系です。``ws=True`` で親のワールド行列も
適用した真のワールド空間の境界ボックスになります。戻り値は
``om2.MBoundingBox`` で、``.min``/``.max`` から座標を取得できます。

ノードの状態照会と階層クエリ
----------------------------

.. code-block:: python

   grandparent = hlib.createNode("transform", name="grandparent")
   parent = hlib.createNode("transform", name="parent")
   child = hlib.createNode("transform", name="child")
   parent.set_parent(grandparent)
   child.set_parent(parent)

   print(child.is_locked)                        # False
   print(child.is_referenced)                     # False（参照シーンなら True）
   print(child.is_type("transform"))               # True
   print(child.is_type("dagNode"))                 # True（継承チェーンも判定）
   print(grandparent.is_ancestor_of(child))         # True
   print(child.root() is grandparent or child.root().full_name == grandparent.full_name)

   plug = child.plug("translateX")
   print(plug.is_keyable)                          # True
   print(plug.parent.full_name)                    # child.translate

``is_type`` は ``cmds.nodeType(inherited=True)`` による継承チェーンで判定するため、
mesh シェイプは ``is_type("shape")`` でも True になります。``root()`` は DAG 階層の
最上位祖先を返し、自身がワールド直下ならそのまま自身を返します。
``Shape`` には同様に ``is_intermediate_object`` があります。

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

ノード型の分類とDAG階層クエリ
------------------------------

.. code-block:: python

   node = hlib.createNode("transform", name="classifyExample")
   print(node.type_id)                 # int（セッション内でのみ有効な内部ID）
   print(node.classification())        # ["drawdb/geometry/transform"]

   root = hlib.createNode("transform", name="root")
   branch = hlib.createNode("transform", name="branch")
   leaf = hlib.createNode("transform", name="leaf")
   branch.set_parent(root)
   leaf.set_parent(branch)

   print(root.child_transforms())   # [Transform('branch')]（Shape子は含まない）
   print(root.leaves())             # [Transform('leaf')]（子を持たない末端）
   print(branch.siblings())         # 親が同じ他の Transform（自身は含まない）

``type_id`` はプラグインの版数や環境によって値が変わりうるため永続化には
向きません。同一セッション内での高速な型比較にのみ使ってください。
``siblings()`` は親が無い（ワールド直下の）場合、他のワールド直下 Transform
（``persp`` / ``top`` などの既定カメラを含む）を対象にします。
``node.plugin_name`` はプラグイン由来のノード型でプラグイン名を返し、
Maya 組み込みのノード型では空文字列になります。

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

直接の親子関係と属性削除
------------------------

.. code-block:: python

   grandparent = hlib.createNode("transform", name="grandparent2")
   parent = hlib.createNode("transform", name="parent2")
   child = hlib.createNode("transform", name="child2")
   parent.set_parent(grandparent)
   child.set_parent(parent)

   print(grandparent.is_parent_of(parent))   # True（直接の親子のみ）
   print(grandparent.is_parent_of(child))    # False（孫は対象外）
   print(grandparent.is_ancestor_of(child))  # True（子孫はすべて対象）
   print(parent.is_child_of(grandparent))    # True
   print(child.attribute_count())            # int（全属性数）

   import maya.cmds as cmds
   cmds.addAttr(child.name(), longName="temp", attributeType="double")
   child.plug("temp").delete_attr()          # 動的属性を削除

   cmds.addAttr(child.name(), longName="lockedTemp", attributeType="double")
   locked_plug = child.plug("lockedTemp")
   locked_plug.set_locked(True)
   # locked_plug.delete_attr()             # ロック中は RuntimeError
   locked_plug.delete_attr(force=True)     # 一時的に解除してから削除

``is_parent_of``/``is_child_of`` は直接の親子関係のみを判定します。
祖先・子孫すべてを対象にする場合は ``is_ancestor_of`` を使ってください。
``delete_attr`` は addAttr で追加した動的属性にのみ使用でき、
``translateX`` のような静的属性を削除しようとすると Maya が拒否します。
ロックされている属性は既定では削除できず ``RuntimeError`` になりますが、
``force=True`` を指定すると一時的にロックを解除してから削除します。
接続がある属性は force に関わらず Maya が自動的に切断してから削除します。

表示・SRT解放・軸判定・オフセットグループ
------------------------------------------

.. code-block:: python

   transform = hlib.createNode("transform", name="rigControl")

   transform.hide()
   print(transform.plug("visibility").get())   # False
   transform.show()

   transform.set_translate((1.0, 2.0, 3.0))
   transform.make_identity(apply=True, translate=True)
   print(transform.get_translate())             # Translate(0.0, 0.0, 0.0)

   driver = hlib.createNode("transform", name="rigDriver")
   driver.plug("translateX").connect(transform.plug("translateX"))
   transform.plug("translate").set_locked(True)
   transform.release_srt()
   print(transform.plug("translate").is_locked)      # False
   print(transform.plug("translateX").source())       # None（接続も解除される）

   from hlib.maths import Vector
   print(transform.closest_axis_to_vector(Vector(0, -1, 0)))   # "-y"

   zero, offset = transform.create_offset_groups("rigControl_zero", "rigControl_offset")
   print(transform.parent_node().name())   # rigControl_offset
   print(offset.parent_node().name())      # rigControl_zero

``show``/``hide`` は ``visibility`` の単純なオン・オフです。``make_identity`` は
``cmds.makeIdentity`` のラッパーで、キーワード引数をそのまま渡します。
``release_srt`` は translate/rotate/scale/shear とその X/Y/Z 子をまとめて
アンロック・接続解除します。``closest_axis_to_vector`` は自身のワールド行列
（回転・スケールのみ、平行移動は無視）で各ローカル軸を変換し、指定した
ワールド方向ベクトルに最も近いものを ``"x"``/``"-y"`` のような文字列で返します
（``include_negative=False`` で負方向を除外可能）。``create_offset_groups`` は
自身の現在のワールド行列に一致するグループを外側から内側の順で作成し、
自身を最も内側のグループへ付け替えます（ワールド位置は変化しません）。
引数を省略すると ``"<自身の名前>_offset"`` という1個のグループになります。

コンストレイント
----------------

``add_constraint`` は呼び出し元を拘束し、引数のノードを拘束元にします。
次の例はシーンにノードとコンストレイントを追加します。

.. code-block:: python

   driver = hlib.createNode("transform", name="hlibDriver")
   driven = hlib.createNode("transform", name="hlibDriven")
   constraint = driven.add_constraint(driver, "parent", maintainOffset=True)
   print(constraint.targets())
   print(constraint.weight_aliases(), constraint.weights())
   constraint.weight_plugs()[0].set(0.5)

   constraint.set_weight(1.0)             # 全ターゲットに一括設定
   constraint.set_weight(0.2, driver)      # 特定ターゲットのみ（Node/str/複数指定可）

複数の拘束元はリストで指定できます。型名は ``"parent"`` と
``"parentConstraint"`` の両方に対応します。戻り値は ``ParentConstraint`` などの
具象ラッパーで、既存ノードを ``hlib.nodes.Node`` で取得しても同じ型に解決されます。
一度の呼び出しを1つの Undo チャンクとして扱います。

対応する型は parent、point、orient、scale、aim、poleVector、geometry、normal、
tangent、pointOnPoly です。PoleVector は RP IK ハンドル、Tangent は NURBS カーブ、
Geometry／Normal／PointOnPoly は各 Maya コマンドに適した形状を指定してください。
IK ハンドルは ``hlib.node(handle_name)`` から ``IkHandle`` として取得でき、
``handle.add_constraint(driver, "poleVector")`` を使用できます。
``set_weight`` はターゲットを省略すると全ターゲット、指定すると該当ターゲットのみ
ウェイトを設定します。``targets()`` に含まれないターゲットを指定すると ``ValueError``
になります。

追加のキーワード引数は対応する Maya コマンドへ渡します。
例えば ``maintainOffset`` は全種類に共通するフラグではありません。
PointOnPoly のターゲットUV等も Maya の仕様に従い、必要に応じてプラグから設定します。
同じ種類の拘束が既にある場合は、Maya の規則で既存拘束へターゲットが追加される場合があります。

joint チェーンと IK ハンドル
------------------------------

.. code-block:: python

   from hlib.nodes import Joint

   root = Joint(cmds.joint(position=(0, 0, 0)))
   mid = Joint(cmds.joint(position=(2, 0, 0)))
   tip = Joint(cmds.joint(position=(4, 0, 0)))

   print(root.chain_from_here())        # [root, mid, tip]（子が1つの間だけ辿る）
   print(root.chain_from_here(tip))     # 同上。tip まで明示的に辿る

   handle_name = cmds.ikHandle(startJoint=root.name(), endEffector=tip.name(),
                                solver="ikRPsolver")[0]
   handle = hlib.node(handle_name)

   print(root.ik_handles())             # [IkHandle(...)]（自身が start joint の場合のみ）
   print(mid.ik_handles())              # []（途中の joint は対象外）

   print(handle.get_end_joint())            # tip
   print(handle.get_joint_list())            # [root, mid]（末端 joint は含まない）
   print(handle.get_joint_list(include_tip=True))  # [root, mid, tip]

``chain_from_here`` は ``to`` を省略すると、子 joint がちょうど1つの間だけ辿り、
分岐（子が0または2つ以上）に達したところで止まります。``to`` を指定した場合は
そこまでの経路を辿り、``to`` が自身の子孫でなければ ``ValueError`` になります。
``ik_handles`` は自身が **start joint** である IK ハンドルのみを対象にします。
Maya は IK ハンドルの ``startJoint`` への接続からしか joint 側を解決できないため、
チェーン途中の joint では常に空リストになります。``IkHandle.get_joint_list`` は
``cmds.ikHandle(query=True, jointList=True)`` をラップしており、これは仕様上
末端 joint を含まないため、必要なら ``include_tip=True`` を指定してください。
``get_end_joint`` は ikEffector ノードの translate 接続元を辿って解決します。

cluster と locator
--------------------

.. code-block:: python

   import maya.cmds as cmds
   from hlib.nodes import Node

   mesh = hlib.node("pCube1")
   cluster_name, handle_name = cmds.cluster(mesh.full_name + ".vtx[0:2]")
   cluster = Node(cluster_name)

   print(cluster.weighted_node())   # cluster1Handle（ハンドル transform）
   print(cluster.geometry())        # [Mesh(...)]（変形対象の shape）

   loc_transform = cmds.spaceLocator(name="myLocator")[0]
   loc_shape_name = cmds.listRelatives(loc_transform, shapes=True)[0]
   locator = Node(loc_shape_name)

   print(locator.get_position())         # Translate(0.0, 0.0, 0.0)
   locator.set_position((1.0, 2.0, 3.0))

``cluster`` ノードは自動的に ``Cluster`` ラッパーへ解決されます。``weighted_node``
はクラスタのハンドル transform（デフォーマ本体とは別ノード）、``geometry`` は
変形対象の shape を返します。``locator`` シェイプは ``Locator`` ラッパーへ解決され、
``get_position``/``set_position`` は ``localPosition`` 属性を ``Translate`` として
扱います。

displayLayer の基本操作
--------------------------

.. code-block:: python

   import maya.cmds as cmds
   from hlib.nodes import Node

   a = hlib.createNode("transform", name="layerMemberA")
   layer = Node(cmds.createDisplayLayer(name="myLayer", empty=True))

   layer.add_members(a)
   print(layer.members())        # [Transform('layerMemberA')]

   layer.set_current()           # 以降の新規ノードの追加先レイヤーになる
   layer.remove_members(a)       # defaultLayer へ戻す（除外に相当）
   print(layer.members())        # []

``displayLayer`` ノードは自動的に ``DisplayLayer`` ラッパーへ解決されます。
Maya の displayLayer メンバーシップは常に単一のレイヤーに限られ、
``add_members`` は既に他のレイヤーに属するノードもこのレイヤーへ排他的に
移動します。``editDisplayLayerMembers`` に明示的な削除フラグは無いため、
``remove_members`` は ``defaultLayer`` へ戻すことで除外を実現しています。

objectSet の基本操作
----------------------

.. code-block:: python

   import maya.cmds as cmds
   from hlib.nodes import Node

   a = hlib.createNode("transform", name="setMemberA")
   b = hlib.createNode("transform", name="setMemberB")
   object_set = Node(cmds.sets(name="controlSet", empty=True))

   object_set.add(a, b)
   print(object_set.members())          # [Transform('setMemberA'), Transform('setMemberB')]
   print(object_set.is_member(a))       # True

   object_set.add(a.full_name + ".tx")  # コンポーネント/プラグ文字列も追加可能
   object_set.remove(b)
   print(object_set.members())          # [Transform('setMemberA'), 'setMemberA.translateX']

``objectSet`` ノードは自動的に ``ObjectSet`` ラッパーへ解決されます。``members()``
はコンポーネント文字列（例: ``"mesh1.vtx[0:2]"``）をそのまま文字列として返し、
それ以外はノードのラッパーとして返します。``add``/``remove`` は Node と文字列を
混在して受け取れます。和集合・積集合・差集合の演算は現時点では未対応です
（このバージョンの ``cmds.sets`` の union/intersection/subtract フラグの挙動が
安定して確認できなかったため、安全のため見送っています）。

blendShape のターゲット操作
------------------------------

.. code-block:: python

   from hlib.nodes import Node

   base = hlib.node("pCube1")
   target = hlib.node("pCube2")   # base と同じトポロジーの別メッシュ

   bs = Node(cmds.blendShape(target.full_name, base.full_name, name="myBlendShape")[0])
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
ターゲット名を含む表記になります（``attribute`` プロパティは常に ``"weight"``）。

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
（influence 名が異なる、mesh のトポロジーが変わった状態への読み込みは
このメソッドの対象外です）。

スキン変形を保ったままjointの姿勢を編集する
--------------------------------------------------

.. code-block:: python

   from hlib.decorators import preserved_skin_shape
   from hlib.nodes.joint import Joint

   joint = Joint("hlibExampleJoint")
   with preserved_skin_shape([joint]):
       # ここで jointOrient/rotate/rotateAxis や階層をどう変更しても、
       # ブロックを抜けた時点でメッシュの見た目は変わらない。
       joint.plug("jointOrientZ").set(45.0)

``preserved_skin_shape`` は Maya標準の ``skinCluster -moveJointsMode`` /
``-recacheBindMatrices`` を使い、ブロック内での joint 姿勢変更を
「新しいバインド姿勢」として扱います。関節の向きを付け直す、
リグを組み替えるといった作業で、既存のスキニングを壊したくない場合に使います。
ブロック全体(モード切り替え・編集・bind行列の再計算)は一回の Undo にまとまります。

頂点位置の編集(``hlib.components`` の ``Vertex``/``CV`` の ``set_position()``)は
``cmds.xform`` 経由でtweakノードを介して書き込むため、このデコレータなしでも
既にスキニングを崩しません。

シーン情報
----------

.. code-block:: python

   from hlib.files import Scene

   scene = Scene()
   print(scene.path())  # 未保存なら None
   print(scene.is_modified())

UI単位と内部単位への一時切り替え
----------------------------------

.. code-block:: python

   from hlib.units import Units, native_units

   print(Units.linear(), Units.angle(), Units.time())  # 例: "cm" "deg" "film"
   Units.set_linear("m")

   with native_units():
       # このブロック内は距離=cm、角度=radianとして扱える
       ...
   # ブロックを抜けると開始時点のUI単位(distanceは"m"のまま)へ復元される

``Units`` の取得・設定はいずれも ``cmds.currentUnit`` の文字列表現
(``"cm"``/``"m"``、``"deg"``/``"rad"``、``"film"``/``"ntsc"`` 等)を使います。
設定は Maya の Undo に対応します。``native_units()`` は行列・ベクトル計算など
シーンの表示単位に依存しない処理をしたい場合に使うコンテキストマネージャで、
``om2.MDistance``/``om2.MAngle`` の ``setUIUnit`` を直接呼ぶため MEL の往復が
無く、ブロックを抜ける際(例外時を含む)に開始時点の単位へ復元します
(時間単位には影響しません)。

プラグインのロード状態
------------------------

.. code-block:: python

   from hlib.plugins import Plugin, Plugins

   plugin = Plugin("matrixNodes")
   print(plugin.is_loaded(), plugin.path(), plugin.version())
   plugin.unload()
   plugin.ensure_loaded()   # 未ロードなら冪等にロードする

   for loaded in Plugins.loaded():
       print(loaded.name())

``is_loaded``/``is_registered`` は未知のプラグイン名でも例外にならず ``False``
を返します。``path``/``version`` も未登録なら ``None`` です。

ワークスペース(プロジェクト)
--------------------------------

.. code-block:: python

   from hlib.workspace import Workspace

   print(Workspace.root())               # 現在のワークスペースのルート
   print(Workspace.rule("scene"))        # 例: "scenes"
   print(Workspace.path_for("scene", "myScene.ma"))  # root/scenes/myScene.ma

``Workspace`` はインスタンスを持たず、常に現在のワークスペース(Mayaのセッションに
1つだけ存在するグローバルな状態)を対象にします。``expand`` はファイルルール名を
解決せず、文字通りルートへ相対パスを連結するだけの点に注意してください
(ルールが指すディレクトリを取得する場合は ``path_for`` を使います)。

参照(reference)の列挙と操作
-------------------------------

.. code-block:: python

   from hlib.files import list_references

   for reference in list_references():
       print(reference.filename(), reference.namespace(), reference.is_loaded())

   top_level = list_references(top_level_only=True)  # ネストした参照を除外

   reference = list_references()[0]
   reference.unload()
   reference.load()
   print(reference.nodes())  # 参照内のノードをラッパーで取得(アンロード中はRuntimeError)

参照ノード自体は ``hlib.nodes.Reference`` として自動解決されます
(``hlib.node("参照ノード名")`` でも取得可能)。``filename``/``namespace``/
``is_loaded``/``nodes``/``parent_reference`` は ``MFnReference`` 経由の
読み取り専用照会、``load``/``unload``/``remove`` は Undo 対応の編集操作です。

数学型
------

.. code-block:: python

   from hlib.maths import Vector

   result = Vector(1, 2, 3) + Vector(4, 5, 6)
   print(tuple(result))  # (5.0, 7.0, 9.0)

   x = Vector(1, 0, 0)
   y = Vector(0, 1, 0)
   x.dot(y)                  # 0.0
   tuple(x.cross(y))         # (0.0, 0.0, 1.0)
   Vector(3, 4, 0).length()  # 5.0
   tuple(Vector(0, 0, 5).normalized())  # (0.0, 0.0, 1.0)

``dot``/``cross``/``length``/``normalized`` は ``Translate``/``Rotate``/``Scale``/``Shear``
など ``Vector`` を継承する全ての型で使用できます。``cross``/``normalized`` の戻り値は
派生クラスの型を保持せず常に ``Vector`` になります(``__add__``/``__sub__`` と同様)。
``normalized()`` はゼロベクトルに対して ``ValueError`` を送出します。

.. code-block:: python

   a = Vector(1, 0, 0)
   b = Vector(0, 1, 0)

   -a                        # Vector(-1.0, -0.0, -0.0)
   Vector(2, 4, 6) / 2        # Vector(1.0, 2.0, 3.0)
   a.length_squared()        # 1.0（sqrt を省ける length() の2乗版）
   a.distance_to(b)          # 1.4142...（2点間のユークリッド距離）
   a.angle_to(b)             # 1.5707...（ラジアン。0〜piの範囲）
   a.is_equivalent(Vector(1 + 1e-12, 0, 0))  # True（許容誤差付き等価判定）
   a.lerp(b, 0.5)             # Vector(0.5, 0.5, 0.0)（線形補間。t<0/t>1は外挿）

``__eq__`` は dataclass が生成する完全一致（かつ同一クラス同士）の比較のため、
浮動小数点誤差を許容する場合は ``is_equivalent`` を使ってください。

.. code-block:: python

   from hlib.maths import Quaternion, EulerRotation

   rotation = EulerRotation.from_degrees(0, 90, 0)   # as_degrees() の逆
   q = rotation.to_quaternion()

   q.conjugate()              # XYZ の符号を反転
   q.inverse()                # 逆四元数（単位四元数なら conjugate と同じ）
   q.dot(q)                   # 1.0（正規化済みなら常に1）
   q.length()                 # 1.0
   q.rotate_vector(Vector(1, 0, 0))    # このQuaternionでベクトルを回転
   q.angle_to(Quaternion())            # 単位四元数との角度差（ラジアン）

   identity = Quaternion()
   halfway = identity.slerp(q, 0.5)    # 球面線形補間（最短経路で補間）

   axis, angle = q.to_axis_angle()     # (Vector, float) へ分解
   Quaternion.from_axis_angle(axis, angle)  # 軸・角度から逆生成

``rotate_vector``/``slerp``/``angle_to``/``inverse`` はいずれも呼び出し前に自身を
正規化するため、正規化していない四元数を渡してもスケールの影響は受けません。

.. code-block:: python

   from hlib.maths import Matrix

   Matrix.identity()          # Matrix() と同じ単位行列
   m = Matrix(translate=(1, 2, 3), scale=(2, 3, 4))
   m.determinant()            # 24.0（スケールの体積比。平行移動は影響しない）
   m.is_equivalent(m)         # True（許容誤差付き等価判定。__eq__ は完全一致のみ）
   m @ Matrix(scale=(2, 2, 2))  # __mul__ と同じ（numpy に倣った @ 演算子）

``maths`` の実装は Maya に依存しません。ただし通常の
``from hlib.maths import ...`` は親パッケージ ``hlib`` の初期化を通るため、
この import には Maya 環境が必要です。

再読み込み
----------

.. code-block:: python

   import hlib
   hlib.reload()

再読み込みは hlib 内の依存関係をもとに行われます。
古いクラスのインスタンスや ``from ... import ...`` で取得済みの参照は
自動では置き換わらないため、必要な参照・ラッパーを取得し直してください。


コンポーネントと座標
--------------------

Vertex / CV はシーンを参照する単体ラッパーです。``x`` / ``y`` / ``z`` は
オブジェクト空間の座標で、Maya の現在の距離単位を使用します。
値を代入するとシーンを更新し、Undo できます。座標のスナップショットが
必要な場合は ``position()`` が返すタプルを保持してください。

.. code-block:: python

    mesh = hlib.nodes.Mesh("pCubeShape1")
    vertex = mesh.vertex(0)
    print(vertex.x, vertex.y, vertex.z)
    vertex.x = 2.0
    vertex.set_position((1, 2, 3), ws=True)
    print(vertex.position(ws=True))

    curve = hlib.nodes.NurbsCurve("curveShape1")
    cv = curve.cv(0)
    cv.z = -cv.z
    curve.cvs().mirror(axis="z", ws=False)
    mesh.vertices([0, 1, 2]).mirror(axis="x", ws=True)

    edge = mesh.edge(0)       # Edge
    face = mesh.face(0)       # Face
    mesh.edges([0, 1]).vertices().mirror(axis="x")
    vertices = mesh.faces([0, 1]).vertices()
    uv = mesh.uv(0)           # UV
    uv.u = 0.25
    uv.v = 0.75
    print(mesh.uvs().positions())

単体型は Vertex、CV、Edge、Face、UV、複数形は Vertices、CVs、Edges、Faces、UVs です。
複数形は反復、添字、スライスに対応します。番号は作成時に固定し、座標は現在の値を
取得します。トポロジー変更後の要素の同一性は保証しません。
UV は現在の UV セットを参照し、セットを切り替えると切替先を参照します。
既存の ``mesh.mirror()`` / ``curve.mirror()`` も複数形へ委譲して使用できます。


シーンオブジェクトの取得
------------------------

.. code-block:: python

    import hlib

    current = hlib.scene()
    print(current)  # 現在のパス。未保存の場合は untitled
    other = hlib.scene("C:/project/scenes/character.ma")
    print(other)    # パスを表示するだけで、ファイルは開かない
    # other.open() # 明示的に開く場合

Scene は取得時のパスを保持します。現在のシーンの切替・名前変更に自動追従しません。
``new()``、``open()``、``save_as()`` を自身で実行した場合は保持パスも更新します。
``save()``、``save_as()``、``is_modified()`` は現在のシーンとパスが一致する場合のみ
使用できます。未保存シーン同士はパスで区別できません。
クラスの定義先は ``hlib.files.Scene``、名前空間クラスは ``hlib.namespaces.Namespace`` です。

旧 ``hlib.scenes`` / ``hlib.session`` は廃止しました。直接importする場合は次の分類を使います。
``hlib.scene()`` など、コマンドから取得する入口は従来どおりです。

.. code-block:: python

    from hlib.files import Scene, list_references
    from hlib.namespaces import Namespace
    from hlib.plugins import Plugin, Plugins
    from hlib.units import Units, native_units
    from hlib.workspace import Workspace
    from hlib.editors import TimeSlider, Viewport, Outliner

タイムスライダー・ビューポート・アウトライナー
----------------------------------------------

.. code-block:: python

    import hlib
    hlib.reload()

    slider = hlib.timeSlider()  # hlib.editors.TimeSlider
    print(slider.current_time(), slider.playback_range())
    slider.set_playback_range(1, 120)
    with slider.preserve_time():
        slider.set_current_time(24)
    print(slider.selected_range())  # 未選択はNone。選択範囲の終端は含まない

    view = hlib.viewport()  # hlib.editors.Viewport
    print(view.panel(), view.camera())
    with view.temporary_settings(grid=False, joints=False):
        pass  # 終了時に指定した表示設定を復元
    with view.suspend():
        pass  # 重い処理。例外時もメインペインの表示状態を復元

    outliner = hlib.outliner()  # hlib.editors.Outliner
    outliner.set_settings(showShapes=True, showNamespace=True)
    outliner.expand_all()       # 展開
    outliner.expand_all(False)  # 折りたたむ

``Viewport.suspend()`` はmGearの ``viewport_off`` と同様に、メインペインの
``manage`` を一時的に無効化します。計算・再生を停止する機能ではありません。
メインペイン内のアウトライナー等も対象となり、切り離したウィンドウは対象外です。
元から非表示の場合は非表示へ戻り、ネストと例外にも対応します。
手動切替には ``Viewport.set_enabled(False/True)``、照会には ``is_enabled()`` を使います。

表示設定はMayaの長いフラグ名で指定します。``settings()`` は対応する表示設定のみを
返し、UI全体やカメラ・階層展開状態は保存しません。
対象を明示する場合は ``hlib.viewport("modelPanel4")``、
``hlib.outliner("outlinerPanel1")`` のように指定します。UIの自動作成は行いません。
ビューポート・アウトライナー・スライダー選択範囲にはMaya GUIが必要です。
時刻・再生範囲の操作はバッチでも利用できます。

参照: `modelEditor <https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Tech-Docs/CommandsPython/modelEditor.html>`_、
`outlinerEditor <https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Tech-Docs/CommandsPython/outlinerEditor.html>`_、
`timeControl <https://help.autodesk.com/cloudhelp/2024/ENU/Maya-Tech-Docs/CommandsPython/timeControl.html>`_。
