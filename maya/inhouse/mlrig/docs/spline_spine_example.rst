スプラインIKの背骨のサンプル
============================

``mlrig.examples.spline_spine`` は、mGear の背骨(``spine_S_shape_01``)に近い操作感の背骨を、
Maya標準ノードと :doc:`spline_ik` で作るサンプルです。骨盤から胸までの骨列を、4つのコントローラー
(腰・腰側の接線・胸側の接線・胸)をCVとする3次カーブに沿わせ、その上に関節ごとのFKコントローラーを
階層で重ねます。毎フレームのPython実行や独自プラグインは使いません。

.. code-block:: python

   from mlrig.examples import spline_spine

   spine = spline_spine.build(name="spine", joint_count=6, length=50.0, height=100.0)
   spine.chest       # 胸のコントローラー
   spine.deform      # スキンに使う骨(根元から順)

``joint_count`` は末端の胸を含む骨の数(4〜32)、``length`` は腰から胸までの長さ、``height`` は腰の高さです。
背骨はワールドの +Y 方向に作り、骨は「X が上(子の方向)、Z が正面」を向きます。
作成は1回の Undo で取り消せます。``<name>_rig`` が既にある名前は使えません。

シンプル版(伸縮なし)
--------------------

``stretch=False`` を渡すと、伸縮と体積の保持を入れないシンプル版を作ります。

.. code-block:: python

   simple = spline_spine.build(name="simpleSpine", joint_count=6, length=50.0, height=100.0, stretch=False)

* ``maxStretch``・``maxSquash``・``volume`` のアトリビュートと、カーブの長さ・比・体積の計算ノードを作りません。
* 骨の長さは作成時のまま固定です。胸を遠ざけても骨は伸びず、一番上の骨は胸に届きません。
  胸を近づけると、カーブより長い分は終点の先へはみ出します。
* カーブ・接線・FK・ねじれの配分・向きの固定(``lockOri*``)・接線の倍率(``tangent*``)は通常版と同じです。

構成
----

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - ノード
     - 役割
   * - ``<name>_cog_ctrl``
     - 全体を動かす。下記のアトリビュートもここに置く
   * - ``<name>_hips_ctrl``
     - 腰。カーブの始点(mGear の ``ik0``)
   * - ``<name>_tan0_ctrl``
     - 腰側の接線。腰の子で、移動だけ操作できる
   * - ``<name>_tan1_ctrl``
     - 胸側の接線。胸の子で、移動だけ操作できる
   * - ``<name>_chest_ctrl``
     - 胸。カーブの終点(mGear の ``ik1``)
   * - ``<name>_fk01_ctrl`` …
     - 関節ごとのFK。スプラインIKの結果の上に階層で重なり、下の段を回すと上の段が一緒に動く
   * - ``<name>_setup_grp``
     - 非表示。スプラインIKの骨列・カーブ・ハンドル
   * - ``<name>_deform_grp``
     - 変形用の骨。FKコントローラーへ追従する。スキンにはこの骨を使う

アトリビュート(``<name>_cog_ctrl``)
-----------------------------------

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - 名前
     - 既定
     - 内容
   * - ``maxStretch``
     - 1.5
     - 伸びの上限(元の長さに対する比)。超えると骨列は胸のコントローラーに届かない
   * - ``maxSquash``
     - 0.5
     - 縮みの下限
   * - ``volume``
     - 1
     - 体積の保持の強さ(0〜1)。伸びると細く、縮むと太くなる
   * - ``lockOriHips``・``lockOriChest``
     - 1
     - 1 なら最下段・最上段の骨の向きを腰・胸のコントローラーの回転に合わせる。0 ならカーブの接線に沿う
   * - ``tangentHips``・``tangentChest``
     - 1
     - 接線のコントローラーまでの長さの倍率。0 で接線が無くなる

計算
----

* **カーブ**: 4つのコントローラーのワールド位置を、そのまま3次カーブのCVにする(:doc:`spline_ik`)。
  腰・胸のコントローラーのワールド行列を、スプラインIKのねじれ(Advanced Twist)の両端にする。
  胸を骨の軸(Y)で回すと、ねじれが根元から胸へ徐々に配分される。
