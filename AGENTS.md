# Codex 作業ガイド

## 基本方針

- 2026-10-06にユーザーが指定した命名規則: hlib独自の取得/設定メソッドはget/set、メソッド内のアトリビュート名はAttr/Attrs、追加アトリビュートはExtra、型変換はasに統一する。getT/setT等の短縮アクセサーは使用しない。数学型はコピー操作と自身更新を併存し、独自APIの自身更新にはItを付ける。OpenMaya標準名と演算条件は維持し、対応する数学値の戻り型はhlib型へ統一する。引数の長短別名と適用例外の詳細は `docs/hlib-api-design.md` を参照し、今回確定した仕様も下記の変更禁止対象とする。

- hlibの確定済み公開APIの引数仕様は、ユーザーから対象仕様への明示的な変更指示がない限り変更禁止とする。引数名・順序・位置引数/キーワード専用の区分・短縮名/長名・既定値・単位・フラグの意味・戻り値を維持する。リファクタリング、他ライブラリへの追従、命名統一、最適化を理由に変更しない。対象には `ws/worldSpace`、`at`、`ra/r/jo`、`safe/get/fast`、接続方向と `f/l/na`、`Node.addAttr` の型指定・`getPlug` を含む。具体的な仕様は `maya/inhouse/hlib/docs/api_arguments.rst`・`maya/inhouse/hlib/docs/api_methods.rst`・`docs/hlib-api-design.md` を参照する。特に `Node.addAttr()` は既定で追加したPlugを返し、明示的な `getPlug=False` の場合のみNoneを返す。通常のsetterが自身を返す仕様も維持し、既定戻り値をNoneへ変更しない。ドキュメントやテストを先に書き換えて仕様変更を正当化することも禁止する。既存の呼び出し仕様を保つ内部修正・不具合修正は可能とする。

- hlibの公開関数・メソッド・プロパティは全パッケージ共通でlowerCamelCase（`getSettings`・`undoChunk`・`minimumVersion`）とする。クラスはPascalCase。Maya標準名・om2継承/オーバーライド・Python特殊メソッド・標準ライブラリに合わせたAPIは元の名前を維持し、通知APIの`get_logger`/`raise_with_notify`も例外として維持する。引数・内部関数・ローカル変数はsnake_caseを使用できるが、Mayaのコマンドフラグは標準表記を優先する。JSON等の保存キーはAPI改名で変更しない。詳細と例外は`docs/hlib-api-design.md`の「確定したコーディングルール」を参照する。

- hlibではQt関連ライブラリ（PySide/PyQt/shiboken/qtpy等）をimportしない。Maya標準UIはcmds/melとMayaの通知APIで扱い、Qtウィジェット取得・変換は利用側のUIパッケージに置く。

- hlibの日本語表記では、Mayaのattributeを「アトリビュート」と呼ぶ。説明・docstring・コメント・メッセージで統一し、API識別子は変更しない。

- Aiderへの実装委譲は行わない。Maya開発時のGPU・メモリ競合を避けるため、ローカルOllamaも作業のために自動起動・モデルロードしない。実装・レビュー・検証は担当エージェントが直接行う。ユーザーが明示的に再開を指示するまで、この方針を維持する。

- C++の内製コードは日本語のDoxygen形式（`@brief`・`@param`・`@return`、必要時`@note`）でファイル・クラス・全ての名前付き関数を説明する。初心者が追えるよう、所有権・Qtシグナル/スロット・非同期処理・Maya呼出の理由もコメントする。引数や戻り値がないタグは省略し、自明な各行の逐語説明は避ける。PythonはGoogle形式docstringを使用する。詳細は `docs/cpp-documentation.md` を参照する。外部submoduleへ一括適用しない。

- hlib・hlib_*・hrigの通知/出力は `hlib.utils.logger` の `debug`・`info`・`warning`・`error`・`print` に集約する。`error` は通知のみ、例外送出は `raise_with_notify` を使用する。`hlib.cmds.warning` やルートの `hlib.warning` は追加しない。

- hlibのAPIは「Mayaへ問い合わせる操作はメソッド」「保持する値はプロパティ」を基本とする。シーン更新は明示的なメソッドで行う。具体例と判断基準は `docs/hlib-api-design.md` を参照する。

