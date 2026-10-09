形状とコンポーネント（頂点・エッジ・フェース）
================================================================================

Mesh・NurbsCurveの形状情報、ミラー、頂点やCVなどの操作を説明します。

未使用の中間Shapeを削除する
----------------------------------------

Transform直下の不要な中間Shapeは次のように取得・削除できます。

.. code-block:: python

   transform = hlib.node("pCube1")
   candidates = transform.unusedIntermediateShapes()  # list[Shape]
   transform.deleteUnusedIntermediateShapes()            # 自身を返す

対象は ``intermediateObject=True`` で、標準のshadingEngineメンバー接続以外に
出力接続を持たないShapeです。SkinCluster等へ形状を供給している中間Shapeや、
message接続・ユーザーのobjectSet等で参照されるShapeは残します。
通常Shape、参照・ノードロック・インスタンス・子DAGを持つShapeも対象外です。
Transform自身が参照/ノードロックされている場合も削除しません。
子Transform以下は検索せず、対象なしは取得が ``[]``、削除は何もしません。

入力履歴だけが残る中間Shapeは削除対象ですが、入力接続を先に外すことで上流の
履歴ノードと親Transformは保持します。削除と接続解除は1回のUndo/Redoに対応し、
途中の失敗時は巻き戻します。Undoを有効にして使用してください。fastフラグはありません。

UVまたは頂点位置を基準に頂点番号を合わせる
------------------------------------------------------------

``Mesh.reorderVertices(reference, uv_set="map1", tolerance=1e-6, *, fast=False, match="uv", worldSpace=False)`` は、
対象の形状を保ったまま基準メッシュの頂点番号へ並べ替え、自身を返します。
基準メッシュは変更しません。

.. code-block:: python

   reference = hlib.node("referenceMesh").shape()
   target = hlib.node("targetMesh").shape()
   target.reorderVertices(reference, uv_set="map1")

   # 頂点位置で対応付ける。UV形状・割り当ては対象のものを維持する。
   target.reorderVertices(reference, match="position", tolerance=0.001)
   target.reorderVertices(reference, match="position", ws=True, tolerance=0.001)

   # Undo不要の場合。現在の頂点tweakも座標へベイクして扱える。
   target.reorderVertices(reference, uv_set="map1", fast=True)

``match="uv"``（既定）は従来のUV照合です。``match="position"`` は頂点位置で照合し、
UVセット名を照合に使用しません。``worldSpace=False`` は各メッシュのローカル座標、
``worldSpace=True``（短縮名 ``ws=True``）はワールド座標を比較します。
位置照合での ``tolerance`` はユークリッド距離の上限(cm)です。
最近傍へ強制対応させる方式ではなく、許容距離内に候補が1頂点だけあることを要求します。
異なる形状や重複位置等で対応が見つからない・曖昧な場合は変更しません。

頂点数・面数・面のつながりと向きが一致し、全頂点を一対一に対応付けられることが条件です。
UVシームは頂点に属する全ての面頂点UVを照合します。重なり等で候補が複数ある場合、
UV未割り当て、孤立頂点、対応不足、トポロジー不一致は変更前に例外とします。
UV照合時の ``tolerance`` はUV座標の各成分の許容誤差で、距離単位ではありません。
面順・面の向き・全UVセット・エッジの硬軟・固定法線・面マテリアルを保持します。
エッジ番号は再構築により変わる場合があります。既存Component参照は取得し直してください。

通常モードは標準コマンドで1回のUndo/Redoに対応し、Undo有効が必要です。
非ゼロの頂点tweak（直接編集オフセット）がある場合は通常モードでは変更前に拒否します。
その場合は作業用の複製で ``fast=True`` を使用できますが、Undoには記録されません。

スキン等のウェイト移し替えは行いません。対象の入力履歴、下流メッシュへの接続、
インスタンス、参照ファイル、カラーセット、クリース、穴付きポリゴン、blind data、
マテリアル以外のコンポーネントセットは未対応です。自動で履歴を削除しません。
基準側は読み取りだけなので履歴付きでも照合できます。

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

作成した形状から頂点・CVへ進む
------------------------------

