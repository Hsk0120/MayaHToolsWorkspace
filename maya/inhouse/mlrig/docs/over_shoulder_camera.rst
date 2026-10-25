肩越しのカメラの配置(OverShoulderCamera)
========================================

``mlrig.setups.OverShoulderCamera`` は、会話する2人の **頭の位置** から、手前の人物(partner)の
**肩越し** に奥の人物(focus)を写すカメラの **位置と向き** を決めます。focus の頭は画面の決まった位置
(例えば三分割法の交点)に写り、カメラは2人を結ぶ線(イマジナリーライン)の片側から動きません。
人物が歩いても、2人とカメラの三角形の位置関係を保ったままカメラが付いていきます。

* 会話の場面で、話し手ごとの肩越しのカメラを、立ち位置が変わるたびに手で置き直したくないとき。
* 2人を結ぶ線を越えない(カメラの側が入れ替わらない)カメラを、人物のアニメーションから自動で決めたいとき。
* 頭を画面の中央ではなく、三分割の位置などに置いた構図を保ちたいとき。

Maya標準ノード(``vectorProduct`` ・ ``plusMinusAverage`` ・ ``multiplyDivide`` ・ ``composeMatrix`` ・
``aimMatrix`` ・ ``multMatrix`` ・ ``distanceBetween`` ・ ``pickMatrix`` ・ ``blendMatrix`` ・ ``decomposeMatrix``)だけで
組み、containerの ``matrix`` へ出力します(既定ではカメラの ``translate`` ・ ``rotate`` へ接続)。独自プラグイン、
エクスプレッション、フレームごとのPythonは使いません。時刻や前のフレームの結果を使わないので、どのフレームでも
同じ配置からは同じ値になります。生成したノードはcontainerが所有し、単位変換のノードは挟みません。

.. code-block:: python

   from mlrig.setups import OverShoulderCamera

   shot = OverShoulderCamera.create("shotCam", "hero_head_jnt", "friend_head_jnt", name="shot",
                                    angle=15, height=1, screenX=1 / 3.0, screenY=1 / 3.0)
   cmds.setAttr("shot.weight", 1)    # 作成時のカメラの姿勢(0)から肩越しの配置(1)へ
   cmds.setAttr("shot.side", -1)     # 2人を結ぶ線の反対側から写す
   cmds.getAttr("shot.focusDistance")  # カメラの基準の位置から focus までの距離(被写界深度のピント合わせに使える)

式
--

focus の位置を ``a`` 、partner の位置を ``b`` 、上をワールドのYとします。

* 2人を結ぶ水平の向き ``u = normalize((b - a) の水平成分)`` (2人を床へ落とした点の間で ``aimMatrix`` が +Z を向ける)。
* ``u`` をY軸まわりに ``θ = side · angle`` 回した向き ``d`` 。 ``side > 0`` なら ``(u × d).y > 0`` の側です。
* カメラの基準の位置 ``c0 = a + distance · d + (0, height, 0)`` 。 ``c0`` から ``a`` へカメラの -Z を向け、+Y をワールドの上へ
  揃えた向きを ``R`` (``aimMatrix``)とします。
* ``D = |a - c0|`` 、focus を通り視線に垂直な面でのフィルムゲートの半分の幅・高さを
  ``halfWidth = D · horizontalFilmAperture · 25.4 / (2f)`` 、 ``halfHeight = D · verticalFilmAperture · 25.4 / (2f)``
  ( ``f`` は焦点距離(mm))とします。
* カメラの位置 ``c = c0 - screenX · halfWidth · X - screenY · halfHeight · Y`` ( ``X`` ・ ``Y`` は ``R`` の右・上の軸)。
  向きは ``R`` のまま平行に動かすので、focus の頭はフィルムゲートの座標 ``(screenX, screenY)`` (左右・上下の端が ±1)に
  写ります。三分割法の交点は ``(±1/3, ±1/3)`` です。
* 出力 ``matrix = blendMatrix(作成時のカメラのワールド行列, R と c の行列, weight)`` 。既定の ``weight=0`` では作成時に
  カメラが動きません。

