楕円体との柔らかい衝突(EllipsoidCollision)
============================================

``mlrig.setups.EllipsoidCollision`` は、コントロールなどの対象の位置が、胸・頭・お腹・太ももなどを近似した楕円体の中へ
入らないよう、楕円体の中心から対象への向きへ押し出した行列を作ります。軸ごとに半径( ``radiusX`` ・ ``radiusY`` ・ ``radiusZ``)を
変えられ、軸の向きは中心のtransformの回転に付いてくるので、球やカプセルでは合わない横長・前後に薄い形を1つのコライダーで近似できます。
表面に近づくと ``softness`` の帯の中で少しずつ押し返し始め、中へ入れても出力は表面へ漸近します。
押し込んだ深さ ``penetration`` と、今の向きでの楕円体の半径 ``directionRadius`` も出力します。
Maya標準ノード(``decomposeMatrix`` ・ ``composeMatrix`` ・ ``plusMinusAverage`` ・ ``vectorProduct`` ・
``multiplyDivide`` ・ ``distanceBetween`` ・ ``condition`` ・ ``multMatrix``)だけで組み、
独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import EllipsoidCollision

   graph = EllipsoidCollision.create("L_hand_ctrl", "chest_jnt", name="handChest",
                                     radiusX=14.0, radiusY=18.0, radiusZ=10.0, softness=1.0)
   owner = graph.container
   # 出力はワールド行列。原点にある親の下の、TRSがidentityのtransformで受ける
   owner.getPlug("matrix").connectTo("L_hand_drv.offsetParentMatrix")
   # 押し込んだ深さで補正シェイプを駆動する例
   owner.getPlug("penetration").connectTo("chestPress_remap.inputValue")

``radiusX`` ・ ``radiusY`` ・ ``radiusZ`` ・ ``softness`` はcontainerのkeyableなアトリビュートです。
楕円体の中心と軸の向きは ``ellipsoid`` のtransformのワールド位置・回転で、移動・回転させると楕円体が付いてきます。

参考にした考え方
----------------

* 楕円体の局所空間で各軸を半径で割ると楕円体は単位球になり、その空間での長さ(正規化した半径)が1になる点が表面です。
  中心からの半直線で表面までの距離を求める考え方は、粒子の接触判定で使われる、点が表面に乗るまで軸を拡大する倍率と同じです
  (`Orientational Ordering in Athermally Sheared, Aspherical, Frictionless Particles <https://arxiv.org/pdf/1806.01739>`_)。
* 楕円体の局所空間へ移して問題を簡単にする考え方は、
  `Continuous Collision Detection for translating Ellipsoid <https://gamedev.net/tutorials/programming/general-and-gameplay-programming/continuous-collision-detection-for-translating-ellipsoid-r2426>`_ と同じです。
* 柔らかく止める式は :doc:`SphereCollision <sphere_collision>` ・ :doc:`PlaneCollision <plane_collision>` と同じで、
  中心からの押し出しのグラフをSphereCollisionと共有しています。

いずれもコードは流用していません。

引数
----

* ``target``: 押し出す対象のtransform。出力はこの現在のワールド行列を平行移動したものです。
* ``ellipsoid``: 楕円体の中心と軸の向きを表すtransform(胸・頭・太もものjointなど)。scale・shearは半径に影響しません。
* ``radiusX`` ・ ``radiusY`` ・ ``radiusZ``: 局所X・Y・Z軸の半径の初期値(cm、1e-4以上)。3つとも同じなら球です。
* ``softness``: 柔らかく押し出し始める距離の初期値(cm、0以上)。0なら表面で硬く止めます。

計算式
------

``c`` を ``ellipsoid`` の位置、 ``Q`` をその回転(scaleを除く)、 ``p`` を ``target`` の位置、 ``s`` を ``softness`` とします。

1. 向き ``u = (p - c) / |p - c|`` (1e-6cm以下なら ``push = 0``)。
2. 局所の向き ``l = u · Q^-1`` 、楕円体の半径 ``R = 1 / sqrt((lx / radiusX)^2 + (ly / radiusY)^2 + (lz / radiusZ)^2)``
   (出力の ``directionRadius``)。 ``c + R u`` は中心から ``u`` の向きへ伸ばした半直線と楕円体の表面の交点です。
