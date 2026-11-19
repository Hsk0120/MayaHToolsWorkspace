差動歯車(DifferentialGear)
==========================

``mlrig.setups.DifferentialGear`` は、車のデフのようなかさ歯車の差動歯車を連動させます。デフケース(リングギヤと
一緒に回り、十字軸を持つ箱)・左右のサイドギヤ(左右の車輪の車軸)・十字軸に乗ったピニオン(スパイダー)ギヤで、
左・右・ケースのうち1つを ``driven`` (求める側)にし、残りの2つの回転から求めます(入力に ``None`` を渡すと、その部材は
固定)。スパイダーはケースに対する十字軸のまわりの自転を求めます。Maya標準ノード(``animBlendNodeAdditiveDA``)だけで
組み、独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import DifferentialGear

   # 左右の車輪の回転からケース(とドライブシャフトの側)を求める。スパイダー2つはケースの子で、十字軸はローカルの Y
   graph = DifferentialGear.create("wheel_L", "wheel_R", "diffCase", ["spider0", "spider1"],
                                   sideTeeth=16, spiderTeeth=10, driven="case", name="rearDiff",
                                   axis="x", spiderAxis="y")
   owner = graph.container
   # ケースとスパイダーの回転へ出力を接続済み。左右の車輪の rotateX を回すだけで動く

``connect=True`` (既定)なら ``driven`` の部材と各スパイダーの回転へ出力を接続します。 ``False`` なら接続せず、
containerの ``drivenRotate`` ・ ``spiderRotate<i>`` を自分で使います。曲がる車の左右の車輪の回転の差、
ケースを回して片側の車輪を押さえたときにもう片側が2倍で回る動き、機械の展示・分解アニメーションなどに使えます。

参考にした考え方
----------------

