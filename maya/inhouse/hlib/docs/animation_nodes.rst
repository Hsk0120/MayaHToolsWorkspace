アニメーションカーブと重み付き加算
============================================================

AnimCurve
---------

共通基底クラスAnimCurveと、Mayaの8型に対応する子クラスを実装しています。
``hlib.getNode()`` / ``hlib.createNode()`` から具象クラスを自動取得します。

* AnimCurveTA / TL / TT / TU: 時間から角度・距離・時間・単位なし。
* AnimCurveUA / UL / UT / UU: 単位なしから角度・距離・時間・単位なし。

各クラスは ``nodes/animCurveTA.py`` など型別ファイルにあり、共通処理は
``nodes/animCurve.py`` にまとめています。

.. code-block:: python

   import hlib

   curve = hlib.createNode("animCurveUU")
   curve.setKey(0, 0).setKey(1, 10)
   print(curve.evaluate(0.5))  # 5.0
   print(curve.keyInputs(), curve.keyValues())
   curve.setTangent(0, outTangentType="flat")
   curve.setInfinity(pre="constant", post="linear")
   curve.mirror(input=True, value=False)

``keyCount()``、``removeKey(index)``、``getTangent(index)``、``getInfinity()``、
``shiftKeys()``、``scaleKeys()`` も利用できます。
時間は秒、角度はrad、距離はcmです。接線角度もradです。
setKeyの既定接線はlinear。既存キーを指定した場合は値を更新します。
接線の詳細編集はsetTangentを使い、weightedTangentsはカーブ全体へ適用されます。
mirrorはキーの入力・出力値の反転であり、ワールド座標のミラーではありません。
接線の反転はMayaのscaleKeyの規則に従います。

``driverPlug()`` はinputの直接接続元、``outputPlug()`` は出力Plug、
``drivenPlugs()`` は直接の接続先を返します。
変換・合成ノードやアニメーションレイヤー越しの探索はまだ行いません。

BlendWeighted
-------------

``input[i] * weight[i]`` の合計を出力します。既定ウェイトは1です。
AnimCurveの子クラスではなく、独立したNodeラッパーです。

.. code-block:: python

   blend = hlib.createNode("blendWeighted")
   blend.setInput(0, 3).setInput(5, 10)
   blend.setWeight(5, 0.5)
   print(blend.result())  # 8.0
   print(blend.inputIndices())  # [0, 5]
   blend.connectInput(0, curve.outputPlug())

``inputs()`` は番号からPlug、``getWeights()`` は入力番号から倍率のdictです。
``outputPlug()`` を別のアトリビュートへ接続できます。
接続の上書きには ``connectInput(..., force=True)`` を明示します。
編集メソッドは内部でUndoチャンクにまとめるため、通常は外側にundo_chunkは不要です。

SDKの作成と対応経路の探索は :doc:`driven_keys`、
既存のアニメーション・SDK接続の保存復元は :doc:`json` を参照してください。

このページのUndoの説明は通常モード（``fast=False``）を前提とします。
対応する値更新メソッドの ``fast=True`` はUndo対象外です。対応範囲と制限は :doc:`fast_edit` を参照してください。

``setInfinity(pre="cycle")`` はpre側だけ変更し、post側を維持します。
両側を戻す場合は ``setInfinity(pre="constant", post="constant")`` を使います。
``getInfinity()`` はOpenMaya経由で取得します。
``setInfinity(pre="cycle", fast=True)`` はUndo不要の直接更新です。
fast時は指定した両側のロック・入力接続を更新前に検証します。
キーや接線の編集は従来どおりMayaコマンドでUndoに対応します。
