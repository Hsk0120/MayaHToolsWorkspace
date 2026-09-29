行列追従と拘束評価の計測
========================

単一入力の軽量な追従
--------------------

``hrig.setups.MatrixFollow`` は、専用Transformバッファへ
``multMatrix -> offsetParentMatrix`` で全成分を渡します。
``decomposeMatrix`` とEuler角への変換を挟みません。
既定のstandard構成ではノード生成・属性・接続・行列計算にhlibを使用し、追加プラグインは不要です。

.. code-block:: python

   import hlib
   from hrig.setups import MatrixFollow

   driver = hlib.createNode("transform", name="driver", skipSelect=True)
   buffer = hlib.createNode("transform", name="followBuffer", skipSelect=True)
   control = hlib.createNode("transform", name="control", parent=buffer, skipSelect=True)
   graph = MatrixFollow.create(driver, buffer, maintain_offset=True)
   # アニメーション用のローカル操作はbufferの子で行う。
   driver.set_translate((2, 0, 0))

戻り値は所有・削除管理用のmultMatrixラッパーです。構築は1回のUndoにまとまります。
生成後の評価は標準ノードだけで動作し、保存・再読込にPythonコールバックを必要としません。

C++とBifrostの明示選択
----------------------

``backend="cpp"`` は ``hrigMatrixFollow`` を1拘束につき1ノード生成します。
``backend="bifrost"`` は1拘束につき1つのbifrostGraphShapeとその親Transformを生成します。
既定値は ``standard`` で、既存リグの自動置換は行いません。

両方とも ``offset * sourceWorld * parentInverse`` を倍精度で計算し、
outputMatrixを専用バッファのOPMへ接続します。単一入力の剛体追従が比較対象で、
parentConstraintの複数入力・軸スキップ・jointOrient等を再実装したものではありません。
scale/shear付きでは全成分追従という独自仕様になります。

C++版は入力以外の状態を持たないMPxNodeで、parallel schedulingを指定しています。
Mayaの版ごとにビルドし、明示選択時のみhrigNodesをロードします。
開発用IDは ``0x0007F102`` です。既存hrigNodesをロード中なら、新バイナリを使うには
Mayaを再起動してください。セキュリティ設定は変更しません。

.. code-block:: powershell

   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' tools/build_maya_plugin.py maya/inhouse/hrig/cpp --versions 2025 2027

.. code-block:: python

   cpp_buffer = hlib.createNode("transform", name="cppFollowBuffer", skipSelect=True)
   graph = MatrixFollow.create(driver, cpp_buffer, backend="cpp")

Bifrost版は ``hlib_bifrost`` を使用し、MathBuilderのmatrix_multiplyを組み合わせます。
列ベクトル規約に合わせて乗算順を逆転し、Maya境界の自動転置を利用します。
Bifrost版の戻り値はhlibのgraphShape参照です。その親Transformも生成物として管理してください。

**Bifrost版は検証用です。** 現環境ではグラフ構築のUndo/RedoでMayaが終了したため、
Undoが有効な状態での構築を拒否します。Undo無効の専用mayapyだけで使用し、
通常作業中のMayaのUndo設定をこの機能のために変更しないでください。
保存・再読込と通常評価を検証しても、編集用の安定性を保証するものではありません。
自動でUndo履歴を消去する処理はありません。

適用条件
--------

* targetは恒等TRS/OPM、ゼロpivot/rotateAxis、入力接続なしのTransformに限定します。
* scale/shearも追従します。位置と回転だけを渡すparentConstraintとは仕様が異なります。
* jointOrient、複数入力のウェイト補間、軸スキップには対応しません。
* 再親付け・インスタンス化・bufferのローカル操作は構築後も行わないでください。
* 入力や親のゼロスケール、評価時の特異行列には対応しません。
* DAG/DGの自己依存を構築前に検査します。構築後に循環する接続を追加しないでください。

親空間の変換には実親のworldInverseMatrixを使用します。
target自身のparentInverseMatrixをOPMへ戻す構成は使用しません。
既存のSpaceSwitchはすでに行列をOPMへ接続しています。
既存リグや保存済みシーンをこのセットアップへ自動変換する処理はありません。

専用プロセスでの再計測
----------------------

リポジトリ直下でPowerShellから実行します。GUI内へ送信しないでください。
この計測専用のPowerShellを使い、終了後に閉じて環境変数を通常作業へ持ち越さないでください。
ツールはMaya standaloneを初期化してから新規シーンを作成するため、
初期化済みのMaya GUIでは処理を開始しません。

