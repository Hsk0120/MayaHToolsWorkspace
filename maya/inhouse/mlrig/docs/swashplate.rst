斜板(Swashplate)
==================

``mlrig.setups.Swashplate`` は、ヘリコプターのローターの斜板(スワッシュプレート)の動きを求めます。回らない斜板を
上下に動かす(コレクティブ)・傾ける(サイクリック)と、ローターとともに回る上の板のピッチリンクの高さが方位角ごとに
変わり、ホーンを押してブレードをピッチ軸のまわりに回します。斜板のtransformを動かし、ローターを回すだけで、各ブレードの
ピッチ角が決まります。Maya標準ノード(Maya 2026以降の ``sin`` ・ ``cos`` ・ ``atan2`` ・ ``divide`` ・ ``power`` ・
``clampRange`` と ``rowFromMatrix`` ・ ``animBlendNodeAdditive`` ・ ``multDoubleLinear`` ・ ``unitConversion``)だけで組み、
独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import Swashplate

   # 斜板とローターは同じ親の下。ブレードはローターの子で、i 枚目は rotateY = -120 i 度の向き
   graph = Swashplate.create("swashplate", "rotor", ["blade0", "blade1", "blade2"], linkRadius=2.0,
                             hornLength=1.5, maxPitch=30.0, name="mainRotor")
   owner = graph.container
   # ブレードの rotateX へ出力を接続済み。斜板の translateY・rotateX・rotateZ とローターの rotateY で動く

``connect=True`` (既定)なら各ブレードの ``rotate<pitchAxis>`` へ ``bladeRotate[i]`` を接続します。 ``False`` なら接続せず、
containerの ``bladeRotate[i]`` ・ ``bladePitch[i]`` を自分で使います。ヘリコプター・ドローン・プロペラ機の可変ピッチの
ローター、扇風機の羽根の角度など、回る羽根の角度を1つの傾く板で操る機構に使えます。 ``linkHeight[i]`` を使うと
ピッチリンクの棒も自分で動かせます。

参考にした考え方
----------------

