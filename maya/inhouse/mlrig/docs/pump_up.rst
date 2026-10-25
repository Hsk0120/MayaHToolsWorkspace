補助骨の増幅(PumpUp)
====================

``mlrig.setups.PumpUp`` は、既存の補助骨(筋肉の膨らみなど)の動きを、1つの値 ``pump`` で後から増やす仕組みを作ります。
演出で筋肉を一時的に盛り上げたい(パンプアップ)ときに、既存の補助骨の階層・仕組みを壊さずに、その挙動へ加算します。
補助骨ごとに増える割合・形を定数として持つので、アニメーターは ``pump`` (またはそれを駆動するコントロールの値)だけを
キーにすれば、部位ごとに決まった品質の膨らみが得られます。
Maya標準ノード(``multMatrix`` ・ ``decomposeMatrix`` ・ ``plusMinusAverage`` ・ ``multiplyDivide`` ・ ``composeMatrix`` ・
``unitConversion``)だけで組み、独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import PumpUp

   graph = PumpUp.create(
       ["biceps_helper_jnt", "triceps_helper_jnt"], name="armPumpUp",
       driver="arm_pump_ctrl.translateY",          # コントロールの値でpumpを駆動
       gains=(1.5, 1.0),                            # 既存の膨らみ(生成時からの変化)を増やす割合
       scaleOffsets=((0, 0.4, 0.4), (0, 0.2, 0.2)))  # pump=1で足すスケール
   owner = graph.container
   # owner.matrix0 を、同じ親の下の変形用jointの offsetParentMatrix へ繋ぐ

参考にした考え方
----------------

* 補助骨の一般的な応用: 筋肉表現のための既存の補助骨の仕組みはそのままに、別の制御用の骨を追加し、
  その骨の移動・スケールの値で既存の補助骨の挙動を加算的に増幅する、という方法。増える量は部位ごとに決めた定数にして、
  アニメーターが一定の品質を簡単に出せるようにし、Mayaとゲームエンジンで同じ結果を確認できるようにする考え方。

この部品は、制御用の値を ``pump`` (コントロールの任意の数値のplugで駆動できる)、部位ごとの定数を ``gain<i>`` ・
``translateOffset<i>`` ・ ``scaleOffset<i>`` にしました。コードは流用していません。

引数
----

* ``helpers``: 増幅する補助骨のtransform(1個以上)。既存の仕組み(ドリブンキー・行列・MuscleBulgeなど)で動いているものです。
* ``driver``: ``pump`` を駆動する数値のplug(コントロールの ``translateY`` など)。省略すると container の ``pump`` を直接キーにします。
* ``gains``: 補助骨ごとの、生成時からの変化に掛ける割合。省略すると全て1。
* ``translateOffsets``: 補助骨ごとの、pump=1で足す移動量(補助骨の親の空間、内部の単位cm)。省略すると全て0。
* ``scaleOffsets``: 補助骨ごとの、pump=1で足すスケール。省略すると全て0。

計算式
------

補助骨の現在の親の空間の行列 ``helper.matrix · helper.offsetParentMatrix`` を ``decomposeMatrix`` で位置 ``T`` ・
回転(Quaternion) ``Q`` ・スケール ``S`` に分け、生成時の位置 ``T0`` ・スケール ``S0`` を定数として持ちます(:meth:`PumpUp.amplify`)。

* ``translate<i> = T + (T - T0) * gain<i> * pump + translateOffset<i> * pump``
* ``scale<i> = S + (S - S0) * gain<i> * pump + scaleOffset<i> * pump``
* ``matrix<i> = composeMatrix(translate<i>, Q, scale<i>)`` (補助骨の親の空間)
* ``worldMatrix<i> = matrix<i> · 補助骨の生成時の親の worldMatrix``

``pump = 0`` では出力は補助骨と一致します(作成時に跳ねません)。補助骨が生成時の姿勢のままなら、増えるのは offset の分だけです。
位置は係数1の ``unitConversion`` で内部の単位(cm)のまま扱うので、UIの長さの単位によらず同じ結果です。

containerのアトリビュート
--------------------------

* ``pump`` : 増幅の度合い(keyable。 ``driver`` を渡した場合は接続済み)。
* ``gain<i>`` ・ ``translateOffset<i>`` ・ ``scaleOffset<i>`` : 補助骨 ``helpers[i]`` の定数(keyable)。
* ``translate<i>`` ・ ``scale<i>`` : 増幅した位置・スケール(確認用)。
* ``matrix<i>`` ・ ``worldMatrix<i>`` : 増幅した行列。

制限
----

* 出力は補助骨そのものへは接続しません(補助骨の行列を読んでいるので循環になる)。同じ親の下に置いた変形用のjointの
  ``offsetParentMatrix`` へ ``matrix<i>`` を繋ぐか、 ``worldMatrix<i>`` を使います。
* 回転は増幅しません。剪断は扱いません(出力では0)。
* ``worldMatrix<i>`` は生成時の親の ``worldMatrix`` に接続します。後から補助骨の親を変えた場合は作り直してください。
* ``pump`` は上限を設けていません。大きくしすぎてスケールが0以下にならないよう、 ``driver`` 側で範囲を制限してください。

テスト
------

``mlrig/__tests__/test_setup_pump_up.py`` (``setups`` スイート)で、回した親の下に移動・回転・スケールを持つ補助骨を2つ(1つは offsetParentMatrix 付き)作り、
pump=0では既存の仕組みが補助骨を動かしても出力が補助骨と一致すること、pumpを正負に変えたときに位置・スケール・行列・ワールド行列が
``MTransformationMatrix`` で独立に分けて組み直した値と一致すること、gain・translateOffset・scaleOffset の引数とアトリビュートの変更、
driverのplug、UI単位(mm)、所有とUndo/Redo、引数の検査を確かめます。
