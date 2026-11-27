傘の骨(Umbrella)
================

``mlrig.setups.Umbrella`` は、中棒を滑るランナー(下ろくろ)の位置1つから、放射状に並んだ親骨と受け骨の行列を出力します。
傘・パラソル・折りたたみ式のアンテナ・花びらが開く機構のように「1つの滑る部品が、周りの骨を一斉に開く」動きを、
containerの ``slide`` 1つで操作できます。三角形ができない位置では端で止まり、超えた量を ``excess`` へ出します。
Maya標準ノードのみで構築し、エクスプレッション・独自プラグイン・フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import Umbrella

   graph = Umbrella.create("umbrellaTop", count=8, ribLength=4.0, stretcherLength=5.0, name="umbrella")
   owner = graph.container
   # ワールド直下(または親の変換がidentity)でTRSがidentityのtransformの、offsetParentMatrixへ接続する
   owner.getPlug("runnerMatrix").connectTo("runner.offsetParentMatrix")
   for index in range(graph.getCount()):
       owner.getPlug("rib%dMatrix" % index).connectTo("rib%d.offsetParentMatrix" % index)
       owner.getPlug("stretcher%dMatrix" % index).connectTo("stretcher%d.offsetParentMatrix" % index)
   owner.getPlug("slide").set(3.0)   # ランナーを付け根から3cmまで押し上げる(この長さでは親骨が水平)

:doc:`scissor_lift` と同じく、入力のノードを持たず、値から部品の行列を作る機構です。
:doc:`crank_slider` はクランクの角度からスライダーの位置を求めますが、Umbrellaはその逆向きで、
スライダー(ランナー)の位置から棒の角度を求めます。

引数
----

* ``base``: 土台のtransform。原点が親骨の付け根(上ろくろ)、-Yが中棒の下向きです。Noneならワールド原点。
* ``count``: 親骨の本数(1〜64)。中棒のまわりに等間隔で並べます。既定は8。
* ``ribLength``: 親骨の付け根から、受け骨とのつなぎ目までの長さ ``a`` (cm)。親骨全体の長さではありません。既定は4。
* ``stretcherLength``: 受け骨の長さ ``b`` (cm)。既定は5。
* ``slide``: 付け根からランナーまでの距離 ``s`` の初期値(cm)。Noneなら ``a + b`` (閉じた状態)。
* ``startAngle``: 0本目の親骨の、中棒まわりの向き(度)。0で土台の+X、正で+Xから-Zへ回ります。既定は0。

``slide`` ・ ``ribLength`` ・ ``stretcherLength`` はcontainerのアトリビュートとして、生成後も変更・アニメーションできます。
本数と ``startAngle`` は生成時に決まります。

計算式
------

土台の空間で、付け根 ``O = (0, 0, 0)`` 、ランナー ``R = (0, -s, 0)`` 、つなぎ目 ``J`` (``|OJ| = a`` 、 ``|RJ| = b``)の三角形を解きます。

1. 止めたslide ``s = clamp(slide, max(|a - b|, 0.001), a + b)`` 、超えた量 ``excess = slide - s``
2. つなぎ目の深さ(中棒に沿った、付け根からの距離) ``d = (a² + s² - b²) / (2s)``
3. つなぎ目の半径(中棒からの距離) ``h = sqrt(max(a² - d², 0))``
4. 親骨の角度 ``φ = atan2(h, d)`` (中棒の下向きから。0で閉じ、90度で水平、90度を超えると反り返る)
5. 受け骨の角度 ``ψ = atan2(h, s - d)`` (中棒の上向きから)
6. k本目の向き ``α_k = startAngle + 360° · k / count``
7. 出力(行ベクトル規約): ``rib_k = R_z(φ - 90°) · R_y(α_k) · base`` 、
   ``stretcher_k = R_z(90° - ψ) · R_y(α_k) · T(0, -s, 0) · base`` 、 ``runner = T(0, -s, 0) · base``

