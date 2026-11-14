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

1. `py -3 tools/setup_maya_typings.py`を1回実行します。型スタブ`types-maya`（MIT）を`typings/maya/`へ配置します（Git対象外、ネットワークが必要）。
2. VS Codeで`MayaHToolsWorkspace.code-workspace`を開き直すか、`Developer: Reload Window`を実行します。

### mlibのコード整形(ruff)

mlibのコードの整形は[ruff](https://docs.astral.sh/ruff/)で統一しています（人によって空白・空行・改行位置が違わないようにするため）。設定は`maya/inhouse/mlib/ruff.toml`が正本で、行幅160・改行はnative（Windowsの作業ツリーはCRLF）・末尾カンマで改行を強制しない、としています。`required-version = "==0.17.5"`を書いてあるので、**別の版のruffは実行を拒否します**（拡張が同梱する版で整形結果が変わるのを防ぐため）。previewのルールは`explicit-preview-rules = true`でコードを明示したものだけ有効にしてあり、ruffを上げても検査が黙って増えません。

- **入れ方**: `maya\inhouse\mlib\_tools\setup.bat`（ダブルクリックで実行。セットアップはこの1本だけです）。`_tools\.venv`へruffとSphinxをまとめて入れます（`py -3.14`〜`py -3.11`を新しい順に探し、Pythonが無ければMaya 2027〜2025のmayapyで`_tools\.mayapy-site`へ入れます。Sphinx 8.2がPython 3.11以上を要求するためこの範囲です）。PCの環境・PATHは変えません。版は固定してあり（`ruff==0.17.5`）、版を上げると整形結果が変わるため、上げるときはmlib全体を整形し直して一緒にコミットします。Mayaへは入れません（mlibの実行には不要です）。
- **実行**: `maya\inhouse\mlib\_tools\format_mlib.bat`（ダブルクリックで実行。ターミナルからは`--no-pause`、またはコマンドパレットの`Tasks: Run Task` →「mlib: Format with ruff」）。`ruff format`（空白・空行・改行位置・引用符）→ `ruff check --fix`（importの並び・未使用名・Mayaのimport形式・未使用引数・pathlib・文字コード・f-string・全角半角など。選んでいるルールと除外の理由は`ruff.toml`に1行ずつ書いてあります）→ `check_mlib_layout.py --check`（ruffに無い検査）の順に実行します。`--check`を付けると何も変えずに検査するので、コミット前の確認に使います。このバッチはコードの静的解析と修正で、テストは`_tools\test_mlib.bat`が担当します（2本構成。手順はmlibの`CONTRIBUTING.md`）。整形・lintはCIに置いていません。
- **拡張**: VS Codeの[Ruff拡張](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff)を推奨に入れてあります（`MayaHToolsWorkspace.code-workspace`の`extensions.recommendations`）。Pythonファイルの既定の整形ツールもruffにしてあるので、`Shift+Alt+F`で整形できます。保存時の自動整形は各自の設定（`"editor.formatOnSave": true`）で有効にしてください。**ワークスペース共通の設定では有効にしていません**。有効にするとmlib以外のPython（`tools/`・`HTools/`等。ruffの設定ファイルが無く既定の行幅88になる）も整形されてしまうためです。拡張が同梱するruffの版は固定した版と違うことがあるので、最終的な判断はバッチとworkflow（固定した版）で行います。
- **バッチの文字コード**: mlibの`_tools/*.bat`はShift-JIS(CP932)で保存します（コメントを日本語で書くため。UTF-8で保存するとcmdが読み誤ります）。ワークスペースの設定で`.bat`は文字コードを自動判別して開くので（`"[bat]": {"files.autoGuessEncoding": true}`。UTF-8のバッチも混在するため固定にはしていません）、右下の表示が`Shift JIS`になっていることを確かめてから保存してください。保存を誤っても`noMaya/test_mlib_batchFiles.py`が検出します。
- **対象外**: `.pyi`（生成物）・`_docs`・`*.md`は整形しません。初期化順が仕様の`__init__.py`はimportを並べ替えません。フレームのファイル名を`os.path.normcase`で大小を無視して比べる`logger.py`・`decorator.py`は`PTH`（pathlibへの置換）の対象外で、テストはパスをMayaのコマンドへ文字列で渡すため`PTH`と`B023`（ループ内で作って同じ周回で呼び切る関数）の対象外です。理由は`ruff.toml`に書いてあります。
- **ruffに無い検査**: `_tools/check_mlib_layout.py --check`が、定数・`__all__`・`if TYPE_CHECKING:`の位置、クラス内のメンバー順と対になる操作の隣接、内部名とfunction setの取得・関数内importの理由コメント、例外の文言とUndoチャンク名・fastの受け取り、docstringの見出し・Raisesの並び・固定文・用語・公開定数の説明、Python 3.7（Maya 2022）で動く書き方とpropertyのgetter、公開入口の入力assert、列挙を見ます。`--fix`が直すのはクラス内メンバーの順だけで、並べ替えた後の空行は`ruff format`が直します。

### mlibの型スタブ

mlibの関数・メソッドは型注釈を持たず、型はdocstring（`Args:`の`name (type):`と`Returns:`の先頭の`type:`）にだけ書いてあります。Pylanceはdocstringを型として読まないため、そのままでは`mlib.ls()`の戻り値などの型が分からず、その先の補完・引数ヒントが出ません。mlibの`_tools/generate_mlib_stubs.py`（`maya/inhouse/mlib/_tools/`）がdocstringの型を注釈にした型スタブ（`.pyi`）を、各`.py`の隣（`maya/inhouse/mlib/nodes/node.pyi`等）へ作ります。

- **設定は不要**: Pylanceは`.py`の隣の`.pyi`を優先して読むため、`stubPath`等を書かなくても認識されます。mlibのフォルダーだけを開いた場合や、別のプロジェクトから`maya/inhouse`をimportの検索パスに入れてmlibを使う場合も同じです。F12（定義へ移動）は`.pyi`を開き、本体を見るときは右クリックの「Go to Source Definition」を使います。
- **Gitで管理**: スタブはコミットするので、cloneしただけで補完が効きます。Pythonは実行時に`.pyi`を読まないため、Mayaの動作には影響しません。スタブ自体の警告で問題一覧が埋まらないよう、`pyrightconfig.json`の`exclude`で解析対象からは外しています（型の参照には使われます）。
- **docstringを変えたら作り直す**: mlibを編集してdocstringの型や引数を変えたら、`maya\inhouse\mlib\_tools\generate_mlib_stubs.bat`（ダブルクリックで実行。ターミナルからは`--no-pause`を付ける。またはコマンドパレットの`Tasks: Run Task` →「mlib: Update type stubs」）で作り直し、`.py`と一緒にmlibのリポジトリでコミットします。古いままでも静的解析・テストは失敗しません（2026-11-14のユーザー指定で、スタブとSphinxの自動検査を外しました）。内容が変わったファイルだけを書き換え、元の`.py`を消したスタブ（先頭行が生成の印のもの）は削除します。`--check`は作り直さずに最新かだけを確かめ（古ければ終了コード1）、`--report`は注釈にできなかった型を一覧表示します。通常のPython 3.9以降で動き、Mayaは不要です。バッチは`py -3.14`〜`py -3.9`を新しい順に探し(`python`と3.15以降は使いません)、Pythonを入れていないPCではMaya 2027〜2023のmayapyを使います(生成される内容は同じです)。
- **引数で戻り値が変わるAPI**は、引数ごとの戻り値を`@overload`で補っています。
  - `mlib.ls(type="joint")`は`Joints`、`type="skinCluster"`は`SkinClusters`、`type="transform"`等の登録済みの型名は`list[Transform]`等、`type="vertex"`等のコンポーネントは`list[Vertex]`等、そのほかの型名は`list[Node]`、`type`無しは`list[Node | Plug | Component]`。型名とクラスの対応は`nodes/__init__.py`の`_WRAPPER_CLASSES`から読みます。
  - `mlib.createNode("transform")`は`Transform`等（登録済みの型名だけ。そのほかは`Node`）。
  - `getConnections`・`getSource`・`getDestinations`は`asNode`・`asPair`・`index`の指定で`list[Plug]`・`list[Node]`・`Node | None`等。`c`・`connections`でのペア指定は全候補の合併型になります。
  - `Joints`・`Vertices`等の複数形のコレクションは、`for`と`[番号]`で要素の型（`Joint`・`Vertex`等）を返します。
- **派生クラスの型**: `mlib.getNode()`は実際には`Joint`等の派生クラスを返しますが、型は`Node`になります。`Node`の未定義の属性は、実行時と同じく`Plug`（`node.tx`等の動的アトリビュート）として扱います。そのため`Node`型のまま派生クラスのメソッド（`getParent`等）を呼ぶと警告になり、その先は`Plug`の補完になります。派生クラスの補完を出したいときは`Joint("joint1")`・`Transform("pCube1")`のようにクラスで取得するか（型が違えば例外）、`joint = mlib.ls("joint1", type="joint")[0]`のように型が決まる書き方にするか、`isinstance`で絞ります。`DagNode.getParent()`・`getParents()`・`getRoot()`は`Transform`型を返します（DAGの親はTransform系）。`Plug`・`Component`の未定義の属性は`Any`扱いにしています（基底クラスのメソッドは補完に出ます。属性名の打ち間違いは検出されません）。`Plug`は`[]`と`for`も受け付けます（`getPlug()`がマルチアトリビュートでも`Plug`型になるため）。docstringで`object`と書いた戻り値（`Plug.get()`等）は`Any`にしています。
- **ルートのクラス**: `mlib.Joint`・`mlib.Vector`等(各パッケージの公開クラス)は、実行時はルートの`__getattr__`で取得し、補完は`mlib/__init__.pyi`の`from .nodes import Joint as Joint`等の再公開で出ます(生成スクリプトが`_CLASS_PACKAGES`と各パッケージの`__all__`から書き出します)。登録の無い型の生成クラス(`mlib.PointLight`等)は実行時には使えますが、補完には出ず`type`型になります。

設定はリポジトリ直下の`pyrightconfig.json`に集約しています（Pylanceが読み込みます）。解析対象、`extraPaths`（`maya/inhouse`・cymel・mgear等）、スタブの場所（`typings`）、ルールの重大度を定義しています。ユーザー設定の`python.analysis.extraPaths`は、この設定ファイルの`extraPaths`が優先されます。

- スタブは完全ではないため、Mayaの実挙動と食い違う指摘は**警告**にしています。エラー（赤）として残るのは、未定義変数などの実際の誤りです。
- `mlib.createNode`などの公開名は、各`__init__.py`の明示importと`__all__`で定義しています。コマンドやノードラッパーを追加したら、使用する公開入口へ追記してください。型選択用の登録対象は各パッケージの`_WRAPPER_CLASSES`へ明示します。`common`は循環参照を避ける遅延公開を使うため、公開表と`if TYPE_CHECKING:`の宣言も揃えます。`maya/inhouse/mlib/_tools/check_mlib_exports.py`と関連テストが不一致を検出します。
- コマンドラインでも同じ設定で確認できます: `pip install pyright`のあと、リポジトリ直下で`pyright --pythonpath "C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe"`。

## 起動を軽くする設定

`MayaHToolsWorkspace.code-workspace` に、起動時の重さを避ける設定を入れてあります(2026-11-14。原因はログと計測で確認)。

- **C/C++の索引から外部ツールを外す**(`C_Cpp.files.exclude`): `maya/external` は9GB超・約30万ファイルあり、C/C++拡張が全部を索引すると索引データベースが2GBを超え、起動のたびにディスクとCPUを長く使っていました。起動時のCMakeの構成も止めています(`cmake.configureOnOpen: false`)。
- **Gitのsubmoduleの変更確認と自動fetchを省く**(`git.ignoreSubmodules`・`git.detectSubmodules`・`git.autofetch`): submoduleが150個以上あり、`git status` が1回数秒〜15秒かかっていました(省くと約0.3秒)。submoduleの中を編集したときは、そのsubmoduleのフォルダーで状態を確かめてください。
- **ファイル監視・検索から外す**(`files.watcherExclude`・`search.exclude`): `maya/external`・`maya/site-packages`・`.maya-output`・mlibの `_tools/.venv` やSphinxの生成物など。

索引の範囲を変えた後に古い索引が残って重いときは、VS Codeを閉じてから `%LOCALAPPDATA%\Microsoft\vscode-cpptools\<ワークスペースのID>` を削除すると、次の起動で作り直されます。GitHub Copilot Chat や Cline などのAI拡張も起動時にCPUを使います(ログで拡張ホストの応答停止の主な原因でした)。重いときは、このワークスペースだけ無効にしてください。

## GitHub共有

ワークスペース、`tools/send_to_maya.py`、本書をコミット対象にします。
ワークスペースのフォルダ参照は相対パスなのでクローン先を選びません。
Mayaのインストールパスだけ各環境に合わせてください。
認証トークン、追加サーバー、自動インストール設定はありません。

## mlib datatypesテスト

`maya/inhouse/mlib/__tests__/inMaya/unit/maths/test_init_valueTypes.py`を開いてCtrl+Shift+Bで送信すると、そのファイルのテストが実行されます。専用タスクやpytestの導入は不要です。VS CodeターミナルとMayaの両方で各テストと最終結果（OK / FAILED）を確認できます。

## 出力の取得範囲

送信したPythonコードの実行中のstdout/stderr（print、unittest出力等）と未処理例外を取得し、実行終了後にまとめて表示します。リアルタイム転送ではありません。MayaネイティブのMEL出力・API警告や、終了後の遅延コールバックの出力は対象外です。既存のloggingハンドラーは作成時の出力先を保持する場合があります。実行中の別スレッドのPython出力が混ざる場合があります。

結果の受け渡しに`.maya-output/`内の実行ごとに異なるJSONを使います。取得後は削除し、Git対象外としています。タイムアウト後に結果が届く場合はファイルが残ります。
