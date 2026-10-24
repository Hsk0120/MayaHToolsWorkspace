尻尾のうねり(WaveChain)
=======================

``mlrig.setups.WaveChain`` は、親子に並んだjoint列の各関節へ、位相を少しずつずらした正弦波の回転を重ね、
根元から先端へ進む波(尻尾・触手・魚のひれのうねり)の行列を出力します。
containerの ``phase`` を進めると波が進むので、 ``phase`` へキーを打つか時間へ接続すれば、手付けのアニメーションの上に
周期的なうねりを足せます。Maya標準ノードのみで構築し、エクスプレッション・独自プラグイン・フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import WaveChain

   graph = WaveChain.create(
       ["tail0", "tail1", "tail2", "tail3", "tail4"], name="tailWave", axis="z",
       amplitude=20, wavelength=4, rootWeight=0.3, tipWeight=1.0,
   )
   owner = graph.container
   # 入力と同じ親子に並べた出力の各transform(TRSがidentity)のoffsetParentMatrixへ接続する
   for index, out in enumerate(["tail0_out", "tail1_out", "tail2_out", "tail3_out", "tail4_out"]):
       owner.getPlug("matrix" + str(index)).connectTo(out + ".offsetParentMatrix")
   # 1秒(24フレーム)で1周期にする例: phaseへキーを打つ
   from maya import cmds
   cmds.setKeyframe(str(owner), attribute="phase", time=0, value=0)
   cmds.setKeyframe(str(owner), attribute="phase", time=24, value=360)

正弦は標準ノードで次のように求めます。角度を ``composeMatrix`` のZ回転にして、 ``vectorProduct`` (Vector Matrix Product)で
``(1, 0, 0)`` を回すと、結果のY成分が正弦になります。

引数
----

* ``joints``: 根元から先端へ、親子に並んだ2つ以上のtransform。
* ``axis``: 各関節のローカルで揺らす回転軸。x/y/z、既定はz。
* ``amplitude``: 振幅(度、-180〜180)。既定の0では生成時に姿勢が変わりません。
* ``wavelength``: 1周期あたりの関節数(0.1以上)。小さいほど細かく波打ちます。
* ``rootWeight`` ・ ``tipWeight``: 根元・先端の関節の振幅の倍率(0〜1)。間の関節は線形に補間します。

``phase`` (既定0)・ ``amplitude`` ・ ``wavelength`` ・ ``rootWeight`` ・ ``tipWeight`` は
containerのアトリビュートとして、生成後も変更・アニメーションできます。

計算式
------

関節の数を ``N`` 、根元を ``i = 0`` とします。

1. 重み ``w_i = rootWeight + (tipWeight - rootWeight) · i/(N - 1)``
2. 角度 ``θ_i = amplitude · w_i · sin(phase - 360 · i/wavelength)`` (度)
3. 出力 ``matrix_i = R_axis(θ_i) · (関節iの matrix * offsetParentMatrix)`` (行ベクトル規約)

3.は関節のローカルの ``axis`` まわりに回してから入力のローカル行列を掛けるので、関節の位置(長さ)は変わらず、
入力の回転(jointOrientやアニメーション)の上にうねりが重なります。 ``phase`` を360度進めると全関節が元の角度へ戻ります。

出力
----

* ``matrix0`` 〜 ``matrixN-1``: 各関節の、入力と同じ親の空間の行列。
* ``angle0`` 〜 ``angleN-1``: 各関節に足した角度 ``θ_i`` (度)。

角度の出力は、UIの角度単位(degree/radian)によらず常に度です。

制限
----

* 波は回転の重ね合わせだけで、うねりによる先端の位置の変化を補正しません(先端の目標を保つ処理ではありません)。
* 揺らす軸は全関節で共通の1軸です。2軸の波(8の字の動き)は、軸の違う2つを重ねる必要があります。
* 物理的な揺れ(慣性・減衰)ではありません。揺れには :doc:`secondary_motion` を使ってください。
* 負・非一様scaleは対象外です。
* 出力を入力と違う親子へ接続したり、非identityのTRSへ重ねたりすると二重変換になります。

テスト
------

``mlrig/__tests__/test_setup_wave_chain.py`` (``setups`` スイート)で、回転した親の下の、jointOrientと回転を持つ5関節について、
振幅0の生成直後に出力のワールド行列が入力と一致すること、 ``phase`` を変えたときの各関節の角度と出力行列、
360度の周期性、先端が振幅×tipWeightに達すること、軸の指定と生成後のアトリビュート変更、UIの角度単位がradianの場合、
引数の検査、生成のUndoを、Pythonの式とOpenMayaで求めた期待値と比べます。Maya 2025・2027で確認しています。

検証動画
--------

``tools/demo_wave_chain.py`` は、新規シーンに8関節のまっすぐな入力の尻尾(赤・半透明)と出力の尻尾(緑)を正面から見る構図で作り、
式と毎フレームの入力値・DG出力をHUDに表示して録画します。 ``phase`` を1フレーム15度で進め、
振幅0(生成時の姿勢)→振幅を25度へ→波が根元から先端へ進む→波長5→9関節→先端の倍率1→0.3→振幅を0へ戻して入力と一致、を
336フレーム・24fpsで記録します。各フレームで、DGの角度が式と一致すること、出力の各区間のワールドでの向きが角度の累積と一致することを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` (``verification.mp4`` ・ ``result.json`` ・
``wave-chain.ma``)に保存し、最新のフォルダーを ``latest-wave-chain.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_wave_chain.py --launch
