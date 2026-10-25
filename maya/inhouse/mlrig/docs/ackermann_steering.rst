車の前輪の切れ角(AckermannSteering)
====================================

``mlrig.setups.AckermannSteering`` は、1つの切れ角(またはハンドルの回転)から、左右の前輪の角度を
アッカーマンの幾何で求めます。曲がるときは内側の前輪が外側の前輪より小さな円を回るので、内輪を外輪より大きく切ると、
両輪の車軸の延長が後輪の軸の延長上の1点(旋回中心)で交わり、タイヤが横に滑らない向きになります。
左右を同じ角度で回すだけのリグより、曲がるときの前輪の見た目が自然になります。
Maya標準ノード(``composeMatrix`` ・ ``vectorProduct`` ・ ``multiplyDivide`` ・ ``plusMinusAverage`` ・ ``angleBetween`` ・
``animBlendNodeAdditiveDA``)だけで組み、独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import AckermannSteering

   # 前+Z・左+X・上+Y の車。左の前輪が正の rotateY で左へ向く。輪距は車輪の位置から測る
   graph = AckermannSteering.create("frontLeft_wheel", "frontRight_wheel", 260.0, name="steering",
                                    axis="y", driver="steeringWheel.rotateZ", driverRatio=-1.0 / 15.0)
   owner = graph.container
   # ハンドルを回すと左右の前輪の rotateY が駆動される。owner.ackermann を0にすると平行に切れる

``connect=True`` (既定)なら左右の車輪の ``rotate<axis>`` へ出力を接続します。 ``False`` なら接続せず、
containerの ``leftAngle`` ・ ``rightAngle`` を自分で使います。

参考にした考え方
----------------

* Lester Banks の記事「Creating a More Accurate Streering Rig in Maya Employing the Ackermann Steering Geometry」
  (表記は記事のまま): 内輪と外輪は半径の違う円を回るので、アッカーマンのステアリングに似たリンクの配置で
  前輪の切れ方をより本物らしくするという考え方。この部品はリンクを組まず、同じ幾何を式で求めます。
* Firgelli Automations「Ackermann Steering Linkage Mechanism」と edumech「Ackermann Principle」:
  アッカーマンの条件 ``cot(δo) - cot(δi) = T / L`` (内輪の角度 δi、外輪の角度 δo、輪距 T、軸距 L)と、
  内輪は小さい半径を回るので外輪より大きく切るという説明。
* 実車やゲームの車両の設定で一般的な「アッカーマンの割合」(0で平行、1でアッカーマンの幾何、その間を混ぜる)の考え方。

いずれもコードは流用していません。

引数
----

* ``left`` ・ ``right``: 左右の前輪のtransform。 ``axis`` の正の回転で車輪が ``left`` の側へ向く向きにします
  (前+Z・上+Y の車なら、左の前輪が +X 側で ``rotateY`` が正のとき左へ向きます)。正の切れ角では ``left`` が内輪です。
* ``wheelBase``: 軸距(前輪の軸と後輪の軸の距離、cm)。
* ``trackWidth``: 輪距(左右の前輪の距離、cm)。省略すると生成時の左右の車輪のワールド位置の距離を測ります。
  角度は ``trackWidth / wheelBase`` の比だけで決まるので、UI単位によらず2つは cm で渡します。
* ``axis``: 車輪のローカルの切る軸(x/y/z)。
* ``driver``: 切れ角を駆動する角度のplug(ハンドルの ``rotateZ`` など、省略可)。 ``driverRatio`` はハンドルの回転に対する切れ角の割合
  (運転席から見た回す向きと切れる向きを合わせるには負の値も使います)。
* ``ackermann``: アッカーマンの割合の初期値(0〜1)。
* ``connect``: Trueなら左右の車輪の ``rotate<axis>`` へ出力を接続します。既に入力がある場合は ``ValueError`` です。

計算式
------

中央の切れ角(後輪の軸の中央から見た、仮想の中央の前輪の角度)を ``δ`` 、軸距を ``L`` 、輪距を ``T`` 、
内輪の側を ``s = +1`` (``left``)、外輪の側を ``s = -1`` (``right``)とします(右へ曲がる負の δ では、式のまま左右が入れ替わります)。

