複数コンポーネントの座標編集
============================================================

Vertices・CVs・UVsでも単体と同じ名前で座標を取得・設定できます。
複数形の取得結果は保持順の座標列です。重心や平均座標ではありません。

.. code-block:: python

   import hlib

   mesh = hlib.node("pCubeShape1")
   vertices = mesh.vertices([2, 0, 5])
   points = vertices.get_position(ws=True)
   vertices.set_positions([(1, 2, 3), (4, 5, 6), (7, 8, 9)], ws=True)

   vertices.set_x(0)                 # 全頂点のXだけを0にする
   vertices.set_y([1, 2, 3])         # 保持順の頂点ごとに設定
   vertices.set_position((0, 0, 0))  # 全頂点が原点に集まる

``get_positions()`` は保持順の座標列を返します。単体と同じ名前で呼べる
``get_position()`` も複数形では座標列を返します。
``set_position(value)`` は全要素への同じ値の適用、
``set_positions(values)`` は要素ごとの設定です。引数の形による暗黙の切り替えはしません。

* Vertex / Vertices、CV / CVs: XYZ、ws指定、get_x()/set_x()等。
* UV / UVs: UV座標、get_u()/set_u()等。現在のUVセットを参照し、ws指定はありません。
* Edge / Edges、Face / Faces: vertices()で接続頂点を取得できます。
  Edges/Facesの結果は共有頂点の重複を除いたVerticesです。
  位置を変える場合は ``faces.vertices().set_positions(...)`` などを使います。

軸の設定メソッドはスカラーまたは要素数と同じ数値列を受け取ります。
get_x()/set_x()等の軸メソッドはオブジェクト空間、位置メソッドの距離はMayaの現在単位です。
単体の ``full_name()`` に対応する複数形は ``full_names()``、番号は ``indices`` です。
単体に存在しない操作を任意転送する仕組みは使わず、意味が定まる操作を明示的に公開します。

一括編集は1回のUndoにまとまります。件数・非有限座標・コンポーネント番号を
書き込み前に検証します。空コレクションには空の座標列を渡せます。
Mayaが途中の書き込みを拒否した場合は例外を返し、完了済み変更の自動ロールバックはしません。
共有shapeや周期カーブのCVの連動、トポロジー変更後の番号の扱いはMayaの規則に従います。

このページのUndoの説明は通常モード（``fast=False``）を前提とします。
対応する値更新メソッドの ``fast=True`` はUndo対象外です。対応範囲と制限は :doc:`fast_edit` を参照してください。
