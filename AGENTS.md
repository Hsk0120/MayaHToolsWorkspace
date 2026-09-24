# Codex 作業ガイド

## 基本方針

- このリポジトリでの説明・作業報告は日本語で行う。
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
| `maya/inhouse/hlib/` | ノード・属性ラッパー、数学型、共通ユーティリティ |
| `maya/inhouse/MayaCommandPorts/` | GUI起動時のcommandPort初期化 |
| `maya/inhouse/integrations/` | SlackやmGearとの連携 |
| `maya/external/` | 外部ツール。Git submoduleの定義は `.gitmodules` を参照 |
| `maya/modules/` | Maya用の `.mod` 定義 |
| `maya/maya_core.bat` | 共通の起動環境設定 |
| `maya/maya_*_en.bat` | バージョン別起動バッチ |
| `tools/send_to_maya.py` | 保存済みPythonファイルを起動中のMayaへ送信 |
| `MayaHToolsWorkspace.code-workspace` | VS Code設定・送信タスク |

## 起動と実行

- 起動バッチは2022・2024・2025・2026・2027用がある。対象バージョンのインストールを確認して使用する。
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

- ノード・属性ラッパーは主に `maya.api.OpenMaya`（API 2.0）を使用する。既存のラッパーと共通処理を確認して再利用する。
- 型の追加は `_core/discovery.py` / `_core/registry.py` と既存の `@node_wrapper` / `@plug_wrapper` に合わせる。自動登録を重複する手動登録を加えない。
- `hlib.reload()` は既存のリロード入口。変更を反映する際はシーンや保持中のインスタンスへの影響を確認する。
- `hlib/maths/` のMaya非依存性を維持する。角度の度・ラジアン、行列の規約は対象型の実装とテストに合わせる。

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
