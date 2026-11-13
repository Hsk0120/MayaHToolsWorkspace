入れ子の筒が伸びる多段シリンダー(TelescopicCylinder)
=======================================================

``mlrig.setups.TelescopicCylinder`` は、ダンプトラックの荷台やクレーンのブームに使われる多段シリンダーの
バレル(外側の筒)と各段の行列を作ります。取り付け位置から先端までの距離から閉じた長さを引いた伸びを、
入れ子の各段へ分けます。分け方は ``sequence`` で切り替えます。

* ``sequence = 1``: 単動式のシリンダーのように、外側の大きい段から順に伸び切ってから次の段が伸びます。
* ``sequence = 0``: 同期式のように、全段が行程の比で同時に伸びます。
* 中間の値は両者の線形補間です。どの値でも各段の伸びの合計は全体の伸びと同じなので、先端は届いたままです。

:doc:`piston` は1段(シリンダーとロッド)の場合です。
Maya標準ノード(``decomposeMatrix`` ・ ``pickMatrix`` ・ ``vectorProduct`` ・ ``plusMinusAverage`` ・
``multiplyDivide`` ・ ``clamp`` ・ ``blendTwoAttr`` ・ ``angleBetween`` ・ ``composeMatrix`` ・ ``multMatrix``)だけで組み、
独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import TelescopicCylinder

   setup = TelescopicCylinder.create("bedHinge_jnt", "bedLift_loc", name="dumpCylinder", stages=3,
                                     axis="x", stroke=[40.0, 38.0, 36.0])
   owner = setup.container
   # 出力はワールド行列。原点にある親の下の、TRSがidentityのtransformで受ける
   owner.getPlug("matrix")[0].connectTo("barrel_drv.offsetParentMatrix")
   for index in range(1, 4):
       owner.getPlug("matrix")[index].connectTo("stage{}_drv.offsetParentMatrix".format(index))

``base`` は取り付け位置(バレルの回転中心)のtransformで、 ``axis`` を閉じた筒の向きにします。
``tip`` は先端(最後の段の端)の位置で、位置だけを使います。各段のモデルは、閉じたときに ``base`` の位置へ
重なる点を原点にして作ります(全段が縮むと全段の原点が ``base`` に重なります)。

参考にした考え方
----------------

* 単動式の多段シリンダーは、油圧で大きい段から小さい段の順に伸び、縮むと入れ子へ戻ります
  (`Telescoping cylinders go the extra distance <https://www.hydraulicspneumatics.com/200/TechZone/Cylinders/Article/False/21653/TechZone-Cylinders>`_ 、
  `How telescopic cylinders work <https://www.mfgrobots.com/Article/repair/31112.html>`_)。
* 全段が同時に伸びる同期式の設計もあります
  (`Telescopic cylinder <https://www.doc.surf/wiki/telescopic-cylinder>`_)。

いずれもコードは流用していません。

引数
----

* ``base``: 取り付け位置のtransform。
* ``tip``: 先端の位置を表すtransform(位置だけを使う)。
* ``stages``: 伸びる段の数(1〜16)。バレルは含みません。
* ``axis``: 筒の軸の向き(``"x"`` ・ ``"y"`` ・ ``"z"``)。
* ``closedLength``: 全段が縮んだときの ``base`` から ``tip`` までの距離(cm)。 ``None`` なら生成時の距離です
  (生成時は全段が縮んだ状態)。
* ``stroke``: 各段の行程(cm)。数値なら全段同じ、列なら外側の段から順。 ``None`` なら ``0.9 × closedLength`` 。
* ``sequence``: 0〜1の分け方(上記)。

container の ``closedLength`` ・ ``sequence`` ・ ``stageStroke[]`` は後から変更できます。

計算式
------

``H`` を ``base`` の位置、 ``R`` をそのワールド行列の回転(scale・shear・平行移動を除く)、 ``u`` を ``R`` で
回した ``axis`` の向き、 ``W`` を ``tip`` の位置、 ``s_k`` を外側から ``k`` 番目の段の行程とします。

