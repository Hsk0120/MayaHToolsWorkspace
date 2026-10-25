足の面への胴体の傾き(GroundTilt)
=================================

``mlrig.setups.GroundTilt`` は、4足の動物や機械の4本の足の接地点が作る面に合わせて、胴体(腰)を傾け、上下させる行列を作ります。
凸凹な地面や坂で足をIKで接地させたとき、胴体が水平のままだと不自然に見えるのを補います。
Maya標準ノード(``plusMinusAverage`` ・ ``aimMatrix`` ・ ``pickMatrix`` ・ ``blendMatrix`` ・ ``multMatrix`` など)だけで組み、
独自プラグインやフレームごとのPython・レイキャストは使いません。

.. code-block:: python

   from mlrig.setups import GroundTilt

   graph = GroundTilt.create(
       "body_ctrl", "frontLeft_foot", "frontRight_foot", "backLeft_foot", "backRight_foot",
       name="bodyTilt", tilt=0.7, height=0.5,
   )
   owner = graph.container
   # 出力はワールド行列。原点にある親の下の、TRSがidentityのtransformで受ける
   owner.getPlug("matrix").connectTo("pelvis_driven.offsetParentMatrix")

``body_ctrl`` はアニメーターが動かす胴体の入力です。出力は ``body_ctrl`` 自身ではなく、駆動される側(腰のjointなど)へ接続します。
``tilt`` ・ ``height`` はcontainerのkeyableなアトリビュートで、作成後も変更できます。

参考にした考え方
----------------

地形に合わせて4足のキャラクターの姿勢を補正する一般的な方法のうち、次の考え方を標準ノードの計算へ置き換えました。コードは流用していません。

* 足・腰・背骨の補正のうち、腰(胴体)は4本の足の接地の結果に合わせて傾ける。足だけを接地させて胴体を水平のままにすると、
  坂で腰が引けたような姿勢に見える。
* 補正は元のアニメーションの姿勢を保つことを優先し、どれだけ補正を加えるかを割合( ``tilt`` ・ ``height`` )で調整できるようにする。
  傾きと高さの調整は互いに影響するので、別々の値にする。

引数
----

* ``body``: 胴体の入力のtransform。現在のワールド行列を、その位置を中心に回して出力します。
* ``frontLeft`` ・ ``frontRight`` ・ ``backLeft`` ・ ``backRight``: 4本の足の接地点のtransform。位置だけを使います。
  ふつうは足のIKのゴールや、接地点のlocatorにします。
* ``tilt``: 足の面の回転を胴体へ加える割合(0〜1、既定1)。
* ``height``: 4本の足の平均の高さの変化を胴体へ加える割合(既定1)。

計算式
------

1. 前 ``F`` ・後 ``B`` ・左 ``L`` ・右 ``R`` は、それぞれ2本の足の位置の平均、中心 ``C`` は4本の平均(ワールド、cm)。
2. 足の面の向き ``A`` は ``aimMatrix`` で求めます。位置 ``C`` で +X を ``F`` へ向け、+Z をできるだけ ``L`` の方向へ揃えた回転です。
3. ``D = A0^-1 · A`` ( ``A0`` は生成時の ``A`` 。Mayaの行ベクトルの規約でワールドの回転差)、
   ``Dt = slerp(単位行列, D, tilt)`` ( ``blendMatrix`` )。
4. ``lift = height * (C.y - C0.y)`` 。
5. ``matrix = Body · T(-b) · Dt · T(b) · T(0, lift, 0)`` 。 ``Body`` は胴体の現在のワールド行列、 ``b`` はその位置です。

生成時は ``D`` が単位行列、 ``lift = 0`` なので、出力は胴体の入力と一致し、作成時に姿勢が跳ねません。
4本の足が平らなまま一緒に上下・水平移動しても ``A`` は変わらないので、回転せず ``lift`` だけが変わります。

出力
----

* ``matrix``: 補正後の胴体のワールド行列。
* ``pitch`` ・ ``roll``: 生成時の前後の向き・左右の向きを ``D`` で回したときの、水平面からの角度の変化(度)。
  確認や他の補正(背骨・首の打ち消しなど)のドライバーに使えます。 ``tilt`` は掛かりません。
* ``lift``: 胴体を上下させた量(cm)。

制限
----

* 出力はワールド行列です。原点以外の親の下へ接続すると二重変換になります。
* 前後の中点・左右の中点から面を求めるので、足の配置は4足の長方形に近い前提です。前後と左右の向きが平行に近い配置は拒否します。
* 上下はワールドY方向だけです。坂に沿った前後の移動や、腰が足から離れすぎないための制限は含みません。
* 地面の形を調べる処理(レイキャスト)は含みません。足の接地は別のIKや配置で行います。

テスト
------

``mlrig/__tests__/test_setup_ground_tilt.py`` (``setups`` スイート)で、回転した親の下の胴体と4本の足について、
OpenMayaで独立に求めた足の面の向き・slerp・行列と、出力と結果のtransformのワールド行列・ ``lift`` ・ ``pitch`` ・ ``roll`` が一致すること
(前足・左足の持ち上げ、凸凹な地面、足の水平移動、 ``tilt`` ・ ``height`` の割合、胴体の移動と回転)、作成直後に跳ねないこと、
平らなままの移動ではliftだけ変わること、containerの所有とUndo/Redo、引数の検査を確認します。Maya 2025・2027で確認しています。

検証動画
--------

``tools/demo_ground_tilt.py`` は、新規シーンに4本の足の接地点(灰の柱)、生成時の胴体(赤・半透明)、出力の胴体(緑)を斜めから見る構図で作り、
式と毎フレームの足の高さ・ ``pitch`` ・ ``roll`` ・ ``lift`` をHUDに表示して録画します。
前足を上げる→後足を上げる→左右の傾き→凸凹→平らなまま持ち上げる→ ``tilt`` を半分にする→基準への復帰を記録し、各フレームで独立計算と一致することを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-ground-tilt.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_ground_tilt.py --launch
