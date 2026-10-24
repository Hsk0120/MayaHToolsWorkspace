目に追従するまぶた(EyelidFollow)
================================

``mlrig.setups.EyelidFollow`` は、目の上下(Pitch)・左右(Yaw)の回転の一部を上下のまぶたへ移し、
まばたき ``blink`` で閉じる行列を出力します。目を下に向けると上まぶたが大きく、下まぶたが少し下がる
「fleshy eye」と呼ばれる動きを、Maya標準ノードのみで構築します。独自プラグインやフレームごとのPythonは使いません。

追従の差で上まぶたが下まぶたを越えそうな入力(大きく下を見る等)でも、上下の縁の開きを0で止め、
両方を間の位置で合わせます。入力を戻すと、そのまま元の開きへ戻ります。

.. code-block:: python

   from mlrig.setups import EyelidFollow

   graph = EyelidFollow.create(
       "eye_l", "upperLid_l", "lowerLid_l", name="eyelid_l",
       pitchAxis="x", yawAxis="y", closeDirection=1,
       upperFollow=0.8, lowerFollow=0.4, yawFollow=0.1, openAngle=40, blinkHeight=0.2,
   )
   owner = graph.container
   # 入力と同じ親空間、TRSがidentityの出力transform(またはjoint)へ接続する
   owner.getPlug("upperMatrix").connectTo("upperLid_l_out.offsetParentMatrix")
   owner.getPlug("lowerMatrix").connectTo("lowerLid_l_out.offsetParentMatrix")
   # まばたき(0で開き、1で閉じる)
   owner.getPlug("blink").set(1)

入力の目と上下のまぶたは同じ親transformの子にし、まぶたの回転中心(位置)を目の中心に置きます。
まぶたの入力は、アニメーターが付けた回転(まぶたの微調整)として出力にも重なります。

引数
----

* ``eye``: 目のtransform。まぶたと同じ親を持つ。
* ``upperLid`` ・ ``lowerLid``: 上下のまぶたのtransform。
* ``pitchAxis``: 親空間でまぶたを開閉する軸(目の上下の軸)。x/y/z、既定はx。
* ``yawAxis``: 親空間での目の左右の軸。 ``pitchAxis`` と異なる軸、既定はy。
* ``closeDirection``: 上まぶたが閉じる(下がる)向きの、 ``pitchAxis`` まわりの回転の符号。1または-1。
  視線が+Z・上が+Yの場合、+X回転で視線が下を向くので1です。
* ``upperFollow`` ・ ``lowerFollow``: 上下のまぶたが目のPitchに追従する割合(0〜1)。
* ``yawFollow``: 上下のまぶたが目のYawに追従する割合(0〜1)。
* ``openAngle``: 生成時の姿勢での、上下のまぶたの縁の開き(度、0より大きく179以下)。
* ``blinkHeight``: まばたきで閉じる位置。0で下まぶたの縁、1で上まぶたの縁(0〜1)。

``upperFollow`` ・ ``lowerFollow`` ・ ``yawFollow`` ・ ``openAngle`` ・ ``blinkHeight`` と ``blink`` (既定0)は
containerのアトリビュートとして、生成後も変更・アニメーションできます。

計算式
------

基準は生成時の姿勢です。目の ``matrix * offsetParentMatrix`` の回転 ``L`` と、生成時の回転 ``E0`` から、
親空間での差分 ``D = E0⁻¹ · L`` (行ベクトル規約)を求め、Pitchを先・Yawを後に回すEuler角
(例: ``pitchAxis=x`` ・ ``yawAxis=y`` なら回転順序xyz)へ分解します(``eyePitch`` ・ ``eyeYaw``、度)。
視線まわりのRollは使いません。

角度は「閉じる向き」を正とする座標で計算します。上まぶたの縁は基準で0度、下まぶたの縁は ``openAngle`` 度です。

