楕円トランメル(EllipticTrammel)
================================

``mlrig.setups.EllipticTrammel`` は、直交する2本の溝を滑る2つのスライダーを長さ一定の棒でつなぎ、棒の上の点に楕円を
描かせる楕円トランメル(アルキメデスのトランメル、楕円コンパス)の動きを求めます。クランクで棒の中点を溝の交点のまわりに
回すと、スライダーAはAの溝に沿って ``L cos θ`` 、スライダーBはBの溝に沿って ``L sin θ`` の位置を往復し、棒はクランクと
逆向きに同じ速さで回ります。棒の上でAから距離 d の点は、半軸 ``|L - d|`` と ``|d|`` の楕円を描きます。
Maya標準ノード(``sin`` ・ ``cos`` ・ ``animBlendNodeAdditive`` ・ ``unitConversion``)だけで組み、独自プラグイン、
エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import EllipticTrammel

   # 棒の長さ4cm。Aは X、Bは Y の溝を滑る。棒はAの子に置き、Aから6cmの点が楕円(半軸2cm・6cm)を描く
   graph = EllipticTrammel.create("crank", "sliderA", "sliderB", "rod", rodLength=4.0, penDistance=6.0,
                                  name="trammel", axis="z", aAxis="x", bAxis="y")
   owner = graph.container
   # 2つのスライダーの translate と棒の rotateZ へ出力を接続済み。クランクの rotateZ を回すだけで動く

``connect=True`` (既定)ならスライダーAの ``translate<aAxis>`` 、スライダーBの ``translate<bAxis>`` (と棒の
``rotate<axis>``)へ出力を接続します。 ``False`` なら接続せず、containerの ``aTranslate`` ・ ``bTranslate`` ・
``rodRotate`` を自分で使います。腕の先を楕円軌道で動かす機械部品、2本のレールで支えて滑る板・はしご、
楕円の軌道を持つワイパーなどに使えます。

参考にした考え方
----------------

