目のハイライトのカメラ追従(EyeHighlight)
=========================================

``mlrig.setups.EyeHighlight`` は、目のハイライト(瞳の上の光の映り込み、キャッチライト)の板や補助骨を、
**カメラと光の方向に合わせて眼球の表面の上で動かします**。鏡のような球に写る光の点は、球の中心から見て
カメラへの向きと光への向きのちょうど中間の方向の表面に現れます。テクスチャやシェーダーに描き込んだハイライトは
カメラを回り込んでも目の中の位置が変わらず不自然になりやすいため、ハイライトを別の板(または補助骨)にして
その点へ置き、カメラが動くと眼球の表面に沿って移るようにします。

* 手描き風・アニメ調の目で、ハイライトの板を眼球の表面に乗せてカメラから見た位置に保ちたいとき。
* 実際のライティングとは別に、決めた光の方向からのハイライトを常に目に入れたいとき。
* ハイライトを瞳の中心に固定する(目の回転だけに付いていく)状態との間を ``follow`` で調整したいとき。

眼球の向き(視線)を決める aim のリグや、カメラから見た顔の向きの重みを出す CameraAngleReader、まぶたを
目の回転に付いていかせる EyelidFollow とは別のもので、眼球の回転は入力として使うだけです。
Maya標準ノード(``aimMatrix`` ・ ``vectorProduct`` ・ ``blendColors`` ・ ``multMatrix`` ・ ``blendMatrix`` など)
だけで組み、結果をハイライトの ``offsetParentMatrix`` へ接続します。独自プラグイン、エクスプレッション、
フレームごとのPythonは使いません。生成したノードはcontainerが所有します。

.. code-block:: python

   from mlrig.setups import EyeHighlight

   # 眼球のjointの子のハイライトの板を、カメラと光の中間の向きの表面へ置く。
   highlight = EyeHighlight.create("eye_L_jnt", "shotCam", "eye_L_highlight", name="eyeHighlightL",
                                   light="keyLight", radius=1.05)
   cmds.setAttr("eyeHighlightL.weight", 1.0)   # 作成時は動かない(weight=0)ので上げる
   cmds.setAttr("eyeHighlightL.follow", 0.5)   # 瞳の中心とカメラ・光の向きの間

   # Python版: 同じ式のワールド行列
   EyeHighlight.placement(cmds.getAttr("eye_L_jnt.worldMatrix[0]"), (0, 15, 40), (-30, 40, 20), 1.05)

式
--

ワールド空間で、 ``E`` を眼球(``eye``)の位置、 ``C`` をカメラの位置、 ``Lp`` を光(``light``)の位置とします。

* ``v = normalize(C - E)`` (眼球からカメラへの向き)、 ``l = normalize(Lp - E)`` (光を指定しなければ ``l = v``)。
* ``h = normalize(v + l)`` (カメラと光の中間の向き。Blinn-Phong の反射のモデルの half vector と同じ。
  光を指定しなければ ``h = v`` で、ハイライトは眼球のうちカメラに正対する点に来る)。
* ``F`` = 眼球の ``aimAxis`` のワールドの向き(瞳の中心の向き)。
* ``m = follow · h + (1 - follow) · F`` 。
* 向き ``R``: ``E`` から ``E + m`` へハイライトの ``aimAxis`` を向け、 ``upAxis`` を眼球の ``upAxis`` へ揃える
  (``aimMatrix``)。
* ハイライトのワールド行列 ``M = T(radius · aimAxis) · R · T(E)`` (行ベクトルの書き方)。位置は
  ``E + radius · normalize(m)`` で、ハイライトの ``aimAxis`` は眼球の外向きの法線になります。

``follow=1`` かつ光があるとき、ハイライトの法線 ``h`` はカメラへの向きと光への向きと同じ角度をなします
(鏡の反射の条件)。カメラ・光の位置は眼球の中心から見た向きだけを使うので、眼球の大きさに比べて
十分遠いとみなす近似です。

