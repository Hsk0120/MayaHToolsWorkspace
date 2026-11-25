パンタグラフ(Pantograph)
========================

``mlrig.setups.Pantograph`` は、なぞる点の動きを固定点を中心に一定の倍率で写すパンタグラフ(平行四辺形リンク)の動きを
求めます。固定点 O から長い腕 O-A-B (``|OA| = a`` 、 ``|OB| = k a``)を出し、A からなぞる点 P へ長さ b の棒、B からペン Q へ
長さ ``k b`` の棒、P から BQ の上の点 C へ長さ ``(k - 1) a`` の棒をつなぐと、A-P-C-B は平行四辺形になり、O・P・Q は常に
一直線で ``OQ = k · OP`` になります。Maya標準ノード(Maya 2026以降の ``sin`` ・ ``cos`` ・ ``atan2`` ・ ``divide`` ・
``power`` ・ ``clampRange`` と ``animBlendNodeAdditive`` ・ ``multDoubleLinear`` ・ ``unitConversion``)だけで組み、
独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import Pantograph

   # 固定点 O を原点に、腕 4cm・棒 4cm・倍率 2。tracer を動かすと pen が2倍の動きをする
   graph = Pantograph.create("tracer", "pen", "arm", "link", armLength=4.0, linkLength=4.0, ratio=2.0,
                             name="copyArm", plane="xy", linkRelative=True)
   owner = graph.container
   # ペンの translateX・translateY と、腕・棒の rotateZ へ出力を接続済み

``connect=True`` (既定)ならペンの ``translate`` の2軸(と腕・棒の ``rotate``)へ出力を接続します。 ``False`` なら接続せず、
containerの ``penTranslateU`` ・ ``penTranslateV`` ・ ``armRotate`` ・ ``linkRotate`` を自分で使います。製図・彫刻の
写し取りの道具、伸縮するアーム(電車の集電装置や卓上ライトの平行リンク)、小さい操作を大きい動きへ広げる(または
``0 < k < 1`` で縮める)機械部品、``k < 0`` で固定点の反対側へ逆さに写す仕掛けなどに使えます。O から見た P・Q・A・B・C の
位置( ``pU`` 〜 ``cV``)も出力するので、残りの棒(B-Q と P-C)は自分で向けられます。

参考にした考え方
----------------

* 平行四辺形リンクで相似な三角形 O-A-P と O-B-Q を保つと、Q が P の ``k`` 倍の位置になる、という機構の性質
  (https://en.wikipedia.org/wiki/Pantograph)。
* 肘 A の位置は、2つの円(O を中心に半径 a、P を中心に半径 b)の交点として、O→P の線へ下ろした垂線の足
  ``m = d/2 + (a² - b²) / (2d)`` と高さ ``h = √(a² - m²)`` から求めます(2本の骨のIKと同じ式)。

コードは流用していません。

引数
----

* ``tracer``: なぞる点 P のtransform(入力)。ローカルの ``translate`` の ``plane`` の2軸を読みます。
* ``pen``: ペン Q のtransform。ローカルの ``translate`` の ``plane`` の2軸を動かします。生成時の位置を基準に、Q の変化だけ
  動きます。 ``tracer`` と同じ親の下で ``pivot + k (P - pivot)`` に置くと、本物のパンタグラフと同じ位置になります。
  離れた場所に置けば、そこで ``k`` 倍の動きをします。
* ``arm`` ・ ``link``: 固定点 O に置く腕と、肘 A に置く棒のtransform(省略可)。 ``plane`` に垂直な軸の ``rotate`` を回します。
  生成時の向きを :meth:`Pantograph.motion` の ``armAngle`` ・ ``linkAngle`` にしておくと、腕の先が A、棒の先が P に一致します。
* ``armLength`` ・ ``linkLength``: a・b (cm、0より大きい)。生成時に固定します。
* ``ratio``: 倍率 k (0以外)。負なら固定点の反対側へ逆さに写します。生成時に固定します。
* ``plane``: 機構が動く平面 ``xy`` ・ ``yz`` ・ ``zx`` 。1文字目が u、2文字目が v の軸で、残りの軸が回転軸です
  (u から v へ回る向きが正)。
* ``pivot``: ``tracer`` の親の空間での固定点 O の (u, v) の位置 (cm)。生成時に固定します。
* ``elbow``: 肘 A を O→P の線のどちら側へ曲げるか(1.0 は u から v へ回る側、-1.0 は逆)。
* ``minimumDistance``: P を止める近い側の端 (cm)。省略すると ``max(|a - b|, 0.001 (a + b))`` です。腕と棒が重なる手前で
  止めたいときに、既定の値以上で ``a + b`` より小さい値を指定します。
* ``linkRelative``: Trueなら ``link`` を ``arm`` の子として扱い、腕に対する角度( ``linkAngle - armAngle``)で回します。
* ``connect``: Trueなら出力を接続します。既に入力がある場合は ``ValueError`` です。

計算式
------

O を原点とし、 ``plane`` の1文字目の軸を u、2文字目の軸を v とします。

1. ``p = tracer の translate - pivot`` 、 ``d = |p|`` 、 ``ψ = atan2(pV, pU)`` 。
2. 腕が届くのは ``|a - b| ≤ d ≤ a + b`` の間なので、 ``d' = clamp(d, minimumDistance, a + b)`` 、 ``excess = d - d'``
   (遠すぎると正、近すぎると負)。向き ψ は保ち、 ``P = d' (cos ψ, sin ψ)`` 。
3. ``Q = k P`` 。 ``penTranslate = 生成時の translate + (Q - 生成時の Q)`` 。
4. 肘: ``m = d'/2 + (a² - b²) / (2 d')`` 、 ``h = √(a² - m²)`` 、 ``ê = (cos ψ, sin ψ)`` 、 ``ê⊥ = (-sin ψ, cos ψ)`` として
   ``A = m ê + elbow · h ê⊥`` 。