* **伸縮**: 比 = カーブの長さ ÷ (元の長さ × リグの拡大率)。この比を ``maxSquash``〜``maxStretch`` に収め、
  スプラインIKの各骨の長さ(``translateX``)に掛ける。
* **体積**: 断面の拡大率 = 1 + ``volume`` × 重み × (比\ :sup:`-0.5` − 1)。重みは sin(π × 段 ÷ (段数 − 1)) で、
  両端は0、中央で1。変形用の骨の ``scaleY``・``scaleZ`` に入れる。
* **向きの固定**: 作成時の「骨とコントローラーの回転の差」を保ったまま、最下段・最上段の骨の回転をコントローラーへ
  寄せた行列を作り、blendMatrix で元の向きと ``lockOri*`` の割合で混ぜる。位置はスプラインIKのまま。
* **FK**: 各段のオフセットは「一つ下の段から見たスプラインIKの段」の行列(``offsetParentMatrix``)で動き、
  その子のFKコントローラーの回転が上の段へ伝わる。
* **変形用の骨**: 各FKコントローラーのワールド行列を ``offsetParentMatrix`` に入れて追従させる。

mGear との違い・制限
--------------------

* 変形用の骨は ``<name>_deform_grp`` の直下に平らに並べる(親子の階層にしない)。
  階層が必要なエンジン向けには、書き出し用の骨を別に用意して拘束する。
* mGear の ``position``(骨列をカーブ上でずらす)、``softness``、``autoBend``(sideBend・frontBend)、
  中央の接線(``centralTangent``)、伸縮・体積の曲線(プロファイル)の編集は用意していない。体積の重みは sin で固定。
* 伸縮の比はリグのルートの ``scaleY`` で割る。ルートを均一でない拡大率で拡大する使い方は想定していない。
* 接線と上方向が平行になる姿勢、骨の軸を大きく超えるねじれ(多回転)は、:doc:`spline_ik` と同じく扱えない。
* 左右の概念は無い(体の中心の部位用)。

コンストレイントで組む簡易版
----------------------------

``mlrig.examples.spline_spine_simple`` は、同じ背骨をノードの構成が追いやすい形で組み直した簡易版です。

.. code-block:: python

   from mlrig.examples import spline_spine_simple

   spine = spline_spine_simple.build(name="spine", joint_count=6, length=50.0, height=100.0)

通常版との違いは次の3点です。コントローラーの階層・名前・アトリビュートの意味・動きは通常版と同じで、
同じ姿勢を付けたときの変形用の骨のワールドマトリクスは一致します。

* コンテナを使いません。カーブとIKハンドルは ``spine_setup_grp`` の下に直接作ります(:doc:`spline_ik` を使わない)。
* マトリクスのノード(``multMatrix``・``decomposeMatrix``・``pickMatrix``・``blendMatrix``)を使わず、追従はコンストレイントで行います。

  * CV: ``spine_cv0``〜``cv3`` を腰・接線・胸へ pointConstraint し、その ``translate`` をカーブの CV へつなぐ。
  * 向きの固定: ``spine_hipsLock``・``spine_chestLock`` の位置はIKの骨への pointConstraint、向きは
    IKの骨と腰・胸のコントローラーの2つへの parentConstraint(``maintainOffset``、translate はスキップ)で決める。
    ウェイトは ``lockOri*`` と ``1 - lockOri*``。parentConstraint のオフセットはターゲットごとに別なので、
    コントローラーと骨の軸の違い(コントローラーは Y が上、骨は X が上)を吸収できる
    (orientConstraint の ``maintainOffset`` はターゲット全体で1つのオフセットになり、ウェイトを変えるとずれる)。
  * FK: 一つ下の段の子にした ``spine_fk02_local`` 等をその段へ parentConstraint し、その ``translate``\ ・
    ``rotate`` を FK のオフセット(npo)へつなぐ。FK の親を回すと上の段も一緒に回る。
  * 変形用の骨: FK コントローラーへ parentConstraint する。

