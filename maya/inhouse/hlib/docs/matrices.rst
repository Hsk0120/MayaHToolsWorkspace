行列の取得と計算
================

ノードの位置・回転・スケールをまとめて扱うときは、
:class:`~hlib.maths.matrix.Matrix` を使います。
ここでは、取得した値を確認しながら、座標変換とノードへの適用までを説明します。
API の引数や戻り値の詳細は、各メソッドのリンク先を参照してください。

ノードから行列を取得する
------------------------

以下の例は Maya 上で上から順番に実行できます。
新しい transform を作成します。距離単位 cm、角度単位 deg の環境を想定しています。

.. code-block:: python

   import math
   import hlib
   from hlib.maths import Matrix

   parent = hlib.createNode("transform", name="matrixGuideParent")
   child = hlib.createNode("transform", name="matrixGuideChild")
   child.set_parent(parent, relative=True)
   parent.set_translate((10, 0, 0))
   child.set_translate((2, 3, 0))

   local = child.get_matrix()
   world = child.get_matrix(ws=True)
   print(tuple(local.translate))    # (2.0, 3.0, 0.0)
   print(tuple(world.translate))    # (12.0, 3.0, 0.0)

:meth:`~hlib.nodes.transform.Transform.get_matrix` は、既定でローカル行列、
``ws=True`` でワールド行列を返します。戻り値は数値リストではなく ``Matrix`` です。
既存ノードの場合も、``child = hlib.node("ノード名")`` で取得して同じ操作ができます。

プラグから取得する
------------------

同じ値を、ノードのアトリビュートを扱う ``Plug`` から取得できます。
``worldMatrix`` は配列なので、要素を指定します。

.. code-block:: python

   local_from_plug = child.plug("matrix").get()
   world_from_plug = child.plug("worldMatrix").element(0, create=True).get()
   print(local.is_equivalent(local_from_plug))    # True
   print(world.is_equivalent(world_from_plug))    # True

現在の ``get_matrix(ws=True)`` は ``worldMatrix[0]`` を参照します。
DAG インスタンスの別経路に対応する行列が必要なら、その経路のインスタンス番号を
確認して配列要素を指定してください。

行列を作成し、成分を読む
------------------------

``Matrix()`` は単位行列です。成分を指定すると変換行列を作成できます。
回転の3成分は **XYZ 順・ラジアン** です。度からは ``math.radians()`` で変換します。

.. code-block:: python

   identity = Matrix()
   matrix = Matrix.compose(
       translate=(4, 5, 6),
       rotate=(0, 0, math.radians(90)),
       scale=(2, 2, 2),
   )
   print(tuple(matrix.translate))    # (4.0, 5.0, 6.0)
   print(tuple(matrix.scale))        # (2.0, 2.0, 2.0)
   print(tuple(round(math.degrees(v), 6) for v in matrix.euler))
   # (0.0, 0.0, 90.0)（丸め前は微小な誤差を含むことがある）
   parts = matrix.decompose()
   print(parts["translate"])
   print(parts["quaternion"])
   print(matrix.rows)                # 4行4列
   print(matrix.values)              # 行優先の16要素

平行移動は16要素の添字12・13・14に入ります。
``Matrix(values)`` で16要素、4行4列、または別の ``Matrix`` からコピーできます。
``values`` を指定した場合、同時に渡した ``translate`` などの成分引数は無視されます。

``Matrix.decompose()`` は成分辞書を返します。
一方、``node.decompose(ws=True)`` は ``Matrix`` を返すため、両者は戻り値が異なります。
回転の分解結果は元のオイラー角の数値と必ずしも一致しません。
XYZ 以外の ``EulerRotation`` の回転順序は、3成分として渡すと引き継がれません。
その回転順序を保って合成する場合は、``rotate=euler.to_quaternion()`` と指定します。

行列の積と逆行列
----------------

hlib は Maya と同じ行ベクトル規約です。
``A * B`` は、点に対して **A、次に B** の順で変換する行列です。
``A @ B`` も同じ行列積になります。掛ける順序を交換すると、一般には結果が変わります。

.. code-block:: python

   move = Matrix(translate=(2, 0, 0))
   turn = Matrix(rotate=(0, 0, math.radians(90)))
   moved_then_turned = (move * turn).transform_point((0, 0, 0))
   turned_then_moved = (turn * move).transform_point((0, 0, 0))
   print(tuple(round(v, 6) for v in moved_then_turned))   # (0.0, 2.0, 0.0)
   print(tuple(round(v, 6) for v in turned_then_moved))   # (2.0, 0.0, 0.0)
   print((matrix * matrix.inverse()).is_equivalent(Matrix()))  # True

