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
     - 成分ごとの乗算・除算・累乗。operationアトリビュートで選択。
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
AddDL、AddDoubleLinear、BlendColors、BlendWeighted、Clamp、Condition、MultDL、
MultDoubleLinear、MultiplyDivide、PlusMinusAverage、RemapValue、Reverse、SetRange、
UnitConversionの14型は型登録とNodeの共通操作だけを持ちます。
専用の入力・範囲・ランプ・結果メソッドは提供しません。
行列・TRSや、上記14型以外に残る専用操作は各クラスのAPIを参照してください。

入力・接続・結果
------------------------------------------------------------

標準アトリビュートは ``getPlug("アトリビュート名")`` で取得し、
``get()``・``set()``・``connectTo()`` で値と接続を扱います。
出力アトリビュートの名前はノード型ごとに異なります。
14型の出力もMaya標準名で取得します。operationの列挙番号、入力アトリビュート名、
配列の論理番号は利用側が明示します。以前の専用メソッドによる番号・有限値の検証、
列挙名の変換、結果のVector化は提供しません。値・返却型・例外は各Plugの仕様に従います。

値設定で既存接続を暗黙に切断しません。接続を置換する場合は ``force=True`` を指定します。
複数のアトリビュート編集を1回のUndoへまとめる場合は、利用側で ``undoChunk`` を使います。

.. code-block:: python

   import mlib
   from mlib.decorator import undoChunk

   multiply = mlib.createNode("multiplyDivide")
   with undoChunk("multiplyInputs"):
       multiply.getPlug("operation").set(1)  # MayaのMultiply
       multiply.getPlug("input1").set((2, 3, 4))
       multiply.getPlug("input2").set((10, 10, 10))
   print(tuple(multiply.getPlug("output").get()))  # (20.0, 30.0, 40.0)

   reverse = mlib.createNode("reverse")
   multiply.getPlug("output").connectTo(reverse.getPlug("input"))

operationの番号はMayaのノード型ごとに定義されています。
MultiplyDivideの乗算とVectorProductの内積・外積は異なる演算です。
AngleBetweenの角度・回転入力と出力はrad、AddDoubleLinear/MultDoubleLinearや
PairBlendの移動はcmで扱います。UI単位が必要な場合はPlugの ``uiUnits=True`` を使います。
計算自体はMayaが行い、ゼロ除算などをmlib独自の計算結果に置き換えません。

配列とランプ
------------------------------------------------------------

.. code-block:: python

   total = mlib.createNode("plusMinusAverage")
   inputs = total.getPlug("input1D")
   with undoChunk("sumInputs"):
       total.getPlug("operation").set(1)  # MayaのSum
       inputs[2].set(10)
       inputs[8].set(20)
   print(inputs.getIndices())  # [2, 8]
   print(total.getPlug("output1D").get())  # 30.0
   total.getPlug("input3D")[0].set((1, 2, 3))
   print(tuple(total.getPlug("output3D").get()))  # (1.0, 2.0, 3.0)

   ramp = mlib.createNode("remapValue")
   with undoChunk("remapSettings"):
       for name, value in (("inputMin", 0), ("inputMax", 10),
                           ("outputMin", 0), ("outputMax", 1)):
           ramp.getPlug(name).set(value)
       points = ramp.getPlug("value")
       for index, position, value, interpolation in (
           (0, 0.0, 0.0, 1), (1, 1.0, 1.0, 1), (4, 0.5, 0.8, 2)
       ):
           point = points[index]
           point[0].set(position)
           point[1].set(value)
           point[2].set(interpolation)
       ramp.getPlug("inputValue").set(5)
   print(ramp.getPlug("outValue").get())

配列の ``[index]`` は未作成要素も参照でき、値設定や接続で要素を作成します。
既存番号は ``getIndices()``、既存参照は ``getElements()``、削除は ``removeElement(index)`` です。
1D/2D/3Dは ``input1D/input2D/input3D`` と ``output1D/output2D/output3D`` を明示します。

RemapValueのvalue配列の子はMayaの定義順でposition、value、interpolationです。
補間はMayaの列挙番号0=None、1=Linear、2=Smooth、3=Splineで設定します。
色ランプも ``getPlug("color")`` の各要素の子へ設定し、
``ramp.getPlug("color")[0][1].set((1, 0, 0))`` のようにRGB値を指定します。
ランプ点を専用の辞書へ変換する処理や、複数編集を自動で束ねる処理はありません。
通常の各Plug編集はUndo対応で、例の複数変更は外側の ``undoChunk`` でまとめています。

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

   from maya import cmds
   from mlib.decorator import undoChunk

   with undoChunk("curveEvaluation"):
       curve = mlib.getNode(cmds.curve(
           degree=1, point=[(0, 0, 0), (10, 0, 0)]))  # Transform
       info = mlib.createNode("curveInfo")
       info.connectCurve(curve, ws=True)
       point = mlib.createNode("pointOnCurveInfo")
       point.connectCurve(curve)
       point.setParameter(0.5, percentage=True)
   print(info.getPlug("arcLength").get())  # 内部距離単位cm
   print(point.getPosition())
   print(point.getTangent())

``cmds.curve`` の点はMayaのUI距離単位です。返されたTransform名を
``mlib.getNode`` で参照へ変換しています。例の外側の ``undoChunk`` は
カーブ・計算ノードの作成と接続を1回のUndoへまとめます。
connectCurve/connectSurfaceは既定でworldSpaceを接続し、インスタンス番号を保持します。
ws=Falseはlocalを接続します。Transformに対応シェイプが複数ある場合は、
対象シェイプを明示してください。評価結果は接続されたデータの空間に従います。
PointOnSurfaceInfoはsetParameters(u, v, percentage=True)でUV位置を指定できます。

Undoとバージョン差
------------------------------------------------------------

通常のPlug更新はそれぞれUndoに対応します。複数編集をまとめる境界は利用側で指定します。``fast`` 引数を持つメソッドは
``fast=True`` でUndoなしのOpenMaya更新を選べます。
``Plug.set()``・``Plug.connectTo()``・``ArrayPlug.removeElement()`` も対応します。
上記14型の配列・ランプも同じPlug操作を使います。
途中のエラーで更新済みの箇所を自動ロールバックするものではありません。
対応範囲と制限は :doc:`fast_edit` を参照してください。

Maya 2026/2027では旧nodeTypeのaddDoubleLinear/multDoubleLinearを指定すると、
MayaがaddDL/multDLを作成します。mlibも実型に対応するAddDL/MultDLを返します。
両組の型登録を維持し、Mayaの実型にない継承・互換別名は追加していません。
入力と出力は実際のMayaアトリビュート名で取得します。
AddDL/MultDLを直接作成できるかは、使用中のMayaの対応型に依存します。
