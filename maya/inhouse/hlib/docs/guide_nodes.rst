ノードとTransform
============================================================

ノードの状態・階層・ピボット・表示と変換を扱います。

例は Maya の Script Editor で実行します。既存ノード名は使用するシーンに合わせてください。
最初に ``import hlib`` を実行してください。

Transform のピボット
---------------------

.. code-block:: python

   transform = hlib.getNode("pCube1")
   print(transform.pivot())              # 既定は (0, 0, 0)
   transform.set_pivot((1.0, 2.0, 3.0))  # 回転・スケールピボットをまとめて設定
   print(transform.pivot(ws=True))       # ワールド空間での現在位置

``pivot`` は ``MFnTransform`` で回転ピボットを読み取り、
``set_pivot`` は ``cmds.xform`` で回転・スケールピボットを更新します。
``set_pivot`` は常に回転・スケールピボットを同じ位置に揃えて設定するため、
片方だけを個別に動かすことはできません。値・戻り値は Maya API の内部距離単位です。

バウンディングボックス
-----------------------

.. code-block:: python

   mesh_transform = hlib.getNode("pCube1")
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

   print(child.is_locked())                        # False
   print(child.is_referenced())                     # False（参照シーンなら True）
   print(child.is_type("transform"))               # True
   print(child.is_type("dagNode"))                 # True（継承チェーンも判定）
   print(grandparent.is_ancestor_of(child))         # True
   print(child.root() is grandparent or child.root().full_name() == grandparent.full_name())

   plug = child.plug("translateX")
   print(plug.is_keyable())                          # True
   print(plug.parent().full_name())                    # child.translate

``is_type`` は ``cmds.nodeType(inherited=True)`` による継承チェーンで判定するため、
mesh シェイプは ``is_type("shape")`` でも True になります。``root()`` は DAG 階層の
最上位祖先を返し、自身がワールド直下ならそのまま自身を返します。
``Shape`` には同様に ``is_intermediate_object`` があります。

ノードの名前と取得
------------------

``str(node)`` と ``node.name()`` は maya.cmds で一意に解決できる最短名、
``node.full_name()`` は完全な DAG パスを返します。どちらも呼び出すたびに求め直すため、
名前変更・親子付け替えの後も同じ Node を ``cmds.select(node)`` のように
maya.cmds へそのまま渡せます。削除済みのノードは空文字列です。

``hlib.getNode(value)`` (``Node(value)`` と同じ)は、名前・MObject・MDagPath のほか、
既存の Node、Plug・MPlug(所有ノード)、Vertex・Vertices などのコンポーネント
(所有シェイプ)も受け付け、実際のノード型に対応するラッパーを返します。
``"dup.tx"`` のように同じ短い名前のノードがあって複数の対象に一致する名前は、
最初の一致を返さず ``RuntimeError`` になります(``"bulk*"`` のように複数のノードに一致する
パターンも同じです。パターンは ``hlib.ls`` を使ってください)。``deleteAttr`` で属性が
削除された Plug・MPlug は、所有ノードが残っていても ``ValueError`` です
(``RuntimeError`` としても捕捉できます)。インスタンス化されたノードは
指定したインスタンスのパスを保持し、そのインスタンスだけが削除された場合は
残っている最初のインスタンスのパスへ切り替わります。

.. code-block:: python

   joint = hlib.createNode("joint", name="nameExampleJoint")
   print(hlib.getNode(joint.plug("tx")))        # nameExampleJoint（Joint）
   print(hlib.getNode(joint.name() + ".tx"))    # 属性名の文字列も所有ノードになる
   copy = hlib.getNode(joint)                   # 同じノードを指す新しいラッパー

詳しくは :doc:`cmds_interop` を参照してください。

ノード型の分類とDAG階層クエリ
------------------------------

.. code-block:: python

   node = hlib.createNode("transform", name="classifyExample")
   print(node.type_id())                 # int（セッション内でのみ有効な内部ID）
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
``node.plugin_name()`` はプラグイン由来のノード型でプラグイン名を返し、
Maya 組み込みのノード型では空文字列になります。

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
   locked_plug.set_flags(locked=True)
   # locked_plug.delete_attr()             # ロック中は RuntimeError
   locked_plug.delete_attr(force=True)     # 一時的に解除してから削除

