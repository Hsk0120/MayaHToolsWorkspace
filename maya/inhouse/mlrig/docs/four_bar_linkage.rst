四節リンク(FourBarLinkage)
===========================

``mlrig.setups.FourBarLinkage`` は、固定の2つの支点(クランクの支点 ``A`` とロッカーの支点 ``D`` )を持つ4本の棒の閉ループ
(クランク ``AB`` ・カプラー ``BC`` ・ロッカー ``DC`` ・地面 ``AD`` )で、クランクを回したときのカプラーとロッカーの関節 ``C`` を求め、
ロッカーのワールド行列(``rockerMatrix``)・カプラーのワールド行列(``couplerMatrix``)・関節の位置(``jointMatrix``)を出力します。
ワイパー・ドアのヒンジ・サスペンション・重機のバケットのリンク・甲冑や小道具の連動など、閉じたリンクの機構をクランクの回転だけで動かせます。
Maya標準ノード(``multMatrix`` ・ ``vectorProduct`` ・ ``plusMinusAverage`` ・ ``multiplyDivide`` ・ ``clamp`` ・ ``condition`` ・
``unitConversion`` ・ ``fourByFourMatrix`` ・ ``angleBetween`` ・ ``pickMatrix`` ・ ``aimMatrix``)だけで組み、
独自プラグイン、IK、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   import mlib
   from mlrig.setups import FourBarLinkage

   # crankPin はクランク(Z回りに回す)の子、rocker は台の子でロッカーの支点に置く、
   # rockerEnd は関節 C の生成時の位置(rocker の子でもよい。位置だけを読む)
   graph = FourBarLinkage.create("crankPin", "rocker", "rockerEnd", name="wiperLink")
   owner = graph.container
   # 出力はワールド行列。ワールド直下の表示用transformの offsetParentMatrix へ繋ぐ
   mlib.getPlug("{}.rockerMatrix".format(owner)).connectTo("rockerGeo.offsetParentMatrix")
   mlib.getPlug("{}.couplerMatrix".format(owner)).connectTo("couplerGeo.offsetParentMatrix")

メニューの **Setup Samples** の「FourBarLinkage - crank, coupler and rocker」でも試せます(:doc:`setup_samples`)。

参考にした考え方
----------------

