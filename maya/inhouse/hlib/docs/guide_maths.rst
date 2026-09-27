ベクトルと回転・数学型
============================================================

Vector・Quaternion・EulerRotationなどの値を使った計算を説明します。

例は Maya の Script Editor で実行します。既存ノード名は使用するシーンに合わせてください。
最初に ``import hlib`` を実行してください。

OpenMaya の型を継承した値
-------------------------

``hlib.maths`` の型は、OpenMaya API 2.0(``maya.api.OpenMaya``、以下 om2)の型を
継承しています。hlib の値をそのまま om2 の関数やコンストラクタへ渡せ、計算は om2 の
C++ 実装で行われます。

.. list-table::
   :header-rows: 1

   * - hlib の型
     - 継承元
   * - ``Vector`` / ``Translation`` / ``Scale`` / ``Shear``
     - ``om2.MVector``
   * - ``Quaternion``
     - ``om2.MQuaternion``
   * - ``EulerRotation``
     - ``om2.MEulerRotation`` (``Vector`` の派生ではありません)
   * - ``Matrix``
     - ``om2.MMatrix``

.. code-block:: python

   import maya.api.OpenMaya as om2
   from hlib.maths import Matrix, Translation

   matrix = Matrix(translate=(1, 2, 3))
   transformation = om2.MTransformationMatrix(matrix)   # 変換せずに渡せる
   data = om2.MFnMatrixData().create(matrix)
   point = om2.MPoint(Translation(1, 2, 3))

演算子と om2 名(``normal``、``asMatrix``、``rotateBy`` などの camelCase)のメソッドは
om2 と同じ意味です。演算子の結果は hlib の型で返りますが、om2 名のメソッドは om2 の
基底型(``om2.MVector`` など)を返します。hlib の型が必要なときは、同じ働きを持つ
snake_case のメソッド(``normalized``、``to_matrix`` など)を使ってください。
``hlib.maths`` の import には Maya(mayapy または Maya 本体)が必要です。
``hlib.maths.easing`` だけは標準ライブラリの ``math`` のみを使う関数群です。

ベクトル
--------

.. code-block:: python

   from hlib.maths import Vector

   result = Vector(1, 2, 3) + Vector(4, 5, 6)
   print(tuple(result))  # (5.0, 7.0, 9.0)

   x = Vector(1, 0, 0)
   y = Vector(0, 1, 0)
   x.dot(y)                  # 0.0(x * y と同じ内積)
   tuple(x.cross(y))         # (0.0, 0.0, 1.0)(x ^ y と同じ外積)
   Vector(3, 4, 0).length()  # 5.0
   tuple(Vector(0, 0, 5).normalized())  # (0.0, 0.0, 1.0)

``dot``/``cross``/``length``/``normalized`` は ``Translation``/``Scale``/``Shear``
など ``Vector`` を継承する型で使用できます。``cross``/``normalized`` や演算子の戻り値は
派生クラスの型を保持せず常に ``Vector`` になります。
``normalized()`` はゼロベクトルに対して ``ValueError`` を送出します
(om2 の ``normal()`` はゼロベクトルでも例外にせず ``om2.MVector`` を返します)。

.. code-block:: python

   a = Vector(1, 0, 0)
   b = Vector(0, 1, 0)

   -a                        # Vector(-1.0, -0.0, -0.0)
   Vector(2, 4, 6) / 2        # Vector(1.0, 2.0, 3.0)(0 で割ると ZeroDivisionError)
   a * b                     # 0.0(om2 と同じく Vector 同士の * は内積)
   a ^ b                     # Vector(0.0, 0.0, 1.0)(外積)
   a.length_squared()        # 1.0（sqrt を省ける length() の2乗版）
   a.distance_to(b)          # 1.4142...（2点間のユークリッド距離）
   a.angle_to(b)             # 1.5707...（ラジアン。0〜piの範囲）
   a.is_equivalent(Vector(1 + 1e-12, 0, 0))  # True（距離が許容誤差以内か）
   a.lerp(b, 0.5)             # Vector(0.5, 0.5, 0.0)（線形補間。t<0/t>1は外挿）

