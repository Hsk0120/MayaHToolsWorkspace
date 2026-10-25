表面に貼り付くコントロール(StickyControl)
==========================================

``mlrig.setups.StickyControl`` は、コントロールを変形するメッシュ(スキンした顔・体など)の表面に貼り付けて、
表面が動いても同じ場所に付いていく(スティッキーコントロール)仕組みを作ります。フェイシャルの細かいコントロールを
皮膚の上に置く場合などに使います。表面の追従は Maya 標準の ``proximityPin`` (元の形で最も近い点を求め、変形後の形で
同じ点の位置・向きを出す)で行い、 ``multMatrix`` で空間を合わせます。独自プラグイン、エクスプレッション、
フレームごとのPython、follicle は使いません。

.. code-block:: python

   from mlrig.setups import StickyControl

   # スキンした顔のメッシュに、頬のコントロールを貼り付ける
   graph = StickyControl.create("face_geo", "cheek_L_ctrl", name="cheekSticky")
   # コントロール自身が動かすデフォーマーより前の段(skinCluster)の出力に追従させる
   StickyControl.create("face_geo", "lip_L_ctrl", name="lipSticky",
                        geometry="face_skinCluster.outputGeometry[0]")

参考にした考え方
----------------

* crab の ``plugins/components/utilities/sticky_patch.py`` (MIT): 小さな面(パッチ)を下のメッシュと同じウェイトで
  スキンし、その面に置いた follicle の下にコントロールを置くことで、コントロールを変形する表面に追従させる構成。
  パッチは下のメッシュ自体ではなく別の写しなので、コントロール自身の変形を受けない(二重の変形を避ける)。

この部品は、パッチと follicle の代わりに、メッシュの元の形と変形後の形を ``proximityPin`` へ直接渡し、
変形後の形を「コントロール自身が動かすデフォーマーより前の段」の出力にできる引数 ``geometry`` で二重の変形を避けるようにしました。
コードは流用していません。

引数
----

* ``mesh``: 変形するメッシュのtransform。空間はこのtransformの ``worldMatrix`` で扱います。
* ``control``: 貼り付けるコントロールのtransform。生成時の位置(表面から離れていてもよい)で表面の場所を決めます。
* ``original``: 変形前の形のメッシュのシェイプ(またはその親のtransform)。省略すると ``mesh`` の中間シェイプ
  (デフォーマーを付けたときにMayaが作る ``<名前>ShapeOrig`` など)のうち最初のものを使います。
* ``geometry``: 追従する変形後の形のplug(メッシュのオブジェクト空間)。省略すると ``mesh`` の変形後のシェイプの ``outMesh`` 。
* ``connect``: Trueならコントロールの ``offsetParentMatrix`` へ接続します。

計算式
------

生成時のコントロールのワールド行列を ``W0`` 、メッシュの生成時のworldMatrixを ``M0`` 、現在を ``M`` 、
コントロールの生成時のローカル行列を ``L0`` 、親の現在のworldInverseMatrixを ``P^-1`` とします。

* ``proximityPin.inputMatrix[0] = W0 · M0^-1`` (定数。 ``offsetTranslation = offsetOrientation = 1`` で、表面からの離れと向きの差を保つ)
* ``matrix = proximityPin.outputMatrix[0] · D^-1 · M``
* ``offsetParentMatrix = L0^-1 · matrix · P^-1``

``D`` は形のデータ自体が持つ変換行列で、デフォーマーの ``outputGeometry`` を ``geometry`` に渡すと単位行列でないことがあります
(``proximityPin`` の出力にそのまま掛かる)。生成時は出力が入力と一致するはずなので、 ``D = inputMatrix^-1 · 生成時の出力`` を
定数として求めて打ち消します。メッシュが変形していなければ ``matrix = W0`` で、作成時に跳ねません。
コントロールのワールド行列は ``L · L0^-1 · matrix`` になり、コントロールを動かすと表面の上での相対的な操作になります。

containerのアトリビュート
--------------------------

* ``matrix`` : 表面に貼り付いたワールド行列。
* ``offsetParentMatrix`` : コントロールの ``offsetParentMatrix`` へ繋ぐ行列(``connect=True`` なら接続済み)。

制限
----

* コントロール自身の値がメッシュを変形する(コントロールで動かすクラスター・スキンの骨など)場合に、そのメッシュの最終の形
  (``outMesh``)へ貼り付けると、コントロールの移動で表面が動き、さらにコントロールが動く二重の変形になります。
  ``geometry`` にコントロールの変形より前の段の出力を渡してください。
* 表面の場所は生成時に決まり、コントロールを動かしても貼り付く場所は変わりません(表面の上を滑らせる仕組みではありません)。
* ``proximityPin`` は元の形で最も近い点を探すので、元の形を後から変えた場合は作り直してください。
* 向きは ``proximityPin`` の表面の向き(法線・接線)の変化に従います。表面が大きく伸び縮みする場所では、向きの変化がUVの向きに影響されます。

テスト
------

``mlrig/__tests__/test_setup_sticky_control.py`` (``setups`` スイート)で、移動・回転した平面と回した親の下の表面から離れたコントロールについて、
作成直後に跳ねないこと、全頂点を剛体として動かすクラスターで貼り付いた行列が同じ剛体の変換(クラスターの移動・回転から独立に求めた値)に
なること、頂点ごとに重みの違うクラスターで頂点に置いたコントロールがその頂点の変形後の位置へ付いていくこと、変形後のコントロールの相対操作、
``geometry`` に前の段のデフォーマーの出力を渡すと後の段の変形に追従しないこと、親の移動と ``connect=False`` 、所有とUndo/Redo、引数の検査を確かめます。
