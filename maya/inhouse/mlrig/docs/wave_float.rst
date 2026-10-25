波の面に浮かぶ物体(WaveFloat)
==============================

``mlrig.setups.WaveFloat`` は、水面に浮かぶ物体(船・浮き・浮き輪・漂う箱など)を、時間で進む波の面に乗せる行列を作ります。
波の面は位置と時刻だけで決まる式(トロコイド波、ゲルストナー波とも呼ばれる波の和)で表すので、
シミュレーションやキャッシュを使わず、どのフレームから再生・スクラブしても同じ姿勢になります。
Maya標準ノード(``composeMatrix`` ・ ``vectorProduct`` ・ ``multiplyDivide`` ・ ``plusMinusAverage`` ・ ``fourByFourMatrix`` ・
``blendMatrix`` ・ ``multMatrix`` など)だけで組み、独自プラグインやフレームごとのPython・エクスプレッションは使いません。

.. code-block:: python

   from mlrig.setups import WaveFloat

   graph = WaveFloat.create("boat_ctrl", name="boatFloat", count=2, connectTime=True)
   owner = graph.container
   owner.getPlug("amplitude0").set(0.6)
   owner.getPlug("wavelength0").set(12.0)
   owner.getPlug("amplitude1").set(0.3)
   owner.getPlug("direction1").set(40.0, uiUnits=True)
   # 出力はワールド行列。原点にある親の下の、TRSがidentityのtransformで受ける
   owner.getPlug("matrix").connectTo("boat_driven.offsetParentMatrix")

``boat_ctrl`` はアニメーターが動かす入力で、その高さを静かな水面とします。出力は ``boat_ctrl`` 自身ではなく、駆動される側(船のjointなど)へ接続します。
波の値・ ``tilt`` ・ ``drift`` ・ ``time`` はcontainerのkeyableなアトリビュートで、作成後も変更できます。

参考にした考え方
----------------

水面を表現する一般的な方法のうち、次の考え方をリグの計算へ置き換えました。コードは流用していません。

* 水面全体の滑らかで自然な波の動きを、向き・波長・振幅の違う数個のトロコイド波の和で表す。
  各点は上下だけでなく波の進む向きにも動き(水の粒子が円を描く動き)、波の山が尖り谷が平らになる。
* 波は位置と時刻の式なので、物体を浮かべるときも、その位置の波の高さ・揺れ・面の傾きを同じ式で求めればよい。
  物体を波に乗せる処理を、毎フレーム前の結果から積み上げる計算(時間の積分)にしない。

引数
----

* ``control``: 浮かせる物体の入力のtransform。現在のワールド行列を、その位置を中心に面の傾きで回し、波の変位だけ動かして出力します。
* ``count``: 重ねる波の数(1〜8、既定2)。
* ``tilt``: 波の面の傾きを物体へ加える割合(0〜1、既定1)。0なら物体の向きは入力のままで、上下・前後にだけ動きます。
* ``drift``: 波による水平方向(前後)の揺れの割合(0〜1、既定1)。0なら上下にだけ動きます。
* ``connectTime``: Trueなら ``time1.outTime`` を ``time`` へ接続します(値はフレーム数)。Falseなら ``time`` を自分で接続・キーします。

各波 ``i`` のアトリビュート:

* ``amplitude<i>``: 振幅(cm、既定0)。既定の0では生成時に姿勢が変わりません。
* ``wavelength<i>``: 波長(cm、既定10・14・18…)。
* ``direction<i>``: 波の進む向き(度、既定0・35・70…)。+X をY軸まわりに回した水平の向きです。
* ``steepness<i>``: 波の山の尖り(0〜1、既定0.5)。水平の揺れの大きさにも掛かります。
* ``speed<i>``: 波の進む速さ(cm / ``time`` の単位、既定0.1)。

計算式
------

1. コントロールのワールド位置を ``p`` とします。波 ``i`` の向き ``D_i = (cos d_i, 0, -sin d_i)`` 、 ``k_i = 2π / wavelength_i`` 、
   位相 ``θ_i = k_i * (D_i・p - speed_i * time)`` (ラジアン)、 ``q_i = steepness_i * drift * amplitude_i`` 。
