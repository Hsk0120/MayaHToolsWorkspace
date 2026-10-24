回転最小化フレーム(RotationMinimizingFrames)
==============================================

``mlrig.setups.RotationMinimizingFrames`` は、曲線やチェーンに沿って並んだ点列の各点に、
接線まわりの余計な回転(ねじれ)がほとんど生じないフレーム(回転最小化フレーム、RMF)を出力します。
スプラインIK・リボン・マトリクススプラインのアップベクトルや、ねじれの分配の基準に使えます。
固定の上方向ベクトルで向きを決める方法(aimConstraintのworld up等)は、接線が上方向と平行に近づくと
向きが急に裏返りますが、RMFは前の点のフレームを次の点へ運ぶので裏返りません。
Maya標準ノード(``vectorProduct`` ・ ``plusMinusAverage`` ・ ``multiplyDivide`` ・ ``condition`` ・ ``fourByFourMatrix`` など)のみで構築し、
独自プラグインやフレームごとのPythonは使いません。

参考にした論文と考え方
----------------------

Wenping Wang, Bert Jüttler, Dayue Zheng, Yang Liu「Computation of Rotation Minimizing Frames」
(ACM Transactions on Graphics 27(1), 2008)の **double reflection法** を使います。
前の点のフレームを、2回の鏡映で次の点へ運ぶ方法です。

1. 1回目: 2点を結ぶ弦 ``v1 = x[i+1] - x[i]`` に垂直な平面で、基準ベクトル ``r`` と接線 ``t`` を鏡映します。
   これで点 ``x[i]`` が点 ``x[i+1]`` へ移ります。
2. 2回目: 鏡映後の接線 ``t_L`` を次の点の接線 ``t[i+1]`` に重ねる鏡映を行い、基準ベクトルにも同じ鏡映をかけます。

2回の鏡映を合わせると回転になります。論文では、この方法は1ステップあたりの計算量が少なく、
局所誤差がステップ幅の4乗のオーダー(4次精度)になると示されています。
論文の公開コードは使わず、論文の式から標準ノードで組み立てました。
mlrigの論文調査メモ(ローカルの ``docs/research/rig-research-papers-2026-10-09.md`` の4-3)で、
「固定サンプル数の前向き連鎖なのでvectorProduct等で組める」とした候補を実装したものです。

.. code-block:: python

   from mlrig.setups import RotationMinimizingFrames

   points = ["spine_pt0", "spine_pt1", "spine_pt2", "spine_pt3", "spine_pt4"]
   graph = RotationMinimizingFrames.create(points, name="spine_rmf", upAxis="y", keepOffset=True)
   owner = graph.container
   # 出力はワールド行列。ワールド直下のtransform(またはjoint)のoffsetParentMatrixへ接続する
   for index in range(len(points)):
       owner.getPlug("matrix" + str(index)).connectTo("spine_out{}.offsetParentMatrix".format(index))

NURBS曲線から作る(fromCurve)
----------------------------

``RotationMinimizingFrames.fromCurve`` は、transformの点列の代わりにNURBS曲線を受け取り、
曲線上の点の位置と **曲線の接線** (``pointOnCurveInfo`` の ``normalizedTangent``)から同じdouble reflectionでフレームを作ります。
点列の差分で接線を近似しないので、両端を含む全ての点でフレームのXが曲線の接線と一致します。

.. code-block:: python

   from mlrig.setups import RotationMinimizingFrames

   graph = RotationMinimizingFrames.fromCurve(
       "spine_crv", 7, name="spine_crv_rmf", upNode="spine_root_ctl", upAxis="y",
   )
   owner = graph.container
   for index in range(7):
       owner.getPlug("matrix" + str(index)).connectTo("spine_out{}.offsetParentMatrix".format(index))

* ``curve``: NURBS曲線のtransform、またはnurbsCurveシェイプ。シェイプの ``worldSpace[0]`` を使うので、位置・接線はワールドです。
* ``count``: 点の数(3以上)。点は ``turnOnPercentage`` でパラメーターの範囲を等分した位置 ``u = i/(count-1)`` です
  (弧長の等分ではありません。CVの間隔が不均一な曲線では点の間隔も不均一になります)。
