仮想のFK階層(VirtualChain)
==========================

``mlrig.setups.VirtualChain`` は、親子にせず同じ親の下に兄弟として並べたコントロールを、
**前のコントロールの子のように** 動かします。根元のコントロールを回すと先のコントロールがすべて付いてくるFKの
動きになりますが、アウトライナー上の階層は平らなままです。

* 書き出し・ゲームエンジン・別のリグとの受け渡しのために、コントロールやjointを親子にしたくないとき。
* 1本の尻尾・髪・紐のコントロールを、あとから「FKとしても使える」ようにしたいとき。
* つなぎごとに追従を切り替えたいとき(``follow<i>`` を0にすると、そのコントロールは前を追わない)。

Maya標準ノード(``multMatrix`` ・ ``blendMatrix``)だけで組み、コントロールの ``offsetParentMatrix`` へ
接続します。独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。生成したノードはcontainerが所有し、
作成時にコントロールの姿勢は変わりません。

.. code-block:: python

   from mlrig.setups import VirtualChain

   chain = VirtualChain.create(["tail0_ctrl", "tail1_ctrl", "tail2_ctrl", "tail3_ctrl"], name="tailChain")
   cmds.setAttr("tailChain.follow2", 0)  # tail2 だけ tail1 を追わない(tail3 は tail2 を追い続ける)
   chain.getControls()                   # 根元から先の順のコントロール

式
--

行列は行ベクトルの書き方(Mayaと同じ、左から右へ掛ける)です。i番目のコントロールについて、
``M_i`` を自分の局所行列(translate・rotate・scale)、 ``O_i`` を ``offsetParentMatrix`` 、
``P_i`` を実際の親のワールド行列(親が無ければ単位行列)、 ``W_i = M_i · O_i · P_i`` をワールド行列とします。

作成時に、前のコントロールに対する関係 ``K_i = O_i · P_i · W_(i-1)^-1`` (作成時の値)を固定し、

``O_i = K_i · W_(i-1) · P_i^-1``

を ``multMatrix`` で求めて ``offsetParentMatrix`` へ接続します。すると ``W_i = M_i · K_i · W_(i-1)`` となり、
本物の親子の階層(``W_i = M_i · (作成時の局所の関係) · W_(i-1)``)と同じになります。前のコントロールの移動・回転・
スケールが、後ろのすべてへ順に伝わります。実際の親(全体の親)を動かすと、全体がその分だけ1回動きます
(``W_(i-1)`` と ``P_i^-1`` で親の分が打ち消し合うので、二重に掛かりません)。

``follow<i>`` は ``blendMatrix`` のウェイトで、0 は作成時の ``O_i`` (前を追わない)、1 は上の式です。
途中の値は ``blendMatrix`` が行列を移動・回転・スケール・剪断に分けて混ぜます。

containerのアトリビュート
-------------------------

.. list-table::
   :header-rows: 1

   * - 名前
     - 内容
   * - ``follow1`` 〜 ``follow<n-1>``
     - i番目のコントロールが i-1番目を追う割合(keyable、0〜1、既定1)。根元(0番目)には無い。
   * - ``controls``
     - コントロールの ``message`` を受ける配列。 ``getControls()`` が読みます(改名しても辿れる)。

制限
----

* Mayaの ``parentMatrix`` ・ ``parentInverseMatrix`` はコントロール自身の ``offsetParentMatrix`` を含むため、
  実際の親のノードの ``worldMatrix`` ・ ``worldInverseMatrix`` を使います。作成後にコントロールを別の親へ
  移すと式が合わなくなるので、作り直します。
* コントロールの ``offsetParentMatrix`` (根元以外)は接続済みであってはいけません。互いに親子・先祖の関係にある
  コントロールと、インスタンスは扱いません(循環や二重の変換になるため)。
* ``follow`` の途中の値は ``blendMatrix`` の成分ごとの補間で、位置は円弧ではありません。0か1で使うのが基本です。
* 行列の積の丸めにより、位置の誤差は 1e-9 cm 程度です(試験の許容は 1e-6)。

試験
----

``mlrig/__tests__/test_setup_virtual_chain.py`` (``setups`` スイート)で、回転した親の下の3つのコントロールについて、
作成直後に姿勢が変わらないこと、乱数の姿勢で各ワールド行列が試験側で独立に書いた式と一致すること、
本物の親子に組んだ複製へ同じ局所の変化を入れたときと一致すること、 ``follow`` を0にしたつなぎと中間の値、
実際の親を動かすと全体が1回だけ動くこと、container所有とUndo/Redo、引数を確認します。

参考にした考え方
----------------

* モジュラーリグのフレームワーク mikan(MIT)の ``rig.rechain`` の考え方(切り離された・拘束されたノードの上に、
  仮想のFK階層を作る)。コードは流用せず、ここでは1つの ``multMatrix`` と ``blendMatrix`` で各つなぎを組んでいます。
* リグのコントロールを ``offsetParentMatrix`` で親の変換に追従させる、行列による親子の一般的な組み方。
