# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 基本方針

- C++の内製コードは日本語のDoxygen形式（`@brief`・`@param`・`@return`、必要時`@note`）でファイル・クラス・全ての名前付き関数を説明する。初心者が追えるよう、所有権・Qtシグナル/スロット・非同期処理・Maya呼出の理由もコメントする。引数や戻り値がないタグは省略し、自明な各行の逐語説明は避ける。PythonはGoogle形式docstringを使用する。詳細は `docs/cpp-documentation.md` を参照する。外部submoduleへ一括適用しない。

- hlibのAPIは「Mayaへ問い合わせる操作はメソッド」「保持する値はプロパティ」を基本とする。シーン更新は明示的なメソッドで行う。具体例と判断基準は `docs/hlib-api-design.md` を参照する。

- 外部ツールの調査メモ・比較表・候補一覧・調査インベントリは `docs/research/` にローカル保存し、Gitへ登録・プッシュしたりSphinxへ掲載したりしない。公開ドキュメントには実装済み機能の仕様・使い方を記載する。

- このリポジトリでの説明・作業報告は日本語で行う。
- Claude Code / Codex / GitHub Copilot を並行運用する前提のリポジトリ。作業開始前に
  `WORK_LOG.md` を確認し、他ツールが進行中の範囲と重ならないか確認する。作業開始時に
  「進行中」へ自分の行を追加し、完了時に「完了履歴」へ移す(運用ルールは同ファイル参照)。

## プロジェクト概要

Maya用のカスタム作業環境リポジトリ。バッチファイル経由でMayaを起動し、内製ツール(HTools/hlib)と外部ツール(mGear, cymel等、Git submodule)を標準環境に影響を与えずロードする。ビルドやパッケージングの工程は無く、`PYTHONPATH` / `MAYA_MODULE_PATH` を介してMaya起動時にそのままロードされるPythonコード群である。

## 起動・実行コマンド

### Mayaの起動

`maya/` ディレクトリから対応バッチを実行する(2022/2024/2025/2026/2027用バッチが用意されている。README記載の代表例):

```bat
cd maya
maya_2026_en.bat
```

各バッチは共通処理 `maya_core.bat` を呼び、`PYTHONPATH`(`inhouse`, `inhouse/HTools`)、`MAYA_SCRIPT_PATH`、`MAYA_PLUG_IN_PATH`、`MAYA_MODULE_PATH`(`modules/`)を設定してからMayaを起動する。`%USERPROFILE%\Documents\maya\<version>\Maya.env` が存在すればあわせて読み込まれる。

### VS CodeからMayaへコードを送信・実行する

1. リポジトリ直下の `MayaHToolsWorkspace.code-workspace` をVS Codeで開く(フォルダ単体で開くとタスク定義が読み込まれないので不可)。
2. 上記バッチでMayaを起動しておく(GUI必須。commandPortが `:7002` に開くのはGUI起動時のみ)。
3. 実行したい `.py` ファイルを開き、**Ctrl+S → Ctrl+Shift+B** で送信する(保存は自動設定済み)。
4. 標準出力・例外はVS Codeターミナルと実行元のMaya双方に表示される。正常終了は `[Maya] Completed`、未処理例外は `[Maya] FAILED`。終了コードは 成功=0 / スクリプト内例外=1 / 接続やファイル不備=2。

実体は `tools/send_to_maya.py`(mayapy経由でタスク実行)が `localhost:7002` へ実行コマンドを送り、対象ツール自体は**起動中のMaya GUIプロセス内**で実行される仕組み(`MayaCommandPorts` が開くPythonポートを利用)。対象は保存済みファイル全体(`__name__ == "__main__"`)で、選択範囲送信・ブレークポイントは非対応。import済み依存モジュールは自動リロードされない。結果受け渡しは `.maya-output/` 配下の実行ごとのJSONファイル(取得後は削除、gitignore対象)。別バージョン/インストール先を使う場合は `MayaHToolsWorkspace.code-workspace` の `maya.pythonExecutable` と `python.defaultInterpreterPath` を対象の `mayapy.exe` に変更する。

