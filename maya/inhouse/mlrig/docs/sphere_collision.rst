球との柔らかい衝突(SphereCollision)
====================================

``mlrig.setups.SphereCollision`` は、コントロールなどの対象の位置が、頭・肩・腹・膝などを近似した球の中へ入らないよう、
球の中心から対象への向きへ押し出した行列を作ります。表面に近づくと ``softness`` の帯の中で少しずつ押し返し始め、
球の中へ入れても出力は表面へ漸近します。手と頭、髪・服のコントロールと体の接触などに使えます。
押し込んだ深さ ``penetration`` も出力するので、補正シェイプのドライバーにも使えます。
Maya標準ノード(``decomposeMatrix`` ・ ``plusMinusAverage`` ・ ``vectorProduct`` ・ ``distanceBetween`` ・
``multiplyDivide`` ・ ``condition`` ・ ``composeMatrix`` ・ ``multMatrix``)だけで組み、
独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import SphereCollision

   graph = SphereCollision.create("hand_ctrl", "head_collider", name="handHead",
                                  radius=9.0, softness=1.0)
   owner = graph.container
   # 出力はワールド行列。原点にある親の下の、TRSがidentityのtransformで受ける
   owner.getPlug("matrix").connectTo("hand_ik_goal.offsetParentMatrix")
   # 押し込んだ深さで補正シェイプを駆動する例
   owner.getPlug("penetration").connectTo("cheekPress_remap.inputValue")

``radius`` ・ ``softness`` はcontainerのkeyableなアトリビュートです。球の中心は ``sphere`` のtransformの位置で、
``sphere`` を動かすと球が付いてきます。

参考にした考え方
----------------

* `maya_expressionCollision <https://github.com/akasaki1211/maya_expressionCollision>`_ (MIT):
  エクスプレッションだけで球・カプセルなどのコライダーを作り、中心からの向きへ半径まで押し戻す。こちらはエクスプレッションを使わず、同じ考え方をDGノードで組みました。
* Lester Banks の記事「How To Incorporate Matrix Collision Into a Rig」: 行列のノードで衝突を作る(物理シミュレーションでなく、DGの計算で押し出す)という使い方。
* 柔らかく止める式は :doc:`PlaneCollision <plane_collision>` と同じ指数関数の漸近を、球の表面からの距離へ当てはめました(グラフの一部を共有しています)。

いずれもコードは流用していません。

引数
----

* ``target``: 押し出す対象のtransform。出力はこの現在のワールド行列を平行移動したものです。
* ``sphere``: 球の中心を表すtransform。scaleは半径に影響しないので、半径は ``radius`` (ワールドのcm)で与えます。
* ``radius``: 球の半径の初期値(cm、0以上)。対象の太さ(指の半径など)を足した値にしてもかまいません。
* ``softness``: 柔らかく押し出し始める距離の初期値(cm、0以上)。0なら表面で硬く止めます。

計算式
------

``c`` を ``sphere`` の位置、 ``p`` を ``target`` の位置、 ``s`` を ``softness`` とします。

1. 向き ``u = (p - c) / |p - c|`` (中心から1e-6cm以下なら ``push = 0``)、距離 ``d = |p - c| - radius`` (出力の ``distance``)。
2. 押し出した後の距離 ``d'`` は :meth:`PlaneCollision.response <mlrig.setups.PlaneCollision.response>` と同じです。

   * ``d >= s`` なら ``d' = d`` (帯の外は入力のまま)。
   * ``d < s`` なら ``d' = s * exp((d - s) / s)`` 。 ``d = s`` で値と傾き(1)が連続し、 ``d`` を下げても ``d'`` は正のまま0へ漸近します。
   * ``s = 0`` なら ``d' = max(d, 0)`` (硬い押し出し)。

3. ``push = d' - d`` (0以上、出力の ``push``)、 ``matrix = target.worldMatrix · T(u * push)`` 。回転とscaleは入力のままです。
4. ``penetration = max(-d, 0)`` (入力が球の中へ入った深さ、cm)。

生成時に対象が表面から ``softness`` 以上離れていれば ``push = 0`` なので、出力は入力と一致し、作成時に姿勢が跳ねません。
:meth:`SphereCollision.pushedPosition` は同じ式をPythonで計算します(検証・配置の確認用)。

出力
----

* ``matrix``: 押し出した後のワールド行列。
* ``distance``: 球の表面からの符号付き距離(cm、確認用)。
* ``push``: 中心からの向きへ押し出した量(cm)。
* ``penetration``: 入力が球の中へ入った深さ(cm、0以上)。補正シェイプ・ ``remapValue`` などの駆動に使えます。

制限
----

* 対象が球の中心と一致する(中心から1e-6cm以下)と向きが決まらないため、 ``push = 0`` として押し出しません。中心を通り抜ける入力では、通り抜けた側へ出力が飛びます。
* 球1つだけです。カプセル(線分)は :doc:`CapsuleCollision <capsule_collision>` を使います。複数のコライダーの合成、メッシュとの衝突には対応しません。
* 押し出すのは位置だけで、表面に沿わせる回転や摩擦はありません。入力を球の中で動かすと、出力は表面の上を滑ります。
* 出力はワールド行列です。原点以外の親の下へ ``matrix`` を接続すると二重変換になります。
* ``plusMinusAverage`` ・ ``multiplyDivide`` は単精度なので、出力の位置には1e-6cm程度の丸めがあります。

テスト
------

``mlrig/__tests__/test_setup_sphere_collision.py`` (``setups`` スイート)で、移動・回転・拡大した球と回転した対象を作り、
いろいろな向きで帯の外・帯の中・球の中・中心の近くまで入れた場合に、出力の行列・ ``distance`` ・ ``push`` ・ ``penetration`` が
OpenMayaで独立に求めた式と一致すること、球の中へ入らないこと、作成直後に跳ねないこと、 ``softness = 0`` の硬い押し出しとアトリビュートの変更、
球の移動と出力の回転の保持、中心と一致した場合に押し出さないこと、Python版 :meth:`SphereCollision.pushedPosition` との一致、
containerの所有とUndo/Redo、引数の検査を確認します。Maya 2027で確認しています。

検証動画
--------

``tools/demo_sphere_collision.py`` は、新規シーンに球のコライダー(灰色)と、入力(赤・半透明)・出力(緑)の小さな球を正面から見る構図で作り、
式と毎フレームの入力の距離・ ``softness`` ・ ``distance`` ・ ``push`` ・ ``penetration`` ・出力の表面からの距離をHUDに表示して録画します。
帯への進入→球の中→中心の近くまで深く入れる→球の中で回り込ませる→ ``softness`` を0(硬い押し出し)→2.5→元の位置への復帰を記録し、
各フレームで出力の位置が式と一致し、球の中へ入らないことを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-sphere-collision.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_sphere_collision.py --launch