1. ``driver`` を渡した場合は ``δ = (driver - 生成時の値) * driverRatio`` 。
2. 旋回半径 ``R = L / tanδ`` に対して、各車輪の角度は ``tan(δ_s) = L / (R - s*T/2)`` 。
   ``δ = 0`` で割らないよう、 ``δ_s = atan2(L*sinδ, L*cosδ - s*(T/2)*sinδ)`` として求めます
   (:meth:`AckermannSteering.angles` が同じ式のPython版)。
3. ``<side>Angle = ackermann * δ_s + (1 - ackermann) * δ`` 。
4. 車輪の ``rotate<axis> = 生成時の値 + <side>Angle`` 。

``sinδ`` ・ ``cosδ`` は ``composeMatrix`` で Z 回りに δ 回した行列と ``vectorProduct`` で (1, 0, 0) を回した方向、
``atan2`` は ``angleBetween`` の ``euler`` の Z(符号付きの角度)で求めます。生成時の δ は0なので跳ねません。
角度は角度のまま、距離は単位を持たない値として渡し、 ``angleBetween`` の ``vector2`` へは係数1の ``unitConversion`` を明示するので
(版によって ``vector2`` が長さの型で、mmでは自動の単位変換が入るため)、UI単位が mm・ラジアンでも同じ結果です。

containerのアトリビュート
--------------------------

* ``steer``: 中央の切れ角(keyable。 ``driver`` を渡した場合は駆動されます)。
* ``wheelBase`` ・ ``trackWidth``: 軸距・輪距(keyable、cm)。変えるとすぐに角度が変わります。
* ``ackermann``: アッカーマンの割合(keyable、0〜1)。
* ``driverRatio``: ``driver`` に掛ける割合(keyable)。
* ``leftAngle`` ・ ``rightAngle``: 左右の前輪の角度(出力、生成時の値を含まない)。

制限
----

* 前輪の2輪だけを切ります(後輪操舵・4輪操舵・多軸の車両は扱いません)。車輪が転がる回転は :doc:`WheelRoll <wheel_roll>` と組み合わせます。
* 旋回中心は後輪の軸の延長上と仮定します。キングピンの傾き・キャスター・トーの初期値・タイヤの滑り角は扱いません(生成時の回転はそのまま足します)。
* 車輪は1軸のローカルの回転で切ります。車体の傾き(ロール)・サスペンションの上下は別の仕組みで与えます。
* ``|δ|`` が90度に近いと内輪の角度が90度を超えます(旋回中心が輪距の内側に入る)。切れ角の上限は設けていません。

テスト
------

``mlrig/__tests__/test_setup_ackermann_steering.py`` (``setups`` スイート)で、回転・移動した車体の下に初期の回転を持つ左右の前輪を作り、
作成直後に回転が変わらないこと、正負の切れ角で旋回半径から独立に求めた角度とPython版に一致し内輪が外輪より大きく切れること、
両輪の車軸の延長が後輪の軸の延長上の同じ点( ``R = L/tanδ`` の位置)で交わること、 ``ackermann`` の割合と軸距・輪距の変更、
ハンドルの ``driver`` と ``driverRatio`` ・ ``axis = z`` ・ ``connect=False`` 、UI単位 mm・ラジアン、containerの所有とUndo/Redo(接続も戻る)、
引数の検査を確認します。Maya 2025・2027で確認しています。

検証動画
--------

``tools/demo_ackermann_steering.py`` は、新規シーンに真上から見た車(車体・4つの車輪の箱。アッカーマンの前輪は緑、比較用に左右を同じ角度で切る前輪は赤)と、
緑の車の両輪の車軸の延長線・後輪の軸の延長線を作り、切れ角を左→右→大きく左→ackermannを0へ→元へ戻す動きで、式と毎フレームの
切れ角・左右の角度・旋回半径・延長線の交点の距離をHUDに表示して録画します。各フレームで角度が式と一致し、緑の車の両輪の車軸が
後輪の軸の延長上の1点で交わることを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-ackermann-steering.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_ackermann_steering.py --launch
