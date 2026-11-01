# QuickPathExplorer

WindowsとMayaで共通の操作を使える、C++／Qtのファイルブラウザーです。上段のフォルダーカラムで階層をたどり、下段でファイルを選択します。左にFavorites・Recent・Drives、右にファイル情報とMaya操作のサイドバーを備えています。

Windows版は静的Qtを含む`QuickPathExplorer.exe`、Maya版は年別の`quickPathExplorer.mll`です。製品のUI・ファイル操作・設定・Maya連携はC++で実装し、実行用のPython/PySideや`_internal`は不要です。Windows版のQtをMayaへ持ち込まず、Maya版はホスト付属Qtを使います。

## 起動

Windowsでは直下の`QuickPathExplorer.exe`を起動します。フォルダーを引数に渡すと、その場所を開きます。

```powershell
.\QuickPathExplorer.exe 'D:/Projects'
```

Mayaでは`release/plug-ins/windows/<Maya年>/quickPathExplorer.mll`をPlug-in Managerでロードし、**Window → QuickPathExplorer**またはMELの`quickPathExplorer;`で開きます。初回のSecurity確認は利用者が判断します。対応する年のmllを使用してください。

`QuickPathExplorer.mod`は年別のプラグインパスと`scripts`のPythonパスを登録します。このワークスペースでは`maya/modules/QuickPathExplorer.mod`を使用します。単独配置ではQPEフォルダーを`MAYA_MODULE_PATH`へ追加し、同梱の`QuickPathExplorer.mod`を読み込ませます。

Maya Code Editorと同様に、`scripts/userSetup.py`がGUI起動後に未ロードのプラグインをロードします。**Window → QuickPathExplorer**へのアイコン付き登録と画面復元は既存のC++プラグインが行い、Python側にはUI処理を置きません。バッチ起動ではロードせず、Plug-in ManagerのAuto loadとの二重ロードも避けます。初回のSecurity確認は通常どおり表示され、信頼設定を変更しません。前回開いていたQPEは保存済みのドック／浮動状態を使って表示し、明示的に閉じた場合は閉じた状態を維持します。

自動起動を使用しない場合は`.mod`をモジュール検索先から外し、年別mllをPlug-in Managerから明示ロードできます。アプリ本体はC++のままで、`userSetup.py`はMaya同梱Pythonを使う起動用ファイルです。

更新時はWindows版QPEを終了します。Maya版は処理を完了してからアンロードするかMayaを終了します。ファイル操作やワーカーが残る間はアンロードを拒否します。他ツールのUIやQt設定は変更しません。

## 基本操作

- 上段のフォルダーをクリックして子階層へ進みます。戻る／進む、Alt+Left／Right、Alt+Up、パス入力も利用できます。
- タブの追加（Ctrl+T）、順方向の切替（Ctrl+Tab）、逆方向の切替（Ctrl+Shift+Tab）、閉じる（Ctrl+W）、閉じたタブの再表示（Ctrl+Shift+T）に対応します。固定、場所ロック、名前付きTab setも利用できます。
- カラムの幅はDisplay Settingsで調整します。名前に合わせる設定、ウィンドウ幅へ寄せる設定、境界の手動リサイズを用意しています。
- Tools → View → Browser layoutでColumns first／Balanced／Files firstを選びます。境界をドラッグするとCustomになり、タブごとに比率を保存します。
- 左右のサイドバーは上部ボタンで表示／非表示を切り替えます。現在のドライブを選択表示し、ドライブ名・レター・使用量・空き容量を表示します。
- 文字サイズは上部のAa（Display Settings）から変更します。10px相当のVery Smallを含みます。入力欄以外ではCtrl+Plus／Minus／0でも拡大・縮小・標準化できます。MayaのDPI倍率を反映します。
- Windowsの既定テーマはOSに追従し、明示的なライト／ダークにも切り替えられます。Mayaはダークを既定とし、ホスト全体のパレットを変更しません。
- ファイル一覧のViewからDetails／Thumbnails／Extended details、子階層を含む表示、グループ、タグ、列を変更します。名前・拡張子等の絞り込みは条件ラベルの×でも解除できます。

ファイルをダブルクリックすると開きます。Windows版は関連付けアプリを起動します。Maya版ではma／mb／fbxを現在のMayaで扱い、他のファイルは関連付けアプリへ渡します。EnterまたはF2で改名し、文字編集やIME変換中は編集欄の操作を優先します。

