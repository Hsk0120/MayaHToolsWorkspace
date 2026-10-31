交差する靭帯の膝(CrossedKneeLinkage)
=====================================

``mlrig.setups.CrossedKneeLinkage`` は、膝の前十字靭帯・後十字靭帯を、大腿骨と脛骨を結ぶ交差した2本の棒(四節リンク)とみなし、
曲げ角 ``flexion`` に対する脛骨のワールド行列を作ります。脛骨は固定の軸の回りに回るのではなく、2本の靭帯に吊られたまま
転がりながら滑ります。回転の中心(瞬間回転中心、2本の靭帯の線の交点)は曲げ角とともに移り、その位置も出力します。
2円の交点の計算は :doc:`FourBarLinkage <four_bar_linkage>` と同じグラフを共有しています。
Maya標準ノード(``composeMatrix`` ・ ``multMatrix`` ・ ``vectorProduct`` ・ ``plusMinusAverage`` ・ ``multiplyDivide`` ・
``clamp`` ・ ``condition`` ・ ``fourByFourMatrix`` ・ ``aimMatrix`` ・ ``unitConversion``)だけで組み、独自プラグイン、エクスプレッション、
フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import CrossedKneeLinkage

   graph = CrossedKneeLinkage.create("L_femur_jnt", "L_tibia_jnt", "L_aclFemur_loc", "L_aclTibia_loc",
                                     "L_pclFemur_loc", "L_pclTibia_loc", name="L_knee")
   owner = graph.container
   # 膝のコントロールの回転で曲げる
   mlib.getPlug("L_knee_ctrl.rotateZ").connectTo(owner.getPlug("flexion"))
   # 出力はワールド行列。ワールド直下の、TRSがidentityのtransformで受ける
   owner.getPlug("tibiaMatrix").connectTo("L_tibia_drv.offsetParentMatrix")

``flexion`` ・ ``aclLength`` ・ ``pclLength`` はcontainerのkeyableなアトリビュートです。付着点の4つのtransformは生成時の位置だけを読み、
接続しません(作成後に消してもかまいません)。

参考にした考え方
----------------

* 膝を交差した四節リンク(十字靭帯を2本の棒、大腿骨と脛骨を残りの2辺)とみなし、瞬間回転中心を2本の靭帯の線の交点とする
  モデルは、膝の運動学で古くから使われているものです(Zuppingerの記述に始まり、膝の装具の設計にも使われます)。
  例: `Acta of Bioengineering and Biomechanics, Vol. 18, No. 4 (2016) <https://actabio.pwr.edu.pl/fcp/HGBUKOQtTKlQhbx08SlkTUARAUWRuHQwFDBoIVURNWHhTFVZpCFghUHcKVigEQUw/302/public/publikacje/v18-4-2016/73.pdf>`_ 、
  `Olinski, Gronowicz, Handtke (2016) <https://yadda.icm.edu.pl/baztech/element/bwmeta1.element.baztech-5b428740-aa4c-474b-8781-f0e59cfb9e50/c/07_olinski_gronowicz_handtke_design_and_characterization_of_a_novel_2016_3.pdf>`_ 。
* 四節リンクの瞬間回転中心を2本の棒の延長線の交点で求める考え方は、義足の多軸膝の解説
  (`O&P Library <https://oandplibrary.org/op/1983_01_015.asp>`_)と同じです。

いずれもコードは流用していません。

引数
----

* ``femur``: 大腿骨のtransform。そのワールド行列を機構の空間にします。付着点の位置はこの空間で固定されます。
* ``tibia``: 脛骨のtransform。生成時の姿勢を曲げ角0の基準にします。
* ``aclFemur`` ・ ``aclTibia``: 前の靭帯の大腿骨側 ``A`` ・脛骨側 ``B`` の付着点のtransform。
* ``pclFemur`` ・ ``pclTibia``: 後ろの靭帯の大腿骨側 ``D`` ・脛骨側 ``C`` の付着点のtransform。
* ``normal``: 曲げの面の法線(大腿骨の空間)。曲げ角はこの軸回りの右ねじの向きが正です。 ``None`` なら ``(B - A) × (C - D)`` で、
  2本の靭帯が交差していれば、脛が後ろ(前の靭帯の脛骨側から後ろの靭帯の脛骨側の向き)へ動く向きが正になります。

計算式
------

大腿骨の空間で、 ``A`` ・ ``D`` を大腿骨側の付着点、 ``B0`` ・ ``C0`` を生成時の脛骨側の付着点、 ``a`` ・ ``p`` を前・後ろの靭帯の長さ、
``θ`` を ``flexion`` 、 ``R(θ)`` を ``n`` 回りの回転とします。

1. 脛骨の上のベクトル ``v = (C0 - B0) R(θ)`` 。 ``R(θ) = F^T * Rz(θ) * F`` ( ``F`` は Z を ``n`` にした正規直交の枠)を ``composeMatrix`` で作ります。
2. ``C = B + v`` が ``D`` から ``p`` の距離にあるので、 ``B`` は「 ``A`` を中心に半径 ``a`` の円」と「 ``D - v`` を中心に半径 ``p`` の円」の交点です。
   :doc:`FourBarLinkage <four_bar_linkage>` と同じ式 ``B = A + x u + s h normalize(n × u)`` ( ``w = D - v - A`` 、 ``d = |w|`` 、 ``u = w / d`` 、
   ``x = clamp((d^2 + a^2 - p^2) / 2d, -a, a)`` 、 ``h = sqrt(max(a^2 - x^2, 0))``)で求め、枝 ``s`` は生成時の配置で固定します。
