カメラの角度の読み取り(CameraAngleReader)
==========================================

``mlrig.setups.CameraAngleReader`` は、顔(頭)から見たカメラの方向を水平角 ``yaw`` と垂直角 ``pitch`` に分け、
「正面・左・右・上・下・後ろ」の6つの重みに変えます。重みを顔の補正シェイプ(ブレンドシェイプ)や補助骨の
ドリブンキーへ接続すると、あおり・俯瞰・真横のような見え方の苦手な角度から見たときだけ、その角度用に用意した
補正を自動で混ぜられます。自由に動くカメラでも重みの和は常に1で、カメラがどう動いても連続に変わるので、
補正が切り替わる瞬間に顔が跳ねません。
Maya標準ノード(``multMatrix`` ・ ``decomposeMatrix`` ・ ``vectorProduct`` ・ ``angleBetween`` ・ ``condition`` ・
``multiplyDivide`` ・ ``clamp`` ・ ``plusMinusAverage``)だけで組み、独自プラグインやフレームごとのPython・
エクスプレッションは使いません。

.. code-block:: python

   from mlrig.setups import CameraAngleReader

   graph = CameraAngleReader.create(
       "head_jnt", "shotCam", name="faceCamera",
       forwardAxis="z", upAxis="y", yawRange=90.0, pitchRange=60.0, backFade=30.0,
   )
   owner = graph.container
   # 俯瞰(カメラが上)用と、あおり(カメラが下)用の補正シェイプへ重みを接続する
   owner.getPlug("weightAbove").connectTo("faceFix_bs.highAngle")
   owner.getPlug("weightBelow").connectTo("faceFix_bs.lowAngle")

``yawRange`` ・ ``pitchRange`` ・ ``backFade`` はcontainerのkeyableなアトリビュートで、作成後も変更できます。
1つの重みを複数の補正へつなぐ場合や、重みの効き方を曲げたい場合は、 ``remapValue`` やドリブンキーを間に挟みます。

参考にした考え方
----------------

カメラの角度に応じて顔の見え方を補う一般的な方法のうち、次の考え方を標準ノードの計算へ置き換えました。コードは流用していません。

* 自由に動かせるカメラでは、顔にとって苦手な角度(あおり・俯瞰など)がどうしても生まれる。カメラが固定の場面では
  手で直すが、自由なカメラでは、苦手な角度ごとに理想の形の補正を用意しておき、カメラの角度に応じて自動で混ぜる。
* 顔に対するカメラの角度は、正面を0度として水平方向(-180〜180度)と垂直方向(-90〜90度)に分け、2次元の平面として扱う。
  その平面上に補正ごとの点を置き、カメラが近い点の補正ほど強く効かせる。
* 補正が切り替わったことが見ている人に分からないよう、重みはどこでも和が1で、どう動いても連続に変わるようにする。
  最も簡単な方法は、点の間を線形に補間すること。点を結んだ三角形の中は3点、外側は中心から外の点へ引いた線で区切った
  領域の2点を混ぜる。

ここでは点を十字(正面・左・右・上・下)に固定し、真後ろは顔が見えないので「後ろ」の重みへ移して、真後ろで左右が
入れ替わるところでも跳ねないようにしています。斜め方向の点や、より細かい点の配置は扱いません
(必要なら出力の ``yaw`` ・ ``pitch`` から :doc:`radial_weights` やドリブンキーで作ります)。

引数
----

* ``head``: 顔の向きを表すtransform(頭のjointなど)。
* ``camera``: カメラ、またはカメラの位置を表すtransform。位置だけを使います。
* ``forwardAxis``: ``head`` のローカルで顔の正面を向く軸。x/y/zと負の向きの-x/-y/-z(既定z)。
* ``upAxis``: ``head`` のローカルで頭の上を向く軸(既定y)。 ``forwardAxis`` と直交する軸を指定します。
  左は ``upAxis × forwardAxis`` (既定ではローカル+X)です。
* ``yawRange``: 左・右の重みが1になる水平角(度、0より大きく180以下、既定90)。
* ``pitchRange``: 上・下の重みが1になる垂直角(度、0より大きく90以下、既定60)。
* ``backFade``: 真後ろから何度の範囲で後ろの重みへ移すか(度、0より大きく180以下、既定30)。

計算式
------

角度は度です。

1. ``p`` = ``camera.worldMatrix`` の位置を ``head.worldInverseMatrix`` で頭の空間へ移した点。
   ``f = p·forward`` 、 ``u = p·up`` 、 ``l = p·left`` 。
2. ``|yaw|`` = ``(f, l, 0)`` と ``(1, 0, 0)`` の間の角度、 ``yaw`` は ``l >= 0`` なら正、負なら負( ``atan2(l, f)`` と同じ)。
   ``pitch = 90 - ((f, l, u) と (0, 0, 1) の間の角度)`` ( ``atan2(u, sqrt(f² + l²))`` と同じ)。
   ``angleBetween`` のラジアンは ``unitConversion`` で度へ明示的に変換するので、UIの角度単位によりません。
3. ``aL = clamp(yaw / yawRange)`` 、 ``aR = clamp(-yaw / yawRange)`` 、 ``bA = clamp(pitch / pitchRange)`` 、
   ``bB = clamp(-pitch / pitchRange)`` (clampは0〜1)。 ``sum = aL + aR + bA + bB`` 、 ``s = max(sum, 1)`` 。
4. ``front = max(1 - sum, 0)`` 、 ``left = aL / s`` 、 ``right = aR / s`` 、 ``above = bA / s`` 、 ``below = bB / s`` 。
   ``sum <= 1`` (正面・横・上下の三角形の中)では重心座標、 ``sum > 1`` (三角形の外)では横と上下の2点の間の補間になり、
   境目の ``sum = 1`` で両者は一致します。
5. ``k = clamp((180 - |yaw|) / backFade)`` 。手順4の5つの重みに ``k`` を掛け、 ``back = 1 - k`` 。

どの場合も6つの重みの和は1です。各重みの変化は、水平角1度あたり最大で ``1 / backFade`` (左右の範囲より後ろへの移行が急な場合)です。

出力
----

* ``yaw``: 水平角(度、-180〜180)。頭の左側にカメラがあると正。
* ``pitch``: 垂直角(度、-90〜90)。頭より上にカメラがあると正(俯瞰)。
* ``weightFront`` ・ ``weightLeft`` ・ ``weightRight`` ・ ``weightAbove`` ・ ``weightBelow`` ・ ``weightBack``: 方向ごとの重み(0〜1、和は1)。

制限
----

* 点の配置は十字の5点と後ろに固定です。斜め方向に専用の補正を置く場合は、出力の角度から別に重みを作ります。
* カメラが頭の真上・真下、または頭と同じ位置にあると水平角が決まらず、0として扱われます。
* カメラの位置だけを見ます。画角(ズーム)やカメラの向き(画面のどこに顔が映っているか)は考慮しません。
* ``head`` に不均一なscaleがあると、角度もその分ゆがみます。
* 重みは見え方の補正のための値で、補正シェイプ自体は作りません。
