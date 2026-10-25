腰の振りと上体の安定化(HipSwing)
=================================

``mlrig.setups.HipSwing`` は、**振りのコントロールの回転で腰(骨盤)だけを支点の周りに振り、背骨の根元から上
(上体)の向きを保ちます**。歩きの腰の回転やダンスの腰の振りを付けるとき、腰を回すたびに上体のコントロールを
逆に回して打ち消す必要がありません。オートリグで一般的な「腰の振り(hip swing)」のコントロールの考え方です。

* 上体を傾けずに、腰だけを左右・前後に振りたいとき(歩き・走りの腰の回転、ダンスの腰の振り)。
* 腰の振りの支点を、腰の関節ではなく背骨の根元(へその辺り)に置きたいとき。
* 上体を腰と一緒に回すか(普通の親子)、向きを保つかを割合で切り替えたいとき。

1関節の回転を割合で伝える RotationFollow、首と頭へ回転を分ける NeckHeadSplit、空間を混ぜる SpaceBlend とは
別のもので、こちらは1つのコントロールの回転を「腰には加え、上体からは打ち消す」組み合わせを1つの式で出します。
Maya標準ノード(``multMatrix`` ・ ``pickMatrix`` ・ ``blendMatrix`` ・ ``composeMatrix`` ・ ``multiplyDivide``)だけで組みます。
独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。生成したノードはcontainerが所有します。

.. code-block:: python

   from mlrig.setups import HipSwing

   # 腰と背骨の根元の入力(COG の下の腰のjointなど)と、背骨の根元の位置に置いた振りのコントロール。
   swing = HipSwing.create("hips_jnt", "spine01_jnt", "hipSwing_ctrl", name="hipSwing")
   # 出力は受け側へつなぐ(入力のノードへはつながない)。
   cmds.connectAttr("hipSwing.hipsMatrix", "pelvis_driven.offsetParentMatrix")
   cmds.connectAttr("hipSwing.spineMatrix", "spine01_driven.offsetParentMatrix")

   # Python版: 同じ式のワールド行列
   HipSwing.matrices(hips, spine, control, controlLocal)["spine"]

胸・首など背骨の根元より上のノードは、背骨の根元の出力の子にするか、ワールド行列に ``spineOffset`` を右から
掛けると、上体全体が同じように動きます。

式
--

ワールド空間、行ベクトルの書き方です。 ``L`` を振りのコントロールの局所の行列( ``matrix`` )、 ``Wc`` をその
ワールド行列、 ``T`` をその ``translate`` の平行移動とします。

* 振りの支点の枠 ``Q = T · L^-1 · Wc`` (コントロールの位置で、 rotate が0のときのワールド行列)。
  ``Q^-1 = Wc^-1 · L · T^-1`` で、逆行列のノード(``inverseMatrix`` はプラグインのノード)を使わずに求めます。
* ``R`` = ``L`` の回転だけ(``pickMatrix``)、 ``Ra = slerp(単位行列, R, swing)`` (``blendMatrix``)。
* 振りのワールドの差 ``S = Q^-1 · Ra · Q`` 。支点の点は ``S`` で動きません。
* 腰の出力 ``hipsMatrix = H · S`` (``H`` は腰の入力のワールド行列)。
* 背骨の根元: 腰と一緒に回した ``B · S`` の位置はそのまま、回転・scale・shear だけを ``stabilize`` の割合で
  元の ``B`` へ戻します(``blendMatrix`` の ``translateWeight`` を0)。
  ``spineMatrix = blend(B · S, B, stabilize)`` 、 ``spineOffset = B^-1 · spineMatrix`` 。

``stabilize = 1`` では上体の向きは元のままで、背骨の根元の位置だけが支点の周りを回った分ずれます(支点を背骨の
根元に置けば、上体はまったく動きません)。 ``stabilize = 0`` では上体も腰と一緒に回ります。コントロールの rotate が
0(または ``swing = 0``)のとき、出力は入力と同じです(作成時に跳ねない)。時刻・前の結果を使わないので、
どのフレームでも同じ入力から同じ値になります。

containerのアトリビュート
-------------------------

.. list-table::
   :header-rows: 1

   * - アトリビュート
     - 内容
   * - ``swing``
     - 振りの割合(0〜1)。既定は1。
   * - ``stabilize``
     - 上体の向きを保つ割合(0〜1)。1で上体は傾かず、0で腰と一緒に回る。既定は1。
   * - ``swingMatrix``
     - 出力。振りのワールドの差 ``S`` 。
   * - ``hipsMatrix`` ・ ``spineMatrix``
     - 出力。振った腰と、安定化した背骨の根元のワールド行列。
   * - ``spineOffset``
     - 出力。背骨の根元より上のノードのワールド行列へ右から掛ける差。

制限
----

* 振りに使うのはコントロールの rotate だけです。支点はコントロールの位置( ``translate`` を含む)で、
  コントロールとその親の scale は1、 ``rotatePivot`` 等は0を前提にします(scale が不均一だと ``S`` が剛体の
  回転になりません)。
* ``swing`` ・ ``stabilize`` の途中の値は四元数の補間(短い方の回り)です。180度を超える振りは扱いません。
* 出力は入力のノードへはつなぎません(入力を書き換えると循環します)。受け側の ``offsetParentMatrix`` へ入れる
  場合は、受け側の親が動くなら親の ``worldInverseMatrix`` を掛けてからつなぎます。
* 脚(股関節から下)は腰の出力の子として一緒に振れます。足を地面に残す場合は、足のIKのハンドルを腰と別の
  空間に置きます。

試験
----

``mlrig/__tests__/test_setup_hip_swing.py`` (``setups`` スイート)で、回転・移動した COG の下の腰・背骨の根元・胸と、
offsetParentMatrix を持つ振りのコントロールについて、作成直後に出力が入力と同じこと、COG・腰・コントロールの
位置と回転・回転の順序の乱数25通りで、試験側で支点の枠とオイラー角から独立に組んだ ``S`` と一致し、支点が
動かないこと、背骨の根元の位置が ``B · S`` で向きが元のままのこと、胸に ``spineOffset`` を掛けると向きが変わらず
根元と同じだけ平行に動くこと、Python版との一致、 ``swing=0.5`` で振りの角度が半分・ ``stabilize`` の0と0.5、
DG・serial・parallel の各評価、UI単位 mm・rad で自動の単位変換の係数が1のこと、container所有と入力へ接続
しないこと・Undo/Redo、引数9種で何も残さないことを確認します。

参考にした考え方
----------------

* AdvancedSkeleton の HipSwinger(腰を振るコントロールで、上体の向きを保つ安定化の割合を持つ)と、
  rigamajig2 の背骨のコンポーネントの hip swing のコントロール(腰の振りの支点を別に持つ)の考え方。
  どちらもコードは流用していません(rigamajig2 はライセンス表記なし、AdvancedSkeleton は独自のライセンス)。
  こちらは階層・拘束ではなく、支点の枠で見た回転の差 ``S`` を腰に掛け、背骨の根元からは回転だけを戻す行列の式で組みます。
