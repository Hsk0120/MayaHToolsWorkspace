左右の鏡像の追従(LiveMirror)
=============================

``mlrig.setups.LiveMirror`` は、左右の片側のコントロール(source)のワールド行列を **対称面で鏡に映し**、
反対側のコントロール(target)が **常にその鏡像の姿勢になる** ようにします。左側だけを動かして対称なポーズを
作る「ライブのシンメトリー」や、右側を左側の鏡像へ一時的に追従させてから自分で調整する用途に使います。

* 左右対称のポーズ(構え・待機など)を、片側だけを動かして作りたいとき。
* キャラクターが移動・回転しても、キャラクターのルートの対称面で左右を対称に保ちたいとき。
* 鏡像の上に、反対側だけの差(少しだけ非対称にする)を上乗せしたいとき。
* 鏡像の行列(``mirrorMatrix``)だけを、ほかの計算(ミラーのポーズのコピーの基準など)に使いたいとき。

Maya標準ノード(``multMatrix`` ・ ``blendMatrix``)だけで組み、結果を target の ``offsetParentMatrix`` へ
接続します。target 自身の translate・rotate・scale は空いたままなので、鏡像の上に調整を上乗せできます。
独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。生成したノードはcontainerが所有します。

.. code-block:: python

   from mlrig.setups import LiveMirror

   # 左の手首のコントロールの鏡像を右の手首のコントロールへ。対称面はルートのYZ面。
   mirror = LiveMirror.create("hand_L_ctrl", "hand_R_ctrl", name="handMirror", plane="root_ctrl")
   cmds.setAttr("handMirror.weight", 0.0)   # 追従を切る(右は作成時の姿勢へ戻る)

   # Python版: ワールド行列を鏡に映した行列
   LiveMirror.mirror(cmds.getAttr("hand_L_ctrl.worldMatrix[0]"))

式
--

行列は行ベクトルの書き方(Mayaと同じ、左から右へ掛ける)です。 ``Ws`` を source のワールド行列、 ``P`` を
対称面の空間(``plane``)のワールド行列、 ``S`` を法線の軸(``axis``)だけ -1 の対角行列、 ``F`` を ``flip`` の
軸だけ -1 の対角行列とします。鏡像は

``M = F · Ws · P^-1 · S · P · C``

です。 ``P^-1 · S · P`` は対称面での反射で、点 ``p`` を ``p - 2((p - o)·n)n`` (``o`` は面の原点、 ``n`` は
単位法線)へ、軸のベクトル ``a`` を ``a - 2(a·n)n`` へ映します。 ``P = Sp · Rp · Tp`` (剪断なし)なら、
対角行列どうしは交換できるので ``Sp`` は打ち消し合い、 ``plane`` のスケールは結果に影響しません。

反射だけでは軸が左手系になる(行列式が -1)ので、 ``F`` で局所の軸の向きを反転して右手系へ戻します。

* ``flip="behavior"`` (既定): 3軸すべてを反転。左右を Maya の Mirror Joint の Behavior で作った場合と同じで、
  左右の同じ回転の値が鏡の動き(両腕を同時に前へ、など)になる向きです。子の位置は局所で符号が反転します。
* ``flip="x"`` ・ ``"y"`` ・ ``"z"``: その1軸だけを反転(左右の向きを Orientation に近い形で作った場合)。

``C`` は ``maintainOffset=True`` のときの定数 ``M0^-1 · Wt0`` (作成時の鏡像と target のずれ)で、既定では
単位行列(厳密な鏡像)です。

target のワールド行列は ``L · OPM · Pw`` (``L`` は target のローカル行列、 ``Pw`` は親のワールド行列)です。
``L`` が作成時の値 ``L0`` のときに ``M`` になるよう

``OPM = L0^-1 · M · Pw^-1``

を求め、作成時の ``offsetParentMatrix`` (定数)から ``blendMatrix`` で ``weight`` に応じて補間し、
target の ``offsetParentMatrix`` へ接続します。weight=1 では target のワールド行列は ``(L · L0^-1) · M`` で、
target の translate・rotate を作成時から動かした分が鏡像の上に上乗せされます。

containerのアトリビュート
-------------------------

.. list-table::
   :header-rows: 1

   * - 名前
     - 内容
   * - ``weight``
     - 作成時の ``offsetParentMatrix`` (0)から鏡像(1)への補間(keyable、0〜1)。既定は1。
   * - ``mirrorMatrix``
     - 鏡像のワールド行列 ``M`` (出力)。
   * - ``matrix``
     - target の ``offsetParentMatrix`` へ入れる値(出力)。 ``connect=False`` では接続せず、この値だけを出力します。

制限
----

* 作成時に target が鏡像の位置に無い場合、 ``maintainOffset=False`` と ``weight=1`` では作成直後に鏡像へ
  移ります(厳密な鏡像にするため)。作成時に動かしたくない場合は ``weight=0`` で作ってから上げるか、
  ``maintainOffset=True`` にします。
* ``plane`` の剪断(回転した親の下の非一様なスケール)は扱いません(面が歪みます)。
* source が非一様なスケールの親の下にある場合、鏡像に剪断が含まれ、 ``blendMatrix`` の補間(weight が0と1の
  間)では剪断が保たれません。weight=1 では剪断も含めて鏡像と一致します。
* target がjointで ``segmentScaleCompensate`` で親のスケールを打ち消す場合、作成後に親のスケールを変えると
  ``L0`` が変わるため、親のスケールは作成時のまま使います。
* target の ``offsetParentMatrix`` を使うので、ほかの接続(空間の切り替えなど)と同時には使えません。
  target の親の下で使う空間の切り替えは target の親側に置きます。
* source と対称面は target 自身・その子にできません(循環になるため)。中央のコントロールを自分自身へ映す使い方は
  対象外です。

試験
----

``mlrig/__tests__/test_setup_live_mirror.py`` (``setups`` スイート)で、回転・移動・スケールした対称面、
非一様なスケールの親の下の source、回転・非一様なスケールの親の下で jointOrient を持つ target(joint)について、
maintainOffset・weight=0・厳密な鏡像の位置からの作成で動かないこと、乱数20姿勢(スケールを含む)と
軸3種 × flip 4種で鏡像が試験側で独立に書いた反射の式(点と軸のベクトルの反射)と一致し右手系であること、
対称面を動かしても鏡像が保たれ target 自身の回転・移動が上乗せされること、weight の補間と connect=False、
Python版 ``mirror()`` と ``mirrorMatrix`` の一致、container所有とUndo/Redo、引数12種で何も残さないことを確認します。

参考にした考え方
----------------

* mGear の ``anim_utils`` のミラーポーズ(MIT。コントロールごとに反転するチャンネルを持ち、左右の
  コントロールの値をPythonで写す操作)。こちらはその操作をリグの中の行列の計算(常に追従する形)にしたもので、
  コードは流用していません。
* Maya の Mirror Joint の Behavior と Orientation の考え方(反射したあとに局所の軸を反転して右手系へ戻す)。
* 対称面での反射の行列 ``P^-1 · S · P`` は、点と平面の一般的な反射の式です。
