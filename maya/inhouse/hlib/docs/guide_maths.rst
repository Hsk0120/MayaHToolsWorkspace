ベクトルと回転・数学型
============================================================

Vector・Quaternion・EulerRotationなどの値を使った計算を説明します。

例は Maya の Script Editor で実行します。既存ノード名は使用するシーンに合わせてください。
最初に ``import hlib`` を実行してください。

数学型
------

.. code-block:: python

   from hlib.maths import Vector

   result = Vector(1, 2, 3) + Vector(4, 5, 6)
   print(tuple(result))  # (5.0, 7.0, 9.0)

   x = Vector(1, 0, 0)
   y = Vector(0, 1, 0)
   x.dot(y)                  # 0.0
   tuple(x.cross(y))         # (0.0, 0.0, 1.0)
   Vector(3, 4, 0).length()  # 5.0
   tuple(Vector(0, 0, 5).normalized())  # (0.0, 0.0, 1.0)

``dot``/``cross``/``length``/``normalized`` は ``Translate``/``Rotate``/``Scale``/``Shear``
など ``Vector`` を継承する全ての型で使用できます。``cross``/``normalized`` の戻り値は
派生クラスの型を保持せず常に ``Vector`` になります(``__add__``/``__sub__`` と同様)。
``normalized()`` はゼロベクトルに対して ``ValueError`` を送出します。

.. code-block:: python

   a = Vector(1, 0, 0)
   b = Vector(0, 1, 0)

   -a                        # Vector(-1.0, -0.0, -0.0)
   Vector(2, 4, 6) / 2        # Vector(1.0, 2.0, 3.0)
   a.length_squared()        # 1.0（sqrt を省ける length() の2乗版）
   a.distance_to(b)          # 1.4142...（2点間のユークリッド距離）
   a.angle_to(b)             # 1.5707...（ラジアン。0〜piの範囲）
   a.is_equivalent(Vector(1 + 1e-12, 0, 0))  # True（許容誤差付き等価判定）
   a.lerp(b, 0.5)             # Vector(0.5, 0.5, 0.0)（線形補間。t<0/t>1は外挿）

``__eq__`` は dataclass が生成する完全一致（かつ同一クラス同士）の比較のため、
浮動小数点誤差を許容する場合は ``is_equivalent`` を使ってください。

.. code-block:: python

   from hlib.maths import Quaternion, EulerRotation

   rotation = EulerRotation.from_degrees(0, 90, 0)   # as_degrees() の逆
   q = rotation.to_quaternion()

   q.conjugate()              # XYZ の符号を反転
   q.inverse()                # 逆四元数（単位四元数なら conjugate と同じ）
   q.dot(q)                   # 1.0（正規化済みなら常に1）
   q.length()                 # 1.0
   q.rotate_vector(Vector(1, 0, 0))    # このQuaternionでベクトルを回転
   q.angle_to(Quaternion())            # 単位四元数との角度差（ラジアン）

   identity = Quaternion()
   halfway = identity.slerp(q, 0.5)    # 球面線形補間（最短経路で補間）

   axis, angle = q.to_axis_angle()     # (Vector, float) へ分解
   Quaternion.from_axis_angle(axis, angle)  # 軸・角度から逆生成

``rotate_vector``/``slerp``/``angle_to``/``inverse`` はいずれも呼び出し前に自身を
正規化するため、正規化していない四元数を渡してもスケールの影響は受けません。

.. code-block:: python

   from hlib.maths import Matrix

   Matrix.identity()          # Matrix() と同じ単位行列
   m = Matrix(translate=(1, 2, 3), scale=(2, 3, 4))
   m.determinant()            # 24.0（スケールの体積比。平行移動は影響しない）
   m.is_equivalent(m)         # True（許容誤差付き等価判定。__eq__ は完全一致のみ）
   m @ Matrix(scale=(2, 2, 2))  # __mul__ と同じ（numpy に倣った @ 演算子）

``maths`` の実装は Maya に依存しません。ただし通常の
``from hlib.maths import ...`` は親パッケージ ``hlib`` の初期化を通るため、
この import には Maya 環境が必要です。

行列の取得・座標変換・ノードへの適用は :doc:`matrices` を参照してください。
