全身の重心(CenterOfMass)
========================

``mlrig.setups.CenterOfMass`` は、体節(上腕・前腕・太ももなど)ごとの **質量の割合** と **重心の位置** から、
**全身の重心(COM)** と、その **床への投影**、 **支え(足)の中心からのずれ** を求めます。
アニメーターが姿勢の重さの乗り方(バランス)を確かめる目安として使います。

* 歩き・走り・ジャンプで、重心の軌跡が自然な形(放物線・左右の揺れ)になっているか確かめたいとき。
* 立ちポーズで、重心の床への投影が両足の間(支えの範囲)に入っているか確かめたいとき。
* 重心の位置を、エクスポート用の骨やゲームエンジン側の確認用の点として出力したいとき。

Maya標準ノード(``wtAddMatrix`` ・ ``plusMinusAverage`` ・ ``multiplyDivide`` ・ ``reverse`` ・ ``clamp`` ・
``decomposeMatrix`` ・ ``composeMatrix`` ・ ``distanceBetween``)だけで組み、containerの行列のアトリビュートへ
出力します。独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。時刻や前のフレームの結果を
使わないので、どのフレームでも同じ姿勢からは同じ値になります。生成したノードはcontainerが所有します。

.. code-block:: python

   from mlrig.setups import CenterOfMass

   table = CenterOfMass.DEMPSTER          # 一般的な人体の体節の表 (質量の割合, 重心の位置の割合)
   segments = [
       dict(start="pelvis_jnt", end="chest_jnt", mass=table["trunk"][0], ratio=table["trunk"][1]),
       dict(start="upperArm_L", end="elbow_L", mass=table["upperArm"][0], ratio=table["upperArm"][1]),
       # …残りの体節
       dict(start="prop_jnt", mass=0.05),  # 先が無い体節は、その点に質量を置く
   ]
   com = CenterOfMass.create(segments, name="com", support=["ankle_L", "ankle_R"])
   cmds.connectAttr("com.centerMatrix", "com_out.offsetParentMatrix")  # ワールドの親の下の受け側joint
   cmds.connectAttr("com.groundMatrix", "comFloor_out.offsetParentMatrix")
   cmds.getAttr("com.balance")                                          # 両足首の中点からの床の上の距離

式
--

体節 i の根元と先のワールド位置を ``s_i`` ・ ``e_i`` 、 ``r_i`` を ``ratio<i>`` 、 ``m_i`` を ``mass<i>`` とします。
体節の重心の点と全身の重心は

``p_i = (1 - r_i) · s_i + r_i · e_i`` (先が無い体節は ``p_i = s_i``)

``c = Σ m_i · p_i / M`` ( ``M = Σ m_i`` )

です。 ``wtAddMatrix`` で根元と先のノードの worldMatrix を重み ``m_i (1 - r_i) / M`` ・ ``m_i r_i / M`` で足すと、
行列の位置の行は重みの線形和なので、和の位置がそのまま ``c`` になります(和の回転・スケールの部分は使わず、
``decomposeMatrix`` で位置だけを取り出します)。重みは ``multiplyDivide`` で求め、 ``M`` は ``plusMinusAverage`` で
足した合計に ``clamp`` で下限 1e-6 を設けて0除算を避けます。質量は相対値でよく、合計が1でなくても構いません。

床への投影は、ワールドの上方向(Y)に沿って ``groundHeight`` の高さへ落とした点 ``(c.x, groundHeight, c.z)`` です。
支え(``support``)を渡すと、支えのノードの位置の平均を同じく床へ落とした点と、床の上での重心との距離
``balance = |(c.x, c.z) - (支えの中心.x, 支えの中心.z)|`` も出力します。

人体の体節の表 ``CenterOfMass.DEMPSTER`` は、生体力学で広く使われる Dempster の値(体重に対する質量の割合と、
根元から先へ向けた重心の位置の割合)です。 ``headNeck`` は首の根元から耳の高さ、 ``trunk`` は股関節から肩まで、
``foot`` はかかと(足首)からつま先までを1つの体節とします。左右の腕・脚を2回数えると割合の合計は1になります。

containerのアトリビュート
-------------------------

.. list-table::
   :header-rows: 1

   * - 名前
     - 内容
   * - ``mass0`` 〜 ``mass<n-1>``
     - 体節ごとの質量(keyable、0以上の相対値)。小道具を持たせる・体型を変えるときに値を変えられます。
   * - ``ratio<i>``
     - 体節の根元から先へ向けた重心の位置の割合(keyable、0〜1)。先を渡した体節だけに作ります。
   * - ``groundHeight``
     - 床のワールドY座標(keyable)。
   * - ``totalMass``
     - 質量の合計(出力)。
   * - ``centerMatrix``
     - 位置が全身の重心で、向きが単位のワールド行列(出力)。
   * - ``groundMatrix``
     - 重心を床へ落とした点のワールド行列(出力)。
   * - ``supportMatrix`` ・ ``balance``
     - 支えの中心を床へ落とした点のワールド行列と、床の上での重心との距離(出力、 ``support`` を渡した場合)。

制限
----

* 体節は点の質量として扱い、形・慣性(回転のしにくさ)は扱いません。体節の重心は根元と先を結ぶ線分の上に置きます。
* 床はワールドのY軸に垂直な平面です。傾いた床・段差は ``groundHeight`` をキーで変えるか、別のリグで扱います。
* ``balance`` は支えの点の平均からの距離で、足の裏の輪郭(支えの多角形)の内外の判定はしません。
* すべての質量を0にすると重みがすべて0になり、重心はワールドの原点になります。

試験
----

``mlrig/__tests__/test_setup_center_of_mass.py`` (``setups`` スイート)で、回転・移動・非一様スケールした親の下の
体節(先のある3つ、先の無い1つ)と2つの支えについて、作成直後と乱数の姿勢10通りで、重心・床の点・支えの中心・
``balance`` が試験側で各ノードのワールド位置から独立に計算した値と一致すること(許容 1e-6)、出力の向きが単位で
あること、質量・割合・床の高さを変えた場合と1つの体節だけに質量がある場合、Python版 ``center()`` との一致、
人体の表の合計、支えを渡さない場合、container所有とUndo/Redo、引数を確認します。

参考にした考え方
----------------

* gt-tools (MIT) のオートリグの重心の参照モジュール(体節ごとの点を体節の質量の割合で重み付けした
  pointConstraint で重心を求め、床へ落とした点を作る考え方)。コードは流用していません(こちらは拘束を使わず
  ``wtAddMatrix`` の重みで計算し、重みと支えとの距離をDGで求めます)。
* Winter「Biomechanics and Motor Control of Human Movement」の体節パラメーターの表(Dempster の値)と、
  体節の重心の加重平均で全身の重心を求める生体力学の一般的な方法。