Python版の ``OverShoulderCamera.placement()`` は同じ式でカメラのワールド行列を返します(確認用)。

containerのアトリビュート
-------------------------

.. list-table::
   :header-rows: 1

   * - 名前
     - 内容
   * - ``distance``
     - focus からカメラの基準の位置までの水平の距離(keyable、cm)。既定は作成時の2人の水平の距離の1.5倍。
   * - ``angle``
     - 2人を結ぶ線からカメラを回す角度(keyable、度、0〜90)。0なら partner の真後ろ。
   * - ``height``
     - focus の頭からのカメラの高さ(keyable、cm)。
   * - ``side``
     - 線のどちら側か(keyable、-1〜1)。+1・-1 で反対側、途中の値は角度を縮めます。
   * - ``screenX`` ・ ``screenY``
     - focus の頭を写す画面の位置(keyable、-1〜1、フィルムゲートの左右・上下の端が ±1)。
   * - ``weight``
     - 作成時のカメラの姿勢(0)から肩越しの配置(1)への補間(keyable、0〜1、回転は球面補間)。
   * - ``matrix``
     - カメラのワールド行列(出力)。 ``connect=True`` (既定)ならカメラの親の空間へ戻して ``translate`` ・ ``rotate`` へ接続します。
   * - ``focusDistance``
     - カメラの基準の位置から focus までの距離(出力、cm)。

制限
----

* 画面の位置はフィルムゲート(横・縦のフィルムバック)を基準にします。解像度の縦横比とフィルムの縦横比が違う場合、
  レンダーの枠(解像度ゲート)の端とは一致しません。フィルムのオフセット・カメラの ``rotatePivot`` ・ ``rotateAxis`` は考慮しません。
* カメラの親が非一様なscaleを持つと、カメラの向きが歪みます(位置は合います)。
* 2人が真上・真下に重なる(水平の距離が0)と線の向きが決まりません(作成時は ValueError)。
* カメラと focus の間に partner 以外の人物が入ることは避けません。3人以上の会話では、片方を相手のグループの中心
  (別に作った中点のtransform)に置き換えて線を作ってください。
* ``vectorProduct`` ・ ``multiplyDivide`` は単精度で計算するため、位置には1e-5cm程度の丸めの誤差が入ります。

試験
----

``mlrig/__tests__/test_setup_over_shoulder_camera.py`` (``setups`` スイート)で、回転・移動・スケールした親の下のカメラと、
回転・非一様スケールした親の下の2人の頭について、既定の ``weight=0`` で作成直後にカメラが動かないこと、2人と
``angle`` ・ ``height`` ・ ``distance`` ・ ``screenX`` ・ ``screenY`` を乱数で変えた20通りとレンズの変更で、カメラの位置・軸が
試験側で独立に書いた式と一致し(位置 1e-4cm、軸 1e-5)、focus の頭がフィルムゲートの指定の位置に写ること(1e-5)、
``side`` の符号でカメラが線の決まった側に留まること、 ``side=0`` で線の延長上に来ること、 ``weight`` の補間、
``connect=False`` とカメラのシェイプの指定、container所有(単位変換なし)とUndo/Redo、引数15種で何も残さないことを確認します。
また、カメラの親・ ``offsetParentMatrix`` ・キーを打った時間を動かしても、DG・serial・parallel の各評価で、出力に先立って
問い合わせたカメラのワールド行列が古い値にならないことを確認します(translate の計算に使うカメラ自身の
``parentInverseMatrix`` は ``offsetParentMatrix`` と親だけで決まり、駆動する translate・rotate とは循環しません)。

参考にした考え方
----------------

* 会話の場面の肩越しのカメラを、写す人物の頭の位置からの角度・距離で置き、画面の三分割法の位置へ頭が来るように
  カメラを水平に動かし、人物が動いても写す人物・手前の人物・カメラの三角形を保って付いていかせる一般的な考え方。
* 向かい合う人物を結ぶ線(イマジナリーライン)を越えてカメラを置かない、映像の基本の決まり。
