肘・膝の留めと長さの振り分け(LimbPin)
=====================================

``mlrig.setups.LimbPin`` は、2関節の腕・脚(肩→肘→手首、股→膝→足首)の骨の長さを書き換える標準DGです。

* **slide**: 合計の長さを保ったまま、上の骨(上腕・太もも)と下の骨(前腕・すね)の長さの比を変えます。
* **pin**: 上の長さを「付け根から極ベクトルの操作子まで」、下の長さを「極ベクトルの操作子からIKの目標まで」へ
  近づけます。同じ操作子を極ベクトルにしたIKでは、pin=1 で肘・膝がちょうど操作子の位置へ来ます
  (肘を机に、膝を床に留める)。

IKの解き方には手を入れず、中間と先端のjointの骨の向きの ``translate`` だけを駆動するので、Maya標準の
``ikRPsolver`` と ``poleVectorConstraint`` の腕・脚へそのまま足せます。Maya標準ノード( ``multMatrix`` ・
``vectorProduct`` ・ ``plusMinusAverage`` ・ ``multiplyDivide`` ・ ``condition`` ・ ``blendColors`` ・係数1の
``unitConversion``)のみで構築し、独自プラグインやフレームごとのPythonは使いません。

.. code-block:: python

   from maya import cmds
   from mlrig.setups import LimbPin

   handle = cmds.ikHandle(startJoint="shoulder", endEffector="wrist", solver="ikRPsolver")[0]
   cmds.parent(handle, "hand_ctrl")
   cmds.poleVectorConstraint("elbow_ctrl", handle)
   graph = LimbPin.create("shoulder", "elbow", "wrist", pole="elbow_ctrl", target="hand_ctrl", name="armPin")
   cmds.setAttr(str(graph.container) + ".pin", 1.0)   # 肘を elbow_ctrl へ留める

引数
----

* ``start`` ・ ``mid`` ・ ``end``: 付け根・中間・先端のjoint。 ``start > mid > end`` の親子で、中間と先端は親から
  ``axis`` の向きに離れていること(作成時の ``translate`` の ``axis`` の値を長さと符号にします)。
* ``pole``: pin の留め先のtransform(極ベクトルの操作子)。 ``target``: IKの目標のtransform。
* ``name``: 一意なcontainer名。 ``axis``: 骨の向きの軸( ``"x"`` ・ ``"y"`` ・ ``"z"`` 、既定 ``"x"``)。右の腕のように
  値が負でも符号を保ちます。
* ``slide``: 初期値(-1〜1、既定0)。 ``pin``: 初期値(0〜1、既定0)。

出力
----

containerの ``slide`` ・ ``pin`` (keyable)、 ``restUpper`` ・ ``restLower`` (作成時の長さ、書き換えれば基準の長さになる)、
``upperLength`` ・ ``lowerLength`` (出力の長さ)。中間・先端のjointの ``translate<axis>`` へ接続します。

計算
----

付け根の親の空間(付け根のjointの ``parentInverseMatrix``)で、付け根の位置 ``R`` (付け根の ``translate``)、
操作子の位置 ``P`` 、目標の位置 ``T`` を求め、 ``d1 = |P - R|`` 、 ``d2 = |T - P|`` とします。作成時の長さを
``U0`` ・ ``L0`` として、

1. slide ``s``: ``δ = s·L0`` (s ≥ 0)、 ``δ = s·U0`` (s < 0)。 ``U' = U0 + δ`` 、 ``L' = L0 - δ`` (合計は ``U0 + L0`` のまま。
   s=1 で下の長さが0、s=-1 で上の長さが0)。
2. pin ``w``: ``U = U' + w(d1 - U')`` 、 ``L = L' + w(d2 - L')`` 。
3. 中間・先端のjointの ``translate<axis>`` へ、作成時の符号を掛けた ``U`` ・ ``L`` を入れます。

付け根の位置は付け根の ``translate`` から読み、付け根の回転・ワールド行列を経由しないので、IKが付け根を回しても
循環しません。付け根の親が一様に拡大縮小されていても、長さはその空間で測るので一致します。
UI単位がmmでも自動の単位変換が入らないよう、長さの受け渡しは係数1の ``unitConversion`` で行います。

pin=1 のとき、上下の長さが付け根→操作子・操作子→目標の距離と等しいので、3点が作る三角形の頂点は操作子そのものになり、
同じ操作子を極ベクトルにした ``ikRPsolver`` の肘・膝は操作子の位置へ来ます(手首・足首は目標に届きます)。

参考にした考え方
----------------

* 腕・脚のIKで、上下の骨の長さの比を合計を保ったまま動かす「slide」の考え方(mGearの2関節の腕・脚のコンポーネントにある
  ``slide`` アトリビュート。MITライセンス。mGearは専用のIKノードの中で計算しますが、ここでは標準ノードで骨の長さだけを変えます)。
* 中間の関節を極ベクトルの操作子へ留める「肘・膝のpin(lock)」の一般的な方法(上下の長さを操作子までの距離へ
  ブレンドする)。オートリグのツールでよく使われる考え方で、コードは流用していません。

試験と検証
----------

* 試験: ``mlrig/__tests__/test_setup_limb_pin.py`` (作成の前後で腕が動かない・slide で合計を保つ・pin=1 で
  ``ikRPsolver`` の肘が操作子に、手首が目標に一致(乱数12姿勢)・pin の途中の線形補間・負の軸と軸 y・UI単位mm/rad・
  所有とUndo/Redo・引数検査)。
* メニューの **Setup Samples > LimbPin - arm with elbow pin and slide** で試せます(:doc:`setup_samples`)。
* 検証動画: ``tools/demo_limb_pin.py`` (:doc:`verification_video`)。

制限
----

* 付け根と中間のjointは scale 1 を前提とします(付け根の親のscaleは扱えます)。
* 骨の向きの1軸の ``translate`` だけを書き換えます。作成時に中間・先端のjointが他の軸にもずれていると、
  そのずれは残るので pin=1 でも肘が操作子から外れます。
* pin で骨を伸ばし縮めするので、離れた操作子へ留めると骨の長さが大きく変わります(長さの上限・下限はありません)。
* 伸び縮み(目標まで届かないときに伸ばす)・soft IK は別のセットアップ( :doc:`index` の各ページ)と組み合わせます。
  同じjointの ``translate`` を駆動するものとは同時に使えません。
