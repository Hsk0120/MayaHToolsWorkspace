スカートの脚よけ(SkirtLegOffset)
================================

``mlrig.setups.SkirtLegOffset`` は、脚(股関節→膝)がスカート・腰布の根元の骨に近づくと、
その骨を脚から離れる向き(外側)へ自動で開く補助骨の計算を作ります。
脚を上げたときに布の骨が脚へめり込んだ姿勢のままだと、揺れ物のシミュレーションや手付けのアニメーションが
めり込んだ状態から始まり、押し出しがうまくいかずに暴れたり張り付いたりします。この部品で先に骨を開いておけば、
めり込んでいない姿勢から計算・作業を始められます。
Maya標準ノード(``vectorProduct`` ・ ``angleBetween`` ・ ``condition`` ・ ``multiplyDivide`` ・ ``plusMinusAverage`` ・
``clamp`` ・ ``composeMatrix`` ・ ``multMatrix`` ・ ``decomposeMatrix`` ・ ``unitConversion``)だけで組み、
独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import SkirtLegOffset

   graph = SkirtLegOffset.create(
       "pelvis_jnt",
       ["skirt_front_jnt", "skirt_frontL_jnt", "skirt_L_jnt", "skirt_back_jnt"],
       [("thigh_L_jnt", "knee_L_jnt"), ("thigh_R_jnt", "knee_R_jnt")],
       name="skirtLegOffset", clearance=10.0, maxAngle=80.0, spread=45.0, connect=True)
   owner = graph.container
   # connect=True なら各骨の offsetParentMatrix へ開く回転を接続済み。骨の回転は手付け・揺れ物に使える

参考にした考え方
----------------

* 補助骨の一般的な使い方: ドライバーとなる骨の回転から、別の骨(補助骨)の移動・回転・スケールを自動で動かし、
  一定の値以上では反応しない上限や、反応の始まりを早める・遅らせる調整を持たせて、髪の毛や揺れ物のめり込みを避ける方法。
* スカートと脚が同じ親の下に並ぶ構成で、脚を上げると同時に補助骨でスカートの根元を自動でずらし、
  めり込んでいない姿勢から揺れ物のシミュレーションを始めると、衝突の押し出しが安定する、という考え方。
  ゲームのように地形に合わせたIKで脚の姿勢が変わる場合でも働くよう、キーに焼き込まずにリグの計算で行います。

この部品は、骨ごとに「骨が外へ開く面」を決め、その面へ写した脚の角度から開く量を求める形にしました。
コードは流用していません。

引数
----

* ``parent``: 腰のtransform。スカートの骨と脚の付け根の共通の親で、計算はこの空間で行います。
* ``skirts``: スカート・腰布の根元の骨(1個以上)。腰の中心( ``parent`` の原点)から離れた位置に置きます。
* ``legs``: 脚ごとの ``(付け根, 先)`` のtransform(股関節と膝など)。付け根→先を脚の向きとします。複数の脚のうち、骨を大きく押す方を使います。
* ``skirtAxis``: 骨のローカルで骨が伸びる向きの軸(x/y/z、-付き可)。省略すると各骨の最初の子transformへの向きです。
* ``clearance``: 脚が骨に届く手前から開き始める角度(度)。大きいほど早く開き、開いた後も脚との間をこの角度だけ空けます。
* ``maxAngle``: 開く角度の上限(度、0〜180)。
* ``spread``: 押す量が0になる、脚が骨の開く面から横へ外れる角度(度、0〜90)。小さいほど、脚の正面にある骨だけが開きます。
* ``connect``: Trueなら各骨の ``offsetParentMatrix`` へ ``offsetMatrix<i>`` を接続します。骨は ``parent`` の直接の子で、
  ``offsetParentMatrix`` が単位行列・未接続である必要があります。

計算式
------

生成時の骨の ``parent`` 空間の行列 ``M`` 、骨の向き ``s`` 、位置 ``p`` から、骨が開く面の法線(回転軸) ``t = normal(s × p)`` と
外向き ``n = t × s`` を定数として持ちます。脚の向き ``l`` ( ``parent`` 空間の 先 - 付け根)から、

