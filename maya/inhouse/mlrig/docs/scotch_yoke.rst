スコッチヨーク(ScotchYoke)
==========================

``mlrig.setups.ScotchYoke`` は、等速で回るクランクのピンが溝付きのヨーク(溝は移動軸に垂直)の中を滑りながらヨークを押し、
ヨークを ``x = r cos θ`` の単振動で往復させるスコッチヨークの動きを求めます。連接棒の無い :doc:`crank_slider` (棒の長さを
無限にした極限)にあたり、ヨークの位置・速さ・加速度は純粋な正弦波になります。溝の中のスライドブロック(ピンに付く)も
動かせます。Maya標準ノード(``sin`` ・ ``cos`` ・ ``animBlendNodeAdditive`` ・ ``condition`` ・ ``unitConversion``)だけで組み、
独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import ScotchYoke

   # ピンの半径3cm。ヨークは X に動き、ヨークの子のブロックは溝に沿って Y に動く
   graph = ScotchYoke.create("crank", "yoke", "block", crankRadius=3.0, name="pump", axis="z",
                             yokeAxis="x", blockAxis="y")
   owner = graph.container
   # ヨークの translateX とブロックの translateY へ出力を接続済み。クランクの rotateZ を回すだけで動く

``connect=True`` (既定)ならヨークの ``translate<yokeAxis>`` (とブロックの ``translate<blockAxis>``)へ出力を接続します。
``False`` なら接続せず、containerの ``yokeTranslate`` ・ ``blockTranslate`` を自分で使います。

参考にした考え方
----------------

