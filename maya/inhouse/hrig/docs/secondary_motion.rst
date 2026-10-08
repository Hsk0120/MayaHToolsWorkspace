揺れ計算とポーズ補間
====================

``hlib.common.DampedSpring`` は等間隔の数値列を減衰ばねで処理します。
Mayaノードを生成せず、Python標準ライブラリだけで計算します。

.. code-block:: python

   from hlib.common import DampedSpring

   result = DampedSpring.solve(
       [(0.0,), (30.0,), (30.0,)],
       seconds_per_sample=1.0 / 24.0,
       frequency=3.0, damping=0.5, limit=45.0,
   )

frequencyは固有振動数Hz、dampingは減衰比、limitは入力からの差の上限です。
初期位置は最初の入力、初速は0です。内部で時間を分割し、サンプル間の入力を
線形補間します。角度の周期処理は呼出側で行ってください。
ライブ評価、衝突、重力、布シミュレーションは提供しません。

複数入力のポーズ補正
--------------------

``PoseRbf.create(drivers, poses, values, scales, name="poseRbf")`` は
複数の数値属性から複数の補正値を生成します。戻り値の ``container`` に
``outputs[0]`` 以降の出力と、再編集用データを保持します。

* drivers: 入力Plugまたは属性名の配列。
* poses: 登録入力値の配列。2〜64ポーズで、各行は入力数と同じ長さ。
* values: 各ポーズの出力値。各行の出力数を揃える。
* scales: 入力軸ごとの距離尺度。正の有限値。

ガウス関数 ``exp(-sum(((input - pose) / scale)**2))`` の組合せを使い、
登録ポーズで指定値に一致する係数をPythonで解きます。再生時は
multiplyDivide等のMaya標準ノードだけで評価し、Pythonコールバックは不要です。
角度属性の入力はMayaの表示単位にかかわらず度として扱います。
出力は単位なしの数値で、角度属性へ接続する場合は単位変換が必要です。

登録点から十分離れると出力は0へ近づきます。正規化したブレンドウェイトではなく、
中間で負値や登録値を超える値になる場合があります。重複・近接しすぎた入力で
係数が安定して解けない場合は生成を拒否します。

``PoseRbf(container).set_values(values)`` で出力値を再設定できます。
このメソッドではポーズ数・入力・出力の次元は変更できません。
``set_data(poses, values, scales)`` は2〜64登録の追加・削除・入力編集とscalesの変更に対応します。
入出力の次元は固定ですが、containerの識別子と外部接続を保持します。
内部ノードは再構築するため、内部計算ノードへの独自接続は保持しません。
変更前に重複・数値不正を検証し、生成・編集はUndo対象です。
``data()`` で保存済み辞書のコピー、``capture()`` で現在入力（角度は度）を取得できます。
Maya Pose Editorのデータ形式との互換はありません。
