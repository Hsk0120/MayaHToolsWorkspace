オルダム継手(OldhamCoupling)
============================

``mlrig.setups.OldhamCoupling`` は、平行にずれた2本の軸を、直交する2つの突起を持つ中間の円板でつなぐオルダム継手の
動きを求めます。入力軸の溝と出力軸の溝は互いに直交し、円板の突起がそれぞれにはまって滑ります。入力軸を θ 回すと、
出力軸と円板は同じ θ だけ回り(等速)、円板の中心は2本の軸の中心を結ぶ線を直径とする円(半径 ``e/2``)を、軸の
2倍の速さ ``2θ`` で回ります。Maya標準ノード(``sin`` ・ ``cos`` ・ ``animBlendNodeAdditive`` ・ ``unitConversion``)
だけで組み、独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import OldhamCoupling

   # 2本の軸のずれ2cm。出力軸は入力軸から +X に置き、円板は生成時に入力軸の中心に置く
   graph = OldhamCoupling.create("inputShaft", "outputShaft", "disc", offset=2.0, name="oldham",
                                 axis="z", offsetAxis="x")
   owner = graph.container
   # 出力軸の rotateZ と円板の translateX・translateY・rotateZ へ出力を接続済み。入力軸の rotateZ を回すだけで動く

``connect=True`` (既定)なら出力軸の ``rotate<axis>`` と、円板の ``translate<offsetAxis>`` ・
``translate<面内のもう1つの軸>`` ・ ``rotate<axis>`` へ出力を接続します。 ``False`` なら接続せず、containerの
``outputRotate`` ・ ``discU`` ・ ``discV`` ・ ``discRotate`` を自分で使います。ずれた軸の間で回転を伝える機械部品、
偏心して回る円板の揺れ、溝の中で滑る部品の位置( ``inputSlide`` ・ ``outputSlide``)を使う表現などに使えます。

参考にした考え方
----------------

