リボン(Ribbon)
================

``mlrig.setups.Ribbon`` は、並んだコントロールを断面にした帯状のNURBSサーフェス(リボン)を作り、
その中心線の上に等間隔の行列を出力します。背骨・首・腕のベンド・尻尾・眉など、少ないコントロールで
滑らかに曲がり、ねじれる部位に使う、モジュラーリグでよく使われる部品です。
スキンやfollicleを使わず、Maya標準ノード(``multMatrix`` ・ ``decomposeMatrix`` ・ ``composeMatrix`` ・
``multiplyDivide`` ・ ``loft`` ・ ``uvPin``)だけで構築し、独自プラグインやフレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import Ribbon

   graph = Ribbon.create(["spine_base_ctl", "spine_mid_ctl", "spine_top_ctl"], count=6,
                         name="spineRibbon", width=4.0, sideAxis="z")
   owner = graph.container
   # 出力はワールド行列。ワールド直下(またはinheritsTransformを切った親の下)のjointで受ける
   for index in range(6):
       owner.getPlug("matrix{}".format(index)).connectTo("spine{}_jnt.offsetParentMatrix".format(index))

コントロールは根元から先端の順に渡します。親子関係は問いません(別々の親でも、ワールド直下でもかまいません)。

引数
----

* ``controls``: 断面にする2つ以上の異なるtransform(根元から先端の順)。
* ``count``: 出力する行列の数(2以上)。
* ``name``: 一意なcontainer名。カーブとサーフェスは ``<name>_grp`` の下にまとめます。
* ``width``: 帯の幅(cm)。後からcontainerの ``width`` で変更できます。UIの長さ単位がmmでもcmとして扱います。
* ``sideAxis``: 各コントロールのローカルで、帯の幅の向きにする軸。

出力(containerのアトリビュート)
---------------------------------

* ``matrix0`` 〜 ``matrix<count-1>``: 帯の中心線上のワールド行列。X=根元から先端へ沿う接線、
  Y=面の法線、Z=X×Y(幅の ``sideAxis`` の+側に近い向き)。scaleは1。
* ``position0`` 〜 ``position<count-1>``: 各出力の帯の上の位置(0=根元、1=先端)。既定値は ``i/(count-1)``。
  キーを打って、出力を帯の上で滑らせることもできます。
* ``width``: 帯の幅(cm)。

計算
----

1. 各コントロール i について、ローカルの ``sideAxis`` の向きへ ``+width/2`` と ``-width/2`` ずらした2点を、
   コントロールのワールド行列で移します( ``composeMatrix`` → ``multMatrix`` → ``decomposeMatrix``)。
2. その2点を結ぶ1次の短いカーブ(断面)を作り、制御点へ接続します。
3. 全ての断面を ``loft`` (3次・uniform、断面が2つなら1次)でつなぎ、帯のサーフェスにします。
   帯は全てのコントロールの位置を通ります。断面が90度を超えてねじれても面が裏返らないよう、
   ``loft`` の自動反転(``autoReverse``)は切ります。
4. ``uvPin`` で、U=``position_i`` ・V=0.5(幅の中央)の点の行列を出力します。U方向の接線をX、法線をYにします。

コントロールを回すと断面が回るので、帯のねじれはコントロールの回転で決まり、その間は滑らかに補間されます。

参考にした考え方
----------------

* trigger(``maya/external/trigger`` の ``objects/ribbon.py`` 、GPL-3.0)などのモジュラーリグにある、
  リボン(NURBSの帯にfollicleでjointを貼り、帯をコントロールで変形する)部品で、複数のコントロールの間を
  サーフェス上の点で滑らかにつなぐ考え方。GPLのためコードは流用せず、構成の考え方だけを使っています。
  ここではスキンとfollicleの代わりに、コントロールの行列から断面を直接作り、Maya 2020以降の標準ノード
  ``uvPin`` で点を取ります。
* 帯の上の位置をアトリビュートにして、出力を帯の上で滑らせる考え方。

試験と検証
----------

* 試験: ``mlrig/__tests__/test_setup_ribbon.py`` (出力がOpenMayaで求めたサーフェスの点・接線・法線と一致・
  全てのコントロールを通る・先端のねじれ・幅と位置の変更・mm単位・containerの所有・引数検査・Undo/Redo)。
* メニューの **Setup Samples > Ribbon - five controls** で試せます(:doc:`setup_samples`)。
* 検証動画: ``tools/demo_ribbon.py`` (:doc:`verification_video`)。

制限
----

* 出力の位置はUの正規化値で、弧長に比例した等間隔ではありません。コントロールの間隔が偏ると出力の間隔も偏ります。
* 帯の長さを保つ(伸びを止める)処理や、伸び縮みに合わせた体積補正は含みません。
  必要なら :doc:`length_compensation` と組み合わせます。
* 隣のコントロールの間で180度以上ねじると、補間の向きが不定になります。
* 負・非一様scaleのコントロールは対象外です(scaleは帯の形にだけ効きます)。