1. ``D = |W - H|`` 、 ``v = normalize(W - H)`` 。
2. ``E = D - closedLength`` 、 ``total = clamp(E, 0, Σs)`` 、 ``overExtension = E - total``
   (伸びすぎは正、閉じた長さより縮めると負)。
3. 順番の伸び ``o_k = clamp(total - Σ_{j<k} s_j, 0, s_k)`` 、均等の伸び ``g_k = total × s_k / Σs`` 。
4. ``stageExtension[k] = g_k + sequence × (o_k - g_k)`` 。
5. ``matrix[0]`` (バレル)の位置は ``H`` 、 ``matrix[k]`` (k = 1〜stages)の位置は
   ``H + v × Σ_{j<k} stageExtension[j]`` 、 ``tipMatrix`` の位置は ``H + v × (closedLength + total)`` 。
6. 向きはいずれも ``R × Q(u→v)`` です。 ``Q(p→q)`` は ``p`` を ``q`` へ回す最短の回転(``angleBetween`` の
   ``euler``)で、 :doc:`tripod_joint` と同じです。 ``bendAngle`` は ``u`` と ``v`` のなす角です。

範囲の中では ``tipMatrix`` の位置が ``W`` と一致します。範囲を超えると全段が伸び切った(または縮み切った)まま
止まり、 ``tipMatrix`` は ``W`` へ届きません。 ``overExtension`` は警告の表示や補正シェイプのドライバーに使えます。
Pythonの ``TelescopicCylinder.extensionsOf(E, strokes, sequence)`` は手順2〜4の各段の伸びを返します。

出力
----

* ``matrix[0]``: バレルのワールド行列。 ``axis`` が先端を向き、scaleは1。
* ``matrix[k]``: 外側から ``k`` 番目の段のワールド行列(同じ向き)。
* ``tipMatrix``: 最後の段の端(先端)のワールド行列。
* ``stageExtension[k]``: 各段の伸び(cm、外側から順、 ``k`` は0から)。
* ``length``: ``base`` から ``tip`` までの距離 ``D`` (cm)。
* ``extension``: 全段の伸びの合計 ``total`` (cm)。
* ``overExtension``: 範囲を超えた量(cm)。
* ``bendAngle``: ``base`` の軸と筒のなす角(度)。

長さはすべてcmです。UIの長さ単位がmmなどでも、内部単位のまま計算します(Mayaが挿入する単位変換の係数を1にします)。

制限
----

* 伸びる順番と縮む順番は同じです(実物の単動式は小さい段から戻ることがありますが、標準ノードでは
  動きの向きの履歴を持てません)。必要なら ``sequence`` をキーで切り替えます。
* 範囲の端は硬い止まりです。段ごとの柔らかい止まりはありません。
* 圧力・速度・重さによる力学は扱いません。
* 筒の向きが ``u`` と逆向き(180度)では最短の回転の軸が決まりません。
* 出力はワールド行列です。原点以外の親の下へ接続すると二重変換になります。

テスト
------

``mlrig/__tests__/unit/setups/test_telescopicCylinder.py`` (``setups`` スイート)で、既定値、順番・均等・中間の分配と
Pythonの式・ ``extensionsOf`` との一致、曲げた位置での各段の位置・向き(OpenMayaの最短の回転)・曲げ角、
伸びすぎ・縮みすぎ、 ``closedLength`` ・ ``stageStroke`` の変更、別の軸と親の回転・scale、UIの長さ単位mm、
containerの所有とUndo/Redo、引数の検査を確認します。Maya 2027で確認しています。

検証動画
--------

``tools/demo_telescopic_cylinder.py`` は、新規シーンに取り付け(赤)、3段のシリンダー(バレルと各段を緑の濃淡)、
先端(黄)を作り、先端を持ち上げながら、式と毎フレームの ``D`` ・ ``E`` ・各段の伸び・ ``overExtension`` を
HUDに表示して録画します。順番に伸びる→縮む→均等に伸びる→行程を超える→範囲へ戻る→閉じた位置への復帰を
記録し、各フレームで各段の伸び・位置が式と一致することを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを
``latest-telescopic-cylinder.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_telescopic_cylinder.py --launch
