輪との柔らかい衝突(TorusCollision)
====================================

``mlrig.setups.TorusCollision`` は、コントロールなどの対象の位置が、スカートの骨組みの輪(フープ)・腕輪・袖口・
首輪・浮き輪などを近似したトーラス(輪)の管の中へ入らないよう、輪の芯の円から対象への向きへ押し出した行列を作ります。
輪の内側(穴)は通り抜けられるので、輪をくぐる手や、輪の縁に引っかかる布のコントロールに使えます。
表面に近づくと ``softness`` の帯の中で少しずつ押し返し始め、中へ入れても出力は表面へ漸近します。
押し込んだ深さ ``penetration`` 、輪の平面からの高さ ``height`` 、軸からの距離 ``axisDistance`` も出力するので、
補正シェイプのドライバーにも使えます。
Maya標準ノード(``decomposeMatrix`` ・ ``composeMatrix`` ・ ``vectorProduct`` ・ ``plusMinusAverage`` ・ ``multiplyDivide`` ・
``distanceBetween`` ・ ``condition`` ・ ``multMatrix``)だけで組み、独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import TorusCollision

   graph = TorusCollision.create("hand_ctrl", "skirtHoop_loc", name="skirtHoop",
                                 majorRadius=30.0, minorRadius=1.5, softness=1.0)
   owner = graph.container
   # 出力はワールド行列。原点にある親の下の、TRSがidentityのtransformで受ける
   owner.getPlug("matrix").connectTo("hand_drv.offsetParentMatrix")
   # 押し込んだ深さで補正シェイプを駆動する例
   owner.getPlug("penetration").connectTo("hoopPress_remap.inputValue")

``majorRadius`` ・ ``minorRadius`` ・ ``softness`` はcontainerのkeyableなアトリビュートです。輪の中心と向きは ``torus`` の
transformのワールド行列から取り、局所Yが輪の軸(輪の平面の法線)です。 ``torus`` を動かす・回すと輪が付いてきます。

参考にした考え方
----------------

* トーラスの符号付き距離 ``length(vec2(length(p.xz) - R, p.y)) - r`` は、Inigo Quilez の
  `distance functions <https://iquilezles.org/articles/distfunctions/>`_ で紹介されている一般的な式です。
  ここでは局所座標へ変換する代わりに、輪の軸 ``n`` への射影で高さと平面内の成分を分け、芯の円上の最近点を明示的に求めています。
* 柔らかく止める式は :doc:`SphereCollision <sphere_collision>` ・ :doc:`PlaneCollision <plane_collision>` と同じで、
  最近点を中心とした押し出しのグラフをSphereCollisionと共有しています。 :doc:`CapsuleCollision <capsule_collision>` が
  「線分上の最近点」を使うのに対し、こちらは「円上の最近点」を使います。

コードは流用していません。

引数
----

* ``target``: 押し出す対象のtransform。出力はこの現在のワールド行列を平行移動したものです。
* ``torus``: 輪の中心と向きを表すtransform(局所Yが軸)。scaleは半径に影響しません(回転だけを使います)。
* ``majorRadius``: 輪の芯の円の半径の初期値(cm、0以上)。0なら輪の中心を中心とする球と同じです。
* ``minorRadius``: 管の半径の初期値(cm、0以上)。対象の太さを含めてもよいです。
* ``softness``: 柔らかく押し出し始める距離の初期値(cm、0以上)。0なら表面で硬く止めます。

計算式
------

``c`` を ``torus`` の位置、 ``n`` ・ ``x`` を ``torus`` の局所Y・局所Xのワールドの向き(scaleを除いた回転、長さ1)、
``p`` を ``target`` の位置、 ``R`` ・ ``r`` ・ ``s`` を ``majorRadius`` ・ ``minorRadius`` ・ ``softness`` とします。

1. ``v = p - c`` 、高さ ``h = dot(v, n)`` (出力の ``height``)、平面内の成分 ``w = v - h n`` 、軸からの距離 ``|w|`` (出力の ``axisDistance``)。
2. 芯の円上の最近点 ``q = c + R w / |w|`` 。 ``|w| <= 1e-6`` cm(軸上)なら ``w`` の代わりに ``x`` を使います。
3. 向き ``u = (p - q) / |p - q|`` (1e-6cm以下なら ``push = 0``)、距離 ``d = |p - q| - r`` (出力の ``distance``)。
   ``|p - q| = sqrt((|w| - R)^2 + h^2)`` なので、これはトーラスの厳密な符号付き距離です。
