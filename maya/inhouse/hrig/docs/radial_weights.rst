円周方向のウェイト
==================

``hrig.setups.RadialWeights`` は、等間隔の方向のうち入力方向を挟む二方向を選び、
方向ベクトルの比率を計算します。hrigに依存せず、Maya標準DGで調整値を評価します。

.. code-block:: python

   import math
   from hrig.setups import RadialWeights

   indices, weights = RadialWeights.weights(math.radians(30), 4)
   graph = RadialWeights.create(math.radians(30), 4, name="directionWeights")
   graph.container.plug("falloff").set(2)
   graph.container.plug("blend").set(0.75)

方向の間隔を ``s`` 、方向Aから入力までの角度を ``t`` とすると、
比率は ``sin(s-t) : sin(t)`` です。Falloff=1では、混合した方向ベクトルが
入力方向と平行になります。円周の最後と最初も隣接として扱います。

* ``directionA`` / ``directionB``: 0始まりの方向番号。作成時に固定。
* ``falloff``: 比率をべき乗してから再正規化する指数。0.1〜8、既定1。
  大きいほど近い方向の影響が強く、小さいほど二方向が均等に混ざります。
* ``blend``: 全体の影響量。0〜1、既定1。
* ``weightA`` / ``weightB``: 正規化比率にBlendを掛けた出力。
* ``restWeight``: ``1 - blend`` 。三出力の合計は1です。

角度はラジアン、方向数は3以上の整数です。方向は作成後に切り替えず、
Falloff/BlendだけをDGで評価します。入力値はDG内でも範囲を制限します。
このクラスはウェイト計算だけを所有し、constraintや骨を作成しません。
