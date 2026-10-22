計算ノード
============================================================

計算ノードはMayaシーン内に作成し、入力が変わるとDGが出力を再計算します。
Python内で計算する :doc:`guide_maths` の値型とは用途が異なります。
クラスはすべて ``mlib.nodes`` 直下にあり、Mayaのノード継承に対応します。

対応ノード
------------------------------------------------------------

.. list-table:: 計算と値の変換
   :header-rows: 1
   :widths: 30 70

   * - クラス
     - 操作
   * - MultiplyDivide
     - 成分ごとの乗算・除算・累乗。setOperationで切り替え。
   * - PlusMinusAverage
     - 1D/2D/3D配列の加算・減算・平均。疎な入力番号を維持。
   * - Condition
     - 2つの値を比較し、成立時と不成立時のRGBを切り替え。
   * - Clamp / Reverse
     - 値の上下限への制限 / 各成分の1-input。
   * - SetRange / RemapValue
     - 範囲の線形変換 / ランプによる値・色の変換。
   * - VectorProduct / AngleBetween
     - 内積・外積・座標変換 / ベクトル間の角度・軸・回転。
   * - AddDoubleLinear / MultDoubleLinear
     - 距離型の2入力を加算・乗算。2026/2027ではAddDL / MultDLが返る。
   * - UnitConversion
     - 単位変換ノードの入力・変換係数・出力。
   * - PairBlend
     - 移動・回転のブレンド。Euler/Quaternion補間。

.. list-table:: 行列と形状の評価
   :header-rows: 1
   :widths: 30 70

   * - クラス
     - 操作
   * - ComposeMatrix
     - 移動・Euler回転/Quaternion・スケール・シアーから行列を構築。
   * - InverseMatrix / PickMatrix
     - 逆行列 / 行列の使用成分の選択。
   * - BlendMatrix / AimMatrix
     - ターゲット順の行列ブレンド / 軸をターゲットへ向ける行列。
   * - FourByFourMatrix
     - 16要素の行列をまとめて設定。
   * - CurveInfo
     - カーブ長。
   * - PointOnCurveInfo
     - カーブ上の位置・法線・接線。
   * - PointOnSurfaceInfo
     - サーフェス上の位置・法線・U/V接線。

既存のMultMatrix、DecomposeMatrix、DistanceBetween、BlendWeighted、BlendColorsも利用できます。
アトリビュートの参照・値取得・接続は共通の ``getPlug()`` を基本にします。
入力番号の検証・モード名の変換・複数の値の同時設定など、ノード固有の処理には専用メソッドを使います。

入力・接続・結果
------------------------------------------------------------

標準アトリビュートは ``getPlug("アトリビュート名")`` で取得し、
``get()``・``set()``・``connectTo()`` で値と接続を扱います。
出力アトリビュートの名前はノード型ごとに異なります。
``getResult()`` や ``getOutputPlug()`` を全計算ノード共通の入口とはしません。
Vector等への変換や入力番号の検証があるノードでは、対応する専用メソッドも利用できます。

値設定で既存接続を暗黙に切断しません。接続を置換する場合は ``force=True`` を指定します。
MultiplyDivideなどに残る ``setInput`` は入力番号と有限値を検証します。
一般のPlug設定へ置き換える場合は、こうしたノード固有の検証は行いません。

.. code-block:: python

   import mlib

   multiply = mlib.createNode("multiplyDivide")
   multiply.setOperation("multiply")
   multiply.setInput(1, (2, 3, 4))
   multiply.setInput(2, (10, 10, 10))
   print(tuple(multiply.getPlug("output").get()))  # (20.0, 30.0, 40.0)

   reverse = mlib.createNode("reverse")
   multiply.getPlug("output").connectTo(reverse.getPlug("input"))

setOperationは名前またはMayaの列挙番号を受け付けます。モード名は各APIページに記載しています。
MultiplyDivideのmultiplyとVectorProductのdot/crossは異なる演算です。
AngleBetween.getResult()と回転入力・出力の数値はradです。
AddDoubleLinear/MultDoubleLinear、PairBlendの移動はcmで扱います。
入力値の計算自体はMayaが行い、ゼロ除算などをmlib独自の計算結果に置き換えません。

配列とランプ
------------------------------------------------------------

