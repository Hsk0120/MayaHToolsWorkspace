箱の縁で転がる(BoxRoll)
========================

``mlrig.setups.BoxRoll`` は、断面が一辺 ``size`` の正方形の物体(箱・サイコロ・角材など)を、角度 ``roll`` だけ床の上で
縁(エッジ)から縁へ転がしたワールド行列を出力します。90度ごとに回転の支点が次の下の縁へ切り替わる「支点の切り替え(pivot switching)」を、
1つの角度だけで扱えます。Maya標準ノード(``unitConversion`` ・ ``multiplyDivide`` ・ ``floor`` ・ ``plusMinusAverage`` ・
``composeMatrix`` ・ ``multMatrix``)だけで組み、独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

:doc:`RockerRoll <rocker_roll>` は丸い底(支点が円弧の上を連続して移る)、:doc:`OutlineBank <outline_bank>` は底の輪郭の縁で傾ける
(元へ戻る傾き)部品で、この部品は平らな面と縁を持つ物体を何回でも続けて転がす(段の番号で支点の縁を進める)向きです。

.. code-block:: python

   from mlrig.setups import BoxRoll

   # 一辺50cmの箱(ローカル原点が底の面の中心、X軸回りに +Z へ転がる)
   graph = BoxRoll.create("crate", 50.0, name="crateRoll", axis="x", upAxis="y")
   owner = graph.container
   # roll をキーで動かし、matrix をワールド直下の表示用transformの offsetParentMatrix へ繋ぐ
   mlib.getPlug("{}.matrix".format(owner)).connectTo("crateGeo.offsetParentMatrix")

参考にした考え方
----------------

* Lester Banks の記事「Rigging a Box With a Dynamic Pivot in Maya」: 箱の回転の支点を中心でなく床に接している縁へ置き、
  転がす向きに合わせて支点を切り替えることで、箱が床に接したまま転がる考え方。
* 同じく Lester Banks で紹介されている、ノードだけで支点を切り替える方法(pivot switching with nodes)と、
  フットロールの支点を縁へ動かす「sliding pivot」の考え方。
* Autodesk Maya ヘルプの ``floor`` ノード(Maya 2024以降の標準の数学ノード): 角度を90度の段の番号と段の中の角度に分けるのに使います。

いずれもコードは流用していません(記事の方法は条件分岐やスクリプトで支点を動かしますが、この部品は段の番号から支点の縁の位置を式で求めます)。

引数
----

* ``target``: 転がす物体のtransform(joint可)。生成時のローカル行列(``matrix * offsetParentMatrix``)と親のワールド行列を基準にします。
* ``size``: 断面の正方形の一辺(0より大きい、cm)。生成時に固定します。
* ``axis``: 転がる回転軸(対象のローカル、x/y/z)。
* ``upAxis``: 対象のローカルの上の軸(x/y/z、axisと別の軸)。
* ``contact``: 生成時の底の面の中心(対象のローカル、cm)。既定はローカル原点。

計算式
------

断面の中心を ``c = contact + size/2 * up`` 、進む向きを ``f = axis × up`` 、生成時の前の下の縁を ``e = contact + size/2 * f`` として、
``n = floor(roll / 90°)`` (段の番号)、 ``φ = roll - n * 90°`` (段の中の角度、0〜90°)と分けます(行ベクトル規約)。

``matrix = T(-c) * R_axis(n * 90°) * T(c - e) * R_axis(φ) * T(e + n * size * f) * L0 * 親の worldMatrix``

(:meth:`BoxRoll.localMatrix` が対象のローカルの部分のPython版)。前半の ``T(-c) * R(n*90°) * T(c)`` は中心の周りの n 段分の回転で、
正方形は90度回しても同じ形なので、 ``n * size`` だけ前へ送ると底が再び床に平らに着きます。後半はその位置の前の下の縁
``e + n * size * f`` を支点に φ だけ回します。φ = 90° の姿勢は次の段の φ = 0 と一致するので、段の切り替わりで値が跳ねません。
支点の縁は床の上にあり続け(滑らない)、箱の角は床より下へ行きません。roll = 0 で生成時のワールド行列と一致し、接続しても跳ねません。
角度は係数を明示した ``unitConversion`` で内部単位(rad)のまま扱うので、UI単位がmm・ラジアンでも結果は同じです
(Maya 2025 の ``floor`` は入出力が長さの型なので、前後にも係数1の ``unitConversion`` を置いて数値のまま渡します)。

containerのアトリビュート
--------------------------

* ``roll``: 転がす角度(keyable、度/ラジアンはUI単位)。正なら ``axis × up`` の向き(例: axis=x・up=y なら +Z)へ進みます。負の角度では逆へ転がります。
* ``step``: 段の番号 ``floor(roll / 90°)`` (確認用、負の角度では負)。
* ``travel``: 支点の縁が進んだ距離 ``step * size`` (確認用)。
* ``matrix``: 転がした物体のワールド行列(出力)。

制限
----

* 断面は正方形で、1つの軸の回りにだけ転がります。長方形の断面(段ごとに進む量が交互に変わる)、2軸の転がり(サイコロを左右にも転がす。
  順番で姿勢が変わるため状態を持たない式では表せない)は扱いません。
* ``roll`` は角度の入力で、移動量から角度を求めません(段の中の角度と箱の中心の移動は比例しません)。
* 床は生成時の対象の「上」に垂直な平面です。斜面・段差には追従しません(親を傾ければ床も傾きます)。
* 角を丸めた箱、転がる勢い・跳ね返り(時間の積分が要る)は扱いません。
* 出力はワールド行列なので、原点以外の親の下へ繋ぐと二重に変換されます。

テスト
------

``mlrig/__tests__/test_setup_box_roll.py`` (``setups`` スイート)で、回転・移動した親の下の箱を作り、roll=0 で生成時と一致すること、
乱数25通りの正負の角度で、箱の角が床より下へ行かず、床に触れている角が段の支点の縁 ``(n + 1/2) * size`` にあり、箱の向きが roll だけ回っていること、
90度の倍数で底が床に平らに着き中心が ``size`` ずつ進むこと・段の切り替わりの前後で値が連続すること、Python版との一致と親への追従、
axis=z と底の中心の指定・UI単位 mm/rad(自動の単位変換ノードが入らない)、containerの所有と入力へ接続しないこと・Undo/Redo、
引数の検査を確認します。Maya 2025・2027で確認しています。

検証動画
--------

``tools/demo_box_roll.py`` は、新規シーンに一辺4cmの箱(緑)と床・比較用の中心で回すだけの箱(赤の枠)を横から見る構図で作り、
前へ3回転がる→後ろへ戻る→元へ戻す動きで、式と毎フレームの roll・step・φ・支点の縁の位置・一番低い角の高さをHUDに表示して録画します。
各フレームで行列が式と一致し、一番低い角が床の上にあることを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-box-roll.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_box_roll.py --launch
