形状とコンポーネント（頂点・エッジ・フェース）
================================================================================

Mesh・NurbsCurveの形状情報、ミラー、頂点やCVなどの操作を説明します。

Mayaのコンポーネント（頂点・エッジ・フェース・CV・UV）は、シェイプを構成する要素です。
メッシュ全体を扱う ``Mesh`` に対して、``Vertex`` はその頂点1個を参照します。

* ``Vertex``：メッシュの頂点
* ``Edge``：メッシュのエッジ（辺）
* ``Face``：メッシュのフェース（面）
* ``CV``：NURBSカーブの制御点
* ``UV``：メッシュのUV要素（テクスチャ座標）

``Component`` は単体要素、``Components`` は同一シェイプの要素群を扱う基底クラスです。
例えば ``Vertices`` は複数の頂点をまとめて扱います。

例は Maya の Script Editor で実行します。既存ノード名は使用するシーンに合わせてください。
最初に ``import hlib`` と ``from maya import cmds`` を実行してください。

プリミティブの生成
------------------

``createPolygon`` は種類を ``type`` （短名 ``typ``）で指定し、単一の ``Mesh`` を返します。
cube（既定）、sphere、cylinder、cone、plane、torus、pipe、pyramid、prism、helix、
platonicSolidを使用できます。``polyCube`` 等のMayaコマンド名でも指定できます。
寸法・分割数・履歴などのフラグは、選んだMayaコマンドの長名・短名に従います。

.. code-block:: python

   mesh = hlib.createPolygon(type="cube", name="body", width=2, constructionHistory=False)
   sphere = hlib.createPolygon(typ="sphere", r=3, sx=24, sy=16)
   mesh.transform().plug("translateX").set(5)
   history = cmds.listHistory(sphere)

``name`` は親Transformの名前です。履歴を有効にしても戻り値はMeshです。
作成は1回のUndoで戻せます。query/editやobject=Falseは受け付けません。
押し出し・結合など既存メッシュの編集コマンドはこの入口の対象外です。

NURBSプリミティブの生成
------------------------

``createNurbs`` はMayaのCreate > NURBS Primitivesの8種類に対応します。
``type`` （短名 ``typ``）でcircle（既定）、square、sphere、cube、cylinder、cone、
plane、torusを選択します。寸法や分割数、履歴は各Mayaコマンドのフラグを使います。

.. code-block:: python

   circle = hlib.createNurbs(type="circle", radius=2)  # NurbsCurve
   sphere = hlib.createNurbs(type="sphere", radius=3)  # NurbsSurface
   faces = hlib.createNurbs(type="cube")  # list[NurbsSurface]（6枚）
   edges = hlib.createNurbs(type="square")  # list[NurbsCurve]（4本）
   circle.transform().plug("translateX").set(5)

戻り値はシェイプです。Cube・Squareは複数シェイプのリストで、
それぞれの ``transform()`` は構成パーツの親Transformです。
``name`` は最上位Transformの名前を指定します。
履歴の有無で戻り値は変わらず、生成全体を1回のUndoで戻せます。
query/edit、object=False、polygonによる非NURBS出力は受け付けません。
NurbsSurfaceはShape共通のアトリビュート・親Transform操作を提供します。

形状情報
--------

Transform の ``shape()`` は実際のシェイプ型に応じて ``Mesh`` や
``NurbsCurve`` を返します。以下は既存ノード名を指定する例です。

.. code-block:: python

   mesh = hlib.getNode("pCube1").shape()
   print(mesh.vertex_count(), mesh.edge_count(), mesh.polygon_count())
   points = mesh.get_points(ws=True)
   normals = mesh.get_normals(ws=True, angle_weighted=True)

   curve = hlib.getNode("curve1").shape()
   print(curve.degree(), curve.cv_count(), curve.span_count())
   print(curve.length())         # オブジェクト空間のカーブ長
   print(curve.length(ws=True))  # 親のスケール等を含むワールド空間のカーブ長
   print(curve.length(ws=True, unit="m"))  # メートルで取得

   cvs = curve.get_cv_positions(ws=True)

   print(curve.get_collocated_cv_groups())  # 重なった CV のグループ（無ければ []）

``length()`` は計算ノードを追加せず、現在のカーブ長を取得します。
戻り値は既定で現在のシーンの距離UI単位です。unitにはmm/cm/m/km/in/ft/yd/mi、
またはMayaの長名を指定できます。シーン設定は変更しません。
ws=Trueは非均等スケール・シアーと対象インスタンスの変換も反映します。
toleranceは出力単位によらず内部単位（cm）での計算許容誤差です。

.. code-block:: python

   from hlib.environment import Preferences
   from hlib.utils import units

   print(Preferences.get_linear_unit())  # 現在のシーン単位（例: "cm"）
   print(units.convert_distance(100, from_unit="cm", to_unit="m"))  # 1.0

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

Transform直下の全Shapeをまとめて反転する場合は
``transform.mirror_geometry(axis="x", ws=False)`` を使います。
従来の ``Transform.mirror()`` はこの名前へ変更しました。
Shapeやコンポーネントの ``mirror()`` は変更していません。

