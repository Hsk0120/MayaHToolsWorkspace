ヒンジ関節の曲げ補正
==============================

``hrig.setups.BendCorrection`` は、直接の親子transformから
回転を補間した親空間行列と、曲げに応じた二つの距離を生成します。
標準ノードだけで計算し、単位変換ノードも含めてcontainerで所有します。
ジョイント生成・スキン・LODは呼び出し側が管理します。

.. code-block:: python

   from hrig.setups import BendCorrection

   graph = BendCorrection.create("upper_jnt", "elbow_jnt", axis="z")
   graph.container.plug("rotationRatio").set(0.5)
   graph.container.plug("referenceAngle").set(90)  # 常に度
   graph.container.plug("innerPush").set(-0.2)
   graph.container.plug("outerPush").set(-0.3)

``matrix`` 出力は、生成時の基準回転から現在の回転へ指定割合で補間します。
位置は現在の関節位置へ100%追従します。直接の親子なので、ワールド行列を介さず
``matrix * offsetParentMatrix`` を使用します。``restMatrix`` に基準姿勢を保存します。
Maya 2022と2025以降のblendMatrixの属性差に対応します。

``axis`` に直交する方向ベクトルとQuaternionの符号から、ヒンジの曲げ角を取得します。
XYZの各軸で90度を超える曲げも扱います。``bendSign`` を-1にすると負方向を曲げとします。
``response = clamp(曲げ角度 * bendSign / referenceAngle, 0, 1)`` です。
``referenceAngle`` は度指定で、シーンの角度単位を変更しても意味は変わりません。

二つの距離出力は ``innerRest + innerPush * response`` と
``outerRest + outerPush * response`` です。距離パラメータは現在のシーン距離単位です。
生成後に距離単位を変更しても既存の実寸を保持します。符号で移動方向を選択できます。

ヒンジ関節の単一軸曲げ向けです。複合回転の解剖学的な曲げ抽出、180度を越える
連続回転、複数回転、負スケール・シアーを含む参照姿勢は対象外です。
生成後に参照ノードを再親子付けしないでください。
補正先を入力関節やその上流へ接続すると循環するため、独立した出力先を使ってください。

``hlib.delete(graph.container)`` で所有する計算ノードを削除できます。
参照した親子transformは削除されません。
