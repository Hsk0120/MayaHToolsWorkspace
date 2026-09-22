# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

Maya用のカスタム作業環境リポジトリ。バッチファイル経由でMayaを起動し、内製ツール(HTools/Hlib)と外部ツール(mGear, cymel等、Git submodule)を標準環境に影響を与えずロードする。ビルドやパッケージングの工程は無く、`PYTHONPATH` / `MAYA_MODULE_PATH` を介してMaya起動時にそのままロードされるPythonコード群である。

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

### テストの実行

pytestやCIランナーは無く、Maya(mayapy)経由での手動実行が前提。

- `maya/inhouse/Hlib/__tests__/test_datatypes.py` を開いて Ctrl+Shift+B で送信すると、`Hlib.maths`(Vector/Translate/Rotate/Scale/Shear/Quaternion/EulerRotation/Matrix)を対象とした unittest が全9件走り、VS Codeターミナルと Maya の両方に各テスト結果とOK/FAILEDが出力される。Maya非依存の純粋ロジックだが、実行手段はこのリポジトリの標準に合わせてMaya経由である。
- 個別テストだけ実行したい場合は、同ファイル末尾の `if __name__ == "__main__":` ブロックが `test_` で始まる関数を `globals()` から収集して実行しているため、一時的に対象外の関数名を変える、または別のtest_*.pyとして必要な関数だけをコピーして送信する。
- 他の `Hlib/__tests__/test_*.py`(`test_decorators.py`/`test_registry.py`/`test_node_creation.py`/`test_node_api.py`/`test_namespace_api.py`/`test_scene_api.py`/`test_skincluster.py`/`test_shapes_constraints.py`)も同様に `unittest.TestCase` を Maya 内で実行する形式で、対応するパッケージ(decorators/core.registry/nodes/scene/components 等)の単体テストを提供する。いずれもテスト対象ノードは専用の一時名前空間やユニーク名で作成し、tearDown で削除する。
- `test_maya_standalone.py` / `test_slack_postMessage.py`(`Hlib/__tests__/`)は疎通確認用の手動スクリプト。後者は環境変数 `SLACK_API_BOT_TOKEN` が必須で、Slackへ実際にメッセージを投稿する副作用がある点に注意。前者は `HTools.decorator`(存在しないモジュール)を参照しており、現状インポートに失敗する。

## アーキテクチャ

### ディレクトリ構成

```
maya/
├ external/     外部ツール(Git submodule): mGear4, mGear5, cymel, AnimationAid, AriTools,
│               CharcoalEditor2, PoseDriverConnect, SIWeightEditor, AdvancedSkeleton,
│               MetaHumanForMaya, jlr_sort_attributes。直接編集せず、変更は各submodule側で行う。
├ inhouse/      内製ツール本体
│  ├ HTools/         Mayaメニューから起動する社内ツール群
│  ├ Hlib/           共通ライブラリ(Node/Plugラッパー、数学型、デコレータ等)
│  ├ MayaCommandPorts/  HTools/Hlibから独立したcommandPort初期化モジュール
│  └ integrations/   外部サービス連携(Slack, mGearガイド操作)
├ modules/      各ツールをMayaに認識させる .mod ファイル(2022/2024/2025/2026/2027対応)
└ maya_*.bat, maya_core.bat  起動バッチ
tools/
└ send_to_maya.py  VS Code タスクが実行するMaya送信スクリプト
```

### HTools ― メニュー登録の仕組み

- `HTools/userSetup.py` がMaya起動時に評価される。GUI起動時のみ・同一セッション内では1回のみ実行される(`MAYA_INHOUSE_USERSETUP_INITIALIZED` 環境変数で二重初期化防止、バッチモードはスキップ)。
- `HTools/` 直下のサブディレクトリ(`animation/`, `material/`, `rigging/` 等、`__` で始まらないもの)をカテゴリとして走査し、各サブディレクトリ内の `.py` ファイル(`__init__.py` を除く)をメニュー項目として動的にQtメニューバーへ追加する。**新規ツールを追加する場合はカテゴリフォルダに `.py` を1本置くだけでHToolsメニューに現れる**(明示的な登録コードは不要)。
- メニュー項目クリック時は `runpy.run_module("HTools.<category>.<tool>", run_name="__main__")` として対象モジュールをその場で実行する。
- `HTools/searchable_menu.py` の `SearchableMenu`(`QtWidgets.QMenu` 拡張)が検索フィールドとフラット/階層表示切り替えを提供する。
- PySide6を優先し、無ければPySide2にフォールバックする実装(Maya 2025以降はPySide6、2022はPySide2)。

### Hlib ― Maya API 2.0 ベースの共通ライブラリ

Maya公式 `maya.cmds` ではなく `maya.api.OpenMaya`(API 2.0)を主に用いた、ノード/属性(plug)のラッパーとメンテナンス性重視の動的登録機構を提供する。

