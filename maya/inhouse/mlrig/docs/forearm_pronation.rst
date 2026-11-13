尺骨の周りを回る橈骨(ForearmPronation)
=========================================

``mlrig.setups.ForearmPronation`` は、前腕の回内・回外(手のひらを返す動き)で、橈骨を尺骨の周りに回す行列を
作ります。手の回転を尺骨から見た相対回転にして回転軸まわりのTwistだけを取り出し、回内側・回外側で別々の可動域へ
柔らかく止めます。橈骨は長さを変えずに軸の周りを回ります。Maya標準ノード(``decomposeMatrix`` ・ ``pickMatrix`` ・
``composeMatrix`` ・ ``multMatrix`` ・ ``multiplyDivide`` ・ ``plusMinusAverage`` ・ ``condition`` ・ ``angleBetween`` ・
``unitConversion`` ・ ``distanceBetween``)だけで組み、独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import ForearmPronation

   setup = ForearmPronation.create("elbow_jnt", "ulnarHead_loc", "radius_jnt", "radiusTip_loc", "hand_ctrl",
                                   name="L_forearmPronation")
   owner = setup.container
   # 出力はワールド行列。原点にある親の下の、TRSがidentityのtransformで受ける
   owner.getPlug("matrix").connectTo("radius_drv.offsetParentMatrix")
   owner.getPlug("tipMatrix").connectTo("radiusTip_drv.offsetParentMatrix")
   # 回内・回外の補正シェイプのドライバー(0〜1)
   owner.getPlug("pronationWeight").connectTo("corrective.pronate")

``ulna`` (肘)と ``hand`` は毎フレーム読み、 ``ulnaTip`` ・ ``radius`` ・ ``radiusTip`` は生成時の位置だけを使います。
そのため ``radius`` 自体をこの出力で動かしても循環しません。 ``hand`` を出力の橈骨の子にすると循環します。

参考にした考え方
----------------

* 回内・回外の軸は橈骨の頭の中心と尺骨の頭の中心を通り、尺骨はほとんど動かず橈骨が尺骨の周りを回ります。
  モーションキャプチャの研究でも、軸は上腕骨小頭の中心付近と尺骨の頭の中心を通るとされています
  (`Pronation-supination axis study <https://www.orthobullets.com/Evidence/17923306>`_)。
* 正常な可動域の目安は回外85度・回内80度です(資料により幅があります)。
* リグの一般的な作り方として、尺骨と橈骨の両方を肘の下に置き、手首のTwistで橈骨を回す例があります
  (`KineFX Ulna <https://www.sidefx.com/docs/houdini/character/kinefx/rig_components/ulna.html>`_)。

いずれもコードは流用していません。

引数
----

* ``ulna``: 尺骨(肘)のtransform。橈骨の親の空間です。
* ``ulnaTip``: 尺骨の頭の中心のtransform。
* ``radius``: 橈骨の頭の中心のtransform(出力の ``matrix`` は生成時のこの行列から回ります)。
* ``radiusTip``: 橈骨の手首側の端のtransform。
* ``hand``: 手のtransform。
* ``pronationLimit`` ・ ``supinationLimit``: 回内側・回外側の可動域(度、1〜179)。既定は80度・85度。
* ``softness``: 可動域の半分に対する柔らかい区間の割合(0で硬い制限)。既定は0.1。
* ``weight``: 手のTwistを橈骨へ伝える割合(0〜1)。既定は1。
* ``sign``: 軸(橈骨の頭→尺骨の頭)まわりの正の回転を回内とするなら ``1`` 、回外とするなら ``-1`` 。左右の腕で
  回内の向きが逆になるときに使います。回す向きは変わらず、 ``pronation`` の符号と可動域の割り当てが変わります。

container の ``pronationLimit`` ・ ``supinationLimit`` ・ ``softness`` ・ ``weight`` ・ ``sign`` は後から変更できます。

計算式
------

基準は生成時の姿勢です。尺骨の空間で ``P`` を橈骨の頭、 ``U`` を尺骨の頭、 ``a = normalize(U - P)`` 、 ``F`` を
原点 ``P`` ・X軸 ``a`` の直交フレーム、 ``Mh`` ・ ``Mu`` を手・尺骨のワールド行列の回転、 ``0`` の添字を生成時の値とします(行ベクトル規約)。

