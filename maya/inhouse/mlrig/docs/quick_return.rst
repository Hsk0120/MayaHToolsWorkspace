早戻り機構(QuickReturn)
========================

``mlrig.setups.QuickReturn`` は、等速で回るクランクのピンがレバーの溝(スロット)を滑りながら、ピボットのまわりに
レバーを左右へ振らせる早戻り機構(クランクとスロット付きレバー)の動きを求めます。往きはゆっくり、戻りは速く振れるので、
形削り盤のラム・からくりの往復・ワイパーのような「行きと帰りで速さの違う往復」を、クランクの1つの回転だけでアニメーションできます。
Maya標準ノード(``sin`` ・ ``cos`` ・ ``atan2`` ・ ``divide`` ・ ``power`` ・ ``animBlendNodeAdditive`` ・ ``multDoubleLinear`` ・
``condition`` ・ ``unitConversion``)だけで組み、独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import QuickReturn

   # ピンの半径2cm、クランクの中心はピボットから5cm上。ラムの溝はピボットから8cm上
   graph = QuickReturn.create("crank", "lever", "ram", crankRadius=2.0, pivotDistance=5.0, ramHeight=-8.0,
                              name="shaper", axis="z", ramAxis="x")
   owner = graph.container
   # レバーの rotateZ とラムの translateX へ出力を接続済み。クランクの rotateZ を回すだけで動く

``connect=True`` (既定)ならレバーの ``rotate<axis>`` (とラムの ``translate<ramAxis>``)へ出力を接続します。
``False`` なら接続せず、containerの ``rotate`` ・ ``ramTranslate`` を自分で使います。

参考にした考え方
----------------

