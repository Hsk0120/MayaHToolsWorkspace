アニメーションカーブと重み付き加算
============================================================

AnimCurve
---------

共通基底クラスAnimCurveと、Mayaの8型に対応する子クラスを実装しています。
``mlib.getNode()`` / ``mlib.createNode()`` から具象クラスを自動取得します。

* AnimCurveTA / TL / TT / TU: 時間から角度・距離・時間・単位なし。
* AnimCurveUA / UL / UT / UU: 単位なしから角度・距離・時間・単位なし。

各クラスは ``nodes/animCurveTA.py`` など型別ファイルにあり、共通処理は
``nodes/animCurve.py`` にまとめています。

.. code-block:: python

   import mlib

   curve = mlib.createNode("animCurveUU")
   curve.setKey(0, 0).setKey(1, 10)
   print(curve.evaluate(0.5))  # 5.0
   print(curve.getKeyInputs(), curve.getKeyValues())
   curve.setTangent(0, outTangentType="flat")
   curve.setInfinity(pre="constant", post="linear")
   curve.mirror(input=True, value=False)

``getKeyCount()``、``removeKey(index)``、``getTangent(index)``、``getInfinity()``、
``shiftKeys()``、``scaleKeys()`` も利用できます。
時間は秒、角度はrad、距離はcmです。接線角度もradです。
setKeyの既定接線はlinear。既存キーを指定した場合は値を更新します。
接線の詳細編集はsetTangentを使い、weightedTangentsはカーブ全体へ適用されます。
mirrorはキーの入力・出力値の反転であり、ワールド座標のミラーではありません。
接線の反転はMayaのscaleKeyの規則に従います。

入力の直接接続元は ``curve.getPlug("input").getSource(skipConversionNodes=False)``、
出力Plugは ``curve.getPlug("output")``、直接の接続先は
``curve.getPlug("output").getDestinations(skipConversionNodes=False)`` で取得します。
変換・合成ノードやアニメーションレイヤー越しの探索はまだ行いません。

BlendWeighted
-------------

``input[i] * weight[i]`` の合計を出力します。既定ウェイトは1です。
AnimCurveの子クラスではなく、独立したNodeラッパーです。

.. code-block:: python

   blend = mlib.createNode("blendWeighted")
   blend.setInput(0, 3).setInput(5, 10)
   blend.setWeight(5, 0.5)
   print(blend.getPlug("output").get())  # 8.0
   print(blend.getInputIndices())  # [0, 5]
   blend.connectInput(0, curve.getPlug("output"))

``BlendWeighted.getInputPlugs()`` は番号からPlug、``getWeights()`` は入力番号から倍率のdictです。
出力の評価と接続には ``blend.getPlug("output")`` を使います。
接続の上書きには ``connectInput(..., force=True)`` を明示します。
``connectInput()`` は既存の定数入力をUndoで戻す処理も行います。
編集メソッドは内部でUndoチャンクにまとめるため、通常は外側に ``undoChunk`` は不要です。

SDKの作成と対応経路の探索は :doc:`driven_keys`、
既存のアニメーション・SDK接続の保存復元は :doc:`json` を参照してください。

このページのUndoの説明は通常モード（``fast=False``）を前提とします。
対応する更新メソッドの ``fast=True`` はUndo対象外です。対応範囲と制限は :doc:`fast_edit` を参照してください。

``setInfinity(pre="cycle")`` はpre側だけ変更し、post側を維持します。
両側を戻す場合は ``setInfinity(pre="constant", post="constant")`` を使います。
``getInfinity()`` はOpenMaya経由で取得します。
``setInfinity(pre="cycle", fast=True)`` はUndo不要の直接更新です。
fast時は指定した両側のロック・入力接続を更新前に検証します。
``setKey()``・``removeKey()``・``setTangent()``・``shiftKeys()`` と、
正の入力倍率による ``scaleKeys()`` も ``fast=True`` でAPI直接更新できます。
``mirror(value=True, fast=True)`` は出力値の反転に対応します。
``input=True`` による入力軸の反転と、負の入力倍率のfast拡縮は更新前に未対応として拒否します。
通常モードのキー・接線編集はMaya標準コマンドでUndoに対応します。
接線型名はMayaコマンドと同じ表記で、APIの ``kTangentSmooth`` は ``spline`` として扱います。
fastの入力 ``step`` はMayaと同じ ``auto`` へ補正します。
入力 ``stepnext`` はMayaの版で補正が異なるため、fastでは更新前に ``NotImplementedError`` で拒否します。
fastの ``setKey`` は ``fixed``・``global``・未知の接線型を、
``setTangent`` は ``global``・未知の接線型を更新前に ``ValueError`` で拒否します。
固定接線の編集には ``setTangent(..., inTangentType="fixed", fast=True)`` 等を使います。
BlendWeightedの値設定は ``setInput()``・``setWeight()`` がfastに対応し、
Undo不要の接続は ``curve.getPlug("output").connectTo(blend.getInputPlug(0), fast=True)`` で行えます。

.. code-block:: python

   import mlib

   fast_curve = mlib.createNode("animCurveUU", fast=True)
   fast_curve.setKey(0, 0, fast=True).setKey(1, 10, fast=True)
   fast_curve.setTangent(0, outTangentType="linear", fast=True)
   fast_curve.shiftKeys(input_offset=2, fast=True)
   fast_curve.scaleKeys(value_scale=0.5, fast=True)
   fast_curve.mirror(value=True, fast=True)
   print(fast_curve.evaluate(2.5))  # -2.5
   fast_curve.removeKey(1, fast=True)
   print(fast_curve.getKeyCount())  # 1
