肋骨の呼吸(RibBreathing)
=========================

``mlrig.setups.RibBreathing`` は、1つの呼吸の値から、複数の肋骨の行列と胸骨の行列を作ります。肋骨は根元を通る固定の2つの軸の
まわりで回り、胸骨はそれに付いて動きます。Maya標準ノード( ``multMatrix`` ・ ``composeMatrix`` ・ ``decomposeMatrix`` ・
``multiplyDivide`` ・ ``plusMinusAverage`` ・ ``condition`` ・ ``unitConversion`` ・ ``distanceBetween`` ・ ``vectorProduct`` ・
``angleBetween``)だけで組み、独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import RibBreathing

   ribs = [("L_rib1_jnt", "L_rib1Mid_loc", "L_rib1Tip_loc"), ("R_rib1_jnt", "R_rib1Mid_loc", "R_rib1Tip_loc"),
           ("L_rib7_jnt", "L_rib7Mid_loc", "L_rib7Tip_loc"), ("R_rib7_jnt", "R_rib7Mid_loc", "R_rib7Tip_loc")]
   setup = RibBreathing.create("chest_jnt", ribs, name="breathing", sternum="sternum_jnt")
   owner = setup.container
   owner.getPlug("breath").set(1.0)  # 0が生成時の姿勢、1が普通に吸った状態
   # 出力はワールド行列。原点にある親の下の、TRSがidentityのtransformで受ける
   owner.getPlug("ribMatrix")[0].connectTo("L_rib1_drv.offsetParentMatrix")
   owner.getPlug("sternumMatrix").connectTo("sternum_drv.offsetParentMatrix")
   # 胸の膨らみの補正シェイプのドライバー(cm)
   owner.getPlug("expansion").connectTo("corrective.chest")

``spine`` は毎フレーム読み、 ``ribs`` と ``sternum`` は生成時の姿勢だけを使います。そのため肋骨自体をこの出力で動かしても
循環しません。 ``spine`` を出力の肋骨の子にすると循環します。

参考にした考え方
----------------

* 吸うときの肋骨の動きは、胸骨側の端が持ち上がるポンプハンドルと、中央が持ち上がって外へ開くバケットハンドルの2つで説明され、
  上の段はポンプ、下の段はバケットが主とされます(`Ribcage Biomechanics <https://wikimsk.org/wiki/Ribcage_Biomechanics>`_)。
* 実測では両方の成分が各段にあり、下の段ほど小さくなります
  (`Geometry and respiratory displacement of human ribs <https://iro.uiowa.edu/esploro/outputs/journalArticle/Geometry-and-respiratory-displacement-of-human/9984318705102771>`_)。
  肺活量いっぱいまで吸ったときの回転は第3肋骨で各11度・13度程度です。既定の10度はこの目安で、普通の呼吸ではもっと小さくなります。
* リグの一般的な作り方としては、胸の骨のスケールやブレンドシェイプで済ませる例と、肋骨と胸骨のコントローラーを作る例
  (`Houdini rib cage rig <https://80.lv/articles/this-houdini-made-rib-cage-rig-allows-creating-lifelike-breathing-animations>`_)があります。

いずれもコードは流用していません。

引数
----

* ``spine``: 胸椎のtransform。肋骨の親の空間です。
* ``ribs``: 肋骨ごとの(根元, 中央, 胸骨側の端)のtransformの並び。2本以上です。根元の行列が ``ribMatrix`` の基準で、
  中央の点はバケットの回転の向き(中央が上がる向き)を決めるのに使います。順番は問いません。
* ``sternum``: 胸骨のtransform。 ``None`` なら胸骨の出力を作りません。
* ``sternalRibs``: 胸骨に付く肋骨の ``ribs`` の番号。 ``None`` ならすべて。浮遊肋は外します。
* ``up``: ``spine`` の空間での上方向。既定は+Y。
* ``pumpAngle`` ・ ``bucketAngle``: ``breath = 1`` で重み1の肋骨を回す角度(度、0〜45)。既定は10度。
* ``minBreath`` ・ ``maxBreath``: 呼吸の値の範囲。既定は-0.5と1.5です(強く吐いた状態と深く吸った状態)。
* ``softness``: 範囲の半分に対する柔らかい区間の割合(0で硬い制限)。 ``breath = 0`` が柔らかい区間に入らない値までです。既定は0.1。

container の ``breath`` ・ ``minBreath`` ・ ``maxBreath`` ・ ``softness`` ・ ``pumpAngle`` ・ ``bucketAngle`` と、肋骨ごとの
``pumpWeight[i]`` ・ ``bucketWeight[i]`` は後から変更できます。 ``softness`` や範囲を変えて ``breath = 0`` が柔らかい区間に入ると、
生成時の姿勢から少しずれます。

計算式
------

