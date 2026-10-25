フットロール(FootRoll)
======================

``mlrig.setups.FootRoll`` は、足のコントロールの1つの値 ``roll`` で、かかと→母指球→つま先の順に支点を移しながら
足を転がす逆足(リバースフット)を作ります。 ``bank`` で足の内側・外側の縁を支点に横へ傾け、
``swivel`` で母指球を中心に足を水平に回し、 ``toeTap`` でつま先の骨だけを上下に振ることもできます。
逆足の階層(swivel > 外縁 > 内縁 > かかと > つま先 > 母指球 > 足首、つま先の下にtoeTap)と同じ計算を、transformの階層を作らずに
Maya標準ノード(``clamp`` ・ ``composeMatrix`` ・ ``multMatrix`` など)の行列の積で行います。
独自プラグインやフレームごとのPython・Set Driven Keyは使いません。

.. code-block:: python

   from mlrig.setups import FootRoll

   graph = FootRoll.create(
       "foot_ctrl", "ankle_jnt", "ball_jnt",
       "toe_pivot", "heel_pivot", "inner_pivot", "outer_pivot",
       name="leftFoot", rollAxis="x", bankAxis="z", breakAngle=30.0,
   )
   owner = graph.container
   # 出力はワールド行列。原点にある親の下の、TRSがidentityのtransformで受ける
   owner.getPlug("ankleMatrix").connectTo("footIk_target.offsetParentMatrix")
   owner.getPlug("ballMatrix").connectTo("toe_out.offsetParentMatrix")

``foot_ctrl`` を動かすと足全体が付いて行き、 ``roll`` ・ ``bank`` ・ ``swivel`` ・ ``toeTap`` (containerのkeyableなアトリビュート)で動かします。
支点のtransformは位置だけを使い、ふつうは ``foot_ctrl`` の下に置いたlocatorにします。

参考にした考え方
----------------

ネットで広く紹介されている、逆足の階層と1つのアトリビュートで足を転がすリギングのtipsを、行列の積へ置き換えました。

* Autodesk Learn「Realtime Rigging: Reverse Foot Systems」: 1つのアトリビュートで足をかかと→母指球→つま先へ転がし、
  左右へのバンクを加える考え方。
* Highend3Dの「Character Setup for Real Time in Maya」: 足を足首・かかと・母指球・つま先の4つの支点で扱い、
  かかと→つま先→母指球→足首の順の逆足の階層でIKを動かす考え方。
* 一般的なフットロールの作り方にある、母指球からつま先へ支点が移る角度(ここでは ``breakAngle`` )で
  rollを分ける方法と、足のコントロールに付けるswivel・toe tapの補助アトリビュート。

コードは流用していません。

引数
----

* ``control``: 足のコントロール。支点の位置と、生成時の足首・母指球の行列は、このtransformの空間で固定します。
* ``ankle`` ・ ``ball``: 足首と母指球(つま先の骨の付け根)のtransform。生成時のワールド行列を基準にします。
  ``ball`` の位置はrollの母指球の支点にもなります。
* ``toe`` ・ ``heel`` ・ ``inner`` ・ ``outer``: つま先の先端・かかと・負のbankの支点・正のbankの支点。位置だけを使います。
* ``rollAxis`` ・ ``bankAxis`` ・ ``swivelAxis``: roll(toeTapも同じ軸)・bank・swivelの回転軸。
  ``control`` のローカル軸x/y/z、 ``-`` を付けると逆回り。互いに異なる軸にします。既定はx・z・y。
* ``breakAngle``: 母指球からつま先へ支点が移る角度(度、既定30)。containerのアトリビュートとして生成後も変更できます。

計算式
------

角度はすべて度です。

1. ``heelAngle = min(roll, 0)`` 、 ``ballAngle = clamp(roll, 0, breakAngle)`` 、
   ``toeAngle = max(roll - breakAngle, 0)`` 、 ``outerAngle = max(bank, 0)`` 、 ``innerAngle = min(bank, 0)`` 。
   ``swivel`` ・ ``toeTap`` は値をそのまま角度にし、どちらも母指球の位置を中心に回します。
2. 支点 ``p`` (生成時の ``control`` の空間の位置)での回転 ``P = T(-p) · R(軸, 角度) · T(p)`` 。
   度からラジアンへの変換と軸の符号は ``unitConversion`` で明示するので、UIの角度単位によりません。
3. ``ankleMatrix = A · P_ball · P_toe · P_heel · P_inner · P_outer · P_swivel · W`` 、
   ``ballMatrix = B · P_toeTap · P_toe · P_heel · P_inner · P_outer · P_swivel · W`` 。
   ``A`` ・ ``B`` は生成時の足首・母指球のワールド行列を ``control`` の空間へ移した定数、 ``W`` は ``control`` の現在のワールド行列です。

``roll = bank = swivel = toeTap = 0`` ではすべての ``P`` が単位行列なので、出力は生成時の足首・母指球と一致し、作成時に姿勢が跳ねません。
母指球の骨( ``ballMatrix`` )は母指球の支点の回転を受けないので、かかとが上がる間もつま先は地面に残ります。

出力
----

* ``ankleMatrix``: 足首のワールド行列。IKのゴールや足首のコントロールの受け側に渡します。
* ``ballMatrix``: 母指球(つま先の骨)のワールド行列。
* ``heelAngle`` ・ ``ballAngle`` ・ ``toeAngle`` ・ ``outerAngle`` ・ ``innerAngle``: 各支点の回転角(度)。
  補正のドライバーにも使えます。

制限
----

* 出力はワールド行列です。原点以外の親の下へ接続すると二重変換になります。
* swivelの中心は母指球に固定です。かかと・つま先を中心に回すswivelは含みません。
* roll・bankの値の上限は設けません。極端な値では足が地面にめり込む向きにも回ります。
* 負・非一様scaleの ``control`` は対象外です。

テスト
------

``mlrig/__tests__/test_setup_foot_roll.py`` (``setups`` スイート)で、回転・移動したコントロールについて、
rotatePivotを持つtransformで組んだ逆足の階層と、rollの各段階(かかと・breakAngle以下・超過)とbankの両向き・
その組み合わせ、swivel・toeTapとの組み合わせで出力の行列と角度が一致すること、toeTapだけでは足首が動かないこと、作成直後に出力が入力と一致すること、各段階で支点が動かないこと、
コントロールの移動と ``breakAngle`` の変更、負の軸、UIの単位がmm・radianの場合、containerの所有とUndo/Redo、
引数の検査を確認します。Maya 2025・2027で確認しています。

検証動画
--------

``tools/demo_foot_roll.py`` は、新規シーンに地面と足のコントロール・支点(灰)、生成時の足(赤・半透明)、
出力の足首と母指球の骨(緑)を斜め横から見る構図で作り、式と毎フレームの ``roll`` ・ ``bank`` と各支点の角度をHUDに表示して録画します。
かかと→母指球→breakAngle超過でつま先→戻す→内外へのbank→swivel→toeTap→基準への復帰を記録し、各フレームで角度が独立計算と一致すること、
支点の位置が動かないこと(誤差)を判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-foot-roll.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_foot_roll.py --launch
