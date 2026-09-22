---
applyTo: "MayaHToolsWorkspace.code-workspace,docs/vscode.md,tools/**/*.py,maya/**/*.py,maya/**/*.bat"
---

# VS CodeからMayaを操作する際の指示

- このワークスペースはフォルダ単体ではなく `MayaHToolsWorkspace.code-workspace` を開いて使う。
- 実行前に対象Maya GUIを対応する `maya/maya_<version>_en.bat` から起動する。
- 現在の既定送信先はMaya 2027の `mayapy.exe`。別バージョンでは `maya.pythonExecutable` と `python.defaultInterpreterPath` を同じ対象の `mayapy.exe` に変更する。
- Pythonファイルの実行は通常のPython実行ではなく、保存して `Ctrl+Shift+B` で `tools/send_to_maya.py` を実行する。コード本体は `localhost:7002` のMaya GUI内で `__main__` として実行される。
- 選択範囲送信とブレークポイント実行には対応しない。相対パスは `__file__` を基準にする。
- import済み依存モジュールは自動リロードされない。変更が反映されない場合は既存のリロード手段を確認する。
- 出力は送信終了後にVS Codeターミナルへ表示される。`[Maya] Completed`、トレースバック、`[Maya] FAILED`、終了コードを確認する。
- Mayaのダイアログ表示中や処理中に応答待ちが終了しても、Maya側の処理がキャンセルされたとは判断しない。自動再送しない。
- Maya依存の変更はMaya内で検証し、mayapy単体で送信スクリプトが起動したことだけを機能確認と報告しない。
- `maya/external/` のsubmoduleやユーザーのMaya環境を、依頼なしに変更しない。