### 静的解析(Pylance/pyright)

`python tools/setup_maya_typings.py` で型スタブ(`types-maya`)を `typings/maya/` へ配置する(Git対象外)。設定はリポジトリ直下の `pyrightconfig.json`(解析対象・`extraPaths`・重大度)。スタブの不完全さに起因する指摘は警告にしてあり、エラーは実際の誤りだけ。コマンドラインでは `pyright --pythonpath "C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe"`。詳細は `docs/vscode.md`。

### テストの実行

pytestやCIランナーは無く、Maya(mayapy)経由での手動実行が前提。

- `maya/inhouse/hlib/__tests__/test_datatypes.py` を開いて Ctrl+Shift+B で送信すると、`hlib.maths`(Vector/Translate/Rotate/Scale/Shear/Quaternion/EulerRotation/Matrix)を対象とした unittest が全9件走り、VS Codeターミナルと Maya の両方に各テスト結果とOK/FAILEDが出力される。Maya非依存の純粋ロジックだが、実行手段はこのリポジトリの標準に合わせてMaya経由である。
- 個別テストだけ実行したい場合は、同ファイル末尾の `if __name__ == "__main__":` ブロックが `test_` で始まる関数を `globals()` から収集して実行しているため、一時的に対象外の関数名を変える、または別のtest_*.pyとして必要な関数だけをコピーして送信する。
- 他の `hlib/__tests__/test_*.py`(`test_decorators.py`/`test_registry.py`/`test_node_creation.py`/`test_node_api.py`/`test_namespace_api.py`/`test_scene_api.py`/`test_scene_ui.py`/`test_skincluster.py`/`test_shapes_constraints.py`/`test_objectset.py`/`test_blendshape.py`/`test_displaylayer.py`/`test_cluster.py`/`test_locator.py`/`test_joint.py`/`test_units.py`/`test_plugin.py`/`test_workspace.py`/`test_reference.py`/`test_coerce.py`/`test_logger.py`/`test_progress.py`/`test_package_layout.py` 等)も同様に `unittest.TestCase` を Maya 内で実行する形式で、対応するパッケージの単体テストを提供する。いずれもテスト対象ノードは専用の一時名前空間やユニーク名で作成し、tearDown で削除する。`test_package_layout.py` は `hlib.files`/`namespaces`/`plugins`/`units`/`workspace`/`editors` の公開名と、`hlib.reload()` が旧 `scenes`/`session` のような廃止済みパッケージ名の残存参照を除去することを検証する。
- **cmds突き合わせ(回帰防止の体系的な仕組み)**: `hlib/__tests__/test_cmds_parity.py` は、`development.rst` の「maya.cmds と OpenMaya API 2.0 の使い分け」方針でcmds→om2に置き換えた読み取り専用メソッドについて、hlib側の戻り値とcmds側の生の値を**同一テスト内で突き合わせる**専任ファイル。他のtest_*.pyにある「固定の期待値になるか」だけのテストと異なり、Mayaバージョン変更やAPIの挙動変化・リファクタによる回帰を継続的に検知する目的を持つ。新しくcmds→om2の置き換えを行った場合はこのファイルに対応する突き合わせを追加するのが規約(既存の突き合わせ一覧はファイル冒頭のdocstringを参照)。
- **一括実行**: `hlib/__tests__/run_all_tests.py` を Ctrl+Shift+B で送信すると、同ディレクトリの対象 `test_*.py`(後述の除外ファイルを除く全件、`test_cmds_parity.py`含む)を同一 Maya セッション内で連続実行し、成功/失敗をファイル単位で集計する。各ファイルの標準出力を保持したまま `hlib/__tests__/.logs/YYYYMMDD_HHMMSS.log`(`*.log` として gitignore 済み)へ書き出し、1件でも失敗すれば `AssertionError` を送出して `[Maya] FAILED` になる。`run_all(notify=...)` は集計後のサマリ文字列を受け取るコールバックを渡せる(`hlib/utils/progress.py` の `notify` と同じ設計で、将来 Slack 通知等を差し込む接続点)。`test_scene_api.py` は setUp/tearDown で現在のシーンを `new(force=True)` するため、一括実行(および単体実行)前に必要な変更は保存しておくこと。
- `test_maya_standalone.py` / `test_slack_postMessage.py` / `test_command_discovery.py`(`hlib/__tests__/`)は一括実行の対象外。前2つは疎通確認用の手動スクリプトで、`test_slack_postMessage.py` は環境変数 `SLACK_API_BOT_TOKEN` が必須でSlackへ実際にメッセージを投稿する副作用があり、`test_maya_standalone.py` は `HTools.decorator`(存在しないモジュール)を参照しており現状インポートに失敗する。`test_command_discovery.py` は `subprocess` で mayapy を別プロセス起動する疎通確認用スクリプトで、Maya GUI の commandPort 経由で実行すると新しい Maya.exe が起動してしまうため単体でも Maya GUI 経由では実行しないこと。

