カムと従動節(CamFollower)
==========================

``mlrig.setups.CamFollower`` は、回転する板カムに押される直動の従動節(フォロワー)が、カムの1回転の間に
「下で止まる・上がる・上で止まる・下がる」を繰り返す変位を求めます。エンジンの弁・からくり人形・印刷機・
自動機の送りなど、休止を挟む往復運動を、カムの1つの回転だけでアニメーションできます。
Maya標準ノード(``floor`` ・ ``sin`` ・ ``cos`` ・ ``animBlendNodeAdditive`` ・ ``multDoubleLinear`` ・
``condition`` ・ ``blendTwoAttr`` ・ ``unitConversion``)だけで組み、独自プラグイン、エクスプレッション、
フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import CamFollower

   # 120度かけて2cm上がり、60度止まり、120度かけて下がり、残りの60度は下で止まる
   graph = CamFollower.create("cam", "valve", rise=2.0, riseAngle=120.0, dwellAngle=60.0, returnAngle=120.0,
                              law="cycloidal", name="valveCam", axis="z", followerAxis="y")
   owner = graph.container
   # 従動節の translateY へ出力を接続済み。カムの rotateZ を回すだけで動く

``connect=True`` (既定)なら従動節の ``translate<followerAxis>`` へ出力を接続します。 ``False`` なら接続せず、
containerの ``translate`` ・ ``lift`` を自分で使います。

参考にした考え方
----------------

