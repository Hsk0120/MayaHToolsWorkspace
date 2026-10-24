ピストン(Piston)
================

``mlrig.setups.Piston`` は、油圧シリンダーやサスペンションのように、両端の部品(シリンダーとロッド)が
互いを向き続ける行列を出力します。両端の距離・基準からの伸縮量・ストロークの範囲を超えた量も出力するので、
機械のリグやメカニカルな部品の確認、補正のドライバーに使えます。
Maya標準ノード(``aimMatrix`` ・ ``multMatrix`` ・ ``distanceBetween`` など)のみで構築し、
独自プラグインやフレームごとのPythonは使いません。

.. code-block:: python

   from mlrig.setups import Piston

   graph = Piston.create(
       "cylinder_mount", "rod_mount", name="frontPiston",
       aimAxis="x", upAxis="y", minimum=6.5, maximum=11.0,
   )
   owner = graph.container
   # 各端の入力と同じ親の下の、TRSがidentityの出力transformへ接続する
   owner.getPlug("baseMatrix").connectTo("cylinder_out.offsetParentMatrix")
   owner.getPlug("tipMatrix").connectTo("rod_out.offsetParentMatrix")

各端のtransformは回転中心を取付け位置に置きます。両端は別々の親の下にあってかまいません
(例: シリンダーは車体、ロッドはサスペンションアーム)。

引数
----

* ``base``: シリンダー側のtransform。
* ``tip``: ロッド側のtransform。
* ``aimAxis``: 相手へ向ける基準の軸。x/y/z、既定はx。生成時の向きとの差だけを使うので、
  部品の軸が生成時にちょうど相手を向いていなくても、出力は跳ねません。
* ``upAxis``: 上方向を揃える軸。 ``aimAxis`` と異なる軸、既定はy。
* ``minimum`` ・ ``maximum``: 最も縮んだとき・伸びたときの両端の距離(cm)。
  省略すると生成時の距離の0.5倍・1.5倍です。

``minimum`` ・ ``maximum`` はcontainerのアトリビュートとして、生成後も変更できます。

計算式
------

基準は生成時の姿勢です。

1. 共通の上方向 ``up`` : 生成時の ``base`` の ``upAxis`` を、 ``base`` の親の空間(offsetParentMatrixを含む)のベクトルとして固定します。
2. 各端で ``aimMatrix`` (primaryMode=Aim、secondaryMode=Align)を使い、現在のワールド行列を入力に、
   ``aimAxis`` を相手の位置へ向け、 ``upAxis`` を ``up`` へ揃えた行列 ``A`` を求めます。位置は入力のままです。
3. 生成時の差 ``C = W0 · A0⁻¹`` ( ``W0`` は生成時のワールド行列、 ``A0`` は生成時の ``A`` )を定数で持ち、
   出力 = ``C · A · (親のworldInverseMatrix)`` 。生成直後は ``C · A0 = W0`` なので入力と一致します。
4. ``length`` = 両端の距離、 ``extension = length - restLength`` 、
   ``overStroke = max(length - maximum, 0) - max(minimum - length, 0)`` (cm)。

両端の ``upAxis`` を同じ ``up`` へ揃えるため、両端を結ぶ線が動いても、シリンダーとロッドは互いにねじれず、
両端を結ぶ線と ``up`` が張る平面に乗ります。

出力
----

* ``baseMatrix`` ・ ``tipMatrix``: 各端の、入力と同じ親の空間の行列。
* ``length``: 両端の現在の距離(cm)。
* ``restLength``: 生成時の距離(cm)。
* ``extension``: 生成時からの伸縮量(cm、伸びると正)。
* ``overStroke``: ストロークの範囲を超えた量(cm、伸びすぎは正、縮みすぎは負、範囲内は0)。

距離の出力は、UIの長さ単位によらず常にcmです。

制限
----

* ストロークの範囲は ``overStroke`` の値として出力するだけで、両端の位置は制限しません。
  範囲内に収めるには、 ``overStroke`` をドライバーにするか、アニメーション側で両端を動かしてください。
* 両端を結ぶ線が ``up`` と平行になる姿勢では、上方向が決まらず向きが不定になります。
* ロッドの長さ(見た目のめり込み・抜け)の判定は行いません。
* 負・非一様scaleは対象外です。
* 出力を別の親の下へ直接接続したり、非identityのTRSへ重ねたりすると二重変換になります。

テスト
------

``mlrig/__tests__/test_setup_piston.py`` (``setups`` スイート)で、回転・移動した親の下の、
相手を向いていない向きで生成した両端について、生成直後に出力が入力と一致すること、
相手側の親を回転・移動しても両端が互いを向き位置が入力のままであること、両端の上方向が共通の平面に乗ること、
``overStroke`` の符号と範囲の変更、UIの長さ単位がmの場合、引数の検査、生成のUndoを、OpenMayaで求めた期待値と比べます。
Maya 2025・2027で確認しています。

検証動画
--------

``tools/demo_piston.py`` は、新規シーンに固定台とアーム(灰)、入力の向きのままの部品(赤・半透明)、
出力のシリンダー(濃い緑)とロッド(薄い緑)を正面から見る構図で作り、式と毎フレームの入力値・DG出力をHUDに表示して録画します。
``minimum=6.5`` ・ ``maximum=11`` で、アームを回してロッドを伸ばす→最大を超える位置で保持→戻す→縮める→最小を超える位置で保持→基準への復帰を、
324フレーム・24fpsで記録します。各フレームで、 ``length`` ・ ``extension`` ・ ``overStroke`` が独立計算と一致すること、
両端の出力の+Xが相手を向くこと(角度の誤差)、位置が入力と一致することを判定します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` (``verification.mp4`` ・ ``result.json`` ・
``piston.ma``)に保存し、最新のフォルダーを ``latest-piston.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_piston.py --launch
