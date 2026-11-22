スチュワートプラットフォーム(StewartPlatform)
==============================================

``mlrig.setups.StewartPlatform`` は、伸縮する脚(ふつう6本)で天板を支えるスチュワートプラットフォーム(パラレルリンクの
台)の脚の動きを求めます。フライトシミュレーターやドライビングシミュレーターの揺れる台、ロボットの6軸の台、望遠鏡の
副鏡の支持などの形です。天板のtransformを自由に動かす・回すだけで、脚ごとの長さ・行程の中の位置・範囲を超えた量が
決まり、シリンダーが相手の取り付け点を向き、ロッドがその点まで進みます。Maya標準ノード(``distanceBetween`` ・
``aimMatrix`` ・ ``multMatrix`` ・ ``decomposeMatrix`` ・ ``animBlendNodeAdditive`` ・ ``condition`` ・ ``unitConversion`` と、
Maya 2026以降の ``clampRange`` ・ ``divide`` ・ ``absolute`` ・ ``max``)だけで組み、独自プラグイン、エクスプレッション、
フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import StewartPlatform

   # 台座の子の取り付け点6つ、天板の子の取り付け点6つ、シリンダー6つ、各シリンダーの子のロッド6つ
   graph = StewartPlatform.create(baseAnchors, platformAnchors, cylinders, rods, minimum=3.0, maximum=6.0,
                                  name="motionBase")
   owner = graph.container
   # 天板を動かすと owner.length[i]・owner.excess[i]・owner.reachable が変わり、シリンダーとロッドが追従する

``cylinders`` ・ ``rods`` を省くと、長さと超過だけを出力します。 ``connect=False`` なら接続せず、containerの
``cylinderMatrix[i]`` ・ ``clampedLength[i]`` を自分で使います。

参考にした考え方
----------------

