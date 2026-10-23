非対称な楕円コーンのSwing可動域制限
====================================

``mlrig.setups.AsymmetricSwingLimit`` は、:doc:`swing_limit` の楕円コーンを、
直交2軸の+側と-側で別の限界角を持てるようにしたものです。
肩の「前へは大きく、後ろへは小さく」のように、曲げる側で可動域が違う関節に使います。
Maya標準ノードのみで構築し、独自プラグインやフレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import AsymmetricSwingLimit

   graph = AsymmetricSwingLimit.create(
       "shoulder_jnt", name="shoulderLimit", axis="x",
       limit1Positive=80, limit1Negative=30,
       limit2Positive=55, limit2Negative=20,
       softness=0.25,
   )
   # 入力と同じ親空間、TRSとjointOrientがidentityの出力骨へ接続する
   graph.container.getPlug("matrix").connectTo("shoulderLimited_jnt.offsetParentMatrix")

引数
----

* ``axis``: 生成時の姿勢での骨の長手(Twist)軸。x/y/z。
* ``limit1Positive`` / ``limit1Negative``: ``SwingLimit.perpendicularAxes(axis)[0]`` の軸の+側・-側へ
  曲げたときの限界角(度、0より大きく179以下)。xならY軸です。
* ``limit2Positive`` / ``limit2Negative``: ``perpendicularAxes(axis)[1]`` の軸の+側・-側の限界角。xならZ軸です。
* ``softness``: :doc:`swing_limit` と同じ。限界角のうち、手前から柔らかく曲げ始める区間の割合(0〜1)。

4つの限界角と ``softness`` はcontainerのアトリビュートとして生成後も変更・アニメーションできます。
+側と-側を同じ値にすると :doc:`swing_limit` と同じ結果になります。

計算式
------

曲げ角 ``θ`` 、先端方向の直交2軸の成分 ``c`` ・ ``s`` 、 ``r = sqrt(c² + s²)`` は :doc:`swing_limit` と同じです。

1. 成分の符号で、その象限の楕円の半径を選びます(成分が0のときは-側)。

   * ``a = c > 0 ? limit1Positive : limit1Negative``
   * ``b = s > 0 ? limit2Positive : limit2Negative``

2. 象限ごとの1/4の楕円で限界角を求めます。

   ``L = a·b·r / sqrt((b·c)² + (a·s)²)``

   軸の上( ``c = 0`` または ``s = 0`` )では、 ``L`` は隣り合う2つの象限で同じ値( ``b`` または ``a`` )になります。
   そのため曲げる向きを一周回しても ``L`` は跳びません(象限の境目で変化の傾きは変わります)。
   曲げがほぼ0で向きが決まらないときは、4つの限界角の最小値を使います。

3. 柔らかい区間・ ``ratio`` ・Swingの補間・Twistの保持は :doc:`swing_limit` と同じ式です。

   ``w = max(softness·L, 0.001)`` 、 ``θ' = θ`` ( ``θ <= L - w`` )、それ以外は ``(L-w) + w·(1 - exp(-(θ-(L-w))/w))``

出力
----

:doc:`swing_limit` と同じです。

* ``matrix`` ・ ``restMatrix`` ・ ``limitedSwingMatrix``
* ``swingAngle`` (``θ``)・ ``limitAngle`` (``L``)・ ``limitedAngle`` (``θ'``)・ ``ratio`` (``θ'/θ``)
* ``excessAngle``: 制限で削った角度 ``θ - θ'`` (度、0以上)。補正シェイプなどのドライバーに使えます。

Pythonの補助関数 ``AsymmetricSwingLimit.quadrantLimits()`` ・ ``asymmetricLimitAngle()`` で、
同じ限界角をMayaの外でも計算できます。

制限
----

* 象限の境目で ``L`` の傾きが変わるため、+側と-側の差が大きいと、向きを回したときに出力の動きの速さが変わります。
* 曲げの向きの不定な180度付近では、Swingの分解自体が連続になりません。限界角は179度までです。
* Twistは制限しません。Twistには :doc:`twist_limit` を使います。
* 位置は入力の現在位置をそのまま使い、scale・shearは出力しません。負・非一様scaleは対象外です。
* 標準ノードの ``multiplyDivide`` を使うため、角度の計算は単精度で、誤差は0.01度程度です。
* 実装はMaya標準ノード(``backend="standard"`` 相当)だけです。C++・Bifrost・Exprespy版はありません。

テスト
------

``mlrig/__tests__/test_setup_asymmetric_swing_limit.py`` (``setups`` スイート)で、+Y・-Y・+Z・-Zの各側の硬い制限、
向きを一周回したときの限界角の連続性、柔らかい区間の単調性と非超過、 ``excessAngle`` 、
+側と-側が同じときのSwingLimitとの一致、jointOrient・OPM・移動を含む基準姿勢、Twistの保持、y/z軸、
生成後のアトリビュート変更、引数の検査、生成のUndo/Redoを、OpenMayaのQuaternionで求めた期待値と比べます。

検証動画
--------

``tools/demo_asymmetric_swing_limit.py`` は、新規シーンに入力(赤)と制限後(緑)の骨、
象限ごとの楕円の限界角(黄)、柔らかい区間の開始 ``L - w`` (灰)を作り、
式・象限ごとに選んだ ``a`` ・ ``b`` ・毎フレームの入力値とDG出力( ``excessAngle`` を含む)をHUDに表示して録画します。
``l1+ = 80`` ・ ``l1- = 30`` ・ ``l2+ = 55`` ・ ``l2- = 20`` ・ ``softness = 0.25`` で、
+Y・-Y・+Z・-Zの各側への曲げ(限界の内側→超える→復帰)、曲げたまま向きを一周、曲げたままのTwist、
基準姿勢への復帰を744フレーム・24fpsで記録し、各フレームでDGの値と出力骨の行列を独立計算と比べます。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、
最新のフォルダーを ``latest-asymmetric-swing-limit.json`` に記録します。

.. code-block:: powershell

   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' tools/demo_asymmetric_swing_limit.py --launch