3. 距離 ``d = |p - c| - R`` (出力の ``distance``)。
4. 押し出した後の距離 ``d'`` は :meth:`PlaneCollision.response <mlrig.setups.PlaneCollision.response>` と同じです。

   * ``d >= s`` なら ``d' = d`` (帯の外は入力のまま)。
   * ``d < s`` なら ``d' = s * exp((d - s) / s)`` 。 ``d = s`` で値と傾き(1)が連続し、 ``d`` を下げても ``d'`` は正のまま0へ漸近します。
   * ``s = 0`` なら ``d' = max(d, 0)`` (硬い押し出し)。

5. ``push = d' - d`` (0以上、出力の ``push``)、 ``matrix = target.worldMatrix · T(u * push)`` 。回転とscaleは入力のままです。
6. ``penetration = max(-d, 0)`` (入力が楕円体の中へ入った深さを、中心からの向きに測ったもの、cm)。

``u`` の向きへ動かしても ``u`` は変わらないので、出力の位置は同じ半直線上の、表面の外(硬い場合は表面上)にあります。
生成時に対象が表面から ``softness`` 以上離れていれば ``push = 0`` なので、出力は入力と一致し、作成時に姿勢が跳ねません。
3つの半径が同じなら ``R`` は一定で、 :doc:`SphereCollision <sphere_collision>` と同じ結果になります。
:meth:`EllipsoidCollision.pushedPosition` ・ :meth:`EllipsoidCollision.directionRadius` は同じ式をPythonで計算します(検証・配置の確認用)。

出力
----

* ``matrix``: 押し出した後のワールド行列。
* ``distance``: 中心からの向きに測った、表面からの符号付き距離(cm、確認用)。
* ``push``: 中心から外への向きへ押し出した量(cm)。
* ``penetration``: 入力が楕円体の中へ入った深さ(cm、0以上)。
* ``directionRadius``: 今の向きでの、中心から表面までの距離 ``R`` (cm)。どの向きから押し込まれたかの確認に使えます。

制限
----

* 押し出す向きは中心からの放射方向で、表面の法線(最近点への向き)ではありません。軸の半径の比が大きいと、
  細い向きの近くでは押し出した先が真の最近点からずれ、斜めから押し込むと表面に沿って横へ滑るように見えます。
  3つの半径が同じなら厳密(球)です。
* ``distance`` ・ ``penetration`` も放射方向に測った値で、表面までの最短距離ではありません。表面の外では最短距離以上、
  中では最短距離以上の深さになり、細い向きの近くほど差が大きくなります。 ``softness`` の帯の厚さも放射方向に測ります。
* 中心から1e-6cm以下では向きが決まらないため、 ``push = 0`` として押し出しません。中心を通り抜ける入力では、
  通り抜けた側へ出力が飛びます。
* 楕円体1つだけです。複数のコライダーの合成、メッシュとの衝突には対応しません。
* 押し出すのは位置だけで、表面に沿わせる回転や摩擦はありません。
* 出力はワールド行列です。原点以外の親の下へ ``matrix`` を接続すると二重変換になります。
* ``plusMinusAverage`` ・ ``multiplyDivide`` は単精度なので、出力の位置には1e-6cm程度の丸めがあります。

テスト
------

``mlrig/__tests__/test_setup_ellipsoid_collision.py`` (``setups`` スイート)で、回転・拡大した中心と回転した対象を作り、
軸の向き・斜めのいろいろな向きで帯の外・帯の中・中・中心の近くまで入れた場合に、出力の行列・ ``distance`` ・ ``push`` ・
``penetration`` ・ ``directionRadius`` がOpenMayaで独立に求めた式と一致すること、楕円体の中へ入らないこと、出力が同じ半直線上にあること、
作成直後に跳ねないこと、 ``softness = 0`` の硬い押し出しと半径・ ``softness`` の変更、中心の移動・回転と出力の回転の保持、
3つの半径が同じ場合にSphereCollisionと一致すること、中心と一致する場合、Python版との一致、containerの所有とUndo/Redo、
引数の検査を確認します。Maya 2027で確認しています。

検証動画
--------

``tools/demo_ellipsoid_collision.py`` は、新規シーンに少し傾けた楕円体(灰色)と、入力(赤・半透明)・出力(緑)の小さな球を正面から見る構図で作り、
式と毎フレームの入力の中心からの距離・ ``directionRadius`` ・ ``distance`` ・ ``push`` ・ ``penetration`` ・出力の正規化した半径をHUDに表示して録画します。
長い軸の側からの進入→中→中心の近くまで深く入れる→中で回り込んで短い軸の側へ移り、半径が変わっても表面に沿うこと→
``softness`` を0(硬い押し出し)→元の位置への復帰を記録し、各フレームで出力の位置が式と一致し、中へ入らないことを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-ellipsoid-collision.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_ellipsoid_collision.py --launch