- hlib/hlib_*の実装移動では旧import用の互換ファイル・別名を残さず、使用側（内製ツール・テスト・ドキュメント）を正式な新配置へ更新する。hlib.cmdsの追加は既存の入力解決・短縮フラグ・Undo規則に合わせ、ノード/アトリビュート/UI参照はhlibオブジェクトで返す。数値・真偽値等の照会値は値として返す。生のcmds転送クラスは追加しない。

- hlibの公開フォルダは `cmds`・`nodes`・`plugs`・`components`・`maths`・`scene`・`ui`・`environment`・`events`・`json`・`utils`・`decorators` を基本とする。シーン内の状態・関係は `scene`、Maya標準UIと表示色は `ui`、作業環境・導入状態は `environment`、通知・遅延実行は `events`、汎用関数は `utils` に置く。個別サービスごとにフォルダを増やさず、`hlib_*` も同じ分類に合わせる。

- `hlib.Object` (`object.py`) は単数の `Node`・`Plug`・`Component` の共通基底と種類判別の入口。各型の入力解決は各基底クラス、複数入力の検証は `Nodes` に集約する。数学値・コレクション・UI・保存データを無理に継承させない。旧 `general`・`_core/coerce.py` の互換入口は置かない。

- hlib.cmdsの公開関数とファイルは同名のlowerCamelCaseとし、create/add/set/get等の動詞+対象で命名する。create/add/setは照会を兼ねず、照会・既存対象の編集はオブジェクトのメソッドへ寄せる。lsは慣用名として維持し、delete/duplicate/select等の動詞も維持する。旧名の互換入口は残さず使用側を更新する。

- hlibのクラス実装は原則1クラス1ファイルとする。ただし単数クラスと対応する複数クラスは、単数形の同じファイルにまとめる（例: joint.pyのJoint/Joints、vertex.pyのVertex/Vertices）。既存の分離済みクラスをこの規則だけで移動する必要はない。関連する関数はクラスのメソッドへ、クラスに依存しない汎用関数は `hlib.utils` へ置く。クラスのパッケージ内に関数だけのPythonファイルを追加しない。公開コマンドは上記の命名・責務ルールに従う。

- hlibおよび `hlib_*` 拡張パッケージの一般Pythonファイル名はlowerCamelCaseに統一する（`eulerRotation.py`、`scriptJob.py`、`channelBox.py`、`arrayPlug.py`）。Mayaコマンド/nodeTypeと同名のファイル、`__init__.py`等の特殊名、テスト探索用 `test_*.py` は既存規則を維持する。先頭の内部用 `_` とパッケージ名 `hlib_bifrost` 等は保持する。クラス名や独自メソッド名はこのファイル名規則とは別に扱う。

- hlibはMaya標準の名前・概念と汎用的な基礎APIを扱う。標準の関係型は `scene`、リグ非依存の数値計算は `utils`、骨の追従・Soft IK・補正・操作形状などの独自セットアップは `hrig.setups` に置く。`hlib/animation` は作らない。Bifrostでも演算部品は `hlib_bifrost.utils`、リグの組み方はhrigに置く。

- about/currentTime/cutKey/deleteUI/keyframe/listConnections/listHistory/listRelatives/menu/menuItem/objExists/parent/playbackOptions/setKeyframe はmaya.cmdsを直接使用する。hrigにも適用し、同名hlibラッパーを再追加しない。必要なNode/Plug変換は使用側で明示する。

- hrigのPythonコードはhlibの命名・書式・日本語Google形式docstringに合わせる。ノード・アトリビュート・接続・Undo・イベント管理はhlibの公開APIを基本にし、リグに依存しない機能はhlibへ還元する。具体的な境界と記述例は `docs/hrig-development.md` を参照する。

- 外部ツールの調査メモ・比較表・候補一覧・調査インベントリは `docs/research/` にローカル保存し、Gitへ登録・プッシュしたりSphinxへ掲載したりしない。公開ドキュメントには実装済み機能の仕様・使い方を記載する。

