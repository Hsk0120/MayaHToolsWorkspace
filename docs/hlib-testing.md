# Mayaバージョン別のhlibテスト

実パネル・色・選択表示の確認は[GUI検証](hlib-gui-testing.md)を参照してください。

Windows上でMaya 2022～2027を個別・一括テストする入口です。
各Mayaに付属するmayapyを別プロセスで起動します。Maya GUIの起動は不要です。
Maya本体と実行に必要なライセンス環境は各バージョンを別途用意してください。
このランナーはMayaのインストールや更新を行いません。

## 実行方法

リポジトリ直下のPowerShellから実行します。

```powershell
# インストール状況の確認だけ
.\tools\run_hlib_tests.bat --list

# 2022・2023・2024・2025・2026・2027を順番に実行
.\tools\run_hlib_tests.bat

# バージョンを指定（複数指定可）
.\tools\run_hlib_tests.bat --versions 2022 2024

# 未インストール以外がすべて成功なら終了コード0
.\tools\run_hlib_tests.bat --allow-missing
```

バッチ自体の制御には、検出した最新のmayapyを使用します。
実テストにはそれぞれのバージョンのmayapyを使用し、起動後にMayaの実バージョンを照合します。
2023も対象です。未インストールの場合は`missing`になり、導入後は同じコマンドで実行できます。

標準配置は`C:\Program Files\Autodesk\Maya<年>\bin\mayapy.exe`です。
別ドライブなどにある場合は以下のように指定します。

```powershell
$env:MAYA_TEST_LOCATION_2023 = 'D:\Autodesk\Maya2023'
$env:HLIB_TEST_PYTHON = 'C:\path\to\python.exe' # 制御用Python 3.7以上、任意
.\tools\run_hlib_tests.bat --versions 2023

# 全バージョン共通の親ディレクトリを変更
.\tools\run_hlib_tests.bat --install-root D:\Autodesk
```

Pythonからも`python tools/run_hlib_tests.py --versions 2027`として実行できます。

## 実行範囲と分離

- 既存の`maya/inhouse/hlib/__tests__/run_all_tests.py`を再利用します。
- バージョンごとに専用の`MAYA_APP_DIR`と一時フォルダーを作ります。ユーザーのMaya設定や起動中のGUIシーンは変更しません。
- 継承したMaya/Python/Qt環境変数を除いて再構築し、内製hlibだけをPYTHONPATHに追加します。ワークスペース起動バッチや外部submoduleのセットアップは呼びません。
- テストの英語ラベル期待値を揃えるため、UI言語を`en_US`に固定します。
- 1バージョンが失敗しても後続を実行します。既定600秒でタイムアウトし、このランナーが起動した対象プロセスと子プロセスを停止します。`--timeout 1200`で変更できます。

以下のファイルは自動実行しません。除外内容は結果JSONにも記録します。

| ファイル | 理由 |
| --- | --- |
| `test_scene_ui.py` | 実GUIのパネルが必要（専用GUIランナーの`unit`スイートで実行） |
| `test_command_discovery.py` | 既存一括ランナーの除外対象。別プロセス専用テスト |
| `test_maya_standalone.py` | 既存の手動疎通用スクリプト |
| `test_slack_postMessage.py` | 実際に外部へメッセージを送信するため |

個々のテスト内でもGUI専用ケースなどがskipされることがあります。詳細ログの`skipped`を確認してください。
Maya 2022では`playbackOptions`自体がUndo履歴を作らないため、タイムライン範囲変更(`TimeSlider.setPlaybackRange`/
`setAnimationRange`)はこのバージョンに限りUndo/Redoできません(Mayaネイティブの制限で、hlibは独自プラグインでは補いません)。
GUI専用のケースと`test_scene_ui.py`は、Mayaを起動していなくても`tools/run_hlib_gui_versions.py --suite unit`で使い捨てのGUIを起動して実行できます（[GUI検証](hlib-gui-testing.md)）。一括テストはシーンを新規作成するテストを含むため、起動中のGUIへ送る場合は未保存の作業がない状態で実行してください。

## 結果

`.maya-output/version-tests/<日時>/`に次を保存します（Git対象外）。

- `summary.txt`：バージョン別の状態・失敗ファイル一覧
- `summary.json`：機械処理用の全結果。各バージョン終了時にも更新
- `<年>/result.json`：実際のMaya/API/Pythonバージョン、状態、除外ファイル、ログパス
- `<年>/<日時>.log`：既存ランナーの詳細テスト結果・トレースバック
- `<年>/console.log`：初期化・終了時を含むプロセス出力
- `<年>/maya_app/`・`<年>/temp/`：その実行専用の設定・一時データ

`passed`は対象テストファイルに失敗がない状態です。`failed`はテスト失敗、`error`は初期化・起動・終了などのエラー、`timeout`は時間切れ、`missing`は未インストールです。
未インストールを成功扱いにしたり、別バージョンへ代替して実行したりはしません。

終了コードは、成功`0`、テスト失敗・実行エラー・タイムアウト`1`、未インストールのみで未完了`2`です。
`--allow-missing`は未インストールによる終了コードだけを抑制し、結果の`missing`表記は残します。

設定・一時ファイルは診断用に保持します。実行終了後、不要な日時フォルダーは手動で削除できます。

## レイアウト規則の検査(Maya不要)

`docs/hlib-api-design.md` の「ファイル・クラスのレイアウト規則」は、`tools/check_hlib_layout.py` で検査します。
`ast`と`tokenize`だけを使うため、通常のPythonで実行でき、hlibやMayaをimportしません。

```powershell
# 規則違反を一覧表示(違反があれば終了コード1)。既定の対象はhlib・hlib_bifrost・hlib_posedriverconnect
python tools/check_hlib_layout.py --check

# 対象を絞る
python tools/check_hlib_layout.py --check maya/inhouse/hlib/nodes

# import群の並び替え・クラス内メンバーの並び替え・空行の正規化を書き込む
python tools/check_hlib_layout.py --fix maya/inhouse/hlib/nodes

# クラスのメンバー構成(分類・行範囲)を表示する
python tools/check_hlib_layout.py --outline maya/inhouse/hlib/nodes/node.py

# 並び替え前に構造を保存し、並び替え後に関数本体・import束縛・モジュール文が同一か比較する
python tools/check_hlib_layout.py --snapshot .maya-output/layout-baseline.json
python tools/check_hlib_layout.py --compare .maya-output/layout-baseline.json
```

`--fix`はメンバーの本文・docstring・デコレータを変更せず、付随するコメントと一緒に移動します。
`--check`と同じく、クラス内や関数内に定義した内側のクラスも並び替えの対象です(外側から順に処理します)。
メソッドを参照するクラス属性や同名メンバーのあるクラスは並び替えず、`--check`で「スキップ」として表示します。
実行後は`--compare`とMayaでのテストで等価性を確認してください。

`--compare`は定義の順序や空行を無視し、各関数・クラスのAST(docstring・デコレータ含む)と
モジュールレベルのimport束縛・その他の文・コメントを比較します。差分があれば一覧表示して終了コード1になります。
順序を無視するため、並べ替えで参照より後に定義が移った場合などの順序依存の変化は検出しません。そうした構成は`--fix`が
「スキップ」として並べ替えない設計ですが、手で並べ替えた場合はMayaでのテストで確認してください。
import文の間に実行文がある`__init__.py`は、`--check`のimport順検査をスキップして表示します。
