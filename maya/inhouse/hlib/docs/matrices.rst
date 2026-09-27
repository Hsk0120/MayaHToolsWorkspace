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
``Matrix`` は OpenMaya API 2.0 の ``om2.MMatrix`` を継承しているため、
``om2.MTransformationMatrix(local)`` のように om2 の関数へそのまま渡せます。
既存ノードの場合も、``child = hlib.node("ノード名")`` で取得して同じ操作ができます。

プラグから取得する
------------------

``MatrixPlug.set()`` は従来通り、所有ノードがtransform/jointならTRS更新へ委譲します。
``offsetParentMatrix`` や独自の行列属性へ、TRSを変更せずに値だけを書き込む場合は
``plug.set_value(matrix)`` を使用してください。通常モードではUndo可能です。

同じ値を、ノードのアトリビュートを扱う ``Plug`` から取得できます。
``worldMatrix`` は配列なので、要素を指定します。

.. code-block:: python

   local_from_plug = child.plug("matrix").get()
   world_from_plug = child.plug("worldMatrix").element(0, create=True).get()
   print(local.is_equivalent(local_from_plug))    # True
   print(world.is_equivalent(world_from_plug))    # True

``get_matrix(ws=True)`` は、ラッパーの ``dag_path()`` が示す DAG インスタンスの
``worldMatrix`` の要素(``worldMatrix[<インスタンス番号>]``)を参照します。
プラグから別のインスタンスの行列を取得する場合は、その経路のインスタンス番号
(``dag_path().instanceNumber()``)を要素に指定してください。

行列を作成し、成分を読む
------------------------

``Matrix()`` は単位行列です。成分を指定すると変換行列を作成できます。
回転の3成分は **XYZ 順・ラジアン** です。度からは ``math.radians()`` で変換します。
``rotate`` には ``EulerRotation`` (その回転順序を反映)や ``Quaternion`` も渡せます。

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
   # (0.0, -0.0, 90.0)（丸め前は微小な誤差を含み、-0.0 と表示されることがある）
   parts = matrix.decompose()
   print(parts["translate"])
   print(parts["quaternion"])
   print(matrix.rows)                # 4行4列
   print(matrix.values)              # 行優先の16要素

平行移動は16要素の添字12・13・14に入ります。
``Matrix(values)`` で16要素、4行4列、``om2.MMatrix``、または別の ``Matrix`` からコピーできます。
``values`` を指定した場合、同時に渡した ``translate`` などの成分引数は無視されます。
``matrix[3, 0]`` のように (行, 列) でも要素を読み書きできます。

``Matrix.decompose()`` は成分辞書を返します。
一方、``node.decompose(ws=True)`` は ``Matrix`` を返すため、両者は戻り値が異なります。
分解は ``om2.MTransformationMatrix`` と同じ規約です。回転の分解結果(``euler`` は XYZ 順序)は
元のオイラー角の数値と必ずしも一致せず、中間軸が 90 度を超える等価な角度になることがあります。
行列式が負(奇数個の負スケール)の行列は、Z スケールを負にし、回転側で 180 度を補って
分解します(``cmds.xform`` や decomposeMatrix ノードと同じ)。
``EulerRotation`` を ``rotate`` に渡すと、その回転順序のまま合成します
(3成分の tuple は XYZ 順序として扱います)。

.. code-block:: python

   from hlib.maths import EulerRotation

   zyx = EulerRotation.from_degrees(30, 45, 60, "zyx")
   print(Matrix(rotate=zyx).is_equivalent(zyx.to_matrix()))    # True

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
新しい行列を返します。ゼロスケールなど逆行列を持たない(``om2.MMatrix.isSingular()``
が真の)場合は ``ValueError`` になります。非常に小さいが 0 ではないスケールの行列は
逆行列を計算できます。
表示上の ``-0.0`` は ``0.0`` と同じ値です。
計算後の比較には、完全一致の ``==`` より、誤差を許容する ``is_equivalent()`` を使います。
``*`` / ``@`` の相手に ``om2.MMatrix`` を使った場合も、結果は ``Matrix`` です。

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

演算子を使う場合は om2 と同じ規約です。``Vector(1, 0, 0) * matrix`` は
``transform_vector()`` と同じ方向の変換で、位置は ``om2.MPoint(1, 0, 0) * matrix`` で
変換できます(om2 の値が左辺なので結果は ``om2.MPoint`` です)。``matrix * vector`` は
om2 と同じ列ベクトルとしての積(転置行列での変換)で、``transform_point()`` とは結果が
異なります。右辺が ``om2.MVector`` / ``om2.MPoint`` でも結果は ``Vector`` です
(``om2.MPoint`` の場合は同次座標の積の x、y、z で、w は捨てます)。``matrix @ vector`` は
``TypeError`` です。演算結果が hlib の型になる規則と例外は :ref:`maths-result-types` を
参照してください。

.. code-block:: python

   import maya.api.OpenMaya as om2
   from hlib.maths import Vector

   print((Vector(1, 0, 0) * matrix).is_equivalent(direction))           # True
   print((om2.MPoint(1, 0, 0) * matrix).isEquivalent(om2.MPoint(point)))  # True

