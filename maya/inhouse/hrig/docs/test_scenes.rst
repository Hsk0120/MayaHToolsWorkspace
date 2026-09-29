テストシーン
============

シーンの生成
------------

計測シーンは ``tools/benchmark_hrig_constraints.py`` の ``build_scene`` で毎回生成します。
固定の.maファイルは同梱していません。前ページのコマンドで同じ構造を再生成できます。
各条件で新規シーンへ切り替え、構築時間を評価時間から除外します。

独立配置
--------

``sourceRoot`` 配下に300個の入力Transform、``targetRoot`` 配下に300個の出力Transformを置き、
入力と出力を1対1で拘束します。各出力を独立に評価できる配置です。

階層配置
--------

入力側は独立配置と同じですが、出力側は前の出力の子に次の出力を置く300段の階層です。
親空間の依存による影響を見る負荷試験で、通常の腕・脚の階層の長さを代表するものではありません。

入力アニメーションと比較対象
----------------------------

入力のtranslateX/Y・rotateY/Z、targetRootのtranslateX・rotateYに1〜120フレームのキーを設定します。
単位はcm・deg・filmです。スケール・shear・jointOrient・複数ターゲットのブレンドは比較対象外です。

* parentConstraint（単一入力）
* multMatrix + decomposeMatrix（translate/rotate出力）
* multMatrix → offsetParentMatrix
* hrigMatrixFollow（C++）→ offsetParentMatrix
* Bifrost GraphShape（1拘束1グラフ、倍精度の行列積2回）→ offsetParentMatrix

性能シーンは初期オフセット有効です。全出力のworldMatrixを要求し、currentTimeとdgevalの
経過時間を計測します。120フレームのウォームアップ後、120フレームを5回計測します。
Cached Playback、描画、スキニングは使用しません。通常のDG値保持やコンパイル済みグラフは利用します。

姿勢検証
--------

拘束8個の小規模シーンで、Serial/Parallel・初期オフセット有無・階層有無・5構成の
40条件を比較します。時刻1・8・31・67・120・15のワールド行列を標準拘束と比較し、
要素の最大絶対誤差1e-6超過で失敗します。逆方向の時刻移動も含みます。

このシーンは拘束の評価専用です。レイヤー切替、GUI操作、スキン済みキャラクター全体の
性能や、Bifrostの配列一括処理の速度は別途検証が必要です。