親の移動・回転・スケールを変更せずに形状の座標を編集し、1回の Undo で戻せます。
ほぼゼロのスケールなど、数値的に不安定なワールド変換はエラーにします。
複製・結合や片側から反対側への対称化を行う機能ではありません。
メッシュの面の頂点順は維持するため、奇数軸での反転後は必要に応じて
法線を処理してください。インスタンスでは共有形状全体に影響します。

ノードの位置と向きのミラー
------------------------------------

.. code-block:: python

   node.mirror_transform(axis="x", ws=True)   # ワールドのYZ平面
   node.mirror_transform(axis="z", ws=False)  # ペアレント空間のXY平面
   node.mirror_transform(axis="xy", ws=True, pivot=(10, 0, 0))

Transform・Jointで使用でき、Transforms・Jointsからも一括実行できます。
通常処理はUndo対応、``fast=True`` はUndoなしです。
``pivot`` は現在のMaya距離単位です。``ws=False`` は形状ミラーの
オブジェクト空間と異なり、親Transformの座標空間です。

向きは ``Matrix.mirrored()`` と同じビヘイビアミラーです。
例えば単位行列をX軸でミラーするとX軸回り180度の向きになります。
負スケールで形状を裏返す処理ではなく、頂点・CVは変更しません。
子孫は親変換に追従し、スキニング済みのJointは通常の姿勢変更として変形に影響します。
バインド情報の補正は行いません。

非ゼロのピボット（補正移動を含む）とTransformのrotateAxisは未対応で、
変更前にエラーになります。JointのjointOrientには対応します。
親に非一様スケールがある場合、ミラー後のローカルスケール・シアーが変わる場合があります。


コンポーネントと座標
--------------------

Vertex / CV はシーンを参照する単体ラッパーです。``get_x()`` / ``get_y()`` /
``get_z()`` はオブジェクト空間の座標を、Mayaの現在の距離単位で返します。
``set_x(value)`` などのメソッドでシーンを更新し、Undoできます。座標のスナップショットが
必要な場合は ``get_position()`` が返すタプルを保持してください。

.. code-block:: python

    mesh = hlib.nodes.Mesh("pCubeShape1")
    vertex = mesh.vertex(0)
    print(vertex.get_x(), vertex.get_y(), vertex.get_z())
    vertex.set_x(2.0)
    vertex.set_position((1, 2, 3), ws=True)
    print(vertex.get_position(ws=True))

    curve = hlib.nodes.NurbsCurve("curveShape1")
    cv = curve.cv(0)
    cv.set_z(-cv.get_z())
    curve.cvs().mirror(axis="z", ws=False)
    mesh.vertices([0, 1, 2]).mirror(axis="x", ws=True)

    edge = mesh.edge(0)       # Edge
    face = mesh.face(0)       # Face
    mesh.edges([0, 1]).vertices().mirror(axis="x")
    vertices = mesh.faces([0, 1]).vertices()
    uv = mesh.uv(0)           # UV
    uv.set_u(0.25)
    uv.set_v(0.75)
    print(mesh.uvs().get_position())

単体型は Vertex、CV、Edge、Face、UV、複数形は Vertices、CVs、Edges、Faces、UVs です。
複数形は反復、添字、スライスに対応します。番号は作成時に固定し、座標は現在の値を
取得します。トポロジー変更後の要素の同一性は保証しません。
UV は現在の UV セットを参照し、セットを切り替えると切替先を参照します。
既存の ``mesh.mirror()`` / ``curve.mirror()`` も複数形へ委譲して使用できます。

詳しい一括操作は :doc:`component_collections` を参照してください。

このページのUndoの説明は通常モード（``fast=False``）を前提とします。
対応する値更新メソッドの ``fast=True`` はUndo対象外です。対応範囲と制限は :doc:`fast_edit` を参照してください。


Shapeのスケール
----------------------------

.. code-block:: python

   shape.scale_geometry(2)                         # オブジェクト空間で一様2倍
   shape.scale_geometry((2, 1, 0.5))               # XYZ別の倍率
   shape.scale_geometry((1, 2, 1), ws=True)        # ワールドY方向だけ2倍
   shape.scale_geometry(2, pivot=(1, 0, 0))        # 指定中心から拡縮
   transform.scale_geometry((2, 1, 1))            # 直下の全Shape
   mesh.scale_geometry(2, indices=[0, 1])         # 頂点を限定
   surface.scale_geometry(2, indices=[(0, 0)])    # サーフェスの(U, V) CV

メッシュ、NURBSカーブ、NURBSサーフェスに対応します。頂点・CVの座標だけを編集し、
Transformの行列は変更しません。既定はオブジェクト空間の原点が中心です。
``ws=True`` ではワールド空間の原点になり、``pivot`` もその空間の現在のMaya距離単位で指定します。
Transformのピボット位置は自動では使いません。

通常のUndoに対応します。負数・0の倍率も指定できますが、面の頂点順は変更しません。
周期CVはMayaの連動規則に従い、インスタンスでは共有形状全体に影響します。
