カプセルとの柔らかい衝突(CapsuleCollision)
============================================

``mlrig.setups.CapsuleCollision`` は、コントロールなどの対象の位置が、太もも・上腕・胴などを近似したカプセル
(2点を結ぶ線分を軸とし、両端が半球の形)の中へ入らないよう、軸から対象への向きへ押し出した行列を作ります。
始点側と終点側で半径を変えられるので、先細りの手足も近似できます。表面に近づくと ``softness`` の帯の中で
少しずつ押し返し始め、中へ入れても出力は表面へ漸近します。スカート・袖・装備品のコントロールと手足の接触などに使えます。
押し込んだ深さ ``penetration`` と軸上の位置 ``parameter`` も出力するので、補正シェイプのドライバーにも使えます。
Maya標準ノード(``decomposeMatrix`` ・ ``plusMinusAverage`` ・ ``vectorProduct`` ・ ``multiplyDivide`` ・ ``clamp`` ・
``distanceBetween`` ・ ``condition`` ・ ``composeMatrix`` ・ ``multMatrix``)だけで組み、
独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import CapsuleCollision

   graph = CapsuleCollision.create("skirt_ctrl", "L_thigh_jnt", "L_knee_jnt", name="skirtThigh",
                                   startRadius=8.0, endRadius=6.0, softness=1.0)
   owner = graph.container
   # 出力はワールド行列。原点にある親の下の、TRSがidentityのtransformで受ける
   owner.getPlug("matrix").connectTo("skirt_drv.offsetParentMatrix")
   # 押し込んだ深さで補正シェイプを駆動する例
   owner.getPlug("penetration").connectTo("thighPress_remap.inputValue")

``startRadius`` ・ ``endRadius`` ・ ``softness`` はcontainerのkeyableなアトリビュートです。軸は ``start`` と ``end`` の
transformの位置を結ぶ線分で、どちらを動かしてもカプセルが付いてきます。

参考にした考え方
----------------

* `maya_expressionCollision <https://github.com/akasaki1211/maya_expressionCollision>`_ (MIT):
  エクスプレッションで作るカプセルのコライダー。軸への射影の比率で両端の半径を線形に補間する先細りのカプセルも同じ考え方です。
  こちらはエクスプレッションを使わず、DGノードで組みました。
* 線分への最近点は、内積による射影を0〜1に制限する一般的な式です(Lester Banks の記事で紹介されている、Bifrostで線分からの距離を
  内積で求める解説など)。
* 柔らかく止める式は :doc:`SphereCollision <sphere_collision>` ・ :doc:`PlaneCollision <plane_collision>` と同じで、
  最近点を中心とした押し出しのグラフをSphereCollisionと共有しています。

いずれもコードは流用していません。

引数
----

* ``target``: 押し出す対象のtransform。出力はこの現在のワールド行列を平行移動したものです。
* ``start`` ・ ``end``: 軸の始点・終点を表すtransform(上腕と肘、太ももと膝のjointなど)。scaleは半径に影響しません。
* ``startRadius`` ・ ``endRadius``: 始点側・終点側の半径の初期値(cm、0以上)。同じ値なら円柱に半球を付けた通常のカプセルです。
* ``softness``: 柔らかく押し出し始める距離の初期値(cm、0以上)。0なら表面で硬く止めます。

計算式
------

``a`` ・ ``b`` を ``start`` ・ ``end`` の位置、 ``p`` を ``target`` の位置、 ``s`` を ``softness`` とします。

1. 軸上の位置 ``t = clamp(dot(p - a, b - a) / |b - a|^2, 0, 1)`` (出力の ``parameter``)。 ``|b - a|^2 <= 1e-12`` なら ``t = 0`` 。
2. 最近点 ``q = a + t (b - a)`` 、半径 ``r = startRadius + (endRadius - startRadius) t`` 。
3. 向き ``u = (p - q) / |p - q|`` (1e-6cm以下なら ``push = 0``)、距離 ``d = |p - q| - r`` (出力の ``distance``)。
4. 押し出した後の距離 ``d'`` は :meth:`PlaneCollision.response <mlrig.setups.PlaneCollision.response>` と同じです。

   * ``d >= s`` なら ``d' = d`` (帯の外は入力のまま)。
   * ``d < s`` なら ``d' = s * exp((d - s) / s)`` 。 ``d = s`` で値と傾き(1)が連続し、 ``d`` を下げても ``d'`` は正のまま0へ漸近します。
   * ``s = 0`` なら ``d' = max(d, 0)`` (硬い押し出し)。

