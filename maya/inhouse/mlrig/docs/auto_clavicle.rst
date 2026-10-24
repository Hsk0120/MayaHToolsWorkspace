鎖骨への自動分配(AutoClavicle)
==============================

``mlrig.setups.AutoClavicle`` は、上腕を大きく上げたときの曲げ(Swing)の一部を鎖骨の回転へ移し、
肩の位置を自然に持ち上げる行列を出力します。上腕は鎖骨が回った分だけSwingを戻すため、
上腕のワールドでの向きはアニメーターが付けた入力のまま変わらず、肩(上腕の根元)の位置だけが動きます。
Maya標準ノードのみで構築し、独自プラグインやフレームごとのPythonは使いません。

人の肩では、腕を上げ始めの約30度は肩甲骨・鎖骨がほとんど動かず、その先は上腕と肩甲骨がおよそ2:1で動くと説明されます
(肩甲上腕リズム)。既定値の ``start=30`` ・ ``weight=1/3`` はこの目安に合わせたものです。

.. code-block:: python

   from mlrig.setups import AutoClavicle

   graph = AutoClavicle.create(
       "clavicle_l", "upperarm_l", name="clavicle_l_auto", axis="x",
       start=30, weight=1.0 / 3.0, maximum=35,
   )
   owner = graph.container
   # 入力と同じ親空間、TRSとjointOrientがidentityの出力骨へ接続する
   owner.getPlug("clavicleMatrix").connectTo("clavicle_l_out.offsetParentMatrix")
   # 出力の上腕は出力の鎖骨の子にする
   owner.getPlug("matrix").connectTo("upperarm_l_out.offsetParentMatrix")

引数
----

* ``clavicle``: 上腕の直接の親joint。
* ``upperarm``: 鎖骨の子joint。
* ``axis``: 生成時の姿勢での上腕の長手(Twist)軸。x/y/z。
* ``start``: 鎖骨が動き始める上腕の曲げ角(度、0〜179)。
* ``weight``: 開始角を超えた分のうち鎖骨へ移す割合(0〜1)。
* ``maximum``: 鎖骨の回転角の上限(度、0より大きく90以下)。

``start`` ・ ``weight`` ・ ``maximum`` はcontainerのアトリビュートとして生成後も変更・アニメーションできます。

計算式
------

基準は生成時の姿勢です。上腕の ``matrix * offsetParentMatrix`` を :doc:`swing_twist` と同じ方法で
Twist ``T`` とSwing ``S`` に分け(行ベクトル規約で ``T * S * U0`` が現在の回転、 ``U0`` は基準回転)、
基準の長手軸と現在の長手軸のなす角 ``θ`` (度)を求めます(:doc:`swing_limit` と同じ)。

1. 鎖骨の角度 ``c = maximum·(1 - exp(-weight·max(θ - start, 0)/maximum))`` 。
   ``θ`` が ``start`` を少し超えたところでは ``weight·(θ - start)`` とほぼ同じで、大きく上げても ``maximum`` を超えません。
2. 比率 ``k = c/θ`` (``θ`` が0.0001度未満なら0)。
3. 鎖骨の追加回転 ``E = U0⁻¹ · S^k · U0`` 。 ``S^k`` はSwingを単位行列から ``k`` だけ補間した回転(``blendMatrix``)で、
   ``U0`` で挟んで上腕の基準空間から鎖骨の空間へ移します。上腕のSwingと同じ向きの軸まわりに ``c`` 度回ります。
4. ``clavicleMatrix = E · (鎖骨の matrix * offsetParentMatrix)`` 。鎖骨に付けた入力の回転にも重なります。
5. 上腕の ``matrix`` は ``T · S^(1-k) · U0`` に上腕の現在位置を合わせたものです。
   ``T·S^(1-k)·U0·E = T·S·U0`` なので、出力の上腕のワールド回転は入力と一致します。

出力
----

* ``clavicleMatrix``: 鎖骨の追加回転を足した、鎖骨と同じ親空間の行列。
* ``clavicleRotation``: 鎖骨の空間での追加回転 ``E`` 。
* ``matrix``: Swingを戻した上腕の、鎖骨の空間の行列。出力の鎖骨の子の出力骨へ接続します。
* ``swingAngle``: 上腕の曲げ角 ``θ`` (度)。
* ``clavicleAngle``: 鎖骨へ移した角度 ``c`` (度)。
* ``upperarmAngle``: 上腕に残した角度 ``θ - c`` (度)。
* ``ratio``: ``k = c/θ`` 。
* ``swingMatrix`` ・ ``twistMatrix`` ・ ``twist`` ・ ``swingX/Y/Z`` : :doc:`swing_twist` と同じ分解結果(上腕の入力側)。

制限
----

* 曲げる向きによらず同じ式で分配します。腕を下げる・後ろへ引く動きでも、 ``start`` を超えれば鎖骨は動きます。
  上げる向きだけで動かしたい場合は、Tポーズなど上げ始める向きが分かる姿勢で生成し、 ``start`` を調整してください。
* Twistは鎖骨へ移さず上腕に残します。
* 曲げの向きの不定な180度付近では、Swing・Twistの分解自体が連続になりません。
* 鎖骨・上腕の位置は入力の現在位置を使い、上腕の出力はscale・shearを持ちません。負・非一様scaleは対象外です。
* 上腕のワールドでの向きは保ちますが、肩の位置が動くので手先の位置は入力と変わります。IKの目標を保つ処理ではありません。
* 別の親空間へ直接接続したり、非identityのTRSへ重ねたりすると二重変換になります。
