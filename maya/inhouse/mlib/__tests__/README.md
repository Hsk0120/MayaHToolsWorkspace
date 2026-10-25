# mlibのテスト

このフォルダとmlib本体を一緒に持ち出せば、ワークスペースの`tools/`なしで実行できます。
mlrig・HTools・cymel・mlib拡張は、本体テストの必須依存に含めません。

## フォルダ

```text
__tests__/
├─ README.md          この手順
├─ run.bat            Maya版テストのWindows用入口
├─ runMaya.py         mayapyで単体・結合テストを実行
├─ runStatic.py       Maya不要の単体テスト・静的検査
├─ runGui.py          専用Maya GUIで単体・結合・表示を確認
├─ run_all_tests.py   テスト探索・実行・ログ集計
├─ unit/             個々の関数・クラス・APIを確認する単体テスト
│  └─ test_static_*.py  通常のPythonで動くもの
├─ integration/      複数のmlib機能を組み合わせる結合テスト
├─ checks/           公開名・配置・生成文書の検査ツール
├─ support/          GUI内の実行・プロセス監視の補助
├─ manual/           自動実行しない個別確認・API調査
└─ _output/          結果・ログ・専用Maya設定（Git対象外）
```

`unit`は例えばノード生成や数学型の演算、`integration`は接続と値設定、
TRSと行列の往復、通常更新とUndoなどを一緒に確認します。
単体テストでもOpenMayaやシーンを使うものはMayaが必要です。

## 準備

- Maya版: 検証対象のMayaと、その実行に必要なライセンスを用意します。GUIの事前起動は不要です。
- 静的検査: 通常のPython 3.11以上を使います。`_docs/.venv`のPythonでも実行できます。
- 以下のコマンドは**この`__tests__`フォルダ**から実行します。Mayaのテスト環境はランナーが用意します。

## 単体・結合を分けて実行

PowerShellで実行します。

```powershell
# 通常Pythonで動く単体テストと、公開名・コード配置の検査
python .\runStatic.py

# Mayaのインストール状況を確認するだけ
.\run.bat --list

# 個々のAPIの単体テスト
.\run.bat --versions 2027 --suite unit

# 複数のmlib機能を組み合わせる結合テスト
.\run.bat --versions 2027 --suite integration

# 両方を実行（--suite省略時もall）
.\run.bat --versions 2027 --suite all

# 対象ファイルだけ実行。指定ミスは失敗として報告する
.\run.bat --versions 2027 --tests test_datatypes.py

# 複数バージョンで同じテストを実行
.\run.bat --versions 2022 2027 --suite all
```

`run.bat`は検出したmayapyを制御用Pythonに使い、実テストには各版のmayapyを使います。
通常Pythonからは`python .\runMaya.py --versions 2027 --suite unit`でも実行できます。
引数を付けず`run.bat`を実行すると、2022〜2027の全版を対象にします。
未インストールは`missing`と記録します。`--allow-missing`はこの状態による終了コードだけを抑制します。

Mayaが標準配置にない場合は、`--install-root D:\Autodesk`、または
`$env:MAYA_TEST_LOCATION_2027 = 'D:\Autodesk\Maya2027'`で場所を指定します。
制御用Pythonを固定する場合は`MLIB_TEST_PYTHON`へ実行ファイルのパスを設定します。

## 基本操作を重点的に確認する

正常系に加え、失敗後の値・接続・ロック、通常のUndo/redo、fastとsafeの違いを確認します。
これらのテストは専用の名前空間を作り、終了時に削除します。

| 区分 | ファイル | 主な確認内容 |
| --- | --- | --- |
| 単体 | `unit/test_delete_basics.py` | 入力型、削除前の拒否、接続された子孫の保護、保持参照の復元 |
| 単体 | `unit/test_plug_basics.py` | 基本型の値、接続の置換・切断、ロック、疎配列、内部単位 |
| 単体 | `unit/test_transform_basics.py` | ローカル/ワールド、TRS、回転順序、親変更、反転不能な親 |
| 結合 | `integration/test_basic_scene_workflows.py` | DG評価、接続と削除、親子変更、複数操作のUndoと例外時の巻戻し |

```powershell
# 基本操作の単体テストだけ
.\run.bat --versions 2027 --suite unit --tests test_delete_basics.py test_plug_basics.py test_transform_basics.py

# 基本操作を組み合わせる結合テストだけ
.\run.bat --versions 2027 --suite integration --tests test_basic_scene_workflows.py
```

これは既存テストを補う重点確認です。全体の回帰確認には`--suite all`を使います。
`undoChunk`の例外では先行更新を残し、`undoTransaction`では通常のUndo対象更新の巻戻しを試みます。
fastの更新はどちらのコンテキストでもUndo対象にしません。

## GUIで確認する

```powershell
python .\runGui.py --versions 2027 --suite unit
python .\runGui.py --versions 2027 --suite integration
python .\runGui.py --versions 2027 --suite visual
```

