遊星歯車機構(PlanetaryGear)
============================

``mlrig.setups.PlanetaryGear`` は、太陽歯車・内歯車(リング)・キャリア(遊星歯車の軸を持つ腕)と、キャリアに乗って
太陽歯車と内歯車の両方にかみ合う遊星歯車の回転を連動させます。3つの部材のうち1つを ``driven`` (求める側)にし、
残りの2つの回転から求めます(入力に ``None`` を渡すと、その部材は固定)。遊星歯車はキャリアに対する自転を求めます。
Maya標準ノード(``animBlendNodeAdditiveDA``)だけで組み、独自プラグイン、エクスプレッション、フレームごとのPythonは
使いません。

.. code-block:: python

   from mlrig.setups import PlanetaryGear

   # 内歯車を固定し、太陽歯車(24歯)を回してキャリアを求める。遊星歯車(12歯)はキャリアの子
   graph = PlanetaryGear.create("sun", None, "carrier", ["planet0", "planet1", "planet2"],
                                sunTeeth=24, planetTeeth=12, driven="carrier", name="hubGear", axis="z")
   owner = graph.container
   # キャリアと遊星歯車の rotateZ へ出力を接続済み。太陽歯車の rotateZ を回すだけで動く

``connect=True`` (既定)なら ``driven`` の部材と各遊星歯車の ``rotate<axis>`` へ出力を接続します。 ``False`` なら
接続せず、containerの ``drivenRotate`` ・ ``planetRotate<i>`` を自分で使います。時計・電動ドリル・車輪のハブ・
自動変速機・ロボットの関節の減速機など、同じ軸の上で回転の速さと向きを変える機構のアニメーションに使えます。

参考にした考え方
----------------

