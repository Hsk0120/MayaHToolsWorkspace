Whitworth形の早戻り機構(WhitworthQuickReturn)
================================================

``mlrig.setups.WhitworthQuickReturn`` は、等速で回るクランクのピンがレバーの溝を滑りながら、クランクの円の内側にある
ピボットのまわりでレバーを全周回し、レバーの腕の先から連接棒でラムを往復させるWhitworth形の早戻り機構の動きを求めます。
レバーはクランクと一緒に回りますが、ピボットが中心からずれているので速さが揺れ、ラムは往きはゆっくり・戻りは速く動きます。
:doc:`quick_return` (レバーが左右に振れる形)と違い、レバーが何回転しても角度が跳ばず、ラムを連接棒で押します。
Maya標準ノード(``sin`` ・ ``cos`` ・ ``atan2`` ・ ``divide`` ・ ``power`` ・ ``animBlendNodeAdditive`` ・ ``multDoubleLinear`` ・
``condition`` ・ ``unitConversion``)だけで組み、独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import WhitworthQuickReturn

   # ピンの半径3cm、ピボットはクランクの中心から1.5cm下。腕3cm、連接棒8cm
   graph = WhitworthQuickReturn.create("crank", "lever", "ram", crankRadius=3.0, pivotDistance=1.5,
                                       armLength=3.0, rodLength=8.0, name="shaper", axis="z", ramAxis="x",
                                       ramDirection=-1.0)
   owner = graph.container
   # レバーの rotateZ とラムの translateX へ出力を接続済み。クランクの rotateZ を回すだけで動く

``connect=True`` (既定)ならレバーの ``rotate<axis>`` (とラムの ``translate<ramAxis>``)へ出力を接続します。
``False`` なら接続せず、containerの ``rotate`` ・ ``ramTranslate`` を自分で使います。

参考にした考え方
----------------

