曲がった軸の間で回転を等速に伝える等速ジョイント(ConstantVelocityJoint)
=============================================================================

``mlrig.setups.ConstantVelocityJoint`` は、車のドライブシャフトの車輪側などに使われるボール式の等速ジョイント
(CVジョイント、Rzeppa形)の出力軸の行列を作ります。入力軸を回すと、曲げた出力軸が入力と同じ角度だけ回ります。
:doc:`universal_joint` (十字軸継手)のような1回転のうちの速さの揺れはありません。ボールを保持するケージの行列
``cageMatrix`` (曲げ角の半分だけ傾いた等速面)と、曲げ角 ``bendAngle`` も出力します。
Maya標準ノード(``decomposeMatrix`` ・ ``pickMatrix`` ・ ``vectorProduct`` ・ ``plusMinusAverage`` ・
``angleBetween`` ・ ``composeMatrix`` ・ ``multMatrix``)だけで組み、独自プラグイン、エクスプレッション、
フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import ConstantVelocityJoint

   graph = ConstantVelocityJoint.create("driveShaft_jnt", "wheelHub_loc", name="outerCvJoint", axis="x")
   owner = graph.container
   # 出力はワールド行列。原点にある親の下の、TRSがidentityのtransformで受ける
   owner.getPlug("matrix").connectTo("stubShaft_drv.offsetParentMatrix")
   owner.getPlug("cageMatrix").connectTo("cage_drv.offsetParentMatrix")

``inputShaft`` は継手の中心に置き、 ``axis`` を軸の向きにしたtransformです。入力軸の ``axis`` まわりの回転
(``rotateX`` など)がそのまま伝わります。 ``outputTarget`` は出力軸の先の点で、位置だけを使います。

参考にした考え方
----------------

* ボール式の等速ジョイントでは、ケージがボールを両軸の角を二等分する面(等速面、homokinetic plane)に保つことで
  入力と出力の角速度が等しくなります
  (`Constant-velocity joint <https://en.wikipedia.org/wiki/Constant-velocity_joint>`_ 、
  `Rzeppa CV Joint Mechanism Explained <https://www.firgelliauto.com/blogs/mechanisms/rzeppa-cv-joint>`_)。
* 十字軸継手のMayaリグの解説
  (`How to rig a universal joint in Maya <https://techartandstuff.blogspot.com/2013/08/how-to-rig-universal-joint-in-maya.html>`_)
  は、完全な等速にはCVジョイントが必要だと述べています。

いずれもコードは流用していません。

引数
----

* ``inputShaft``: 継手の中心に置いた入力軸のtransform。
* ``outputTarget``: 出力軸の先の点を表すtransform(位置だけを使う)。
* ``axis``: 入力・出力の軸の向き(``"x"`` ・ ``"y"`` ・ ``"z"``)。
* ``atTarget``: ``True`` なら ``matrix`` の位置を ``outputTarget`` に置きます(出力軸の先端)。
  既定の ``False`` は継手の中心です。向きはどちらも同じで、 ``cageMatrix`` は常に継手の中心です。

計算式
------

``c`` を ``inputShaft`` の位置、 ``R`` をそのワールド行列の回転(scale・shear・平行移動を除く)、
``u`` を ``R`` で回した ``axis`` の向き、 ``v = normalize(outputTarget の位置 - c)`` を出力軸の向き、
``h = normalize(u + v)`` を二等分の向きとします。 ``Q(p→q)`` は ``p`` を ``q`` へ回す最短の回転
(回転軸 ``p × q`` 、 ``angleBetween`` の ``euler``)です。

1. ``matrix = R × Q(u→v)`` 、位置は ``c`` (``atTarget`` では ``outputTarget`` の位置)。 ``axis`` が ``v`` を向きます。
2. ``cageMatrix = R × Q(u→h)`` 、位置は ``c`` 。 ``axis`` が ``h`` を向き、残りの2軸がボールの並ぶ等速面を張ります。
   等速面は ``u`` と ``v`` から同じ角度(``β / 2``)だけ傾き、入力と出力はこの面に対して鏡像の関係です。
3. ``bendAngle = β`` = ``u`` と ``v`` のなす角。

行列は行ベクトルの規約なので、 ``R × Q`` は入力軸の向きを作ってからワールドで ``Q`` だけ回したものです。
入力軸を ``axis`` まわりに ``θ`` 回すと ``R`` は ``u`` まわりに ``θ`` 回り、 ``Q(u→v)`` で写した ``matrix`` は
``v`` まわりにちょうど ``θ`` 回ります。これが等速です。まっすぐ(``v = u``)なら ``matrix`` ・ ``cageMatrix`` は
入力軸と同じ向きです。

出力
----

* ``matrix``: 出力軸のワールド行列(位置は継手の中心、 ``atTarget`` では先の点、scaleは1)。
* ``cageMatrix``: ケージ(等速面)のワールド行列(位置は継手の中心、scaleは1)。ボール・ケージのモデルを付けます。
* ``bendAngle``: 入力軸と出力軸のなす角(度)。可動域の確認や、ブーツ(蛇腹のカバー)の補正シェイプのドライバーに使えます。

制限
----

* ``β = 180`` 度(折り返し)では最短の回転の軸が決まりません。実物のボール式の等速ジョイントはおよそ45度までです。
  可動域の制限はしないので、必要なら ``bendAngle`` を見て ``outputTarget`` 側で制限します。
* ボール・溝・ケージの寸法は扱わず、2本の軸が継手の中心で交わる理想的な継手です。軸方向の伸縮(プランジ)は
  向きに影響しません。プランジは :doc:`tripod_joint` で扱います。
* 出力軸の回転の累積(何回転したか)は出力しません。行列は常に今の向きです。
* 出力はワールド行列です。原点以外の親の下へ接続すると二重変換になります。

テスト
------

``mlrig/__tests__/unit/setups/test_constantVelocityJoint.py`` (``setups`` スイート)で、まっすぐなら出力・ケージが入力軸と
同じ向き・曲げ角0になること、出力軸が先の点を向き向きがOpenMayaで求めた最短の回転と一致すること、
入力を15度ずつ1周回すと出力が出力軸まわりに同じ角度だけ回ること(同じ曲げ角の :doc:`universal_joint` は
3度以上ずれること)、ケージの軸が二等分の向きを向き入力・出力から同じ角度にあること、 ``atTarget`` 、
別の軸と入力軸の親の回転・scale、containerの所有とUndo/Redo、引数の検査を確認します。Maya 2027で確認しています。

検証動画
--------

``tools/demo_constant_velocity_joint.py`` は、新規シーンに入力軸(赤)、等速ジョイントの出力軸(緑)、比較用の
十字軸継手の出力軸(青)、ケージ(黄)を作り、入力軸を一定の速さで回しながら、式と毎フレームの入力角・曲げ角・
等速ジョイントの出力角・十字軸継手の出力角・ケージの傾きをHUDに表示して録画します。
まっすぐ→曲げ角を上げる(45度)→実物の可動域を超える70度→安全な30度へ戻す→まっすぐへの復帰を記録し、
各フレームで等速ジョイントの出力角が入力角と一致し、ケージの傾きが曲げ角の半分であることを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを
``latest-constant-velocity-joint.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_constant_velocity_joint.py --launch