2.は余弦定理 ``b² = a² + s² - 2as·cosφ`` から ``d = a·cosφ`` を求めたものです。
7.により、親骨のローカル ``(a, 0, 0)`` と受け骨のローカル ``(b, 0, 0)`` が同じ点 ``J`` に来ます。
行列のZは開閉の蝶番の向き(中棒まわりの接線)です。

``b > a`` のとき、 ``s = sqrt(b² - a²)`` で親骨が水平になり、さらに押し上げると水平を超えて開きます(``s = b - a`` で真上)。
``b < a`` のときは、親骨は ``asin(b / a)`` までしか開かず、それより押し上げると閉じる向きへ戻ります。
水平まで開く傘にするには ``stretcherLength`` を ``ribLength`` より長くしてください。

出力
----

* ``runnerMatrix``: ランナーのワールド行列(向きは土台と同じ)。
* ``rib0Matrix`` 〜: 親骨のワールド行列。原点は付け根、Xが親骨の向き。
* ``stretcher0Matrix`` 〜: 受け骨のワールド行列。原点はランナー、Xが受け骨の向き。
* ``clampedSlide``: 範囲 ``|a - b| 〜 a + b`` で止めた ``slide`` 。
* ``excess``: 範囲を超えた量(閉じる側へ超えると正、開く側へ超えると負、範囲内は0)。
* ``radius``: つなぎ目の中棒からの距離 ``h`` 。
* ``ribAngle`` ・ ``stretcherAngle``: ``φ`` と ``ψ`` 。開き具合に応じた布の補正シェイプなどのドライバーに使えます。

長さはUIの長さの単位、角度はUIの角度の単位で表示されます(内部はcm・radianで、自動の unitConversion は作りません)。

制限
----

* 実際の傘の止まる位置(はじき)は扱いません。開ききる位置・閉じきる位置は ``slide`` のアニメーションか、
  ``slide`` のアトリビュートの最小・最大で決めてください。出力が止まるのは三角形ができなくなる端だけです。
* 親骨はまっすぐな1本の棒として扱い、しなり・折りたたみ傘の多段の骨・布の張りは扱いません。
* 全部の親骨は同じ長さ・同じ角度で開きます(1本ずつ違う角度にはできません)。
* 計算ノードが単精度のため、閉じきる端の近く(``h`` が0に近い所)では角度に0.1度程度の誤差が出ることがあります。
* ``a = b`` で ``slide`` を0へ近づけると、ランナーが付け根へ重なる手前(0.001cm)で止めます。
* 土台の負・非一様scaleは対象外です。出力は土台のワールド行列を含むので、変換を持つ親の下のtransformへ接続すると二重変換になります。

テスト
------

``mlrig/__tests__/inMaya/unit/setups/test_umbrella.py`` (``setups`` スイート)で、移動・回転した土台について、
既定で閉じていること、 ``slide`` を変えたときの ``clampedSlide`` ・ ``excess`` ・ ``radius`` ・角度と、全部の親骨・受け骨の先が
式から求めたつなぎ目で一致すること、蝶番の向き、親骨が水平になる位置と反り返り、範囲の外で止まり範囲へ戻すと元へ戻ること、
``a > b`` での最大の角度、生成後の長さの変更と土台の移動、UIの単位がradian・meterの場合、引数の検査、生成のUndoを確かめます。
Maya 2027で確認しています。

検証動画
--------

``tools/demo_umbrella.py`` は、新規シーンに8本骨の傘(緑=親骨、青=受け骨、黄=ランナー、赤・半透明=入力の ``slide`` の位置を示す輪)を
斜め横から見る構図で作り、式と毎フレームの入力値・DG出力をHUDに表示して録画します。閉じた状態→ランナーを押し上げて開く→水平→
水平を超えて反り返る→開く側の端を超えて止まり ``excess`` が負になる→範囲へ戻す→閉じる側の端を超えて止まり ``excess`` が正になる→
閉じた状態へ戻る、を記録します。各フレームで、DGの値が式と一致すること、全部の親骨と受け骨の先が同じつなぎ目に来ることを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` (``verification.mp4`` ・ ``result.json`` ・
``umbrella.ma``)に保存し、最新のフォルダーを ``latest-umbrella.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_umbrella.py --launch