.. code-block:: python

   total = mlib.createNode("plusMinusAverage")
   total.setOperation("sum")
   total.setInput(2, 10)
   total.setInput(8, 20)
   print(total.getInputIndices())  # [2, 8]
   print(total.getPlug("output1D").get())  # 30.0
   total.setInput(0, (1, 2, 3), dimension=3)
   print(tuple(total.getPlug("output3D").get()))  # (1.0, 2.0, 3.0)

   ramp = mlib.createNode("remapValue")
   ramp.setRange(0, 10, 0, 1)
   ramp.setRampPoint(0, 0.0, 0.0)
   ramp.setRampPoint(1, 1.0, 1.0)
   ramp.setRampPoint(4, 0.5, 0.8, interpolation="smooth")
   ramp.setInput(5)
   print(ramp.getPlug("outValue").get())

``PlusMinusAverage.getInputPlug(index, dimension=1)`` は既存要素のみを参照し、未作成要素はIndexErrorです。
setInput/connectInputで要素を明示的に作成し、removeInputで接続を含めて削除します。
RemapValueは ``getRampPoints()`` で番号ごとのposition/value/interpolationを取得できます。
色ランプの場合はkind="color"とRGBの3要素を渡します。表示色用Colorオブジェクトは使用しません。

行列の構築とブレンド
------------------------------------------------------------

.. code-block:: python

   import math

   compose = mlib.createNode("composeMatrix")
   compose.setTranslate((10, 0, 0))
   compose.setRotate((0, math.radians(45), 0))  # 回転入力はrad
   compose.setScale((1, 1, 1))

   blend = mlib.createNode("blendMatrix")
   blend.connectTarget(0, compose.getOutputPlug(), weight=0.5)
   matrix = blend.getResult()  # mlib.maths.Matrix

ComposeMatrixのQuaternion入力はXYZW順です。setQuaternionの後に
setUseEulerRotation(False)を指定してQuaternion入力へ切り替えます。
BlendMatrixは論理番号順に逐次ブレンドし、ウェイトを正規化する加重平均ではありません。
各ターゲットの成分ウェイトなどはgetTargetPlug(index)の子Plugで設定できます。
AimMatrixはprimary/secondaryそれぞれの入力軸、モード、ターゲット行列・ベクトルを設定できます。

InverseMatrixはMaya付属のmatrixNodesプラグインの型です。
mlibは自動ロードしないため、未ロードなら明示的に読み込みます。

.. code-block:: python

   import maya.cmds as cmds

   cmds.loadPlugin("matrixNodes", quiet=True)
   inverse = mlib.createNode("inverseMatrix")
   inverse.connectInput(compose.getOutputPlug())

カーブ・サーフェス
------------------------------------------------------------

.. code-block:: python

   curve = mlib.createCurve(degree=1, point=[(0, 0, 0), (10, 0, 0)])
   info = mlib.createNode("curveInfo")
   info.connectCurve(curve, ws=True)
   print(info.getPlug("arcLength").get())  # 内部距離単位cm

   point = mlib.createNode("pointOnCurveInfo")
   point.connectCurve(curve)
   point.setParameter(0.5, percentage=True)
   print(point.getPosition())
   print(point.getTangent())

connectCurve/connectSurfaceは既定でworldSpaceを接続し、インスタンス番号を保持します。
ws=Falseはlocalを接続します。Transformに対応シェイプが複数ある場合は、
対象シェイプを明示してください。評価結果は接続されたデータの空間に従います。
PointOnSurfaceInfoはsetParameters(u, v, percentage=True)でUV位置を指定できます。

Undoとバージョン差
------------------------------------------------------------

通常の更新はメソッドごとにUndoをまとめます。``fast`` 引数を持つメソッドは
``fast=True`` でUndoなしのOpenMaya更新を選べます。
``Plug.set()``・``Plug.connectTo()`` も対応します。配列・ランプの専用編集など、
``fast`` 引数のないメソッドは通常のUndo対応処理を使用します。
途中のエラーで更新済みの箇所を自動ロールバックするものではありません。
対応範囲と制限は :doc:`fast_edit` を参照してください。

Maya 2026/2027では旧nodeTypeのaddDoubleLinear/multDoubleLinearを指定すると、
MayaがaddDL/multDLを作成します。mlibも実型に対応するAddDL/MultDLを返します。
両組のクラスは同じ便利メソッドを持ち、Mayaの実型にない継承・互換別名は追加していません。
AddDL/MultDLを直接作成できるかは、使用中のMayaの対応型に依存します。
