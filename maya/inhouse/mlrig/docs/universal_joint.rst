曲がった軸の間で回転を伝えるユニバーサルジョイント(UniversalJoint)
====================================================================

``mlrig.setups.UniversalJoint`` は、ドライブシャフトやロボットの手首のように、曲がった2本の軸の間で回転を伝える
ユニバーサルジョイント(カルダン継手・十字軸継手)の出力軸の行列を作ります。入力軸を回すと、十字軸を介して
曲げた出力軸が回り、1回転のうちに出力が入力より速い区間と遅い区間ができる、実物どおりの揺れが出ます。
曲げ角 ``bendAngle`` と角速度の比 ``speedRatio`` も出力します。
Maya標準ノード(``decomposeMatrix`` ・ ``composeMatrix`` ・ ``plusMinusAverage`` ・ ``vectorProduct`` ・
``angleBetween`` ・ ``multiplyDivide`` ・ ``clamp`` ・ ``aimMatrix``)だけで組み、
独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import UniversalJoint

   graph = UniversalJoint.create("driveShaft_jnt", "rearAxle_loc", name="propShaftJoint",
                                 axis="x", pinAxis="y")
   owner = graph.container
   # 出力はワールド行列。原点にある親の下の、TRSがidentityのtransformで受ける
   owner.getPlug("matrix").connectTo("propShaft_drv.offsetParentMatrix")

``inputShaft`` は継手の中心(十字軸の中心)に置き、 ``axis`` を軸の向き、 ``pinAxis`` を入力ヨークのピンの向きにした
transformです。入力軸の ``axis`` まわりの回転(``rotateX`` など)が伝わります。 ``outputTarget`` は出力軸の先の点で、
位置だけを使います。

参考にした考え方
----------------

* 十字軸継手の角度の関係 ``tan γ1 = cos β tan γ2`` と角速度の比は、機構の解説
  (`Hooke's Angular Shaft Coupling <https://www.firgelliauto.com/blogs/mechanisms/hooke-s-angular-shaft-coupling>`_ 、
  `Universal joint の解説 <https://automotivepartswiki.blogspot.com/2022/01/universal-joint.html>`_)を参考にしました。
  2つの継手を位相を揃えて直列にすると揺れが打ち消される点もここにあります。
* Mayaでの作り方は、入力軸の子に置いた上方向のlocatorと aim constraint で出力軸を向ける方法
  (`How to rig a universal joint in Maya <https://techartandstuff.blogspot.com/2013/08/how-to-rig-universal-joint-in-maya.html>`_)
  が知られています。これは十字軸の幾何と一致するので、同じ考え方を ``aimMatrix`` の align で閉じた形にしました。

いずれもコードは流用していません。

引数
----

* ``inputShaft``: 継手の中心に置いた入力軸のtransform。
* ``outputTarget``: 出力軸の先の点を表すtransform(位置だけを使う)。
* ``axis``: 入力・出力の軸の向き(``"x"`` ・ ``"y"`` ・ ``"z"``)。
* ``pinAxis``: 入力ヨークのピンの向き。 ``axis`` と異なる軸です。出力の行列でもこの軸を、入力のピンを
  出力軸に垂直な面へ射影した向きへ揃えます。
* ``atTarget``: ``True`` なら出力の行列の位置を ``outputTarget`` に置きます(直列にしたときの中間軸の先端)。
  既定の ``False`` は継手の中心です。向きはどちらも同じです。

計算式
------

``c`` を ``inputShaft`` の位置、 ``u`` ・ ``a`` をそのワールドの ``axis`` ・ ``pinAxis`` の向き(長さ1)、
``v = normalize(outputTarget の位置 - c)`` を出力軸の向きとします。

1. 十字軸のもう一方のピン(出力ヨークのピン)は ``a`` と ``v`` の両方に垂直なので ``b = a × v`` 。
   出力軸の基準の向きは ``v × b = a - v (v・a)`` 、つまり ``a`` を ``v`` に垂直な面へ射影した向きです。
2. ``matrix`` は ``aimMatrix`` で、 ``axis`` を ``v`` へ向け、 ``pinAxis`` を ``a`` へ揃えた行列です(scaleは1)。
   残りの軸は ``b`` と平行です。まっすぐ(``v = u``)なら入力軸と同じ向きになります。
3. ``bendAngle = β`` = ``u`` と ``v`` のなす角。
4. ``pinTwist = a・(u × v)`` 。曲げ平面から測った入力ヨークの角度を ``γ1`` とすると ``sin β sin γ1`` です。
5. ``speedRatio = cos β / (cos²β + pinTwist²)`` 。 ``1 - sin²β cos²γ1 = cos²β + sin²β sin²γ1`` なので、
   教科書の ``ω2 / ω1 = cos β / (1 - sin²β cos²γ1)`` と同じです。分母には0除算を避ける下限 1e-9 を付けます。

