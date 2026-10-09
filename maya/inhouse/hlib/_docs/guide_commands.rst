コマンドによるシーン編集
============================================================

選択・複製・グループ化・キー設定など、hlib直下のコマンドを使います。
引数の短縮表記は :doc:`flag_aliases` を参照してください。

例は Maya の Script Editor で実行します。既存ノード名は使用するシーンに合わせてください。
最初に ``import hlib`` を実行してください。

getを省略した取得関数
----------------------------

``hlib.cmds`` からもget省略の取得関数を使えます。対象は次の13関数です。

``attr``、``channelBox``、``drivenKey``、``node``、``outliner``、``plug``、``scene``、
``shelf``、``timeSlider``、``viewport``、``window``、``workspaceControl``、``workspaceLayout``。

ルートの同名関数は同じ関数オブジェクトの再公開です。
例えば ``hlib.cmds.node is hlib.node`` はTrueになります。
各省略関数はget付きの処理本体へ委譲し、引数・既定値・フラグ・戻り値を保持します。
対応する正式名の一覧は :doc:`getter_aliases` を参照してください。

.. code-block:: python

   import hlib

   created = hlib.cmds.createNode("transform", name="commandLookupExample")
   node = hlib.cmds.node(created)
   plug = hlib.cmds.plug(node.fullName() + ".translateX")
   attr = hlib.cmds.attr(plug)
   value = attr.get()             # フラグなしはPlugから内部単位cmで取得
   scene = hlib.cmds.scene()      # 取得時のシーンパスを保持
   print(scene.path)

   assert hlib.cmds.node is hlib.node
   assert attr is plug

``attr()`` に照会フラグを明示した場合は、従来のMaya照会値・状態を返します。
``scene()`` はSceneオブジェクトの取得だけを行い、シーンの読み込みや保存は行いません。

シーン編集コマンド
------------------

.. code-block:: python

   import hlib
   from maya import cmds

   a = hlib.createNode("transform", name="a")
   b = hlib.createNode("transform", name="b")

   print(cmds.objExists(a))          # True
   copy = hlib.duplicate(a, name="aCopy")
   parent = hlib.createGroup([a, b], name="grp")
   empty = hlib.createGroup(name="emptyGrp", empty=True)

   hlib.delete(copy)

対象の引数には名前の文字列のほか、Node・Plug・Vertex などのコンポーネント、
Vertices などのコレクション、Selection、Maya API 2.0 の MObject・MDagPath・MPlug と
それらのリストを指定できます。変換の規則と、hlib のオブジェクトを ``maya.cmds`` へ
そのまま渡す場合の仕様は :doc:`cmds_interop` を参照してください。

``duplicate``/``createGroup`` はいずれも作成したノードのラッパーを返します。
``createNode``/``createGroup`` の ``parent`` は所有ノードへ解決します(Plug を渡すとその
ノードが親になります)。``createGroup`` に空のリストを渡すと、現在の選択をグループ化せずに
``ValueError`` になります。
``createGroup`` は ``nodes`` を省略すると ``maya.cmds.group`` と同じく現在の選択を
グループ化します。空のグループを作る場合は ``empty=True`` を指定してください
（選択も無く ``empty`` も指定しない場合は Maya がエラーを送出します）。
``delete`` は複数ノードもまとめて受け付けます。Plug(アトリビュート)を渡すと ``TypeError`` です
(``maya.cmds.delete`` はアトリビュートを削除せず何もしないため)。動的アトリビュートの削除は
``plug.delete()``、所有ノードの削除は ``hlib.delete(plug.node())`` を使ってください。

作成結果から次の操作を選ぶ
--------------------------

.. list-table::
   :header-rows: 1

   * - 作成
     - 戻り値
     - 頂点・CVへ進む入口
   * - ``createPolygon(...)``
     - Mesh
     - ``mesh.vertices()``
   * - ``createCurve(...)``
     - Transform
     - ``curve_transform.shape().cvs()``
   * - ``createNurbs(type="circle", ...)``
     - NurbsCurve
     - ``circle.cvs()``
   * - ``createNurbs(type="square", ...)``
     - list[NurbsCurve]
     - 各シェイプの ``cvs()``
   * - ``createNurbs(type="cube", ...)``
     - list[NurbsSurface]
     - 各シェイプの ``scaleGeometry(...)`` 等

