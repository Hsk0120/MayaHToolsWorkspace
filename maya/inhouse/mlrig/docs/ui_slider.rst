枠の中のスライダー(UiSlider)
============================

``mlrig.setups.UiSlider`` は、フェイシャルのUIパネルなどで使う、枠の中だけを動くスライダーのコントロールから、
正規化した位置と、方向ごと・角ごとの0〜1の重みを出す仕組みを作ります。コントロールの移動は Maya の transformLimits で枠の中に止め、
出力は数値だけなので、補正シェイプ(blendShapeの重み)・ドリブンキーなどの入力へ繋いで使います。
Maya標準ノード(``unitConversion`` ・ ``plusMinusAverage`` ・ ``multiplyDivide`` ・ ``clamp``)だけで組み、
独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import UiSlider

   # 上下左右に動く2次元のスライダー(枠の半分の幅が2cm)
   graph = UiSlider.create("mouth_slider_ctrl", name="mouthSlider", size=2.0)
   # 上だけに動く1次元のスライダー
   UiSlider.create("brow_slider_ctrl", name="browSlider", size=1.0, rangeX=(0, 0), rangeY=(0, 1))
   owner = graph.container
   # owner.upRight などを blendShape の重みへ繋ぐ

参考にした考え方
----------------

* mGear の ``shifter_classic_components/ui_slider_01`` (MIT): 枠(参照表示の正方形)とその中のコントロールを置き、
  横・縦それぞれ正の向き・負の向きを使うかの設定から、コントロールの ``translateX`` ・ ``translateY`` を
  transformLimits で -1〜0〜1 の範囲に制限し、ほかのチャンネルをkeyableから外す構成。

この部品は、範囲の制限に加えて、移動量を ``size`` で正規化した位置と、正負へ分けた方向の重み・角の重み(双一次の積)を
DGで計算して container へ出力するようにしました。コードは流用していません。

引数
----

* ``control``: スライダーとして動かすtransform。生成時の位置を中心(0, 0)とします。枠の形はサンプルのように別のtransformへ作ります。
* ``size``: 正規化の1に当たる移動量(内部の単位cm)。
* ``rangeX`` ・ ``rangeY``: 横・縦の範囲 ``(min, max)`` 。minは-1〜0、maxは0〜1。 ``(0, 0)`` でその軸は動かしません(片方は動く必要があります)。
* ``limit``: Trueならコントロールの移動を transformLimits(``minTransXLimit`` 等)で範囲内に止め、Zは生成時の位置に固定します。
* ``lockChannels``: Trueなら使わないチャンネル(``translateZ`` ・回転・スケール、範囲が0の軸)をkeyableから外します。

計算式
------

生成時のコントロールの位置 ``(X0, Y0)`` を定数として持ち、移動量は係数1の ``unitConversion`` で内部の単位(cm)のまま読みます
(UIの長さの単位によらず同じ結果)。

* ``x = clamp((translateX - X0) / size, rangeX)`` 、 ``y = clamp((translateY - Y0) / size, rangeY)``
* ``right = clamp(x, 0, 1)`` 、 ``left = clamp(-x, 0, 1)`` 、 ``up = clamp(y, 0, 1)`` 、 ``down = clamp(-y, 0, 1)``
* ``upRight = up * right`` 、 ``upLeft = up * left`` 、 ``downRight = down * right`` 、 ``downLeft = down * left``

作成直後(生成時の位置)は全ての出力が0です。transformLimits を切っても、出力は範囲へclampします。
Python版の式は :meth:`UiSlider.weights` です。

containerのアトリビュート
--------------------------

* ``size`` ・ ``rangeX`` ・ ``rangeY`` : 生成時の定数(読み取り用。変えても transformLimits は変わりません)。
* ``x`` ・ ``y`` : 正規化した位置。
* ``right`` ・ ``left`` ・ ``up`` ・ ``down`` : 方向ごとの重み(0〜1)。
* ``upRight`` ・ ``upLeft`` ・ ``downRight`` ・ ``downLeft`` : 角の重み(0〜1)。

制限
----

* 枠は正方形の範囲(縦横とも同じ ``size``)で、円形の範囲や任意の形には対応しません。
* 角の重みは方向の重みの積なので、 ``right`` と ``upRight`` は同時に値を持ちます(辺と角の補正を重ねる場合は、
  補正シェイプ側で辺の分を差し引く作り方にします)。
* ``size`` ・範囲を後から変える場合は作り直してください(transformLimits は生成時に設定します)。
* コントロールの親の空間の ``translate`` を読むので、枠ごとパネルを動かしても出力は変わりません。

テスト
------

``mlrig/__tests__/test_setup_ui_slider.py`` (``setups`` スイート)で、回した枠の下の原点から離れた位置のコントロールについて、
作成直後に全ての出力が0であること、制限を切って範囲の外を含む格子の各位置へ動かしたときに位置・方向・角の重みが
Pythonで独立に求めた値と一致すること、transformLimits の値と有効化・枠の外へ出ないこと、片側だけ・1軸だけの範囲、
使わないチャンネルのkeyable、UI単位(mm)、所有とUndo/Redo(制限・keyableも戻る)、引数の検査を確かめます。