* 往きと戻りの時間の比は、クランクが等速なので、それぞれの区間のクランクの角度の比になるという関係
  (https://mr-iitkgp.vlabs.ac.in/exp/quick-return-mechanism/theory.html)。
* ピボットとクランクの中心の距離 d がピンの半径 r より大きいとき、レバーの振れの片側は ``α = asin(r/d)`` で、
  クランクの角度は往きが ``180° + 2α`` 、戻りが ``180° - 2α`` になるという一般的な幾何
  (https://www.firgelliauto.com/blogs/mechanisms/slotted-lever-quick-return 、
  https://www.firgelliauto.com/blogs/mechanisms/inverted-slider-crank-chain)。

いずれもコードは流用していません。

引数
----

* ``crank``: クランクのtransform。ローカルの ``rotate<axis>`` を回します。生成時の姿勢を、ピンがピボットから最も遠い位置
  (``θ = 0`` 、レバーは中央)とします。
* ``lever``: レバーのtransform。ピボットに置き、ローカルの ``rotate<axis>`` を動かします。クランクと同じ向きの軸で回し、
  生成時はクランクの中心の方を向けておきます。
* ``ram``: ラムのtransform(省略可)。ローカルの ``translate<ramAxis>`` を動かします。
* ``crankRadius`` ・ ``pivotDistance``: ピンの半径 r と、クランクの中心とピボットの距離 d (cm、 ``d > r`` )。生成時に固定します。
* ``ramHeight``: ピボットからラムの溝までの高さ H (cm)。containerの ``ramHeight`` で後から変えられます。
  ラムの移動軸の正の向きがレバーの +φ の傾きと逆なら負の値にします(``axis = z`` では +φ でレバーの先が -X 側へ倒れるので、
  X へ動くラムには負の値を与えます)。
* ``axis`` ・ ``ramAxis``: クランクとレバーの回転軸、ラムの移動軸(x/y/z)。
* ``connect``: Trueなら出力を接続します。既に入力がある場合は ``ValueError`` です。

計算式
------

1. ``θ = クランクの rotate<axis> - 生成時の値 + phase`` 。
2. ピボットから見たピンの位置 ``x = r sin θ`` 、 ``y = d + r cos θ`` (``d > r`` なので ``y > 0``)。
3. ``leverAngle φ = atan2(x, y)`` 、 ``rotate = 生成時のレバーの rotate<axis> + φ`` 。
4. ``slotDistance ρ = √(d² + r² + 2dr cos θ)`` (ピボットからピンまで、溝の中のブロックの位置)。
5. ``ramOffset = H x / y = H tan φ`` 、 ``ramTranslate = 生成時のラムの translate<ramAxis> + ramOffset`` 。
6. ``speedRatio = dφ/dθ = r (r + d cos θ) / ρ²`` 。負の間が戻りで ``returnStroke = 1`` 。
   往きの中央(θ = 0)で ``r / (d + r)`` 、戻りの中央(θ = 180°)で ``-r / (d - r)`` です。
7. ``swingAngle α = asin(r / d)`` 、 ``timeRatio = (180° + 2α) / (180° - 2α)`` (生成時に固定の値)。

θ = 0 では φ = 0 なので、接続してもレバーは跳ねません。 ``y > 0`` なので ``atan2`` ・割り算は折り返さず、
クランクを何回転させても連続します。履歴を持たない閉じた式なので、クランクを逆に回すとレバーも同じ経路を戻ります。

数値の加算は ``animBlendNodeAdditive`` を連ねて倍精度で行います(``plusMinusAverage`` ・ ``multiplyDivide`` は単精度のため)。
``sin`` ・ ``cos`` ・ ``atan2`` ・ ``divide`` ・ ``power`` ・ ``multDoubleLinear`` の入出力は版により長さの型なので、
係数を明示した ``unitConversion`` を挟み、UI単位(mm・ラジアン等)に関係なく同じ結果にします。
``returnStroke`` の判定だけは単精度の ``condition`` です(切り替わりの角度の誤差は1e-6度程度)。

containerのアトリビュート
--------------------------

* ``phase`` : クランクの角度に足す値(keyable)。
* ``ramHeight`` : ラムの溝の高さ H (keyable)。
* ``rotate`` : レバーの回転(出力)。
* ``leverAngle`` : 生成時からのレバーの振れ φ ( ``-α〜α`` )。
* ``slotDistance`` : ピボットからピンまでの距離 ρ ( ``d - r〜d + r`` )。溝の中のブロックを動かすのに使えます。
* ``ramOffset`` ・ ``ramTranslate`` : ラムの移動量とラムの移動(``ramTranslate`` は ``ram`` を渡したときだけ)。
* ``speedRatio`` : クランクの角速度に対するレバーの角速度の比。音・振動のドライバーに使えます。
* ``returnStroke`` : 戻りの間1、往きの間0。
* ``swingAngle`` ・ ``timeRatio`` : 振れの片側の角度 α と、往き / 戻りの時間比(固定の値)。

制限
----

* クランクはローカルの1軸の回転チャンネル( ``rotate<axis>`` )を読みます。複数軸の回転やワールドでの回転は扱いません。
* ``d > r`` の揺動形だけです。 ``d < r`` でレバーが全周回る形(Whitworth形)は、 ``atan2`` の折り返しの追跡が要るため扱いません。
* ラムはレバーの先がラムの溝を直接押す形(``H tan φ``)だけです。リンクでラムを押す形は扱いません。
* クランク・レバー・ラムの形状は作りません。レバーの長さは ``d + r`` より長くしておきます。

テスト
------

``mlrig/__tests__/unit/setups/test_quickReturn.py`` (``setups`` スイート)で、作成直後にレバーとラムが跳ねないこと、
正負・複数回転の角度でレバーの振れ・溝の距離・ラムの移動が試験側の幾何(ピンの位置とピボットを結ぶ直線)と一致すること、
振れの最大が ``±α`` で ``90° + α`` で起きることと ``timeRatio`` 、Python版( :meth:`QuickReturn.motion` )との一致と
``speedRatio`` がDGの振れの数値微分と一致すること、戻りの区間がクランクの ``180° - 2α`` ぶんであること、 ``phase`` ・
``ramHeight`` の変更、 ``axis = x`` ・ ``ramAxis = y`` ・UI単位mm/ラジアン・ラムなし、containerの所有とUndo/Redo、
引数の検査を確認します。Maya 2027で確認しています。

検証動画
--------

``tools/demo_quick_return.py`` は、新規シーンにクランク(赤、先がピン)・スロット付きレバー(緑)・ラム(緑)を正面から見る構図で作り、
クランクを等速で2回転→逆へ半回転→元へ戻す動きで、式と毎フレームの θ ・ φ ・ ρ ・ラムの移動・速さの比・往き/戻りをHUDに表示して
録画します。各フレームでDGの出力が試験側の幾何と一致し、ピンがレバーの直線の上にあることを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-quick-return.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_quick_return.py --launch
