車輪の転がり(WheelRoll)
=======================

``mlrig.setups.WheelRoll`` は、車体(またはその移動用コントローラー)の前進距離から、接地点が滑らずに転がる車輪の回転を
出力します。回転角は「前進距離 ÷ 半径」なので、車体を動かすだけで車輪が自然に回ります。
Maya標準ノードのみで構築し、エクスプレッション・独自プラグイン・フレームごとのPythonは使いません。
前のフレームの値(履歴)を使わず現在の位置だけから求めるので、どのフレームから再生・スクラブしても同じ結果になります。

.. code-block:: python

   from mlrig.setups import WheelRoll

   graph = WheelRoll.create(
       "vehicle_ctl", "wheel_front_l", radius=35.0, name="wheel_front_l_roll",
       forwardAxis="z", spinAxis="x", direction=1,
   )
   owner = graph.container
   # 車輪と同じ親の下の、TRSがidentityの出力transform(またはjoint)へ接続する
   owner.getPlug("matrix").connectTo("wheel_front_l_out.offsetParentMatrix")

車輪ごとに1つ作ります。半径の違う前輪・後輪も、それぞれの ``radius`` で同じ車体から作れます。

引数
----

* ``vehicle``: 動かす車体(またはその移動用コントローラー)のtransform。
* ``wheel``: 車輪のtransform。回転中心を車軸に置く。
* ``radius``: 車輪の半径(cm、0より大きい)。
* ``forwardAxis``: ``vehicle`` の親空間での前進方向の軸。x/y/z、既定はz。
* ``spinAxis``: ``wheel`` のローカルでの車軸(自転軸)。x/y/z、既定はx。
* ``direction``: 前進したときの自転の向きの符号。1または-1。
  上が+Y・前が+Z・車軸がXなら、+X回転で前側が下がる(前へ転がる)ので1です。

``radius`` と ``offset`` (足す角度、度、既定0)はcontainerのアトリビュートとして、生成後も変更・アニメーションできます。

計算式
------

基準は生成時の姿勢です。 ``vehicle`` の ``matrix * offsetParentMatrix`` の位置 ``T`` と、生成時の位置 ``T0`` から、

1. ``travel = (T - T0) · forwardAxis`` (親空間、cm)
2. ``spin = direction · travel / radius · 180/π + offset`` (度)
3. ``revolutions = spin / 360``
4. 出力 ``matrix = R_spinAxis(spin) · (wheelの matrix * offsetParentMatrix)`` (行ベクトル規約)

円周 ``2πr`` だけ進むとちょうど1回転し、接地点は地面に対して止まります(滑らない)。
4.は車輪のローカルの車軸まわりに回してから入力のローカル行列を掛けるので、車輪の位置や入力の回転(ステアリング等)は保たれます。
位置は ``vectorProduct`` (Point Matrix Product)で原点を変換して取り出し、UIの長さ単位によらずcmで計算します。

出力
----

* ``matrix``: 車輪の、入力と同じ親の空間の行列。
* ``travel``: 前進距離(cm)。
* ``spin``: 車輪の回転角(度)。
* ``revolutions``: 回転数。

制限
----

* 前進方向は ``vehicle`` の親空間の固定の軸です。曲がりながら進む経路の長さ(道のり)は扱わず、
  親空間の軸へ投影した直線距離で回します。カーブを走る場合は、経路に沿って動く親の下に ``vehicle`` を置くか、
  ``offset`` で補ってください。
* 横移動・上下移動は回転に含めません。
* 車輪の上下動(サスペンション)・地面の起伏による半径方向の変化は扱いません。
* 負・非一様scaleは対象外です。
* 出力を別の親の下へ直接接続したり、非identityのTRSへ重ねたりすると二重変換になります。

テスト
------

``mlrig/__tests__/test_setup_wheel_roll.py`` (``setups`` スイート)で、回転した親の下の車体と、回転を持つ車輪について、
生成直後に出力が入力と一致すること、前進方向の移動だけを数え横・上下の移動を含めないこと、円周だけ進むと1回転すること、
接地点が滑らないこと(車体を1e-3cm動かしたときの接地点の移動が中心の移動の1%未満、回転しない入力の車輪では中心と同じだけ動くことと比較)、
前進軸・車軸・向き・半径・offsetの変更、UIの単位がm・radianの場合、引数の検査、生成のUndoを確認します。
Maya 2025・2027で確認しています。

検証動画
--------

``tools/demo_wheel_roll.py`` は、新規シーンに車体(灰)、地面、回らない入力の車輪(赤・半透明)と、
スポークと黄色の印を付けた出力の車輪(緑)を横から見る構図で作り、式と毎フレームの入力値・DG出力をHUDに表示して録画します。
半径3cmの前後輪で、円周 ``2πr`` (18.85cm)の前進でちょうど1回転→さらに前進→後退→横移動(回転しない)→基準への復帰を、
276フレーム・24fpsで記録します。各フレームで、回転角が式と一致すること、出力行列が期待値と一致すること、
接地点の滑りの比率(車体を微小量動かしたときの接地点の移動÷車体の移動)が0.01未満であることを判定します
(録画では最大0.0035。行列の浮動小数の誤差による値です)。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` (``verification.mp4`` ・ ``result.json`` ・
``wheel-roll.ma``)に保存し、最新のフォルダーを ``latest-wheel-roll.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_wheel_roll.py --launch