作成コマンドの戻り値はコマンドごとに決まっています。
``createCurve`` はTransformなので ``shape()`` を経由し、
``createPolygon`` と単一形状の ``createNurbs`` は返されたシェイプを使います。

.. code-block:: python

   mesh = hlib.createPolygon(type="cube", name="componentBody", constructionHistory=False)
   mesh.vertices([0, 1]).setPositionZ(2.0)

   curve_transform = hlib.createCurve(name="componentCurve", degree=1,
                                      point=[(0, 0, 0), (1, 1, 0), (2, 0, 0)])
   curve = curve_transform.shape()
   curve.cvs([0, 1]).setPositionZ(1.0)

   circle = hlib.createNurbs(type="circle", name="componentCircle")
   circle.cvs().mirror(axis="x")

``vertices()`` と ``cvs()`` の入力は、そのシェイプの実番号です。
省略・``None`` は取得時の全要素、``[]`` は空集合、重複は最初の出現だけを保持します。
直接 ``Vertices(shape, indices)`` 等を構築する場合もシェイプラッパーが必要です。
Transformや名前文字列は ``hlib.node(name).shape()`` でシェイプへ解決してください。
複数シェイプを持つTransformでは ``shapes()`` で対象を選びます。

.. list-table:: シェイプからの単数・複数取得
   :header-rows: 1

   * - シェイプ
     - 単数
     - 複数
   * - Mesh
     - ``vertex(index)`` / ``edge(index)`` / ``face(index)`` / ``uv(index)``
     - ``vertices(indices=None)`` / ``edges(indices=None)`` / ``faces(indices=None)`` / ``uvs(indices=None)``
   * - NurbsCurve
     - ``cv(index)``
     - ``cvs(indices=None)``

単数取得は ``idx`` も使えます。省略名は対応する正式getterへ委譲し、
引数・返却型は共通です（:doc:`getter_aliases`）。
CV/CVsはNURBSカーブ用です。NURBSサーフェスの2次元CVには
この単一番号の入口を使えません。

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

   mesh = hlib.node("pCube1").shape()
   print(mesh.numVertices(), mesh.numEdges(), mesh.numPolygons())
   points = mesh.points(ws=True)
   normals = mesh.vertexNormals(ws=True, angle_weighted=True)

   curve = hlib.node("curve1").shape()
   print(curve.degree(), curve.numCVs(), curve.numSpans())
   print(curve.length())         # オブジェクト空間のカーブ長
   print(curve.length(ws=True))  # 親のスケール等を含むワールド空間のカーブ長
   print(curve.length(ws=True, unit="m"))  # メートルで取得

   cvs = curve.cvPositions(ws=True)

   print(curve.collocatedCVGroups())  # 重なった CV のグループ（無ければ []）

``length()`` は計算ノードを追加せず、現在のカーブ長を取得します。
戻り値は既定でcmです。``unit=None`` の場合だけ現在の距離UI単位を使います。
unitにはmm/cm/m/km/in/ft/yd/mi、
またはMayaの長名を指定できます。シーン設定は変更しません。
ws=Trueは非均等スケール・シアーと対象インスタンスの変換も反映します。
toleranceは出力単位によらず内部単位（cm）での計算許容誤差です。

.. code-block:: python

   from hlib.common import Preferences
   from hlib.common import units

   print(Preferences.linearUnit())  # 現在のシーン単位（例: "cm"）
   print(units.convertDistance(100, from_unit="cm", to_unit="m"))  # 1.0

位置配列は Maya API 2.0 の ``MPointArray``、``vertexNormals()`` は ``list[Vector]`` です。
距離は Maya API の内部単位を使い、``ws=False`` はオブジェクト空間です。
``vertexNormals()`` は ``MFnMesh.getVertexNormals()`` を使い、接する面頂点法線を
頂点ごとに平均して、頂点番号順に返します。``angle_weighted=True`` は角度で重み付けし、
Falseは角度による重み付けをしません。面ごとの法線配列や最初の面法線ではありません。
``collocatedCVGroups`` はほぼ同じ位置にある CV（クリーンアップ前のカーブの
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
単位はcmです。既定はその空間の原点で、
Transform のピボット位置は自動では使用しません。
``indices=None`` は全頂点／全 CV、空のリストは変更なしです。