1. ``Δ = F (Mh0 Mu0⁻¹)⁻¹ (Mh Mu⁻¹) F⁻¹`` 。尺骨から見た手の回転の生成時からの差を、軸がXのフレームで表したものです。
2. ``Δ`` のクォータニオンの ``(x, w)`` から ``handTwist = atan2(2wx, w² - x²)`` (度、-180〜180)。軸に垂直なSwing(手首の曲げ)は含まれません。
3. ``rawPronation = sign × handTwist × weight`` 。
4. ``w = max(softness × (pronationLimit + supinationLimit) / 2, 0.001)`` 、 ``hi = pronationLimit - w`` 、
   ``lo = -supinationLimit + w`` として :doc:`twist_limit` と同じ指数関数で制限します。
   ``raw > hi`` なら ``hi + w(1 - exp(-(raw - hi) / w))`` 、 ``raw < lo`` なら ``lo - w(1 - exp(-(lo - raw) / w))`` 、それ以外は ``raw`` 。これが ``pronation`` です。
5. ``excessPronation = rawPronation - pronation`` 、 ``pronationWeight = max(pronation / pronationLimit, 0)`` 、
   ``supinationWeight = max(-pronation / supinationLimit, 0)`` 。
6. ``matrix = R0 × F⁻¹ × Rx(sign × pronation) × F × 尺骨のワールド行列`` ( ``R0`` は生成時の橈骨の尺骨空間の行列)。
   ``tipMatrix`` は同じ向きで ``radiusTip`` の位置です。
7. ``interosseousDistance`` は尺骨の空間で、橈骨の中点 ``(P + D) / 2`` と尺骨の中点 ``U / 2`` の距離(cm)です。 ``D`` は回した後の橈骨の先、尺骨の始点は ``ulna`` の原点です。

出力
----

* ``matrix``: 橈骨のワールド行列。
* ``tipMatrix``: 橈骨の先の位置にある同じ向きのワールド行列。
* ``handTwist``: 尺骨から見た手の軸まわりのTwist(度)。
* ``rawPronation``: 制限前の回内の角度(度)。回内が正、回外が負。
* ``pronation``: 制限後の回内の角度(度)。
* ``excessPronation``: 可動域を超えた量(度)。
* ``pronationWeight`` ・ ``supinationWeight``: 可動域に対する割合(0〜1)。補正シェイプのドライバーに使えます。
* ``interosseousDistance``: 橈骨と尺骨の中点の距離(cm)。前腕の幅や筋肉の補正に使えます。

角度は常に度、長さはcmです。UIの単位によりません。

制限
----

* ``handTwist`` は-180〜180度で、±180度をまたぐと符号が反転します。
* 軸は生成時に尺骨の空間で固定し、肘の曲げや負荷で軸が動く効果は扱いません。
* 手の位置を橈骨の先へ追従させる処理はしません。手は入力のまま動きます。
* 手が ``ulna`` の子でなくても尺骨からの相対回転で測ります。肘の曲げだけで手が尺骨と一緒に動かないリグでは、その分がSwingまたはTwistとして読まれます。
* 出力はワールド行列です。原点以外の親の下へ接続すると二重変換になります。

テスト
------

``mlrig/__tests__/unit/setups/test_forearmPronation.py`` (``setups`` スイート)で、生成時の姿勢、軸まわりの回転とOpenMayaの
結果の一致(位置・向き・橈骨の長さ)、Swingの無視、柔らかい制限と硬い制限、 ``sign`` と ``weight`` 、尺骨の移動、生成時の入力を
一度だけ読むこと、 ``interosseousDistance`` 、親の回転・scale、UIの単位(rad・mm・m)、containerの所有とUndo/Redo、
引数の検査を確認します。Maya 2027で確認しています。

検証動画
--------

``tools/demo_forearm_pronation.py`` は、新規シーンに尺骨(灰)、回転軸(白)、可動域ありの橈骨(緑)、可動域なしの橈骨(赤)、
手(黄)を作り、手のTwistを範囲内・可動域超え・範囲内へ戻す順に動かし、手首のSwingと肘の曲げも加えて録画します。式と毎フレームの
入力・ ``handTwist`` ・ ``pronation`` ・ ``excessPronation`` ・重み・ ``interosseousDistance`` をHUDに表示し、各フレームで式と一致することを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを
``latest-forearm-pronation.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_forearm_pronation.py --launch