3. ``C = B + v`` 、 ``excess = max(d - (a + p), |a - p| - d, 0)`` 。
4. ``tibiaMatrix = T0 * T(-B0) * R(θ) * T(B) * S`` ( ``T0`` は生成時の脛骨の大腿骨の空間での行列、 ``S`` は大腿骨の worldMatrix、行ベクトル規約)。
   脛骨は ``B0`` が ``B`` へ来るよう回転 ``R(θ)`` で動くので、生成時の脛骨の上の ``C0`` は ``C`` へ来ます。
5. 瞬間回転中心 ``P = A + t (B - A)`` 、 ``t = ((D - A) × e2)・n / ((e1 × e2)・n)`` ( ``e1 = B - A`` 、 ``e2 = C - D``)。
   分母の絶対値が 1e-9 より小さい(2本の線が平行)場合は分母を 1e-9 にします。
6. ``aclMatrix`` ・ ``pclMatrix`` は ``A`` ・ ``D`` に置き、X を ``B`` ・ ``C`` へ、Z を ``n`` へ向けた行列( ``aimMatrix``)です。

:meth:`CrossedKneeLinkage.tibiaPose` がPython版です。

containerのアトリビュート
--------------------------

* ``flexion``: 曲げ角(keyable、角度)。
* ``aclLength`` ・ ``pclLength``: 前・後ろの靭帯の長さ(keyable、既定は生成時の距離)。
* ``excess``: 閉ループが作れないときの長さの不足・超過(確認用、作れるときは0)。
* ``tibiaMatrix`` ・ ``aclMatrix`` ・ ``pclMatrix`` ・ ``instantCenterMatrix``: ワールド行列(出力)。

制限
----

* 平面の機構です。実際の膝の付着点は矢状面に乗っておらず、脛骨の回旋(screw home)や側副靭帯は扱いません。
  付着点は ``n`` に垂直な面へ射影した位置ではなく、そのままの位置で計算するので、面の外の成分はそのまま脛骨と一緒に動きます。
* 靭帯は伸び縮みしない棒です。 ``aclLength`` ・ ``pclLength`` を変えて閉ループが作れない( ``d > a + p`` または ``d < |a - p|``)と、
  ``B`` は ``A`` から ``D - v`` への線の上で ``A`` から ``a`` の点に止まり、 ``C`` と ``D`` の距離は ``p`` になりません。このとき2本の靭帯の線は
  平行になり、瞬間回転中心は無いので ``instantCenterMatrix`` は遠くへ飛びます。 ``excess`` で量を確認できます。
* 枝は生成時に固定します。 ``B`` ・ ``A`` ・ ``D - v`` が一直線になる曲げ角を越えると、物理的な機構と同じくそこで折り返します。
* 曲げ角が大きくなると(付着点の配置によりますが、例の配置では130度を超えたあたりから)瞬間回転中心が膝の外へ大きく移り、
  脛骨の動きは膝らしくなくなります。付着点は解剖学の資料に合わせて置いてください。
* 出力はワールド行列なので、原点以外の親の下へ繋ぐと二重に変換されます。
* 計算は ``multiplyDivide`` などの単精度のノードを通るため、位置の誤差は 1e-5 cm 程度です。

テスト
------

``mlrig/__tests__/test_setup_crossed_knee_linkage.py`` (``setups`` スイート)で、移動・回転・scale した腰の下の大腿骨に、交差する2本の靭帯
(前 3.72cm・後ろ 4.27cm)の付着点を置き、次を確認します。

* 作成直後に脛骨の出力が生成時と一致し、靭帯の長さが付着点の距離であること。
* 0〜120度を10度刻みで曲げ、脛骨の上の ``B0`` ・ ``C0`` の行き先が、前の靭帯の角度を走査して二分法で解いた独立計算と一致し、
  脛骨の回転が ``n`` 回りの ``θ`` で、靭帯の向き・瞬間回転中心(2直線の交点)・Python版が一致すること。この配置では瞬間回転中心が
  0〜70度で後ろへ、10〜120度で上へ移ること。
* 曲げると ``B0`` の行き先が固定軸の回転より大きく動く(転がりと滑り)こと。
* 靭帯の長さの変更と、 ``d < |a - p|`` の届かない場合の ``excess`` 。
* 作成後の腰・大腿骨の移動回転、UI単位 mm/rad での作成、法線を逆にすると曲げの向きが逆になること、containerの所有と入力へ接続しないこと・
  Undo/Redo、引数の検査。

Maya 2027で確認しています。

検証動画
--------

``tools/demo_crossed_knee_linkage.py`` は、新規シーンに膝を横から見る構図で作り、0度から120度まで曲げて60度へ戻し、 ``aclLength`` を
3.72cmから9cmへ伸ばして閉ループが作れない状態(前の靭帯を赤で表示)にし、3.72cmへ戻したあと、-15度まで伸ばして0度へ戻す動きを録画します。
緑が CrossedKneeLinkage の脛骨と靭帯、青が比較用の単純な蝶番(生成時の瞬間回転中心を固定軸にして同じ角度だけ回す)、赤い球が瞬間回転中心です。
HUDに式・固定値・毎フレームの曲げ角・ ``aclLength`` ・ ``d`` ・ ``B`` ・瞬間回転中心・靭帯の長さ・ ``B`` の移動量・ ``excess`` を表示し、
各フレームで独立計算と一致することを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-crossed-knee-linkage.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_crossed_knee_linkage.py --launch
