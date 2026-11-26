端からの巻き取り(RollUpChain)
=============================

``mlrig.setups.RollUpChain`` は、親子に並んだjoint列を、端の関節から1つずつ順に曲げて渦巻きに巻き取る行列を出力します。
舌・尻尾・触手・巻物・旗・ゾウの鼻のように「先から丸まっていく」動きを、containerの ``roll`` 1つで操作できます。
``roll`` は「巻き終えた関節の数」で、届く範囲の外では端で止まり、超えた量を ``excess`` へ出します。
Maya標準ノードのみで構築し、エクスプレッション・独自プラグイン・フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import RollUpChain

   graph = RollUpChain.create(
       ["tail0", "tail1", "tail2", "tail3", "tail4", "tail5"], name="tailRoll", axis="z",
       angle=60, decay=0.85, width=1.0,
   )
   owner = graph.container
   # 入力と同じ親子に並べた出力の各transform(TRSがidentity)のoffsetParentMatrixへ接続する
   for index in range(6):
       owner.getPlug("matrix" + str(index)).connectTo("tail{}_out.offsetParentMatrix".format(index))
   owner.getPlug("roll").set(2.5)   # 先端の2関節を巻き終え、3つ目が半分まで曲がる

:doc:`wave_chain` が全関節を同時に揺らすのに対して、RollUpChainは関節ごとに曲がり始める時期をずらします。
2つは同じ形の出力(関節ごとの親空間の行列)なので、RollUpChainの出力を受けたtransformの列をWaveChainの入力にすれば重ねられます。

引数
----

* ``joints``: 根元から先端へ、親子に並んだ2つ以上のtransform。
* ``axis``: 各関節のローカルで曲げる回転軸。x/y/z、既定はz。
* ``angle``: 最初に巻く関節が巻き終えたときの角度(度、-180〜180)。符号で巻く向きが変わります。既定は60。
* ``decay``: 巻く順が1つ後になるごとに角度へ掛ける倍率(0.1〜1)。1では全関節が同じ角度(円)、
  1未満では後から巻く関節ほど角度が小さく、外へ広がる渦巻きになります。既定は1。
* ``width``: 同時に曲がっていく関節の数(0.01以上)。1では1関節ずつ、大きくすると複数の関節がなだらかに曲がります。既定は1。
* ``fromRoot``: Trueなら根元から、False(既定)なら先端から巻きます。

``roll`` (既定0)・ ``angle`` ・ ``decay`` ・ ``width`` はcontainerのアトリビュートとして、生成後も変更・アニメーションできます。
``roll`` の既定が0なので、生成時に姿勢は変わりません。

計算式
------

関節の数を ``N`` 、根元を ``i = 0`` とします。巻く順 ``j`` は、先端から巻くとき ``j = N - 1 - i`` 、根元から巻くとき ``j = i`` です。

1. 止めたroll ``rolled = clamp(roll, 0, N - 1 + width)`` 、超えた量 ``excess = roll - rolled``
2. 重み ``w_i = clamp((rolled - j) / width, 0, 1)``
3. 角度 ``θ_i = angle · decay^j · w_i`` (度)
4. 合計 ``totalAngle = Σ θ_i``
5. 出力 ``matrix_i = R_axis(θ_i) · (関節iの matrix * offsetParentMatrix)`` (行ベクトル規約)

2.により、巻く順 ``j`` の関節は ``roll`` が ``j`` から ``j + width`` へ進む間に0から最大の角度まで線形に曲がります。
最後の関節が曲がり終えるのが ``roll = N - 1 + width`` なので、これを上限にします。
5.は関節のローカルの ``axis`` まわりに回してから入力のローカル行列を掛けるので、関節の位置(長さ)は変わらず、
入力の回転(jointOrientやアニメーション)の上に巻き取りが重なります。

区間の長さがすべて等しいまっすぐな鎖では、 ``decay = 1`` ・ ``angle = 360 / N`` で全部巻くと正N角形になり、先端が根元へ戻ります。
``decay`` の倍率は等比で角度を減らす近似で、アルキメデスの渦巻き(1巻きごとに半径が一定量だけ増える)とは厳密には一致しません。

出力
----

* ``matrix0`` 〜 ``matrixN-1``: 各関節の、入力と同じ親の空間の行列。
* ``angle0`` 〜 ``angleN-1``: 各関節に足した角度 ``θ_i`` (度)。
* ``rolled``: 範囲 ``0 〜 N - 1 + width`` で止めた ``roll`` 。
* ``excess``: 範囲を超えた量(上へ超えると正、0より下は負、範囲内は0)。
* ``totalAngle``: 角度の合計(度)。巻いた量に応じた補正シェイプなどのドライバーに使えます。

角度の出力は、UIの角度単位(degree/radian)によらず常に度です。

制限
----

* 巻き取りは回転の重ね合わせだけで、巻いた部分同士の衝突・厚みによる半径の変化は扱いません。
  太さのある形状で重なる場合は、 ``angle`` を小さくするか ``decay`` を下げて外側の巻きを広げてください。
* 重みは線形なので、関節が曲がり始める瞬間と曲がり終える瞬間に速さが切り替わります。 ``width`` を大きくすると目立たなくなります。
* joint列の最後の関節(先端)の回転は、その子に形状や骨が無ければ見た目に現れません。
  曲げたい区間の根元にある関節を ``joints`` へ渡してください。
* 曲げる軸は全関節で共通の1軸です。
* 負・非一様scaleは対象外です。
* 出力を入力と違う親子へ接続したり、非identityのTRSへ重ねたりすると二重変換になります。

テスト
------

``mlrig/__tests__/inMaya/unit/setups/test_rollUpChain.py`` (``setups`` スイート)で、回転した親の下の、jointOrientと回転を持つ6関節について、
roll=0の生成直後に出力のワールド行列が入力と一致すること、 ``roll`` を変えたときの各関節の角度・ ``rolled`` ・ ``excess`` ・
``totalAngle`` と出力行列、先端から順に曲がること、範囲の外で止まり範囲へ戻すと元へ戻ること、
まっすぐな鎖を ``decay = 1`` ・ ``angle = 360 / N`` で巻くと先端が根元へ戻ること、根元から巻く指定・軸の指定と生成後のアトリビュート変更、
UIの角度単位がradianの場合、引数の検査、生成のUndoを、Pythonの式とOpenMayaで求めた期待値と比べます。Maya 2027で確認しています。

検証動画
--------

``tools/demo_roll_up_chain.py`` は、新規シーンに10関節のまっすぐな入力の尻尾(赤・半透明)と出力の尻尾(緑)を正面から見る構図で作り、
式と毎フレームの入力値・DG出力をHUDに表示して録画します。roll=0(生成時の姿勢)→先端から順に巻く→上限(N-1+width)を超えて
止まり ``excess`` が増える→範囲へ戻す→ ``decay`` を1へ(きつい巻き)→ ``width`` を4へ(なだらかな巻き)→0より下へ下げて止まる→0へ戻して入力と一致、
を記録します。各フレームで、DGの角度・ ``rolled`` ・ ``excess`` が式と一致すること、出力の各区間のワールドでの向きが角度の累積と一致することを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` (``verification.mp4`` ・ ``result.json`` ・
``roll-up-chain.ma``)に保存し、最新のフォルダーを ``latest-roll-up-chain.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_roll_up_chain.py --launch