ハイライトのワールド行列は ``L · OPM · Pw`` (``L`` はローカル行列、 ``Pw`` は親のワールド行列)なので、
``L`` が作成時の値 ``L0`` のときに ``M`` になるよう ``OPM = L0^-1 · M · Pw^-1`` を求め、作成時の
``offsetParentMatrix`` から ``blendMatrix`` で ``weight`` に応じて補間します。 ``Pw^-1`` にはハイライト自身の
``parentInverseMatrix`` (駆動する ``offsetParentMatrix`` を含む)ではなく、親の ``worldInverseMatrix`` を使います。
ハイライトの translate・rotate・scale は空いたままで、作成時から動かした分(板の大きさ・傾きの調整)が
計算した配置の上に上乗せされます。

containerのアトリビュート
-------------------------

.. list-table::
   :header-rows: 1

   * - アトリビュート
     - 内容
   * - ``radius``
     - 眼球の中心からハイライトまでの距離(cm、角膜の半径)。既定は作成時の眼球とハイライトの距離。
   * - ``follow``
     - 0で瞳の中心(眼球の ``aimAxis``)に留まり、1でカメラ・光の中間の向きへ完全に移る。既定は1。
   * - ``weight``
     - 作成時のハイライトの姿勢(0)から計算した配置(1)への補間。既定の0では作成時に動かない。
   * - ``highlightMatrix``
     - 出力。ハイライトのワールド行列 ``M`` 。
   * - ``matrix``
     - 出力。ハイライトの ``offsetParentMatrix`` へ入れる値(``connect=True`` で接続済み)。

制限
----

* 光がカメラのちょうど反対側にある場合と、 ``follow`` の途中の値で ``h`` と ``F`` がちょうど逆向きの場合は、
  向きが決まりません(ハイライトが眼球の裏へ回る配置で、通常は画面に写りません)。
* 角膜のふくらみ・屈折は扱わず、半径 ``radius`` の球の表面として計算します。ハイライトが瞳から外れすぎる場合は
  ``follow`` を下げて瞳の中心へ寄せます。
* ハイライトの ``offsetParentMatrix`` を使うので、ほかの接続と同時には使えません。眼球・カメラ・光は
  ハイライト自身・その子にできません(循環になるため)。
* シェーダー上のハイライト(スペキュラー)とは別のもので、ハイライトの板の見た目(テクスチャ・常に表示する
  設定など)は利用側で用意します。

試験
----

``mlrig/__tests__/test_setup_eye_highlight.py`` (``setups`` スイート)で、回転・非一様なスケールの頭の下の
眼球(joint)の子のハイライトについて、作成時に動かないことと ``radius`` の既定値、頭・眼球・カメラ・光・
``radius`` ・ ``follow`` の乱数25通りで位置・向きが試験側で独立に書いた式と Python版に一致し右手系であること、
光があるときの反射の条件、ハイライト自身の translate・rotate の上乗せ、 ``follow=0`` で目の前に留まり眼球の回転に
付いていくこと、光なしでカメラに正対すること、前・上の軸5通り、weight の補間と connect=False、DG・serial・
parallel の各評価で古い値にならないこと、container所有とUndo/Redo、引数14種で何も残さないことを確認します。

参考にした考え方
----------------

* Wikipedia「Catch light」(目に写る照明の映り込みが表情を生き生きと見せるという撮影の考え方)。
* Wikipedia「Blinn–Phong reflection model」(視線と光の向きの中間の half vector と法線が一致する点で
  鏡面反射が最も強くなる)。
* Blender Studio の「Lighting」(artist guide)にある、手描き風の表現ではハイライトを実際の反射とは別に
  キャラクターのリグから置くことがあるという説明。
* SideFX のフォーラムにある、カメラに付いてくるスペキュラー(ハイライト)の位置決め用のロケーターの話題
  (カメラから見た位置でハイライトを決める考え方)。コードは流用していません。
