位置をずらせるFK(SlidingFk)
==============================

``mlrig.setups.SlidingFk`` は、尻尾・触手・背骨などの節の多いチェーンを、節の数より少ないFKコントロールで動かすための部品です。
コントロールごとにチェーン上の位置 ``position<k>`` (根元0〜先端1)と広がり ``falloff<k>`` を持ち、
コントロールの回転をその位置の近くの数節へ割り振ります。位置はアトリビュートなので、アニメーションの途中で
曲げる場所をチェーンに沿ってずらせます(根元で曲げていたものを先の方で曲げる、など)。
Maya標準ノード(``distanceBetween`` ・ ``setRange`` ・ ``clamp`` ・ ``plusMinusAverage`` ・ ``condition`` ・ ``multiplyDivide`` ・
``composeMatrix`` ・ ``blendMatrix`` ・ ``multMatrix``)だけで組み、コンストレイント、独自プラグイン、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import SlidingFk

   graph = SlidingFk.create(["tail0", "tail1", "tail2", "tail3", "tail4", "tail5", "tail6"],
                            ["tail_bendA_ctrl", "tail_bendB_ctrl"], name="tailSlide",
                            positions=(0.2, 0.7), falloff=0.3)
   owner = graph.container
   # 出力はワールド行列。原点にある親の下の、TRSがidentityのjointで受ける
   for index in range(7):
       owner.getPlug("matrix" + str(index)).connectTo("tail_bind{}.offsetParentMatrix".format(index))
   owner.getPlug("position0").set(0.5)    # 1つ目のコントロールで曲げる場所を中ほどへ

参考にした考え方
----------------

* mikan の ``templates/template/rig/slide`` (MIT、「slide FK chain rig」): チェーンに沿って位置(parameter)を動かせるFKコントロールを持ち、
  各節の位置とコントロールの位置の差を ``falloff`` で割った値を三角形の曲線(-1→0、0→1、1→0)で重みにし、
  コントロールごとに節の重みの合計で割って、コントロールの回転を節へ割り振る(クォータニオンの球面補間)構成。

SlidingFkはこの「位置と広がりを持つコントロールの回転を、正規化した三角形の重みで節へ分ける」考え方を、
animCurve・式を使わず ``distanceBetween`` (差の絶対値)・ ``setRange`` ・ ``clamp`` と ``blendMatrix`` (単位行列からの球面補間)で組み直しました。
mikanのようにコントロール自体をチェーンの曲線に沿って動かす仕組み(motionPathと逆変換)は持たず、コントロールの置き場所は利用側で決めます。
コードは流用していません。

引数
----

* ``joints``: 根元から順の節のtransform(joint可)を3個以上。親子の列でなくてもかまいません。
* ``controls``: 回転を読むコントロールのtransform(1個以上)。 ``rotate`` と ``rotateOrder`` を、各節の生成時の向きの空間での回転として使います。
  例えば節の向きのZ軸で曲げたいなら、コントロールの ``rotateZ`` を回します。
* ``positions``: コントロールごとのチェーン上の位置の初期値(0〜1)。省略すると ``(k+0.5)/コントロール数`` の等間隔です。
* ``falloff``: 重みが0になるまでの位置の差の初期値(全コントロール共通、0より大きい)。省略すると ``1.5/(節の数-1)`` です。

計算式
------

1. 節jのチェーン上の位置 ``t_j`` は、生成時の節の間の長さの累積を全長で割った値です(:meth:`SlidingFk.parameters` 。先頭0・末尾1)。
2. ``tri_jk = clamp(1 - |t_j - c_k| / falloff_k, 0, 1)`` ( ``c_k = position<k>`` 。 ``|t_j - c_k|`` は ``distanceBetween`` 、 ``1 - x/falloff`` は ``setRange`` )。
3. ``w_jk = tri_jk / Σ_j tri_jk`` (コントロールごとに節の重みの合計が1。合計が0なら0)。
4. ``R_j = slerp(I, Q_1, w_j1) · slerp(I, Q_2, w_j2) · …`` ( ``Q_k`` はコントロールkの回転。 ``blendMatrix`` で単位行列から補間し ``multMatrix`` で積む)。
5. ``matrix<j> = R_j · Rest_j · matrix<j-1>`` 。 ``Rest_j`` は生成時の親の節に対する相対行列(定数)、 ``matrix<-1>`` は先頭の節の親の ``worldMatrix`` です。

末尾の節は回転を受けず、1つ前の節に付いていきます。重みの合計が1なので、同じ軸の回転なら曲がりの合計はコントロールの回転と等しくなります。
コントロールの回転が0なら生成時の姿勢と一致し、作成時に跳ねません。

出力
----

* ``matrix0`` 〜 ``matrix<n-1>``: 各節のワールド行列。
* ``weight<j>[k]``: 節j・コントロールkの正規化した重み(確認用)。

制限
----

* 1つのコントロールの回転を複数の節へ球面補間で分けるので、180度を超える回転は短い向きの回転として扱われます。
* 複数のコントロールの回転は順に積むので、違う軸の回転を同じ節で重ねると、順序による差が出ます。
* コントロールをチェーンの曲がりに沿って動かす仕組み(コントロールの位置の出力)はありません。コントロールはチェーンの外に置きます
  (出力の節の下に置くと循環になります)。
* falloffが節の間隔より小さく、位置が節の間にあると、どの節にも重みが届かず回転は0になります。
* 出力はワールド行列です。原点以外の親の下へ接続すると二重変換になります。

テスト
------

``mlrig/__tests__/test_setup_sliding_fk.py`` (``setups`` スイート)で、回転・移動した親の下のjointOrient付き・長さの不均等な6節と2つのコントロールを作り、
コントロールの回転が0なら位置・falloffによらず生成時と一致し親に付いていくこと、節の位置の割合と ``weight<j>[k]`` が独立計算と一致しコントロールごとの合計が1であること、
回転・位置・falloffを変えた各状態で各節の行列がOpenMayaで独立に求めた三角形の重み・ ``MQuaternion.slerp`` ・積と一致すること、
falloffを小さくして位置を節に合わせるとその節だけが回転を全て受けること、平面のチェーンで1つのコントロールのZ回転が先端の向きの変化の合計と等しいこと、
重みが届かない位置で回転が0になること、containerの所有とUndo/Redo、引数の検査を確認します。Maya 2025・2027で確認しています。

検証動画
--------

``tools/demo_sliding_fk.py`` は、新規シーンに8節の尻尾(入力、灰)と出力(緑)、2つのコントロールの位置を示す目印(黄・橙)を横から見る構図で作り、
コントロールの回転・ ``position`` ・ ``falloff`` を順に変えて、曲げる場所がチェーンに沿って移る様子を録画します。
式と毎フレームの位置・広がり・節ごとの重み・曲がりの合計をHUDに表示し、各フレームで出力が独立計算と一致することを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-sliding-fk.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_sliding_fk.py --launch
