シャフトの長さを保って滑るトリポード継手(TripodJoint)
=========================================================

``mlrig.setups.TripodJoint`` は、車のドライブシャフトの内側(デフ側)に使われるトリポード形の継手の
スパイダーとシャフトの行列を作ります。サスペンションで外側の継手(車輪側)が上下して両端の距離が変わっても、
シャフトの長さは変えず、スパイダーがハウジングの軸に沿って滑ります(プランジ)。滑れる範囲を超えた量
``overPlunge`` と、そのときのシャフトの伸び縮み ``stretch`` も出力します。
Maya標準ノード(``decomposeMatrix`` ・ ``pickMatrix`` ・ ``vectorProduct`` ・ ``plusMinusAverage`` ・
``multiplyDivide`` ・ ``clamp`` ・ ``angleBetween`` ・ ``composeMatrix`` ・ ``multMatrix``)だけで組み、
独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import ConstantVelocityJoint, TripodJoint

   inner = TripodJoint.create("diffOutput_jnt", "wheelHub_loc", name="innerTripod", axis="x")
   owner = inner.container
   # 出力はワールド行列。原点にある親の下の、TRSがidentityのtransformで受ける
   owner.getPlug("matrix").connectTo("spider_drv.offsetParentMatrix")
   owner.getPlug("tipMatrix").connectTo("shaftTip_drv.offsetParentMatrix")

``housing`` はハウジング(デフの出力軸)のtransformで、プランジ0の位置に置き、 ``axis`` を軸の向きにします。
``axis`` まわりの回転(``rotateX`` など)はシャフトへ等速で伝わります。 ``outerJoint`` はシャフトの反対側
(外側の継手の中心)で、位置だけを使います。外側の継手の向きは :doc:`constant_velocity_joint` で作れます。

参考にした考え方
----------------

* トリポード継手では、スパイダーの3本のトラニオン(ローラー付き)がハウジングの軸方向の溝を滑るので、
  角度を付けたまま回転を伝えつつ軸方向へ伸び縮みします。ドライブシャフトの内側がプランジを受け持ち、
  外側の継手はプランジしません
  (`Tripod Joint Mechanism Explained <https://www.firgelliauto.com/blogs/mechanisms/tripod-joint>`_ 、
  `US5213546A Anti-shudder tripod constant velocity joint <https://patents.google.com/patent/US5213546>`_)。

いずれもコードは流用していません。

引数
----

* ``housing``: ハウジングのtransform。
* ``outerJoint``: 外側の継手の位置を表すtransform(位置だけを使う)。
* ``axis``: ハウジング・シャフトの軸の向き(``"x"`` ・ ``"y"`` ・ ``"z"``)。
* ``length``: シャフトの長さ(cm)。 ``None`` なら生成時の ``housing`` と ``outerJoint`` の距離(つまり生成時はプランジ0)。
* ``minPlunge`` ・ ``maxPlunge``: 滑れる範囲(cm)。負はハウジングの奥へ押し込む向きです。
  ``None`` ならそれぞれ ``-0.1 × length`` ・ ``0.1 × length`` 。

container の ``length`` ・ ``minPlunge`` ・ ``maxPlunge`` は後から変更できます。

計算式
------

``H`` を ``housing`` の位置、 ``R`` をそのワールド行列の回転(scale・shear・平行移動を除く)、 ``u`` を ``R`` で
回した ``axis`` の向き、 ``W`` を ``outerJoint`` の位置、 ``L`` を ``length`` とします。

1. ``d = W - H`` 、軸方向の成分 ``a = d·u`` 、軸からの距離の2乗 ``b² = |d|² - a²`` 。
2. スパイダーの中心を軸上の ``c = H + u × p`` に置き、 ``|W - c| = L`` を解く(直線と球の交点)と
   ``(a - p)² + b² = L²`` 。ハウジング側の解は ``p = a - √(L² - b²)`` です。
   ``L < b`` (軸から長さより遠く届かない)では根号の中を0にし、軸に最も近い点 ``p = a`` を使います。
