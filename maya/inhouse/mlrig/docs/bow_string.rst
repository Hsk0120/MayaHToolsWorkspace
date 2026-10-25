弓の弦(BowString)
==================

``mlrig.setups.BowString`` は、弓の上下の先端から弦を引く点(ノック位置・引き手のコントロール)へ向かう
弦の上半分・下半分の行列と長さを出力します。生成時からの引き量 ``draw`` と、0〜1に正規化した
``drawWeight`` も出力するので、リム(弓の腕)の曲がりや補正シェイプを一つの値でまとめて動かせます。
Maya標準ノード(``aimMatrix`` ・ ``multMatrix`` ・ ``distanceBetween`` ・ ``plusMinusAverage`` ・
``multiplyDivide`` ・ ``clamp``)のみで構築し、独自プラグインやフレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import BowString

   graph = BowString.create("bow_top_tip", "bow_bottom_tip", "nock_ctl", name="bowString",
                            aimAxis="x", upAxis="y", maxDraw=30.0)
   owner = graph.container
   # 各先端と同じ親の下の、TRSがidentityの出力jointへ接続する
   owner.getPlug("topMatrix").connectTo("string_top_jnt.offsetParentMatrix")
   owner.getPlug("bottomMatrix").connectTo("string_bottom_jnt.offsetParentMatrix")
   # 弦の先(子のjoint)をノックの位置まで伸ばす
   owner.getPlug("topLength").connectTo("string_topEnd_jnt.translateX")
   owner.getPlug("bottomLength").connectTo("string_bottomEnd_jnt.translateX")

弦を張っただけの姿勢(ノックが上下の先端を結ぶ線から離れた状態)で作成します。
上下の先端は別々の親(上のリム・下のリム)の下にあってかまいません。

引数
----

* ``top`` ・ ``bottom``: 弦を掛ける上・下の先端のtransform。
* ``nock``: 弦を引く点のtransform。
* ``name``: 一意なcontainer名。
* ``aimAxis``: 弦の向き(先端からノックへ)にする軸。
* ``upAxis``: 弓の面の法線へ揃える軸。``aimAxis`` と異なる軸。
* ``maxDraw``: ``drawWeight`` が1になる引き量(cm)。省略時は上下の先端の距離の0.5倍。
  後からcontainerの ``maxDraw`` で変更できます。

出力(containerのアトリビュート)
---------------------------------

* ``topMatrix`` ・ ``bottomMatrix``: 各先端の親空間の行列。位置は先端の現在位置のままで、
  生成時にノックを向いていたローカルの向きが常にノックを向きます。
* ``topLength`` ・ ``bottomLength``: 各先端からノックまでの距離(cm)。
* ``restDraw``: 生成時の、上下の先端の中点からノックまでの距離(cm、弦を張ったときの距離)。
* ``draw``: ``|nock - (top + bottom) / 2| - restDraw`` (cm)。弓から離れるほど大きくなります。
* ``drawWeight``: ``clamp(draw / maxDraw, 0, 1)``。

計算
----

1. 生成時に、3点から弓の面の法線 ``n = (top - nock) × (bottom - nock)`` を求め、上の先端の親空間の
   ベクトルとして固定します。弓全体を回すと法線も一緒に回ります。
2. 各先端で ``aimMatrix`` が ``aimAxis`` をノックの位置へ、 ``upAxis`` を ``n`` へ揃えた回転を求めます。
   弦の上下の半分が同じ面に乗り、ねじれません。
3. 出力 = (生成時のワールド行列 × 生成時の ``aimMatrix`` 出力の逆) × 現在の ``aimMatrix`` 出力 を、
   各先端の親の空間へ戻したもの。生成時の差を定数で保つので、作成時に姿勢が跳ねません。

参考にした考え方
----------------

* 弓のリグで、弦の上下の半分を弦を引く点のコントロールへ向け、長さを伸ばす一般的な作り方。
* コントローラーを少なくして、一つの値(ここでは引き量)で複数の部位(リムの曲がり・補正)を動かす考え方。
* 両端の部品が互いを向く行列の作り方は :doc:`piston` と同じです。

試験と検証
----------

* 試験: ``mlrig/__tests__/test_setup_bow_string.py`` (作成時に跳ねない・弦の向き・長さ・引き量・
  弓の面の法線・引数検査・Undo)。
* メニューの **Setup Samples > BowString - bow and nock** で試せます(:doc:`setup_samples`)。
* 検証動画: ``tools/demo_bow_string.py`` (:doc:`verification_video`)。

制限
----

* 弦の長さ・引き量は出力するだけで、ノックの位置(引きすぎ)は制限しません。
* 弦が弓の面の法線と平行になる位置へノックを動かすと、向きが不定になります。
* 矢の発射(弦から離れる切り替え)や、リムの曲がりそのものは含みません。 ``drawWeight`` を
  リムのjointの回転や補正シェイプへつないで使います。
* 負・非一様scaleは対象外です。
