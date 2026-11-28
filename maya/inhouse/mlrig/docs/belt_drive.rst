ベルト伝動(BeltDrive)
======================

``mlrig.setups.BeltDrive`` は、2つのプーリーにかかるベルトを、駆動プーリーの回転 ``rotation`` 1つで動かします。
軸間距離と2つの半径から、ベルトの上下の直線部(2円の共通接線)の位置・向き・長さ、プーリーへの巻き付け角、
ベルトの長さ、従動プーリーの回転を出力します。ファンベルト・ミシン・コンベヤ・自転車のチェーンのように
「2つの輪に帯がかかる」部品を、半径や軸間距離を変えても帯が輪から離れないように組めます。
平行掛け(オープン)と十字掛け(クロス。ベルトが途中で交差し、従動プーリーが逆に回る)を ``crossed`` で切り替えます。
Maya標準ノードのみで構築し、エクスプレッション・独自プラグイン・フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import BeltDrive

   graph = BeltDrive.create("motorShaft", driverRadius=2.0, drivenRadius=1.0, distance=6.0, name="fanBelt")
   owner = graph.container
   # ワールド直下(または親の変換がidentity)でTRSがidentityのtransformの、offsetParentMatrixへ接続する
   owner.getPlug("driverMatrix").connectTo("driverPulley.offsetParentMatrix")
   owner.getPlug("drivenMatrix").connectTo("drivenPulley.offsetParentMatrix")
   owner.getPlug("upperSpanMatrix").connectTo("beltUpper.offsetParentMatrix")
   owner.getPlug("lowerSpanMatrix").connectTo("beltLower.offsetParentMatrix")
   # 直線部の部品は、ローカル+Xへ長さ1で作り、scaleXへ spanLength をつなぐと接点から接点まで伸びる
   owner.getPlug("spanLength").connectTo("beltUpper.scaleX")
   owner.getPlug("rotation").set(90.0)   # 従動プーリーは 90 * 2 / 1 = 180度回る

:doc:`gear_train` は歯数の比で回転だけを伝えます。BeltDriveは回転の比に加えて、ベルトの形(接線と巻き付け)を求めます。
閉じた曲線に沿って板を巡回させる :doc:`tread_belt` と組み合わせる場合は、 ``travel`` (ベルトの送り量)を
TreadBeltの ``distance`` へ接続します。

引数
----

* ``base``: 土台のtransform。原点が駆動プーリーの中心、+Xが従動プーリーの向き、Zが回転軸です。Noneならワールド原点。
* ``driverRadius``: 駆動プーリーの半径 ``r1`` (cm)。既定は2。
* ``drivenRadius``: 従動プーリーの半径 ``r2`` (cm)。既定は1。
* ``distance``: 軸間距離 ``d`` の初期値(cm)。既定は6。
* ``crossed``: Trueなら十字掛け、Falseなら平行掛け。既定はFalse。

``rotation`` ・ ``driverRadius`` ・ ``drivenRadius`` ・ ``distance`` ・ ``crossed`` はcontainerのアトリビュートとして、
生成後も変更・アニメーションできます。

計算式
------

土台の空間で、駆動プーリーの中心 ``O = (0, 0)`` 、従動プーリーの中心 ``C = (d, 0)`` とします。
接点へ向かう半径の向きを ``n = (cosθ, sinθ)`` とすると、共通接線の条件は ``n · (C - O) = r1 - sign · r2`` です
(``sign`` は平行掛けで +1、十字掛けで -1)。

1. ``k = r1 - sign · r2`` (平行掛けは半径の差、十字掛けは半径の和)
2. 止めた軸間距離 ``d = max(distance, |k|, 0.001)`` 、足りない量 ``excess = distance - d`` (0以下)
3. 直線部の長さ ``L = sqrt(d² - k²)``
4. 接点の角度 ``θ = atan2(L, k)`` (``= acos(k / d)`` 。軸間の線から、駆動側の上の接点へ向かう半径までの角度)
5. 上の直線部: 駆動側の接点 ``r1 · (cosθ, sinθ)`` から、向き ``(sinθ, -cosθ)`` へ ``L`` 。
   下の直線部: 駆動側の接点 ``r1 · (cosθ, -sinθ)`` から、向き ``(sinθ, cosθ)`` へ ``L``
6. 巻き付け角: 駆動側 ``360° - 2θ`` 、従動側は平行掛けで ``2θ`` 、十字掛けで ``360° - 2θ``
7. ベルトの長さ ``beltLength = 2L + r1 · 駆動側の巻き付け + r2 · 従動側の巻き付け`` (角度はradian)
8. 回転の比 ``ratio = sign · r1 / r2`` 、従動プーリーの回転 ``drivenRotation = ratio · rotation`` 、
   ベルトの送り ``travel = r1 · rotation`` (radian)
