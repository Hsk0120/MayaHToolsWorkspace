胸郭の上を滑る肩甲骨(ScapulaGlide)
====================================

``mlrig.setups.ScapulaGlide`` は、肩甲骨のコントロールなどの対象の位置を、胸郭を近似した楕円体の表面へ投影し、
表面の外向きの法線へ指定した軸を向けた行列を作ります。コントロールを背中から離しても、胸郭の中へ押し込んでも、
出力は常に表面に吸い付いたまま背中の上を滑り、肩甲骨の板が胸郭に沿って傾きます。
押し出しだけの :doc:`EllipsoidCollision <ellipsoid_collision>` と違い、表面から浮いた位置には留まりません。
Maya標準ノード(``decomposeMatrix`` ・ ``composeMatrix`` ・ ``plusMinusAverage`` ・ ``vectorProduct`` ・
``multiplyDivide`` ・ ``distanceBetween`` ・ ``condition`` ・ ``aimMatrix``)だけで組み、
独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import ScapulaGlide

   graph = ScapulaGlide.create("L_scapula_ctrl", "chest_jnt", name="L_scapulaGlide",
                               radiusX=14.0, radiusY=18.0, radiusZ=10.0, offset=1.0,
                               normalAxis="z", upAxis="y")
   owner = graph.container
   # 出力はワールド行列。原点にある親の下の、TRSがidentityのtransformで受ける
   owner.getPlug("matrix").connectTo("L_scapula_drv.offsetParentMatrix")

``radiusX`` ・ ``radiusY`` ・ ``radiusZ`` ・ ``offset`` はcontainerのkeyableなアトリビュートです。
楕円体の中心と軸の向きは ``ribcage`` のtransformのワールド位置・回転で、胸のjointを動かすと胸郭が付いてきます。

参考にした考え方
----------------

* 物を面に沿わせて置き、面に垂直に立てるのは、Mayaの
  `geometry constraint と normal constraint の組み合わせ <https://help.autodesk.com/cloudhelp/2016/ENU/Maya/files/GUID-7665A291-FAA7-44C0-BDEB-A6C83482116C.htm>`_
  として知られています。メッシュとの最近点の探索やメッシュの法線の平均の代わりに、楕円体の式で閉じた形に置き換えました。
* 肩甲骨や眉の骨のような、下の形に沿って滑る部位を面へ拘束する例は、
  `Autodesk フォーラムの normal constraint と geometry constraint の質問 <https://forums.autodesk.com/t5/maya-animation-and-rigging-forum/problem-with-normal-constraint-and-a-geometry-constraint-while/td-p/12701412>`_
  にもあり、上方向(World Up)の決め方が問題になりやすい点を参考に、上方向を対象の軸へ揃える形にしました。
* 楕円体の中心からの向きで表面までの距離を求める式は :doc:`EllipsoidCollision <ellipsoid_collision>` と同じです。

いずれもコードは流用していません。

引数
----

* ``target``: 投影する対象のtransform(肩甲骨のコントロール・鎖骨の先のlocatorなど)。位置と、上方向に使う軸の向きを読みます。
* ``ribcage``: 楕円体の中心と軸の向きを表すtransform(胸のjointなど)。scale・shearは半径に影響しません。
* ``radiusX`` ・ ``radiusY`` ・ ``radiusZ``: 局所X・Y・Z軸の半径の初期値(cm、1e-4以上)。
* ``offset``: 表面から法線の向きへ浮かせる距離の初期値(cm)。肩甲骨の厚みや皮下の厚みです。負なら内側へ沈めます。
* ``normalAxis``: 出力の行列で外向きの法線へ向ける軸(``"x"`` ・ ``"y"`` ・ ``"z"``)。
* ``upAxis``: 出力の行列で ``target`` の同じ軸の向きへ揃える軸。 ``normalAxis`` と異なる軸です。

計算式
------

``c`` を ``ribcage`` の位置、 ``Q`` をその回転(scaleを除く)、 ``p`` を ``target`` の位置、
``rx`` ・ ``ry`` ・ ``rz`` を半径とします。

