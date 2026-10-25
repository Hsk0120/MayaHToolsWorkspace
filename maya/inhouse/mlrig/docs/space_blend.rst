複数の空間への重み付き追従(SpaceBlend)
==========================================

``mlrig.setups.SpaceBlend`` は、コントロールなどを world・胴・頭・手のような複数の参照空間へ、
空間ごとの重みの割合で同時に追従させる行列を作ります。重みは合計で割って使うので、
例えば world と手を1ずつにすると両方の動きの半分ずつに付いていきます。
生成時の姿勢を保つ(offsetを持つ)ので、どの重みにしても作成時に跳ねません。
Maya標準ノード(``multMatrix`` ・ ``plusMinusAverage`` ・ ``condition`` ・ ``multiplyDivide`` ・ ``blendMatrix``)だけで組み、
コンストレイント、独自プラグイン、フレームごとのPythonは使いません。

1つの空間だけを選ぶ切り替え(重みの補間なし、切り替え時に姿勢を保つ)は ``mlrig.setups.SpaceSwitch`` を使います。
SpaceBlendは、複数の空間の間を連続的に混ぜたい場合(持ち物を両手の間で受け渡す、首を胴と頭の中間に追従させるなど)に使います。

.. code-block:: python

   from mlrig.setups import SpaceBlend

   graph = SpaceBlend.create("prop_ctrl_space", ["world_space", "hand_L_space", "hand_R_space"],
                             name="propBlend", weights=(1.0, 0.0, 0.0))
   owner = graph.container
   # 出力はワールド行列。原点にある親の下の、TRSがidentityのtransformで受ける
   owner.getPlug("matrix").connectTo("prop_ctrl_offset.offsetParentMatrix")
   owner.getPlug("weight1").set(1.0)   # worldと左手に半分ずつ

``weight0`` 〜 ``weight<n-1>`` はcontainerのkeyableなアトリビュート(0以上)で、空間の順に並びます。

参考にした考え方
----------------

* ``maya/external/cmt`` の ``scripts/cmt/rig/spaceswitch.py`` (MIT): コンストレイントを使わず、 ``blendMatrix`` の各targetへ
  空間ごとの「offset · 空間のworldMatrix」を接続し、targetのweightで空間を切り替えて ``offsetParentMatrix`` へ出力する方法。
* maya-pulse のドキュメント「Spaces」: 空間ごとに追従する側からのoffsetを保存し、選んだ空間の行列と掛けて ``offsetParentMatrix`` へ入れる、
  行列による空間の切り替えの説明。
* Robert Joosten の「maya-weighted-blend-matrix」のREADME: 標準の ``blendMatrix`` はtargetを順に重ねる(加算的な)混ぜ方なので、
  重みを均等に扱う混ぜ方とは異なる、という指摘。

SpaceBlendは、cmtの方法を元に、 ``blendMatrix`` の順に重ねる性質を逆に使い、i番目のtargetの割合を ``w_i / (w_0 + … + w_i)`` にすることで、
空間の順番によらず重みの合計で割った平均になるようにしました。コードは流用していません。

引数
----

* ``follower``: 追従させる対象のtransform。生成時のワールド行列を基準(各空間からのoffset)にします。follower自体は変更しません。
* ``spaces``: 参照空間のtransform(2個以上、重複なし、followerを含まない)。
* ``weights``: 空間ごとの重みの初期値(0以上)。省略すると先頭の空間だけ1です。

計算式
------

1. 空間iの追従先 ``target_i = offset_i · space_i.worldMatrix`` 。 ``offset_i = 生成時のfollower · 生成時のspace_i の逆`` (定数)。
2. ``blendMatrix`` の入力を ``target_0`` 、 ``target[i-1]`` を ``target_i`` 、そのweightを ``ratio_i = w_i / (w_0 + … + w_i)`` にします
   ( :meth:`SpaceBlend.ratios` 。累積が0なら0)。
3. ``blendMatrix`` は前の結果から各targetへ順に補間するので、位置は ``Σ w_i · p_i / Σ w_i`` (正確な重み付き平均)、
   回転は順に行う球面補間になります。2つの空間だけなら回転は ``slerp(q_0, q_1, w_1 / (w_0 + w_1))`` です。

生成時は全ての ``target_i`` がfollowerの行列と同じなので、重みに関係なく出力はfollowerと一致し、作成時に跳ねません。

出力
----

* ``matrix``: 混ぜた後のワールド行列。
* ``totalWeight``: 重みの合計(確認用)。

制限
----

* 3つ以上の空間の回転は、順に行う球面補間なので、厳密なクォータニオンの平均とは少し異なります(位置は正確な平均です)。
* 重みが全て0のときは先頭の空間に追従します。
* 重みを変えた瞬間に姿勢を保つ(切り替え時の補正)機能はありません。空間を動かした後に重みを変えると、出力はその割合の位置へ動きます。
  切り替え時に姿勢を保ちたい場合は ``SpaceSwitch`` を使います。
* 出力はワールド行列です。原点以外の親の下へ ``matrix`` を接続すると二重変換になります。

テスト
------

``mlrig/__tests__/test_setup_space_blend.py`` (``setups`` スイート)で、回転・移動した3つの空間とfollowerを作り、
作成直後はどの重みでも跳ねないこと、1つの空間だけの重みでその空間の追従先と一致すること、位置がOpenMayaで独立に求めた重み付き平均と一致すること、
2つの空間で回転が ``MQuaternion.slerp`` と一致すること、割合の計算と重みが全て0の場合、初期値、containerの所有とUndo/Redo、引数の検査を確認します。
Maya 2025・2027で確認しています。

検証動画
--------

``tools/demo_space_blend.py`` は、新規シーンに world(灰)・胸(青)・手(黄)の空間と出力(緑の十字)を正面から見る構図で作り、
胸を揺らし・手を回し続けながら、重みを world → 胸 → 手 → 均等 → 胸と手(1:3) → world と変えて録画します。
式と毎フレームの重み・ ``blendMatrix`` へ渡す割合・出力の位置をHUDに表示し、各フレームで出力の位置が重み付き平均と一致することを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-space-blend.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_space_blend.py --launch