Transform直下の全Shapeをまとめて反転する場合は
``transform.mirrorGeometry(axis="x", ws=False)`` を使います。
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

   node.mirrorTransform(axis="x", ws=True)   # ワールドのYZ平面
   node.mirrorTransform(axis="z", ws=False)  # ペアレント空間のXY平面
   node.mirrorTransform(axis="xy", ws=True, pivot=(10, 0, 0))

Transform・Jointで使用でき、Transforms・Jointsからも一括実行できます。
通常処理はUndo対応、``fast=True`` はUndoなしです。
``pivot`` はcm単位です。``ws=False`` は形状ミラーの
オブジェクト空間と異なり、親Transformの座標空間です。

向きは ``Matrix.mirror()`` と同じビヘイビアミラーです。
例えば単位行列をX軸でミラーするとX軸回り180度の向きになります。
負スケールで形状を裏返す処理ではなく、頂点・CVは変更しません。
子孫は親変換に追従し、スキニング済みのJointは通常の姿勢変更として変形に影響します。
バインド情報の補正は行いません。

非ゼロのピボット（補正移動を含む）とTransformのrotateAxisは未対応で、
変更前にエラーになります。JointのjointOrientには対応します。
親に非一様スケールがある場合、ミラー後のローカルスケール・シアーが変わる場合があります。


コンポーネントと座標
--------------------

Vertex / CV はシーンを参照する単体ラッパーです。``positionX()`` / ``positionY()`` /
``positionZ()`` は既定でオブジェクト空間の座標を、cm単位で返します。
``ws=True`` でワールド空間を指定できます。
``setPositionX(value)`` などのメソッドでシーンを更新し、Undoできます。座標のスナップショットが
必要な場合は ``position()`` が返すタプルを保持してください。

.. code-block:: python

    mesh = hlib.nodes.Mesh("pCubeShape1")
    vertex = mesh.vertex(0)
    print(vertex.positionX(), vertex.positionY(), vertex.positionZ())
    vertex.setPositionX(2.0)
    vertex.setPosition((1, 2, 3), ws=True)
    print(vertex.position(ws=True))

    curve = hlib.nodes.NurbsCurve("curveShape1")
    cv = curve.cv(0)
    cv.setPositionZ(-cv.positionZ())
    curve.cvs().mirror(axis="z", ws=False)
    mesh.vertices([0, 1, 2]).mirror(axis="x", ws=True)

    edge = mesh.edge(0)       # Edge
    face = mesh.face(0)       # Face
    mesh.edges([0, 1]).vertices().mirror(axis="x")
    vertices = mesh.faces([0, 1]).vertices()
    uv = mesh.uv(0)           # UV
    uv.setU(0.25)
    uv.setV(0.75)
    print(mesh.uvs().position())

単体型は Vertex、CV、Edge、Face、UV、複数形は Vertices、CVs、Edges、Faces、UVs です。
複数形は反復、添字、スライスに対応します。番号はOpenMayaと同じで作成時に固定し、座標は現在の値を
取得します。トポロジー変更後の要素の同一性は保証しません。
周期カーブのCVは末尾の重複CVもAPI番号で参照します。cmdsへ渡す名前や通常更新では、
末尾の重複CVを先頭の対応する番号へ変換します。
UV は現在の UV セットを参照し、セットを切り替えると切替先を参照します。
既存の ``mesh.mirror()`` / ``curve.mirror()`` も複数形へ委譲して使用できます。

詳しい一括操作は :doc:`component_collections` を参照してください。

選択した頂点をシェイプごとに編集する
------------------------------------

.. code-block:: python

   captured = hlib.captureSelection()
   for vertices in captured.filter("vertex").components():
       if vertices.valid():
           vertices.setPositionZ(2.0)
   captured.select(missing="skip")  # 残っている対象を選び直す

``hlib.ls(sl=True, type="vertex")`` は単体Vertexのリストです。
``captureSelection().filter("vertex").components()`` は、同一シェイプ・種類ごとの
Verticesコレクションのリストを返します。複数メッシュの選択も各シェイプへ分けられ、
各グループ内は取得時の順序を維持します。通常編集はグループごとに1回のUndoです。
正式な種類名は ``vertex`` / ``edge`` / ``face`` / ``uv`` / ``controlVertex`` です。
Selectionの ``filter`` には従来の記号 ``vtx`` / ``e`` / ``f`` / ``map`` / ``cv`` も使えます。
どちらの取得も種類を絞る処理なので、オブジェクト選択やフェース選択を頂点へ変換しません。
ターゲットのデルタから頂点を外す操作は :doc:`guide_deformers` を参照してください。

