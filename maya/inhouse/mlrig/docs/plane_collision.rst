平面との柔らかい衝突(PlaneCollision)
======================================

``mlrig.setups.PlaneCollision`` は、コントロールなどの対象の位置が床・壁などの平面より下へ沈まないよう、
平面の法線の向きへ押し出した行列を作ります。面に近づくと ``softness`` の帯の中で少しずつ押し返し始め、
面より下へ入れても出力は面から ``radius`` の高さへ漸近します。足と床、手と机・壁の接触などに使えます。
Maya標準ノード(``vectorProduct`` ・ ``decomposeMatrix`` ・ ``plusMinusAverage`` ・ ``multiplyDivide`` ・
``condition`` ・ ``composeMatrix`` ・ ``multMatrix``)だけで組み、独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import PlaneCollision

   graph = PlaneCollision.create("foot_ctrl", "floor_ctrl", name="footFloor", axis="y",
                                 softness=1.0, radius=0.5)
   owner = graph.container
   # 出力はワールド行列。原点にある親の下の、TRSがidentityのtransformで受ける
   owner.getPlug("matrix").connectTo("foot_ik_goal.offsetParentMatrix")

``softness`` ・ ``radius`` はcontainerのkeyableなアトリビュートです。面は ``plane`` のtransformの原点を通り、
ローカルの ``axis`` を法線とする無限平面で、 ``plane`` を動かす・回すと面が付いてきます。

参考にした考え方
----------------

* Lester Banks の記事「How To Incorporate Matrix Collision Into a Rig」と「Tips for using Maya Collision Systems and Matrix Nodes Together」:
  行列のノードで、キャラクターの足と床のような要素を接触させる(物理シミュレーションでなく、DGの計算で押し出す)という使い方。
* Lester Banks の記事「Create a Soft Collision for Objects in Geometry Nodes」: 衝突を硬く止めるのでなく、近づいたところから柔らかく押し返す考え方。
* 柔らかく止める式は、mlrigの ``mlrig.setups.SoftIK`` と同じ指数関数の漸近( ``s * exp(-x/s)`` )を、平面からの距離へ当てはめました。

いずれもコードは流用していません。

引数
----

* ``target``: 押し出す対象のtransform。出力はこの現在のワールド行列を平行移動したものです。
* ``plane``: 面を表すtransform。原点を通り、ローカルの ``axis`` を法線とします。scaleは法線の正規化で無視するので、距離は常にワールドのcmです。
* ``axis``: 法線を表す ``plane`` のローカル軸(x/y/z)。正の向きが面の上(押し出す向き)です。
* ``softness``: 柔らかく押し出し始める距離の初期値(cm、0以上)。0なら面で硬く止めます。
* ``radius``: 面から浮かせる距離の初期値(cm)。対象の半径や靴底の厚みに使います。

計算式
------

``n`` を ``plane`` の法線(ワールド、正規化)、 ``o`` を ``plane`` の原点、 ``p`` を ``target`` の位置、 ``s`` を ``softness`` とします。

1. 距離 ``d = dot(p - o, n) - radius`` (出力の ``distance``)。
2. 押し出した後の距離 ``d'`` ( :meth:`PlaneCollision.response` )。

   * ``d >= s`` なら ``d' = d`` (帯の外は入力のまま)。
   * ``d < s`` なら ``d' = s * exp((d - s) / s)`` 。 ``d = s`` で値と傾き(1)が連続し、 ``d`` を下げても ``d'`` は正のまま0へ漸近します。
   * ``s = 0`` なら ``d' = max(d, 0)`` (硬い押し出し)。

3. ``push = d' - d`` (0以上、出力の ``push``)、 ``matrix = target.worldMatrix · T(n * push)`` 。回転とscaleは入力のままです。

生成時に対象が面から ``radius + softness`` 以上離れていれば ``push = 0`` なので、出力は入力と一致し、作成時に姿勢が跳ねません。

出力
----

* ``matrix``: 押し出した後のワールド行列。
* ``distance``: ``radius`` を引いた面からの符号付き距離(cm、確認用)。
* ``push``: 法線の向きへ押し出した量(cm、確認用。接地の強さとして他の値の駆動にも使えます)。

制限
----

* 面は無限平面です。床の端や凹凸(メッシュとの衝突)、複数の面には対応しません。
* 押し出すのは位置だけで、接地時に足の裏を面へ沿わせる回転は行いません(必要なら :doc:`FootRoll <foot_roll>` などと組み合わせます)。
* 面に沿った摩擦(滑り止め)や、沈めた量に応じた押し戻しの遅れはありません。入力を面の下で横へ動かすと、出力も面の上をそのまま滑ります。
* 出力はワールド行列です。原点以外の親の下へ ``matrix`` を接続すると二重変換になります。
* ``plusMinusAverage`` ・ ``multiplyDivide`` は単精度なので、出力の位置には1e-6cm程度の丸めがあります。

テスト
------

``mlrig/__tests__/test_setup_plane_collision.py`` (``setups`` スイート)で、傾けて移動・拡大した面と回転した対象を作り、
帯の外・帯の中・面の下・深く沈めた場合で出力の行列・ ``distance`` ・ ``push`` がOpenMayaで独立に求めた式と一致すること、
面より下へ沈まないこと、作成直後に跳ねないこと、式の単調性と帯の境界での連続性、 ``softness = 0`` の硬い押し出しとアトリビュートの変更、
面の移動・回転と出力の回転の保持、 ``axis = z`` 、containerの所有とUndo/Redo、引数の検査を確認します。Maya 2025・2027で確認しています。

検証動画
--------

``tools/demo_plane_collision.py`` は、新規シーンに12度傾けた床(灰色)と、入力(赤・半透明)・出力(緑)の球を正面から見る構図で作り、
式と毎フレームの入力の高さ・ ``softness`` ・ ``distance`` ・ ``push`` ・出力の高さをHUDに表示して録画します。
帯への進入→面の下→深く沈める→面の下で横へ滑らせる→ ``softness`` を0(硬い押し出し)→2.5→元の位置への復帰を記録し、
各フレームで出力の位置が式と一致し、面から ``radius`` 未満にならないことを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-plane-collision.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_plane_collision.py --launch
