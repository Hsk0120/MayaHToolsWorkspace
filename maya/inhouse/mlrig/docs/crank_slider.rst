クランクとピストン(CrankSlider)
===============================

``mlrig.setups.CrankSlider`` は、回るクランクのピンにコネクティングロッド(長さ ``rodLength``)で繋いだピストンを、
シリンダーの軸に沿って滑らせるワールド行列(``pistonMatrix``)と、ピンに付いたままピストンへ向くロッドのワールド行列(``rodMatrix``)を出力します。
エンジン・ポンプ・ミシン・蒸気機関車の動輪など、回転を往復の直線運動へ変える機構(往復スライダー・クランク機構)を、クランクの回転だけで動かせます。
Maya標準ノード(``multMatrix`` ・ ``vectorProduct`` ・ ``plusMinusAverage`` ・ ``multiplyDivide`` ・ ``clamp`` ・ ``unitConversion`` ・
``composeMatrix`` ・ ``pickMatrix`` ・ ``aimMatrix``)だけで組み、独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import CrankSlider

   # crankPin はクランク(Z回りに回す)の子、piston はエンジンのtransformの子でY軸の上に置く
   graph = CrankSlider.create("crankPin", "piston", name="engineCrank", axis="y", rod="conRod")
   owner = graph.container
   # 出力はワールド行列。ワールド直下の表示用transformの offsetParentMatrix へ繋ぐ
   mlib.getPlug("{}.pistonMatrix".format(owner)).connectTo("pistonGeo.offsetParentMatrix")
   mlib.getPlug("{}.rodMatrix".format(owner)).connectTo("conRodGeo.offsetParentMatrix")

参考にした考え方
----------------

* 機械のリグで、ピストン・クランク・ベルト・タイヤを連動させる一般的な作り方: アニメーターが動かすのは回転だけにして、
  他の部品はコンストレイント・エクスプレッション・ユーティリティノードで追従させる考え方。ここではエクスプレッションを使わず、
  ピストンの位置を標準ノードの式で求めます。
* 往復スライダー・クランク機構の一般的な式: クランクの半径 ``r`` ・角度 ``θ`` (上死点から)・ロッドの長さ ``L`` のとき、
  ピストンのピンの高さは ``r cosθ + sqrt(L^2 - r^2 sin^2θ)`` 。この部品はクランクの形を仮定せず、ピンの位置とシリンダーの直線から
  「ピンを中心とする半径 ``L`` の球と直線の交点」として同じ値を求めます。

コードは流用していません。

引数
----

* ``pin``: クランクのピンの位置を示すtransform(回るクランクの子に置く)。位置だけを使います。
* ``piston``: ピストンのtransform(joint可)。生成時の位置をピストンのピン、親の空間をシリンダーの空間(エンジン)にします。
* ``axis``: シリンダーの軸(ピストンの親の空間)。 ``x`` ・ ``y`` ・ ``z`` ・ ``-x`` ・ ``-y`` ・ ``-z`` または3次元の向き。ピストンがピンから離れる向きにします。
* ``rod``: ロッドのtransform(省略可)。回転中心をピンの位置に置き、生成時の姿勢を ``rodMatrix`` の基準にします。
  省略するとピンの位置で X をピストンへ、Z を機構の面の法線へ向けた枠を基準にします。
* ``normal``: 機構の面の法線(ピストンの親の空間、省略可)。既定は ``axis × (ピン - ピストン)`` 。ピンが軸の上にある姿勢(上死点・下死点)で作る場合は指定します。

計算式
------

ピストンの親の空間で、ピンの位置 ``P`` 、ピストンのピンの生成時の位置 ``X0`` 、軸の単位ベクトル ``d`` として、

``v = P - X0`` 、 ``a = dot(v, d)`` 、 ``t = a + sqrt(max(L^2 - (dot(v, v) - a^2), 0))``

``pistonMatrix = R_p * T(d * t) * S`` 、 ``stroke = t``

(``R_p`` は生成時のピストンのローカル行列、 ``S`` は親の worldMatrix、行ベクトル規約。 :meth:`CrankSlider.pistonOffset` がPython版)。
生成時はピストンがピンより軸の先にあるので ``a < 0`` 、 ``sqrt`` の中は ``a^2`` で ``t = 0`` となり、作成しても跳ねません。
ロッドは生成時の姿勢を ``pickMatrix`` (平行移動だけ)でピンの位置へ運び、 ``aimMatrix`` で生成時にピストンのピンを指していた軸をピストンのピンへ、
機構の面の法線を生成時と同じ法線へ揃えます。長さは係数1の ``unitConversion`` で数値にし、位置は単位の無いノードで計算するので、
UI単位がmmでも結果は同じです。

containerのアトリビュート
--------------------------

* ``rodLength``: ロッドの長さ(keyable、既定は生成時のピンとピストンの距離)。
* ``stroke``: ピストンの生成時の位置からの軸に沿った移動量(確認用)。
* ``pistonMatrix``: ピストンのワールド行列(出力)。
* ``rodMatrix``: ロッドのワールド行列(出力)。

制限
----

* ピストンは1本の直線の上だけを動きます。ピンが機構の面から外れても、ロッドの長さの球と直線の交点で求めます(面の外への傾きは見ない)。
* ``rodLength`` が軸からピンまでの距離より短く届かない場合、ピストンは軸の上の最も近い点に止まり、ピンとの距離は ``rodLength`` になりません。
* ピンと逆側の交点(ピストンがクランクの反対側へ回り込む解)は扱いません。
* クランク自体の回転(駆動)は扱いません。 :doc:`GearTrain <gear_train>` ・ :doc:`WheelRoll <wheel_roll>` などの出力で回せます。
* 出力はワールド行列なので、原点以外の親の下へ繋ぐと二重に変換されます。

テスト
------

``mlrig/__tests__/test_setup_crank_slider.py`` (``setups`` スイート)で、回転・移動したエンジンの下の半径2cmのクランクと長さ6cmのロッドを作り、
作成直後に生成時と一致すること、クランクを15度刻みで一周させてピストンが閉じた式の高さに来ること・ピンとの距離がロッドの長さに保たれること・
軸の上にあること・Python版と一致すること・ロッドがピンの位置からピストンへ向き法線を保つこと、ロッドのtransformを渡した場合の姿勢、
rodLength の変更と届かない短いロッド、作成後のエンジンの移動回転、軸 ``-x`` とUI単位 mm/rad、containerの所有とUndo/Redo、引数の検査を確認します。
Maya 2025・2027で確認しています。

検証動画
--------

``tools/demo_crank_slider.py`` は、新規シーンにクランク・ロッド・ピストン(緑)とシリンダーの枠を正面から見る構図で作り、
クランクを2回転させたあと ``rodLength`` を変える動きで、式と毎フレームのクランクの角度・stroke・閉じた式の値・ピンとピストンの距離をHUDに表示して録画します。
各フレームでピストンの位置が閉じた式と一致し、ピンとの距離が ``rodLength`` に保たれることを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-crank-slider.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_crank_slider.py --launch
