# GitHub Copilot 作業ガイド

## 基本方針

- このリポジトリでの説明・作業報告は日本語で行う。
- 変更前に対象ファイルと近傍の実装・テストを確認し、依頼に必要な範囲だけ変更する。
- 既存の変更、未追跡ファイル、submodule の状態を保持する。無関係な修正や一括整形を行わない。
- 仕様や実行方法は `README.md` と `docs/vscode.md`、既存の実装を確認して判断する。
- Mayaで未実行の処理を動作確認済みと報告しない。

## プロジェクト構成

- `maya/inhouse/HTools/`: Mayaメニューから起動する内製ツール。
- `maya/inhouse/hlib/`: Maya API 2.0 のノード・属性ラッパー、数学型、共通ユーティリティ。
- `maya/inhouse/MayaCommandPorts/`: GUI起動時のcommandPort初期化。HTools/hlibとは独立。
- `maya/inhouse/integrations/`: Slack、mGearなどとの連携。
- `maya/external/`: 外部ツールのGit submodule。原則として直接編集しない。
- `maya/modules/`: Maya用 `.mod` 定義。
- `maya/maya_core.bat` と `maya/maya_*_en.bat`: Mayaの起動環境設定。
- `tools/send_to_maya.py`: 保存済みPythonファイルを起動中のMayaへ送信。

## 実装ルール

- Maya依存コードでは既存の `maya.api.OpenMaya`、ラッパー、共通ヘルパーを優先して再利用する。
- `hlib` のノード・plug型は、既存の `@node_wrapper` / `@plug_wrapper` と自動発見・登録の仕組みに合わせる。不要な手動登録を追加しない。
- `hlib/maths/` はMaya非依存性を維持する。角度は内部ラジアン、入出力は度数法という既存の規約を確認する。
- シーンを変更する処理は既存のUndo対応に従い、必要なら `hlib.decorators.undo` を使う。
- HToolsの新規ツールはカテゴリ内の既存パターンと動的メニュー登録の条件に合わせる。
- UIはPySide6優先、PySide2フォールバックを維持し、対象MayaのQtで利用できるAPIだけを使う。
- 相対リソースパスは `__file__` を基準にする。ユーザー環境の `Maya.env`、認証情報、トークンを無断で変更・記録しない。
- Slackなど外部サービスへ実際に送信する処理は、明示的な依頼なしに実行しない。

## MayaとVS Codeの実行

- Mayaは `maya/maya_<version>_en.bat` から起動する。対象バージョンのインストールを確認する。
- VS Codeでは `MayaHToolsWorkspace.code-workspace` を開き、Maya GUIを起動してから保存済みPythonファイルを `Ctrl+Shift+B` で送信する。
- `mayapy.exe` は送信スクリプトを実行するだけで、対象コードは `localhost:7002` 経由で起動中のMaya GUI内に実行される。
- import済みモジュールは自動リロードされない。必要な場合は `hlib.reload()` を使用する。
- 送信の終了コードは、正常終了0、対象コードの例外1、接続・ファイル等の失敗2。タイムアウトしてもMaya側の処理がキャンセルされたとは限らない。

## 検証

- リポジトリに通常のpytest/CI工程があるとは仮定しない。対象ファイルの既存テストと実行方法を確認する。
- 数学型の変更は `maya/inhouse/hlib/__tests__/test_datatypes.py` をMaya経由で実行する。
- Maya依存コードは通常のPython環境でimportできると仮定せず、必要なら構文チェックとMaya内実行を分けて報告する。
- UI・起動処理の変更では、対象Mayaでの起動、メニュー表示、操作結果を確認する。
- 変更後は可能な限り対象を絞った検証を先に行い、実行できなかった検証項目と理由を明記する。

## Gitと外部依存

- 作業開始時に `git status --short` で既存の変更を確認する。
- `maya/external/` はsubmoduleであるため、変更が必要な場合は対象submoduleのガイドと状態を確認し、親リポジトリの参照更新と区別する。
- `git reset --hard`、`git checkout --`、コミット、ブランチ作成は明示的に依頼された場合だけ行う。
- `.maya-output/` の実行結果は生成物であり、コミット対象にしない。
