歯車の連動(GearTrain)
======================

``mlrig.setups.GearTrain`` は、駆動側の歯車の回転から、続く歯車の回転を歯数の比で求めます(歯車列)。
かみ合う歯車は逆向きに ``前の歯数 / この歯数`` の割合で、同じ軸に固定した歯車は前の歯車と同じ角度で回ります。
機械・時計・乗り物の歯車やプーリーを、駆動側の1つの回転だけでアニメーションできます。
Maya標準ノード(``multiplyDivide`` ・ ``plusMinusAverage`` ・ ``animBlendNodeAdditiveDA``)だけで組み、
独自プラグイン、エクスプレッション、フレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import GearTrain

   # 駆動側24歯 → 12歯とかみ合う → 同じ軸の20歯 → 10歯とかみ合う
   graph = GearTrain.create("driver_gear", ["gear1", "gear2", "gear3"], (24, 12, 20, 10),
                            name="clockGears", axis="z", links=("mesh", "shaft", "mesh"))
   owner = graph.container
   # 各歯車の rotateZ へ出力を接続済み。駆動側の rotateZ を回すだけで全体が回る

``connect=True`` (既定)なら各歯車の ``rotate<axis>`` へ出力を接続します。 ``False`` なら接続せず、
containerの ``rotate<i>`` を自分で使います(別の軸や、表示用の子のノードへ繋ぐ場合など)。

参考にした考え方
----------------

* LinkedIn Learning の講座「Rigging Mechanical Objects in Maya」の「Using expressions to drive gears」:
  32歯の歯車が16歯の歯車を回すと2:1になる、という歯数の比(駆動側の歯数 / 従動側の歯数)で従動側の回転を求め、
  エクスプレッションで駆動する考え方。この部品は同じ比をエクスプレッションではなく標準ノードのDGで求め、
  歯数をアトリビュートにしてすぐに比を変えられるようにしました。
* かみ合う歯車は向きが逆になり、同じ軸に固定した歯車は同じ角度で回る、という一般的な歯車列(複合歯車)の考え方。

いずれもコードは流用していません。

引数
----

* ``driver``: 駆動側の歯車のtransform。ローカルの ``rotate<axis>`` を回します。
* ``gears``: 連動させる歯車のtransform(1個以上)。前から順につながります。
* ``teeth``: 歯数(0より大きい)。先頭が駆動側、続きが ``gears`` の順です。半径(ピッチ円の半径)を入れても比は同じです。
* ``axis``: 全ての歯車のローカルの回転軸(x/y/z)。
* ``links``: 各歯車の1つ前(先頭は ``driver``)とのつながり方。 ``"mesh"`` (かみ合う)または ``"shaft"`` (同じ軸に固定)。省略すると全てmesh。
* ``connect``: Trueなら各歯車の ``rotate<axis>`` へ出力を接続します。既に入力がある場合は ``ValueError`` です。

計算式
------

1. ``ratio0 = 1`` 。かみ合う歯車は ``ratio<i> = -ratio<i-1> * teeth<i-1> / teeth<i>`` 、同じ軸の歯車は ``ratio<i> = ratio<i-1>``
   (:meth:`GearTrain.ratios`)。
2. ``rotate<i> = ratio<i> * (駆動側の rotate<axis> - 生成時の値) + 生成時の歯車の rotate<axis> + phase<i>`` 。

かみ合う2つの歯車は、送った歯の数(歯数×回転角)が同じで向きが逆になります。生成時は駆動側の変化が0なので、
接続しても歯車は跳ねません。角度の加算と比の乗算は ``animBlendNodeAdditiveDA`` (角度のまま ``A * weightA + B * weightB`` を求める標準ノード)で行い、
角度の単位変換ノードを挟まないので、UI単位が度でもラジアンでも同じ結果です。

containerのアトリビュート
--------------------------

* ``teeth0`` (駆動側)〜 ``teeth<n>`` : 歯数(keyable)。変えるとすぐに比が変わります。
* ``phase1`` 〜 ``phase<n>`` : 各歯車に足す角度(keyable)。歯のかみ合わせの見た目を合わせるのに使います。
* ``ratio1`` 〜 ``ratio<n>`` : 駆動側に対する回転の比(確認用)。
* ``rotate1`` 〜 ``rotate<n>`` : 各歯車の回転(出力)。

``gears[i]`` は ``teeth<i+1>`` ・ ``phase<i+1>`` ・ ``ratio<i+1>`` ・ ``rotate<i+1>`` に対応します。

制限
----

* 駆動側はローカルの1軸の回転チャンネル( ``rotate<axis>`` )を読みます。複数軸を同時に回した駆動側の回転(Euler角の混ざり)や、
  ワールドでの回転は扱いません。
* 歯車の位置(軸間距離)は配置しません。歯数に合わせた半径で、かみ合う位置に置くのは利用側です。
* 遊星歯車(軸そのものが公転する歯車)、ラックとピニオン(回転と直線の変換)、ベルトの伸びは扱いません
  (車輪が地面を転がる変換は :doc:`WheelRoll <wheel_roll>` )。
* 比は歯数から求める固定の割合で、歯のバックラッシュ(遊び)や滑りはありません。

テスト
------

``mlrig/__tests__/test_setup_gear_train.py`` (``setups`` スイート)で、初期の回転を持たせた駆動側と4つの歯車(2つ目は同じ軸)を作り、
作成直後に回転が変わらないこと、駆動側を正負・1回転超の角度で回したときに試験側で独立に積み上げた比と一致すること、
かみ合う歯車の送った歯の数(歯数×回転角)が同じで逆向きなこと、歯数・phaseの変更、 ``axis = x`` と先頭がshaftの場合と ``connect=False`` 、
UI単位がラジアンの場合(単位変換ノードが入らないこと)、containerの所有とUndo/Redo(接続も戻る)、引数の検査を確認します。
Maya 2025・2027で確認しています。

検証動画
--------

``tools/demo_gear_train.py`` は、新規シーンに歯数どおりの大きさの4つの歯車(24・12・同じ軸の8・16歯。外周に歯の印の付いた円柱、駆動側は赤、従動側は緑、各歯車の1つの歯が白)を
正面から見る構図で作り、駆動側を回す→逆回転→1回転→phaseを変える→元へ戻す動きで、式と毎フレームの駆動側の角度・各歯車の比と角度・
かみ合う歯の送り量をHUDに表示して録画します。各フレームで回転が式と一致し、かみ合う歯車の送り量が等しいことを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` に保存し、最新のフォルダーを ``latest-gear-train.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_gear_train.py --launch