``is_parent_of``/``is_child_of`` は直接の親子関係のみを判定します。
祖先・子孫すべてを対象にする場合は ``is_ancestor_of`` を使ってください。
``delete_attr`` は addAttr で追加した動的属性にのみ使用でき、
``translateX`` のような静的属性を削除しようとすると Maya が拒否します。
ロックされている属性は既定では削除できず ``RuntimeError`` になりますが、
``force=True`` を指定すると一時的にロックを解除してから削除します。
接続がある属性は force に関わらず Maya が自動的に切断してから削除します。
削除した属性の Plug は無効になり(``plug.is_valid()`` が ``False``、``str(plug)`` は空文字列)、
``get()``/``set()`` は ``RuntimeError`` です。同じ名前で追加し直した属性は ``node.plug()`` で
取得し直してください。

表示・SRT解放・軸判定・オフセットグループ
------------------------------------------

.. code-block:: python

   transform = hlib.createNode("transform", name="rigControl")

   transform.set_visible(False)
   print(transform.plug("visibility").get())   # False
   transform.set_visible(True)

   transform.set_translate((1.0, 2.0, 3.0))
   transform.make_identity(apply=True, translate=True)
   print(transform.get_translate())             # Translation(0.0, 0.0, 0.0)

   driver = hlib.createNode("transform", name="rigDriver")
   driver.plug("translateX").connect(transform.plug("translateX"))
   transform.plug("translate").set_flags(locked=True)
   transform.unlock_and_disconnect_transform_channels()
   print(transform.plug("translate").is_locked())      # False
   print(transform.plug("translateX").source())       # None（接続も解除される）

   from hlib.maths import Vector
   print(transform.closest_axis_to_vector(Vector(0, -1, 0)))   # "-y"

   zero, offset = transform.create_offset_groups("rigControl_zero", "rigControl_offset")
   print(transform.parent_node().name())   # rigControl_offset
   print(offset.parent_node().name())      # rigControl_zero

``show``/``hide`` は ``visibility`` の単純なオン・オフです。``make_identity`` は
``cmds.makeIdentity`` のラッパーで、キーワード引数をそのまま渡します。
``unlock_and_disconnect_transform_channels`` は translate/rotate/scale/shear とその X/Y/Z 子をまとめて
アンロック・接続解除します。``closest_axis_to_vector`` は自身のワールド行列
（回転・スケールのみ、平行移動は無視）で各ローカル軸を変換し、指定した
ワールド方向ベクトルに最も近いものを ``"x"``/``"-y"`` のような文字列で返します
（``include_negative=False`` で負方向を除外可能）。``create_offset_groups`` は
自身の現在のワールド行列に一致するグループを外側から内側の順で作成し、
自身を最も内側のグループへ付け替えます（ワールド位置は変化しません）。
引数を省略すると ``"<自身の名前>_offset"`` という1個のグループになります。

コンストレイントを削除する
--------------------------

``Transform.delete_constraints()`` は自身を拘束しているコンストレイントと、
その入力経路にあるpairBlendを削除します。Jointでも使用できます。

.. code-block:: python

   import hlib

   driven = hlib.getNode("rigControl")
   deleted_names = driven.delete_constraints()
   print(deleted_names)  # 削除前のノード名。該当がなければ []

入力接続をpairBlend・unitConversionに限って上流へ辿ります。
拘束元ノード、アニメーションカーブ、コンストレイントに繋がらないpairBlendは残します。
unitConversion自体は削除対象に含めません。
削除ノードの出力が他のノードにも使われている場合や、削除対象が参照・ロックされている場合は
変更前にエラーにします。全体は一回のUndoで戻せます。

現在姿勢の維持やベイク、pairBlendに接続されていたアニメーションの再接続は行いません。
削除後に姿勢が変わる場合があります。

複数ノードへの操作は :doc:`bulk_collections`、行列の計算は :doc:`matrices` を参照してください。

このページのUndoの説明は通常モード（``fast=False``）を前提とします。
対応する値更新メソッドの ``fast=True`` はUndo対象外です。対応範囲と制限は :doc:`fast_edit` を参照してください。

ノードの削除
------------

``node.delete()`` はそのノードクラスの削除処理を実行します。
基底NodeはMaya標準の規則でDAGの子階層も削除します。
``hlib.delete(nodes)`` は各入力を具象ノードへ解決し、入力順に ``node.delete()`` を
呼び出します。先行処理で削除済みとなった対象や重複はスキップします。
全体を1回のUndoで戻せます。

``Joint.delete()`` はウェイト移送・子階層保持を伴う専用操作です。
``hlib.delete(joint_name)`` でもこの専用操作が呼ばれます。
独自ノードクラスも ``delete()`` の上書きで削除挙動を変更できます。