``Vector()`` はゼロベクトル、``Vector(x, y)`` は z=0、``Vector([x, y, z])`` や
``Vector(om2.MPoint(...))`` も使えます(om2 のコンストラクタと同じ)。
``Vector(x=1, z=3)`` のようなキーワード引数も使え、省略した成分は 0 です
(``Quaternion`` は ``x``/``y``/``z``/``w``、省略時は単位四元数の値。``EulerRotation`` は
``x``/``y``/``z``/``order``)。成分は数値だけで、``Vector("1", "2", "3")`` のような文字列は
om2 と同じく ``ValueError`` です。

添字は ``-3`` 〜 ``2`` (``Quaternion`` は ``-4`` 〜 ``3``、``Matrix`` は ``-16`` 〜 ``15``)の
整数で、範囲外は負の値も含めて ``IndexError`` です(om2 の型は ``v[-4]`` でも最後の成分を
返しますが、hlib は検査します)。スライス ``v[0:2]`` は成分の ``tuple`` を返します
(スライスへの代入はできません)。

値の比較・変更・複製
--------------------

値は om2 と同じく **可変** です。成分や添字へ代入でき、``+=`` / ``-=`` / ``*=`` / ``/=`` は
同じオブジェクトを書き換えて型を保ちます(om2 に in-place 版が無い ``Vector`` の ``^=``、
``Quaternion`` の ``+=`` / ``-=``、``Matrix`` の ``@=`` も hlib で in-place にしています)。
ただし om2 と同じく結果の型が変わる演算は、名前を新しい値へ束ね直します
(``v *= w`` は内積の ``float``、``m *= v`` は列ベクトルとしての積の ``Vector``)。
ハッシュは使えないため、``dict`` のキーや ``set`` の要素にはできません。

.. code-block:: python

   v = Vector(1, 2, 3)
   alias = v
   v += Vector(1, 1, 1)      # v と alias は同じオブジェクトなので両方が変わる
   v.x = 10.0
   copied = Vector(v)         # 別の値として持つ場合は複製する(copy.copy も可)

``==`` は om2 と同じく成分の完全一致です。同じ om2 の型の系統であれば、派生型が
違っても等しくなり得ます(``Translation(1, 2, 3) == Scale(1, 2, 3)`` は ``True``)。
系統の違う値との比較は例外になりません。``om2.MPoint`` など系統の違う om2 の型とは
``False`` です。それ以外(``None``、文字列、tuple など)は相手側の比較に判断を委ね
(Python の ``NotImplemented``)、相手も判断しなければ ``False`` になります。
ただし **om2 の型が左辺** の比較(``om2.MPoint() == Vector()``、
``om2.MVector() == Quaternion()`` など)は om2 側が ``TypeError`` を送出し、hlib では
防げません。浮動小数点誤差を許容する場合は ``is_equivalent`` を使ってください。

``copy.copy`` / ``copy.deepcopy`` / ``pickle`` は型と値を保ったまま複製できます。
利用者が定義した派生クラスでは、``__dict__`` や ``__slots__`` に追加した属性も複製され、
独自の引数を取る ``__init__`` を定義していても複製時には呼ばれません。
om2 の型は C++ の実体をコンストラクタ(``__init__``)で確保するため、om2 の型を
``__new__`` だけで作るとアクセス時に Maya ごと落ちますが、hlib の型は ``__new__`` の
時点で確保するため落ちません。以前の hlib(dataclass 版)で作った pickle は読み込めません。

四元数
------

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

   axis, angle = q.to_axis_angle()     # (Vector, float) へ分解。角度は 0〜pi
   Quaternion.from_axis_angle(axis, angle)  # 軸・角度から逆生成
   Quaternion(angle, axis)                  # om2 の軸角コンストラクタ(axis は Vector)

