顎の開閉(JawHinge)
==================

``mlrig.setups.JawHinge`` は、顎の開き角(Pitch)を閉じた姿勢の側だけ柔らかく止め、開き角に比例して顎を前へ滑らせる
行列を出力します。人の顎は開くときに回転だけでなく下顎頭が前へ滑るため、回転だけの顎より口の開きが自然になります。
また、アニメーションやドライバーの重なりで顎が閉じた姿勢を越えて上顎へめり込む入力を、 ``softness`` 度の手前で止めます。
Maya標準ノードのみで構築し、独自プラグインやフレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import JawHinge

   graph = JawHinge.create(
       "jaw", name="jaw_hinge", pitchAxis="x", yawAxis="y", openDirection=1,
       softness=2.0, slide=(0.0, 0.0, 0.02),
   )
   owner = graph.container
   # 入力と同じ親空間、TRSがidentityの出力transform(またはjoint)へ接続する
   owner.getPlug("matrix").connectTo("jaw_out.offsetParentMatrix")

顎のtransformは回転中心を顎関節に置き、口を閉じた姿勢で生成します。生成時の姿勢が「閉じた姿勢(0度)」になります。

引数
----

* ``jaw``: 親transformを持つ顎のtransform。
* ``pitchAxis``: 親空間で顎を開閉する軸。x/y/z、既定はx。
* ``yawAxis``: 親空間で顎を左右へ振る軸。 ``pitchAxis`` と異なる軸、既定はy。
* ``openDirection``: 顎が開く向きの、 ``pitchAxis`` まわりの回転の符号。1または-1。
  前が+Z・上が+Yの場合、+X回転で前が下がるので1です。
* ``softness``: 閉じた姿勢を越えてよい最大の角度(度、0〜45)。0で硬い制限。
* ``slide``: 開き角1度あたりの、親空間での移動量(cm)。3成分。

``softness`` と ``slide`` はcontainerのアトリビュートとして、生成後も変更・アニメーションできます。

計算式
------

基準は生成時の姿勢です。顎の ``matrix * offsetParentMatrix`` の回転 ``L`` と生成時の回転 ``J0`` から、
親空間での差分 ``D = J0⁻¹ · L`` (行ベクトル規約)を求め、Pitchを先・Yawを後に回すEuler角へ分解します
(:doc:`eyelid_follow` と同じ分解)。

1. 開き角 ``a = openDirection · pitch`` (度)、 ``w = max(softness, 0.001)``
2. ``a ≥ 0`` なら ``o = a`` 、 ``a < 0`` なら ``o = -w·(1 - exp(a/w))``
3. 出力の回転 = ``J0 · Euler(pitch = openDirection·o, 入力のYaw, 入力のRoll)``
4. 出力の位置 = 顎の現在位置 + ``slide · o``

2.は ``a = 0`` で値も傾きも連続(傾き1)で、閉じる向きへ大きく入力しても ``-w`` を越えません。
開く側は変えないため、生成時の姿勢では出力が入力と一致し、姿勢は跳ねません。
Pitchだけを置き換えて組み直すので、左右の振り(Yaw)と傾き(Roll)は入力のままです。

出力
----

* ``matrix``: 顎の、入力と同じ親空間の行列。
* ``openAngle``: 入力の開き角 ``a`` (度)。
* ``limitedOpen``: 制限後の開き角 ``o`` (度)。
* ``slideOffset``: 足した移動量 ``slide · o`` (cm、3成分)。

角度の出力は、UIの角度単位(degree/radian)によらず常に度です。

制限
----

* 前方スライドは開き角に比例する直線の近似で、下顎頭の実際の軌道(関節結節に沿った曲線)ではありません。
* ``o < 0`` (閉じすぎの入力)では、 ``slide`` の逆向きへ最大 ``w`` 度分だけ動きます。
* 歯・唇の接触判定は行いません。閉じた姿勢の判定は生成時の姿勢だけを基準にします。
* Yawが±90度に近い姿勢ではEuler分解が不定になります。
* 負・非一様scaleは対象外で、出力はscale・shearを持ちません。
* 別の親空間へ直接接続したり、非identityのTRSへ重ねたりすると二重変換になります。

テスト
------

``mlrig/__tests__/test_setup_jaw_hinge.py`` (``setups`` スイート)で、生成直後に出力が入力と一致すること、
開く側は回転がそのまま通りslideだけ前へ出ること(Yaw・Rollを含む)、閉じすぎの入力が ``-softness`` の手前で単調に止まり戻すと復帰すること、
``softness=0`` の硬い制限、 ``openDirection=-1`` と別の軸の指定、生成後のアトリビュート変更、UIの角度単位がradianの場合、
引数の検査、生成のUndoを、OpenMayaで求めた期待値と比べます。顎には基準回転(jointOrient)と位置を持たせています。
Maya 2025・2027で確認しています。

検証動画
--------

``tools/demo_jaw_hinge.py`` は、新規シーンに上顎(灰・固定)、入力の顎(赤・半透明)、出力の顎(緑)を横から見る構図で作り、
式と毎フレームの入力値・DG出力をHUDに表示して録画します。 ``softness=4`` ・ ``slide=(0, 0, 0.03)`` で、
開く(30度)・閉じる・閉じすぎの入力(-25度)での保持・復帰・左右に振りながらの開閉と閉じすぎ・基準への復帰を、
384フレーム・24fpsで記録します。各フレームで、DGの開き角と制限後の角度が式と一致すること、 ``-softness`` を越えないこと、
出力の顎のワールド回転・位置が期待値と一致すること、出力のYawが入力のYawと一致することを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` (``verification.mp4`` ・ ``result.json`` ・
``jaw-hinge.ma``)に保存し、最新のフォルダーを ``latest-jaw-hinge.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_jaw_hinge.py --launch
