コマンドによるシーン編集
============================================================

選択・複製・グループ化・キー設定など、mlib直下のコマンドを使います。
引数の短縮表記は :doc:`flag_aliases` を参照してください。

例は Maya の Script Editor で実行します。既存ノード名は使用するシーンに合わせてください。
最初に ``import mlib`` を実行してください。

get付きの取得関数
----------------------------

``mlib.cmds`` とルートの ``mlib`` から同じ正式get関数を使えます。
対象は ``getChannelBox/getDrivenKey/getNode/getOutliner/getPlug/getScene/``
``getShelf/getTimeSlider/getViewport/getWindow/getWorkspaceControl/getWorkspaceLayout`` です。
例えば ``mlib.cmds.getNode is mlib.getNode`` はTrueになります。
省略入口は廃止しました（:doc:`getter_aliases`）。

.. code-block:: python

   import mlib

   created = mlib.cmds.createNode("transform", name="commandLookupExample")
   node = mlib.cmds.getNode(created)
   plug = mlib.cmds.getPlug(node.getFullName() + ".translateX")
   value = plug.get()             # Plugから内部単位cmで取得
   scene = mlib.cmds.getScene()      # 取得時のシーンパスを保持
   print(scene.path)

   assert mlib.cmds.getNode is mlib.getNode

アトリビュート参照は ``getPlug()``、値は ``Plug.get()``、状態は専用メソッドで取得します。
特定時刻の値などMaya固有の照会は ``maya.cmds.getAttr`` を使います。
``getScene()`` はSceneオブジェクトの取得だけを行い、シーンの読み込みや保存は行いません。

シーン編集コマンド
------------------

.. code-block:: python

   import mlib
   from maya import cmds

   a = mlib.createNode("transform", name="a")
   b = mlib.createNode("transform", name="b")

   print(cmds.objExists(a))          # True
   copy = mlib.duplicate(a, name="aCopy")
   parent = mlib.createGroup([a, b], name="grp")
   empty = mlib.createGroup(name="emptyGrp", empty=True)

   mlib.delete(copy)

対象の引数には名前の文字列のほか、Node・Plug・Vertex などのコンポーネント、
Vertices などのコレクション、Selection、Maya API 2.0 の MObject・MDagPath・MPlug と
それらのリストを指定できます。変換の規則と、mlib のオブジェクトを ``maya.cmds`` へ
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
``plug.delete()``、所有ノードの削除は ``mlib.delete(plug.getNode())`` を使ってください。

作成結果から次の操作を選ぶ
--------------------------

.. list-table::
   :header-rows: 1

   * - 作成
     - 戻り値
     - 頂点・CVへ進む入口
   * - ``createPolygon(...)``
     - Mesh
     - ``mesh.getVertices()``
   * - ``createCurve(...)``
     - Transform
     - ``curve_transform.getShape().getCVs()``
   * - ``createNurbs(type="circle", ...)``
     - NurbsCurve
     - ``circle.getCVs()``
   * - ``createNurbs(type="square", ...)``
     - list[NurbsCurve]
     - 各シェイプの ``getCVs()``
   * - ``createNurbs(type="cube", ...)``
     - list[NurbsSurface]
     - 各シェイプの ``scaleGeometry(...)`` 等

作成した型からの連続例と単数・複数コンポーネントは :doc:`guide_geometry`、
値を作成フラグへ渡す際のUI単位との境界は :doc:`cmds_interop` を参照してください。

選択を取得して分類する
----------------------

.. code-block:: python

   selected_vertices = mlib.ls(sl=True, type="vertex")  # list[Vertex]
   captured = mlib.captureSelection()
   vertex_groups = captured.filter("vertex").getComponents()  # list[Vertices]
   for vertices in vertex_groups:
       print(vertices.shape, vertices.indices)

``ls`` はMayaの検索結果の順に参照を返します。単一のノード型
``type="joint"`` / ``type="skinCluster"`` はJoints / SkinClusters、
その他のノード型やコンポーネント型はリストです。
``type=["joint"]`` のようなMayaの複数型指定はリストを返します。
コンポーネントの型指定は ``vertex`` / ``edge`` / ``face`` / ``uv`` / ``controlVertex`` です。
選択済みの該当要素を絞る処理で、メッシュ選択から全頂点への変換は行いません。
全頂点を取得するときは対象Meshの ``getVertices()`` を使います。

``captureSelection()`` は取得時点の参照を保持し、現在の選択へ自動追従しません。
``filter("vertex").getComponents()`` で複数シェイプを分けて一括編集する例は
:doc:`guide_geometry`、選び直しは :doc:`selection_and_channelbox` を参照してください。

選択とアニメーション
--------------------

.. code-block:: python

   import mlib
   from maya import cmds

   a = mlib.createNode("transform", name="animationA")
   b = mlib.createNode("transform", name="animationB")

   mlib.select([a, b])
   print(mlib.ls(selection=True))
   mlib.select(clear=True)

   cmds.currentTime(1)
   cmds.setKeyframe(a.getPlug("translateX"), value=0.0)
   cmds.currentTime(24)
   cmds.setKeyframe(a.getPlug("translateX"), value=10.0)

   mlib.bakeResults(a, time=(1, 24), attribute=["translateX"], simulation=True)

``select`` は ``maya.cmds.select`` と同じ引数を受け付けます。``nodes`` を省略すると
``clear=True`` のような選択操作専用のフラグだけで呼び出せます。
時刻やキー操作は ``maya.cmds`` を使用します。現在時刻の照会は
``cmds.currentTime(query=True)`` と明示します。
``bakeResults`` は時間範囲を補いません。``time=(start, end)`` を明示してください。
``simulation`` の既定値はFalseです。シーン全体の評価が必要ならTrueを指定します。
GUIではベイク中のメインペインを非表示にし、終了時に元の状態へ戻します。

``mlib.getPlug("node.attr")`` はPlug参照を返します。
``node.getPlug("attrName")`` からも同じアトリビュートを取得できます。
取得した ``Plug`` の ``get()``/``get(uiUnits=True)``/``set()``/``connectTo()``、
および ``node.addAttr()`` で値・接続・追加アトリビュートを操作します。
``Plug`` は ``maya.cmds.getAttr(plug)`` のように maya.cmds へそのまま渡すこともできます
（:doc:`cmds_interop`）。

ノードのアトリビュートは、:meth:`~mlib.nodes.node.Node.getPlug` で取得した
:class:`~mlib.plugs.plug.Plug` オブジェクトを通して操作します。
ノードからは ``getPlug()``、アトリビュート名からは ``mlib.getPlug()`` を使います。

コマンドの命名と役割
--------------------

正式コマンドのファイル名と関数名は動詞+対象です。``ls`` は一覧取得の慣用名として維持します。
作成・取得コマンドの旧名は残しません。公開関数とファイルは同名です
（:doc:`getter_aliases`）。

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
``constraint.getTargets()`` / ``constraint.getWeightPlugs()``、編集は
``constraint.setWeight()`` を使います。セットは
``object_set.getMembers()`` / ``add()`` / ``remove()`` を使います。
``drivenKey`` は関係取得のみで、キーの生成は ``setKey()`` です。