* 入力軸・中間の円板・出力軸の3つが同じ角速度で回り、円板が2つの溝の中で滑ることでずれを吸収するという
  オルダム継手の一般的な説明(https://en.wikipedia.org/wiki/Oldham_coupling、
  https://mr-iitkgp.vlabs.ac.in/exp/oldham-coupling-mechanism/theory.html)。
* 溝の滑りの最大の速さが ``e ω`` になるという関係
  (https://www.firgelliauto.com/blogs/mechanisms/oldham-coupling)。

円板の中心の軌道(半径 ``e/2`` 、2倍の速さ)は、2本の溝の線の交点として下の計算式で導いています。
資料によっては軌道の半径を e とするものがありますが、試験では2本の溝の線の交点を独立に解いて ``e/2`` を確かめています。
コードは流用していません。

引数
----

* ``inputShaft``: 入力軸のtransform。ローカルの ``rotate<axis>`` を回します。生成時の姿勢を ``θ = 0`` (入力軸の溝が
  偏心の向きに直交し、円板の中心が入力軸の中心にある)とします。
* ``outputShaft``: 出力軸のtransform。ローカルの ``rotate<axis>`` を動かします。
* ``disc``: 中間の円板のtransform。生成時に入力軸の中心に置きます。親の空間の ``axis`` が軸の向き、 ``offsetAxis`` が
  入力軸から出力軸への向きである前提です。
* ``offset``: 2本の軸の間の距離 e (cm、0より大きい)。生成時に固定します。
* ``axis``: 軸の回転軸(x/y/z)。
* ``offsetAxis``: 円板の親の空間で、入力軸から出力軸へ向かう軸(x/y/z、 ``axis`` と別の軸)。面内のもう1つの軸は外積
  ``axis × offsetAxis`` で決まり、向きが負の軸(例: ``axis = z`` ・ ``offsetAxis = y`` なら -X)には符号を反転して書きます。
* ``outputDirection``: 出力軸の回転の向き(1.0 か -1.0)。出力軸の回転軸の正の向きが入力軸と逆なら -1.0 にします。
* ``connect``: Trueなら出力を接続します。既に入力がある場合は ``ValueError`` です。

計算式
------

入力軸の中心を原点 O1、偏心の軸を u、面内のもう1つの軸 ``axis × offsetAxis`` を v とし、出力軸の中心を ``O2 = (e, 0)``
とします。

1. ``θ = 入力軸の rotate<axis> - 生成時の値 + phase`` 。
2. 入力軸の溝の向きは ``s = (-sin θ, cos θ)`` (生成時は v)、出力軸の溝は入力軸の溝に直交する ``t = (cos θ, sin θ)`` 。
3. 円板の中心 C は O1 を通る s の線と、O2 を通る t の線の交点です。C を s の線へ置くと ``C = k s`` で、 ``(C - O2)·s = 0``
   から ``k = O2·s = -e sin θ`` 。よって ``C = (e sin² θ, -e sin θ cos θ) = (e/2)(1 - cos 2θ, -sin 2θ)`` 。
4. ``∠O1 C O2`` が直角なので、C は O1O2 を直径とする円(中心 ``M = (e/2, 0)`` 、半径 ``e/2``)の上にあり、
   ``C - M = (e/2)(cos(2θ + 180°), sin(2θ + 180°))`` 。軸が半回転すると円板の中心は1周します。
5. ``discOffsetU = e sin² θ`` 、 ``discOffsetV = -e sin θ cos θ`` 、
   ``discU = 生成時の円板の translate<offsetAxis> + discOffsetU`` 、 ``discV = 生成時の円板の translate<v の軸> ± discOffsetV``
   (v の軸の向きが負なら -)。
6. 溝の中の位置: ``inputSlide = C·s = -e sin θ`` (入力軸の中心から入力の溝に沿って)、
   ``outputSlide = (C - O2)·t = -e cos θ`` (出力軸の中心から出力の溝に沿って)。それぞれ ``±e`` の間を1回転に1往復し、
   向きの切り替わり(端)は1回転に2回です。
7. ``orbitAngle = 2θ`` 、 ``discRotate = 生成時の円板の rotate<axis> + θ`` 、
   ``outputRotate = 生成時の出力軸の rotate<axis> + outputDirection × θ`` (等速)。

θ = 0 では移動・回転が0なので、接続しても跳ねません。履歴を持たない閉じた式なので、入力軸を逆に回すと同じ経路を
戻ります。 ``sin² θ`` ・ ``sin θ cos θ`` は ``2θ`` の ``cos`` ・ ``sin`` から1次式で作り、掛け算のノードを使いません。

数値の加算は ``animBlendNodeAdditive`` を連ねて倍精度で行います(``plusMinusAverage`` ・ ``multiplyDivide`` は単精度のため)。
``sin`` ・ ``cos`` の入出力は版により長さの型なので、係数を明示した ``unitConversion`` を挟み、UI単位(mm・ラジアン等)に
関係なく同じ結果にします。

containerのアトリビュート
--------------------------

* ``phase`` : 入力軸の角度に足す値(keyable)。
* ``outputRotate`` : 出力軸の回転。
* ``discU`` ・ ``discV`` ・ ``discRotate`` : 円板の移動と回転。 ``discOffsetU`` ・ ``discOffsetV`` は生成時からの移動量
  (v の符号を掛ける前)。
* ``inputSlide`` ・ ``outputSlide`` : 2つの溝の中の円板の中心の位置。
* ``orbitAngle`` : 円板の中心の公転の、生成時からの角度 ``2θ`` 。
* ``offset`` ・ ``orbitRadius`` : 固定の値( ``e`` ・ ``e/2`` )。

制限
----

* 入力軸はローカルの1軸の回転チャンネル( ``rotate<axis>`` )を読みます。複数軸の回転やワールドでの回転は扱いません。
* 2本の軸は平行で、ずれは生成時に固定します。軸の傾き(角度のずれ)は扱いません(:doc:`universal_joint` を使います)。
* 円板の親の空間は、入力軸の回転軸と偏心の向きに軸をそろえる前提です。
* 溝の摩擦・遊び・円板の厚みは扱いません。軸・溝・円板の形状は作りません。

テスト
------

``mlrig/__tests__/inMaya/unit/setups/test_oldhamCoupling.py`` (``setups`` スイート)で、作成直後に跳ねないこと、
正負・複数回転の角度で円板の中心が2本の溝の線の交点(試験側で連立方程式を解いた値)にあり、 ``∠O1 C O2`` が直角で
半径 ``e/2`` の円の上にあること、 ``inputSlide`` ・ ``outputSlide`` が溝に沿った距離であること、出力軸と円板が等速で
回り中心の公転が ``2θ`` であること、Python版( :meth:`OldhamCoupling.motion` )との一致、 ``phase`` 、
``axis = x`` ・ ``offsetAxis = z`` ・向き -1 ・UI単位mm/ラジアン、ほかの (axis, offsetAxis) の組でも円板の中心が溝の上に
あること、containerの所有とUndo/Redo、引数の検査を確認します。Maya 2027で確認しています。

検証動画
--------

``tools/demo_oldham_coupling.py`` は、新規シーンに入力軸(赤)と入力の溝、出力軸(緑)と出力の溝、中間の円板(青)と
直交する2本の突起、円板の中心(黄)と、中心が描くはずの円(灰色のカーブ)を正面から見る構図で作り、入力軸を等速で
2回転→逆へ半回転→元へ戻す動きで、式と毎フレームの θ ・円板の中心・2つの溝の中の位置・出力軸の角度をHUDに表示して
録画します。各フレームでDGの出力が試験側の式と一致し、円板の中心が2本の溝の線の上と半径 ``e/2`` の円の上にあることを
判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを
``latest-oldham-coupling.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_oldham_coupling.py --launch
