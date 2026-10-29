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

### mlibの型スタブ

mlibの関数・メソッドは型注釈を持たず、型はdocstring（`Args:`の`name (type):`と`Returns:`の先頭の`type:`）にだけ書いてあります。Pylanceはdocstringを型として読まないため、そのままでは`mlib.ls()`の戻り値などの型が分からず、その先の補完・引数ヒントが出ません。`tools/generate_mlib_stubs.py`がdocstringの型を注釈にした型スタブ（`.pyi`）を、各`.py`の隣（`maya/inhouse/mlib/nodes/node.pyi`等）へ作ります。

- **設定は不要**: Pylanceは`.py`の隣の`.pyi`を優先して読むため、`stubPath`等を書かなくても認識されます。mlibのフォルダーだけを開いた場合や、別のプロジェクトから`maya/inhouse`をimportの検索パスに入れてmlibを使う場合も同じです。F12（定義へ移動）は`.pyi`を開き、本体を見るときは右クリックの「Go to Source Definition」を使います。
- **Gitで管理**: スタブはコミットするので、cloneしただけで補完が効きます。Pythonは実行時に`.pyi`を読まないため、Mayaの動作には影響しません。スタブ自体の警告で問題一覧が埋まらないよう、`pyrightconfig.json`の`exclude`で解析対象からは外しています（型の参照には使われます）。
- **docstringを変えたら作り直す**: mlibを編集してdocstringの型や引数を変えたら、`tools\generate_mlib_stubs.bat`（またはコマンドパレットの`Tasks: Run Task` →「mlib: Update type stubs」）で作り直し、`.py`と一緒にコミットします。古いままだと`__tests__/unit/test_static_stub_generation.py`（`runStatic.py`）が失敗します。内容が変わったファイルだけを書き換え、元の`.py`を消したスタブ（先頭行が生成の印のもの）は削除します。`--check`は作り直さずに最新かだけを確かめ（古ければ終了コード1）、`--report`は注釈にできなかった型を一覧表示します。通常のPython 3.9以降で動き、Mayaは不要です。
- **引数で戻り値が変わるAPI**は、引数ごとの戻り値を`@overload`で補っています。
  - `mlib.ls(type="joint")`は`Joints`、`type="skinCluster"`は`SkinClusters`、`type="transform"`等の登録済みの型名は`list[Transform]`等、`type="vertex"`等のコンポーネントは`list[Vertex]`等、そのほかの型名は`list[Node]`、`type`無しは`list[Node | Plug | Component]`。型名とクラスの対応は`nodes/__init__.py`の`_WRAPPER_CLASSES`から読みます。
  - `mlib.createNode("transform")`は`Transform`等（登録済みの型名だけ。そのほかは`Node`）。
  - `getConnections`・`getSource`・`getDestinations`は`asNode`・`asPair`・`index`の指定で`list[Plug]`・`list[Node]`・`Node | None`等。`c`・`connections`でのペア指定は全候補の合併型になります。
  - `Joints`・`Vertices`等の複数形のコレクションは、`for`と`[番号]`で要素の型（`Joint`・`Vertex`等）を返します。
- **スタブだけで緩めている点**: `mlib.getNode()`は実際には`Joint`等の派生クラスを返しますが、型は`Node`になります。派生クラスのメソッドを使っても警告にならないよう、`Node`・`Plug`・`Component`の未定義の属性は`Any`扱いにしています（基底クラスのメソッドは補完に出ます。属性名の打ち間違いは検出されません）。派生クラスの補完を出したいときは`joint = mlib.ls("joint1", type="joint")[0]`のように型が決まる書き方にするか、`isinstance`で絞ります。`Plug`は`[]`と`for`も受け付けます（`getPlug()`がマルチアトリビュートでも`Plug`型になるため）。docstringで`object`と書いた戻り値（`Plug.get()`等）は`Any`にしています。

設定はリポジトリ直下の`pyrightconfig.json`に集約しています（Pylanceが読み込みます）。解析対象、`extraPaths`（`maya/inhouse`・cymel・mgear等）、スタブの場所（`typings`）、ルールの重大度を定義しています。ユーザー設定の`python.analysis.extraPaths`は、この設定ファイルの`extraPaths`が優先されます。

- スタブは完全ではないため、Mayaの実挙動と食い違う指摘は**警告**にしています。エラー（赤）として残るのは、未定義変数などの実際の誤りです。
- `mlib.createNode`などの公開名は、各`__init__.py`の明示importと`__all__`で定義しています。コマンドやノードラッパーを追加したら、使用する公開入口へ追記してください。型選択用の登録対象は各パッケージの`_WRAPPER_CLASSES`へ明示します。`common`は循環参照を避ける遅延公開を使うため、公開表と`if TYPE_CHECKING:`の宣言も揃えます。`maya/inhouse/mlib/__tests__/checks/check_mlib_exports.py`と関連テストが不一致を検出します。
- コマンドラインでも同じ設定で確認できます: `pip install pyright`のあと、リポジトリ直下で`pyright --pythonpath "C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe"`。

## GitHub共有

ワークスペース、`tools/send_to_maya.py`、本書をコミット対象にします。
ワークスペースのフォルダ参照は相対パスなのでクローン先を選びません。
Mayaのインストールパスだけ各環境に合わせてください。
認証トークン、追加サーバー、自動インストール設定はありません。

## mlib datatypesテスト

`maya/inhouse/mlib/__tests__/unit/test_datatypes.py`を開いてCtrl+Shift+Bで送信すると、全9件のテストが実行されます。専用タスクやpytestの導入は不要です。VS CodeターミナルとMayaの両方で各テストと最終結果（OK / FAILED）を確認できます。

## 出力の取得範囲

送信したPythonコードの実行中のstdout/stderr（print、unittest出力等）と未処理例外を取得し、実行終了後にまとめて表示します。リアルタイム転送ではありません。MayaネイティブのMEL出力・API警告や、終了後の遅延コールバックの出力は対象外です。既存のloggingハンドラーは作成時の出力先を保持する場合があります。実行中の別スレッドのPython出力が混ざる場合があります。

結果の受け渡しに`.maya-output/`内の実行ごとに異なるJSONを使います。取得後は削除し、Git対象外としています。タイムアウト後に結果が届く場合はファイルが残ります。
