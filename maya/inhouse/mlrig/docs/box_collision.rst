箱との柔らかい衝突(BoxCollision)
================================

``mlrig.setups.BoxCollision`` は、コントロールなどの対象の位置が、腰・胸・机の天板・箱の荷物などを近似した箱(直方体)の中へ
入らないよう、表面の法線の向きへ押し出した行列を作ります。辺の長さ( ``sizeX`` ・ ``sizeY`` ・ ``sizeZ``)を軸ごとに変えられ、
角と辺は ``rounding`` の半径で丸められます。軸の向きは中心のtransformの回転に付いてきます。
:doc:`SphereCollision <sphere_collision>` ・ :doc:`EllipsoidCollision <ellipsoid_collision>` と違い、押し出す向きは中心からの放射方向ではなく、
箱の外では最近点からの向き、中では最も浅い面の向きなので、平らな面の上では対象が面に垂直に止まり、横へ滑りません。
表面に近づくと ``softness`` の帯の中で少しずつ押し返し始め、中へ入れても出力は表面へ漸近します。
押し込んだ深さ ``penetration`` と、押し出す向き ``normal`` も出力します。
Maya標準ノード(``decomposeMatrix`` ・ ``composeMatrix`` ・ ``plusMinusAverage`` ・ ``vectorProduct`` ・ ``multiplyDivide`` ・
``clamp`` ・ ``distanceBetween`` ・ ``condition`` ・ ``multMatrix``)だけで組み、独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import BoxCollision

   graph = BoxCollision.create("L_hand_ctrl", "table_top", name="handTable",
                               sizeX=120.0, sizeY=4.0, sizeZ=60.0, rounding=1.0, softness=1.0)
   owner = graph.container
   # 出力はワールド行列。原点にある親の下の、TRSがidentityのtransformで受ける
   owner.getPlug("matrix").connectTo("L_hand_drv.offsetParentMatrix")
   # 押し込んだ深さで補正シェイプを駆動する例
   owner.getPlug("penetration").connectTo("palmPress_remap.inputValue")

``sizeX`` ・ ``sizeY`` ・ ``sizeZ`` ・ ``rounding`` ・ ``softness`` はcontainerのkeyableなアトリビュートです。
箱の中心と軸の向きは ``box`` のtransformのワールド位置・回転で、移動・回転させると箱が付いてきます。

参考にした考え方
----------------

* 箱の符号付き距離 ``|max(q, 0)| + min(max(qx, qy, qz), 0)`` ( ``q = |l| - e``)と、内側の箱を小さくしてから半径を引く角の丸め方は、
  `Inigo Quilez: distance functions <https://iquilezles.org/articles/distfunctions/>`_ の箱・角を丸めた箱と同じ考え方です。
* 外の点の最近点を各軸の範囲へのclampで求める考え方は、向きのある箱(OBB)への最近点の求め方として一般的なものです
  (例: `BB.Collision.Primitives <https://bb.hexdocs.pm/BB.Collision.Primitives.md>`_ の点とOBBの最近点)。
* 柔らかく止める式は :doc:`PlaneCollision <plane_collision>` と同じで、押し出し量のグラフを共有しています。
  逆回転をクォータニオンの共役で作る方法は :doc:`EllipsoidCollision <ellipsoid_collision>` と同じです。

いずれもコードは流用していません。

引数
----

* ``target``: 押し出す対象のtransform。出力はこの現在のワールド行列を平行移動したものです。
* ``box``: 箱の中心と軸の向きを表すtransform。scale・shearは大きさに影響しません。
* ``sizeX`` ・ ``sizeY`` ・ ``sizeZ``: 局所X・Y・Z軸の辺の長さの初期値(cm、1e-4以上)。丸めを含めた外形の長さです。
* ``rounding``: 角と辺の丸めの半径の初期値(cm、0以上)。辺の長さの半分を超えた軸は平らな部分が無くなり、
  3軸とも超えると半径 ``rounding`` の球になります。
* ``softness``: 柔らかく押し出し始める距離の初期値(cm、0以上)。0なら表面で硬く止めます。

計算式
------

``c`` を ``box`` の位置、 ``Q`` をその回転(scaleを除く)、 ``p`` を ``target`` の位置、 ``r`` を ``rounding`` 、 ``s`` を ``softness`` とします。