2. 変位 ``offset = Σ (q_i D_i.x cos θ_i, amplitude_i sin θ_i, q_i D_i.z cos θ_i)`` 。
3. 面の接線 ``Tx`` ・ ``Tz`` は、静かな水面の点 ``(px, 0, pz)`` が動いた先を ``px`` ・ ``pz`` で偏微分したもの(式の微分をそのまま標準ノードで組みます)。
   ``u_i = q_i k_i sin θ_i`` 、 ``v_i = amplitude_i k_i cos θ_i`` として
   ``Tx = (1, 0, 0) + Σ D_i.x (-u_i D_i.x, v_i, -u_i D_i.z)`` 、 ``Tz = (0, 0, 1) + Σ D_i.z (-u_i D_i.x, v_i, -u_i D_i.z)`` 。
4. 法線 ``N = normalize(Tz × Tx)`` 、面の回転 ``R`` は行が ``(X' = normalize(Tx), N, X' × N)`` の行列、
   ``Rt = slerp(単位行列, R, tilt)`` ( ``blendMatrix`` )。
5. ``matrix = W · T(-p) · Rt · T(p + offset)`` 。 ``W`` はコントロールの現在のワールド行列です。

sin・cosは標準ノードに無いため、 ``composeMatrix`` で位相をZ軸の回転にし、 ``vectorProduct`` で(1,0,0)を回したX・Y成分として求めます。
同じ式のPython版を ``WaveFloat.surface(x, z, time, waves, drift)`` で得られます(デモの水面の表示や確認に使えます)。

出力
----

* ``matrix``: 波に乗せた物体のワールド行列。
* ``heave``: 上下の変位(cm、確認用)。
* ``normal``: 水面の法線(確認や、しぶき・傾きに応じた補正のドライバーに使えます)。 ``tilt`` は掛かりません。

制限
----

* 出力はワールド行列です。原点以外の親の下へ接続すると二重変換になります。
* 波はワールドのXZ平面の上の水面で、静かな水面の高さはコントロールの高さです。水面の高さの基準を別のノードから取る機能はありません。
* 物体は1点(コントロールの位置)の波に乗ります。大きな船の船首・船尾で別々の波を拾う処理や、浮力・揺れの遅れ(慣性)は含みません。
* ``steepness*amplitude*k`` の和が1を超えると面が折り返して裏返るので、尖りは1未満に抑えてください。
* 水面のメッシュの変形は含みません(表示が必要なら、同じ式で変形する別の仕組みを使います)。

テスト
------

``mlrig/__tests__/test_setup_wave_float.py`` (``setups`` スイート)で、回転した親の下のコントロールについて、
試験側で独立に書いた波の変位と、差分近似で求めた面の接線から作った行列が、出力と結果のtransformのワールド行列・ ``heave`` ・ ``normal`` と一致すること
(複数の時刻・位置・コントロールの向き、 ``tilt`` ・ ``drift`` の0と途中の値)、振幅0では作成直後や時刻に関わらず跳ねないこと、
``surface()`` がDGと一致し1つの波が ``speed*time`` だけ進むこと、 ``connectTime`` でフレームに追従しフレームを戻すと同じ姿勢に戻ること、
containerの所有とUndo/Redo、引数の検査を確認します。Maya 2025・2027で確認しています。

検証動画
--------

``tools/demo_wave_float.py`` は、新規シーンに水面(青・半透明、表示のためデモ側で同じ式で変形)、入力のコントロールの船(赤・半透明)、
出力の船(緑)を斜め上から見る構図で作り、式と毎フレームの振幅・位置・ ``tilt`` ・ ``drift`` ・ ``heave`` ・水平の揺れ・法線の傾きをHUDに表示して録画します。
振幅0→波が立つ→波に乗る→コントロールを水平に動かす→ ``tilt`` 0→ ``drift`` 0→戻す→振幅0で入力へ戻るを記録し、各フレームで独立計算と一致することを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-wave-float.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_wave_float.py --launch
