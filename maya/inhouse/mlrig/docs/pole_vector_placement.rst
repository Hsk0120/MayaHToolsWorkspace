ポールベクターの位置(PoleVectorPlacement)
==========================================

``mlrig.setups.PoleVectorPlacement`` は、付け根・中間・先端の3関節(肩・肘・手首、股関節・膝・足首)の位置から、
曲がる向きの延長上にポールベクターの位置を出力します。ポールは3関節の平面上で、付け根と先端を結ぶ線に垂直な向きに置くので、
そこへIKのポールベクターを置いてもIKの曲がる平面は変わりません。FKからIKへの切り替えでポールを合わせる、
膝・肘の向きを表示する、などに使えます。Maya標準ノードのみで構築し、独自プラグインやフレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import PoleVectorPlacement

   graph = PoleVectorPlacement.create("fk_shoulder", "fk_elbow", "fk_wrist", name="arm_pole", distance=20)
   owner = graph.container
   # ワールド直下のtransformへ接続すると、FKの曲がる向きの外側20cmに置かれる
   owner.getPlug("matrix").connectTo("arm_pole_guide.offsetParentMatrix")
   # FK→IKの切り替え時は、arm_pole_guideのワールド位置をIKのポールベクターのコントローラーへ写す

引数
----

* ``start`` ・ ``mid`` ・ ``end``: 付け根・中間・先端のtransform(別々のtransform)。
* ``distance``: 中間関節からポールまでの距離(cm、0以上)。省略すると生成時の付け根→中間→先端の長さの合計の0.5倍。

``distance`` はcontainerのアトリビュートとして、生成後も変更・アニメーションできます。

計算式
------

各位置はワールド(cm)です。 ``s`` =付け根、 ``m`` =中間、 ``e`` =先端として、

1. ``t = ((m - s)·(e - s)) / |e - s|²`` 、 ``p = s + t·(e - s)`` (中間関節を付け根-先端の線へ下ろした点)
2. ``d = m - p`` (曲がる向き)、 ``bendDistance = |d|``
3. ``|d| ≥ 0.0001`` なら ``pole = m + distance · d/|d|`` 、それ以外(一直線)は ``pole = m``

位置は ``vectorProduct`` (Point Matrix Product)で各関節のワールド行列から原点を変換して取り出し、
ポールの行列は ``fourByFourMatrix`` で組むので、UIの長さ単位によらずcmで計算します。

出力
----

* ``matrix``: 回転なし・位置 ``pole`` のワールド行列。ワールド直下のtransformの ``offsetParentMatrix`` へ接続します。
* ``position``: ポールのワールド位置(cm、3成分。単位を持たない数値なので、長さのアトリビュートへ直接つなぐ場合はUIの単位に注意)。
* ``bendDistance``: 曲がりの大きさ ``|d|`` (cm)。

制限
----

* 一直線(``|d| < 0.0001cm``)では曲がる向きが決まらないため、ポールは中間関節の位置になります。
  ほぼ一直線の付近では、曲がる向きのわずかな変化でポールが大きく動きます。IKの目標を伸ばしきった姿勢でFK→IKを合わせる場合は、
  少し曲げた姿勢で合わせてください。
* ポールの位置を出力するだけで、IKハンドルへの接続やFK/IKの切り替え処理は行いません。
* 中間関節より外側に置くので、 ``distance`` が小さいと、ポールが中間関節に近くなりIKの向きが不安定になりやすくなります。

テスト
------

``mlrig/__tests__/test_setup_pole_vector_placement.py`` (``setups`` スイート)で、回転・移動した親の下の3関節について、
既定の距離、FKの4通りの姿勢でポールが式と一致し、付け根-先端の線に垂直で3関節の平面上にあり、距離が ``distance`` になること、
一直線でポールが中間関節になること、 ``distance`` の変更、UIの長さ単位がmの場合、引数の検査、生成のUndoを確認します。
Maya 2025・2027で確認しています。

検証動画
--------

``tools/demo_pole_vector_placement.py`` は、新規シーンにFKの腕(青)、ポール(緑の球)、付け根と先端を結ぶ線(黄)、
中間関節からポールへの線(緑)を斜め上から見る構図で作り、式と毎フレームの入力値・DG出力をHUDに表示して録画します。
``distance=8`` で、腕を上げる→上腕をねじる(ポールが曲がる平面と一緒に回る)→肘を曲げる→肘を伸ばしきる(ポールが肘へ)→
曲げ直す→基準への復帰を、312フレーム・24fpsで記録します。各フレームで、DGの位置が式と一致すること、
表示の球が出力の位置にあること、ポールが付け根-先端の線に垂直(90度)で3関節の平面上にあることを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` (``verification.mp4`` ・ ``result.json`` ・
``pole-vector-placement.ma``)に保存し、最新のフォルダーを ``latest-pole-vector-placement.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_pole_vector_placement.py --launch