計算結果をノードへ適用する
--------------------------

取得した ``Matrix`` は、その時点の値を保持したオブジェクトです。
成分を書き換えるだけではシーンは変わりません。
:meth:`~hlib.nodes.transform.Transform.set_matrix` で明示的に適用します。

``Matrix`` は可変で、``translate`` などのプロパティへの代入や ``*=`` は同じオブジェクトを
書き換えます。別の変数から参照している場合はその値も変わるため、元の値を残したいときは
``Matrix(world)`` や ``copy.copy(world)`` で複製してから編集します。
一方、``matrix.translate`` などが返す成分は複製なので、``matrix.translate.x = 1`` と
書いても行列は変わりません(``matrix.translate = (1, y, z)`` と代入します)。

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

現在の実装は、行列を ``om2.MTransformationMatrix`` と同じ規約で分解して
translate・rotate・scale・shear に書き込みます。ただし同じ行列になる候補のうち、
現在のチャンネル値に近いものを選びます。

* スケールの符号の組み合わせは、行列式の符号が許す限り現在の scale チャンネルに揃えます
  (2軸の符号の反転を、残りの軸まわりの 180 度回転で補います)。scale が (-1, 1, 1) の
  ミラーのノードは、``set_translate`` や ``set_matrix(node.get_matrix())`` の後も
  (-1, 1, 1) のままで、rotate も変わりません。
* ``set_scale(value)`` (``plug("scale").set(value)`` も同じ)では、要求した value の符号を
  最優先します。ローカル空間では value がそのまま scale に入り、rotate は変わりません
  (``cmds.setAttr`` で scale だけを書いた場合と同じ)。
* 回転はノードの rotateOrder で表し、等価な解のうち現在の rotate チャンネル値に最も近いもの
  (``om2.MEulerRotation.closestSolution``)を書き込みます。

現在の scale チャンネルの符号と行列式の符号が合わない場合は、om2 の規約(Z スケールが負)で
書き込みます。例えば scale が (1, 1, 1) のノードへ ``set_matrix(Matrix(scale=(-1, 1, 1)))`` を
適用すると、scale は (1, 1, -1)、rotate は (0, 180, 0) になります(行列は同じ)。
特定の軸を負にしたい場合は ``set_scale`` を使ってください。
``cmds.xform(matrix=...)`` は常に om2 の規約(Z スケールが負)で書き込むため、負スケールの
ノードや Euler の別解では、結果の行列は同じでもチャンネル値が異なることがあります。
``get_scale`` / ``get_shear`` / ``get_quaternion`` / ``get_rotate`` も同じ規約で分解するため、
``node.set_scale(node.get_scale())`` のような往復でチャンネル値は変わりません
(``Matrix`` の ``scale`` などは常に om2 の規約です)。
``get_rotate`` / ``set_rotate`` の3成分は ``cmds.xform(rotation=...)`` と同じく
ノードの rotateOrder の値で、戻り値の ``EulerRotation`` の order もノードの回転順序です。
回転を XYZ 順序で取得する場合は ``get_euler`` を使います。

joint は jointOrient と rotateAxis を保ったまま rotate を求め、segmentScaleCompensate が
有効な場合は inverseScale による補正を除いてから分解します。
適用例は、ピボットと rotateAxis(transform の場合)が既定値、offsetParentMatrix が単位行列、
inheritsTransform が有効な通常の transform を想定しています。
特殊なピボットや transform の rotateAxis の補正は行いません。
取得できた行列を、あらゆるノードへそのまま再現できるわけではありません。

Maya API の行列と相互変換する
----------------------------------------

``Matrix`` は ``om2.MMatrix`` の派生なので、om2 の関数へは変換せずにそのまま渡せます。
om2 の関数が返した ``om2.MMatrix`` は ``Matrix.from_mmatrix()`` で ``Matrix`` にできます。

.. code-block:: python

   transformation = om2.MTransformationMatrix(matrix)   # そのまま渡せる
   copied = Matrix.from_mmatrix(transformation.asMatrix())
   print(copied.is_equivalent(matrix))    # True
   api_matrix = matrix.to_mmatrix()       # 素の om2.MMatrix の複製(互換用)

``to_transformation()`` / ``from_transformation()`` で
Maya API 2.0 の ``MTransformationMatrix`` とも相互変換できます。
これらは値の変換であり、シーンの変更は行いません。
om2 名のメソッド(``adjoint()``、``homogenize()`` など)の戻り値は ``om2.MMatrix`` です。

関連ページ
----------

* :class:`~hlib.maths.matrix.Matrix` — 合成・分解・積・逆行列の API
* :class:`~hlib.nodes.transform.Transform` — ノードからの取得と適用
* `cymel入門のMatrix解説 <https://ryusas.github.io/cymel/ja/gettingstarted.html#matrix>`_ — 説明構成の参考。上記の使用例は hlib の実装に合わせています。

このページのUndoの説明は通常モード（``fast=False``）を前提とします。
対応する値更新メソッドの ``fast=True`` はUndo対象外です。対応範囲と制限は :doc:`fast_edit` を参照してください。
