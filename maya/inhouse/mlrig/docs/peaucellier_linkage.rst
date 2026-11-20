ポーセリエ・リプキン機構(PeaucellierLinkage)
==============================================

``mlrig.setups.PeaucellierLinkage`` は、クランクの円運動を厳密な直線運動へ変えるポーセリエ・リプキン機構の動きを
求めます。固定点 O から長さ a の2本の腕 OA・OB を出し、辺の長さ b の菱形 APBQ をつなぐと、P と Q は O を通る直線の
上にあり ``|OP| · |OQ| = a² - b²`` (反転)になります。P を O を通る円(中心 C、 ``|OC| = r``)の上でクランクで回すと、
Q は O から ``(a² - b²) / (2r)`` 離れた直線の上だけを動きます。Maya標準ノード(Maya 2026以降の ``sin`` ・ ``cos`` ・
``atan2`` ・ ``divide`` ・ ``power`` ・ ``clampRange`` と ``animBlendNodeAdditive`` ・ ``multDoubleLinear`` ・
``unitConversion``)だけで組み、独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import PeaucellierLinkage

   # 固定点 O を原点、クランクを (2, 0) に置く。腕 5cm・菱形の辺 2cm なので、ペンは x = 5.25 の縦の直線を動く
   graph = PeaucellierLinkage.create("crank", "pen", "armA", "armB", crankLength=2.0, armLength=5.0,
                                     sideLength=2.0, name="straightLine", axis="z", penAxis="y")
   owner = graph.container
   # ペンの translateY と腕の rotateZ へ出力を接続済み。クランクの rotateZ を回すだけで動く

``connect=True`` (既定)ならペンの ``translate<penAxis>`` (と腕の ``rotate<axis>``)へ出力を接続します。 ``False`` なら
接続せず、containerの ``penTranslate`` ・ ``armARotate`` ・ ``armBRotate`` を自分で使います。回転するモーターから
ピストン・スライドを直線に押す機械部品、直線のガイドが無いのにまっすぐ動く装置、反転の幾何を見せる教材などに使えます。
O・P・Q・A・B の位置( ``pX`` 〜 ``bY``)も出力するので、菱形の4本の辺は自分で向けられます。

参考にした考え方
----------------

