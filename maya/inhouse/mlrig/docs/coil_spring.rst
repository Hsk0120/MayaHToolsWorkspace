コイルばね(CoilSpring)
======================

``mlrig.setups.CoilSpring`` は、サスペンションやばね仕掛けのように、両端(根元と先端)の間に張ったコイルばねの
らせん上の各点の行列を出力します。両端の距離が変わると巻きの間隔(ピッチ)だけが変わり、巻きの半径と線の太さは
変わりません。そのため、ばねのメッシュを拡大縮小したときのように線まで潰れて見えることがありません。
縮めても巻き同士が接する長さ(密着長)より短くはならず、足りない分を ``coilBind`` として出力します。
Maya標準ノード(``aimMatrix`` ・ ``composeMatrix`` ・ ``multMatrix`` ・ ``distanceBetween`` など)のみで構築し、
独自プラグインやフレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import CoilSpring

   graph = CoilSpring.create(
       "spring_seat", "spring_top", name="frontSpring",
       count=17, turns=5.0, radius=1.2, wireDiameter=0.3, aimAxis="y", upAxis="x",
   )
   owner = graph.container
   # 各点を、TRSがidentityでワールドの直下(または親がidentity)のjointへ接続する
   for index in range(17):
       owner.getPlug("matrix{}".format(index)).connectTo("spring_jnt{}.offsetParentMatrix".format(index))

出力のjointへらせん状のばねのメッシュをスキンすると、伸縮しても巻きの太さが保たれます。

引数
----

* ``base``: ばねの根元のtransform。
* ``tip``: ばねの先端のtransform。
* ``count``: らせん上の点(出力行列)の数。2〜1000、既定は13。巻き1周あたり4点以上を目安にします。
* ``turns``: 巻き数。0.5以上、既定は4。
* ``radius``: 巻きの半径(cm)。既定は1。
* ``wireDiameter``: 線の太さ(cm)。0以上、既定は0.2。0なら密着しません。
* ``aimAxis``: ``base`` のローカルで、ばねの軸の向きにする軸。x/y/z、既定はx。
  ばねの軸は常に ``base`` から ``tip`` へ向けるので、生成時に ``base`` の軸が ``tip`` を向いていなくてもかまいません。
* ``upAxis``: ``base`` のローカルで、巻き始め(角度0)の向きにする軸。 ``aimAxis`` と異なる軸、既定はy。

``turns`` ・ ``radius`` ・ ``wireDiameter`` はcontainerのkeyableなアトリビュートとして、生成後も変更できます。

計算式
------

1. ばねの座標系 ``F`` : ``aimMatrix`` (primaryMode=Aim、secondaryMode=Align)で、 ``base`` の位置から
   ``aimAxis`` を ``tip`` へ向け、 ``upAxis`` を ``base`` の現在の ``upAxis`` の向きへ揃えます。
   ``base`` を軸まわりに回すと、ばねも一緒にねじれます。
2. ``L`` = 両端の距離、 ``solidLength = turns × wireDiameter`` 、
   ``effectiveLength = max(L, solidLength)`` 、 ``coilBind = effectiveLength − L`` 、
   ``pitch = effectiveLength / turns`` 、 ``gap = pitch − wireDiameter`` (cm)。
3. 点 ``i`` ( ``t = i / (count − 1)`` )の行列(行ベクトル規約):

   ``matrix_i = T(upAxis × radius) · R(aimAxis, 360 × turns × t 度) · T(aimAxis × effectiveLength × t) · F``

各点の ``upAxis`` は軸から外向き、 ``aimAxis`` はばねの軸の向きです。最初の点は根元、最後の点は先端から、
それぞれ軸に垂直に ``radius`` だけ離れた位置になります。

出力
----

* ``matrix0`` 〜 ``matrixN-1``: らせん上の各点のワールド行列。
* ``length``: 両端の現在の距離(cm)。
* ``solidLength``: 巻き同士が接する長さ(cm)。
* ``effectiveLength``: らせんの実際の長さ(cm)。密着より縮めたときは ``solidLength`` 。
* ``pitch``: 巻き1周あたりの軸方向の距離(cm)。
* ``gap``: 隣の巻きとの隙間(cm)。密着で0。
* ``coilBind``: 密着より縮めた量(cm)。範囲内は0。補正やドライバーに使えます。

距離の出力は、UIの長さ単位によらず常にcmです。

制限
----

* 各点の向きはばねの軸に沿い、らせんの接線の傾き(ピッチ角)は含めません。
  巻き数に対して長く伸ばすと、線の断面がわずかに斜めに見えます。
* 密着より縮めると、ばねの先端側は ``tip`` へ届きません(その距離が ``coilBind`` )。 ``tip`` の位置は制限しません。
* ばね全体の曲がり(軸の湾曲)・座屈は扱いません。軸は常に両端を結ぶ直線です。
* 巻きの向きは ``aimAxis`` まわりの右ねじだけです。
* 両端を結ぶ線が ``base`` の ``upAxis`` と平行になる姿勢では、巻き始めの向きが不定になります。
* 負・非一様scaleは対象外です。出力はワールド行列なので、親がidentityでない場所へ直接接続すると二重変換になります。

テスト
------

``mlrig/__tests__/test_setup_coil_spring.py`` (``setups`` スイート)で、回転したbaseと斜めのtipについて、
各点の位置・半径方向・軸方向と長さの出力がOpenMayaで組んだ式と一致すること、伸ばしても半径が変わらないこと、
密着長より縮めたときの ``coilBind`` と安全な長さへの復帰、baseの回転によるねじれ、アトリビュートの変更、
Python版 ``CoilSpring.coilLayout`` との一致、別の軸の指定、containerの所有とUndo/Redo、引数の検査を確かめます。
Maya 2027で確認しています。

検証動画
--------

``tools/demo_coil_spring.py`` は、新規シーンに根元と先端のlocator、らせんの各点(緑の線でつないだ球)、
密着を示す赤い表示を正面から見る構図で作り、式と毎フレームの入力値・DG出力をHUDに表示して録画します。
伸ばす→密着長まで縮める→密着長を超えて押し込む→保持→元の長さへ戻す、の順に記録し、各フレームで出力が
独立計算と一致することを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_coil_spring.py --launch
