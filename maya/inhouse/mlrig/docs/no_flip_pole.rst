反転しない膝のポール(NoFlipPole)
==================================

``mlrig.setups.NoFlipPole`` は、Rotate Plane IKの脚・腕のポールベクターの位置を、足(手)のコントロールの
前の向きから求めます。ワールドに固定したポールのコントロールでは、足を股関節の前後へ大きく振ったときに
膝の向きが反転(フリップ)しますが、この部品はポールを足の前の向きに付け、脚の軸に垂直な面へ射影して置くので、
足がどこへ動いても膝は足の前の向きに対して同じ角度を保ちます。 ``kneeTwist`` で脚の軸まわりに回すと、
膝のコントロールを動かすのと同じように膝の向きを変えられます。
Maya標準ノード(``pickMatrix`` ・ ``vectorProduct`` ・ ``aimMatrix`` ・ ``distanceBetween`` ・ ``multiplyDivide`` ・
``composeMatrix`` ・ ``multMatrix``)だけで組み、独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from maya import cmds
   from mlrig.setups import NoFlipPole

   graph = NoFlipPole.create("hip_jnt", "foot_ctrl", mid="knee_jnt", name="legPole",
                             forwardAxis="z", distance=40.0)
   owner = graph.container
   # 出力はワールド行列。ワールド直下(またはTRSがidentityの親の下)のlocatorで受け、ポールベクターにする
   owner.getPlug("matrix").connectTo("leg_pole_loc.offsetParentMatrix")
   cmds.poleVectorConstraint("leg_pole_loc", "leg_ikHandle")

``mid`` を渡すと、生成時の膝の向きを足の前の向きから測った角度を ``offset`` に入れ、作成直後のポールが
今の膝の曲がる面の上(膝の側)に来ます。そのためポールベクターを付けても膝が跳ねません。

参考にした考え方
----------------

* 「Advanced Rigging」の no-flip knee のチュートリアル(書籍 The Art of Rigging Volume 1 の no flip knee を元にしたもの、
  ワシントン大学 CSE459 の講義資料として公開): ポールベクターを足に付け、足のコントロールの ``knee`` ・ ``offset`` のアトリビュートを
  足し合わせてIKのtwistへ入れ、 ``knee`` を膝のコントロールのように使う考え方。
* tech-artists.org のフォーラムの話題「NoFlip Leg with Pole Vector」: no-flipの膝とポールのコントロールを両立させたい場合の悩み
  (ロケーターをポールへ向けて角度を足すと回転の一部で値が飛ぶ)。この部品はtwistの角度ではなく、ポールの位置そのものを
  脚の軸に垂直な面で回すので、角度の符号の飛びが起きません。
* Autodesk Maya ヘルプ「Pole Vector constraints」: ポールベクターはRotate Plane Solverのikハンドルだけに効き、
  付け根からポールへの向きで膝の曲がる面を決めること。

いずれもコードは流用していません。

引数
----

* ``start``: 付け根(股関節・肩)のtransform/joint。
* ``end``: 先端の位置を表すtransform(足首のIKコントロールやikHandle)。
* ``control``: 前の向きを読むtransform。省略すると ``end`` 。
* ``mid``: 中間関節(膝・肘)。指定すると作成直後のポールを今の膝の面に置きます。省略すると ``offset`` は0です。
* ``forwardAxis``: ``control`` のローカルで前を表す軸(x/y/z/-x/-y/-z)。
* ``distance``: 脚の軸からポールまでの距離(cm、0より大きい)。省略すると生成時の付け根から先端までの距離です。
* ``position``: 付け根から先端までのどの割合の高さに置くか(既定0.5で中央)。

``kneeTwist`` ・ ``offset`` (角度)、 ``distance`` (長さ)、 ``position`` はcontainerのkeyableなアトリビュートで、
現在のUI単位(度・ラジアン、cm・mmなど)で入力できます。

計算式
------