4. 押し出した後の距離 ``d'`` は :meth:`PlaneCollision.response <mlrig.setups.PlaneCollision.response>` と同じです。

   * ``d >= s`` なら ``d' = d`` (帯の外は入力のまま)。
   * ``d < s`` なら ``d' = s * exp((d - s) / s)`` 。 ``d = s`` で値と傾き(1)が連続し、 ``d`` を下げても ``d'`` は正のまま0へ漸近します。
   * ``s = 0`` なら ``d' = max(d, 0)`` (硬い押し出し)。

5. ``push = d' - d`` (0以上、出力の ``push``)、 ``matrix = target.worldMatrix · T(u * push)`` 。回転とscaleは入力のままです。
6. ``penetration = max(-d, 0)`` (入力が管の中へ入った深さ、cm)。

``u`` は ``n`` と ``w`` の張る平面の中にあるので、押し出しても対象が輪を回る角度は変わりません。軸上では芯の円上の全ての点が
等距離なので ``d`` は連続し、押し出す向きだけを ``x`` で決めます。生成時に対象が表面から ``softness`` 以上離れていれば
``push = 0`` なので、出力は入力と一致し、作成時に姿勢が跳ねません。 :meth:`TorusCollision.pushedPosition` ・
:meth:`TorusCollision.closestRingPoint` は同じ式をPythonで計算します(検証・配置の確認用。軸上の向きは ``fallback`` で渡します)。

出力
----

* ``matrix``: 押し出した後のワールド行列。
* ``distance``: トーラスの表面からの符号付き距離(cm、確認用)。
* ``push``: 芯の円から外への向きへ押し出した量(cm)。
* ``penetration``: 入力が管の中へ入った深さ(cm、0以上)。
* ``height``: 輪の平面からの符号付きの高さ(cm、 ``n`` の向きが正)。輪のどちら側から押し込まれたかを分けられます。
* ``axisDistance``: 輪の軸からの距離(cm)。 ``majorRadius`` より小さければ輪の内側(穴の側)です。

制限
----

* 輪は真円で、管の太さは一定です。楕円の輪、太さの変わる管には対応しません。 ``torus`` のscaleは無視します。
* ``majorRadius < minorRadius`` (穴の無いトーラス)でも式は同じですが、穴は塞がり、軸の近くでは押し出す向きが ``x`` に固定されます。
  軸上を通り抜ける入力では、出力が ``x`` の側へ飛びます。
* 対象が芯の円上にある(最近点から1e-6cm以下)と向きが決まらないため、 ``push = 0`` として押し出しません。
* トーラス1つだけです。複数のコライダーの合成、メッシュとの衝突には対応しません。
* 押し出すのは位置だけで、表面に沿わせる回転や摩擦はありません。
* 出力はワールド行列です。原点以外の親の下へ ``matrix`` を接続すると二重変換になります。
* ``plusMinusAverage`` ・ ``multiplyDivide`` は単精度なので、出力の位置には1e-6cm程度の丸めがあります。

テスト
------

``mlrig/__tests__/unit/setups/test_torusCollision.py`` (``setups`` スイート)で、傾けた輪(回転・不均一なscaleあり)と回転した対象を作り、
輪の4つの角度×管の断面の5つの角度×5つの距離で帯の外・帯の中・中・芯の近くまで入れた場合、穴の中と軸上の場合に、
出力の行列・ ``distance`` ・ ``push`` ・ ``penetration`` ・ ``height`` ・ ``axisDistance`` がOpenMayaで独立に求めた式と一致すること、
トーラスの表面の中へ入らないこと、作成直後に跳ねないこと、 ``softness = 0`` の硬い押し出しと半径・ ``softness`` の変更、
輪の移動・回転と出力の回転の保持、 ``majorRadius = 0`` (球)、Python版との一致、containerの所有とUndo/Redo、引数の検査を確認します。
Setup Samples の ``TorusCollision - soft hoop collider`` も ``unit/root/test_setupSamples.py`` で確認します。Maya 2027で確認しています。

検証動画
--------

``tools/demo_torus_collision.py`` は、新規シーンに傾けた輪(灰色のトーラス)と、入力(赤・半透明)・出力(緑)の小さな球を斜め上から見る構図で作り、
式と毎フレームの ``height`` ・ ``axisDistance`` ・管の芯からの入力の距離・ ``distance`` ・ ``push`` ・ ``penetration`` ・出力の表面からの距離をHUDに表示して録画します。
外から管の帯への進入→管の中→芯の近くまで深く入れる→管の断面を回り込む→輪の穴をくぐる→ ``softness`` を0(硬い押し出し)→
元の位置への復帰を記録し、各フレームで出力の位置が式と一致し、管の中へ入らないことを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-torus-collision.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_torus_collision.py --launch