1. ``planeAngle`` : 面へ写した脚の向き ``(l·s, l·n)`` の、骨の向きから外側へ測った角度(= ``atan2(l·n, l·s)`` 、度)。
   ``angleBetween`` の角度に ``l·n`` の符号を付けて求めます。
2. ``lateralAngle = |90 - (l と t の角度)|`` : 脚が面から横へ外れた角度。
3. ``push = clamp((planeAngle + clearance) * clamp(1 - lateralAngle / spread, 0, 1), 0, maxAngle)`` (:meth:`SkirtLegOffset.push`)。
4. ``angle<i> = max(各脚の push) * weight`` 。
5. ``G`` を行が ``t, s, n`` 、位置が ``p`` の行列として、 ``offsetMatrix<i> = G^-1 · Rx(angle<i>) · G`` ( ``p`` を通る ``t`` 回りの回転)、
   ``matrix<i> = M · offsetMatrix<i>`` 、 ``worldMatrix<i> = matrix<i> · parent の worldMatrix`` 。

脚が骨の開く面の中にあり上限に届かないとき、開いた骨と、面へ写した脚の間は ``clearance`` 度になります。
角度は ``unitConversion`` で度・ラジアンを明示的に変換するので、UI単位が度でもラジアンでも同じ結果です。
生成時に脚が ``clearance`` より離れていれば ``angle<i>`` は0で、出力は生成時の骨と一致します(跳ねません)。

containerのアトリビュート
--------------------------

* ``clearance`` ・ ``maxAngle`` ・ ``spread`` : 上の引数と同じ(keyable、度)。
* ``weight`` : 開く量の割合(keyable、既定1)。0で開かない。
* ``angle<i>`` : 骨 ``skirts[i]`` を開く角度(度、確認用・ドリブンキーやブレンドの入力にも使える)。
* ``offsetMatrix<i>`` : ``parent`` 空間での開く回転(差分)。 ``connect=True`` で骨の ``offsetParentMatrix`` へ接続します。
* ``matrix<i>`` ・ ``worldMatrix<i>`` : 開いた骨の ``parent`` 空間・ワールドの行列。

制限
----

* 脚は付け根→先の1本の線分の向きだけで見ます。太さ・膝から下・脚の位置(腰の中心からのずれ)は見ないので、
  脚の太さの分は ``clearance`` ・ ``spread`` で調整します。
* 骨は面の中で外へ開くだけで、横へよける・縮む動きはしません。骨の先の節は親に付いて動くだけです(先の節の補正は揺れ物・手付けで行う)。
* 腰の中心( ``parent`` の原点)にある骨や、腰の中心からまっすぐ外を向いた骨は、開く面が決まらないので ``ValueError`` です。
* 布同士・布と体の衝突やシミュレーションは行いません(この部品はシミュレーションの前の姿勢を作る)。
* 生成時に脚が既に骨へ近い( ``clearance`` 以内)場合は、作成した時点で骨が開きます。

テスト
------

``mlrig/__tests__/test_setup_skirt_leg_offset.py`` (``setups`` スイート)で、傾けた腰の下に左右の脚と外へ15度開いた8本の骨を作り、
作成直後に全ての角度が0で骨と一致すること、前・横・後ろ・ひねり・腰の回転の各姿勢で角度・ ``offsetMatrix`` ・ ``matrix`` ・ ``worldMatrix`` が
試験側で ``atan2`` ・ ``asin`` ・軸回りのQuaternionから独立に求めた値と一致すること、脚を前へ上げると前の骨だけが開き、
開いた骨と面へ写した脚の間が ``clearance`` 度になること(単調に開くこと)、アトリビュートの変更、 ``connect=True`` での接続と骨のワールド行列、
``skirtAxis`` の指定、UI単位(mm・ラジアン)、所有とUndo/Redo、引数の検査を確かめます。
