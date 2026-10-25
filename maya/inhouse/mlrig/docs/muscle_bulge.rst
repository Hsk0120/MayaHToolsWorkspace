筋肉の膨らみ(MuscleBulge)
==========================

``mlrig.setups.MuscleBulge`` は、肘・膝・指などの子の関節を曲げたときに、親の骨(上腕・大腿など)の上に置いた
補助骨を膨らませ、外側へ押し出す行列を作ります。スキンのウェイトをこの補助骨へ少し分けると、
曲げたときの筋肉の盛り上がりや、曲げた内側の形が痩せるのを補えます。
Maya標準ノード(``vectorProduct`` ・ ``angleBetween`` ・ ``setRange`` ・ ``multiplyDivide`` ・ ``composeMatrix`` など)だけで組み、
独自プラグインやフレームごとのPython・Set Driven Keyは使いません。

.. code-block:: python

   from mlrig.setups import MuscleBulge

   graph = MuscleBulge.create(
       "upperArm_jnt", "elbow_jnt", name="bicepsBulge",
       axis="x", pushAxis="y", position=0.5,
       startAngle=60.0, fullAngle=140.0, bulge=0.4, push=0.5,
   )
   owner = graph.container
   # 補助骨を上腕の子に置き、translate/rotate/scaleを0/0/1のまま、matrixをoffsetParentMatrixで受ける
   owner.getPlug("matrix").connectTo("biceps_helper.offsetParentMatrix")

``elbow_jnt`` を曲げると、曲げ角が ``startAngle`` を超えたところから補助骨が膨らみ始め、 ``fullAngle`` で最大になります。
``startAngle`` ・ ``fullAngle`` ・ ``bulge`` ・ ``push`` ・ ``position`` はcontainerのkeyableなアトリビュートで、作成後も変更できます。

参考にした考え方
----------------

補助骨で筋肉の膨らみを表現する一般的な方法のうち、次の考え方を標準ノードの計算へ置き換えました。コードは流用していません。

* 補助骨は主な骨の上の機械的に決まる位置(骨と骨の中間や1/3の位置など)に置く。体形を変えても骨の長さに対する割合で
  付いて行くので、形との相対位置がずれにくい( ``position`` は現在の骨の長さに対する割合)。
* 曲げのドライバーにはEuler角を使わない。ここでは子の骨の長手軸が何度傾いたか(ひねりを含まない曲げの大きさ)を使うので、
  90度を超える曲げや複数の軸の回転でも値が飛ばない。
* ドライバーの範囲は普段の可動域より広く取る(手首で110度、肘で140〜160度程度)。
* 膨らみは曲げ始めから少しずつではなく、ある程度曲がってから急に出すと、風船のように見えず柔らかい印象になる。
  ここでは ``startAngle`` から ``fullAngle`` の間をsmoothstepでつなぐ。
* 曲げたときにシルエットが直線的にならないよう、補助骨を少し外側へ押し出す( ``push`` )。

曲げ角を半分だけ受け継ぐ関節の補助骨(半回転)は :doc:`rotation_follow` ・ :doc:`bend_correction` 、
ひねりによる痩せは :doc:`twist_distribution` ・ :doc:`length_compensation` を組み合わせます。

引数
----

* ``parent``: 補助骨を載せる骨のtransform。補助骨はこの骨の向きを保ちます。
* ``joint``: ``parent`` の直接の子で、曲げ角を測る関節。生成時の向きを曲げ角0とします。
* ``axis``: 長手軸x/y/z(既定x)。 ``joint`` のこの軸の傾きを曲げ角とし、補助骨はこの軸に直交する2軸を膨らませます。
* ``pushAxis``: 押し出す向き( ``parent`` のローカル軸)。x/y/zと負の向きの-x/-y/-z(既定y)。
* ``position``: ``parent`` から ``joint`` までのどの割合に置くか(0〜1、既定0.5)。
* ``startAngle`` ・ ``fullAngle``: 膨らみ始める角度と最大になる角度(度、 ``0 <= startAngle < fullAngle <= 180`` 、既定45・135)。
* ``bulge``: 最大のときに2軸のscaleへ足す量(既定0.3で1.3倍)。
* ``push``: 最大のときに押し出す距離(cm、既定0.5)。

