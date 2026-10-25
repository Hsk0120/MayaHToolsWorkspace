4辺からの潰しと伸ばし(SquashBox)
=================================

``mlrig.setups.SquashBox`` は、箱形の対象(頭・胴・小道具など)を上・下・外・内の4辺から押し引きして、
反対の辺を支点に潰す・伸ばす行列を作ります。伸ばした向きと直交する2軸は、体積を保つように細く・太くします。
Maya標準ノード(``multiplyDivide`` ・ ``plusMinusAverage`` ・ ``composeMatrix`` ・ ``multMatrix``)だけで組み、
transformの階層や独自プラグイン、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import SquashBox

   graph = SquashBox.create("head_ctrl", name="headSquash", height=24.0, width=18.0,
                            verticalAxis="y", sideAxis="x", volume=1.0)
   owner = graph.container
   # 出力はワールド行列。原点にある親の下の、TRSがidentityのtransformで受ける
   owner.getPlug("matrix").connectTo("head_squash_jnt.offsetParentMatrix")
   owner.getPlug("top").set(3.0)

``top`` ・ ``bottom`` ・ ``outer`` ・ ``inner`` ・ ``volume`` はcontainerのkeyableなアトリビュートで、
ふつうはコントロールの移動(例: 上の矢印のコントロールの ``translateY``)を接続して使います。

参考にした考え方
----------------

``maya/external/mgear5`` の ``shifter_classic_components/squash4Sides_01`` (MIT)は、上・下・外・内の4つの矢印のコントロールを
入れ子のtransformに置き、各コントロールの移動量から、反対の辺の位置を支点にした拡大と、
直交する向きの ``2 - 伸ばした比率`` の拡大(体積を保つ近似)を各階層のscaleへ接続します。
SquashBoxはこの考え方(反対の辺を支点にした4つの拡大を上→下→外→内の階層の順に重ねる・体積の割合)を、
transformの階層を作らずに行列の積で計算する形にしました。コードは流用していません。

引数
----

* ``root``: 箱の基準のtransform。箱はこの原点を中心に置き、出力はこの現在のワールド行列に付いてきます。
* ``height`` ・ ``width``: 上下の辺の間、外と内の辺の間の長さ(cm)。
* ``verticalAxis`` ・ ``sideAxis``: rootのローカルで上下・外内を表す軸(x/y/z、別の軸)。上・外は正の向きです。
* ``volume``: 体積を保つ割合の初期値(0〜1)。0なら直交する向きは変えません。

計算式
------

辺の値を ``a`` (cm、外へ動かすと正)、向かい合う辺の間の長さを ``d`` とします。

1. 伸ばす向きの拡大率 ``1 + a/d`` 、直交する2軸の拡大率 ``1 - volume * a/d`` ( :meth:`SquashBox.factors` )。
   ``volume = 1`` のとき、mGearの ``2 - (d + a)/d`` と同じ値です。
2. 1つの辺の行列 ``P = T(-p) · S · T(p)`` 。 ``p`` は反対の辺の中心の生成時の位置で、そこを支点に拡大します。
3. ``localMatrix = P_inner · P_outer · P_bottom · P_top`` (Mayaの行ベクトルの規約で左から先に適用。
   上→下→外→内の入れ子の階層の末端の点を親へたどるのと同じ順)、 ``matrix = localMatrix · root`` 。

全ての値が0なら ``localMatrix`` は単位行列なので、作成時に姿勢が跳ねません。
1つの辺だけを動かすと、反対の辺の中心は動かず、動かした辺の中心はちょうど ``a`` だけ外へ動きます。

出力
----

* ``localMatrix``: rootの空間での潰し・伸ばしの行列。rootの子に置いたtransformの ``offsetParentMatrix`` へ接続できます。
* ``matrix``: ``localMatrix · root`` のワールド行列。

制限
----

* 直交する向きの拡大率は体積を正確に保つ式( ``1/sqrt(1 + a/d)`` )ではなく、mGearと同じ線形の近似です。
  大きく伸ばすと直交する向きが0以下になり、潰しすぎ( ``a <= -d`` )でも裏返ります。値の範囲は制限していません。
* 4つの拡大は互いに独立ではなく、上→下→外→内の階層の順に重なります(mGearの入れ子の階層と同じ)。
  例えば ``top`` と ``bottom`` を同時に動かすと、 ``bottom`` の支点(上の辺)は ``top`` の拡大で動いた位置になります。
* 出力はワールド行列です。原点以外の親の下へ ``matrix`` を接続すると二重変換になります。

テスト
------

``mlrig/__tests__/test_setup_squash_box.py`` (``setups`` スイート)で、回転・移動したrootの下に scalePivot を反対の辺に置いた
transformの階層(上→下→外→内)を組み、各辺の伸ばし・潰しと組み合わせで出力の行列が参照の末端のワールド行列と一致すること、
作成直後に跳ねないこと、反対の辺の不動と動かした辺の移動量、 ``volume`` の割合、rootの移動と回転、軸の指定、containerの所有とUndo/Redo、
引数の検査を確認します。Maya 2025・2027で確認しています。

検証動画
--------

``tools/demo_squash_box.py`` は、新規シーンに生成時の箱(赤・半透明)と出力の箱(緑)を正面から見る構図で作り、
式と毎フレームの4辺の値・ ``volume`` ・各向きの拡大率をHUDに表示して録画します。
上を伸ばす→上を潰す→下→外→内→組み合わせ→ ``volume`` を0にする→基準への復帰を記録し、
各フレームで参照の階層と一致することを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-squash-box.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_squash_box.py --launch