``rotate_vector``/``slerp``/``angle_to`` は正規化した回転として扱います。
``inverse`` は共役を長さの二乗で割った逆四元数を返し、長さを1には揃えません。
ゼロ四元数では ``normalized``/``inverse`` が ``ValueError`` を送出します。

積 ``q1 * q2`` は om2 と同じ順序で、**q1 を先に適用してから q2** を適用する回転です
(``q1.to_matrix() * q2.to_matrix()`` と同じ回転。Hamilton 積では ``q2 ⊗ q1``)。
``to_swing_twist(axis)`` が返す ``(swing, twist)`` は、``twist * swing`` で元の回転に
戻ります。``2 * q`` は om2 と同じく4成分のスカラー倍(正規化しない)で、om2 と同じく
``q * 2`` と ``q / 2`` には対応しません。

``to_euler(order)`` と ``Matrix`` の ``euler`` / ``rotation`` / ``decompose()`` は om2
(``MEulerRotation.decompose`` / ``MTransformationMatrix``)の解を返します。等価な解のうち
中間軸が 90 度を超える側になることがあります(``cmds.xform(matrix=...)`` で書き込まれる
チャンネル値と同じ解)。値そのものではなく回転を比べる場合は、``to_quaternion()`` や
``to_matrix()`` の ``is_equivalent`` を使ってください。

オイラー回転
------------

``EulerRotation`` は内部値がラジアンで、表示(``repr``)は度です。回転順序 ``order`` は
om2 と同じ整数(``kXYZ``\ =0、``kYZX``\ =1、``kZXY``\ =2、``kXZY``\ =3、``kYXZ``\ =4、
``kZYX``\ =5。Maya の rotateOrder 属性と同じ番号)で、名前は ``order_name`` で
取得・設定します。コンストラクタの order には名前と番号のどちらも使えます。

.. code-block:: python

   euler = EulerRotation(0.1, 0.2, 0.3, "zyx")
   euler.order          # 5
   euler.order_name     # 'zyx'
   euler.order_name = "xyz"   # 成分は並べ替えない(並べ替えは om2 の reorder())
   euler.to_quaternion()      # 回転順序を反映した Quaternion
   euler.to_matrix()          # 回転順序を反映した Matrix

``==`` は回転順序を含めた成分の比較です。``+`` / ``-`` / ``*`` は om2 の Euler の演算
(順序の違う値は左辺の順序へ変換して計算、``*`` は数値ならスケール、回転なら合成)です。
om2 に無い ``2 * euler`` と ``euler / 2`` (成分ごとの除算。順序は保つ)も使えます。
``Vector`` の派生ではないため、``dot`` / ``cross`` / ``length`` / ``normalized`` /
``distance_to`` / ``angle_to`` / ``lerp`` はありません。

行列
----

.. code-block:: python

   from hlib.maths import Matrix

   Matrix.identity()          # Matrix() と同じ単位行列
   m = Matrix(translate=(1, 2, 3), scale=(2, 3, 4))
   m.determinant()            # 24.0（スケールの体積比。平行移動は影響しない）
   m.is_equivalent(m)         # True（許容誤差付き等価判定。__eq__ は完全一致のみ）
   m @ Matrix(scale=(2, 2, 2))  # m * Matrix(...) と同じ行列積(@ は行列同士だけ)

   v = Vector(1, 0, 0)
   v * m                      # 行ベクトル規約の方向変換(平行移動を含まない)
   m * v                      # om2 と同じ列ベクトルとしての積(v * m の転置版)
   m.transform_point(v)       # 位置の変換(平行移動を含む)。om2.MPoint(v) * m と同じ位置

``m * v`` は ``m.transform_point(v)`` ではありません。位置は ``transform_point()``、
方向は ``transform_vector()`` か ``v * m`` を使ってください。

行列の取得・座標変換・ノードへの適用は :doc:`matrices` を参照してください。