5. ``B = k A`` 、 ``C = P + (k - 1) A`` (A-P-C-B が平行四辺形、C は B-Q の上)。
6. ``armAngle = ψ + elbow · atan2(h, m)`` (腕 O→A と、平行な棒 P→C の角度)、
   ``linkAngle = ψ - elbow · atan2(h, d' - m)`` (棒 A→P と、平行な棒 B→Q の角度)。
7. ``armRotate = 生成時の rotate + (armAngle - 生成時の armAngle)`` 。 ``linkRotate`` も同様で、 ``linkRelative=True`` なら
   ``linkAngle - armAngle`` の変化を使います。

範囲の端では ``a² - m²`` が丸め誤差でわずかに負になるので、0で止めてから平方根を取ります。 ``d'`` は ``minimumDistance``
(0より大きい)以上なので、割り算で0除算は起きません。なぞる点が固定点と重なったとき( ``d = 0``)は ``ψ = 0`` として
近い側の端で止まります。生成時はすべての移動・回転の変化が0なので、接続しても跳ねません。履歴を持たない閉じた式なので、
なぞる点を戻すと同じ姿勢に戻ります。

数値の加算は ``animBlendNodeAdditive`` 、積は ``multDoubleLinear`` で倍精度のまま行います。数学ノードの入出力は版に
より長さ・角度の型なので、係数を明示した ``unitConversion`` を挟み、UI単位(mm・ラジアン等)に関係なく同じ結果にします。

containerのアトリビュート
--------------------------

* ``penTranslateU`` ・ ``penTranslateV`` : ペンの移動。 ``armRotate`` ・ ``linkRotate`` : 腕・棒の回転(渡したときだけ)。
* ``tracerDistance`` ・ ``clampedDistance`` ・ ``excess`` : 固定点からなぞる点までの距離、範囲に止めた距離、止めた量。
* ``tracerAngle`` ・ ``armAngle`` ・ ``linkAngle`` : O→P、腕 O→A、棒 A→P の u からの角度。
* ``pU`` ・ ``pV`` ・ ``qU`` ・ ``qV`` ・ ``aU`` ・ ``aV`` ・ ``bU`` ・ ``bV`` ・ ``cU`` ・ ``cV`` : O から見た位置。
* ``armLength`` ・ ``linkLength`` ・ ``ratio`` ・ ``minimumDistance`` ・ ``maximumDistance`` ・ ``pivotU`` ・ ``pivotV`` :
  固定の値。

制限
----

* なぞる点はローカルの ``translate`` の2軸を読みます。平面の外への移動、親の違うノードどうしのワールドでの位置は
  扱いません。
* 範囲の端は硬く止めます(柔らかい止まりは無い)。超えた量は ``excess`` で見られます。
* ``tracerAngle`` は ``atan2`` の値(-180〜180度)なので、なぞる点が固定点の -u 側を横切ると ``armRotate`` ・
  ``linkRotate`` の値が360度とびます(姿勢は同じ)。キーを焼く・モーションブラーをかけるときは注意してください。
* 棒 B-Q・P-C のtransformは作らず、位置( ``bU`` 〜 ``cV``)と角度だけを出力します。
* 倍率・棒の長さ・固定点は生成時に固定で、アニメーションできません。
* Maya 2026以降の数学ノードを使うため、Maya 2025以前では作れません。

テスト
------

``mlrig/__tests__/inMaya/unit/setups/test_pantograph.py`` (``setups`` スイート)で、作成直後に跳ねないことと固定の値、
範囲の中の位置で ``Q = k P`` ・腕と棒の長さ( ``|OA| = a`` ・ ``|AP| = b`` ・ ``|OB| = k a`` ・ ``|BQ| = k b`` ・
``|PC| = (k - 1) a``)・平行四辺形・肘の側、シーンのペンが ``pivot + k p`` 、腕の子の棒の先がなぞる点、腕の先が A に
一致すること、範囲の外で向きを保って端で止まること・ ``excess`` ・NaNを出さないこと・戻したときの復帰、Python版
( :meth:`Pantograph.motion` )との一致、 ``plane = zx`` ・肘の向き -1 ・負の倍率・ ``minimumDistance`` ・UI単位mm/ラジアン、
containerの所有とUndo/Redo、引数の検査を確認します。棒の長さは試験側でDGの出力の位置から独立に測ります。
Maya 2027で確認しています。

検証動画
--------

``tools/demo_pantograph.py`` は、新規シーンになぞる点(赤)・腕と棒(青)・平行四辺形の残りの棒(水色)・ペン(緑)と、
届く範囲の円(灰色)を正面から見る構図で作り、なぞる点で四角を描く→遠い端を超える→固定点へ近づけて近い端を超える
→元へ戻す動きで、式と毎フレームの入力・ ``excess`` ・ P と Q の位置をHUDに表示して録画します。各フレームで棒の長さが
一定、 ``Q = k P`` 、DGの出力がPython版と一致することを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを
``latest-pantograph.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_pantograph.py --launch