基準は生成時の姿勢です。 ``spine`` の空間で ``H`` を根元、 ``M`` を中央、 ``T`` を胸骨側の端、 ``v = T - H`` 、 ``u`` を上方向の単位ベクトル
とします(行ベクトル規約)。

1. ``effectiveBreath = softLimit(breath, minBreath, maxBreath, softness)`` 。式は :doc:`twist_limit` と同じ指数関数です。
   ``excessBreath = breath - effectiveBreath`` 。
2. ``F_b`` を原点 ``H`` ・X軸 ``normalize(v)`` のフレーム、 ``F_p`` を原点 ``H`` ・X軸 ``normalize(v × u)`` のフレームとします。
3. ``s = (hmax - H·u) / (hmax - hmin)`` (最上段0、最下段1)から、既定の重みは ``pumpWeight = 1 - 0.5s`` 、
   ``bucketWeight = 0.5 + 0.5s`` です。
4. ``rp = effectiveBreath × pumpAngle × pumpWeight`` 、 ``rb = effectiveBreath × bucketAngle × bucketWeight × σ`` です。
   ``σ`` は ``M`` の弦からのずれ ``c`` について、 ``((normalize(v) × c)·u)`` の符号です(中央が上がる向きが正)。
5. ``ribMatrix = R0 × F_b⁻¹ × Rx(rb) × F_b × F_p⁻¹ × Rx(rp) × F_p × spineのワールド行列`` ( ``R0`` は生成時の根元の ``spine`` 空間の行列)。
   ``midMatrix`` ・ ``tipMatrix`` は同じ向きで生成時の中央・端の位置です。
6. ``expansion`` は ``spine`` の空間での中央の点の移動量の平均です(cm)。
7. 胸骨: ``Δ`` を胸骨に付く肋骨の端の平均の移動、 ``a0`` ・ ``a`` を上半分の端の平均から下半分の端の平均へのベクトルの生成時と現在の値、
   ``S0`` を生成時の胸骨の ``spine`` 空間の行列、 ``P`` をその位置の平行移動の行列として、
   ``sternumMatrix = S0 × P⁻¹ × R(a0 → a) × P × T(Δ) × spineのワールド行列`` 、 ``sternumLift = Δ·u`` です。

出力
----

* ``ribMatrix[i]``: 肋骨の根元の行列(ワールド)。
* ``midMatrix[i]`` ・ ``tipMatrix[i]``: 肋骨の中央・胸骨側の端の位置にある同じ向きの行列(ワールド)。
* ``effectiveBreath``: 制限後の呼吸の値。
* ``excessBreath``: 範囲を超えた量。
* ``expansion``: 肋骨の中央の移動量の平均(cm)。胸の膨らみの補正シェイプのドライバーに使えます。
* ``sternumMatrix``: 胸骨の行列(ワールド)。 ``sternum`` を指定したときだけあります。
* ``sternumLift``: 胸骨の上方向の移動量(cm)。 ``sternum`` を指定したときだけあります。

制限
----

* 肋骨と胸骨の閉じた連結は解きません。胸骨は端の平均に追従するので、端と胸骨の間の距離は少し変わります。肋軟骨の変形で吸収する想定です。
* 軸は生成時に ``spine`` の空間で固定します。肋骨の曲がり方の個人差や、肋骨そのものの変形は扱いません。
* 呼吸の周期は作りません。 ``breath`` にキーを打つか、別の駆動をつないでください。
* 出力はワールド行列です。原点以外の親の下へ接続すると二重変換になります。

テスト
------

``mlrig/__tests__/unit/setups/test_ribBreathing.py`` (``setups`` スイート)で、生成時の姿勢、2つの軸の回転とOpenMayaの結果の一致、
肋骨の長さ、吸ったときの向き、バケットだけのときの端の固定と左右の鏡像、重みと角度の変更、柔らかい制限、 ``expansion`` 、
胸骨の移動と傾き、 ``sternalRibs`` 、肋骨の順番、胸椎の回転・scale、生成時の入力を一度だけ読むこと、UIの単位(rad・mm・m)、
containerの所有とUndo/Redo、引数の検査を確認します。Maya 2027で確認しています。

検証動画
--------

``tools/demo_rib_breathing.py`` は、新規シーンに胸椎(灰)、5段の左右の肋骨(緑)、生成時の肋骨(薄い赤)、胸骨(黄)を作り、
吸う・範囲を超えて吸う・強く吐く・範囲を超えて吐く・戻す・胸椎を曲げて呼吸する順に動かして録画します。式と毎フレームの入力・
``effectiveBreath`` ・ ``excessBreath`` ・ ``expansion`` ・ ``sternumLift`` をHUDに表示し、各フレームで式と一致することを判定します。
録画では見やすいように角度を既定より大きい18度にしています。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-rib-breathing.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_rib_breathing.py --launch
