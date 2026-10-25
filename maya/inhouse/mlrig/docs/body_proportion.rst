体格のパラメーター(BodyProportion)
==================================

``mlrig.setups.BodyProportion`` は、「腕の長さ」「肩幅」「脚の長さ」「上腕の太さ」のような少数の体格のパラメーターで、
体格調整用の骨の移動・スケールを生成時の体格(標準の体格)から変える仕組みを作ります。
衣装やモデルを全員共通の標準の体格で作り、骨格に体格のパラメーターの値を入れるだけで個別の体格を作る用途を想定しています。
パラメーターごとに下限・上限と、値が1(負の側は-1)のときの骨ごとの変化量を持つので、体格の設定は数値の組(:meth:`BodyProportion.getValues`)
として保存・再利用できます。
Maya標準ノード(``clamp`` ・ ``multiplyDivide`` ・ ``blendWeighted`` ・ ``unitConversion``)だけで組み、
独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import BodyProportion

   graph = BodyProportion.create([
       {"name": "armLength", "minimum": -1.0, "maximum": 1.0, "targets": {
           "elbow_L_jnt": {"translate": (0.9, 0, 0), "translateNegative": (-0.6, 0, 0)},
           "wrist_L_jnt": {"translate": (0.9, 0, 0), "translateNegative": (-0.6, 0, 0)}}},
       {"name": "armThickness", "maximum": 2.0, "targets": {
           "shoulder_L_jnt": {"scale": (0, 0.4, 0.4), "scaleNegative": (0, -0.3, -0.3)}}},
   ], name="bodyProportion")
   graph.setValues({"armLength": 0.5, "armThickness": 1.2})
   values = graph.getValues()   # {"armLength": 0.5, "armThickness": 1.2} を体格の設定として保存できる

参考にした考え方
----------------

* 体格を変えるための一般的な方法: モデル・衣装は共通の標準の体格で作り、体格変更用の骨にウェイトを付けておいて、
  骨の移動・スケールだけで個別の体格を作る。体格は少数のパラメーターで表し、パラメーターごとに上限・下限と、
  値が1変わったときの骨の変化量を決めておく(ドリブンキーで設定することが多い)。骨による変形なので、
  ブレンドシェイプのように体格ごとの形状を持たずに済み、体格の設定は数値として保存・転送できる、という考え方。

* 衣装の組み合わせによる調整も同じ数値で行える: 例えば上着の裾をズボンへ入れる組み合わせでは、腰の太さを受け持つ
  体格調整用の骨のスケールを小さくする値を、組み合わせの表として持っておく。形状のバリエーションを別に作らないので、
  後から見ても何をしているかが数値で分かる、という考え方。

この部品は、パラメーターの値を下限・上限でclampし、正の側と負の側で別の変化量を持てる一次式にしました(ドリブンキーの
折れ線のうち、0で折れる2本の直線に当たります)。コードは流用していません。

引数
----

* ``parameters``: パラメーターの定義の列。各要素は ``{"name": 名前, "minimum": 下限, "maximum": 上限, "targets": {骨: 量}}`` 。

  * ``name``: 英数字で始まりが英字の名前(containerのアトリビュート名になる)。 ``translate`` ・ ``scale`` ・ ``rest`` ・ ``joint`` で始まる名前は不可。
  * ``minimum`` ・ ``maximum``: 値をclampする範囲(既定 -1・1)。 ``minimum <= 0 <= maximum`` 。
  * ``targets``: 骨(transformまたはjoint)ごとの量の辞書 ``{"translate": (x, y, z), "scale": (x, y, z), "translateNegative": ..., "scaleNegative": ...}`` 。
    値が1のとき(Negativeは-1のとき)の生成時からの変化量で、移動は骨の親の空間、内部の単位(cm)。省略した量は0、
    Negativeを省略すると正の量の符号を反転したもの(0をまたいで同じ傾きの一次式)。

* ``name``: 一意なcontainer名。
* ``connect``: Trueなら出力を骨の ``translate`` ・ ``scale`` へ接続します(既定)。Falseならcontainerの出力だけを作ります。

計算式
------

骨 ``i`` の生成時の移動 ``T0`` ・スケール ``S0`` を定数として持ち、パラメーター ``k`` の値 ``v`` を
``p = clamp(v, 0, maximum)`` (正の部分)と ``n = clamp(-v, 0, -minimum)`` (負の部分の大きさ)に分けます(:meth:`BodyProportion.evaluate`)。

* ``translate<i> = T0 + Σk (p * translate量 + n * translateNegative量)``
* ``scale<i> = S0 + Σk (p * scale量 + n * scaleNegative量)``

全てのパラメーターが0なら骨は生成時のままです(作成時に跳ねません)。生成時の値は ``blendWeighted`` の倍率1の入力として倍精度のまま渡すので、
作成直後の骨の値は元の値と一致します。移動は係数1の ``unitConversion`` で内部の単位(cm)のまま扱うので、UIの長さの単位によらず同じ結果です。

containerのアトリビュート
--------------------------

* ``<名前>`` : パラメーターの値(keyable、既定0)。コントロールの値などで駆動しても構いません。
* ``<名前>Minimum`` ・ ``<名前>Maximum`` : clampの範囲(書き換え可)。
* ``<名前>Translate<i>`` ・ ``<名前>TranslateNegative<i>`` ・ ``<名前>Scale<i>`` ・ ``<名前>ScaleNegative<i>`` : 骨 ``i`` の変化量(keyable、書き換え可)。
* ``translate<i>`` ・ ``scale<i>`` : 骨 ``i`` の出力。 ``restTranslate<i>`` ・ ``restScale<i>`` : 生成時の値。
* ``joint<i>`` : 骨 ``i`` へのmessage(:meth:`BodyProportion.getJoints`)。骨の番号は定義に最初に現れた順です。
* ``parameterNames`` : パラメーター名(:meth:`BodyProportion.getParameters`)。

制限
----

* 回転は扱いません(Euler角の足し算は軸の順番に依存するため)。
* 骨の ``translate`` ・ ``scale`` は出力で駆動されるので、体格調整用の骨にアニメーションのキーは打てません。
  アニメーション用の骨とは分けて、体格調整用の骨(またはその上の階層)に使ってください。
* 変化量はパラメーターの値に比例する一次式(0で折れる)だけです。途中で曲がる形が必要な場合はパラメーターを分けるか、
  ドリブンキーで値を作って ``<名前>`` を駆動してください。
* スケールの量は足し算なので、大きな負の値でスケールが0以下にならないよう範囲を決めてください。

テスト
------

``mlrig/__tests__/test_setup_body_proportion.py`` (``setups`` スイート)で、回転と一様scale 2を持つ胴の下の腕(jointOrient付き)を使い、
作成直後に各jointのワールド行列が変わらないこと(誤差1e-9)、範囲の外を含む乱数15組の値で移動・スケールが独立に計算した値と一致し、
範囲の外は端の値と同じになること、負の側の別の量と省略時の一次式、量と範囲の書き換え、値の取得と設定、 ``connect=False`` と骨の番号の順、
UI単位(mm)で自動の単位変換が入らないこと、所有とUndo/Redo、引数の検査を確かめます。
