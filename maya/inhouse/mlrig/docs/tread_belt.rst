履帯・ベルトの巡回(TreadBelt)
==============================

``mlrig.setups.TreadBelt`` は、閉じたNURBS曲線(履帯・キャタピラ・コンベアのベルトの通り道)の上に、
count 枚の板(駒)を弧長で等間隔に並べ、送り量 ``distance`` に合わせて一周し続けるワールド行列を出力します。
車体の移動量を ``driver`` に渡すと、地面に付いた側の板がその場に止まるように履帯が回ります。
Maya標準ノード(``curveInfo`` ・ ``multiplyDivide`` ・ ``plusMinusAverage`` ・ ``animCurveUU`` ・ ``motionPath`` ・ ``composeMatrix``)だけで組み、
独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import TreadBelt

   # 車体の子にある閉じた曲線(YZ面、法線はX)の上を、車体の translateZ で24枚の板が巡回する
   graph = TreadBelt.create("tread_path", 24, name="leftTread", normal=(1, 0, 0),
                            driver="tank.translateZ")
   owner = graph.container
   for index in range(24):
       # 出力はワールド行列。ワールド直下の板の offsetParentMatrix へ繋ぐ
       mlib.getPlug("{}.matrix{}".format(owner, index)).connectTo("plate{}.offsetParentMatrix".format(index))

参考にした考え方
----------------

* tech-artists.org のフォーラム「Motion path in maya」: 履帯の板ごとに motion path を作り、板ごとに位置をずらす。
  motion path のアニメーションカーブを cycle(cycle with offset ではない)の外挿で繰り返して一周を続け、
  タイムラインの代わりに「track」のようなアトリビュートをアニメーションカーブの入力へ繋いで駆動する考え方。
* Lester Banks の戦車のリグを紹介する記事(2017年3月、lesterbanks.com/2017/03/rig-tank-maya/)で紹介されている、履帯の板を1本の曲線に沿って同期して動かし、
  車輪の動きと合わせる戦車のリグの構成。
* polycount のフォーラムで挙がっていた、駆動輪の周りで板が裏返る(flip)問題。この部品は上方向を曲線のtransformの
  回転に付いて回るベルトの面の法線(motionPath の objectRotation)にして、曲線上のどこでも裏返らないようにしました。

この部品は、時間で動くアニメーションカーブの代わりに、0→0・1→1 の直線キーを前後とも cycle にした ``animCurveUU`` を
「小数部分を取る」ノードとして使い、送り量から求めた割合を0〜1へ折り返します。いずれもコードは流用していません。

引数
----

* ``curve``: 閉じた(closed/periodic)NURBS曲線のtransform、またはnurbsCurveシェイプ。開いた曲線は ``ValueError`` です。
* ``count``: 板の数(1以上)。一周を弧長で等分した位置に並びます。
* ``normal``: 曲線のローカル空間での、ベルトの面の法線。板の ``upAxis`` がこの向き(を接線に直交させた向き)を向きます。
* ``frontAxis`` ・ ``upAxis``: 板のローカルで、曲線の接線へ向ける軸と、法線へ向ける軸(x/y/z、別の軸)。既定はX・Z。
* ``driver``: 送り量を駆動する長さのplug(車体の ``translateZ`` など)。指定すると ``distance = driver - 生成時の値`` になり、
  生成時は板が動きません。省略した場合は ``distance`` を直接キーや接続で動かします。

計算式
------

1. ``length`` = 曲線のワールドでの長さ(``curveInfo.arcLength``)。曲線を変形させると毎回求め直します。
2. ``fraction<i> = frac(i / count + phase + distance / length)`` (:meth:`TreadBelt.fractions`)。 ``frac`` は
   cycle の外挿の ``animCurveUU`` で、負の値や一周を超える値も0〜1へ折り返します。
3. ``motionPath`` (fractionMode = 弧長の割合)が ``fraction<i>`` の位置と、 ``frontAxis`` を接線・ ``upAxis`` を法線へ向けた回転を出し、
   ``composeMatrix`` で ``matrix<i>`` にします。

``distance`` が正なら曲線の向き(パラメーターの増える向き)へ送ります。車体を前へ動かしたときに地面側の板が後ろへ送られるよう、
曲線の向き(または ``normal`` の向きで作る円の回り方)を合わせます。 ``motionPath.uValue`` は長さの型なので、
割合は係数1の ``unitConversion`` で渡し、 ``distance`` と ``length`` も同じく係数1で数値として割るので、UI単位がmmでも結果は変わりません。

containerのアトリビュート
--------------------------

* ``distance``: 送り量(長さ、keyable)。 ``driver`` を指定した場合は接続済みです。
* ``phase``: 一周を1とした全体のずらし量(keyable)。駆動輪の歯と板の合わせに使います。
* ``length``: 曲線の長さ(確認用)。
* ``fraction0`` 〜 ``fraction<n-1>``: 各板の弧長の割合(確認用)。
* ``matrix0`` 〜 ``matrix<n-1>``: 各板のワールド行列(出力)。

制限
----

* 板の間隔は曲線に沿った長さで等しく、板と板の間の直線距離(弦)ではありません。曲がりの強い所では板の間の直線距離が少し縮みます。
* 板そのものの長さ・ピンの連結は扱いません。曲線の長さを変えると板の間隔が変わります(板の数は作成時に固定)。
* 駆動輪・遊動輪の回転は含みません。同じ ``distance`` (または車体の移動量)で :doc:`WheelRoll <wheel_roll>` を組み合わせます。
* 履帯のたるみ・地面の凹凸への追従は、曲線そのものを変形(CVをjointやクラスターで動かす)して与えます。
* 出力はワールド行列なので、原点以外の親の下へ繋ぐと二重に変換されます。

テスト
------

``mlrig/__tests__/test_setup_tread_belt.py`` (``setups`` スイート)で、移動・回転したtransformの下の横長の閉じた曲線を作り、
送り量0・正・負・一周超と phase で、各板の割合と位置・接線・上方向が OpenMaya の ``MFnNurbsCurve`` で弧長から独立に求めた値と一致すること、
隣り合う板の間が弧長で ``length / count`` であること、driver の変化量が送り量になり生成時に動かず一周で元へ戻ること、
一周を120分割で送っても上方向が面の法線側から外れず1ステップの向きの変化が小さいこと(裏返らない)、曲線のCVを動かしたときの追従、
UI単位mmで自動の単位変換ノードが入らないことと軸・法線の指定、containerの所有とUndo/Redo、引数の検査を確認します。
Maya 2025・2027で確認しています。

検証動画
--------

``tools/demo_tread_belt.py`` は、新規シーンに長円の履帯の通り道と、車体(灰色の箱)・16枚の板(緑)・前後の車輪の目印を横から見る構図で作り、
車体を前へ進める→止まる→後ろへ戻す→phaseを変える動きで、式と毎フレームの送り量・長さ・板の割合・地面側の板の位置をHUDに表示して録画します。
各フレームで板の位置と向きが弧長からの独立計算と一致し、上方向が裏返らないことを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-tread-belt.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_tread_belt.py --launch
