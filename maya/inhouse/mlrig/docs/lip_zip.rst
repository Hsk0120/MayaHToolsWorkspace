唇を口角から閉じ合わせる(LipZip)
=================================

``mlrig.setups.LipZip`` は、上唇と下唇の対になった点を、左右の口角から中央へ向かって順に閉じ合わせる行列を作ります。
口を開けたまま唇だけを閉じる、片側の口角から唇がくっついていく(いわゆるリップジップ・スティッキーリップ)表現に使います。
Maya標準ノード(``setRange`` ・ ``clamp`` ・ ``reverse`` ・ ``multiplyDivide`` ・ ``plusMinusAverage`` ・ ``blendMatrix``)だけで組み、
独自プラグインやフレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import LipZip

   upper = ["upperLip0_jnt", "upperLip1_jnt", "upperLip2_jnt", "upperLip3_jnt", "upperLip4_jnt"]
   lower = ["lowerLip0_jnt", "lowerLip1_jnt", "lowerLip2_jnt", "lowerLip3_jnt", "lowerLip4_jnt"]
   graph = LipZip.create(upper, lower, name="mouthZip", falloff=0.3)
   owner = graph.container
   # 出力はワールド行列。原点にある親の下の、TRSがidentityのtransformで受ける
   owner.getPlug("upperMatrix0").connectTo("upperLip0_driven.offsetParentMatrix")
   owner.getPlug("zipLeft").set(0.5)

``upper`` ・ ``lower`` は、ふつう唇のコントロールやカーブに沿って動く点(jointやtransform)です。
出力は入力の点自身ではなく、駆動される側(スキンに使う唇のjointなど)へ接続します。

参考にした考え方
----------------

``maya/external/mgear5`` の ``rigbits/facial_rigger/lips_rigger.py`` (MIT)は、上唇・下唇を口角の点を共有する2本の列として扱い、
口角・中央のコントロールから各点を動かします。LipZipはこの「上下の唇を口角から口角への対の列として持つ」構成を前提に、
各組を口角からの距離に応じて閉じ合わせる、一般的なリップジップの考え方を標準ノードで組みました。コードは流用していません。

* 閉じ合わせる前の唇の動き(口の開閉・唇のコントロール)はそのまま残し、閉じる量だけを別の値(``zipLeft`` ・ ``zipRight``)で足す。
* 閉じた組の上唇と下唇は、2点の間の決まった高さ(``meetHeight``)で合わさる。
* 左右は別々に閉じられ、両側から閉じると中央で合わさる。閉じる途中の組は幅(``falloff``)の中でなめらかに移る。

引数
----

* ``upper`` ・ ``lower``: 上唇・下唇の点のtransform。同じ数で、右の口角側(i=0)から左の口角側へ並べます。口角そのものは含めません。
* ``positions``: 各組の唇に沿う位置(0〜1、右の口角が0・左の口角が1)。省略すると ``(i+1)/(n+1)`` の等間隔。
* ``zipLeft`` ・ ``zipRight``: 左・右の口角から閉じる量の初期値(0〜1、既定0)。1で口全体が閉じます。
* ``falloff``: 閉じる途中の幅(0.01〜1、既定0.3)。小さいほど1組ずつはっきり閉じます。
* ``meetHeight``: 閉じたときに合わさる高さ(0=下唇の位置、1=上唇の位置、既定0.5)。

計算式
------

i番目の組の位置を ``u`` とし、左の口角からの近さを ``dL = u`` 、右の口角からの近さを ``dR = 1 - u`` とします( ``reverse`` )。

1. 片側の閉じる前線: ``low = 1 - zip * (1 + falloff)`` 、 ``high = low + falloff`` (左右で別々)。
2. ``t = clamp((d - low) / falloff, 0, 1)`` ( ``setRange`` と ``clamp``)、 ``s(t) = t*t*(3-2t)`` (smoothstep)。
3. ``weight = min(s(tL) + s(tR), 1)`` 。
4. ``meet = blend(lower, upper, meetHeight)`` 、 ``upperMatrix = blend(upper, meet, weight)`` 、 ``lowerMatrix = blend(lower, meet, weight)`` 。
   ``blend`` は ``blendMatrix`` で、位置は線形、回転はslerpで補間します。入力は各点の現在のワールド行列です。

``zip = 0`` では ``low = 1`` なので、口角そのもの( ``d = 1`` )より手前の組はすべて ``weight = 0`` です。
生成時は ``zipLeft`` ・ ``zipRight`` が0なので、出力は入力の点と一致し、作成時に姿勢が跳ねません。
``zip = 1`` では ``high = 1 - zip*(1+falloff) + falloff = 0`` なので、すべての組が ``weight = 1`` になります。
閉じた後も入力の点のワールド行列から毎回求めるので、口を開ける・唇のコントロールを動かすと、閉じた組も付いてきます。

出力
----

* ``upperMatrix<i>`` ・ ``lowerMatrix<i>``: 閉じ合わせた後の上唇・下唇の点のワールド行列。
* ``weight<i>``: その組が閉じた割合(0〜1)。確認や、唇の押しつぶし(scale)などの補正のドライバーに使えます。

``zipLeft`` ・ ``zipRight`` ・ ``falloff`` ・ ``meetHeight`` ・ ``position<i>`` はcontainerのkeyableなアトリビュートで、作成後も変更できます。

制限
----

* 出力はワールド行列です。原点以外の親の下へ接続すると二重変換になります。
* 上唇と下唇の点は同じ数の対である前提です。数が違う場合は、カーブ上の点などで数を揃えてから渡します。
* 閉じた唇が互いにめり込まない処理や、唇の厚みに合わせた押しつぶしは含みません( ``weight<i>`` を使って別に足します)。
* 合わさる位置は2点の補間で、唇の面に沿った位置ではありません。上下の点の間が大きく開いていると、閉じる途中の組が直線的に移ります。

テスト
------

``mlrig/__tests__/test_setup_lip_zip.py`` (``setups`` スイート)で、回転した頭の下の5組の点について、
:meth:`LipZip.response` の割合と、OpenMayaで独立に求めた補間の行列が出力と一致すること(左だけ・右だけ・両側・幅と高さの組み合わせ)、
作成直後に跳ねないこと、左から閉じると左の口角に近い組から順に閉じ左右が対称なこと、全体を閉じると ``meetHeight = 0`` で下唇の位置に合わさること、
入力の点・頭を動かしたときに付いてくること、 ``position<i>`` の変更、containerの所有とUndo/Redo、引数の検査を確認します。Maya 2025・2027で確認しています。

検証動画
--------

``tools/demo_lip_zip.py`` は、新規シーンに7組の唇の入力の点(赤・半透明)と出力の点(緑)を正面から見る構図で作り、
式と毎フレームの ``zipLeft`` ・ ``zipRight`` ・ ``meetHeight`` ・下唇を下げる量・各組の ``weight`` をHUDに表示して録画します。
左から閉じる→全体を閉じる→開く→右から閉じる→両側から中央で合わせる→合わさる高さを下げる→閉じたまま下唇を下げる→基準への復帰を記録し、
各フレームで独立計算と一致することを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-lip-zip.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_lip_zip.py --launch
