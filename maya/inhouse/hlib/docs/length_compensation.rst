伸縮と体積補正
==============

``hlib.animation.LengthCompensation`` は、基準長と入力長から長さ倍率と
横断面の倍率を計算する標準ノードのグラフです。

.. code-block:: python

   from hlib.animation import LengthCompensation

   graph = LengthCompensation.create(10.0)
   graph.container.plug("inputLength").set(15.0)
   graph.container.plug("lengthScale").get()  # 1.5

入力長を基準長で割り、minSquash〜maxStretchに制限します。
1より大きい側をstretch、小さい側をsquashで元の長さとブレンドします。
stretch/squash/volumeは0〜1、minSquashは0.01〜1、maxStretchは1〜100です。
既定はそれぞれ1/1/1/0.1/2です。基準長は正の有限値を渡してください。

lengthScaleが ``s`` のとき、体積補正は ``s ** -0.5`` です。
volume=0なら横倍率1、volume=1なら逆平方根、途中は線形補間します。
長手方向にs、断面の2軸に同じ横倍率を適用する棒状の近似です。
スキンのウェイト・関節曲げを含めた実メッシュ体積を保証しません。

距離の単位は呼出側で揃えます。inputLength/restLengthは単位なしの数値なので、
MDistance等との接続では明示的な単位変換が必要です。
グラフは骨やメッシュを編集せず、containerが演算ノードを所有します。
生成はUndoに対応し、再生時にPythonや独自プラグインは使用しません。