右クリックの対象はメニューを開いた時点で固定します。選択外を右クリックしても既存選択・プレビューを変更しません。Copy／Cut／Paste、Duplicate、Rename、New Folder／New Text File、Delete、Properties、Open with等を利用できます。

## Mayaの操作

上部のNew Scene／Save Asボタンと、右サイドバーの操作選択（Open／Import／Reference／Save）を使用します。未保存シーンの確認を通し、キャンセル時は現在のシーンを保持します。読込処理そのものが失敗した場合のシーン状態はMayaの結果に従います。

- Save Asは保存名・場所・形式を指定します。新規設定の既定はMaya Binary（mb）です。Save Sceneは既存形式を維持します。
- Import／Referenceは名前空間、ルート／ファイル名／明示名、既存名前空間等を指定できます。追加項目はAdvanced optionsにまとめています。
- FBXは新規シーンとして開く場合と既存シーンのアニメーション更新を切り替えられます。右ペインで方式を選び、Maya標準オプション画面も開けます。
- QPEからのシーンOpen／Save成功時にMaya標準Recent Filesへ追加します。Import／ReferenceはシーンのRecent Filesへ追加しません。
- シーンOpenに追従してそのフォルダーへ移動します。場所ロック中は新しいタブを使います。
- シーン情報・サムネイルのsidecarは明示操作で保存します。

QPEのファイルUndo／RedoはMayaシーンのUndoとは別です。現在のMayaシーンへのImport等では標準MayaコマンドのUndo仕様を維持します。

## ファイル整理・検索

コピー／移動／ごみ箱／改名／新規作成、衝突確認、フォルダー結合、永続的なUndo／Redo、転送キュー・停止・再開、条件検索と保存検索、本文検索、タグ・評価・コレクション、一括改名、ZIP作成・閲覧・選択展開、重複検出、ハッシュ、フォルダー比較、2番目のファイル一覧を備えています。

詳細と制限は[ファイル整理ガイド](ORGANIZER_GUIDE.md)を参照してください。Find command（Ctrl+Shift+P）から操作名でも探せます。

削除はWindowsのごみ箱への移動です。OSが処理中の間は完了扱いにしません。完了後は親・子カラムと別タブの一覧を更新します。外部アプリで変更された復元先やUndoバックアップを検出した場合は復元を停止します。

転送再開は項目単位です。途中のファイルは先頭からコピーし直します。実ネットワーク切断や停電を含む完全なトランザクション保証はありません。ZIPは20GiB／10万項目を上限とし、パス逸脱・リンク・重複名を拒否します。

## 表示と非同期処理

フォルダー列挙、Shellアイコン、画像・メディア情報はGUI処理から分離します。先頭100件から段階表示し、最終結果でソートを確定します。要求先と世代を照合し、古い結果・エラーが現在表示を上書きしないようにします。タブ・再訪時には保持した一覧を使いつつ、変更を再確認します。

サムネイル用のFFmpegはLGPL構成でexe／mllへ格納し、必要時にユーザーキャッシュへ展開します。動画を開く操作は関連付けアプリへ渡します。ファイルシステムのI/O待ち自体をなくすものではありません。

## ビルド・配布

[BUILDING.md](BUILDING.md)にVisual Studio構成、CMake、Windows／Mayaのビルド、対応ソース・ライセンスと改変Qtへの再リンク手順をまとめています。

- `build_windows.cmd`: コンパイル・回帰テスト後に直下のexeを更新。
- `build_maya.cmd --versions 2022 2027`: 指定年のmllを更新。
- `generate_projects.cmd`: Visual Studioプロジェクトを生成。
- `check_environment.cmd`: 開発環境を確認。

QPE独自コードはMIT、Qt・FFmpeg等にはそれぞれのライセンスが適用されます。配布時は対応ソース・ライセンス・再リンク資料も提供してください。ZIP化やリポジトリの新規公開はビルドに含めません。

検証手順と未確認範囲は[VERIFICATION.md](VERIFICATION.md)を参照してください。Qt自動操作、OS実入力、実再起動は区別します。実IME、クラウドプロバイダー、ネットワーク断、混在DPIなど、全環境の全操作を保証するものではありません。