計算式
------

角度は度、距離はcmです。

1. 曲げ角 ``bendAngle = angle(d0, d)`` 。 ``d`` は ``parent`` の空間で見た ``joint`` の ``axis`` の向き
   ( ``joint.matrix * joint.offsetParentMatrix`` で変換して正規化)、 ``d0`` は生成時の ``d`` (定数)。
   ``angleBetween`` のラジアンは ``unitConversion`` で度へ明示的に変換するので、UIの角度単位によりません。
2. ``t = clamp((bendAngle - startAngle) / (fullAngle - startAngle), 0, 1)`` 、 ``weight = t*t*(3 - 2t)`` 。
3. ``scale = 1 + bulge * weight`` 、 ``offset = push * weight`` 。
4. ``matrix = S · T`` ( ``parent`` の空間)。 ``S`` は ``axis`` が1、他の2軸が ``scale`` の拡大、
   ``T`` は回転なしで、移動 ``position * (jointの現在の位置) + pushAxis * offset`` 。
   ``worldMatrix = matrix · parent.worldMatrix`` 。

生成時は ``bendAngle = 0`` なので ``weight = 0`` 、補助骨は ``parent`` の向きのまま骨の途中に置かれ、膨らみません。
``joint`` を長手軸回りにひねるだけでは ``d`` が変わらないので、膨らみません。

出力
----

* ``matrix``: ``parent`` の空間の補助骨の行列。 ``parent`` の子に置いた補助骨の ``offsetParentMatrix`` へ接続します。
* ``worldMatrix``: 補助骨のワールド行列。
* ``bendAngle``: 曲げ角(度)。他の補正のドライバーにも使えます。
* ``weight``: 膨らみの割合(0〜1)。
* ``scale`` ・ ``offset``: 現在の膨らみのscaleと押し出しの距離(cm)。

制限
----

* 曲げ角は向きの差の大きさだけで、曲げる向き(内側・外側・横)は区別しません。向きごとに違う膨らみが必要なら、
  :doc:`cone_reader` の重みやPose RBFを組み合わせます。
* 180度を超える曲げは扱いません(角度は0〜180度)。
* ``parent`` と ``joint`` の長手軸は同じ ``axis`` である前提です。負・非一様scaleの骨は対象外です。
* 体積を厳密に保つ計算ではありません。 ``bulge`` ・ ``push`` は見た目で調整する量です。

テスト
------

``mlrig/__tests__/test_setup_muscle_bulge.py`` (``setups`` スイート)で、回転した親の下の上腕・肘(jointOrientと初期回転を持つ)について、
OpenMayaで独立に求めた曲げ角・割合・行列と、出力・補助骨のワールド行列が一致すること(各方向の曲げ・90度超・開始前・最大以降)、
作成直後に膨らまないこと、ひねりだけでは膨らまないこと、アトリビュートの変更と骨の長さの変更の反映、長手軸y、
UIの角度単位がradianの場合、containerの所有とUndo/Redo、引数の検査を確認します。Maya 2025・2027で確認しています。

検証動画
--------

``tools/demo_muscle_bulge.py`` は、新規シーンに上腕・前腕と、上腕の中央の補助骨(緑、膨らみを示す半透明の楕円体)を作り、
式と毎フレームの曲げ角・ ``weight`` ・ ``scale`` ・ ``offset`` をHUDに表示して録画します。
肘を0→170度まで曲げて戻し、ひねりだけの区間と、斜めに曲げる区間を記録し、各フレームで独立計算と一致することを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-muscle-bulge.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_muscle_bulge.py --launch