9. 出力(行ベクトル規約): ``driver = R_z(rotation) · base`` 、 ``driven = R_z(drivenRotation) · T(d, 0, 0) · base`` 、
   ``upperSpan = R_z(θ - 90°) · T(r1·cosθ, r1·sinθ, 0) · base`` 、
   ``lowerSpan = R_z(90° - θ) · T(r1·cosθ, -r1·sinθ, 0) · base``

5.の従動側の接点は ``C + sign · r2 · (cosθ, ±sinθ)`` で、駆動側の接点から直線部の向きへ ``L`` 進んだ点と一致します。
半径が同じ平行掛けでは ``k = 0`` 、 ``θ = 90°`` で、直線部は軸間の線に平行、巻き付けは両方180度です。
駆動側が大きい平行掛けでは ``θ < 90°`` で、駆動側の巻き付けが180度より大きく、従動側が小さくなります。

出力
----

* ``driverMatrix`` ・ ``drivenMatrix``: 2つのプーリーのワールド行列(それぞれの中心が原点、Z軸まわりに回る)。
* ``upperSpanMatrix`` ・ ``lowerSpanMatrix``: ベルトの直線部のワールド行列。原点は駆動側の接点、Xが従動側の接点への向きで、
  ローカル ``(spanLength, 0, 0)`` が従動側の接点です。上の直線部のYはベルトの外側、下の直線部のYは内側を向きます。
* ``clampedDistance``: 共通接線が引ける範囲で止めた軸間距離。
* ``excess``: 軸間距離の足りない量(近すぎると負、範囲内は0)。
* ``spanLength``: 直線部の長さ ``L`` 。 ``beltLength``: ベルト1周の長さ。 ``travel``: ベルトの送り量。
* ``tangentAngle``: 接点の角度 ``θ`` 。 ``driverWrap`` ・ ``drivenWrap``: 巻き付け角。
* ``ratio``: 回転の比(十字掛けは負)。 ``drivenRotation``: 従動プーリーの回転。

長さはUIの長さの単位、角度はUIの角度の単位で表示されます(内部はcm・radianで、自動の unitConversion は作りません)。

制限
----

* ベルトの長さは一定に保ちません。軸間距離・半径を変えると ``beltLength`` が変わります(実際のベルトは伸びないので、
  長さを保つにはテンショナーが要ります)。たるみ・伸び・滑りも扱いません。
* プーリーは2つで、同じ面にあり、回転軸が平行な場合だけです。3つ以上のプーリー・テンショナー・ねじれたベルトは扱いません。
* 平行掛けで ``distance < |r1 - r2|`` (一方の円がもう一方の中に入る)、十字掛けで ``distance < r1 + r2`` (円が重なる)と
  共通接線が引けないため、その端で止めて ``excess`` へ足りない量を出します。
* 巻き付いた部分(弧)の形は出力しません。弧の部品は、プーリーと同じ中心の円の一部を ``tangentAngle`` で切って作ってください。
* 直線部の行列は回転では動きません(ベルトが流れる見た目は、 ``travel`` で模様や :doc:`tread_belt` の板を送ってください)。
* 土台の負・非一様scaleは対象外です。出力は土台のワールド行列を含むので、変換を持つ親の下のtransformへ接続すると二重変換になります。

テスト
------

``mlrig/__tests__/inMaya/unit/setups/test_beltDrive.py`` (``setups`` スイート)で、移動・回転した土台について、
平行掛け・十字掛け・同じ半径・従動側が大きい場合の値が式と一致すること、直線部の両端が2つの円周上にあり半径に垂直であること
(角度の式から独立な接線の条件)、平行掛けは同じ側のまま・十字掛けは反対側へ渡ること、 ``beltLength`` が直線部と弧を
折れ線で測った長さと一致すること、近すぎる軸間距離で止まり離すと元へ戻ること、土台の移動、UIの単位がradian・meterの場合、
引数の検査、生成のUndoを確かめます。Maya 2027で確認しています。

検証動画
--------

``tools/demo_belt_drive.py`` は、新規シーンに2つのプーリー(緑=駆動、青=従動)とベルトの直線部(黄)、入力の軸間距離の位置を示す
輪(赤・半透明)を正面から見る構図で作り、式と毎フレームの入力値・DG出力をHUDに表示して録画します。駆動プーリーを回す→
軸間距離を広げる・縮める→従動プーリーを大きくする→十字掛けへ切り替える→十字掛けの端(``r1 + r2``)より近づけて止まり
``excess`` が負になる→範囲へ戻す→平行掛けへ戻して端(``|r1 - r2|``)より近づける→最初の状態へ戻る、を記録します。
各フレームで、DGの値が式と一致すること、直線部の両端が円周上にあり半径に垂直であることを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` (``verification.mp4`` ・ ``result.json`` ・
``belt-drive.ma``)に保存し、最新のフォルダーを ``latest-belt-drive.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_belt_drive.py --launch