出力ヨークの角度は ``tan γ2 = tan γ1 / cos β`` で、 ``speedRatio`` は ``γ1 = 0, 180`` 度(ピンが曲げ平面にある)で
最大の ``1 / cos β`` 、 ``γ1 = ±90`` 度で最小の ``cos β`` です。
:meth:`UniversalJoint.outputAngle` と :meth:`UniversalJoint.speedRatio` は同じ式をPythonで計算します。

二重継手(等速)
--------------

1つ目の継手を ``atTarget=True`` で作り、その ``matrix`` を中間軸の先端のtransformの ``offsetParentMatrix`` で受けます。
中間軸の両端のヨークのピンを平行にする(位相を揃える)には、2つ目の継手の ``pinAxis`` に1つ目の残りの軸
(``axis="x"`` ・ ``pinAxis="y"`` なら ``"z"``)を指定します。入力軸と出力軸が平行(Z配置)、または対称(W配置)で
2つの曲げ角が等しければ、揺れが打ち消されて出力軸は入力軸と同じ角度だけ回ります。

.. code-block:: python

   first = UniversalJoint.create("input_jnt", "middleEnd_loc", name="joint1", atTarget=True)
   first.container.getPlug("matrix").connectTo("middleEnd_drv.offsetParentMatrix")
   second = UniversalJoint.create("middleEnd_drv", "outputEnd_loc", name="joint2", pinAxis="z")

出力
----

* ``matrix``: 出力軸のワールド行列(位置は継手の中心、 ``atTarget`` では先の点)。
* ``bendAngle``: 入力軸と出力軸のなす角(度)。
* ``speedRatio``: 出力軸と入力軸の角速度の比。音・揺れ・摩耗表現のドライバーや、曲げすぎの確認に使えます。
* ``pinTwist``: ``a・(u × v)`` 。入力ヨークのピンの、曲げ平面に垂直な成分(``sin β sin γ1``)。

制限
----

* ``β = 90`` 度では ``cos β = 0`` で出力軸が止まり(ロック)、 ``a`` と ``v`` が平行になると出力のピンの向きが
  決まりません。90度を超える曲げは対象外です。実物の十字軸継手は多くが45度程度までです。
* 出力軸の回転の累積(何回転したか)は出力しません。行列は常に今の向きです。
* 十字軸・ヨークの寸法(オフセット)は扱わず、2本の軸が継手の中心で交わる理想的な継手です。
  プランジ(軸方向の伸縮)は ``outputTarget`` までの距離に関係なく向きだけで決まります。
* 等速ジョイントは :doc:`constant_velocity_joint` を使います。十字軸継手だけで等速にするには二重継手にします。
* 出力はワールド行列です。原点以外の親の下へ ``matrix`` を接続すると二重変換になります。
* ``multiplyDivide`` などは単精度なので、 ``speedRatio`` には1e-6程度の丸めがあります。

テスト
------

``mlrig/__tests__/unit/setups/test_universalJoint.py`` (``setups`` スイート)で、まっすぐなら出力が入力軸と同じ向き・
曲げ角0・比1になること、出力軸が先の点を向き出力ヨークのピンが入力ヨークのピンと出力軸の両方に垂直なこと、
出力ヨークの角度が ``tan γ2 = tan γ1 / cos β`` を満たすこと、 ``speedRatio`` が出力角の差分の比・Python版と一致し
``cos β`` から ``1 / cos β`` の範囲で揺れること、位相を揃えた二重継手で出力が入力と同じ角度だけ回ること、
``atTarget`` 、別の軸と入力軸の親の回転、Python版の端の値、containerの所有とUndo/Redo、引数の検査を確認します。
Maya 2027で確認しています。

検証動画
--------

``tools/demo_universal_joint.py`` は、新規シーンに入力軸(赤)、1つ目の継手の出力軸(青)、二重継手の出力軸(緑)を
横から見る構図で作り、入力軸に一定の速さで回る目印を付けて、式と毎フレームの入力角・曲げ角・
``speedRatio`` ・1つ目の出力角・二重継手の出力角をHUDに表示して録画します。
まっすぐ→曲げ角を上げる(45度)→ロックの手前(80度)まで曲げる→安全な30度へ戻す→まっすぐへの復帰を記録し、
各フレームで1つ目の出力角が ``tan γ2 = tan γ1 / cos β`` と一致し、二重継手の出力角が入力角と一致することを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-universal-joint.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_universal_joint.py --launch