参照の現在有効性を確認する
--------------------------

単数と複数の ``valid()`` は、シェイプの生存・種類と現在の番号範囲を確認します。
削除やトポロジー縮小で参照できなくなればFalseです。空コレクションも、
対応するシェイプが生存していればTrueです。UVは現在のUVセットで判定します。
判定はシーンやUndoキューを変更しません。

.. code-block:: python

   held_vertex = mesh.vertex(0)
   held_vertices = mesh.vertices([0, 1])
   if held_vertex.valid() and held_vertices.valid():
       print(held_vertex.position(), held_vertices.position())

番号が範囲内でも、トポロジー変更前と同じ要素を指す保証はありません。
変更後は必要な参照を取得し直してください。``valid()`` を追加しても、
無効な参照での名前・座標照会が例外になる既存の動作は変わりません。

このページのUndoの説明は通常モード（``fast=False``）を前提とします。
対応する値更新メソッドの ``fast=True`` はUndo対象外です。対応範囲と制限は :doc:`fast_edit` を参照してください。

例えば ``mesh.vertices([0, 1]).setPositionZ(2.0, fast=True)`` は
入力履歴のないメッシュで使えます。履歴付きメッシュ、周期カーブ、
NURBSサーフェス等の未対応対象をfastへ渡すと ``NotImplementedError`` です。
履歴を残す編集やUndoが必要な場合は、既定の通常モードを使います。
座標値はcmです。作成コマンドへ数値を渡す境界ではUI単位へ明示変換してください
（:doc:`cmds_interop`）。


Shapeのスケール
----------------------------

.. code-block:: python

   shape.scaleGeometry(2)                         # オブジェクト空間で一様2倍
   shape.scaleGeometry((2, 1, 0.5))               # XYZ別の倍率
   shape.scaleGeometry((1, 2, 1), ws=True)        # ワールドY方向だけ2倍
   shape.scaleGeometry(2, pivot=(1, 0, 0))        # 指定中心から拡縮
   transform.scaleGeometry((2, 1, 1))            # 直下の全Shape
   mesh.scaleGeometry(2, indices=[0, 1])         # 頂点を限定
   surface.scaleGeometry(2, indices=[(0, 0)])    # サーフェスの(U, V) CV
   mesh.scaleGeometry(2, fast=True)              # om2で直接更新、Undoなし

メッシュ、NURBSカーブ、NURBSサーフェスに対応します。頂点・CVの座標だけを編集し、
Transformの行列は変更しません。既定はオブジェクト空間の原点が中心です。
``ws=True`` ではワールド空間の原点になり、``pivot`` はその空間のcm単位で指定します。
Transformのピボット位置は自動では使いません。

通常のUndoに対応します。負数・0の倍率も指定できますが、面の頂点順は変更しません。
周期CVはMayaの連動規則に従い、インスタンスでは共有形状全体に影響します。
メッシュ・カーブは座標をom2で一括取得し、通常更新はcmdsでUndoに対応します。
``fast=True`` は入力履歴なしのメッシュ・非周期カーブに対応し、Undoへ記録しません。
サーフェス・周期カーブ・入力履歴付き形状のfast更新は ``NotImplementedError`` です。
周期カーブの先頭と末尾が同じCVを表す場合、番号をまとめて一回だけ拡縮します。
重み付きCVのワールドXYZはOpenMayaの値を使い、設定時もCVの重みを保持して逆変換します。


単数の ``setPosition``、複数の ``setPositions``、Shapeの ``scaleGeometry`` は
同じ座標書込み処理を使います。複数点の通常更新も単数ラッパーを生成し直さず、
指定順でcmdsへ書き込みます。通常更新は一回のUndo、fast更新はUndoなしです。
周期CVを複数回指定した座標設定は後の値を優先し、拡縮では同じCVを一回だけ処理します。
