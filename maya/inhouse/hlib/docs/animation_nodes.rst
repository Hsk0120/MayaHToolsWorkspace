アニメーションカーブと重み付き加算
============================================================

AnimCurve
---------

共通基底クラスAnimCurveと、Mayaの8型に対応する子クラスを実装しています。
``hlib.node()`` / ``hlib.createNode()`` から具象クラスを自動取得します。

* AnimCurveTA / TL / TT / TU: 時間から角度・距離・時間・単位なし。
* AnimCurveUA / UL / UT / UU: 単位なしから角度・距離・時間・単位なし。

各クラスは ``nodes/animCurveTA.py`` など型別ファイルにあり、共通処理は
``nodes/animCurve.py`` にまとめています。

.. code-block:: python

   import hlib

   curve = hlib.createNode("animCurveUU")
   curve.set_key(0, 0).set_key(1, 10)
   print(curve.evaluate(0.5))  # 5.0
   print(curve.inputs(), curve.values())
   curve.set_tangent(0, outTangentType="flat")
   curve.set_infinity(pre="constant", post="linear")
   curve.mirror(input=True, value=False)

``key_count()``、``remove_key(index)``、``tangent(index)``、``infinity()``、
``shift_keys()``、``scale_keys()`` も利用できます。
時間・角度・距離の数値は現在のMaya UI単位です。
set_keyの既定接線はlinear。既存キーを指定した場合は値を更新します。
接線の詳細編集はset_tangentを使い、weightedTangentsはカーブ全体へ適用されます。
mirrorはキーの入力・出力値の反転であり、ワールド座標のミラーではありません。
接線の反転はMayaのscaleKeyの規則に従います。

``driver()`` はinputの直接接続元、``output()`` は出力Plug、
``driven_plugs()`` は直接の接続先を返します。
変換・合成ノードやアニメーションレイヤー越しの探索はまだ行いません。

BlendWeighted
-------------

``input[i] * weight[i]`` の合計を出力します。既定ウェイトは1です。
AnimCurveの子クラスではなく、独立したNodeラッパーです。

.. code-block:: python

   blend = hlib.createNode("blendWeighted")
   blend.set_input(0, 3).set_input(5, 10)
   blend.set_weight(5, 0.5)
   print(blend.result())  # 8.0
   print(blend.input_indices())  # [0, 5]
   blend.connect_input(0, curve.output())

``inputs()`` は番号からPlug、``weights()`` は入力番号から倍率のdictです。
``output()`` を別の属性へ接続できます。
接続の上書きには ``connect_input(..., force=True)`` を明示します。
編集メソッドは内部でUndoチャンクにまとめるため、通常は外側にundo_chunkは不要です。

SDKの自動構築・間接接続の探索・保存復元は今後の拡張です。
これらの設計案は :doc:`animation_nodes_research` を参照してください。
