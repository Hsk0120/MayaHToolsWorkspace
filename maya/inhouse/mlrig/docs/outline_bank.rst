輪郭の縁で傾く支点(OutlineBank)
================================

``mlrig.setups.OutlineBank`` は、箱・足の裏・缶・機械の台座などの底の輪郭(nurbsCurve)を使い、コントロールを傾けた向きの側の
縁を支点にして物体を傾けたワールド行列を出力します。支点は傾ける向きとともに輪郭の上を連続して移るので、前後・左右・斜めの
どの向きへ傾けても、その側の縁で床に接したまま起き上がります。逆足(:doc:`FootRoll <foot_roll>`)の内外の縁のように
支点を軸ごとに決めておく必要がなく、輪郭の形を曲線で描くだけで済みます。
Maya標準ノード(``composeMatrix`` ・ ``multMatrix`` ・ ``vectorProduct`` ・ ``multiplyDivide`` ・ ``unitConversion`` ・
``nearestPointOnCurve``)だけで組み、独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import OutlineBank

   # bankCtrl: 傾けるコントロール(rotateX・rotateZ で傾ける)。baseOutline: 底の輪郭の閉じた曲線(コントロールと同じ親の下)
   graph = OutlineBank.create("bankCtrl", "baseOutline", name="crateBank", upAxis="y")
   owner = graph.container
   # matrix をワールド直下の箱の offsetParentMatrix へ繋ぐ
   mlib.getPlug("{}.matrix".format(owner)).connectTo("crateGeo.offsetParentMatrix")

参考にした考え方
----------------

* mikan(MIT)の ``templates/mod/rig/bank`` : コントロールの回転で上の軸を回して床の面へ落とし、その向きへ伸ばした点に最も近い
  輪郭の曲線の点(``nearestPointOnCurve``)を回転の支点にする考え方。探す点までの距離を輪郭の大きさの2倍にする既定値もこれに合わせました。
* 一般的な「動く支点(dynamic pivot)」: 物体を中心でなく接地している縁の周りに回すと、床に接したまま傾く。

コードは流用していません(mikanはコントロールの回転をtransformの ``rotatePivot`` へ渡す階層で組んでいますが、この部品は
transformの階層を作らず行列の積で出力します)。

引数
----

* ``control``: 傾けるコントロールのtransform(jointは不可)。 ``rotate`` ・ ``rotateOrder`` ・ ``translate`` を使います。
  出力はこのtransform自身ではなく、別の受け側へ接続します。
* ``outline``: 底の輪郭のnurbsCurve(またはそのtransform)。閉じた形(始点と終点が同じ点の1次の曲線、円など)にし、
  生成時の物体の底に重ねます。コントロールの回転に付いて回らない場所(コントロールと同じ親の下など)に置きます。
* ``upAxis``: 上の軸(x/y/z、底の空間)。
* ``reach``: 支点を探す点までの距離(cm)。Noneなら輪郭のローカルの大きさ(``boundingBoxSize`` の最大の辺)の2倍。
  containerの ``reach`` として後から変えられます。

計算式
------

底の空間を ``B = T(translate) * offsetParentMatrix * 親の worldMatrix`` 、コントロールの回転を ``R`` として(行ベクトル規約)、

* 向き ``d = normalize(up * R * F)`` (``F`` は上の軸の成分を0にする行列)。傾いた側の床の面の上の向きです。
* 支点 ``p`` = 底の空間の点 ``reach * d`` に最も近い輪郭の上の点(ワールドで ``nearestPointOnCurve`` を使い、底の空間へ戻す)。
* ``matrix = T(-p) * R * T(p) * B``

(:meth:`OutlineBank.direction` ・ :meth:`OutlineBank.localMatrix` がPython版)。 ``B`` の逆行列はプラグインの ``inverseMatrix`` を
使わず、 ``worldInverseMatrix * S * Sh * R`` (コントロールの scale・shear・rotate)で求めます。
回転が0なら ``R`` は単位行列なので、支点の位置に関わらず出力はコントロールの(scaleを除く)ワールド行列と一致し、接続しても跳ねません。
傾きが0のときの0ベクトルの正規化を避けるため、 ``F`` は別の軸へごく小さい値(``EPSILON`` = 1e-9)を足します。
組むあいだは内部単位(cm・rad)にするので、UI単位がm・ラジアンでも自動の単位変換の係数は1で、結果は同じです。

containerのアトリビュート
--------------------------

* ``reach``: 支点を探す点までの距離(keyable)。大きいほど斜めの向きで支点が角へ寄り、小さいほど辺の上を滑らかに移ります。
* ``pivot``: 支点(底の空間、cm、確認用)。
* ``matrix``: 傾けた物体のワールド行列(出力)。

制限
----

* 支点は「探す点に最も近い輪郭の点」なので、凸な輪郭で意味のある結果になります。凹んだ輪郭では凹みの中の点が支点になることがあります。
* 角のある輪郭を斜めに傾けると、支点は角の手前の辺の上にあり、角が少し床へ潜ります(既定のreachで、一辺4cmの正方形を14度で約0.11cm)。
  ``reach`` を大きくすると角へ寄って潜りは小さくなりますが、向きの小さな変化で支点が辺の上を速く移ります。
* 上の軸の回りのねじり(``rotateY`` など)も同じ支点の周りに回ります。必要ならコントロールのそのチャンネルをロックします。
* コントロールの scale・shear は出力に含めず、rotatePivotなどのpivot・rotateAxis は0を前提にします。
* 床は底の空間で上の軸に垂直な平面で、斜面・凹凸には追従しません(親を傾ければ床も傾きます)。
* 出力はワールド行列なので、原点以外の親の下へ繋ぐと二重に変換されます。

テスト
------

``mlrig/__tests__/test_setup_outline_bank.py`` (``setups`` スイート)で、回転・移動した親の下のコントロールと一辺4cmの正方形の輪郭を作り、
回転0でコントロールのワールド行列と一致すること、面の向きの傾きで支点が辺の中点になり OpenMaya で独立に組んだ ``T(-p) R T(p) B`` と
Python版に一致すること、斜めの傾きで支点が輪郭の上にあって動かず(reachを大きくしたとき)底の4隅が床へ潜らないこと、円の輪郭で支点が
傾いた向きの円の上の点になり底の円の最も低い点が床に接すること、移動・親への追従、upAxis=z・rotateOrder・UI単位 m/rad、
containerの所有とUndo/Redo、引数の検査を確認します。Maya 2025・2027で確認しています。

検証動画
--------

``tools/demo_outline_bank.py`` は、新規シーンに正方形の底の輪郭(黄)・傾く箱(緑)・比較用の中心で回すだけの箱(赤)を斜め上から見る構図で作り、
+X→斜め→-Z→-X→元へ戻す傾きで、式と毎フレームの回転・支点・最も低い角の高さをHUDに表示して録画します。
各フレームで行列が式と一致し、支点が輪郭の上にあって傾けても動かないことを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-outline-bank.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_outline_bank.py --launch