1. 局所の位置 ``l = (p - c) · Q^-1`` 、内側の箱の半分の長さ ``e = clamp(size / 2 - r, 0, size / 2)`` (軸ごと)。
2. 最近点 ``k = clamp(l, -e, e)`` 、外へ出た分 ``o = l - k`` 。
3. 外( ``|o| > 1e-6cm``): ``d = |o| - r`` 、局所の法線 ``n = o / |o|`` 。面の外では面の法線、辺・角の外では辺・角からの向きです。
4. 中: ``q = |l| - e`` の最大の成分の軸 ``i`` (同じ値なら X、Y、Z の順)で ``d = q_i - r`` 、 ``n = sign(l_i) * 軸i`` ( ``l_i = 0`` なら+側)。
5. ``d`` は出力の ``distance`` 、ワールドの法線 ``N = n · Q`` は出力の ``normal`` です。
6. 押し出した後の距離 ``d'`` は :meth:`PlaneCollision.response <mlrig.setups.PlaneCollision.response>` と同じです。

   * ``d >= s`` なら ``d' = d`` (帯の外は入力のまま)。
   * ``d < s`` なら ``d' = s * exp((d - s) / s)`` 。 ``d = s`` で値と傾き(1)が連続し、 ``d`` を下げても ``d'`` は正のまま0へ漸近します。
   * ``s = 0`` なら ``d' = max(d, 0)`` (硬い押し出し)。

7. ``push = d' - d`` (0以上、出力の ``push``)、 ``matrix = target.worldMatrix · T(N * push)`` 。回転とscaleは入力のままです。
8. ``penetration = max(-d, 0)`` (入力が箱の中へ入った、最も浅い面からの深さ、cm)。

外では ``d`` は表面までの最短距離で、 ``N`` の向きへ動かしても最近点は変わらないので、出力は最近点からの同じ直線上にあります。
中では最も浅い面へ垂直に押し出すので、出力はその面の外(硬い場合は面上)にあります。
生成時に対象が表面から ``softness`` 以上離れていれば ``push = 0`` なので、出力は入力と一致し、作成時に姿勢が跳ねません。
立方体で ``rounding`` が辺の長さの半分以上なら、中心以外では同じ半径の :doc:`SphereCollision <sphere_collision>` と同じ結果になります。
:meth:`BoxCollision.pushedPosition` ・ :meth:`BoxCollision.signedDistance` は同じ式をPythonで計算します(検証・配置の確認用)。

出力
----

* ``matrix``: 押し出した後のワールド行列。
* ``distance``: 表面からの符号付き距離(cm、中は負)。
* ``push``: ``normal`` の向きへ押し出した量(cm)。
* ``penetration``: 入力が箱の中へ入った深さ(cm、0以上)。
* ``normal``: 押し出す向き(ワールド、単位ベクトル)。どの面から押し込まれたかの確認や、面ごとの補正シェイプの切り替えに使えます。

制限
----

* 中の法線は最も浅い面で決まります。中心と辺を結ぶ面(どちらの面にも同じ深さの点の集まり)をまたぐと押し出す面が切り替わり、
  深く押し込んだ入力では出力が別の面へ跳びます。浅い押し込みでは跳びは小さく、 ``softness`` の帯の外では起きません。
* 中心では X、Y、Z の順に優先した、最も浅い面の+側へ押し出します。中心を通り抜ける入力では、通り抜けた側へ出力が飛びます。
* ``rounding = 0`` の角・辺の外では、法線が角からの向きへ連続に回りますが、面の外との境目で曲がり方(2階微分)は不連続です。
  ``rounding`` を少し付けると、中に入った場合を除き表面がなめらかになります。
* 箱1つだけです。複数のコライダーの合成、メッシュとの衝突には対応しません。
* 押し出すのは位置だけで、表面に沿わせる回転や摩擦はありません。
* 出力はワールド行列です。原点以外の親の下へ ``matrix`` を接続すると二重変換になります。
* ``plusMinusAverage`` ・ ``multiplyDivide`` ・ ``clamp`` は単精度なので、出力の位置には1e-6cm程度の丸めがあります。

テスト
------

``mlrig/__tests__/test_setup_box_collision.py`` (``setups`` スイート)で、回転・拡大した中心と回転した対象を作り、
面・辺・角の外、帯の中、面の中へ置いた場合に、出力の行列・ ``distance`` ・ ``push`` ・ ``penetration`` ・ ``normal`` が
OpenMayaで独立に求めた式と一致すること、箱の中へ入らないこと、作成直後に跳ねないこと、丸めと ``softness = 0`` の硬い押し出し、
辺の長さの変更、中心の移動・回転と出力の回転の保持、丸めきった立方体がSphereCollisionと一致すること、中心での向き、
Python版との一致、containerの所有とUndo/Redo、引数の検査を確認します。Maya 2027で確認しています。

検証動画
--------

``tools/demo_box_collision.py`` は、新規シーンに少し傾けた角の丸い箱(灰色)と、入力(赤・半透明)・出力(緑)の小さな球を正面から見る構図で作り、
式と毎フレームの入力の局所の位置・ ``distance`` ・ ``push`` ・ ``penetration`` ・ ``normal`` ・出力の表面からの距離をHUDに表示して録画します。
上の面への進入→深く押し込む→面の上を横へ動かし、縁から角を回り込んで側面へ→ ``softness`` を0(硬い押し出し)→元の位置への復帰を記録し、
各フレームで出力の位置が式と一致し、箱の中へ入らないことを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-box-collision.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_box_collision.py --launch