* 斜板を軸に沿って動かすとすべてのブレードのピッチが同じだけ変わり(コレクティブ)、傾けるとローターの1回転で
  ピッチが1周期上下する(サイクリック)、という斜板の仕組み(https://en.wikipedia.org/wiki/Swashplate_(aeronautics))。
* 実機ではピッチリンクをブレードより先の方位角に付け、傾きとローター面の傾きのずれ(位相、単一ローターで約90度)を
  補います。 ``linkAzimuth`` がこのずれに当たります。式の一般形は NASA TM-102265
  (https://ntrs.nasa.gov/citations/19940008347)の目次の項目(方位角とアクチュエーターの変位によるピッチ)を手がかりに
  しましたが、本文の式は使っていません。
* リンクの高さを面の式から、ピッチ角をホーンの直角三角形から求める式は自分で確かめたものです。コードは流用していません。

引数
----

* ``swashplate``: 回らない斜板のtransform。ローカルの原点を通り、ローカルの +Y を法線とする面を斜板の面とします。
  上下に動かす・X/Zまわりに傾けます。ローターと同じ親の下に置き、生成時は法線が上(+Y の側)を向いている必要があります。
* ``rotor``: ローターのtransform。ローカルの ``rotateY`` で回します(親の +Y が回転軸)。生成時の translateX・translateZ を
  回転軸の位置に固定します。
* ``blades``: ブレードのtransformのlist。i 番目のブレードの方位角を ``ローターの rotateY + 360 i / N`` 度とし、
  ローカルの ``rotate<pitchAxis>`` を回します。ふつうはローターの子に置き、 i 番目を ``rotateY = -360 i / N`` 度の向きにします。
* ``linkRadius``: ピッチリンクの軸からの半径 Rs (cm)。 ``hornLength``: ホーンの長さ L (cm)。どちらも生成時に固定します。
* ``maxPitch``: ピッチ角の上限(度、0〜90)。リンクの高さを ``±L sin(maxPitch)`` に止めます。
* ``linkAzimuth``: ブレードの方位角からピッチリンクまでの角度(度)の初期値。containerの ``linkAzimuth`` で後から変えられます。
* ``pitchAxis`` ・ ``pitchDirection``: ブレードのピッチ軸(x/y/z)と向き(1.0 か -1.0)。リンクが上がると前縁が上がる向きが
  ピッチ軸の負の向きなら -1.0 にします。
* ``connect``: Trueなら出力を接続します。既に入力がある場合は ``ValueError`` です。

計算式
------

親の空間で、回転軸を +Y、軸の位置を ``(cx, cz)`` とします。

1. 斜板の面: 法線 ``n`` は斜板の ``matrix`` の +Y 軸の行、面が通る点 ``p`` は ``matrix`` の移動。
   ``a = nx / ny`` 、 ``b = nz / ny`` 。
2. 軸の上の面の高さ ``G = py + a (px - cx) + b (pz - cz)`` 、 ``collective = G - G0`` (G0 は生成時の G。containerの
   ``neutralHeight``)。
3. 方位角 ``ψi = ローターの rotateY + 2πi / N`` 、リンクの方位角 ``ψi + linkAzimuth`` 。リンクの位置
   ``(cx + Rs cos, ?, cz - Rs sin)`` (``rotateY`` が正のとき +X は -Z の側へ回る)を面の式
   ``n · (x - p) = 0`` へ入れると、 ``y_i = G - Rs (a cos(ψi + linkAzimuth) - b sin(ψi + linkAzimuth))`` 。
4. ``d_i = y_i - G0`` (``linkHeight[i]``)、 ``dc_i = clamp(d_i, -L sin(maxPitch), L sin(maxPitch))`` 、
   ``linkExcess[i] = d_i - dc_i`` 。
5. ``bladePitch[i] = atan2(dc_i, √(L² - dc_i²))`` (= ``asin(dc_i / L)``。ホーンの先がリンクの高さまで上がる角度)。
6. ``bladeRotate[i] = 生成時の rotate<pitchAxis> + pitchDirection × (bladePitch[i] - 生成時の bladePitch[i])`` 。

``d_i`` は ``C + A cos ψ + B sin ψ`` の形になり、等間隔のブレードの平均は ``collective`` に一致します(サイクリックの
成分は打ち消し合う)。生成時はすべての回転が変わらないので、接続しても跳ねません。履歴を持たない閉じた式なので、
ローターを何回転させても、逆に回しても同じ値になります。

数値の加算は ``animBlendNodeAdditive`` 、積は ``multDoubleLinear`` で倍精度のまま行います。数学ノードの入出力は版に
より長さ・角度の型なので、係数を明示した ``unitConversion`` を挟み、UI単位(mm・ラジアン等)に関係なく同じ結果にします。

containerのアトリビュート
--------------------------

* ``linkAzimuth`` : ブレードからピッチリンクまでの方位角のずれ(keyable)。
* ``collective`` : 軸の上の斜板の高さの変化。 ``tiltA`` ・ ``tiltB`` : 面の傾き a・b。
* ``azimuth[i]`` ・ ``linkHeight[i]`` ・ ``linkExcess[i]`` ・ ``bladePitch[i]`` ・ ``bladeRotate[i]`` : ブレードごとの方位角・
  リンクの高さ・止めた量・ピッチ角・ブレードの回転。
* ``linkRadius`` ・ ``hornLength`` ・ ``maxPitch`` ・ ``neutralHeight`` ・ ``bladeCount`` : 固定の値。

制限
----

* ローターの回転軸は親の空間の +Y に固定です(ローターのローカルの ``rotateY`` を読む)。斜板とローターは同じ親の下に置きます。
* ローターの軸の位置は生成時に固定します(ローターを後から横へ動かすと合わなくなる)。
* ピッチリンクは軸に平行(鉛直)とし、リンクの傾き・長さの変化やホーンの水平の動きは無視します。ピッチ角は
  ``asin(d / L)`` の近似です。
* ピッチ角の範囲の端は硬く止めます(柔らかい止まりは無い)。超えた量は ``linkExcess[i]`` で見られます。
* ブレードのフラッピング(上下の羽ばたき)・リードラグ・ローター面の傾きは作りません。
* Maya 2026以降の数学ノードを使うため、Maya 2025以前では作れません。

テスト
------

``mlrig/__tests__/inMaya/unit/setups/test_swashplate.py`` (``setups`` スイート)で、作成直後に跳ねないことと固定の値、
回した親の下でリンクの位置が斜板の面の上(斜板のローカルで y = 0)にあり ``L sin(pitch)`` がリンクの高さに一致し
ブレードの回転がピッチ角だけ変わること、コレクティブだけでは全ブレードが同じ ``asin(h / L)`` になること、傾けると
1回転で1周期変わり3枚の平均がコレクティブになること、上限での止まりと ``linkExcess`` ・戻したときの復帰、Python版
( :meth:`Swashplate.motion` )との一致、 ``linkAzimuth`` がローターの回転と同じずれになること、 ``pitchAxis = z`` ・
向き -1、containerの所有とUndo/Redo、引数の検査を確認します。面の上にあることは試験側でワールドマトリクスから独立に
確かめます。Maya 2027で確認しています。

検証動画
--------

``tools/demo_swashplate.py`` は、新規シーンに斜板(赤)・ローターのハブ(青)・3枚のブレード(緑)・ピッチしない参照の
板(灰色)・ピッチリンクの下端(橙)を斜め上から見る構図で作り、ローターを回し続けながら、斜板を上げる(コレクティブ)→
傾ける(サイクリック)→上限を超えて上げる→元へ戻す動きで、式と毎フレームの入力・各ブレードのリンクの高さ・ピッチ角・
超過をHUDに表示して録画します。各フレームでリンクの下端が斜板の面の上にあること、ホーンの幾何、DGとPython版の一致、
ブレードの回転を判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを
``latest-swashplate.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_swashplate.py --launch