5. ``push = d' - d`` (0以上、出力の ``push``)、 ``matrix = target.worldMatrix · T(u * push)`` 。回転とscaleは入力のままです。
6. ``penetration = max(-d, 0)`` (入力がカプセルの中へ入った深さ、cm)。

``u`` は軸の途中では軸に垂直なので、押し出しても ``t`` は変わりません。軸の端より先(``t`` が0・1に張り付く範囲)では、
端の点を中心とする半球の押し出しになります。生成時に対象が表面から ``softness`` 以上離れていれば ``push = 0`` なので、
出力は入力と一致し、作成時に姿勢が跳ねません。 :meth:`CapsuleCollision.pushedPosition` ・
:meth:`CapsuleCollision.closestParameter` は同じ式をPythonで計算します(検証・配置の確認用)。

出力
----

* ``matrix``: 押し出した後のワールド行列。
* ``distance``: カプセルの表面からの符号付き距離(cm、確認用)。
* ``push``: 軸から外への向きへ押し出した量(cm)。
* ``penetration``: 入力がカプセルの中へ入った深さ(cm、0以上)。
* ``parameter``: 軸上の最近点の位置(0=始点、1=終点)。 ``penetration`` と組み合わせて、どの高さで押し込まれたかで補正シェイプを分けられます。

制限
----

* 半径が両端で違う場合、 ``r`` は軸への垂直な射影の位置で補間する近似です。先細りの側面の真の最近点(円錐台の母線への垂線の足)とは、
  半径の差が大きいほどずれます。出力は近似した表面(同じ ``r(t)`` の距離)の外へは出ますが、側面の傾きの分だけ押し出しの向きは
  軸に垂直のままです。両端の半径が同じなら厳密です。
* 対象が軸上にある(最近点から1e-6cm以下)と向きが決まらないため、 ``push = 0`` として押し出しません。軸を通り抜ける入力では、
  通り抜けた側へ出力が飛びます。
* カプセル1つだけです。複数のコライダーの合成、メッシュとの衝突には対応しません。
* 押し出すのは位置だけで、表面に沿わせる回転や摩擦はありません。
* 出力はワールド行列です。原点以外の親の下へ ``matrix`` を接続すると二重変換になります。
* ``plusMinusAverage`` ・ ``multiplyDivide`` は単精度なので、出力の位置には1e-6cm程度の丸めがあります。

テスト
------

``mlrig/__tests__/test_setup_capsule_collision.py`` (``setups`` スイート)で、傾けた軸(端に回転・拡大あり)と回転した対象を作り、
側面の5つの高さ・3つの向きで帯の外・帯の中・中・軸の近くまで入れた場合と、軸の端より先(半球)の場合に、出力の行列・
``distance`` ・ ``push`` ・ ``penetration`` ・ ``parameter`` がOpenMayaで独立に求めた式と一致すること、表面の中へ入らないこと、
作成直後に跳ねないこと、 ``softness = 0`` の硬い押し出しと半径・ ``softness`` の変更、軸の移動と出力の回転の保持、
両端が一致した場合(球)と軸上の場合、Python版との一致、containerの所有とUndo/Redo、引数の検査を確認します。Maya 2027で確認しています。

検証動画
--------

``tools/demo_capsule_collision.py`` は、新規シーンに先細りのカプセル(灰色)と、入力(赤・半透明)・出力(緑)の小さな球を正面から見る構図で作り、
式と毎フレームの ``parameter`` ・入力の軸からの距離・ ``r`` ・ ``distance`` ・ ``push`` ・ ``penetration`` ・出力の表面からの距離をHUDに表示して録画します。
側面の帯への進入→中→軸の近くまで深く入れる→中で上下へ動かして先細りの半径に沿わせる→端の半球を回り込む→
``softness`` を0(硬い押し出し)→元の位置への復帰を記録し、各フレームで出力の位置が式と一致し、中へ入らないことを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-capsule-collision.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_capsule_collision.py --launch