逆行列は変換を戻すために使います。``inverse()`` は元の行列を変更せず、
新しい行列を返します。ゼロスケールなど逆行列を持たない場合は ``ValueError`` になります。
表示上の ``-0.0`` は ``0.0`` と同じ値です。
計算後の比較には、完全一致の ``==`` より、誤差を許容する ``is_equivalent()`` を使います。

ローカルとワールドを変換する
----------------------------

通常の親子関係では、``world = local * parent_world`` です。
ワールド行列から親を基準とした行列を求める場合は、親の逆行列を右から掛けます。
この例は ``inheritsTransform=True``、``offsetParentMatrix`` が単位行列の transform を対象にしています。

.. code-block:: python

   parent_world = parent.get_matrix(ws=True)
   calculated_world = local * parent_world
   calculated_local = world * parent_world.inverse()
   print(calculated_world.is_equivalent(world))    # True
   print(calculated_local.is_equivalent(local))    # True

同じ考え方で、任意の基準ノードから見た相対行列を求められます。
例えば ``child_world * reference_world.inverse()`` は、reference の座標系で表した child の行列です。
ワールドへ戻すときは、その相対行列に ``reference_world`` を右から掛けます。

位置と方向を変換する
--------------------

位置には ``transform_point()``、方向には ``transform_vector()`` を使います。
位置には平行移動が加わり、方向には加わりません。方向にも回転・スケール・シアーは作用します。

.. code-block:: python

   point = matrix.transform_point((1, 0, 0))
   direction = matrix.transform_vector((1, 0, 0))
   print(tuple(round(v, 6) for v in point))       # (4.0, 7.0, 6.0)
   print(tuple(round(v, 6) for v in direction))   # (0.0, 2.0, 0.0)
   restored = matrix.inverse().transform_point(point)
   print(tuple(round(v, 6) for v in restored))    # (1.0, 0.0, 0.0)

戻り値は、それぞれ ``Translation`` と ``Vector`` です。
方向の長さが不要な場合は ``direction.normalized()`` で単位ベクトルにできます。
これは法線専用の変換ではありません。非一様スケール下の法線変換とは区別してください。

計算結果をノードへ適用する
--------------------------

取得した ``Matrix`` は、その時点の値を保持したオブジェクトです。
成分を書き換えるだけではシーンは変わりません。
:meth:`~hlib.nodes.transform.Transform.set_matrix` で明示的に適用します。

.. code-block:: python

   target = hlib.createNode("transform", name="matrixGuideTarget")
   target.set_parent(parent, relative=True)
   edited = Matrix(world)
   edited.translate = (20, 4, 0)
   target.set_matrix(edited, ws=True)
   print(tuple(target.get_translate(ws=True)))   # (20.0, 4.0, 0.0)
   print(tuple(target.get_translate()))          # (10.0, 4.0, 0.0)
   print(tuple(world.translate))                 # (12.0, 3.0, 0.0) コピー元は不変

``set_matrix()`` は既定ではローカル空間、``ws=True`` ではワールド空間への適用です。
処理内で Undo チャンクをまとめています。通常の呼び出しを外側から囲む必要はありません。
また、これは値のコピーであり、ノード間の接続や追従関係を作る操作ではありません。

現在の実装は、行列を分解して translate・rotate・scale・shear に書き込みます。
適用例は、回転順序 XYZ、ピボットと rotateAxis が既定値、offsetParentMatrix が単位行列、
inheritsTransform が有効な通常の transform を想定しています。
jointOrient や特殊なピボット、異なる回転順序などの補正は行いません。
取得できた行列を、あらゆるノードへそのまま再現できるわけではありません。

Maya API の行列と相互変換する
----------------------------------------

.. code-block:: python

   api_matrix = matrix.to_mmatrix()
   copied = Matrix.from_mmatrix(api_matrix)
   print(copied.is_equivalent(matrix))    # True

``to_transformation()`` / ``from_transformation()`` で
Maya API 2.0 の ``MTransformationMatrix`` とも相互変換できます。
これらは値の変換であり、シーンの変更は行いません。

関連ページ
----------

* :class:`~hlib.maths.matrix.Matrix` — 合成・分解・積・逆行列の API
* :class:`~hlib.nodes.transform.Transform` — ノードからの取得と適用
* `cymel入門のMatrix解説 <https://ryusas.github.io/cymel/ja/gettingstarted.html#matrix>`_ — 説明構成の参考。上記の使用例は hlib の実装に合わせています。

このページのUndoの説明は通常モード（``fast=False``）を前提とします。
対応する値更新メソッドの ``fast=True`` はUndo対象外です。対応範囲と制限は :doc:`fast_edit` を参照してください。
