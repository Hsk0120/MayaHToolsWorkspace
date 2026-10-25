尻尾・触手のFK/IKの切り替え(FkIkChain)
==========================================

``mlrig.setups.FkIkChain`` は、尻尾・触手・首などの節の列で、FKのチェーンとIKのチェーンの姿勢を
``blend`` の割合(0=FK、1=IK)で混ぜた各節のワールド行列を作ります。
既定では、各節の **親の節に対する相対行列** を混ぜて根元から積むので、途中の割合でも節の間の長さが保たれ、
チェーン全体がFKとIKの間を弧を描いて移ります。コントロールの表示の切り替えに使う ``fkVisibility`` ・ ``ikVisibility`` と、
切り替えの前にFKをIKの姿勢へ合わせる :meth:`FkIkChain.matchFkToIk` も持ちます。
Maya標準ノード(``multMatrix`` ・ ``blendMatrix`` ・ ``condition``)だけで組み、コンストレイント、独自プラグイン、フレームごとのPythonは使いません。

IKのチェーン自体は、Spline IK(``mlrig.setups.SplineIK``)・HingeIK・リボンなど、別の仕組みで動かしたものを渡します。

.. code-block:: python

   from mlrig.setups import FkIkChain

   graph = FkIkChain.create(["tail_fk0", "tail_fk1", "tail_fk2", "tail_fk3"],
                            ["tail_ik0", "tail_ik1", "tail_ik2", "tail_ik3"],
                            name="tailFkIk", blend=0.0)
   owner = graph.container
   # 出力はワールド行列。原点にある親の下の、TRSがidentityのjointで受ける
   for index in range(4):
       owner.getPlug("matrix" + str(index)).connectTo("tail_bind{}.offsetParentMatrix".format(index))
   owner.getPlug("fkVisibility").connectTo("tail_fkCtrls_grp.visibility")
   owner.getPlug("ikVisibility").connectTo("tail_ikCtrls_grp.visibility")

   graph.matchFkToIk()                 # FKをIKの今の姿勢へ合わせる(1回だけの操作、Undo可)
   owner.getPlug("blend").set(0.0)     # 合わせた後なら、IKからFKへ切り替えても跳ねない

参考にした考え方
----------------

* mGear 5 の ``shifter_classic_components/chain_01`` (MIT): FK・IKの両方を持つチェーンで、アニメーション用の
  ``blend`` (Fk/Ik Blend)アトリビュートと、その値から作るFKコントロール(reverse)・IKコントロールの表示の切り替え、
  切り替え時に姿勢を合わせるための参照(match ref)を持つ構成。各節は ``parentConstraint`` の2つの重みをblendと1-blendにして
  ワールドの位置と向きを混ぜています。

FkIkChainは、mGearの「1つのblendアトリビュートと表示の切り替え・合わせ込み」の構成を、コンストレイントを使わず ``blendMatrix`` で組み直しました。
節ごとのワールドの位置を直線で混ぜると途中の割合で節の間が縮む(弦を引いたような形になる)ため、
既定では親の節に対する相対行列を混ぜて根元から積む形にしています(ワールドで混ぜる形も ``space="world"`` で選べます)。コードは流用していません。

引数
----

* ``fkChain``: FKの節のtransform(joint可)を根元から順に2個以上。
* ``ikChain``: IKの節のtransform(joint可)。 ``fkChain`` と同じ数・同じ順で、重複は不可。
* ``blend``: 割合の初期値(0〜1)。
* ``space``: ``"local"`` (既定、親の節に対する相対行列を混ぜる)または ``"world"`` (節ごとのワールド行列を混ぜる)。

計算式
------

``W^fk_i`` ・ ``W^ik_i`` を節iのワールド行列、 ``blend(A, B, w)`` を ``blendMatrix`` (scale・移動は線形、回転は球面補間)とします。

* ``space="local"`` :

  1. ``out_0 = blend(W^fk_0, W^ik_0, w)``
  2. ``L^fk_i = W^fk_i · (W^fk_{i-1})^-1`` 、 ``L^ik_i = W^ik_i · (W^ik_{i-1})^-1`` (親の節に対する相対行列)
  3. ``out_i = blend(L^fk_i, L^ik_i, w) · out_{i-1}``

  FKとIKで節の間の長さが同じなら、どの割合でも出力の節の間の長さは同じです(異なる場合は、親の節から見た位置を直線で混ぜます)。
* ``space="world"`` : ``out_i = blend(W^fk_i, W^ik_i, w)`` 。

``w=0`` ならFK、 ``w=1`` ならIKの各節のワールド行列と一致します。
``fkVisibility = (w < 1)`` 、 ``ikVisibility = (w > 0)`` ( ``condition`` )。

出力
----

* ``matrix0`` 〜 ``matrix<n-1>``: 混ぜた後の各節のワールド行列。
* ``fkVisibility`` ・ ``ikVisibility``: FK・IKのコントロールを表示する間だけ真になるbool。
* ``fkChain`` ・ ``ikChain``: 渡した節のmessage(:meth:`FkIkChain.getChain` で取得)。

切り替え時の合わせ込み
----------------------

:meth:`FkIkChain.matchFkToIk` は、FKの各節のtranslate・rotate・scaleへ、IKの対応する節の現在のワールド行列を根元から順に書き込みます
(mlibの ``Transform.setMatrix(worldSpace=True)`` 。jointOrientのあるjointも可)。1回のUndoで戻せます。
IKからFKへ切り替える前に呼ぶと、切り替えの前後で姿勢が跳ねません。

制限
----

* IKのコントロール(ゴール・ポール・Spline IKのコントロール)をFKの姿勢へ合わせる逆向きの合わせ込みは、IKの組み方によるため扱いません。
* ``matchFkToIk`` はロック・接続のある節には書き込めません。FKがIKと別の長さの場合、FKの節の位置もIKへ移ります。
* 出力はワールド行列です。原点以外の親の下へ接続すると二重変換になります。
* 割合の途中での体積・長さの補正、節ごとに違う割合(根元はFK・先はIKなど)は扱いません。

テスト
------

``mlrig/__tests__/test_setup_fk_ik_chain.py`` (``setups`` スイート)で、回転した親の下に姿勢の違うFK(transform)とIK(joint)の5節のチェーンを作り、
blend=0・1でFK・IKと一致すること(local・world)、途中の割合でOpenMayaで独立に求めた相対行列の補間と積に一致し節の間の長さが保たれること、
worldでは節ごとの補間に一致し節の間が縮むこと、節や親を動かしても追従すること、表示の切り替え、 ``matchFkToIk`` の一致・Undo/Redo・切り替えで跳ねないこと
(jointOrientのあるjointのFKも)、containerの所有とUndo/Redo、引数の検査を確認します。Maya 2025・2027で確認しています。

検証動画
--------

``tools/demo_fk_ik_chain.py`` は、新規シーンにFK(青、ゆるく波打つ)とIK(黄、先端が円を描く)の6節の尻尾と、
混ぜた出力(緑)・比較用にワールドで混ぜた出力(赤)を横から見る構図で作り、 ``blend`` を0→1→0と変えながら録画します。
式と毎フレームの割合・節の間の長さ(local・world)をHUDに表示し、各フレームで出力が独立計算と一致し、localの節の間の長さが保たれることを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-fk-ik-chain.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_fk_ik_chain.py --launch