`unit`・`integration`は同名フォルダのテスト、`visual`は実パネルへの適用と画像保存です。
`--suite all`では3つを別々の専用GUIで実行します。
各GUIは専用設定を使い、ランナーが起動したMayaだけを終了します。
自動判定と、保存画像の目視確認は別の結果です。

テストにはシーンの初期化があるため、**作業中のMayaへ一式を送信しないでください**。
GUI用スイートはランナーが設定する`MLIB_DISPOSABLE_GUI=1`を確認します。
通常のPreferencesや、起動中のMayaのシーンは変更しません。

## 結果を見る

テストが失敗すると、起動元のターミナルにも詳細ログの絶対パス・失敗ファイル名・
エラーの行番号と内容を表示します。成功したテストの詳しい出力はログにだけ保存します。
Mayaの起動・終了の異常や時間切れでは、取得できた例外と起動ログのパスを表示します。

- mayapy: `_output/maya/<日時>/summary.txt`と`summary.json`
- GUI: `_output/gui/<日時>/summary.txt`と`summary.json`
- 各版の`result.json`: 実際のMaya/API/Python版、実行件数、失敗、スキップ理由
- 詳細ログ: 失敗した検査とトレースバック

`passed`は対象検査の成功、`failed`は検査失敗、`error`は起動・初期化などの異常、
`timeout`は時間切れ、`missing`はMaya未インストールです。スキップは未確認として結果に残ります。
終了コードは成功0、失敗・異常1、未インストールだけで未完了なら2です。
`--timeout 1200`で各版の制限時間を変更できます（既定600秒）。

## テストを追加する

1. 単体は`unit/`、本体機能同士の結合は`integration/`へ`test_名前.py`を追加します。
2. `unittest.TestCase`または`unittest.FunctionTestCase`で期待値を判定します。
3. 末尾に`if __name__ == "__main__": unittest.main()`などの実行入口を置きます。
4. `--tests ファイル名`で確認してから、同じスイート全体を実行します。

通常Pythonで動くものは`unit/test_static_名前.py`とします。`runStatic.py`が検出し、
Maya版ランナーはそのファイルを除外します。各テストは作ったノード・設定を後片付けしてください。
他パッケージとの連携はmlib本体に混ぜず、利用側のリポジトリへ置きます。

## コードの書式を検査する

この`__tests__`フォルダから実行します。Mayaは不要です。

```powershell
# 本体全体、または指定ファイルを検査する
python .\checks\check_mlib_layout.py --check
python .\checks\check_mlib_layout.py --check ..\nodes\node.py
```

違反があればファイル・行番号・検査コード・内容を表示し、終了コード1を返します。
`L030`は代入・比較演算子、`L031`はカンマ・括弧、`L032`は引数の`=`、
`L033`は行末コメントの空白、`L034`は名前へ直接代入するlambdaです。
文字列内部とf-stringの埋込み式は対象外です。引数として渡すlambdaは許可します。
Sphinxの説明コメント`#:`は維持し、コードとの間の空白だけを検査します。

既存の`--fix`が直すのはimport順・クラス内の順・空行です。
上記5項目は検査のみで自動修正しません。`runStatic.py`からも同じ検査を実行します。

`L040`は公開入口の冒頭にある入力検証のassert、`L043`は判定できるテキストファイルAPIの
文字コード未指定を報告します。`L041`（単純な列挙）・`L042`（pathlibへの置換）は確認候補の情報表示です。
これらはコードの意図を完全には判別しません。テスト・内部整合性のassert、添字更新、
バイナリ、MayaのDAGパス等は一律に変更しません。

入力assertを確認した後、適切な例外型と報告された行番号を指定すると、その行だけを修正できます。
次は`node.py`の12行目がL040として報告された場合の例です。実際の対象と行番号へ置き換えてください。

```powershell
python .\checks\check_mlib_layout.py --fix-asserts TypeError ..\nodes\node.py --line 12
python .\checks\check_mlib_layout.py --check ..\nodes\node.py
```

値の範囲等の検証には`ValueError`も選べます。`--line`は繰り返し指定できます。
例外型は推測せず、選択されたassertの条件とメッセージをraiseへ移します。
コメントを含む場合や同じ行に他の文がある場合は、保存前に拒否します。
修正後は例外型が変わるため、呼出し側と該当APIのテストも確認してください。
`enumerate`・`pathlib`への置換と文字コードの選択は、内容を確認して手動で行います。

## 文書の検査

`_docs`のビルド後、同じ文書用Pythonで実行します。

```powershell
..\_docs\.venv\Scripts\python.exe .\checks\check_mlib_docs.py --check-directory ..\_docs\_build\html
..\_docs\.venv\Scripts\python.exe .\checks\check_mlib_doc_getter_names.py ..\_docs\_build\html
```

ブラウザ自動確認を使う場合だけ`checks/browser-requirements.txt`からPlaywrightを入れ、
`python -m playwright install chromium`を実行します。静的検査やMayaテストには不要です。