* ``upVector``: 最初の点の上方向(ワールド、既定(0, 1, 0))。 ``upNode`` を指定しない場合に使います。
* ``upNode`` ・ ``upAxis``: 指定すると、そのtransformの ``upAxis`` (ワールド)を最初の点の上方向にします。根元のねじりを操作するコントローラーに使います。

``keepOffset`` はありません(入力にtransformが無いため)。出力は接線をX・基準ベクトルをYとするフレームそのものです。

既存のSplineIK・リボンへのつなぎ方の例
--------------------------------------

次は使い方の例で、既存の :doc:`spline_ik` などのモジュールの挙動は変えていません。

* **スプラインIKのアップベクトルの代わり**: ``ikSplineSolver`` の Advanced Twist を使わず、IK用の曲線から ``fromCurve`` でフレームを作り、
  各jointと同じ数の出力を、ワールド直下に置いた結果jointの ``offsetParentMatrix`` へ接続します。
  jointの長さは曲線のパラメーターの等分で決まるため、弧長に沿った配置が必要なら、点を ``motionPath`` (fractionMode)で弧長等分に置いたtransformの点列から ``create`` を使います。
* **リボン**: NURBSサーフェスの代わりに、中心の曲線から ``fromCurve`` で作ったフレームのY(基準ベクトル)方向へ幅を持たせると、
  ねじれの少ない帯になります。両端のねじりを合わせる場合は、出力の上に :doc:`twist_distribution` を重ねます。

引数
----

* ``nodes``: 曲線・チェーンに沿って並んだ3つ以上のtransform。位置だけを使います(motionPathで曲線に乗せたtransform等)。
* ``upAxis``: 最初のtransformのローカルで、上方向として使う軸。x/y/z、既定はy。
  最初のtransformを接線まわりに回すと、全てのフレームが同じ角度だけねじれます(根元でねじりを操作できる)。
* ``keepOffset``: Trueなら、生成時の各transformのワールド行列とフレームの差を保ち、生成直後の出力を入力と一致させます(既定)。
  Falseなら、接線をX・基準ベクトルをYとするフレームそのものを出力します。

計算式
------

``x[i]`` を各点のワールド位置(cm)とします。

1. 単位接線 ``t[i]``: 間の点は中心差分 ``x[i+1] - x[i-1]`` 、両端は片側差分を正規化します。
2. 最初の基準ベクトル ``r[0]``: 最初のtransformの ``upAxis`` から ``t[0]`` の成分を除いて正規化します。
3. ``i → i+1`` (double reflection):

   * ``v1 = x[i+1] - x[i]`` 、 ``c1 = v1·v1``
   * ``r_L = r[i] - (2/c1)(v1·r[i]) v1`` 、 ``t_L = t[i] - (2/c1)(v1·t[i]) v1``
   * ``v2 = t[i+1] - t_L`` 、 ``c2 = v2·v2``
   * ``r[i+1] = r_L - (2/c2)(v2·r_L) v2`` (正規化。 ``c2`` が1e-10未満なら鏡映しない)

4. フレーム ``F[i]`` の行は X= ``t[i]`` 、Y= ``r[i]`` 、Z= ``t[i]×r[i]`` 、位置 ``x[i]`` 。
5. ``keepOffset=True`` では 出力 = ``(生成時のワールド行列 · 生成時のF[i]⁻¹) · F[i]`` 。

位置は ``vectorProduct`` (Point Matrix Product)で各transformのワールド行列から原点を変換して取り出すので、
UIの長さ単位によらずcmで計算します。

出力
----

* ``matrix0`` 〜 ``matrixN-1``: 各点のワールド行列。ワールド直下のtransformの ``offsetParentMatrix`` へ接続します。

制限
----

* 接線は点列の差分による近似です。点の間隔が粗く急に曲がる場合や、片側差分を使う両端では、
  曲線の本当の接線とずれます。テストでは1点あたり約54度回るらせんで、20倍に細かく分割した参照と比べると、
  最初の基準ベクトルが約16〜18度ずれ(接線の近似の違いによる)、両端は片側差分のため2〜4度ずれますが、
  間の点のねじれの増え方の差は1度未満でした。