* カムの1回転を休止・上昇・休止・下降の区間に分け、上昇・下降にサイクロイド曲線
  ``s = h (θ/β - sin(2πθ/β) / 2π)`` を使うと、区間の境目で速度も加速度も0になるという一般的な設計の関係
  (https://faculty.ksu.edu.sa/sites/default/files/me_363_cam_handout.pdf 、
  https://www.firgelliauto.com/es/blogs/mechanisms/disk-cam-with-translating-follower 、
  https://www.firgelliauto.com/blogs/mechanisms/cam-producing-variable-rectilinear-motion)。
* 運動曲線 f が ``f(0) = 0`` ・ ``f(1) = 1`` なので、上昇と下降の進みをそれぞれ0〜1に止めて差を取れば、
  区間ごとに分岐しなくても4つの区間が1つの式になる、という組み立て(この部品で考えた形です)。

いずれもコードは流用していません。

引数
----

* ``cam``: カムのtransform。ローカルの ``rotate<axis>`` を回します。生成時の姿勢を、上昇が始まる直前
  (下の休止の終わり、 ``θ = 0`` )とします。
* ``follower``: 従動節のtransform。ローカルの ``translate<followerAxis>`` を動かします。
* ``rise``: 上昇量 h (cm)。containerの ``rise`` で後から変えられます。
* ``riseAngle`` ・ ``dwellAngle`` ・ ``returnAngle``: 上昇・上の休止・下降の区間のカムの角度(度)。
  合計は360度以下で、残りが下の休止です。生成時に固定します。
* ``law``: 上昇・下降の運動曲線。 ``"cycloidal"`` (既定)か ``"harmonic"`` 。
* ``axis`` ・ ``followerAxis``: カムの回転軸と従動節の移動軸(x/y/z)。
* ``connect``: Trueなら従動節へ出力を接続します。既に入力がある場合は ``ValueError`` です。

計算式
------

``β1`` ・ ``βd`` ・ ``β2`` は上昇・上の休止・下降の角度、 ``h`` は上昇量です(式の角度はラジアン)。

1. ``θ = カムの rotate<axis> - 生成時の値 + phase`` 、 ``turn = floor(θ / 360°)`` 、
   ``w = θ - 360°·turn`` (1回転の中の角度、0〜360°)。
2. ``u1 = clamp(w / β1, 0, 1)`` (上昇の進み)、 ``u2 = clamp((w - β1 - βd) / β2, 0, 1)`` (下降の進み)。
3. ``lift = h (f(u1) - f(u2))`` 、 ``translate = 生成時の従動節の translate<followerAxis> + lift`` 。
4. ``velocity = ds/dθ = h (f'(u1) / β1 - f'(u2) / β2)`` (cm/ラジアン)。

運動曲線は次の2つです。

* ``cycloidal`` : ``f(u) = u - sin(2πu) / 2π`` 、 ``f'(u) = 1 - cos(2πu)`` 。速度も加速度も区間の端で0なので、
  休止から滑らかに動き出します。速度の最大は上昇の中央で ``2h / β1`` です。
* ``harmonic`` : ``f(u) = (1 - cos πu) / 2`` 、 ``f'(u) = (π/2) sin(πu)`` 。速度は端で0ですが、加速度は端で跳びます。

f' は u = 0・1 で0なので、止めた u から求めた速度は休止中に自動で0になり、区間の境目で変位も速度も連続します。
θ = 0 では lift = 0 なので、接続しても従動節は跳ねません。履歴を持たない閉じた式なので、カムを逆に回すと
従動節も同じ経路を戻ります。

数値の加算は ``animBlendNodeAdditive`` を連ねて倍精度で行います(``plusMinusAverage`` ・ ``multiplyDivide`` は単精度のため)。
``floor`` ・ ``sin`` ・ ``cos`` ・ ``multDoubleLinear`` の入出力は版により長さの型なので、係数を明示した ``unitConversion`` を挟み、
UI単位(mm・ラジアン等)に関係なく同じ結果にします。

containerのアトリビュート
--------------------------

* ``rise`` : 上昇量 h (keyable)。
* ``phase`` : カムの角度に足す値(keyable)。区間の始まりをカムの見た目に合わせるのに使います。
* ``translate`` : 従動節の移動(出力)。
* ``lift`` : 生成時からの変位(0〜h)。補正シェイプや音のドライバーに使えます。
* ``velocity`` : カムの角度あたりの従動節の速さ ds/dθ (cm/ラジアン、上昇中は正、下降中は負)。
* ``camAngle`` : 1回転の中のカムの角度 w 。
* ``riseProgress`` ・ ``returnProgress`` : 上昇・下降の進み u1 ・ u2 (0〜1)。
* ``turn`` : カムの回転数。

制限
----

* カムはローカルの1軸の回転チャンネル( ``rotate<axis>`` )を読みます。複数軸の回転やワールドでの回転は扱いません。
* 従動節は直動(軸に沿って動く)だけです。揺動従動節(レバーが振れる形)は扱いません。
* カムの形状(輪郭)は作りません。ナイフエッジ従動節なら、基礎円の半径 r0 に対し、カムのローカルで角度
  ``90° - θ`` の向きへ ``r0 + lift(θ)`` の点を並べた曲線が輪郭になります(Setup Samplesで描いています)。
  ローラー従動節の輪郭(オフセット曲線)や圧力角は扱いません。
* 運動曲線はサイクロイドと単弦の2つです。多項式(3-4-5 等)の曲線は扱いません。

テスト
------

``mlrig/__tests__/unit/setups/test_camFollower.py`` (``setups`` スイート)で、作成直後に従動節が跳ねないこと、
4つの区間それぞれの変位が試験側で区間ごとに書いた式と一致すること(正負の回転・複数回転)、区間の境目で変位と速度が
連続すること、Python版( :meth:`CamFollower.motion` )との一致と ``velocity`` がDGの変位の数値微分と一致すること、
``harmonic`` ・ ``rise`` の変更・ ``phase`` 、 ``axis = x`` ・ ``followerAxis = z`` ・UI単位mm/ラジアン・下の休止なし、
containerの所有とUndo/Redo、引数の検査を確認します。Maya 2027で確認しています。

検証動画
--------

``tools/demo_cam_follower.py`` は、新規シーンに板カム(赤、輪郭は式から描いた形)と従動節(緑の棒、灰色は動かない入力の目印)を
正面から見る構図で作り、カムを1回転→もう1回転の途中まで→逆回転→元へ戻す動きで、式と毎フレームの θ ・区間・ u1 ・ u2 ・
変位・速度をHUDに表示して録画します。各フレームでDGの出力が試験側の式と一致し、従動節の先がカムの輪郭の上にあることを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-cam-follower.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_cam_follower.py --launch