* ケースの回転は左右のサイドギヤの平均 ``ωL + ωR = 2 ωC`` 、片側を止めるともう片側は2倍
  (https://www.firgelliauto.com/blogs/mechanisms/differential-motions)。
* 左右の車輪の回転の平均がドライブシャフトの回転になること
  (https://doc.comsol.com/6.1/doc/com.comsol.help.models.mbd.differential_gear/models.mbd.differential_gear.pdf)。
* リングギヤの角速度はサイドギヤの平均(https://arxiv.org/pdf/2112.11254)。

スパイダーの自転と符号は、ケースから見たときにサイドギヤとスパイダーの接点で両方の速度が一致する(滑らずにかみ合う)
ことから下の計算式で導いています。コードは流用していません。

引数
----

* ``left`` ・ ``right`` ・ ``case``: 左右のサイドギヤとケースのtransform。ローカルの ``rotate<axis>`` を読みます
  (``driven`` の部材は書きます)。入力の部材に ``None`` を渡すと固定(回らない)とします。 ``driven`` の部材に ``None`` を
  渡すと、containerの出力だけを作ります。入力が両方 ``None`` なら ``ValueError`` です。
* ``spiders``: スパイダーのtransform(0個以上)。ケースの子に置き、ローカルの ``rotate<spiderAxis>`` を動かします。
  ``spiderAxis`` は十字軸(車軸からスパイダーへ向かう向き、外向きでも内向きでもよい)に沿わせます。jointなら
  ``jointOrient`` で向けると、 ``rotate`` はその軸のまわりの回転になります。
* ``sideTeeth`` ・ ``spiderTeeth``: サイドギヤ(左右同じ)・スパイダーの歯数(0より大きい)。生成時に固定します。
  ピッチ円の半径(サイドギヤは車軸からスパイダーの中心まで、スパイダーはスパイダーの中心からサイドギヤの中心の
  車軸方向の位置まで)を入れても比は同じです。
* ``driven``: 求める部材 ``"left"`` ・ ``"right"`` ・ ``"case"`` 。
* ``axis``: 左右のサイドギヤとケースのローカルの回転軸(車軸、x/y/z)。
* ``spiderAxis``: スパイダーのローカルの回転軸(十字軸、x/y/z)。
* ``connect``: Trueなら出力を接続します。既に入力がある場合は ``ValueError`` です。

スパイダーの向き(自転の符号)は、生成時のワールドの位置と軸から :meth:`DifferentialGear.spiderSign` で決め、
containerの ``spiderSign<i>`` に固定します。スパイダーがあるときは、ケースと、左右のどちらかのサイドギヤのノードが
必要です(位置で左の側を決めるため)。

計算式
------

サイドギヤの歯数を ``Zs`` 、スパイダーを ``Zp`` 、各部材の生成時からの回転の変化を ``ΔL`` ・ ``ΔR`` ・ ``ΔC`` とします
(入力の ``Δ = rotate<axis> - 生成時の値`` 、 ``None`` の入力は 0)。

1. ケースから見るとスパイダーの軸は止まっていて、左右のサイドギヤは同じスパイダーにかみ合うので、逆向きに同じ量だけ回る:
   ``ΔL - ΔC = -(ΔR - ΔC)`` 。つまり ``ΔL + ΔR = 2 ΔC`` (ケースは左右の平均)。
2. ``driven = "case"``: ``ΔC = (ΔL + ΔR) / 2`` 。
3. ``driven = "left"``: ``ΔL = 2 ΔC - ΔR`` 。右を止めると左はケースの2倍。 ``driven = "right"``: ``ΔR = 2 ΔC - ΔL`` 。
4. ``sideSpin = ΔL - ΔC`` (左のケースに対する回転。右は ``-sideSpin``)、 ``spiderSpin = (Zs / Zp) sideSpin`` 。
5. スパイダーの符号: ケースの座標で車軸を X、左のサイドギヤの中心を ``(-a, 0, 0)`` 、スパイダーの中心を ``(0, b, 0)`` 、
   軸を +Y とすると、接点 ``(-a, b, 0)`` の速度は左のサイドギヤで ``(0, 0, α b)`` 、スパイダーで ``φ (0, 1, 0) × (-a, 0, 0)
   = (0, 0, φ a)`` 。一致させると ``φ = (b / a) α = (Zs / Zp) α`` 。左が反対の側にあるか、軸が内向きなら符号が逆になる:
   ``spiderSign = -sign(車軸 · (左の中心 - スパイダーの中心)) × sign(スパイダーの軸 · 車軸からスパイダーへの向き)`` 。
6. ``drivenRotate = 生成時の driven の rotate<axis> + Δ(driven)`` 、
   ``spiderRotate<i> = 生成時のスパイダーの rotate<spiderAxis> + spiderSign<i> × spiderSpin`` 。

生成時は変化が0なので、接続しても跳ねません。どれも角度の1次式なので、角度のまま ``A * weightA + B * weightB`` を求める
``animBlendNodeAdditiveDA`` を連ねて倍精度で足し、角度の単位変換ノードを挟みません。UI単位が度でもラジアンでも同じ結果です。
履歴を持たない閉じた式なので、入力を戻すと同じ角度へ戻ります。

containerのアトリビュート
--------------------------

* ``drivenRotate`` : ``driven`` の部材の回転。
* ``leftAngle`` ・ ``rightAngle`` ・ ``caseAngle`` : 各部材の生成時からの回転の変化(入力の部材は入力の変化そのもの)。
* ``sideSpin`` : 左のサイドギヤのケースに対する回転 ``ΔL - ΔC`` (直進なら0、曲がると左右の差の半分)。
* ``spiderSpin`` : スパイダーのケースに対する自転の大きさ ``(Zs / Zp) sideSpin`` 。
* ``spiderRotate<i>`` : 各スパイダーの回転(接続先の値)。
* ``sideTeeth`` ・ ``spiderTeeth`` ・ ``spiderSign<i>`` : 固定の歯数と、各スパイダーの自転の符号。

制限
----

* 左右のサイドギヤとケースはローカルの1軸の回転チャンネル(``rotate<axis>``)を読み書きします。回転軸は平行で同じ向きの前提です。
* スパイダーはケースの子(ケースと一緒に回る空間)に置きます。符号は生成時の配置で決めるので、生成後にスパイダーの位置・
  向きを変えたときは作り直します。
* 左右のサイドギヤは同じ歯数です(左右で歯数が違う差動歯車・遊星歯車式の差動は扱いません)。
* ドライブピニオンとリングギヤの減速比、リミテッドスリップ(摩擦・トルクの配分)、歯の形状は扱いません。

テスト
------

``mlrig/__tests__/inMaya/unit/setups/test_differentialGear.py`` (``setups`` スイート)で、作成直後に跳ねないことと固定の
符号、乱数の入力でケースが左右の平均になること、各スパイダーと左右のサイドギヤの接点で両方の物質点のワールドの変位が一致する
こと(式を使わずにシーンのワールド位置の有限差分で。外向き・下向き・内向きのスパイダー)、 ``driven = "left"`` ・ ``"right"``
と片側固定での2倍、Python版( :meth:`DifferentialGear.motion` )との一致、 :meth:`DifferentialGear.spiderSign` 、
``axis = z`` ・ ``spiderAxis = x`` ・UI単位mm/ラジアン、containerの所有とUndo/Redo、引数の検査を確認します。Maya 2027で
確認しています。

検証動画
--------

``tools/demo_differential_gear.py`` は、新規シーンにデフケース(緑)、左のサイドギヤ(赤)、右のサイドギヤ(灰色)、
スパイダー2つ(青)と各歯車の向きの目印を斜めから見る構図で作り、右を止めたままケースを回す→右も一緒に回す(直進)→
右を逆へ回す→元へ戻す動きで、式と毎フレームの入力・DGの出力をHUDに表示して録画します。各フレームでDGの出力が試験側の式と
一致し、接点の弧長が一致することを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを
``latest-differential-gear.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_differential_gear.py --launch