.. code-block:: powershell

   $base = Join-Path $PWD '.maya-output/constraint-benchmark'
   New-Item -ItemType Directory -Force "$base/app2025", "$base/temp2025" | Out-Null
   $env:MAYA_APP_DIR = "$base/app2025"
   $env:TEMP = "$base/temp2025"
   $env:TMP = $env:TEMP
   & 'C:/Program Files/Autodesk/Maya2025/bin/mayapy.exe' tools/benchmark_hrig_constraints.py --count 300 --frames 120 --repeats 5 --output "$base/maya2025.json"

C++をビルド済みで対応Bifrostが導入されている場合は、同じ隔離環境で5構成を比較できます。

.. code-block:: powershell

   & 'C:/Program Files/Autodesk/Maya2025/bin/mayapy.exe' tools/benchmark_hrig_constraints.py --plugins --count 300 --frames 120 --repeats 5 --output "$base/plugins2025.json"

Serial・Parallelだけを比較する場合は ``--modes serial parallel`` を指定します。
省略時は従来どおりDG（off）も含めます。SerialはMayaの評価グラフの直列評価であり、
Bifrost内部を含めた全処理をCPU 1スレッドに制限する指定ではありません。

.. code-block:: powershell

   & 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' tools/benchmark_hrig_constraints.py --plugins --modes serial parallel --count 300 --frames 120 --repeats 5 --output "$base/serial-parallel.json"

Cached Playbackは起動後に無効化し、ウォームアップ・各反復の直前にも無効状態を照会します。
有効なら例外で中断し、その計測は採用しません。JSONの ``cached_playback`` は実際の照会値で、
各計測行にも記録します。アニメーションキャッシュの生成・再利用は行いません。
通常のDGの値保持やBifrostのコンパイル済みグラフの再利用は、この設定とは別です。

計測方法
--------

* parentConstraint、multMatrix＋decomposeMatrix、MatrixFollowの3構成を比較します。
* DG（off）・Serial・Parallel、独立出力・階層出力の18条件を固定seedで並べ替えます。
* ``--plugins`` を付けるとC++/Bifrostを追加した5構成・30計測条件・60姿勢条件になります。
  Bifrostのロード版もJSONへ記録します。全構成を同じ実行で測り直してください。
* Bifrostは1拘束1グラフです。1グラフ内で配列を一括処理する設計の速度は測っていません。
* まず小規模シーンで各評価モード・初期オフセットの有無・階層の有無を組み合わせ、
  全出力のワールド行列をparentConstraintと比較します。誤差1e-6超過は失敗です。
* 比較シーンは回転・移動のみで、スケール、シアー、jointOrient、pivot、
  複数入力ウェイトを含みません。これらを含むリグへの完全互換性を示す試験ではありません。
* Cached Playbackを無効にし、120フレームのウォームアップ後に反復します。
* 時刻変更と全出力へのdgeval要求を含む経過時間を測定します。
  Python呼出しを含み、描画・スキニング・UIの時間を含まないため、FPSとは異なります。
* JSONへMaya/API版・OS・CPU・スレッド数・評価モード・fallback・生測定値・
  中央値・最小最大値・全シーンノード数を保存します。
* 構築時間も保存しますが、各構成で入力検証や実装経路が異なるため公平な構築速度比較ではありません。
* 小規模の姿勢試験は公開createを使用します。性能シーンは同じ内部ビルダーで接続し、
  各ノード作成時の依存探索を繰り返しません。比較用に決められたトポロジーのみが対象です。
  通常のリグ作成で内部ビルダーを直接呼び出さないでください。

300段の階層は依存経路の差を見るストレス試験です。通常の腕・脚全体が同率で速くなる
という意味ではありません。他のMaya・重い処理を止め、各バージョンを順番に計測してください。
同一マシンでもバックグラウンド処理・電力制御による変動があります。
比率だけでなく、各反復の時間と差の大きさを確認してください。

既存スカートの候補検証
----------------------

``--skirt`` はSkirtRigを作成し、回転だけを使用するparentConstraintを
orientConstraintへ置換した候補と比較します。``--count`` を3で割った列数
（最低8列、各3骨）で作成します。
複数軸回転、root移動、blend/falloffのアニメーションを評価します。
姿勢不一致の場合はJSONへ失敗を保存し、終了コード1で停止します。
これは候補の検証用であり、SkirtRigの既定実装を変更するオプションではありません。

測定値・比較結果は環境依存のため、Git対象外の ``.maya-output`` や
``docs/research`` へ保存します。