* ``vectorProduct`` などは単精度(float)で計算するため、倍精度のPython版と最大0.03度程度の差が出ます(録画で最大0.028度)。
* 最初のtransformの ``upAxis`` が最初の接線と平行だと、最初の基準ベクトルが決まりません。
* 回転最小化は「接線まわりのねじれを増やさない」性質で、両端のねじれを指定した値に合わせる処理(ねじれの分配)は行いません。
  両端を合わせたい場合は、出力の上に :doc:`twist_distribution` などを重ねてください。
* 点の数は生成時に固定です。ノード数は点の数に比例します(1点あたり約30ノード)。

テスト
------

``mlrig/__tests__/test_setup_rotation_minimizing_frames.py`` (``setups`` スイート)で、
生成直後に出力が入力と一致すること(keepOffset)、点を3通りに動かしてもDGのフレームがPython版のdouble reflectionと一致し
正規直交であること、平面曲線で最初の基準ベクトルが法線なら全ての点で法線のままであること(回転最小化の性質)、
粗い点列と細かく分割した参照とのねじれの増え方の差、接線が真上を通る半円で隣り合う基準ベクトルの角度が接線の曲がりを超えないこと、
根元のねじりが全てのフレームへ同じ角度で伝わること、UIの長さ単位がmの場合、引数の検査、生成のUndoを確認します。
``CurveRotationMinimizingFramesTest`` で ``fromCurve`` について、回転・移動したtransformの下の3次曲線で、
DGのフレームが ``cmds.pointOnCurve`` で独立に求めた位置・接線からのPython版と一致し、両端を含めXが曲線の接線と一致すること、
CVを動かした変形への追従、 ``upNode`` のねじりが全てのフレームへ同じ角度で伝わること、平面曲線で法線を保つこと、
UIの長さ単位がmの場合、引数の検査、生成のUndoを確認します。
Maya 2025・2027で確認しています。

検証動画
--------

``tools/demo_rotation_minimizing_frames.py`` は、9点の点列(黄の線)に沿って、RMFのフレーム(緑の板。板の長い向きと先端の球が基準ベクトル ``r`` )と、
比較用に固定の上方向(ワールドY)から作ったフレーム(赤・半透明。録画のPythonで計算した表示だけで、リグには含まない)を並べて録画します。
直線(生成時)→接線が両端で真上を通る半円→らせん→3次元の波→直線への復帰を、312フレーム・24fpsで記録します。
各フレームで、DGのフレームがPython版のdouble reflectionと0.05度未満で一致すること(単精度のため)、 ``t`` と ``r`` が直交することを判定します。
HUDには、比較用の固定の上方向のフレームで隣り合う ``r`` が1ステップで回る角度も表示し、らせんへの変形中に最大約147度裏返ることを示します。

新規シーンを作るため、作業中のMayaへは送りません。次のコマンドは隔離した使い捨てのMaya 2027 GUIを起動して録画し、
終了後に閉じます。結果は ``.maya-output/verification/<実行ID>/`` (``verification.mp4`` ・ ``result.json`` ・
``rotation-minimizing-frames.ma``)に保存し、最新のフォルダーを ``latest-rotation-minimizing-frames.json`` に記録します。

.. code-block:: powershell

   $env:MAYA_VERIFICATION_FFMPEG = "C:/path/to/ffmpeg.exe"
   python tools\demo_rotation_minimizing_frames.py --launch

``tools/demo_rotation_minimizing_frames_curve.py`` は、6つのCVを動かす3次のNURBS曲線(黄)について、
``fromCurve`` のフレーム(緑)と、同じ9点に置いたtransformから ``create`` で作ったフレーム(赤・半透明、差分の接線)を並べて録画します。
直線→両端を上げる→3次元のS字→コイル→直線への復帰を、264フレーム・24fpsで記録します。
各フレームで、DGのフレームが曲線の接線を使うPython版と0.05度未満で一致すること(実測は最大0.00004度)、
フレームのXと曲線の接線の差が0.05度未満であること(実測は最大0.000003度)を判定します。
比較として、差分の接線を使う ``create`` では、両端の接線が曲線の接線から最大約32度ずれることをHUDに表示します。

.. code-block:: powershell

   python tools\demo_rotation_minimizing_frames_curve.py --launch
