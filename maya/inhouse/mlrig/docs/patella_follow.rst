膝蓋骨の追従(PatellaFollow)
=============================

``mlrig.setups.PatellaFollow`` は、膝を曲げたときの膝蓋骨(パテラ)の位置と向きを作ります。膝蓋骨は長さが変わらない膝蓋腱で
脛骨粗面(脛の上の前側)に引かれ、大腿骨の溝(膝蓋骨が乗る溝)の円弧に沿って滑るものとみなし、「溝の中心を中心とする円」と
「脛骨粗面を中心とする膝蓋腱の長さの円」の交点に膝蓋骨を置きます。2円の交点の計算は :doc:`FourBarLinkage <four_bar_linkage>` と
同じグラフを共有しています。脛骨は入力のtransformのワールド行列をそのまま読むので、膝をIK・FK・:doc:`CrossedKneeLinkage <crossed_knee_linkage>`
のどれで曲げても追従します。
Maya標準ノード(``multMatrix`` ・ ``vectorProduct`` ・ ``plusMinusAverage`` ・ ``multiplyDivide`` ・ ``clamp`` ・ ``condition`` ・
``angleBetween`` ・ ``composeMatrix`` ・ ``animBlendNodeAdditiveDA`` ・ ``fourByFourMatrix`` ・ ``aimMatrix`` ・ ``unitConversion``)だけで組み、
独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import PatellaFollow

   graph = PatellaFollow.create("L_femur_jnt", "L_tibia_jnt", "L_patellaGroove_loc", "L_patella_jnt",
                                "L_tibialTuberosity_loc", name="L_patella")
   owner = graph.container
   # 出力はワールド行列。ワールド直下の、TRSがidentityのtransformで受ける
   owner.getPlug("patellaMatrix").connectTo("L_patella_drv.offsetParentMatrix")
   owner.getPlug("tendonMatrix").connectTo("L_patellarTendon_drv.offsetParentMatrix")

``grooveRadius`` ・ ``tendonLength`` はcontainerのkeyableなアトリビュートです。溝の中心・膝蓋骨・脛骨粗面のtransformは
生成時の位置(膝蓋骨は向きも)だけを読み、接続しません。脛骨粗面の位置は生成時に脛骨のローカルへ移して保持します。

参考にした考え方
----------------

* 膝蓋骨は大腿骨の膝蓋面(溝)に乗り、ほぼ伸びない膝蓋腱で脛骨粗面とつながるため、膝の曲げに合わせて溝に沿って下・後ろへ
  動くという解剖学の説明(例: `Patella - Physiopedia <https://www.physio-pedia.com/Patella>`_ 、
  `Patellar ligament - Kenhub <https://www.kenhub.com/en/library/anatomy/patellar-ligament>`_)。
* 膝蓋骨を脛骨の回転に固定の割合で追従させる代わりに、長さ一定の腱の拘束と溝の円の交点で求める形は、
  :doc:`FourBarLinkage <four_bar_linkage>` (溝の中心・膝蓋骨・脛骨粗面・膝を四節リンクとみなす)と同じ考え方です。

いずれもコードは流用していません。

引数
----

* ``femur``: 大腿骨のtransform。そのワールド行列を溝の空間にします。溝の中心はこの空間で固定されます。
* ``tibia``: 脛骨のtransform。そのワールド行列を接続し、脛骨粗面を一緒に動かします。大腿骨の子でなくてもかまいません。
* ``groove``: 溝の中心 ``G`` を示すtransform。膝蓋骨が乗る溝(大腿骨の顆の前面)の円弧の中心に置きます。
* ``patella``: 膝蓋骨のtransform。生成時の位置 ``P0`` と向きを基準にします。溝の半径 ``r`` の既定は ``|P0 - G|`` です。
* ``tuberosity``: 脛骨粗面 ``T0`` (膝蓋腱の脛骨側の付着点)を示すtransform。膝蓋腱の長さ ``L`` の既定は ``|T0 - P0|`` です。
* ``normal``: 曲げの面の法線(大腿骨の空間)。 ``grooveAngle`` はこの軸回りの右ねじが正です。 ``None`` なら ``(P0 - G) × (T0 - P0)`` で、
  膝を曲げて膝蓋骨が溝に沿って下へ回る向きが正になります。

計算式
------

大腿骨の空間で計算し、 ``S`` を大腿骨の worldMatrix、 ``W`` を脛骨の worldMatrix とします(行ベクトル規約)。

1. 現在の脛骨粗面 ``T = T0' * W * S^-1`` ( ``T0'`` は生成時の脛骨のローカルでの脛骨粗面)。 ``vectorProduct`` の点と行列の積で求めます。
2. 膝蓋骨 ``P`` は「 ``G`` を中心に半径 ``r`` の円」と「 ``T`` を中心に半径 ``L`` の円」の交点です。
   :doc:`FourBarLinkage <four_bar_linkage>` と同じ式 ``P = G + x u + s h normalize(n × u)`` ( ``w = T - G`` 、 ``d = |w|`` 、 ``u = w / d`` 、
   ``x = clamp((d^2 + r^2 - L^2) / 2d, -r, r)`` 、 ``h = sqrt(max(r^2 - x^2, 0))``)で求め、枝 ``s`` は生成時の配置で固定します。
3. ``excess = max(d - (r + L), |r - L| - d, 0)`` 。
4. ``R`` は ``angleBetween`` が返す ``(P0 - G)`` から ``(P - G)`` への最短回転、 ``grooveAngle = sign(axis・n) * angle`` 。
5. ``patellaMatrix = M0 * T(-P0) * R * T(P) * S`` ( ``M0`` は生成時の膝蓋骨の大腿骨の空間での行列)。膝蓋骨は ``G`` の回りに
   溝に沿って回った分だけ向きを変え、位置は ``P`` に来ます。
6. ``tendonMatrix`` は ``P`` に置き、X を脛骨粗面(ワールド)へ、Z を ``n`` へ向けた行列( ``aimMatrix``)です。

:meth:`PatellaFollow.patellaPose` がPython版です。

containerのアトリビュート
--------------------------

* ``grooveRadius``: 溝の半径(keyable、既定は生成時の距離)。
* ``tendonLength``: 膝蓋腱の長さ(keyable、既定は生成時の距離)。
* ``grooveAngle``: 溝の上で生成時から回った角度(出力、角度)。補正シェイプのドライバーに使えます。
* ``excess``: 交点が作れないときの長さの不足・超過(確認用、作れるときは0)。
* ``patellaMatrix`` ・ ``tendonMatrix``: ワールド行列(出力)。

制限
----

* 平面の機構です。溝は円弧で近似し、膝蓋骨の横方向のずれ(lateral tracking)や傾き(tilt)、脛骨の回旋は扱いません。
  脛骨粗面が曲げの面の外へ動くと、 ``P`` は面の中の円との交点ではなく、3次元の2つの球の交わりの円のうち ``n × u`` の向きの点になります。
* 溝の中心・膝蓋骨・脛骨粗面が一直線に並ぶ配置では、既定の法線が作れないので ``normal`` を渡します。
* ``angleBetween`` の最短回転を使うので、溝の上の回転が180度に近づくと向きが不定になります(膝の可動域では起こりません)。