3. ``plunge = clamp(p, minPlunge, maxPlunge)`` 、 ``overPlunge = p - plunge`` (引き出しすぎは正、押し込みすぎは負)。
4. ``c = H + u × plunge`` 、 ``v = normalize(W - c)`` 。
5. ``matrix = R × Q(u→v)`` に位置 ``c`` 、 ``tipMatrix`` は同じ向きで位置 ``W`` 。 ``Q(p→q)`` は ``p`` を ``q`` へ回す
   最短の回転(``angleBetween`` の ``euler``)で、 :doc:`constant_velocity_joint` と同じ等速の向きです。
6. ``shaftLength = |W - c|`` 、 ``stretch = shaftLength - L`` 、 ``bendAngle`` = ``u`` と ``v`` のなす角。

範囲の中では ``shaftLength = L`` 、 ``stretch = 0`` です。範囲を超えるとスパイダーが止まり、シャフトの長さが
変わります。 ``stretch`` は、シャフトのモデルを伸ばす・ブーツ(蛇腹)の補正シェイプを動かす・範囲の確認に使えます。
Pythonの ``TripodJoint.plungeOf(a, b, L)`` は手順2の制限前の ``p`` を返します。

出力
----

* ``matrix``: スパイダー(シャフトの内側の端)のワールド行列。 ``axis`` がシャフトの向き、scaleは1。
* ``tipMatrix``: 同じ向きで外側の継手の位置にある行列。
* ``plunge``: 滑った量(cm、範囲内に制限済み)。
* ``overPlunge``: 範囲を超えた量(cm)。
* ``shaftLength``: スパイダーの中心から外側の継手までの距離(cm)。
* ``stretch``: ``shaftLength - length`` (cm)。
* ``bendAngle``: ハウジングの軸とシャフトのなす角(度)。

長さはすべてcmです。UIの長さ単位がmmなどでも、内部単位のまま計算します(Mayaが挿入する単位変換の係数を1にします)。

制限
----

* 実物ではスパイダーの中心がハウジングの軸のまわりを小さく3倍の周期で回り(orbit)、ローラーも傾きますが、
  寸法に依存し小さいので扱いません。スパイダーの中心は常にハウジングの軸上です。
* 範囲の端は硬い止まりです(柔らかく止める処理はありません)。
* ``outerJoint`` がハウジングの後ろ側(``a < 0``)に来る使い方は対象外です。実物の可動角はおよそ20〜25度です。
* シャフトの向きが ``u`` と逆向き(180度)では最短の回転の軸が決まりません。
* 出力はワールド行列です。原点以外の親の下へ接続すると二重変換になります。

テスト
------

``mlrig/__tests__/unit/setups/test_tripodJoint.py`` (``setups`` スイート)で、既定の長さ・範囲、まっすぐ軸に沿って
動かしたときのプランジ、回したハウジングで曲げた位置の直線と球の交点・シャフトの長さ・向き(OpenMayaの
最短の回転)・曲げ角、範囲を超えたときの ``overPlunge`` ・ ``stretch`` 、届かない場合、ハウジングの回転が等速で
伝わること・ ``tipMatrix`` 、別の軸と親の回転・scale、UIの長さ単位mm、containerの所有とUndo/Redo、引数の検査を
確認します。Maya 2027で確認しています。

検証動画
--------

``tools/demo_tripod_joint.py`` は、新規シーンにハウジング(赤)、スパイダーとシャフト(緑)、外側の継手(黄)を作り、
外側の継手を上下させながら、式と毎フレームの外側の継手の高さ・ ``a`` ・ ``b`` ・制限前のプランジ・ ``plunge`` ・
``overPlunge`` ・ ``shaftLength`` ・ ``stretch`` ・ ``bendAngle`` をHUDに表示して録画します。
まっすぐ→上下に振る(範囲内)→範囲を超える→範囲へ戻る→まっすぐへの復帰を記録し、各フレームで
プランジが式と一致し、範囲内ではシャフトの長さが一定であることを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを
``latest-tripod-joint.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_tripod_joint.py --launch