## アーキテクチャ

### ディレクトリ構成

```
maya/
├ external/     外部ツール(Git submodule、37個。一覧は下記「external ― 外部ツール一覧」参照)。
│               直接編集せず、変更は各submodule側で行う。
├ inhouse/      内製ツール本体
│  ├ HTools/         Mayaメニューから起動する社内ツール群
│  ├ hlib/           共通ライブラリ(Node/Plugラッパー、数学型、デコレータ等)
│  ├ MayaCommandPorts/  HTools/hlibから独立したcommandPort初期化モジュール
│  ├ integrations/   外部サービス連携(Slack, mGearガイド操作)
│  └ MayaCinematicCameraHUD/  C++プラグイン(別リポジトリのsubmodule。このワークスペースで編集・ビルドする)
├ modules/      各ツールをMayaに認識させる .mod ファイル(2022/2024/2025/2026/2027対応、MAYA_MODULE_PATHの対象)
├ modules_disabled/  上記と同形式だが未登録の .mod ファイル(無効化されたツール/汎用ライブラリ)。有効化するには modules/ へ移動する
└ maya_*.bat, maya_core.bat  起動バッチ
tools/
└ send_to_maya.py  VS Code タスクが実行するMaya送信スクリプト
```

### external ― 外部ツール一覧

`maya/external/` 配下の Git submodule 37個。いずれも直接編集せず、変更は各submoduleのリポジトリ側で行う。

**Python基盤/ラッパーライブラリ**
- `cymel`: Maya APIとコマンドの軽量ラッパーモジュール。
- `pymel`: `maya.cmds` の直訳的で非pythonicな部分を解消する、Mayaコマンドのpythonicなラッパー(nodetypes.pyを自動生成)。
- `paya`: `cmds`/OpenMaya自体を再ラップせず、その上に機能を足すリガー向けオブジェクト指向ツールキット(PyMELライクなAPI)。
- `AL_omx`: Animal Logic製、Maya APIとコマンドの薄いラッパーライブラリ(PyPi配布)。

**リギング/オートリグフレームワーク**
- `mgear4`, `mgear5`: mGear(既存記載の通り、モジュラーリギングフレームワーク)。
- `crab`: コンポーネント(腕・脊椎・脚など)単位でスケルトンとコントロールリグを構築するモジュラーリギングツール。
- `fossil`: リギング・アニメーションツール群。
- `maya-pulse`: リギングフレームワーク/ツールキット(開発中)。
- `mikan`: Maya/Tangerine向けのブループリント式モジュラーオートリギングフレームワーク。
- `trigger`: モジュラーなリギング・自動化ツール。
- `nl_rigging_tools`(nlRT): リギングツール集。
- `AdvancedSkeleton`, `AnimationAid`, `AriTools`(既存記載): オートリグ/リギング支援ツール。

