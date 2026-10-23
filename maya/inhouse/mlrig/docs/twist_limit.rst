非対称なTwist可動域制限
========================

``mlrig.setups.TwistLimit`` は、jointの長手軸まわりのねじれ(Twist)を下限・上限の範囲へ制限した行列を出力します。
前腕・手首・首のように、ねじれる向きによって可動域が違う関節の補助骨や、
可動域を超えた入力を受け止める出力骨に使います。曲げ(Swing)は制限しません。
Maya標準ノードのみで構築し、独自プラグインやフレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import TwistLimit

   graph = TwistLimit.create(
       "forearm_jnt", name="forearmTwistLimit", axis="x",
       minimum=-30, maximum=70, softness=0.3,
   )
   # 入力と同じ親空間、TRSとjointOrientがidentityの出力骨へ接続する
   graph.container.getPlug("matrix").connectTo("forearmLimited_jnt.offsetParentMatrix")

曲げも制限する場合は、:doc:`swing_limit` を別の出力骨に使うか、入力側で組み合わせます。

引数
----

* ``axis``: 生成時の姿勢での骨の長手(Twist)軸。x/y/z。
* ``minimum`` / ``maximum``: Twistの下限・上限(度)。 ``-179 <= minimum < maximum <= 179`` 。
  右手系で長手軸の正の向きから見て反時計回りが正です。0(生成時の姿勢)を範囲に含めない指定もできますが、
  その場合は生成時の姿勢でも出力が入力と一致しません。
* ``softness``: 可動域の半分 ``(maximum - minimum)/2`` のうち、限界の手前から柔らかく止め始める区間の割合(0〜1)。
  0は限界で硬く止め、1は範囲の中央から緩め始めます。

``minimum`` ・ ``maximum`` ・ ``softness`` はcontainerのアトリビュートとして生成後も変更・アニメーションできます。

計算式
------

基準は生成時の姿勢です。入力jointの ``matrix * offsetParentMatrix`` を基準からの回転に直し、
:doc:`swing_twist` と同じ方法でTwistとSwingへ分け、符号付きのTwist角 ``t`` (度、-180〜180)を求めます。

1. 柔らかい区間の幅 ``w = max(softness·(max - min)/2, 0.001)`` 、上側の開始角 ``hi = max - w`` 、
   下側の開始角 ``lo = min + w`` とします。 ``w`` は可動域の半分以下なので ``lo <= hi`` です。
2. 制限後のTwist角 ``t'`` は

   * ``t > hi`` なら ``t' = hi + w·(1 - exp(-(t - hi)/w))``
   * ``t < lo`` なら ``t' = lo - w·(1 - exp(-(lo - t)/w))``
   * それ以外は ``t' = t`` (入力のまま)

   ``t'`` は ``max`` ・ ``min`` へ近づくだけで越えません。開始角で傾きが1なので、止まり始めで角度が跳びません。
   Soft IK・:doc:`swing_limit` と同じ形の式を、上下それぞれに使います。
3. ``t'`` で長手軸まわりの回転を作り直し(``composeMatrix``)、 ``Twist(t') * Swing * 基準回転`` に
   入力の現在位置を合わせて ``matrix`` に出力します。Swingは入力のままです。

出力
----

* ``matrix``: 制限後の回転と入力の現在位置。入力と同じ親空間の行列。
* ``restMatrix``: 生成時の位置と回転。
* ``limitedTwistMatrix``: 基準姿勢から見た制限後のTwist。
* ``limitedTwist``: 制限後のTwist角 ``t'`` (度)。
* ``excessTwist``: 制限で削った量 ``t - t'`` (度、符号付き)。補正シェイプ等のドライバーに使えます。
* ``swingMatrix`` ・ ``twistMatrix`` ・ ``twist`` ・ ``swingX/Y/Z`` : :doc:`swing_twist` と同じ分解結果(入力側)。

制限
----

* 入力のTwist角は -180〜180度で表すため、入力が±180度をまたぐと ``t`` の符号が反転し、
  出力が上限側から下限側へ切り替わります。多回転のねじれは扱いません。
* 曲げの向きの不定な180度付近では、Swing・Twistの分解自体が連続になりません。
* 位置は入力の現在位置をそのまま使い、scale・shearは出力しません。負・非一様scaleは対象外です。
* 別の親空間へ直接接続したり、非identityのTRSへ重ねたりすると二重変換になります。
* 標準ノードの ``multiplyDivide`` を使うため、角度の計算は単精度で、誤差は0.01度程度です。
* 実装はMaya標準ノード(``backend="standard"`` 相当)だけです。C++・Bifrost・Exprespy版はありません。

テスト
------

``mlrig/__tests__/test_setup_twist_limit.py`` (``setups`` スイート)で、非対称な硬い制限、
柔らかい区間の連続・単調・非超過、Swingの保持、jointOrient・OPM・移動を含む基準姿勢、y/z軸、
生成後のアトリビュート変更、引数の検査、生成のUndo/Redoを、OpenMayaのQuaternionで求めた期待値と比べます。

検証動画
--------

``tools/demo_twist_limit.py`` は、新規シーンに入力(赤)と制限後(緑)の骨を作り、骨の根元に
Twistを読む文字盤(+Yが0度)と、許される範囲(黄の弧と線)、柔らかい区間の開始(灰の線)を表示します。
各骨の針が文字盤上のTwist角を示します。式と毎フレームの入力値・DG出力をHUDに表示して録画します。
``minimum=-30`` ・ ``maximum=70`` ・ ``softness=0.3`` で、+側・-側それぞれのねじれ(範囲の内側→超える→保持→復帰)、
曲げたままのねじれ(Swingを保持)、基準姿勢への復帰を528フレーム・24fpsで記録します。
各フレームで、DGの ``twist`` ・ ``limitedTwist`` ・ ``excessTwist`` と出力骨の行列を独立計算と比べます。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` (``verification.mp4`` ・ ``result.json`` ・
``twist-limit.ma``)に保存し、最新のフォルダーを ``latest-twist-limit.json`` に記録します。

.. code-block:: powershell

   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' tools/demo_twist_limit.py --launch