* 2つのピボットは直線を、棒の上の点は楕円を描き、その半軸は点から2つのピボットまでの距離、棒の中点は円を描くという
  トランメルの一般的な性質(https://en.wikipedia.org/wiki/Ellipsograph)。
* 楕円の媒介変数表示 ``x = a cos θ`` 、 ``y = b sin θ``
  (https://www.firgelliauto.com/blogs/mechanisms/trammel-for-drawing-ellipses)。

コードは流用していません。

引数
----

* ``crank``: クランクのtransform。溝の交点に置き、ローカルの ``rotate<axis>`` を回します。生成時の姿勢を ``θ = 0``
  (棒がAの溝の上に寝て、スライダーAが交点から L、スライダーBが交点)とします。
* ``sliderA`` ・ ``sliderB``: スライダーのtransform。ローカルの ``translate<aAxis>`` ・ ``translate<bAxis>`` を動かします。
* ``rod``: 棒のtransform(省略可)。スライダーAの位置に置き(子にする)、ローカルの ``rotate<axis>`` を回します。
* ``rodLength``: 2つのスライダーの間の棒の長さ L (cm、0より大きい)。生成時に固定します。
* ``penDistance``: 楕円を描く点のスライダーAからの距離 d (cm)。Bを越えた先や負(Aの手前)でもよく、省略すると ``1.5 L`` 。
* ``axis`` ・ ``aAxis`` ・ ``bAxis``: クランクと棒の回転軸、スライダーAとBの移動軸(x/y/z)。
* ``aDirection`` ・ ``bDirection`` ・ ``rodDirection``: 向き(1.0 か -1.0)。交点からAへの向きとAの移動軸、クランクが +θ 回った
  とき棒の中点が向かうBの溝の向きとBの移動軸、棒とクランクの回転軸の正の向きがそれぞれ逆なら -1.0 にします。
* ``connect``: Trueなら出力を接続します。既に入力がある場合は ``ValueError`` です。

計算式
------

1. ``θ = クランクの rotate<axis> - 生成時の値 + phase`` 。
2. 溝の交点を原点、Aの溝を x、Bの溝を y とすると、棒の中点は ``(L/2 cos θ, L/2 sin θ)`` 。 ``|AB| = L`` で A・B がそれぞれの
   溝の上にあるので ``A = (L cos θ, 0)`` 、 ``B = (0, L sin θ)`` (中点がABの中点になる)。
3. ``aOffset = aDirection × L (cos θ - 1)`` 、 ``aTranslate = 生成時のAの translate<aAxis> + aOffset`` 。
4. ``bOffset = bDirection × L sin θ`` 、 ``bTranslate = 生成時のBの translate<bAxis> + bOffset`` 。
5. 棒の向き A→B は ``(-cos θ, sin θ)`` で、生成時の向き ``(-1, 0)`` から ``-θ`` 回っています。
   ``rodAngle = -θ`` 、 ``rodRotate = 生成時の棒の rotate<axis> + rodDirection × rodAngle`` 。
6. 棒の上でAから d の点は ``P = A + d (B - A) / L = ((L - d) cos θ, d sin θ)`` 。生成時からの移動を
   ``penX = aDirection × (L - d)(cos θ - 1)`` 、 ``penY = bDirection × d sin θ`` として出力します。
   半軸は ``semiAxisA = |L - d|`` (Aの溝の向き)、 ``semiAxisB = |d|`` (Bの溝の向き)の固定の値です。
   ``d = L/2`` (棒の中点)は円、 ``d = 0`` ・ ``d = L`` (スライダー)は直線になります。

θ = 0 ではすべての移動・回転が0なので、接続しても跳ねません。履歴を持たない閉じた式なので、クランクを逆に回すと
同じ経路を戻ります。

数値の加算は ``animBlendNodeAdditive`` を連ねて倍精度で行います(``plusMinusAverage`` ・ ``multiplyDivide`` は単精度のため)。
``sin`` ・ ``cos`` の入出力は版により長さの型なので、係数を明示した ``unitConversion`` を挟み、UI単位(mm・ラジアン等)に
関係なく同じ結果にします。

containerのアトリビュート
--------------------------

* ``phase`` : クランクの角度に足す値(keyable)。
* ``aTranslate`` ・ ``aOffset`` 、 ``bTranslate`` ・ ``bOffset`` : スライダーの移動と、生成時からの移動量。
* ``rodRotate`` ・ ``rodAngle`` : 棒の回転(``rod`` を渡したときだけ)と、生成時からの回転量 ``-θ`` 。
* ``penX`` ・ ``penY`` : 棒の上の点の、生成時からのAの溝・Bの溝に沿った移動。棒の外の物をこの楕円で動かすのに使えます。
* ``rodLength`` ・ ``penDistance`` ・ ``semiAxisA`` ・ ``semiAxisB`` : 固定の値。

制限
----

* クランクはローカルの1軸の回転チャンネル( ``rotate<axis>`` )を読みます。複数軸の回転やワールドでの回転は扱いません。
* 2本の溝は直交する直線だけです。直交しない溝(傾いた楕円)は扱いません。
* 棒はスライダーAの子に置く前提で、回転だけを出力します。棒の上の点の位置は ``penX`` ・ ``penY`` を自分で使います。
* スライダーを入力にして(クランクなしで)棒を動かす向きの計算は扱いません。
* クランク・溝・棒の形状は作りません。

テスト
------

``mlrig/__tests__/inMaya/unit/setups/test_ellipticTrammel.py`` (``setups`` スイート)で、作成直後に跳ねないこと、
正負・複数回転の角度でA・Bが溝の上にあり ``|AB| = L`` 、ABの中点がクランクの先に一致すること、Aの子の棒の上の点の
ワールド位置がBの方向にあり楕円の上にあること、Python版( :meth:`EllipticTrammel.motion` )との一致、棒がクランクと逆向きに
回ること、1回転の点の移動の幅が ``2|L - d|`` ・ ``2|d|`` であること、 ``penDistance`` の既定値と中点の円、 ``phase`` 、
``axis = x`` ・ ``aAxis = y`` ・ ``bAxis = z`` ・向き -1 ・UI単位mm/ラジアン・棒なし、containerの所有とUndo/Redo、
引数の検査を確認します。Maya 2027で確認しています。

検証動画
--------

``tools/demo_elliptic_trammel.py`` は、新規シーンにクランク(赤)・横と縦の溝(灰色の線)・スライダーA/B(緑)・棒(青)・
棒の先の点(黄)と、その点が描くはずの楕円(灰色のカーブ)を正面から見る構図で作り、クランクを等速で2回転→逆へ半回転→
元へ戻す動きで、式と毎フレームの θ ・A/Bの位置・棒の角度・点の位置をHUDに表示して録画します。各フレームでDGの出力が
試験側の式と一致し、棒の長さが L のまま、点のワールド位置が楕円の上にあることを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを
``latest-elliptic-trammel.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_elliptic_trammel.py --launch