**アニメーション**
- `aTools`: Alan Camilo氏制作のアニメーションツールキット。
- `animation-retargeting-tool`: リグ間、またはモーキャプ→カスタムリグへのアニメーション転送ツール。
- `guppy_animation_tools`: Arc Tracerなどアニメーション制作支援ツール集。
- `ml_tools`: Morgan Loomis氏のアニメーションツールをまとめたリポジトリ。
- `Red9_StudioPack`: テクニカルアニメーション向けの総合Mayaツールパック。
- `studiolibrary`: ポーズ/アニメーションを保存・管理するQtベースのライブラリツール。
- `PoseDriverConnect`(既存記載): ポーズドリブン関連ツール。

**スキン/ウェイト編集**
- `SkinPowerTool`: SkinMagicプラグインの代替となるスキンウェイト編集ツール。
- `defWeightTransfer`: デフォーマウェイト(bend/cluster/FFD等)の転送・ミラー・変換ツール。
- `maya-skinning-tools`: スキニング支援ツール集(スムーズウェイト等)。
- `skinner`: スキンウェイトのエクスポート/インポート/転送ツール。
- `SIWeightEditor`(既存記載): Softimage風のスキンウェイト編集ツール。

**メッシュ/リターゲット**
- `MayaMeshRetarget`: RBF補間とスキンウェイトベースのクラスタリングでメッシュ変形をソース→ターゲットへ転送するツール。
- `MetaHumanForMaya`(既存記載): MetaHuman関連ツール。

**その他**
- `gt-tools`: 汎用のアニメーション/リギング補助ツール集(GT Tools)。
- `jlr_sort_attributes`(既存記載): チャンネルボックスのユーザー定義属性を並び替えるツール。
- `CharcoalEditor2`(既存記載): エディタ系ツール。

**汎用Pythonライブラリ(Maya専用ツールではない)**
- `rich`: ターミナル出力の表・プログレスバー・シンタックスハイライト等を行うライブラリ。
- `pyyaml`: YAML パーサ/エミッタ(実体は `lib/yaml` 配下。トップレベルの `yaml/` は未使用のCython版ソース)。
- `tqdm`: プログレスバー。
- `tabulate`: テキストでの表整形。
- `natsort`: 自然順ソート。
- 上記5つは対応する `.mod` を `maya/modules_disabled/` に用意済みだが、`maya/modules/` へは未登録(MAYA_MODULE_PATH対象外)のため起動時に自動ロードされない。有効化するにはそのバージョン用の `.mod` を `maya/modules/` へコピー/移動する。個別スクリプトで使うだけなら `.mod` を経由せず `sys.path` へ直接追加してもよい。

### HTools ― メニュー登録の仕組み

- `HTools/userSetup.py` がMaya起動時に評価される。GUI起動時のみ・同一セッション内では1回のみ実行される(`MAYA_INHOUSE_USERSETUP_INITIALIZED` 環境変数で二重初期化防止、バッチモードはスキップ)。
- `HTools/` 直下のサブディレクトリ(`animation/`, `material/`, `rigging/` 等、`__` で始まらないもの)をカテゴリとして走査し、各サブディレクトリ内の `.py` ファイル(`__init__.py` を除く)をメニュー項目として動的にQtメニューバーへ追加する。**新規ツールを追加する場合はカテゴリフォルダに `.py` を1本置くだけでHToolsメニューに現れる**(明示的な登録コードは不要)。
- メニュー項目クリック時は `runpy.run_module("HTools.<category>.<tool>", run_name="__main__")` として対象モジュールをその場で実行する。
- `HTools/searchable_menu.py` の `SearchableMenu`(`QtWidgets.QMenu` 拡張)が検索フィールドとフラット/階層表示切り替えを提供する。
- PySide6を優先し、無ければPySide2にフォールバックする実装(Maya 2025以降はPySide6、2022はPySide2)。

### hlib ― Maya API 2.0 ベースの共通ライブラリ

Maya公式 `maya.cmds` ではなく `maya.api.OpenMaya`(API 2.0)を主に用いた、ノード/属性(plug)のラッパーとメンテナンス性重視の動的登録機構を提供する。

