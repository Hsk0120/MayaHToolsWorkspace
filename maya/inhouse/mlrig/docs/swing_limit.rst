楕円コーンのSwing可動域制限
==============================

``mlrig.setups.SwingLimit`` は、jointの曲げ(Swing)を楕円のコーンの内側へ制限した行列を出力します。
肩・股関節・首のように、曲げる向きによって可動域が違う関節の補助骨や、
可動域を超えた入力を受け止める出力骨に使います。Maya標準ノードのみで構築し、
独自プラグインやフレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import SwingLimit

   graph = SwingLimit.create(
       "shoulder_jnt", name="shoulderLimit", axis="x",
       limit1=70, limit2=30, softness=0.25,
   )
   # 入力と同じ親空間、TRSとjointOrientがidentityの出力骨へ接続する
   graph.container.getPlug("matrix").connectTo("shoulderLimited_jnt.offsetParentMatrix")

引数
----

* ``axis``: 生成時の姿勢での骨の長手(Twist)軸。x/y/z。
* ``limit1`` / ``limit2``: 長手軸に直交する2軸の側へ曲げたときの限界角(度、0より大きく179以下)。
  どちらの軸かは ``SwingLimit.perpendicularAxes(axis)`` で、xなら(y, z)、yなら(z, x)、zなら(x, y)です。
  符号の正負は区別しません(+Y側と-Y側は同じlimit1)。
* ``softness``: 限界角のうち、手前から柔らかく曲げ始める区間の割合(0〜1)。
  0は限界角で硬く止め、1は0度から緩め始めます。

``limit1`` ・ ``limit2`` ・ ``softness`` はcontainerのアトリビュートとして生成後も変更・アニメーションできます。

計算式
------

基準は生成時の姿勢です。入力jointの ``matrix * offsetParentMatrix`` を基準からの回転に直し、
既存の :doc:`swing_twist` と同じ方法でTwistとSwingへ分けます。

1. 長手軸の単位ベクトル ``a`` をSwingで回した先端方向 ``v`` と、曲げ角 ``θ = angle(a, v)`` (度)を求めます。
2. ``v`` の直交2軸の成分を ``c`` ・ ``s`` 、 ``r = sqrt(c² + s²)`` として、楕円の限界角を求めます。

   ``L = l1·l2·r / sqrt((l2·c)² + (l1·s)²)``

   ``c`` の側へ曲げれば ``L = l1`` 、 ``s`` の側なら ``L = l2`` で、その間は楕円でつながります。
   曲げがほぼ0で向きが決まらないときは ``min(l1, l2)`` を使います。
3. 柔らかい区間の幅 ``w = max(softness·L, 0.001)`` 、開始角 ``start = L - w`` として、

   * ``θ <= start`` なら ``θ' = θ`` (入力のまま)
   * それ以外は ``θ' = start + w·(1 - exp(-(θ - start)/w))``

   ``θ'`` は ``L`` へ近づくだけで越えません。 ``start`` で傾きが1なので、曲げ始めの境目で角度が跳びません。
   Soft IKと同じ形の式です。
4. ``ratio = θ'/θ`` (``θ`` がほぼ0なら1)だけ、Swingを恒等回転からQuaternionで補間します(``blendMatrix``)。
   曲げる向き(Swingの回転軸)は変えず、角度だけを縮めます。
5. ``twist * 制限後のSwing * 基準回転`` に入力の現在位置を合わせて ``matrix`` に出力します。Twistは制限しません。

出力
----

* ``matrix``: 制限後の回転と入力の現在位置。入力と同じ親空間の行列。
* ``restMatrix``: 生成時の位置と回転。
* ``limitedSwingMatrix``: 基準姿勢から見た制限後のSwing。
* ``swingAngle``: 入力の曲げ角 ``θ`` (度)。
* ``limitAngle``: 今の向きの限界角 ``L`` (度)。
* ``limitedAngle``: 制限後の曲げ角 ``θ'`` (度)。
* ``excessAngle``: 制限で削った角度 ``θ - θ'`` (度、0以上)。補正シェイプなどのドライバーに使えます。
* ``ratio``: ``θ'/θ`` 。
* ``swingMatrix`` ・ ``twistMatrix`` ・ ``twist`` ・ ``swingX/Y/Z`` : :doc:`swing_twist` と同じ分解結果(入力側)。

制限
----

* 曲げの向きの不定な180度付近では、Swingの分解自体が連続になりません。限界角は179度までです。
* 楕円は曲げ角で測ったもので、+側と-側は同じ限界角です。片側だけ狭くする非対称な範囲には :doc:`asymmetric_swing_limit` を使います。
* Twistの可動域は制限しません。Twistには :doc:`twist_limit` を使います。
* 位置は入力の現在位置をそのまま使い、scale・shearは出力しません。負・非一様scaleは対象外です。
* 別の親空間へ直接接続したり、非identityのTRSへ重ねたりすると二重変換になります。
* 標準ノードの ``multiplyDivide`` を使うため、角度の計算は単精度で、誤差は0.01度程度です。
* 実装はMaya標準ノード(``backend="standard"`` 相当)だけです。C++・Bifrost・Exprespy版はありません。

テスト
------

``mlrig/__tests__/test_setup_swing_limit.py`` (``setups`` スイート)で、各軸の硬い制限、
斜め方向の楕円の限界角、柔らかい区間の単調性と非超過、Twistの保持、jointOrient・OPM・移動を含む基準姿勢、
y/z軸、生成後のアトリビュート変更、引数の検査、生成のUndo/Redoを、OpenMayaのQuaternionで求めた期待値と比べます。

検証動画
--------

``tools/demo_swing_limit.py`` は、新規シーンに入力(赤)と制限後(緑)の骨、楕円の限界角(黄)、
柔らかい区間の開始 ``L - w`` (灰)を作り、式と毎フレームの入力値・DG出力をHUDに表示して録画します。
``l1=70`` ・ ``l2=35`` ・ ``softness=0.25`` で、+Y側・+Z側への曲げ(限界の内側→超える→保持→復帰)、
曲げたまま向きを一周、曲げたままのTwist、基準姿勢への復帰を600フレーム・24fpsで記録します。
各フレームで、DGの ``swingAngle`` ・ ``limitAngle`` ・ ``limitedAngle`` と出力骨の行列を独立計算と比べます。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` (``verification.mp4`` ・ ``result.json`` ・
``swing-limit.ma``)に保存し、最新のフォルダーを ``latest-swing-limit.json`` に記録します。

.. code-block:: powershell

   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' tools/demo_swing_limit.py --launch