* 3つの部材の回転を歯数で結ぶWillisの式 ``(θs - θc) / (θr - θc) = -Zr / Zs``
  (https://www.tec-science.com/?p=28857)。
* 内歯車を固定したときの太陽歯車とキャリアの比 ``1 + Zr / Zs``
  (https://www.firgelliauto.com/es/blogs/mechanisms/epicyclic-planetary-gear-train)。
* 同心にかみ合う歯数の条件 ``Zr = Zs + 2 Zp`` (https://www.tspi.at/diy/planetarycalc.html)。
* どの部材を固定・入力・出力にするかで6通りの使い方があること
  (https://www.alibre.com/blog/the-inputs-and-outputs-of-planetary-gears/)。

遊星歯車の自転は、キャリアから見たときに太陽歯車・内歯車とのピッチ円の接点で弧長が一致する(滑らずに転がる)ことから
下の計算式で導いています。コードは流用していません。

引数
----

* ``sun`` ・ ``ring`` ・ ``carrier``: 太陽歯車・内歯車・キャリアのtransform。ローカルの ``rotate<axis>`` を読みます
  (``driven`` の部材は書きます)。入力の部材に ``None`` を渡すと固定(回らない)とします。 ``driven`` の部材に ``None`` を
  渡すと、containerの出力だけを作ります。入力が両方 ``None`` なら ``ValueError`` です。
* ``planets``: 遊星歯車のtransform(0個以上)。ローカルの ``rotate<axis>`` を動かします。位置は動かしません
  (キャリアの子にして、キャリアと一緒に公転させます)。
* ``sunTeeth`` ・ ``planetTeeth``: 太陽歯車・遊星歯車の歯数(0より大きい)。内歯車は ``Zs + 2 Zp`` です。生成時に固定します。
  半径(ピッチ円の半径)を入れても比は同じです。
* ``driven``: 求める部材 ``"sun"`` ・ ``"ring"`` ・ ``"carrier"`` 。
* ``axis``: 全ての歯車とキャリアのローカルの回転軸(x/y/z)。
* ``followCarrier``: Trueなら遊星歯車はキャリアの子(キャリアと一緒に回る空間)とし、キャリアに対する自転を書きます。
  Falseならキャリアと一緒に回らない空間とし、キャリアの回転を足した固定した空間での自転を書きます。
* ``connect``: Trueなら出力を接続します。既に入力がある場合は ``ValueError`` です。

遊星歯車を等間隔に n 個置いて両方へかみ合わせられるかは、 :meth:`PlanetaryGear.canSpaceEvenly` (``Zs + Zr`` が n で
割り切れるか)で確かめます。例えば ``Zs = 24`` ・ ``Zp = 12`` (``Zr = 48``)は3個・4個とも置けます。

計算式
------

歯数を ``Zs`` ・ ``Zp`` ・ ``Zr = Zs + 2 Zp`` 、各部材の生成時からの回転の変化を ``Δs`` ・ ``Δr`` ・ ``Δc`` とします
(入力の ``Δ = rotate<axis> - 生成時の値`` 、 ``None`` の入力は 0)。

1. キャリアから見ると3つの歯車は固定軸の歯車列で、太陽歯車と遊星歯車は外接(逆向き)、遊星歯車と内歯車は内接(同じ向き)。
   ピッチ円の接点で弧長が一致するので ``Zs (Δs - Δc) = -Zp (Δp - Δc)`` 、 ``Zr (Δr - Δc) = Zp (Δp - Δc)`` 。
2. 2つを合わせるとWillisの式 ``Zs Δs + Zr Δr = (Zs + Zr) Δc`` 。
3. ``driven = "carrier"``: ``Δc = (Zs Δs + Zr Δr) / (Zs + Zr)`` 。内歯車を固定すると ``Δc = Δs / (1 + Zr / Zs)`` (減速)。
4. ``driven = "ring"``: ``Δr = ((Zs + Zr) Δc - Zs Δs) / Zr`` 。キャリアを固定すると ``Δr = -(Zs / Zr) Δs`` (逆転)。
5. ``driven = "sun"``: ``Δs = ((Zs + Zr) Δc - Zr Δr) / Zs`` 。内歯車を固定すると ``Δs = (1 + Zr / Zs) Δc`` (増速)。
6. 遊星歯車: ``planetSpin = Δp - Δc = -(Zs / Zp)(Δs - Δc) = (Zr / Zp)(Δr - Δc)`` (キャリアに対する自転)、
   ``planetAngle = Δc + planetSpin`` (固定した空間での自転)。
7. ``drivenRotate = 生成時の driven の rotate<axis> + Δ(driven)`` 、
   ``planetRotate<i> = 生成時の遊星歯車の rotate<axis> + (followCarrier なら planetSpin 、違えば planetAngle)`` 。

生成時は変化が0なので、接続しても跳ねません。歯のかみ合わせの見た目は、生成時の遊星歯車の角度で合わせます。
どれも角度の1次式なので、角度のまま ``A * weightA + B * weightB`` を求める ``animBlendNodeAdditiveDA`` を連ねて倍精度で
足し、角度の単位変換ノードを挟みません。UI単位が度でもラジアンでも同じ結果です。履歴を持たない閉じた式なので、
入力を戻すと同じ角度へ戻ります。

containerのアトリビュート
--------------------------

* ``drivenRotate`` : ``driven`` の部材の回転。
* ``sunAngle`` ・ ``ringAngle`` ・ ``carrierAngle`` : 各部材の生成時からの回転の変化(入力の部材は入力の変化そのもの)。
* ``planetSpin`` ・ ``planetAngle`` : 遊星歯車のキャリアに対する自転と、固定した空間での自転(生成時からの変化)。
* ``planetRotate<i>`` : 各遊星歯車の回転(接続先の値)。
* ``sunTeeth`` ・ ``planetTeeth`` ・ ``ringTeeth`` : 固定の歯数。

制限
----

* 各部材はローカルの1軸の回転チャンネル( ``rotate<axis>`` )を読み書きします。全ての部材の回転軸は平行で、同じ向きの前提です。
* 遊星歯車の位置(公転)は動かしません。キャリアの子にするか、キャリアと同じ回転をする空間に置きます。
* 段付きの遊星歯車(2つの歯数を持つ遊星)・2段の遊星歯車列・遊星歯車の数による配置は扱いません。
* 歯数は生成時に固定します。歯の形・バックラッシ・摩擦は扱いません。歯車の形状は作りません。

テスト
------

``mlrig/__tests__/inMaya/unit/setups/test_planetaryGear.py`` (``setups`` スイート)で、作成直後に跳ねないこと、
乱数の入力で太陽歯車-遊星歯車・内歯車-遊星歯車のピッチ円の接点の弧長が一致すること、内歯車を固定したときに遊星歯車の
内歯車との接点の物質点が止まり、太陽歯車との接点が太陽歯車の物質点と同じ速さで動くこと(シーンのワールド位置の有限差分)、
``driven = "ring"`` ・ ``"sun"`` でもWillisの式を満たすこととキャリア固定の逆転、Python版( :meth:`PlanetaryGear.motion` )
との一致、 ``followCarrier = False`` のワールドの向き、 ``axis = x`` ・UI単位mm/ラジアン、 :meth:`PlanetaryGear.ringTeeth` ・
:meth:`PlanetaryGear.canSpaceEvenly` 、containerの所有とUndo/Redo、引数の検査を確認します。Maya 2027で確認しています。

検証動画
--------

``tools/demo_planetary_gear.py`` は、新規シーンに太陽歯車(赤)、内歯車(灰色)、キャリアの腕(緑)、遊星歯車3つ(青)と
各歯車の向きの目印を正面から見る構図で作り、内歯車を固定したまま太陽歯車を回す→内歯車も回す→元へ戻す動きで、式と
毎フレームの入力・DGの出力をHUDに表示して録画します。各フレームでDGの出力が試験側の式と一致し、ピッチ円の接点の弧長が
一致することを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを
``latest-planetary-gear.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_planetary_gear.py --launch