- このリポジトリでの説明・作業報告は日本語で行う。途中経過の報告・質問・確認・最終報告を含め、ユーザーへの返答はすべて日本語にする。英語の資料やツール出力を読んだ後、長い作業の途中、文脈が要約された後でも英語に切り替えない。コード・コマンド・識別子・ログの引用はそのままでよい。
- Claude Code / Codex / GitHub Copilot を並行運用する前提のリポジトリ。作業開始前に
  `WORK_LOG.md` を確認し、他ツールが進行中の範囲と重ならないか確認する。作業開始時に
  「進行中」へ自分の行を追加し、完了時に「完了履歴」へ移す(運用ルールは同ファイル参照)。
- 作業開始時に `git status --short` を確認し、既存の変更や未追跡ファイルを保持する。
- 依頼に必要な範囲を変更し、周辺コードの命名・書式・設計に合わせる。
- 仕様やコマンドは実装を確認する。概要は `README.md`、VS Code連携は `docs/vscode.md` を参照する。
- 完了時は変更内容、実施した検証、未検証の項目を簡潔に伝える。Mayaで未実行なら動作確認済みとしない。

## プロジェクト概要

Windows上でバッチ経由でMayaを起動し、標準環境への影響を抑えて内製・外部ツールをロードするカスタム作業環境。
Pythonコードは `PYTHONPATH` / `MAYA_MODULE_PATH` などを介してロードされ、通常のビルドやパッケージング工程はない。

| パス | 役割 |
| --- | --- |
| `maya/inhouse/HTools/` | Mayaメニューから実行する内製ツール |
| `maya/inhouse/hlib/` | ノード・アトリビュートラッパー、数学型、共通ユーティリティ |
| `maya/inhouse/MayaCommandPorts/` | GUI起動時のcommandPort初期化 |
| `maya/inhouse/MayaCinematicCameraHUD/` | C++プラグイン(別リポジトリのsubmodule)。ビルドは `tools/build_maya_plugin.py`、ロードは `maya/modules/*.mod` |
| `maya/inhouse/integrations/` | SlackやmGearとの連携 |
| `maya/external/` | 外部ツール。Git submoduleの定義は `.gitmodules` を参照 |
| `maya/modules/` | Maya用の `.mod` 定義 |
| `maya/maya_core.bat` | 共通の起動環境設定 |
| `maya/maya_*_en.bat` | バージョン別起動バッチ |
| `tools/send_to_maya.py` | 保存済みPythonファイルを起動中のMayaへ送信 |
| `MayaHToolsWorkspace.code-workspace` | VS Code設定・送信タスク |

## 起動と実行

- 起動バッチは2022・2023・2024・2025・2026・2027用がある。対象バージョンのインストールを確認して使用する。
- バッチは環境変数を設定し、存在する場合はユーザーの `Documents/maya/<version>/Maya.env` を読み込む。ユーザー環境を無断で書き換えない。
- VS Codeでは `MayaHToolsWorkspace.code-workspace` を開き、対象ファイルを保存して `Ctrl+Shift+B` で送信する。
- 現在の送信タスクはMaya 2027の `mayapy.exe` を使用する。実際のパスはワークスペースの `maya.pythonExecutable` を確認する。
- Pythonの送信先は `127.0.0.1:7002`。対象コードは送信側のmayapyではなく、起動中のMaya GUI内で `__main__` として実行される。

リポジトリルートからPowerShellで既存テストを送信する例（Maya GUI起動済みが前提）:

```powershell
& 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' tools/send_to_maya.py maya/inhouse/hlib/__tests__/test_datatypes.py
```

- 対象はこのワークスペース内の保存済み `.py` ファイル全体。選択範囲送信やブレークポイントには対応しない。
- import済み依存モジュールは自動リロードされない。必要な場合は既存のリロード手段を確認する。
- 終了コードは正常終了0、対象コードの例外1、接続・ファイル等の失敗2。出力と最終結果の両方を確認する。
- 応答待ちは300秒で終了するがMaya側の処理はキャンセルされない。タイムアウト時は実行状況を確認し、自動再送しない。
- `.maya-output/` は実行結果の受け渡し用。生成物をコミット対象にしない。

## 実装時の指針

### HTools