* 四節リンクの関節を「2つの円の交点」として置く古典的な作図(機構学の教科書・Techniques de l'Ingénieur の関節機構の解説)。
* Tech-Artists.org の四辺形のリグの相談で挙がった、IKチェーンとエクスプレッションの三角法で閉ループを解く案。
  ここではIK・エクスプレッションを使わず、交点を標準ノードの閉じた式で求めます。
* 閉ループのリンクには「交わる/交わらない」2つの枝があり、途中で枝が入れ替わらないようにする必要があること(マルチボディ解析の例題)。

コードは流用していません。

引数
----

* ``pin``: クランクのピン ``B`` を示すtransform(回るクランクの子に置く)。位置だけを使います。
* ``rocker``: ロッカーのtransform(joint可)。生成時の位置をロッカーの支点 ``D`` 、親の空間を機構の空間(台)にします。
  生成時の姿勢を ``rockerMatrix`` の基準にします。
* ``end``: カプラーとロッカーを繋ぐ関節 ``C`` の生成時の位置を示すtransform。位置だけを読み、接続しません。
  生成時の ``|C - B|`` をカプラーの長さ、 ``|C - D|`` をロッカーの長さにします。
* ``coupler``: カプラーのtransform(省略可)。生成時の姿勢を ``couplerMatrix`` の基準にします。省略するとピンの位置で
  X を ``C`` へ、Z を機構の面の法線へ向けた枠を基準にします。
* ``normal``: 機構の面の法線(ロッカーの親の空間、省略可)。既定は ``(D - B) × (C - B)`` 。 ``B`` ・ ``C`` ・ ``D`` が一直線に並ぶ姿勢で作る場合は指定します。

計算式
------

ロッカーの親の空間で、ピンの位置 ``P = B`` 、支点 ``D`` 、カプラーの長さ ``b`` 、ロッカーの長さ ``c`` 、機構の面の単位法線 ``n`` として、

``w = D - P`` 、 ``d = |w|`` 、 ``u = w / d``

``x = clamp((d^2 + b^2 - c^2) / (2d), -b, b)`` 、 ``h = s * sqrt(max(b^2 - x^2, 0))``

``C = P + x u + h normalize(n × u)``

``excess = max(d - (b + c), |b - c| - d, 0)`` 、 ``transmissionAngle = angle(B - C, D - C)``

``s`` (+1/-1)は生成時に ``C`` が ``B→D`` の線のどちら側にあったかで決める枝で、クランクを回しても反対の枝(交差した配置)へ跳びません。
:meth:`FourBarLinkage.jointPosition` がPython版です。

* ``jointMatrix = T(C) * S`` ( ``S`` はロッカーの親の worldMatrix、行ベクトル規約)。 ``fourByFourMatrix`` の単位の無い成分で作るので、
  UI単位がmmでも単位変換が入りません。
* ``rockerMatrix`` は生成時のロッカーの行列 ``R_r * S`` を、 ``aimMatrix`` で生成時に ``D→C`` を指していた軸を ``C`` へ、
  法線を生成時の法線へ揃えたものです。支点 ``D`` は動きません。
* ``couplerMatrix`` は生成時のカプラーの姿勢を ``pickMatrix`` (平行移動だけ)でピンの位置へ運び、 ``aimMatrix`` で ``C`` へ向けたものです。
* 伝達角 ``μ`` はカプラーとロッカーの間の角度で、90度に近いほど力が伝わりやすく、0度・180度に近いと死点(ロッカーが動きにくい姿勢)です。

containerのアトリビュート
--------------------------

* ``couplerLength`` ・ ``rockerLength``: カプラー・ロッカーの長さ(keyable、既定は生成時の距離)。
* ``excess``: 閉ループが作れないときの長さの不足・超過(確認用、作れるときは0)。
* ``transmissionAngle``: 伝達角(確認用)。
* ``rockerMatrix`` ・ ``couplerMatrix`` ・ ``jointMatrix``: ワールド行列(出力)。

制限
----

* ピン ``B`` は機構の面の中を動く前提です。面の外へ出ると ``C`` は ``B→D`` の線の回りの円の上の ``n × u`` の向きの点になり、
  面の外への傾きは見ません。
* ``d > b + c`` または ``d < |b - c|`` で閉ループが作れない場合、 ``C`` は ``B→D`` の線の上で ``B`` から ``b`` の点に止まり、
  ロッカーとの距離は ``c`` になりません。 ``excess`` で量を確認できます。
* 枝は生成時に固定します。クランクを ``B`` ・ ``C`` ・ ``D`` が一直線になる死点の近くで回すと、 ``C`` がその点で折り返します(物理的な機構と同じ)。
  枝を途中で切り替える機能はありません。
* クランク自体の回転(駆動)は扱いません。 :doc:`GearTrain <gear_train>` ・ :doc:`WheelRoll <wheel_roll>` などの出力で回せます。
* 出力はワールド行列なので、原点以外の親の下へ繋ぐと二重に変換されます。
* 計算は ``multiplyDivide`` などの単精度のノードを通るため、位置の誤差は 1e-5 cm 程度です。

テスト
------

``mlrig/__tests__/test_setup_four_bar_linkage.py`` (``setups`` スイート)で、回転・移動した台の下にクランク2cm・地面6cm・カプラー5cm・
ロッカー4cmの機構(Grashofのクランク・ロッカー)を作り、次を確認します。

* 作成直後にロッカーの出力が生成時と一致し、関節が ``end`` の位置にあること。
* クランクを15度刻みで一周させ、関節がロッカーの角度の閉じた式(Freudensteinの形 ``K1 cosψ + K2 sinψ = K3`` 、試験側の独立計算)と
  Python版に一致し、棒の長さ・ロッカーの支点・カプラーとロッカーの向き・法線・伝達角(余弦定理)が保たれること。
* 交差した配置で作ると一周してもその枝のままであること。
* 長さの変更、 ``d > b + c`` と ``d < |b - c|`` の届かない場合の位置と ``excess`` 。
* 作成後の台の移動回転、カプラーのtransformを渡した場合の姿勢とUI単位 mm/rad、containerの所有と入力へ接続しないこと・Undo/Redo、引数の検査。

Maya 2027で確認しています。

検証動画
--------

``tools/demo_four_bar_linkage.py`` は、新規シーンに機構を正面から見る構図で作り、クランクを一周させたあと、180度の位置で
``couplerLength`` を5cmから2.5cmへ縮めて閉ループが作れない状態(関節を赤で表示)にし、5cmへ戻して元の角度へ戻す動きを録画します。
HUDに式・固定値・毎フレームのクランクの角度・ ``couplerLength`` ・ ``d`` ・ロッカーの角度・伝達角・棒の長さ・ ``excess`` を表示し、
各フレームで関節が閉じた式と一致することを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-four-bar-linkage.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_four_bar_linkage.py --launch