- **動的wrapper登録** (`hlib/_core/discovery.py`, `hlib/_core/registry.py`): `hlib/nodes/*.py` のクラスに `@node_wrapper("<Mayaのnodetype>")`、`hlib/plugs/*.py` のクラスに `@plug_wrapper("<attrType>")` を付けるだけで、サブパッケージ初期化時に `pkgutil` でモジュールを走査して自動的に `NodeRegistry` に登録される。**新しいノード型/属性型のラッパーを追加する際は新規ファイルを追加してデコレータを付けるだけで実行時には登録される**。ただしエディターの静的解析向けに、`hlib/nodes/__init__.py`(ノードクラス)と、コマンドなら `hlib/__init__.py`・`hlib/cmds/__init__.py` の `if TYPE_CHECKING:` ブロックへの追記も必要(漏れは `test_typing_exports.py` が検出する)。同一型に複数クラスを登録しようとすると `ValueError` になる。ノード側は `Node`/`Transform`/`Shape`/`Joint`/`Mesh`/`Camera`/`NurbsCurve`/`SkinCluster`/`IkHandle`/`ObjectSet`/`BlendShape`/`DisplayLayer`/`Cluster`/`Locator`/`Reference`に加え、`Constraint` 系(Parent/Point/Orient/Scale/Aim/PoleVector/Geometry/Normal/Tangent/PointOnPoly の10種)を提供する。これらのクラスは `hlib` 直下には公開されず、`hlib.nodes.Joint` のように所属パッケージ(`hlib.nodes`/`hlib.plugs`/`hlib.maths`/`hlib.components`/`hlib.files`/`hlib.namespaces`/`hlib.plugins`/`hlib.units`/`hlib.workspace`/`hlib.editors`)から import する。
- **ファクトリパターン**: `Node.__new__`(`hlib/nodes/node.py`)が対象の実際の Maya nodeType を調べ、登録済みのサブクラス(例: `Joint`, `SkinCluster`)があれば自動的にそちらへ差し替えてインスタンス化する。呼び出したクラス自身と実際の型が異なれば差し替わる点に注意(例: 非jointノード名を渡して `Joint("name")` を呼んでも、実際の型が `Transform` ならその型が返る)。属性未定義の場合は `__getattr__` がMayaのplugとして解決を試みる(`Plug` を返す)。
- **`hlib/cmds/` ― ファイル名駆動のコマンド自動公開**: `cmds/<コマンド名>.py` に同名の関数(例: `createNode.py` の `createNode()`)を定義するだけで、`hlib.cmds.<コマンド名>` と `hlib.<コマンド名>` の両方から呼べるようになる(`cmds/__init__.py` の編集は不要。非公開名・サブパッケージ・同名関数を持たないファイルは対象外)。既存コマンドは `createNode`/`ls`/`node`/`constraint`/`scene`。命名は Maya コマンドに合わせてキャメルケース。各モジュールの docstring は Synopsis/Return value/Flags/Examples 形式で書き、Sphinx側の専用テンプレートで個別ページとして生成される。`hlib.reload()` は追加・変更・削除を検出して両方の公開名に反映する。
- **依存順リロード** (`hlib/_core/reload.py`): `hlib.reload()` がパッケージ配下の現存モジュールをmodule globals内の相互参照から依存グラフを推定し、依存先を先に安全な順序でreloadする。Script Editor上での開発・修正の反映に使う。
- `hlib/maths/`: `Vector`/`Translate`/`Rotate`/`Scale`/`Shear`/`Quaternion`/`EulerRotation`/`Matrix` などMaya非依存(標準`math`のみ)の値型。`Matrix` を除き `@dataclass(frozen=True)` の不変値オブジェクトで、等価比較・ハッシュは自動生成される(`slots=True` はMaya 2022同梱のPython 3.7と非互換のため不使用)。`EulerRotation` は内部値がradian、表示・入出力はdegreesである点に注意。
- `hlib/components/`: Mesh/NurbsCurveの部分要素を、作成時に番号を固定した参照として提供する(`Vertex`/`Vertices`、`CV`/`CVs`、`Edge`/`Edges`、`Face`/`Faces`、`UV`/`UVs`)。座標は都度シーンから取得し、`Vertex`/`CV`(`PointComponent`系)は代入で即座にシーンへ反映しUndoできる。トポロジー変更後の番号の同一性は保証しない。
- 旧 `hlib/scenes/` は責務ごとに分割済み: `hlib/files/`(`Scene`。`Scene(path=None)`の`None`は現在のシーン、指定時はそのパスを取得時点で保持するだけで読み込まない。`save()`/`save_as()`/`is_modified()` は保持パスが現在のシーンと一致する場合のみ使用でき、一致しなければ `RuntimeError`。シーン内の参照を列挙する `list_references()` も提供、参照ノード自体は `hlib.nodes.Reference`)、`hlib/namespaces/`(`Namespace`)、`hlib/plugins/`(プラグインのロード状態を扱う `Plugin`/`Plugins`)、`hlib/units.py`(UI単位の `Units`。取得・設定とも `cmds.currentUnit` 文字列表現、と内部単位を一時強制する `native_units()`)、`hlib/workspace.py`(プロジェクト設定を扱う `Workspace`)、`hlib/editors/`(既存エディターを参照する `Viewport`/`Outliner`、共通基底 `_Editor`、タイムライン操作の `TimeSlider`)。
- `hlib/decorators/`: `undo.py` の `undo_chunk` コンテキストマネージャと `undoable` デコレータで複数のMaya操作を単一のUndoチャンクにまとめる。`selection.py` の `preserved_selection` コンテキストマネージャはブロックの前後でMayaの選択状態を保存・復元する(ブロック内で例外が起きても復元される)。
- `hlib/utils/`: `logger.py`(ログ出力)、`progress.py`(Maya非依存の進捗バー、Slack通知等への`notify`コールバック対応)。
- トップレベル `hlib/__init__.py` は `cmds`/`nodes`/`plugs`/`components`/`files`/`namespaces`/`plugins`/`units`/`workspace`/`editors`/`maths` サブパッケージと `reload()` のみを直接公開し、加えて `hlib.cmds` の公開コマンド関数をフラットに再公開する(`hlib.createNode`/`hlib.ls`/`hlib.node`/`hlib.constraint`/`hlib.scene`)。`Node`/`Joint`/`Matrix` などのクラスは `hlib.Node` のようには公開されず、必ず `hlib.nodes.Node` のように所属パッケージから import する。`hlib.reload()` は旧 `scenes`/`session` のような廃止済みパッケージ名の残存参照を検出して除去する。