作成した型からの連続例と単数・複数コンポーネントは :doc:`guide_geometry`、
値を作成フラグへ渡す際のUI単位との境界は :doc:`cmds_interop` を参照してください。

選択を取得して分類する
----------------------

.. code-block:: python

   selected_vertices = hlib.ls(sl=True, type="vertex")  # list[Vertex]
   captured = hlib.captureSelection()
   vertex_groups = captured.filter("vertex").components()  # list[Vertices]
   for vertices in vertex_groups:
       print(vertices.shape, vertices.indices)

``ls`` はMayaの検索結果の順に参照を返します。単一のノード型
``type="joint"`` / ``type="skinCluster"`` はJoints / SkinClusters、
その他のノード型やコンポーネント型はリストです。
``type=["joint"]`` のようなMayaの複数型指定はリストを返します。
コンポーネントの型指定は ``vertex`` / ``edge`` / ``face`` / ``uv`` / ``controlVertex`` です。
選択済みの該当要素を絞る処理で、メッシュ選択から全頂点への変換は行いません。
全頂点を取得するときは対象Meshの ``vertices()`` を使います。

``captureSelection()`` は取得時点の参照を保持し、現在の選択へ自動追従しません。
``filter("vertex").components()`` で複数シェイプを分けて一括編集する例は
:doc:`guide_geometry`、選び直しは :doc:`selection_and_channelbox` を参照してください。

選択とアニメーション
--------------------

.. code-block:: python

   import hlib
   from maya import cmds

   a = hlib.createNode("transform", name="animationA")
   b = hlib.createNode("transform", name="animationB")

   hlib.select([a, b])
   print(hlib.ls(selection=True))
   hlib.select(clear=True)

   cmds.currentTime(1)
   cmds.setKeyframe(a.plug("translateX"), value=0.0)
   cmds.currentTime(24)
   cmds.setKeyframe(a.plug("translateX"), value=10.0)

   hlib.bakeResults(a, time=(1, 24), attribute=["translateX"], simulation=True)

``select`` は ``maya.cmds.select`` と同じ引数を受け付けます。``nodes`` を省略すると
``clear=True`` のような選択操作専用のフラグだけで呼び出せます。
時刻やキー操作は ``maya.cmds`` を使用します。現在時刻の照会は
``cmds.currentTime(query=True)`` と明示します。
``bakeResults`` は時間範囲を補いません。``time=(start, end)`` を明示してください。
``simulation`` の既定値はFalseです。シーン全体の評価が必要ならTrueを指定します。
GUIではベイク中のメインペインを非表示にし、終了時に元の状態へ戻します。

``hlib.attr("node.attr")`` は型付きPlugを返します。照会フラグを明示すると
従来のMaya照会値・状態を返します。``node.plug("attrName")`` からもPlugを取得できます。
取得した ``Plug`` の ``get()``/``getu()``/``set()``/``connectTo()``、
および ``node.addAttr()`` で値・接続・追加アトリビュートを操作します。
``Plug`` は ``maya.cmds.getAttr(plug)`` のように maya.cmds へそのまま渡すこともできます
（:doc:`cmds_interop`）。

ノードのアトリビュートは、:meth:`~hlib.nodes.node.Node.plug` で取得した
:class:`~hlib.plugs.plug.Plug` オブジェクトを通して操作します。
ノードからは ``plug()``、アトリビュート名からは ``hlib.attr()`` または
``hlib.plug()`` を使えます。

コマンドの命名と役割
--------------------

正式コマンドのファイル名と関数名は動詞+対象です。``ls`` は一覧取得の慣用名として維持します。
作成コマンドの旧名は残しません。取得コマンドにはget省略入口もあります。
省略入口も、省略名と同名のファイル・関数で公開しています。
正式名と省略名は同じ引数・戻り値です（:doc:`getter_aliases`）。

.. list-table::
   :header-rows: 1

   * - 旧名
     - 現在の名前
   * - ``constraint``
     - ``addConstraint``
   * - ``curve``
     - ``createCurve``
   * - ``ikHandle``
     - ``createIkHandle``
   * - ``sets``
     - ``createSet``
   * - ``group``
     - ``createGroup``

``create`` / ``add`` は生成・追加専用です。拘束の照会は
``constraint.targets()`` / ``constraint.weightPlugs()``、編集は
``constraint.setWeight()`` を使います。セットは
``object_set.members()`` / ``add()`` / ``remove()`` を使います。
``drivenKey`` は関係取得のみで、キーの生成は ``setKey()`` です。
