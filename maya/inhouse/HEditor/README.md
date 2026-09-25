# HEditor

Maya用のPythonスクリプトエディタの初期実装です。VS CodeのDark+を参考にした配色、タブ、行番号、補完候補、出力欄を備えています。hlibとは独立しています。

## 起動

ワークスペースの起動バッチでMayaを起動し、Pythonタブで実行します。

```python
import heditor
heditor.show()
```

`maya/modules/HEditor.mod` がPythonパスとバージョン別プラグインパスを設定します。プラグインのロードは `show()` を呼んだ時だけ行います。起動済みのMayaには、`.mod` を追加した後の再起動が必要です。

プラグインの信頼確認が出た場合はMayaの画面で確認してください。HEditorはSecurity設定を変更しません。

0.1.1では、補完準備中に入力した内容を準備完了後に再要求します。ロード済みの`maya.cmds`の候補を出すために検索パスの走査を待つこともありません。候補更新時のメモリ管理も修正しています。右下の`Completion: ready`で準備状態を確認できます。旧版を起動済みの場合は、編集中のスクリプトとシーンを保存してMayaを再起動してください。C++プラグインはPythonの`reload()`だけでは更新されません。

## 操作

| 操作 | キー／場所 |
| --- | --- |
| 補完候補 | 入力時、または Ctrl+Space |
| 候補の確定 | Enter／Tab |
| 選択範囲を実行（選択なしなら全体） | Ctrl+Enter |
| タブ全体を実行 | F5 |
| 新規／開く／保存 | Ctrl+N／Ctrl+O／Ctrl+S |
| 検索 | Ctrl+F |
| 補完情報の再取得 | Refresh completion |

0.1.2から、コードはMaya標準のPython実行経路で実行し、変数の名前空間も標準Script Editorと共有します。HEditorの実行結果はMaya共通の出力へ流れ、標準Script Editorにも表示されます。HEditor側は`MCommandMessage`の出力通知を購読し、他のエディタからの出力・警告・エラーも表示します。stdout/stderrの置き換えは行いません。シーン操作のUndo可否は実行したコマンドに従い、自動のUndoチャンクは追加しません。

共有対象はHEditorを初めて開いた後のMaya出力です。過去の履歴の取り込みや、別エディタが独自に保持するログの同期は行いません。Clear outputはHEditorの表示だけを消去します。HEditor本体とスクリプト実行はMayaと同じプロセスで、別プロセスなのは補完ワーカーだけです。

ファイルはUTF-8を使用します。未保存のタブを閉じる時は保存確認が出ます。通常のウィンドウ終了は非表示になり、そのMayaセッション中はタブを保持します。Maya終了後のタブ復元は未実装です。

## 補完の仕組み

- C++/Qtで編集・表示・要求の世代管理を行います。
- Mayaのメインスレッドで、現在の`sys.path`とロード済みモジュールの公開名を取得します。
- 別の`mayapy -S`プロセスが、標準ライブラリ`ast`でソースを解析します。Mayaの初期化や補完対象のimportは行いません。
- 未ロードのソース解析結果はメモリ内にキャッシュし、ファイルの更新時刻・サイズが変わったら再解析します。ロード済みモジュールでは取得した実在名を優先し、検索パスを走査しません。
- 入力後100msで補完を要求します。処理中の要求は最新の入力へまとめ、古い回答を表示しません。応答が10秒ない場合は補完ワーカーだけを停止します。

Jedi・Pyright等、追加のPythonライブラリは不要です。C++のみでPython構文を独自実装する代わりに、Maya同梱のPython標準ライブラリを解析補助に使用しています。

`import maya.cmds as cmds`の別名、`from package import Class`、モジュールの公開名、ソース上のクラスの直接定義メソッド、トップレベルのローカル関数を補完します。ロード済みの`hlib.ls`など動的な公開名も対象です。関数の引数名は候補のツールチップで確認できます。

新しいパッケージの配置、実行後のimport、`sys.path`の変更、hlibのリロード後は **Refresh completion** を押してください。

## 現段階の制限

- Python専用です。MEL、デバッガー、LSP、VS Code拡張機能は未対応です。
- 関数の戻り値や任意のインスタンスの型推論、継承メソッドの完全な解決、ネストしたスコープの解析は未対応です。
- zip内ソース、未ロードのバイナリ拡張、`__getattr__`で生成される未知の属性は完全には補完できません。
- 補完は静的な名前の候補であり、型・構文の正しさを保証するものではありません。
- スクリプト実行自体はMayaのメインスレッドで行うため、長時間の実行中はMayaが待機します。
- 現在の検証対象はWindowsのMaya 2024／2027です。他のバージョンでは専用バイナリのビルドと検証が必要です。

## 開発・テスト

リポジトリ直下から実行します。Maya devkitとVisual Studioの既存ビルド基盤を使用します。

```powershell
& 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' tools/build_maya_plugin.py maya/inhouse/HEditor --versions 2024 2027
& 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/HEditor/tests/run_tests.py 2024 2027
```

テストは補完ユニットテスト、Maya standaloneでの`.mod`／プラグイン／実在する補完候補の確認、同じC++ウィジェットによるoffscreen描画・補完挿入・実行ボタン確認に分かれています。ログ・画像は`.maya-output/heditor-tests/`に保存します。offscreen検証とMaya GUI内での操作確認は別です。

GUI確認は次のコマンドで、既存のMayaとは別の空シーン・専用設定を使用して実施できます。

```powershell
& 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/HEditor/tests/run_gui.py 2024
& 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/HEditor/tests/run_gui.py 2027
```

テスト用モジュールディレクトリにはHEditorの`.mod`だけを用意します。ワークスペース全体の外部モジュールを読み込んでいた従来の起動タイムアウトは、この構成で解消しました。普段の起動バッチ・ユーザー設定・信頼設定は変更しません。外部ツールを全て有効にした構成の互換性検証とは別です。

GUI内で表示、コード全体の実行、標準Script Editorとの双方向の出力・変数共有、日本語・警告・例外の表示、実際の補完候補の表示、Enterによる確定、選択範囲だけの実行、閉じる／アンロードを確認します。結果・画面・候補一覧の画像を`.maya-output/heditor-gui/<日時>/`に保存します。

過去の検証結果と変更内容はリポジトリの`WORK_LOG.md`を参照してください。

起動／テストの期限は各120秒、終了待ちは30秒です。`--timeout`と`--shutdown-timeout`で秒数を指定できます。タイムアウト時はテストが起動したプロセスだけを停止します。`result.json`はGUIテスト自体、`monitor.json`は起動／実行／終了の監視、`run-result.json`は両者をまとめた結果です。テスト成功後もMayaが終了しなかった場合は、GUI成功と終了タイムアウトの両方を記録し、終了コードは1になります。

表示される速度計測はワーカーのキャッシュ済み名前検索だけの所要時間です。初回起動・IPC・描画・ネットワークドライブを含むエンドツーエンドの速度ではありません。