* 接線の倍率(``tangentHips``・``tangentChest``)を作りません。接線のコントローラーは残します。

FKコントローラーなし
~~~~~~~~~~~~~~~~~~~~

``fk=False`` を渡すと、FKコントローラー(``spine_fk_grp`` 以下)と向きの固定の割合(``lockOri*``)を作りません。
最下段・最上段の骨の向きは、常に腰・胸のコントローラーに合わせます(``lockOri* = 1`` と同じ)。

* 最下段: 腰のコントローラーへ parentConstraint(``maintainOffset``)。IKの根元は常にカーブの始点(腰の位置)にあるので、位置も腰から取れる。
* 最上段: 位置はIKの骨への pointConstraint、向きは胸のコントローラーへの orientConstraint(``maintainOffset``)。
  伸縮の上限や ``stretch=False`` で骨が胸に届かないことがあるので、位置は胸から取らない。
* 中間: IKの骨へ parentConstraint。

ターゲットが1つなので、コントローラーと骨の軸の違いは ``maintainOffset`` のオフセットで吸収できます。
``spine_hipsLock``・``spine_chestLock`` と reverse ノードも作りません。FKを回さず ``lockOri* = 1`` のときのFKあり版と
同じ動きです。``spine.fk`` は空のリストになります。

.. code-block:: python

   noFk = spline_spine_simple.build(name="noFkSpine", fk=False)

``stretch=False`` も通常版と同じに使えます。ねじれはスプラインIKのハンドルの ``dWorldUpMatrix``\ ・
``dWorldUpMatrixEnd`` へ腰・胸の ``worldMatrix`` をつないで取ります(ハンドルの入力で、マトリクスのノードではない)。

テスト
------

``mlrig/__tests__/unit/examples/test_splineSpine.py``\ (``setups`` スイート)で、基準姿勢・伸縮と上限下限・体積・
ねじれの配分・向きの固定・FK・接線の倍率・Undo を、実際の行列で確かめています。
簡易版は ``mlrig/__tests__/unit/examples/test_splineSpineSimple.py`` で、同じ内容(接線の倍率を除く)と、
コンテナ・マトリクスのノードを作らないこと・腰側の向きの固定・リグ全体の拡大と、
``fk=False`` でFKのノードを作らずFKあり版と同じ姿勢になることを確かめています。

検証動画
--------

``python tools/demo_spline_spine.py --launch``\ (Maya 2027 の ``mayapy`` で実行)で、使い捨ての隔離した Maya GUI を
起動して録画します。作業中の Maya には触れません。胸を上げて伸ばす → 上限 1.5 を超えて止まる → 縮める →
前へ曲げる(向きの固定)→ 胸を60度ねじる → 腰と胸を左右にずらしてS字にする → FK を足す → 元に戻す、の順に
384フレーム(24fps)を記録し、各フレームで次の値を独立計算と比べます。

* 骨の長さ = 10 cm × clamp(カーブの長さ ÷ 50, 0.5, 1.5)(DGの ``translateX`` と、変形用の骨の間隔)
* 中央の骨の断面の拡大率 = 1 + ``volume`` × 重み × (比\ :sup:`-0.5` − 1)
* ``lockOriChest`` = 1 のとき、最上段の骨の X 軸と胸のコントローラーの Y 軸の角度が 0.05 度未満
* 比が範囲内で FK を回していないとき、最上段の骨と胸のコントローラーの距離が 0.25 cm 以内
  (骨は線分なので、曲がりが強いとカーブの端から少しずれる)

``--simple`` を付けるとシンプル版を録画します(胸を15cm上げても骨が伸びない → 前へ曲げる → ねじる → S字 →
FK → 戻す、312フレーム)。各フレームで骨の長さが 10 cm のまま・断面の拡大率が 1 のまま・向きの固定が保たれることを
確かめます。

動画と診断は ``.maya-output/verification/<実行ID>/`` に保存します(Git には登録しません)。
