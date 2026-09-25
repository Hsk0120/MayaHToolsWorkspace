# VS CodeからMayaへ実行

## 初回設定

リポジトリ直下の`MayaHToolsWorkspace.code-workspace`をVS Codeで開きます。
フォルダだけを開く場合は、このワークスペース内のタスク設定は読み込まれません。
Maya送信用の外部拡張機能やpipパッケージは不要です。

既定はWindowsのMaya 2027です。別バージョンや別インストール先では、
ワークスペースファイルの次の2設定を使うMayaの`mayapy.exe`へ変更してください。

- `maya.pythonExecutable`: 送信タスクが実際に使うPython
- `python.defaultInterpreterPath`: Microsoft Python拡張を使用する場合の初期インタープリター

Python拡張は送信には不要です。導入済みで以前別のPythonを選んでいた場合は、
`Python: Select Interpreter`から同じmayapy.exeを選び直してください。

## 毎回の操作

1. このリポジトリのバッチからMayaを起動します。
2. VS Codeで実行したい`.py`ファイルを開きます。
3. **Ctrl+S → Ctrl+Shift+B**で送信します。タスク起動時にも保存される設定です。
4. 実行終了後、Python出力と例外がVS Codeターミナルに表示されます。Maya側にも同じ出力が残ります。

確認用コード（シーンは変更しません）:

```python
import maya.cmds as cmds
print('VS Code -> Maya:', cmds.about(version=True))
print('Selection:', cmds.ls(selection=True))
```

## 動作

mayapyは送信スクリプトを実行し、localhost:7002へファイル実行コマンドを送ります。
対象ツール自体は**起動中のMaya GUI内**で実行されます。
mayapyを選択するだけでMaya GUIに接続するわけではありません。
VS Codeの通常の「Pythonファイルを実行」とは別の操作です。

対象はワークスペース内の保存済みPythonファイル全体です。選択範囲送信や
ブレークポイントには対応しません。実行時の`__name__`は`__main__`です。
import済みの依存モジュールは自動リロードしません。
相対リソースパスは`__file__`を基準にしてください。

正常終了は`[Maya] Completed`、未処理例外はトレースバックと`[Maya] FAILED`で表示します。終了コードは正常0、コード内の例外1、接続やファイル等の失敗2です。
Mayaがダイアログ表示中などの場合は実行が待機することがあります。
300秒で応答待ちは終了しますが、Maya側の処理はキャンセルされません。

## 補完と静的解析(Pylance)

Mayaの`maya.cmds`や`maya.api.OpenMaya`はPythonソースの無い`.pyd`/`.pyc`のため、そのままでは補完・引数チェックが効きません。次の準備で解決します。

1. `python tools/setup_maya_typings.py`を1回実行します。型スタブ`types-maya`（MIT）を`typings/maya/`へ配置します（Git対象外、ネットワークが必要）。
2. VS Codeで`MayaHToolsWorkspace.code-workspace`を開き直すか、`Developer: Reload Window`を実行します。

設定はリポジトリ直下の`pyrightconfig.json`に集約しています（Pylanceが読み込みます）。解析対象、`extraPaths`（`maya/inhouse`・cymel・mgear等）、スタブの場所（`typings`）、ルールの重大度を定義しています。ユーザー設定の`python.analysis.extraPaths`は、この設定ファイルの`extraPaths`が優先されます。

- スタブは完全ではないため、Mayaの実挙動と食い違う指摘は**警告**にしています。エラー（赤）として残るのは、未定義変数などの実際の誤りです。
- `hlib.createNode`のように実行時に動的公開される名前は、各`__init__.py`の`if TYPE_CHECKING:`ブロックで静的解析へ宣言しています。コマンドやノードラッパーを追加したら、このブロックにも追記してください（`test_typing_exports.py`が不一致を検出します）。
- コマンドラインでも同じ設定で確認できます: `pip install pyright`のあと、リポジトリ直下で`pyright --pythonpath "C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe"`。

## GitHub共有

ワークスペース、`tools/send_to_maya.py`、本書をコミット対象にします。
ワークスペースのフォルダ参照は相対パスなのでクローン先を選びません。
Mayaのインストールパスだけ各環境に合わせてください。
認証トークン、追加サーバー、自動インストール設定はありません。

## hlib datatypesテスト

`maya/inhouse/hlib/__tests__/test_datatypes.py`を開いてCtrl+Shift+Bで送信すると、全9件のテストが実行されます。専用タスクやpytestの導入は不要です。VS CodeターミナルとMayaの両方で各テストと最終結果（OK / FAILED）を確認できます。

## 出力の取得範囲

送信したPythonコードの実行中のstdout/stderr（print、unittest出力等）と未処理例外を取得し、実行終了後にまとめて表示します。リアルタイム転送ではありません。MayaネイティブのMEL出力・API警告や、終了後の遅延コールバックの出力は対象外です。既存のloggingハンドラーは作成時の出力先を保持する場合があります。実行中の別スレッドのPython出力が混ざる場合があります。

結果の受け渡しに`.maya-output/`内の実行ごとに異なるJSONを使います。取得後は削除し、Git対象外としています。タイムアウト後に結果が届く場合はファイルが残ります。