### MayaCommandPorts

HTools/hlibから独立した最小モジュール(依存は `maya.cmds` / `maya.utils` のみ)。GUI起動時のみ遅延実行でcommandPortを `:7001`(MEL)/`:7002`(Python)に開く。既存ポートは開き直さず、失敗はwarning出力に留める。VS Code連携(`tools/send_to_maya.py`)はこの `:7002` を使用する。無効化するには `maya/modules/MayaCommandPorts.mod` をmodules検索対象外へ移動する。

### integrations

- `integrations/slack/`: `post_message(text, channel="random", thread_ts=None)`。環境変数 `SLACK_API_BOT_TOKEN` が未設定または `slack_sdk` が無い場合は `RuntimeError`。
- `integrations/mgear/guide/`: mGearガイド(`isGearGuide` 属性を持つtransform)の取得・更新ヘルパー。`update_guide()` は呼び出し時に初めて `mgear` を import するため、mGear未導入でも本モジュール自体のimportは可能。

### C++プラグイン(別リポジトリ)

C++のMayaプラグインは別リポジトリで管理し、submoduleとして取り込む。現在の対象は `maya/inhouse/MayaCinematicCameraHUD`(`.mll` を `release/plug-ins/windows/<Mayaバージョン>/` にコミットする構成)。