1. ``e = closeDirection · eyePitch``
2. 追従後の縁: ``u = upperFollow · e`` 、 ``l = openAngle + lowerFollow · e``
3. 合う位置: ``meet = l - blinkHeight · (l - u)`` 、開き: ``g = max(l - u, 0)``
4. 上の縁 ``U = meet - (1 - blink)·(1 - blinkHeight)·g`` 、下の縁 ``W = meet + (1 - blink)·blinkHeight·g``
5. ``upperAngle = closeDirection · U`` 、 ``lowerAngle = closeDirection · (W - openAngle)`` 、
   ``lidYaw = yawFollow · eyeYaw`` 、 ``gap = W - U``

``l ≥ u`` (交差しない入力)で ``blink=0`` のとき ``U = u`` 、 ``W = l`` となり、追従そのものです。
``blink=1`` では ``U = W = meet`` で閉じます。 ``l < u`` では ``g = 0`` なので、 ``blink`` によらず ``U = W = meet`` で止まります。

各まぶたの出力行列は、まぶたの現在の回転に、親空間のPitch(``upperAngle`` / ``lowerAngle``)とYaw(``lidYaw``)を
目と同じ回転順序で重ね、まぶたの現在位置を合わせたものです。生成直後は角度が0なので、出力は入力と一致し、姿勢は跳ねません。

出力
----

* ``upperMatrix`` ・ ``lowerMatrix``: 上下のまぶたの、入力と同じ親空間の行列。
* ``eyePitch`` ・ ``eyeYaw``: 目の基準からのPitch・Yaw(度)。
* ``upperAngle`` ・ ``lowerAngle``: 各まぶたに足したPitch(度、 ``pitchAxis`` まわりの右手系)。
* ``lidYaw``: 上下のまぶたに足したYaw(度)。
* ``gap``: 閉じる向きで測った上下の縁の開き(度、0以上)。

角度の出力は、UIの角度単位(degree/radian)によらず常に度です。

制限
----

* まぶたは目の中心まわりの回転だけで、まぶたの形の変形(縁の沿い・眼球表面への密着)は行いません。
  変形が必要な場合は、出力の角度をドライバーとして補正シェイプやワイヤーと組み合わせてください。
* ``gap`` による交差防止は上下の縁の角度についてだけで、メッシュ同士の接触判定ではありません。
* Yawが±90度に近い姿勢ではEuler分解が不定になります。目の可動域(おおむね±50度以内)を想定しています。
* 目・まぶたの負・非一様scaleは対象外で、出力はscale・shearを持ちません。
* 別の親空間へ直接接続したり、非identityのTRSへ重ねたりすると二重変換になります。

テスト
------

``mlrig/__tests__/test_setup_eyelid_follow.py`` (``setups`` スイート)で、生成直後に出力が入力と一致すること、
上下・左右を見たときの角度と出力行列、目に基準回転(jointOrient)がある場合、 ``blink`` で閉じて ``blinkHeight`` の位置で合うこと、
追従の差で交差する入力で開きが0に止まり戻すと復帰すること、 ``closeDirection=-1`` と別の軸の指定、
生成後のアトリビュート変更、UIの角度単位がradianの場合、引数の検査、生成のUndoを、OpenMayaで求めた期待値と比べます。
Maya 2025・2027で確認しています。

検証動画
--------

``tools/demo_eyelid_follow.py`` は、新規シーンに眼球(白・黒目)、視線(黄)、セットアップなしの入力のまぶたの縁(赤)、
出力のまぶた(緑の球殻と縁)を作り、式と毎フレームの入力値・DG出力をHUDに表示して録画します。
``upperFollow=0.8`` ・ ``lowerFollow=0.2`` ・ ``yawFollow=0.15`` ・ ``openAngle=30`` ・ ``blinkHeight=0.2`` で、
下を見る・上を見る・左右を見る・まばたき・下を見たままのまばたき・交差する入力(下へ70度)での保持・基準への復帰を、
474フレーム・24fpsで記録します。各フレームで、DGの角度が式と一致すること、 ``gap`` が0以上であること、
出力のまぶたのワールド回転が期待値と一致することを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` (``verification.mp4`` ・ ``result.json`` ・
``eyelid-follow.ma``)に保存し、最新のフォルダーを ``latest-eyelid-follow.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_eyelid_follow.py --launch