* 理想のスコッチヨークの変位 ``x = r cos θ`` ・行程 ``2r`` ・速さ ``-rω sin θ`` ・加速度 ``-rω² cos θ`` という一般的な関係
  (https://www.firgelliauto.com/blogs/mechanisms/scotch-yoke)。θ の基準をどこに取るかで sin と cos が入れ替わるため、
  このページでは生成時のピンの向きを θ = 0 と決め、テストでピンの位置と突き合わせています。

コードは流用していません。

引数
----

* ``crank``: クランクのtransform。ローカルの ``rotate<axis>`` を回します。生成時の姿勢を ``θ = 0``
  (ピンがヨークの移動軸の正の向きにあり、ヨークが行程の正の端)とします。
* ``yoke``: ヨークのtransform。ローカルの ``translate<yokeAxis>`` を動かします。
* ``block``: 溝の中のブロックのtransform(省略可)。ヨークの子に置き、ローカルの ``translate<blockAxis>`` を溝に沿って動かします。
* ``crankRadius``: ピンの半径 r (cm、0より大きい)。生成時に固定します。
* ``axis`` ・ ``yokeAxis`` ・ ``blockAxis``: クランクの回転軸、ヨークの移動軸、ブロックの移動軸(x/y/z)。
* ``yokeDirection`` ・ ``blockDirection``: 移動の向き(1.0 か -1.0)。生成時のピンの向きとヨークの移動軸の正の向きが逆、
  またはクランクが +θ 回ったときピンが動く溝の向きとブロックの移動軸の正の向きが逆なら -1.0 にします。
* ``connect``: Trueなら出力を接続します。既に入力がある場合は ``ValueError`` です。

計算式
------

1. ``θ = クランクの rotate<axis> - 生成時の値 + phase`` 。
2. クランクの中心から見たピンの位置は ``(r cos θ, r sin θ)`` (生成時のピンの向きを x、溝の向きを y とする)。
3. ヨークの溝はピンの x にあるので ``yokeOffset = yokeDirection × r (cos θ - 1)`` 、
   ``yokeTranslate = 生成時のヨークの translate<yokeAxis> + yokeOffset`` 。
4. ブロックはピンの y にあるので ``blockOffset = blockDirection × r sin θ`` 、
   ``blockTranslate = 生成時のブロックの translate<blockAxis> + blockOffset`` 。
5. ``velocity = dx/dθ = -yokeDirection × r sin θ`` (cm/ラジアン)、 ``acceleration = d²x/dθ² = -yokeDirection × r cos θ`` 。
   クランクの角速度 ω を掛けると時間あたりの速さ・加速度になります。
6. ``travel = (1 - cos θ) / 2`` (生成時の端で0、反対の端で1)、 ``returnStroke = (sin θ < 0)`` (生成時の端へ戻る半周で1)、
   ``stroke = 2r`` (生成時に固定の値)。

θ = 0 ではヨーク・ブロックとも移動0なので、接続しても跳ねません。履歴を持たない閉じた式なので、クランクを逆に回すと
同じ経路を戻ります。往きと戻りは同じ半周ずつで、:doc:`quick_return` のような速さの差はありません。

数値の加算は ``animBlendNodeAdditive`` を連ねて倍精度で行います(``plusMinusAverage`` ・ ``multiplyDivide`` は単精度のため)。
``sin`` ・ ``cos`` の入出力は版により長さの型なので、係数を明示した ``unitConversion`` を挟み、UI単位(mm・ラジアン等)に
関係なく同じ結果にします。 ``returnStroke`` の判定だけは単精度の ``condition`` です。

containerのアトリビュート
--------------------------

* ``phase`` : クランクの角度に足す値(keyable)。
* ``yokeTranslate`` ・ ``yokeOffset`` : ヨークの移動と、生成時からの移動量。
* ``blockTranslate`` ・ ``blockOffset`` : ブロックの移動(``block`` を渡したときだけ)と、溝に沿った移動量。
* ``velocity`` ・ ``acceleration`` : クランクの角度あたりのヨークの速さと加速度。揺れ・音のドライバーに使えます。
* ``travel`` : 行程のどこにいるか(0〜1)。補正シェイプ・色のドライバーに使えます。
* ``returnStroke`` : 生成時の端へ戻る間1、離れる間0。
* ``stroke`` : ヨークの行程 2r (固定の値)。

制限
----

* クランクはローカルの1軸の回転チャンネル( ``rotate<axis>`` )を読みます。複数軸の回転やワールドでの回転は扱いません。
* 溝はヨークの移動軸に垂直な直線だけです。傾いた溝・曲がった溝(停留を作る形)は扱いません。
* ブロックはヨークの子に置く前提で、ヨークに対する移動を出力します。ヨークの外に置く場合は ``blockOffset`` を自分で使います。
* クランク・ヨーク・ブロックの形状は作りません。

テスト
------

``mlrig/__tests__/inMaya/unit/setups/test_scotchYoke.py`` (``setups`` スイート)で、作成直後にヨークとブロックが跳ねないこと、
正負・複数回転の角度でヨークの溝の位置とブロックの位置が試験側で求めたピンの x ・ y と一致すること、Python版
( :meth:`ScotchYoke.motion` )との一致、 ``velocity`` ・ ``acceleration`` がDGのヨークの位置の1階・2階の数値微分と一致すること、
``returnStroke`` が位置の増える区間と一致すること、1回転の行程が ``2r`` で戻りが半周であること、 ``phase`` 、
``axis = x`` ・ ``yokeAxis = y`` ・ ``blockAxis = z`` ・向き -1 ・UI単位mm/ラジアン・初期位置あり・ブロックなし、
containerの所有とUndo/Redo、引数の検査を確認します。Maya 2027で確認しています。

検証動画
--------

``tools/demo_scotch_yoke.py`` は、新規シーンにクランク(赤、先が白いピン)・溝付きのヨーク(緑)・溝の中のブロック(緑)を
正面から見る構図で作り、クランクを等速で2回転→逆へ半回転→元へ戻す動きで、式と毎フレームの θ ・ヨークとブロックの位置・
速さ・加速度・往き/戻りをHUDに表示して録画します。各フレームでDGの出力が試験側の式と一致し、ピンのワールド位置が
ヨークの溝の中心線の上とブロックの中心にあることを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを
``latest-scotch-yoke.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_scotch_yoke.py --launch