* 往きと戻りの時間の比は、クランクが等速なので、それぞれの区間のクランクの角度の比になるという関係
  (https://mr-iitkgp.vlabs.ac.in/exp/quick-return-mechanism/theory.html)。
* Whitworth形の時間比 ``(360° - 2α) / 2α`` (``α = acos(d/r)`` に相当)という一般的な幾何
  (https://www.firgelliauto.com/blogs/mechanisms/whitworth-quick-return-mechanism)。資料により d と r の呼び方が
  入れ替わっているため、式はこのページで導き直し、テストで幾何と突き合わせています。

いずれもコードは流用していません。

引数
----

* ``crank``: クランクのtransform。ローカルの ``rotate<axis>`` を回します。生成時の姿勢を ``θ = 0``
  (ピンがピボットから最も遠く、レバーがクランクと同じ向き)とします。
* ``lever``: レバーのtransform。ピボットに置き、ローカルの ``rotate<axis>`` を動かします。クランクと同じ向きの軸で回し、
  生成時はピンの方を向けておきます。
* ``ram``: ラムのtransform(省略可)。ローカルの ``translate<ramAxis>`` を動かします。移動軸は、ピボットを通り生成時の
  レバーに垂直な直線に沿わせます。
* ``crankRadius`` ・ ``pivotDistance``: ピンの半径 r と、クランクの中心とピボットの距離 d (cm、 ``0 ≤ d < r`` )。
  生成時に固定します。 ``d = 0`` ではレバーはクランクと同じ速さで回ります。
* ``armLength`` ・ ``rodLength``: レバーの腕の長さ a と連接棒の長さ L (cm、 ``L > a > 0`` )。生成時に固定します。
* ``ramDirection``: ラムの移動の向き(1.0 か -1.0)。 ``axis = z`` では +φ でレバーの腕の先が -X 側へ動くので、
  ラムを -X 側に置いて X へ動かすときは -1.0 にします。
* ``axis`` ・ ``ramAxis``: クランクとレバーの回転軸、ラムの移動軸(x/y/z)。
* ``connect``: Trueなら出力を接続します。既に入力がある場合は ``ValueError`` です。

計算式
------

1. ``θ = クランクの rotate<axis> - 生成時の値 + phase`` 。
2. ピボットから見たピンの位置は ``(r sin θ, d + r cos θ)`` 。その向きを θ から測った差が
   ``lag δ = atan2(-d sin θ, r + d cos θ)`` 。 ``r > d`` なので ``r + d cos θ > 0`` で、δ は ±90° の内側を連続して動きます。
3. ``leverAngle φ = θ + δ`` 、 ``rotate = 生成時のレバーの rotate<axis> + φ`` 。回転数を追わずに連続します。
4. ``slotDistance ρ = √(d² + r² + 2dr cos θ)`` (ピボットからピンまで、 ``r - d〜r + d`` )。
5. ``speedRatio = dφ/dθ = r (r + d cos θ) / ρ²`` 。常に正で、往きの中央(θ = 0)で最小 ``r / (r + d)`` 、
   戻りの中央(θ = 180°)で最大 ``r / (r - d)`` です。
6. 腕の先は ``(a sin φ, a cos φ)`` 、ラムはピボットを通る横の直線上で連接棒の長さだけ離れた点なので、
   ``ramOffset = ramDirection × (a sin φ + √(L² - a² cos² φ) - √(L² - a²))`` 、
   ``ramTranslate = 生成時のラムの translate<ramAxis> + ramOffset`` 。
7. ラムの速さは ``a cos φ (1 + a sin φ / √(L² - a² cos² φ))`` で、 ``L > a`` なので括弧の中は正です。よって
   ``cos φ < 0`` (``d + r cos θ < 0``)の間が戻りで ``returnStroke = 1`` 。ラムの端はレバーが横を向く φ = 90°・270° です。
8. ``β = acos(d / r)`` 、 ``returnAngle = 2β`` (戻りにあたるクランクの角度)、 ``timeRatio = (180° - β) / β`` 、
   ``stroke = 2a`` (生成時に固定の値)。

θ = 0 では φ = 0 なので、接続してもレバーとラムは跳ねません。履歴を持たない閉じた式なので、クランクを逆に回すと
同じ経路を戻ります。

数値の加算は ``animBlendNodeAdditive`` を連ねて倍精度で行います(``plusMinusAverage`` ・ ``multiplyDivide`` は単精度のため)。
``sin`` ・ ``cos`` ・ ``atan2`` ・ ``divide`` ・ ``power`` ・ ``multDoubleLinear`` の入出力は版により長さの型なので、
係数を明示した ``unitConversion`` を挟み、UI単位(mm・ラジアン等)に関係なく同じ結果にします。
``returnStroke`` の判定だけは単精度の ``condition`` です。

containerのアトリビュート
--------------------------

* ``phase`` : クランクの角度に足す値(keyable)。
* ``rotate`` : レバーの回転(出力)。
* ``leverAngle`` : 生成時からのレバーの回転 φ (連続した角度)。
* ``lag`` : クランクとの角度の差 δ (``±asin(d/r)`` の範囲)。
* ``slotDistance`` : ピボットからピンまでの距離 ρ 。溝の中のブロックを動かすのに使えます。
* ``speedRatio`` : クランクの角速度に対するレバーの角速度の比。音・振動のドライバーに使えます。
* ``ramOffset`` ・ ``ramTranslate`` : ラムの移動量とラムの移動(``ramTranslate`` は ``ram`` を渡したときだけ)。
* ``returnStroke`` : 戻りの間1、往きの間0。
* ``returnAngle`` ・ ``timeRatio`` ・ ``stroke`` : 戻りのクランクの角度 2β 、往き / 戻りの時間比、ラムの行程 2a (固定の値)。

制限
----

* クランクはローカルの1軸の回転チャンネル( ``rotate<axis>`` )を読みます。複数軸の回転やワールドでの回転は扱いません。
* ``d < r`` の全周形だけです。 ``d > r`` の揺動形は :doc:`quick_return` を使います。
* ラムの直線はピボットを通り、生成時のレバーに垂直な向きだけです。ピボットからずらした直線(高さのあるラム)は扱いません。
* クランク・レバー・連接棒・ラムの形状は作りません。連接棒の向きが要る場合は、腕の先とラムの間をエイムで結びます。

テスト
------

``mlrig/__tests__/inMaya/unit/setups/test_whitworthQuickReturn.py`` (``setups`` スイート)で、作成直後にレバーとラムが
跳ねないこと、正負・複数回転の角度で連続したレバーの角度・ ``lag`` ・溝の距離・ラムの移動が試験側の幾何(ピンへの向きと、
腕の先から棒の長さで届く点)と一致すること、2回転の間にレバーの角度が跳ばずちょうど720度回ること、Python版
( :meth:`WhitworthQuickReturn.motion` )との一致と ``speedRatio`` がDGの回転の数値微分と一致すること、 ``returnStroke`` が
ラムの戻る区間と一致すること、戻りの区間がクランクの ``2β`` ぶんであることと ``timeRatio`` ・行程 ``2a`` ・端の角度、
``phase`` 、 ``axis = x`` ・ ``ramAxis = y`` ・ ``ramDirection = -1`` ・ ``d = 0`` ・UI単位mm/ラジアン・ラムなし、
containerの所有とUndo/Redo、引数の検査を確認します。Maya 2027で確認しています。

検証動画
--------

``tools/demo_whitworth_quick_return.py`` は、新規シーンにクランク(赤、先がピン)・全周回るレバー(緑)・連接棒(白)・
ラム(緑)を正面から見る構図で作り、クランクを等速で2回転→逆へ半回転→元へ戻す動きで、式と毎フレームの θ ・ φ ・ δ ・
ρ ・ラムの移動・速さの比・往き/戻りをHUDに表示して録画します。各フレームでDGの出力が試験側の幾何と一致し、
ピンがレバーの直線の上にあり、連接棒の長さが L のままであることを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを
``latest-whitworth-quick-return.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_whitworth_quick_return.py --launch