- `HTools/userSetup.py` がGUI起動時にメニューを作成する。バッチモードのスキップと同一セッションでの二重初期化防止を維持する。
- カテゴリフォルダ内のツール用 `.py` は動的にメニューへ登録され、`runpy.run_module(..., run_name="__main__")` で実行される。追加前に既存カテゴリと走査条件を確認する。
- UIのPySide6優先・PySide2フォールバックを維持する。対象MayaのPython・Qtで使用できるAPIを選ぶ。
- シーンを変更する処理は既存のUndo対応に合わせ、必要に応じて `hlib/decorators/undo.py` を利用する。

### hlib

- ノード・アトリビュートラッパーは主に `maya.api.OpenMaya`（API 2.0）を使用する。既存のラッパーと共通処理を確認して再利用する。
- 型の追加は `_core/discovery.py` / `_core/registry.py` と既存の `@node_wrapper` / `@plug_wrapper` に合わせる。自動登録を重複する手動登録を加えない。
- 静的解析(Pylance/pyright)は、リポジトリ直下の `pyrightconfig.json` に設定を集約している。`maya.cmds` 等の補完は `python tools/setup_maya_typings.py` で `typings/maya/`(Git対象外)へ型スタブを配置して有効にする。スタブ起因の指摘は警告扱いで、エラーは実際の誤り。詳細は `docs/vscode.md`。
- `hlib.createNode` など実行時に動的公開される名前は、`hlib/__init__.py`・`hlib/cmds/__init__.py`・`hlib/nodes/__init__.py` の `if TYPE_CHECKING:` ブロックで静的解析へ宣言している。コマンドやノードラッパーを追加したら同ブロックにも追記する(`test_typing_exports.py` が不一致を検出する)。
- `hlib.reload()` は既存のリロード入口。変更を反映する際はシーンや保持中のインスタンスへの影響を確認する。
- `hlib/maths/` の値型は OpenMaya API 2.0 の型を継承する(Vector/Translation/Scale/Shear は `om2.MVector`、Quaternion は `MQuaternion`、EulerRotation は `MEulerRotation`、Matrix は `MMatrix`)。演算の意味は om2 に合わせ、値は可変・ハッシュ不可。Maya に依存しない純粋な値型へ戻さない(`easing` だけは標準 `math` のみ)。詳細は `hlib/docs/guide_maths.rst` と `api_naming.rst` の意味の変更の一覧。
- Mayaの信頼済みプラグインの場所(`optionVar SafeModeAllowedlistPaths`)をスクリプトから変更しない。MayaのSafeModeが拒否する設定で、迂回せずユーザーがPreferences > Securityで登録する。
- hlib内では独自のMayaプラグインを実装・同梱・自動ロードしない。`MPxCommand` / `MPxNode` / `MFnPlugin` による登録は、Undo対応やバージョン差の回避目的でも追加しない。既存の内部プラグインもこの方針の解消対象とし、残存している場合は未対応箇所を明記する。Maya標準コマンドと既存のUndo可能な処理を優先し、実現できない機能は制限・未対応として明示する。`hlib.environment`による既存プラグインの状態照会・明示的なロード管理は、この禁止の対象に含めない。

### 外部ツールと連携

- 外部submoduleを内製コードと混同しない。変更が依頼に必要な場合は対象submoduleの状態と独自のガイドを確認し、親リポジトリの参照更新も区別して扱う。
- 無関係なsubmodule更新や外部ライブラリの一括整形を行わない。
- `MayaCommandPorts` はHTools/hlibから独立した構成を維持する。
- Slackへの実投稿など外部への送信を伴うスクリプトは、ユーザーから送信の指示がある場合にのみ実行する。認証トークンをコードやログへ出さない。

## 検証

- 共通のpytest/CIコマンドを前提にせず、変更対象の既存テストと実行方法を確認する。
- 数学型の変更は `maya/inhouse/hlib/__tests__/test_datatypes.py` で検証する。標準の実行経路は上記のMaya送信タスク。
- `test_maya_standalone.py` や `test_slack_postMessage.py` は手動スクリプト。名前だけで安全な一括テストと判断せず、実行前に副作用を確認する。
- Maya依存コードは通常のPythonでimportできると仮定しない。構文チェックとMaya内の動作確認を区別する。
- UI・起動処理の変更では、対象Mayaでの起動、メニュー表示、操作結果を必要な範囲で確認する。実行環境が使えない場合は、その制約と確認手順を報告する。
- ドキュメントのみの変更では内容・参照先・差分を確認し、Mayaの起動は不要。