- **動的wrapper登録** (`Hlib/core/discovery.py`, `Hlib/core/registry.py`): `Hlib/nodes/*.py` のクラスに `@node_wrapper("<Mayaのnodetype>")`、`Hlib/plugs/*.py` のクラスに `@plug_wrapper("<attrType>")` を付けるだけで、パッケージ初期化時に `pkgutil` でモジュールを走査して自動的に `NodeRegistry` に登録される。**新しいノード型/属性型のラッパーを追加する際は新規ファイルを追加してデコレータを付けるだけでよく、`__init__.py` 等の手動編集は不要**。同一型に複数クラスを登録しようとすると `ValueError` になる。ノード側は `Node`/`Transform`/`Shape`/`Joint`/`Mesh`/`Camera`/`NurbsCurve`/`SkinCluster`/`IkHandle`に加え、`Constraint` 系(Parent/Point/Orient/Scale/Aim/PoleVector/Geometry/Normal/Tangent/PointOnPoly の10種)を提供する。
- **ファクトリパターン**: `Node.__new__`(`Hlib/nodes/node.py`)が対象の実際の Maya nodeType を調べ、登録済みのサブクラス(例: `Joint`, `SkinCluster`)があれば自動的にそちらへ差し替えてインスタンス化する。属性未定義の場合は `__getattr__` がMayaのplugとして解決を試みる(`Plug` を返す)。
- **依存順リロード** (`Hlib/core/reload.py`): `Hlib.reload()` がパッケージ配下の現存モジュールをmodule globals内の相互参照から依存グラフを推定し、依存先を先に安全な順序でreloadする。Script Editor上での開発・修正の反映に使う。
- `Hlib/maths/`: `Vector`/`Translate`/`Rotate`/`Scale`/`Shear`/`Quaternion`/`EulerRotation`/`Matrix` などMaya非依存(標準`math`のみ)の値型。`Matrix` を除き `@dataclass(frozen=True)` の不変値オブジェクトで、等価比較・ハッシュは自動生成される(`slots=True` はMaya 2022同梱のPython 3.7と非互換のため不使用)。`EulerRotation` は内部値がradian、表示・入出力はdegreesである点に注意。
- `Hlib/components/`: Mesh/NurbsCurveの部分要素を、作成時に番号を固定した参照として提供する(`Vertex`/`Vertices`、`CV`/`CVs`、`Edge`/`Edges`、`Face`/`Faces`、`UV`/`UVs`)。座標は都度シーンから取得し、`Vertex`/`CV`(`PointComponent`系)は代入で即座にシーンへ反映しUndoできる。トポロジー変更後の番号の同一性は保証しない。
- `Hlib/cmds/`: `maya.cmds` 相当の手続き的API(`create_node`、`ls`、`constraint`)を集約する。`Hlib/__init__.py` が起動時にここを走査し、`Hlib.cmds.create_node` と `Hlib.create_node` の両方から呼べるようフラットに再公開する。
- `Hlib/decorators/`: `undo.py` の `undo_chunk` コンテキストマネージャと `undoable` デコレータで複数のMaya操作を単一のUndoチャンクにまとめる。`selection.py` の `preserved_selection` コンテキストマネージャはブロックの前後でMayaの選択状態を保存・復元する(ブロック内で例外が起きても復元される)。
- `Hlib/utils/`: `logger.py`(ログ出力)、`progress.py`(Maya非依存の進捗バー、Slack通知等への`notify`コールバック対応)。
- トップレベル `Hlib/__init__.py` は `Hlib/cmds` の公開関数をフラットに再公開し(`Hlib.create_node`/`Hlib.ls`/`Hlib.constraint`)、`reload()` を公開する。`initialize_node_api` / `initialize_plug_api` を通じて発見した全公開クラスを `__all__` に含める。

### MayaCommandPorts

HTools/Hlibから独立した最小モジュール(依存は `maya.cmds` / `maya.utils` のみ)。GUI起動時のみ遅延実行でcommandPortを `:7001`(MEL)/`:7002`(Python)に開く。既存ポートは開き直さず、失敗はwarning出力に留める。VS Code連携(`tools/send_to_maya.py`)はこの `:7002` を使用する。無効化するには `maya/modules/MayaCommandPorts.mod` をmodules検索対象外へ移動する。

### integrations

- `integrations/slack/`: `post_message(text, channel="random", thread_ts=None)`。環境変数 `SLACK_API_BOT_TOKEN` が未設定または `slack_sdk` が無い場合は `RuntimeError`。
- `integrations/mgear/guide/`: mGearガイド(`isGearGuide` 属性を持つtransform)の取得・更新ヘルパー。`update_guide()` は呼び出し時に初めて `mgear` を import するため、mGear未導入でも本モジュール自体のimportは可能。

## 開発上の注意

- Pythonの単体実行環境(venv/pip install)は用意されていない。全てMaya本体(GUIまたはmayapy)を介して動作する前提で、純粋ロジックのテストであってもMaya経由で実行するのがこのリポジトリの標準的な方法。
- `maya/external/*` はGit submodule。変更が必要な場合は各submoduleのリポジトリ側で行う(親リポジトリからの直接コミット対象ではない)。
- 新規clone後は `git submodule update --init --recursive` が必要。