* 円の反転で O を通る円は直線へ写り、菱形と2本の腕の8本の棒で反転を作る、という機構の性質
  (https://en.wikipedia.org/wiki/Peaucellier%E2%80%93Lipkin_linkage 、
  https://www.cut-the-knot.org/pythagoras/invert.shtml)。
* ``|OP| · |OQ| = a² - b²`` は、菱形の中心 M と半分の対角線 h から ``a² = m² + h²`` ・ ``b² = h² + ((|OQ| - |OP|)/2)²``
  (``m = (|OP| + |OQ|)/2``)を引いて確かめた式です。

コードは流用していません。

引数
----

* ``crank``: クランクのtransform。円の中心 C に置き、ローカルの ``rotate<axis>`` を回します。生成時の姿勢を ``θ = 0``
  (P が O から最も遠い ``2r`` の位置、Q は直線と O→C の線の交点)とします。
* ``pen``: 直線の上を動く点 Q のtransform。ローカルの ``translate<penAxis>`` を動かします。直線に沿わせて置きます。
* ``armA`` ・ ``armB``: 固定点 O に置く腕のtransform(省略可)。ローカルの ``rotate<axis>`` を回します。A はクランクが
  +θ 回ったとき P が向かう側(v の正の側)の腕です。生成時の向きを θ = 0 の向き(:meth:`PeaucellierLinkage.motion` の
  ``armAngleA`` ・ ``armAngleB``)にしておくと、腕の先が A・B に一致します。
* ``crankLength`` ・ ``armLength`` ・ ``sideLength``: r・a・b (cm)。 ``0 < b < a`` 、 ``a - b < 2r ≤ a + b`` を
  満たす必要があります(菱形が θ = 0 で成り立ち、範囲が0より広い条件)。生成時に固定します。
* ``axis`` ・ ``penAxis``: クランクと腕の回転軸、ペンの移動軸(x/y/z)。
* ``penDirection`` ・ ``armDirection``: 向き(1.0 か -1.0)。直線の v の向きとペンの移動軸、腕とクランクの回転軸の正の
  向きがそれぞれ逆なら -1.0 にします。
* ``connect``: Trueなら出力を接続します。既に入力がある場合は ``ValueError`` です。

計算式
------

O を原点、O→C を u、クランクが +θ 回ったとき P が向かう側を v とします。

1. ``θ = クランクの rotate<axis> - 生成時の値 + phase`` 。
2. 菱形が成り立つのは ``a - b ≤ |OP| ≤ a + b`` の間なので、 ``θmax = 2 acos((a - b) / (2r))`` として
   ``crankAngle = clamp(θ, -θmax, θmax)`` 、 ``excessAngle = θ - crankAngle`` 。
3. ``P = (r + r cos θ, r sin θ)`` 。 ``φ = θ/2`` とすると ``P = |OP| (cos φ, sin φ)`` 、 ``|OP| = 2r cos φ`` 。
4. 反転 ``|OQ| = k / |OP|`` (``k = a² - b²``)、 ``Q = |OQ| (cos φ, sin φ)`` 。 ``qX = |OQ| cos φ = k / (2r)`` は
   θ によらず一定(直線)、 ``qY = |OQ| sin φ = (k / (2r)) tan φ`` 。
5. ``penTranslate = 生成時の translate<penAxis> + penDirection × qY`` 。
6. 腕: ``m = (|OP| + |OQ|) / 2`` 、 ``h = √(a² - m²)`` 、 ``α = atan2(h, m)`` 、 ``armAngleA = φ + α`` 、
   ``armAngleB = φ - α`` 、 ``A = a (cos armAngleA, sin armAngleA)`` (B も同様)。
   ``armARotate = 生成時の rotate<axis> + armDirection × (armAngleA - α0)`` (α0 は θ = 0 の α。B は ``+ α0``)。

DG は ``qX`` を反転の結果から実際に掛け算して求めるので、 ``qX`` が ``lineDistance`` のまま変わらないことが、
直線を保っていることの確かめになります。範囲の端では ``a² - m²`` が丸め誤差でわずかに負になるので、0で止めてから
平方根を取ります。θ = 0 ではすべての移動・回転が0なので、接続しても跳ねません。履歴を持たない閉じた式なので、
クランクを逆に回すと同じ経路を戻ります。

数値の加算は ``animBlendNodeAdditive`` 、積は ``multDoubleLinear`` で倍精度のまま行います。数学ノードの入出力は版に
より長さ・角度の型なので、係数を明示した ``unitConversion`` を挟み、UI単位(mm・ラジアン等)に関係なく同じ結果にします。

containerのアトリビュート
--------------------------

* ``phase`` : クランクの角度に足す値(keyable)。
* ``penTranslate`` : ペンの移動。 ``armARotate`` ・ ``armBRotate`` : 腕の回転(腕を渡したときだけ)。
* ``crankAngle`` ・ ``excessAngle`` : 範囲に止めたクランクの角度と、止めた量(範囲の中では0)。
* ``pX`` ・ ``pY`` ・ ``qX`` ・ ``qY`` ・ ``aX`` ・ ``aY`` ・ ``bX`` ・ ``bY`` : O から見た u・v の位置。
* ``armAngleA`` ・ ``armAngleB`` : 腕の u からの角度。 ``opDistance`` ・ ``oqDistance`` : ``|OP|`` ・ ``|OQ|`` 。
* ``crankLength`` ・ ``armLength`` ・ ``sideLength`` ・ ``inversionConstant`` (k)・ ``lineDistance`` (k / (2r))・
  ``maxAngle`` (θmax): 固定の値。

制限
----

* クランクはローカルの1軸の回転チャンネル( ``rotate<axis>`` )を読みます。複数軸の回転やワールドでの回転は扱いません。
* 範囲の端は硬く止めます(柔らかい止まりは無い)。超えた量は ``excessAngle`` で見られます。
* 菱形の4本の辺のtransformは作らず、位置( ``pX`` 〜 ``bY``)だけを出力します。
* O を通らない円(直線ではなく円弧になる)や、Hart の反転器などほかの反転器は扱いません。
* Maya 2026以降の数学ノードを使うため、Maya 2025以前では作れません。

テスト
------

``mlrig/__tests__/inMaya/unit/setups/test_peaucellierLinkage.py`` (``setups`` スイート)で、作成直後に跳ねないことと
固定の値、範囲の中の角度で腕 OA・OB が a、菱形の4辺が b、 ``|CP| = r`` 、Q が直線 ``x = k / (2r)`` の上、O・P・Q が一直線で
あること、 ``|OP| · |OQ| = k`` とシーンのクランクの先・腕の先が P・A・B に一致しペンが ``qY`` だけ動くこと、範囲の端での
止まり・ ``excessAngle`` ・NaNを出さないこと・戻したときの復帰、Python版( :meth:`PeaucellierLinkage.motion` )との一致、
``phase`` 、 ``axis = x`` ・ ``penAxis = z`` ・向き -1 ・UI単位mm/ラジアン・腕1本、containerの所有とUndo/Redo、引数の検査を
確認します。棒の長さは試験側でDGの出力の位置から独立に測ります。Maya 2027で確認しています。

検証動画
--------

``tools/demo_peaucellier_linkage.py`` は、新規シーンにクランク(赤)・2本の腕(青)・菱形の4辺(水色)・ペン(緑)と、
ペンが動くはずの直線(灰色)・P が回る円(灰色)を正面から見る構図で作り、クランクを範囲の端まで回す→端を超えて回す
→逆の端を超える→元へ戻す動きで、式と毎フレームの θ ・ ``excessAngle`` ・ ``|OP|·|OQ|`` ・ Q の位置をHUDに表示して
録画します。各フレームで棒の長さが a・b のまま、 ``qX`` が ``k / (2r)`` のまま、DGの出力がPython版と一致することを
判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを
``latest-peaucellier-linkage.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_peaucellier_linkage.py --launch
