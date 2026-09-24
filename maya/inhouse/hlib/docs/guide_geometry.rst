形状とコンポーネント
============================================================

Mesh・NurbsCurveの形状情報、ミラー、頂点やCVなどの操作を説明します。

例は Maya の Script Editor で実行します。既存ノード名は使用するシーンに合わせてください。
最初に ``import hlib`` を実行してください。

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

詳しい一括操作は :doc:`component_collections` を参照してください。
