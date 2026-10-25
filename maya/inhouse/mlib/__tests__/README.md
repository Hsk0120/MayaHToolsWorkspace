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

## 文書の検査

`_docs`のビルド後、同じ文書用Pythonで実行します。

```powershell
..\_docs\.venv\Scripts\python.exe .\checks\check_mlib_docs.py --check-directory ..\_docs\_build\html
..\_docs\.venv\Scripts\python.exe .\checks\check_mlib_doc_getter_names.py ..\_docs\_build\html
```

ブラウザ自動確認を使う場合だけ`checks/browser-requirements.txt`からPlaywrightを入れ、
`python -m playwright install chromium`を実行します。静的検査やMayaテストには不要です。