* スチュワートプラットフォーム(Gough-Stewart platform)は、台座と天板を6本の直動の脚で結び、脚の長さだけで天板の
  6自由度を決める機構です(https://en.wikipedia.org/wiki/Stewart_platform)。
* 天板の姿勢から脚の長さを求める逆運動学は、取り付け点どうしの距離を測るだけの閉じた式です。脚の長さから天板の姿勢を
  求める順運動学は反復計算が要るため、このセットアップは逆運動学(天板が入力)だけを扱います。
* 式は自分で確かめたもので、コードは流用していません。

引数
----

* ``baseAnchors``: 台座側の取り付け点のtransformのlist。台座の子に置きます。
* ``platformAnchors``: 天板側の取り付け点のtransformのlist(同じ数)。天板の子に置きます。i 番目どうしを脚で結びます。
* ``cylinders``: シリンダーのtransformのlist(同じ数、省略可)。台座側の取り付け点の位置へ移し、ローカルの ``aimAxis`` を
  天板側の取り付け点へ向けます。jointは使えません(jointOrientを含めて分解しないため)。
* ``rods``: ロッドのtransformのlist(同じ数、省略可)。i 番目のシリンダーの子に置きます。ローカルの
  ``translate<aimAxis>`` を止めた脚の長さにするので、範囲内ではロッドの原点が天板側の取り付け点に重なります。
  ロッドの形は原点からシリンダーの側(``aimAxis`` の負の向き)へ伸ばして作ります。
* ``minimum`` ・ ``maximum``: 脚の長さの範囲(cm)。省略すると、生成時の最も短い脚の0.75倍・最も長い脚の1.25倍です。
  containerの ``minimum`` ・ ``maximum`` で後から変えられます。
* ``aimAxis`` ・ ``upAxis``: シリンダーのローカルで相手へ向ける軸と、台座側の取り付け点の同じ軸へ寄せる軸(x/y/z、別の軸)。
* ``connect``: Trueならシリンダーの translate・rotate とロッドの ``translate<aimAxis>`` へ出力を接続します。既に入力が
  ある場合は ``ValueError`` です。

計算式
------

脚 i の台座側の取り付け点のワールド位置を ``B_i`` 、天板側を ``P_i`` とします。

1. ``length[i] = |P_i - B_i|`` (``distanceBetween``)。 ``extension[i] = length[i] - restLength[i]``
   (``restLength[i]`` は生成時の長さ)。
2. ``clampedLength[i] = clamp(length[i], minimum, maximum)`` 、 ``excess[i] = length[i] - clampedLength[i]``
   (伸びすぎは正、縮みすぎは負、範囲内は0)。
3. ``stroke[i] = (length[i] - minimum) / (maximum - minimum)`` (行程の中の位置。止めないので範囲外では0未満・1超)。
4. ``maxExcess = max_i |excess[i]|`` 、 ``reachable = (maxExcess <= 0)`` (すべての脚が範囲内なら1)。
5. ``cylinderMatrix[i]`` : 台座側の取り付け点のワールドマトリクスを、 ``aimAxis`` が ``P_i - B_i`` を向き、 ``upAxis`` が
   取り付け点の ``upAxis`` から脚の向きの成分を除いた向きになるよう回したもの(``aimMatrix``)。シリンダーへは
   ``cylinderMatrix[i] × シリンダーの親の逆`` を分解した translate・rotate を接続します。
6. ロッドの ``translate<aimAxis> = clampedLength[i]`` 。範囲を超えると、ロッドの原点は天板側の取り付け点から
   ``|excess[i]|`` だけ離れます。

履歴を持たない閉じた式なので、天板をどの順に動かしても同じ値になります。台座を動かしても、取り付け点のワールド位置を
使うので正しく追従します。数値の加算は ``animBlendNodeAdditive`` で倍精度のまま行い、長さの型の入出力には係数を
明示した ``unitConversion`` を挟んで、UI単位(mm等)に関係なく同じ結果にします。

containerのアトリビュート
--------------------------

* ``minimum`` ・ ``maximum`` : 脚の長さの範囲(keyable)。
* ``length[i]`` ・ ``extension[i]`` ・ ``clampedLength[i]`` ・ ``excess[i]`` ・ ``stroke[i]`` : 脚ごとの長さ・生成時からの
  伸び・止めた長さ・超過・行程の中の位置。
* ``cylinderMatrix[i]`` : シリンダーのワールドマトリクス。
* ``maxExcess`` ・ ``reachable`` : 超過の最大と、すべての脚が範囲内かどうか。
* ``restLength[i]`` ・ ``legCount`` : 固定の値。

制限
----

* 天板は止めません。脚が範囲を超える姿勢でも天板は入力のまま動き、ロッドの先が取り付け点から離れることと ``excess[i]`` ・
  ``reachable`` で超過を示します。天板を範囲内へ引き戻す処理(反復が要る)は作りません。
* 脚の長さから天板の姿勢を求める順運動学は扱いません。
* 脚が台座側の取り付け点の ``upAxis`` と平行になると、シリンダーの軸まわりの向きが不定です。 ``upAxis`` は脚と
  平行にならない向き(台座の面に沿う向き)へ置きます。
* 生成時にシリンダーは台座側の取り付け点へ移ります(生成時の姿勢との差は保ちません)。
* 取り付け点・シリンダーの親の scale は1を前提とします。シリンダーにjoint・ピボット・rotateAxisは使えません。
* 脚どうし・脚と天板の干渉、取り付け点の継手の角度の限界は見ません。
* Maya 2026以降の数学ノードを使うため、Maya 2025以前では作れません。

テスト
------

``mlrig/__tests__/inMaya/unit/setups/test_stewartPlatform.py`` (``setups`` スイート)で、作成直後の値と固定の値、回した親の
下で天板を6自由度で動かしたときの ``length`` ・ ``extension`` ・ ``stroke`` が試験側で独立に測ったワールドの距離に
一致すること、シリンダーが取り付け点の位置にあり軸が相手を向き ``upAxis`` が取り付け点の軸に寄ること、範囲内で
ロッドの原点が天板側の取り付け点に重なること、範囲を超えたときの止まり・ ``excess`` ・ ``maxExcess`` ・ ``reachable`` と
一部の脚だけが超える姿勢・戻したときの復帰、 ``minimum`` ・ ``maximum`` の変更、Python版
( :meth:`StewartPlatform.legs` )との一致、台座・親を動かしたときの追従、 ``aimAxis = x`` とシリンダー無し・接続なし、
containerの所有とUndo/Redo、引数の検査を確認します。Maya 2027で確認しています。

検証動画
--------

``tools/demo_stewart_platform.py`` は、新規シーンに台座(灰色)・天板(赤、入力)・6本のシリンダー(青)とロッド(緑、出力)・
天板側の取り付け点(橙)を斜め上から見る構図で作り、天板を上下・水平移動・傾け・ひねり→範囲を超えて持ち上げる→元へ
戻す動きで、式と毎フレームの入力・各脚の長さ・行程・超過をHUDに表示して録画します。各フレームで脚の長さが
ワールドの距離に一致すること、ロッドの先と取り付け点の距離が超過に一致すること、シリンダーが相手を向くこと、DGと
Python版の一致を判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを
``latest-stewart-platform.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_stewart_platform.py --launch
