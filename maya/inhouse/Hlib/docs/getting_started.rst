使い始める
==========

実行環境
--------

ワークスペースのバージョン別起動バッチから Maya を起動すると、
``maya/inhouse`` が Python の検索パスに追加されます。
以下は Maya の Script Editor の Python タブで実行する例です。
ノード作成例は現在のシーンにノードを追加します。

ノードと属性
------------

.. code-block:: python

   import Hlib
   from Hlib.decorators.undo import undo_chunk

   with undo_chunk("Hlib example"):
       node = Hlib.cmds.create_node("transform", name="hlibExample")
       node.attr("visibility").set(False)

   print(node.name())
   print(node.attr("visibility").get())
   print(Hlib.cmds.ls(type="transform"))

``create_node`` は ``maya.cmds.createNode`` にキーワード引数を渡し、
対応するラッパーを返します。既存ノードは ``Hlib.Node("ノード名")`` で取得できます。
``ls`` は ``maya.cmds.ls`` の引数を受け取り、通常はラッパーのリストを返します。
``type="joint"`` と ``type="skinCluster"`` は、それぞれ ``Joints`` と
``SkinClusters`` コレクションを返します。

形状情報
--------

Transform の ``shape()`` は実際のシェイプ型に応じて ``Mesh`` や
``NurbsCurve`` を返します。以下は既存ノード名を指定する例です。

.. code-block:: python

   mesh = Hlib.Node("pCube1").shape()
   print(mesh.num_vertices, mesh.num_edges, mesh.num_polygons)
   points = mesh.points(ws=True)

   curve = Hlib.Node("curve1").shape()
   print(curve.degree, curve.num_cvs, curve.num_spans)
   print(curve.length())  # オブジェクト空間の弧長
   cvs = curve.cv_positions(ws=True)

位置配列は Maya API 2.0 の ``MPointArray`` です。
距離は Maya API の内部単位を使い、``ws=False`` はオブジェクト空間です。

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

コンストレイント
----------------

``add_constraint`` は呼び出し元を拘束し、引数のノードを拘束元にします。
次の例はシーンにノードとコンストレイントを追加します。

.. code-block:: python

   driver = Hlib.cmds.create_node("transform", name="hlibDriver")
   driven = Hlib.cmds.create_node("transform", name="hlibDriven")
   constraint = driven.add_constraint(driver, "parent", maintainOffset=True)
   print(constraint.targets())
   print(constraint.weight_aliases(), constraint.weights())
   constraint.weight_plugs()[0].set(0.5)

複数の拘束元はリストで指定できます。型名は ``"parent"`` と
``"parentConstraint"`` の両方に対応します。戻り値は ``ParentConstraint`` などの
具象ラッパーで、既存ノードを ``Hlib.Node`` で取得しても同じ型に解決されます。
一度の呼び出しを1つの Undo チャンクとして扱います。

対応する型は parent、point、orient、scale、aim、poleVector、geometry、normal、
tangent、pointOnPoly です。PoleVector は RP IK ハンドル、Tangent は NURBS カーブ、
Geometry／Normal／PointOnPoly は各 Maya コマンドに適した形状を指定してください。
IK ハンドルは ``Hlib.Node(handle_name)`` から ``IkHandle`` として取得でき、
``handle.add_constraint(driver, "poleVector")`` を使用できます。

追加のキーワード引数は対応する Maya コマンドへ渡します。
例えば ``maintainOffset`` は全種類に共通するフラグではありません。
PointOnPoly のターゲットUV等も Maya の仕様に従い、必要に応じてプラグから設定します。
同じ種類の拘束が既にある場合は、Maya の規則で既存拘束へターゲットが追加される場合があります。

シーン情報
----------

.. code-block:: python

   from Hlib import Scene

   scene = Scene()
   print(scene.path())  # 未保存なら None
   print(scene.is_modified())

数学型
------

.. code-block:: python

   from Hlib.maths import Vector

   result = Vector(1, 2, 3) + Vector(4, 5, 6)
   print(tuple(result))  # (5.0, 7.0, 9.0)

``maths`` の実装は Maya に依存しません。ただし通常の
``from Hlib.maths import ...`` は親パッケージ ``Hlib`` の初期化を通るため、
この import には Maya 環境が必要です。

再読み込み
----------

.. code-block:: python

   import Hlib
   Hlib.reload()

再読み込みは Hlib 内の依存関係をもとに行われます。
古いクラスのインスタンスや ``from ... import ...`` で取得済みの参照は
自動では置き換わらないため、必要な参照・ラッパーを取得し直してください。


コンポーネントと座標
--------------------

Vertex / CV はシーンを参照する単体ラッパーです。``x`` / ``y`` / ``z`` は
オブジェクト空間の座標で、Maya の現在の距離単位を使用します。
値を代入するとシーンを更新し、Undo できます。座標のスナップショットが
必要な場合は ``position()`` が返すタプルを保持してください。

.. code-block:: python

    mesh = Hlib.Mesh("pCubeShape1")
    vertex = mesh.vertex(0)
    print(vertex.x, vertex.y, vertex.z)
    vertex.x = 2.0
    vertex.set_position((1, 2, 3), ws=True)
    print(vertex.position(ws=True))

    curve = Hlib.NurbsCurve("curveShape1")
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
