複数コンポーネントの座標編集
============================================================

Vertices・CVs・UVsでも単体と同じ名前で座標を取得・設定できます。
複数形の取得結果は保持順の座標列です。重心や平均座標ではありません。

.. code-block:: python

   from maya.api.OpenMaya import MSpace
   import hlib

   mesh = hlib.getNode("pCubeShape1")
   vertices = mesh.vertices([2, 0, 5])
   points = vertices.getPosition(space=MSpace.kWorld)
   vertices.setPositions([(1, 2, 3), (4, 5, 6), (7, 8, 9)], space=MSpace.kWorld)

   vertices.setX(0)                 # 全頂点のXだけを0にする
   vertices.setY([1, 2, 3])         # 保持順の頂点ごとに設定
   vertices.setPosition((0, 0, 0))  # 全頂点が原点に集まる

``getPosition()`` は保持順の座標列を返します。単体と同じ名前で呼べる
``getPosition()`` も複数形では座標列を返します。
``setPosition(value)`` は全要素への同じ値の適用、
``setPositions(values)`` は要素ごとの設定です。引数の形による暗黙の切り替えはしません。

* Vertex / Vertices、CV / CVs: XYZ（cm）、space指定、getX()/setX()等。
* UV / UVs: UV座標、getU()/setU()等。現在のUVセットを参照し、space指定はありません。
* Edge / Edges、Face / Faces: vertices()で接続頂点を取得できます。
  Edges/Facesの結果は共有頂点の重複を除いたVerticesです。
  位置を変える場合は ``faces.vertices().setPositions(...)`` などを使います。

軸の設定メソッドはスカラーまたは要素数と同じ数値列を受け取ります。
getX()/setX()等の軸メソッドはオブジェクト空間、位置メソッドの距離はcmです。
単体の ``fullName()`` に対応する複数形は ``fullNames()``、番号は ``indices`` です。
単体に存在しない操作を任意転送する仕組みは使わず、意味が定まる操作を明示的に公開します。

一括編集は1回のUndoにまとまります。件数・非有限座標・コンポーネント番号を
書き込み前に検証します。空コレクションには空の座標列を渡せます。
Mayaが途中の書き込みを拒否した場合は例外を返し、完了済み変更の自動ロールバックはしません。
共有shapeや周期カーブのCVの連動、トポロジー変更後の番号の扱いはMayaの規則に従います。

このページのUndoの説明は通常モード（``fast=False``）を前提とします。
対応する値更新メソッドの ``fast=True`` はUndo対象外です。対応範囲と制限は :doc:`fast_edit` を参照してください。
