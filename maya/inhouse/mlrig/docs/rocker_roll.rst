丸い底の転がり(RockerRoll)
==========================

``mlrig.setups.RockerRoll`` は、底が半径 ``radius`` の円弧になった物体(揺り椅子の脚、丸い足の裏、起き上がり小法師、
転がる樽の側面など)を、角度 ``roll`` だけ床の上で滑らずに転がしたワールド行列を出力します。
回転の支点が角度とともに円弧の上の接地点へ移る「動く支点(rolling pivot / dynamic pivot)」を、1つの角度だけで扱えます。
Maya標準ノード(``unitConversion`` ・ ``multiplyDivide`` ・ ``composeMatrix`` ・ ``multMatrix``)だけで組み、
独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import RockerRoll

   # 揺り椅子(ローカル原点が脚の接地点、脚の円弧の半径40cm、X軸回りに前後へ揺れる)
   graph = RockerRoll.create("rockingChair", 40.0, name="chairRock", axis="x", upAxis="y")
   owner = graph.container
   # roll をキーで動かし、matrix をワールド直下の表示用transformの offsetParentMatrix へ繋ぐ
   mlib.getPlug("{}.matrix".format(owner)).connectTo("chairGeo.offsetParentMatrix")

参考にした考え方
----------------

* Lester Banks の記事「Incorporating a Dynamic Pivot in Your Rigs With Maya」・「Rigging a Box With a Dynamic Pivot in Maya」:
  転がる物体の回転の支点を中心でなく接地している縁へ置き、アニメーション中に支点を動かすことで、物体が地面に接したまま転がる考え方。
* 同じく Lester Banks の記事「Jarred Love Shows Two Methods for Creating a Movable Pivot for Animating in Maya」(動かせる支点の作り方)と、
  円柱の足を底の縁で転がす支点をベクトルの計算で動かすフットロールの紹介。
* 一般的な「滑らずに転がる」関係: 転がった弧の長さ ``radius * 角度`` と床の上の移動量が等しい(:doc:`WheelRoll <wheel_roll>` は
  移動から回転を求める向き、この部品は回転から移動と支点を求める向き)。

いずれもコードは流用していません。

引数
----

* ``target``: 転がす物体のtransform(joint可)。生成時のローカル行列(``matrix * offsetParentMatrix``)と親のワールド行列を基準にします。
* ``radius``: 底の円弧の半径(0より大きい、cm)。containerの ``radius`` として後から変えられます。
* ``axis``: 転がる回転軸(対象のローカル、x/y/z)。
* ``upAxis``: 対象のローカルの上の軸(x/y/z、axisと別の軸)。円弧の中心は接地点からこの向きへ ``radius`` 。
* ``contact``: 生成時の接地点(対象のローカル、cm)。既定はローカル原点。

計算式
------

円弧の中心を ``c = contact + radius * up`` 、転がる向きを ``f = axis × up`` として(行ベクトル規約)、

``matrix = T(-c) * R_axis(roll) * T(radius * roll * f) * T(c) * L0 * 親の worldMatrix``

(:meth:`RockerRoll.localMatrix` が対象のローカルの部分のPython版)。中心は ``radius * roll`` (roll はラジアン)だけ ``f`` へ進み、
物体は中心の周りに ``roll`` だけ回るので、角度 ``roll`` の位置の円弧の点がちょうど床に触れます(接地点が円弧の上を移る)。
roll = 0 で生成時のワールド行列と一致し、接続しても跳ねません。角度・長さは係数1の ``unitConversion`` で内部単位(rad・cm)のまま掛けるので、
UI単位がmm・ラジアンでも結果は同じです。

containerのアトリビュート
--------------------------

* ``roll``: 転がす角度(keyable、度/ラジアンはUI単位)。正なら ``axis × up`` の向き(例: axis=x・up=y なら +Z)へ進みます。
* ``radius``: 底の円弧の半径(keyable)。変えると中心の高さと進む量が変わります。
* ``travel``: 中心が進んだ距離 ``radius * roll`` (確認用)。
* ``matrix``: 転がした物体のワールド行列(出力)。

制限
----

* 底は1つの半径の円弧で、1つの軸の回りにだけ転がります。楕円・平らな部分のある底(箱の縁で転がる場合)、2軸の転がり(球の底)は扱いません。
* 床は生成時の対象の「上」に垂直な平面です。斜面・凹凸には追従しません(親を傾ければ床も傾きます)。
* 円弧の範囲(脚の端)を超えて転がす角度の制限はありません。揺り椅子の脚の長さに合わせた範囲は ``roll`` のキーで守ります。
* 出力はワールド行列なので、原点以外の親の下へ繋ぐと二重に変換されます。

テスト
------

``mlrig/__tests__/test_setup_rocker_roll.py`` (``setups`` スイート)で、回転・移動した親の下の物体を作り、roll=0 で生成時と一致すること、
正負・半回転を超える角度で OpenMaya の ``MTransformationMatrix`` で独立に組んだ行列と Python版に一致すること、
角度 roll の位置の円弧の点が転がった弧の長さだけ前の床の点に一致し中心がいつも床から radius の高さにあること(滑らない)、
radius の変更と親の移動回転への追従、axis=z と接地点の指定・UI単位 mm/rad(自動の単位変換ノードが入らない)、
containerの所有とUndo/Redo、引数の検査を確認します。Maya 2025・2027で確認しています。

検証動画
--------

``tools/demo_rocker_roll.py`` は、新規シーンに円弧の脚(緑)と座面の箱・比較用の中心で回すだけの脚(赤)を横から見る構図で作り、
前へ揺らす→後ろへ揺らす→半径のアトリビュートを変える(描いた脚の円弧は4cmのまま)→元へ戻す動きで、式と毎フレームの roll・travel・接地点の位置をHUDに表示して録画します。
各フレームで行列が式と一致し、接地点が床の上(高さの誤差)・転がった弧の長さだけ前にあることを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-rocker-roll.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_rocker_roll.py --launch
