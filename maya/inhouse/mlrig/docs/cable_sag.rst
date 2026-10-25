ケーブルの垂れ(CableSag)
=========================

``mlrig.setups.CableSag`` は、2つのtransform(留め具)の間に張ったケーブル・ホース・ロープ・電線が、長さ ``length`` を保つように
垂れた形の上の ``count`` 個の点のワールド行列(``matrix0`` 〜)を出力します。両端を近づけるほど深く垂れ、長さ以上に離すと一直線に張ります。
シミュレーションを使わず、両端のコントロールを動かすだけでケーブルの形が決まるので、揺れ物の前段の形や、背景の電線・ホースの配置に使えます。
Maya標準ノード(``vectorProduct`` ・ ``plusMinusAverage`` ・ ``multiplyDivide`` ・ ``clamp`` ・ ``unitConversion`` ・ ``fourByFourMatrix``)だけで組み、
独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   import mlib
   from mlrig.setups import CableSag

   # hookA・hookB はケーブルを留める位置のtransform(コントロールの子など)
   graph = CableSag.create("hookA", "hookB", 9, name="hose", length=12.0)
   owner = graph.container
   # 出力はワールド行列。ワールド直下のjoint(ケーブルのスキンの骨)の offsetParentMatrix へ繋ぐ
   for index in range(9):
       mlib.getPlug("{}.matrix{}".format(owner, index)).connectTo("hose{}_jnt.offsetParentMatrix".format(index))

参考にした考え方
----------------

* 80.lv の記事「Fully Procedural Catenary Curves Generator in Maya」: シミュレーションを使わないノードベースのケーブルの曲線で、
  リグ・アニメーション向けに、制御点を動かしても長さを保つ「長さ固定」のモードを持ち、曲線は懸垂線(catenary)の放物線による近似で作る考え方。
* John D. Cook のブログ記事「How much will a cable sag? A simple approximation」: 長さ ``2s`` のケーブルを距離 ``2x`` で張った
  懸垂線の中央の深さ ``g`` を、 ``g² ≈ (s - x)(s + x/2)`` (J. S. Frame の近似、相対誤差1/117未満)で求める考え方。
  ここでは ``L = 2s`` ・ ``D = 2x`` に書き直した ``h² = (L - D)(2L + D)/8`` を使います。
  垂れが浅い場合は放物線の弧長の近似 ``L ≈ D + 8h²/(3D)`` と同じ値になります。

コードは流用していません(記事にはコードがありません)。

引数
----

* ``start`` ・ ``end``: ケーブルの両端のtransform(joint・locator可)。ワールド位置だけを使います。
* ``count``: 出力する点の数(両端を含む、2以上)。 ``matrix0`` が ``start`` 、 ``matrix<count-1>`` が ``end`` の位置です。
* ``length``: ケーブルの長さ(cm、UI単位によらない)。省略すると生成時の両端の距離の1.1倍。containerの ``length`` (keyable)で後から変えられます。
* ``gravity``: 重力の向き(ワールド、既定 ``(0, -1, 0)``)。長さは問いません。

計算式
------

両端の位置 ``A`` ・ ``B`` 、弦 ``C = B - A`` 、弦の長さ ``D = |C|`` 、重力の単位ベクトル ``g`` として、

``h = sqrt(max((L - D)(2L + D)/8, 0))`` (垂れの深さ、 ``sag``。水平に張った懸垂線の中央の深さとの差は1/117未満)

``n = normalize(g - (g·Ĉ)Ĉ)`` (弦に垂直で重力に最も近い向き)

``P(u) = A + C·u + n·h·4u(1-u)`` 、 ``P'(u) = C + n·h·4(1-2u)`` 、 ``u = i/(count-1)``

点 ``i`` の行列は、X = ``normalize(P'(u))`` (ケーブルに沿う向き)、Z = ``normalize(X × (-g))`` 、Y = ``Z × X`` 、位置 ``P(u)`` を
``fourByFourMatrix`` で組んだワールド行列です(Y は重力と反対の側)。 :meth:`CableSag.points` がPython版です。
形は懸垂線を中央の深さ ``h`` の放物線で近似します。垂れは弦に垂直な向きに付き、弦が傾いた場合も同じ式を弦の長さで使います
(傾いた懸垂線は左右非対称になりますが、その違いは扱いません)。
両端の位置は ``vectorProduct`` (点×行列)で単位なしのまま取り出し、長さは係数1の ``unitConversion`` で数値にするので、UI単位がmmでも結果は同じです。

containerのアトリビュート
--------------------------

* ``length``: ケーブルの長さ(keyable)。
* ``sag``: 弦の中央からの垂れの深さ ``h`` (確認用)。
* ``span``: 両端の距離 ``D`` (確認用)。
* ``matrix<i>``: 点 ``i`` のワールド行列(出力)。

制限
----

* 形は懸垂線でなく、深さを懸垂線に合わせた放物線の近似です。出力の点を通る放物線の弧長は ``length`` より少し短く、
  長さが弦の1.1倍で約0.2%、1.2倍で約0.5%、1.4倍で約1.1%、2倍で約2.3%短くなります。弦が傾くと実際の懸垂線は低い側へ寄りますが、この形は左右対称です。
  点の間隔は ``u`` で等間隔で、弧長で等間隔ではありません(垂れが深いと両端の間隔が広くなります)。
* 両端の距離が ``length`` 以上になると垂れは0で、ケーブルは弦の上に一直線に並んだまま伸びます(長さを保って留め具を引き止めることはしません)。
* 両端が真上・真下に並ぶ(弦が重力と平行)と、垂れる向きと枠が決まりません。長さが余っていてもケーブルは一直線になり、枠が回ることがあります。
* 地面・物体との衝突、ケーブルの重さ・張力による揺れ、ねじれは扱いません(揺れは出力の骨に揺れ物を重ねて付けます)。
* 出力はワールド行列なので、原点以外の親の下へ繋ぐと二重に変換されます。

テスト
------

``mlrig/__tests__/test_setup_cable_sag.py`` (``setups`` スイート)で、回転・移動した柱の子の始点とワールド直下の終点の間に7点のケーブルを作り、
終点を上下前後へ動かした各姿勢で点の位置・枠がOpenMayaで独立に求めた放物線の点と接線に一致し両端が留め具の位置にあること、
水平に張ると中央が弦から真下へ ``sag`` だけ垂れ両端を近づけるほど深くなること、 ``sag`` が二分法で解いた懸垂線の中央の深さと1/117未満の差であること、
細かい折れ線で求めた放物線の弧長と ``length`` の差が上の近似の精度以内であること、
張った場合に垂れ0で弦の上に等間隔に並ぶこと、重力の向き・点の数、UI単位 mm/rad、containerの所有とUndo/Redo、引数の検査を確認します。
Maya 2025・2027で確認しています。

検証動画
--------

``tools/demo_cable_sag.py`` は、新規シーンに2本の柱と、その間のケーブルの点(緑)と点を結ぶ曲線を正面から見る構図で作り、
右の留め具を近づける・離す・上下させたあと ``length`` を変える動きで、式と毎フレームの ``span`` ・ ``sag`` ・弧長と ``length`` の比をHUDに表示して録画します。
各フレームで点の位置が式と一致することを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-cable-sag.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_cable_sag.py --launch