1. ``aimMatrix`` で、付け根の位置を原点に、Yを先端へ向け、Xを ``control`` の ``forwardAxis`` (ワールド)へ合わせた枠 ``A`` を作ります。
   Xは前の向きを脚の軸に垂直な面へ射影した向き、Zは ``X × Y`` です。
2. ``L`` を付け根から先端までの距離(出力の ``legLength``)、 ``θ = offset + kneeTwist`` として、

   ``matrix = T(distance, 0, 0) · R_Y(offset) · R_Y(kneeTwist) · T(0, L * position, 0) · A`` (行ベクトル規約)。

   位置は ``付け根 + 軸 * L * position + (X cosθ - Z sinθ) * distance`` (:meth:`NoFlipPole.polePosition`)で、
   脚の軸まわりに右手回りへ ``θ`` だけ回した向きです。
3. ``offset`` は生成時に ``mid`` から :meth:`NoFlipPole.restAngle` で求めます(膝の向きを脚の軸に垂直な面へ射影し、Xから測った角度)。

ポールは常に脚の軸に垂直な向きにあるので、IKの曲がる面は「脚の軸と、足の前の向きを ``θ`` 回した向き」で決まります。
足を前後へ振っても、その面は足に付いて回るだけで、ワールドの固定の点を回り込むことによる反転が起きません。

出力
----

* ``matrix``: ポールのワールド行列(位置がポールの位置、Yが脚の軸)。
* ``legLength``: 付け根から先端までの距離(cm、確認用)。

制限
----

* 足先(前の向き)が脚の延長と平行になる姿勢(つま先を脚の軸の向きへ伸ばす)では、膝の向きが決まらず急に回ります。
  生成時にこの姿勢なら ``ValueError`` にします。
* 膝の向きは足のコントロールの向きに付くので、足を回すと膝も回ります(意図した動き)。足を回さずに膝だけ別の場所へ向けたい場合は
  ``kneeTwist`` を使います。ワールドに置いたポールのコントロールと切り替える仕組みは含みません
  (:doc:`SpaceBlend <space_blend>` などで混ぜられます)。
* 生成時に膝が一直線(曲がっていない)なら ``offset`` は0になり、ポールを付けたときに脚のねじれが変わることがあります。少し曲げて作ります。
* 出力はワールド行列です。原点以外の親の下へ ``matrix`` を接続すると二重変換になります。

テスト
------

``mlrig/__tests__/test_setup_no_flip_pole.py`` (``setups`` スイート)で、少し前に曲がった脚のRP IKとY回りに回した足のコントロールに
ポールを付け、作成直後に膝が動かず、ポールが膝の面の上の膝の側・軸から ``distance`` ・高さ ``L/2`` にあること、
コントロールを動かす・回したときにOpenMayaで脚の軸まわりのクォータニオン回転として独立に求めた位置と一致すること、
足を股関節の後ろ下から前上まで振り上げても膝の向きが足の前の向きに対して同じ角度を保ち(同じ動きでワールドに固定した
ポールの脚は膝が反転することも確認)、 ``kneeTwist`` ・ ``distance`` ・ ``position`` 、 ``mid`` 無しと ``forwardAxis = -x`` 、
UI単位がmm・ラジアンの場合、containerの所有とUndo/Redo、引数の検査を確認します。Maya 2025・2027で確認しています。

検証動画
--------

``tools/demo_no_flip_pole.py`` は、新規シーンに2本の同じ脚を前後に離して並べ、左(赤)はワールドに固定したポール、右(緑)はNoFlipPoleのポールで
同じ足の動きを与えて横から録画します。足を後ろから前上へ振り上げる→足をY回りに回す→ ``kneeTwist`` を回す→元へ戻す動きで、
式と毎フレームの足の角度・ ``kneeTwist`` ・両方の膝の向き(足の前の向きとの角度)をHUDに表示し、
緑の膝の向きが足の前の向き+ ``θ`` から外れないことと、ポールの位置が式と一致することを各フレームで判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-no-flip-pole.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_no_flip_pole.py --launch