- **置き場所の規則**: このワークスペースで**編集する**リポジトリは `maya/inhouse/` 、編集せず成果物を使うだけのものは `maya/external/` にsubmoduleとして置く。編集後はまずプラグイン側リポジトリでコミットし、その後に親リポジトリでsubmoduleの参照を更新する。
- **ビルド**: `tools/build_maya_plugin.py <プラグインのフォルダ> --versions <年...>`(2022/2024/2025/2026/2027 で実ビルドとロードを確認済み)(または VS Code のタスク「Maya plugin: Build MayaCinematicCameraHUD」)。Visual Studio・CMake・ツールセットを自動検出し、ビルドフォルダは `.maya-output/plugin-build/` 配下(Git対象外)に作る。`--list` で検出結果を確認できる。
- **devkit**: 別配布のdevkitは不要。Maya 2025/2027 のようにインストール先に `cmake/pluginEntry.cmake` が無い版や、Qt用zipが未展開の版は、`tools/maya_devkit.py` がインストール先(ヘッダ・lib・moc・Qt用zip)から `.maya-output/devkit/<年>/` にローカルdevkitを自動生成する(Program Files配下は書き換えず、管理者権限も不要)。別途入手したdevkitを使う場合は環境変数 `MAYA_DEVKIT_<年>` に `devkitBase` を指定する。ツールセットの対応は 2022=v142、2024=v143、2025=v143、2026=v145、2027=v145(`tools/build_maya_plugin.py` の `TOOLSETS`)。Maya 2023 は未インストールのためビルド未対応。
- **ロード**: `maya/modules/<名前>.mod` の `MAYA_PLUG_IN_PATH` で検索パスに通すだけで、自動ロードはしない(Plug-in Manager または `cmds.loadPlugin` で読み込む)。初回ロード時にMayaの「信頼されていない場所からのロード」警告ダイアログが出てGUI(とcommandPort経由の送信実行)が止まるため、ロード前に信頼済みの場所へ登録しておく。登録は Preferences > Security > Plug-ins の「My trusted plugin locations」で「Add」するか、警告ダイアログで「Apply to all plugins in this location」にチェックして Allow する(各フォルダ1回のみ。プラグインのフォルダはバージョン別なので使う版の分だけ)。**スクリプトからの登録はできない**: `optionVar SafeModeAllowedlistPaths` への追記はMayaのSafeModeが拒否する(戻り値1・値は変化せずセキュリティログに reject/Deny)ため、迂回せず手動で行う。HToolsの「system > checkWorkspacePluginTrust」は、`maya/inhouse/` 配下で未登録の場所を確認して一覧表示し、Preferences画面を開く読み取り専用ツール。自動テストやCIでは、警告が出ないmayapy(`tools/run_hlib_tests.py` 等)を使う。
- **注意**: 上記の「hlib内では独自プラグインを用意しない」方針は hlib のコードに対するもので、別リポジトリのC++プラグインは対象外。ビルドすると追跡対象の `release/**/*.mll` が書き換わるため、リリースとしてコミットする意図が無い場合は `git checkout -- release/` で戻す。

## 開発上の注意

- Pythonの単体実行環境(venv/pip install)は用意されていない。全てMaya本体(GUIまたはmayapy)を介して動作する前提で、純粋ロジックのテストであってもMaya経由で実行するのがこのリポジトリの標準的な方法。
- `maya/external/*` はGit submodule。変更が必要な場合は各submoduleのリポジトリ側で行う(親リポジトリからの直接コミット対象ではない)。
- 新規clone後は `git submodule update --init --recursive` が必要。
- hlib内では独自のMayaプラグインを実装・同梱・自動ロードしない。`MPxCommand` / `MPxNode` / `MFnPlugin` による登録は、Undo対応やバージョン差の回避目的でも追加しない。既存の内部プラグインもこの方針の解消対象とし、残存している場合は未対応箇所を明記する。Maya標準コマンドと既存のUndo可能な処理を優先し、実現できない機能は制限・未対応として明示する。`hlib.plugins`による既存プラグインの状態照会・明示的なロード管理は、この禁止の対象に含めない。