1. 局所の向き ``l = normalize((p - c) · Q^-1)`` (``|p - c|`` が1e-6cm以下なら ``l = (1, 0, 0)``)。
2. 楕円体の半径 ``R = 1 / sqrt((lx / rx)^2 + (ly / ry)^2 + (lz / rz)^2)`` (出力の ``directionRadius``)。
3. 表面の点 ``s = l R`` 。 ``(sx / rx)^2 + (sy / ry)^2 + (sz / rz)^2 = 1`` を満たします。
4. 外向きの法線は陰関数 ``(x / rx)^2 + (y / ry)^2 + (z / rz)^2`` の勾配の向きで、
   ``n = normalize(sx / rx^2, sy / ry^2, sz / rz^2)`` 。ワールドでは ``normal = n · Q`` (出力の ``normal``)。
5. 出力の位置 ``out = c + s · Q + normal * offset`` 。
6. ``matrix`` は ``aimMatrix`` で、 ``out`` から ``normalAxis`` を ``normal`` の向きへ向け、 ``upAxis`` を
   ``target`` のワールドの ``upAxis`` の向き(法線に垂直な面へ射影したもの)へ揃えます。scaleは1です。
7. ``distance = |p - c| - R`` (対象が表面から離れている距離を中心からの向きに測ったもの。外が正、中が負)。

3つの半径が同じなら ``n = l`` で、球の表面への投影と同じです。
:meth:`ScapulaGlide.glidePosition` は同じ式をPythonで計算します(検証・配置の確認用)。

出力
----

* ``matrix``: 表面に乗せて法線へ向けたワールド行列。
* ``normal``: 出力位置での外向きの単位法線(ワールド)。補正シェイプや揺れ物の向きのドライバーに使えます。
* ``distance``: 対象と表面の放射方向の符号付き距離(cm)。コントロールをどれだけ引き離したか・押し込んだかの確認や、
  肩をすくめた量のドライバーに使えます。
* ``directionRadius``: 今の向きでの、中心から表面までの距離 ``R`` (cm)。

制限
----

* 投影は中心からの放射方向で、表面の最近点ではありません。軸の半径の比が大きいと、細い向きの近くでは
  コントロールの真下(最近点)から少しずれた位置に乗ります。3つの半径が同じなら厳密(球)です。
* 胸郭は楕円体1つで近似します。肋骨の凹凸・背骨の溝・メッシュへの吸着には対応しません。
* 中心から1e-6cm以下では向きが決まらないため、局所+Xの向きの表面を使います。中心を通り抜ける入力では、
  反対側の表面へ出力が飛びます。
* ``target`` の ``upAxis`` が法線と平行になると、法線まわりのねじれが不定になります。
* 回転はコントロールの ``upAxis`` だけを使い、肩甲骨の上方回旋・前傾などの解剖学的な回転は自動では付きません。
* 出力はワールド行列です。原点以外の親の下へ ``matrix`` を接続すると二重変換になります。
* ``plusMinusAverage`` ・ ``multiplyDivide`` は単精度なので、出力の位置には1e-6cm程度の丸めがあります。

テスト
------

``mlrig/__tests__/test_setup_scapula_glide.py`` (``setups`` スイート)で、回転・拡大した胸郭と回転したコントロールを作り、
表面の外・中・軸の向き・斜めの向きへ動かした場合に、出力の位置・法線・上方向・ ``distance`` ・ ``directionRadius`` が
OpenMayaで独立に求めた式と一致すること、 ``offset`` を除いた点が楕円体の表面にあること、法線が表面の接線に垂直なこと、
中心と一致する場合、半径・ ``offset`` の変更と胸郭の移動・回転、3つの半径が同じ場合に放射方向と一致すること、
別の軸の指定、Python版との一致、containerの所有とUndo/Redo、引数の検査を確認します。Maya 2027で確認しています。

検証動画
--------

``tools/demo_scapula_glide.py`` は、新規シーンに胸郭の楕円体(灰色・半透明)、入力のコントロール(赤い球)、
出力の肩甲骨の板(緑)とその外向きの法線(黄色の棒)を背中側の斜め上から見る構図で作り、式と毎フレームの入力の位置・
``distance`` ・出力の位置・ ``directionRadius`` ・法線・表面の式の値をHUDに表示して録画します。
背中から引き離す→胸郭の中へ押し込む→横(長い軸)へ回り込む→中心の近くまで入れる→上(長い軸)へ回る→元の位置への復帰を記録し、
各フレームで出力の位置と法線が式と一致し、出力が表面にあることを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-scapula-glide.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_scapula_glide.py --launch
