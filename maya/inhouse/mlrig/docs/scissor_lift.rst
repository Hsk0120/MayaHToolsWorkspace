シザーリフト(ScissorLift)
==========================

``mlrig.setups.ScissorLift`` は、X字に組んだ同じ長さの腕を何段も重ねたシザーリフト(パンタグラフ)を、
台の高さ1つで動かします。各段の腕は真ん中で交わったまま開閉し、片側の支点は固定、反対側の支点は横へ滑ります。
腕・台・滑る足のワールド行列を出力するので、jointやジオメトリの ``offsetParentMatrix`` へつなぐだけで動きます。
Maya標準ノード(``multiplyDivide`` ・ ``clamp`` ・ ``plusMinusAverage`` ・ ``angleBetween`` ・ ``animBlendNodeAdditiveDA`` ・
``composeMatrix`` ・ ``multMatrix``)だけで組み、独自プラグイン、エクスプレッション、フレームごとのPython、IKは使いません。

.. code-block:: python

   from mlrig.setups import ScissorLift

   lift = ScissorLift.create("liftBase", armLength=6.0, stages=3, height=6.0, name="lift")
   cmds.connectAttr("lift.arm0AMatrix", "arm0A_jnt.offsetParentMatrix")
   cmds.connectAttr("lift.platformMatrix", "platform_jnt.offsetParentMatrix")
   cmds.setAttr("lift.height", 12.0)

``base`` (土台のtransform)のローカルで、固定側の支点を原点、腕が開く向きを +X、持ち上がる向きを +Y とします。
出力の行列はすべて土台の ``worldMatrix`` に追従します。 ``base=None`` ならワールド原点です。

式
--

腕の長さ ``L`` ・段数 ``n`` ・台の高さ ``H`` のとき:

* 1段の高さ ``h = clamp(H / n, 0, L)``
* 滑る側の支点までの距離 ``w = sqrt(L² - h²)`` (三平方の定理。腕の長さは変わらない)
* 腕の角度 ``θ = atan2(h, w)``

k段目(0始まり)の腕Aは ``(0, k·h)`` から ``(w, (k+1)·h)`` へ、腕Bは ``(0, (k+1)·h)`` から ``(w, k·h)`` へ渡り、
2本は腕の長さの半分の点で交わります。腕の行列は固定側(x=0)の端を原点、X=腕の向き(腕Aは +θ、腕Bは -θ 回す)、
Z=土台のZです。台は ``(0, n·h)`` 、滑る足は ``(w, 0)`` と ``(w, n·h)`` に置き、回転は土台と同じです。
``atan2`` は ``angleBetween`` の ``euler`` の Z で求めます。全体を内部単位(cm・radian)で組むので、
UI単位を変えても自動の ``unitConversion`` は入りません。

containerのアトリビュート
-------------------------

.. list-table::
   :header-rows: 1

   * - 名前
     - 内容
   * - ``height``
     - 台の高さ(keyable、既定 ``armLength * stages * 0.5`` = 腕の角度30度)。他のコントロールから接続して駆動できる。
   * - ``armLength``
     - 腕の長さ(keyable)。
   * - ``stageHeight`` ・ ``spread`` ・ ``angle``
     - 1段の高さ ``h`` ・滑る側の距離 ``w`` ・腕の角度 ``θ`` (出力)。
   * - ``arm<k>AMatrix`` ・ ``arm<k>BMatrix``
     - k段目の2本の腕のワールド行列。
   * - ``platformMatrix`` ・ ``baseSliderMatrix`` ・ ``topSliderMatrix``
     - 台・下の滑る足・上の滑る足のワールド行列。

Python版の ``ScissorLift.evaluate(height, armLength, stages)`` は (h, w, θ(度)) を返します。

制限
----

* 腕は全段同じ長さで、交点は腕の真ん中に限ります(交点がずれた腕・段ごとに長さの違う腕は扱わない)。
* 片側の支点が固定の形だけです(両側が中心へ寄る形は、出力に ``-w/2`` の移動を掛けて利用側で作る)。
* 高さが ``n·L`` を超えると腕は垂直で、0未満は水平で止まります(台は ``n·h`` の位置で止まる)。
* ``multiplyDivide`` ・ ``clamp`` は単精度なので、位置の誤差は 1e-5 cm 程度です(腕が垂直に近いほど ``w`` の誤差が増え、
  試験の実測は h=7.9997 で 1.9e-6 cm)。
* 腕の太さ・ピンの径は扱いません。出力の行列は生成時の腕の向きを持たない標準の枠なので、モデルの向きが違う場合は
  利用側でオフセットを掛けます。

試験
----

``mlrig/__tests__/test_setup_scissor_lift.py`` (``setups`` スイート)で、回転・移動した土台の上の3段で、
いろいろな高さに対して腕の両端が段の支点に乗り、2本の腕が中点で交わり、台・滑る足が支点の上にあること(試験側の三平方の独立計算)、
Python版との一致、範囲の端、腕の長さの書き換えと土台への追従、base無しと1段、UI単位 mm/rad、container所有とUndo/Redo、引数を確認します。

参考にした考え方
----------------

* lesterbanks.com の、Joe Rule のシザーアームのリグを紹介する記事(各段の腕に IK チェーンを持たせ、1つのコントロールで全体を動かす)。
* The Rookies に公開された、Mayaの手続き的なシザーリフトの学生作品の解説(1つの LiftHeight アトリビュートから multiplyDivide のノードと直接のつなぎで動かし、競合するコンストレイントを減らして安定させる)。
* Autodesk Forums「Need help rigging scissor like mechanism」(シザー機構は2つの4節リンクを組み合わせた6節リンク)。

ここでは IK を使わず、腕の長さが一定であることから三平方の定理で滑る側の距離を直接求めています。コードの流用はありません。
