# ファイル整理・検索・プレビュー

上段カラムと下段ファイル一覧を維持し、追加機能はパス欄右端の **Tools** と右クリックへまとめています。Mayaのバージョン番号によるファイル整理・次番号保存は今回の対象外です。

Toolsは **Search / organize、View、Transfers / history、Tabs / workspaces、Maya、Settings / diagnostics** に分類しています。以下でToolsから直接選ぶと記載した操作も、現在は該当する分類内にあります。**Find command…（Ctrl+Shift+P）** なら操作名で検索できます。選択数や保存状態に合わない操作は無効表示になります。

## コピー・移動・取り消し

ファイル／フォルダーの右クリックにCopy、Cut、Duplicate、Move to Recycle Bin、Paste hereを追加しています。一覧にフォーカスがある場合はCtrl+C／X／V、Deleteが使えます。入力欄の編集中は通常の文字編集が優先されます。

同名の行先がある場合は、Keep both（別名）、Skip existing、Replace（Undo用に元を退避）を選択します。フォルダーのReplaceは結合ではなく置換です。コピーではMerge foldersも選べます。バックグラウンドで処理し、完了・スキップ・失敗・中止を別に表示します。失敗の詳細はコピー可能な結果ウィンドウに出ます。中止は現在のコピー中またはファイル境界で反映します。OSのブロック中のI/Oを即座に中断する保証はありません。

Undo file operation／一覧上のCtrl+Zは、QPEのファイル操作履歴を戻します。MayaシーンのUndoには接続しません。コピー、移動、複製、ごみ箱、改名、新規作成、ZIP作成／展開を対象とします。再起動後も履歴を保持し、対象またはバックアップが外部で変更されていれば停止します。ごみ箱からのUndoはQPEのバックアップを使うため、Windowsのごみ箱には元の項目が残る場合があります。外部アプリで実行したファイル操作はQPEのUndo対象外です。

Undo用データは設定ファイルの隣の`undo`へ保存します。移動時の原本は元のフォルダーに`.qpe-undo-…`という名前で退避します。**履歴を保持する間はディスク容量を使います。** 不要になったらTools → Discard Undo historyで確認後に解放できます。外部で変更された退避物は自動削除しません。Undo中のOSエラーでは途中まで復元される場合があり、残った履歴とバックアップを保持します。停電・強制終了を含む完全なトランザクション保証はありません。

ドライブのルート、リンク／ジャンクション、QPEのUndo保存先への操作は拒否します。ネットワークのごみ箱対応はOS側にも依存します。

## ドラッグ操作と2ペイン

- Explorerからファイル一覧、フォルダーカラム、タブへドロップするとコピーします。Shiftを押したドロップは移動です。
- Favorites側へドロップするとお気に入り登録になります。
- QPEからExplorerへファイルURLを渡せます。外部アプリが実施する操作の取り消しは、そのアプリ側で行います。
- Tools → Second file paneで、独立した場所を表示する2番目の一覧を開きます。パス入力、Parent folder、フォルダーダブルクリックで移動できます。右クリックのPaste hereとドロップは第2ペインの場所を使用します。

## 検索と保存検索

Tools → Search subfolders、または一覧上のCtrl+Fで検索画面を開きます。Scope folderに検索範囲、Nameに部分名またはワイルドカード、File typesに`*.ma;*.mb`などを指定します。Modified withinは直近の日数、0は日付制限なしです。Stopで中止し、条件変更後の古い結果は表示しません。読めない場所は検索結果と分けて報告します。

検索結果のダブルクリックは元の場所へ移動して選択します。ファイル自体を開くには右クリックOpenを使います。Save searchで条件を保存するとFavoritesとTools → Saved searchesから再利用できます。Favorites内の右クリックで保存検索を削除できます。

任意のEverything連携はTools → Configure Everything CLIで`es.exe`を指定し、検索画面のSearch usingを切り替えます。Everything本体を起動しておく必要があります。Everythingモードは専用の検索式を使うため、File typesとModified withinは空／0にして検索式に条件を書きます。未導入でもFolder scanは使えます。外部CLIのAPI仕様は[公式資料](https://www.voidtools.com/support/everything/command_line_interface/)に準拠します。

## タブ・ラベル

タブの場所・履歴・選択・検索文字・表示位置をMaya／Windows単体で別々に保存し、明示パスなしの起動時に復元します。使えなくなったパスは飛ばし、ステータスに表示します。Tools → Reopen closed tab、Save tab set、Load tab setで閉じたタブや案件ごとのセットを扱えます。一覧上でCtrl+T、Ctrl+W、Ctrl+Tab、Ctrl+Shift+Tが使えます。

右クリックのTags / rating / collectionでタグ、0〜5の評価、コレクションを付けます。Tools → Browse tags / collectionsでタグ名・コレクション名、または`rating:3`のような最低評価で一覧化できます。ファイルは移動せず、ローカルユーザーのQPE設定に保存します。Finderタグとの相互変換や他PCへの自動同期はありません。QPEでの改名・移動には追従しますが、外部アプリでの移動追跡は行いません。

## 一括リネーム・ZIP・比較

- Batch Renameは置換、正規表現、接頭辞／接尾辞、001形式の連番に対応します。拡張子を保ち、Before／Afterで確認してからApplyします。衝突があると実行できません。相互入替えを伴う名前変更は未対応です。
- Create ZIPとExtract ZIPは既存出力を上書きしません。展開は新規フォルダーへ行い、パス逸脱・リンク・重複名を拒否します。展開制限は20GiB／10万項目です。ZIP以外の形式は外部アプリを利用してください。
- SHA-256は内容のハッシュを表示します。Find duplicate filesは同一内容の組を列挙し、勝手に削除しません。
- Compare / synchronize foldersは相対パスと内容を比較します。差分確認後に元→先へコピーする一方向同期です。先にだけ存在するファイルは残します。同期したファイルごとにUndo履歴を作ります。双方向同期や空フォルダーだけの同期は対象外です。
- Show hidden filesでドット名／Windows hidden属性を含むカラムと主一覧を再列挙します。

## プレビューとMaya情報

動画・EXR／HDRのサムネイルはFFmpegを使用します。単体配布版には`imageio-ffmpeg`を同梱します。Maya環境では`QPE_FFMPEG`に実行ファイルを指定するか、利用するPython環境に`imageio-ffmpeg`を導入します。未導入時は必要な設定を画面に表示します。EXR表示は確認用で、レンダリング用の色管理とは一致しません。

Open・ダブルクリック・SpaceはOSの関連付けアプリへファイルを渡します。Maya内の.ma／.mbだけは現在のMayaへ読み込みます。Import／Referenceは明示操作です。QPE独自の文書・画像・動画ビューアーはありません。選択時の情報欄・静止サムネイルは引き続き利用できます。

Scene information / dependenciesは`.ma`の先頭8MiBの宣言からMayaバージョンや参照パスを読取ります。完全な依存グラフ解析ではありません。相対パスはプロジェクト解決が必要と明示し、UDIM等のパターンは単一ファイルの欠損と混同しません。`.mb`は直接解析せず、付随情報を使用します。

MayaのTools → Save current scene preview sidecarは、**保存済み・未変更の現在シーン**について`.qpe.json`と`.qpe.png`を隣に保存します。メタデータにはMayaバージョン、プロジェクト、リファレンス、fileノードのテクスチャを含めます。画像はmodelPanelのplayblastです。プレビュー選択によってシーンを開いたり変更したりしません。

Save read settings preset／Load read settings presetでImport／Reference設定を保存・復元できます。Existing Maya namespacesで既存ネームスペースを設定欄へ取り込めます。通常の読込設定もQPE終了時に保存します。Recentには成功した読込ファイルだけを追加します。

## Maya不要の配布

`python tools/build_qpe_standalone.py`で専用venvを作り、`.maya-output/qpe-standalone-build/dist/QuickPathExplorer/`へ生成します。**フォルダー全体**をコピーして`QuickPathExplorer.exe`を実行してください。exe単体だけでは動きません。更新はアプリを閉じて配布フォルダーを置き換えます。ユーザー設定は配布先と分離されています。インストーラー、自動更新、Windows標準Explorerの置換登録は行いません。

ソース用`launch_python.bat`は隣のexe、`QPE_PYTHON`、PySide6導入済みPython、Maya2027〜2022の順で実行環境を探します。第1引数は初期フォルダーです。

## 検証と手動確認

- `python tools/test_qpe_organizer.py`: 実ファイル、競合、中止、Undo、ZIP、検索、比較。専用一時ファイルを実際のごみ箱へ送るWindowsテストを含みます。
- `tools/qpe_ui_organizer.py <出力先>`: Qt操作、検索世代、編集欄の保護、タブ、ドロップ、リネーム。Mayaでは既存の隔離GUIランナーから実行します。作業中のMayaへ送信しないでください。
- `tools/qpe_media_smoke.py <出力先>`: FFmpegが利用可能な独立Pythonで生成動画とEXRの静止サムネイルのデコードを確認。
- 配布exeの`--smoke-test <出力先>`は専用設定で起動、PNGとJSONを保存して終了します。

実デバイス／接続に依存する確認は、専用コピーを使って次の順に行ってください。

1. Explorer→QPE、QPE→Explorer、タブ、カラム、第2ペインへファイルをドラッグ。コピー／Shift移動の行先・元の有無を確認する。
2. 日本語IME変換中にCtrl+C／X／VやEnterを操作。編集中の文字に作用し、Mayaの別ビューではQPEが操作されないことを確認する。
3. 物理ホイールでカラム上下端を越えて操作。別の列や背後のMayaビューが動かないことを確認する。
4. 共有フォルダー上の専用データで検索・コピー中に接続を切る。UIの反応、失敗表示、中止後の元データとUndoを確認する。OSのI/O待ちで遅れる時間も記録する。
5. 4Kと通常DPIの画面をまたいで移動し、列名・ボタン・メニューが読めるか確認する。
6. 利用中のEverything／外部ビューアー、Windows Properties／Open withを実行して関連付けを確認する。

これらの実入力・実ネットワーク確認を自動テストの合格で代替しません。

## 追加の表示・整理機能

下段の表示欄でDetails（従来の一覧）、Thumbnails（サムネイル）、Metadata（タグ・評価・所在・画像寸法付き）を切り替えます。サムネイルは表示範囲を最大2件ずつ読み、256件まで縮小画像を保持します。PNG等の画像、既存の動画/EXRデコーダー、Mayaの付随PNGを利用します。場所別にモード、列、幅、並び順、グループを保存します。Columnsから名前以外の列を隠せます。既存のカラム領域は維持します。

Include subfoldersは子階層のファイルを下段へまとめます。Type、Modified day、Location、Tagでグループ化でき、タグ選択欄で絞り込めます。グループ見出しはファイル操作対象になりません。Manage label namesでタグ名をまとめて変更・削除します。主一覧のDetailsへ戻ると従来の4列表示です。

検索はScope folderをセミコロン区切りで複数指定できます。Files/Folders/Both、KiB単位のサイズ範囲、除外フォルダーの名前/相対パスのワイルドカード、タグのAll/Any条件を追加しました。100件単位で途中結果を表示します。保存検索に追加条件も含めます。自動更新を選ぶと表示中に10秒間隔で再検索します。Stopは自動更新も止め、Searchで再開します。Everythingモードの追加条件はEverything自身の検索式で指定してください。

Merge foldersはコピー専用です。同名ファイルの種類・サイズ・更新日時を比較し、replace/skip/renameを個別選択できます。行先だけにある項目は残します。Undoは結合先フォルダー全体を保持するため容量を使い、その後に結合先が外部変更されていれば戻しません。結合しながらの移動には対応しません。

File jobs / retryでは実行中・待機中・完了したジョブを確認します。同じQPEウィンドウ内の新規依頼をFIFOで予約し、転送済みバイト数と速度を表示します。Pause queueは次のジョブの開始を止めます。現在のファイルの途中再開を意味しません。Cancel active、Cancel queued、Retry failed itemsで対象を分けて操作します。一般ジョブの予約はメモリ内です。コピー・移動・複製の予約は追加の永続化に対応し、下記「転送を止める・再開する」から明示的に復元します。別ウィンドウ/別Mayaとは既存のOSロックで排他し、共有の順番待ちは行いません。

File history / Redoに履歴を表示します。Undoは最新の履歴へ、Redoは最後に取り消した一操作へ適用します。新しい操作をするとRedoは失効します。任意の古い一操作だけを飛び越えて取り消す機能はありません。移動元・先の外部変更はRedoでも検査します。保持日数/容量を設定でき、Clean up expired historyから確認後に古い履歴を削除します。自動削除は行いません。容量集計には元の場所に退避した移動元も含みます。

Calculate selected / folder sizeは、選択項目または現在フォルダーを必要時だけ再帰集計し、ファイル数・フォルダー数・バイト数・ドライブ空き容量・読取エラーを表示します。親子を同時に選んでも二重集計しません。

Find command（既定Ctrl+Shift+P）はTools内のコマンドを検索します。QPE settingsでキー割当、既存の文字/UIサイズ画面、外部アプリ、隠し項目、Undo保持条件を扱えます。キーはQPE内だけで有効にし、文字編集欄を保護します。Mayaに割り当て済みの全キーを自動収集する機能はありません。

設定のExport/Importは形式名`qpe.preferences`・バージョン1のJSONです。既定では表示設定・キー・読込プリセット・保持条件だけを書出します。ローカルパスを含めるチェックでFavorites、タグ、場所別表示等も追加できます。Undoデータや実行中ジョブは含めません。異なるPCで存在しないパスを自動変換しません。

追加検証は`tools/test_qpe_advanced.py`と`tools/qpe_ui_advanced.py <出力先>`を使用します。実入力・ネットワーク・非常に大きなフォルダーの応答時間は別途実機確認が必要です。


`tools/qpe_ui_scale.py`のローカル32×32 PNG 1000枚では、列挙約4.2秒、サムネイル切替約2.2秒、切替中のイベント間隔最大約0.19秒でした。キャッシュ21枚・画像読込同時数2以下を確認しています。巨大EXRやネットワーク環境の性能保証ではありません。結果は`.maya-output/verification/qpe-advanced-scale-r2/result.json`です。

最新の検証範囲と未実施項目は[操作検証ガイド](VERIFICATION.md)を参照してください。

## 操作統一・検索・作業セット・転送回復

Details／Thumbnails／Metadataのいずれも、Enterで単一項目を改名、ダブルクリックまたはSpaceでOpenを実行します。Openは一件ずつ行います。編集欄では文字入力を優先します。関連付けは変更せず、Open with…でWindowsのアプリ選択画面を開けます。OSへ渡せなかった場合はエラーを表示し、Recentへ追加しません。OSの受付成功はアプリ内の読込完了を保証しません。

パス欄は入力途中のフォルダー名と最近のパスを非同期で候補表示します。右クリックには従来の文字編集に加えてParent folders／Recent pathsがあります。候補の選択後、Enterで移動します。環境変数を含むパスも解決します。

Tools → Save workspace／Load workspaceは既存の名前付きタブ保存（tabSets）を利用します。セット切替前の状態はRestore previous workspaceで戻せます。Delete workspaceで保存セットだけを削除できます。タブ右クリックのPin tabは閉じる操作を防ぎ、Lock locationは別フォルダーへの移動を新規タブで開きます。これらの属性も保存します。既存タブ保存があったため、新しい独立した保存形式は増やしていません。

Search subfoldersのContaining textで本文を検索できます。対象はtxt/md/py/mel/ma/json/csv/log/ini/xml/yaml等、1ファイル16MiBまでです。UTF-8、UTF-16 BOM、CP932を扱い、一致行番号と冒頭400文字を表示します。1ファイル200一致行が上限です。結果行のツールチップで複数行を確認できます。未対応形式や上限超過は件数とツールチップで報告します。バイナリのmbやPDF本文は対象外です。Everythingモードは従来どおり独自の検索式を使います。

ZIP右クリック → Browse ZIPで展開前の内部パス・サイズを表示します。複数選択してExtract selectedを押すと、指定した**新規フォルダー**へ選んだ項目だけ抽出します。フォルダー項目はその配下を含めます。抽出はUndo履歴へ登録します。既存フォルダーへの上書き、暗号化ZIP、7z等は対象外です。パス逸脱・リンク・重複パス、20GiB／10万項目超のZIPは拒否します。

### 転送を止める・再開する

File jobs / retryにPause / resume active transferとMove up／Move downを追加しました。前者はコピー・移動・複製の実行中処理をブロック境界で止めます。Pause queueは後続ジョブの開始だけを止める従来機能です。OSがI/O待ち中の場合、すぐ停止できるとは限りません。

コピー・移動・複製は設定フォルダーのjobsへ記録します。待機中の保存済み転送だけならQPEを閉じても記録を残します。実行中は中止か完了を待ってから閉じてください。再起動後はTools → Recover saved transfersで対象を確認して再開します。自動でファイル操作を再開することはありません。

- 準備済みの元ファイル／行先と、完了済み出力をハッシュ照合します。外部で変更された場合は停止します。
- 再開は項目単位です。**途中のファイルは先頭からコピーし直します。バイト位置からの再開ではありません。**
- まだ準備していない待機ジョブは、再開時点の原本を対象にします。画面にもこの違いを表示します。
- 履歴に確定済みと記録された項目は二重転送しません。確定処理中の異常終了で状態が曖昧な場合はReview requiredとし、Undo履歴・原本・行先を確認します。
- 連続した同一ジョブの完了分は一つのUndo履歴にまとめます。別操作を挟んだ再開分は別履歴になります。
- Discard recordは再開用記録を除外するだけで、原本やUndoバックアップは削除しません。
- Windowsコピーと同様のACL等を完全再現する転送エンジンではありません。ネットワーク断・停電を含めた完全なトランザクション保証もありません。

### ファイル状態と原因の確認

MetadataのAvailability列と右側情報に、ローカル／取得が必要／ローカル保持状態を表示します。Windows Cloud Files APIから取得できる場合はin sync／not in syncも表示します。not in syncを同期エラーと決めつけません。未対応プロバイダーや取得できない状態はunknownです。オンライン属性のあるファイルは、サムネイル・画像寸法・静止プレビュー・本文検索で自動取得しません。必要な素材をWindows Explorerで明示的に取得してから再表示してください。

Diagnose file usage / availabilityは属性と利用状況を確認する読取専用操作です。使用中プロセスの特定はPowerToys FileLocksmithCLI.exeをConfigure File Locksmith CLIから指定するか、PATHに置いてください。自動的なプロセス終了・権限変更はしません。標準のファイル操作エラーには、使用中・権限・空き容量・接続の確認先を追加しています。

### 追加項目の検証と手動確認

`tools/test_qpe_productivity.py`は本文検索、ZIP抽出、クラウド属性、保存転送、外部変更拒否、中断後の確定照合、停止中の中止を専用一時データで検証します。`tools/qpe_ui_productivity.py`はOpen要求、3表示のEnter、パス補完、タブ固定／ロック、検索、ZIP、キュー操作、状態表示を確認します。Mayaでは隔離GUIランナーを使用します。

実プロバイダーのクラウド同期エラー、実ネットワーク切断、物理IME、混在DPIは自動テストの合格に含めません。

1. OneDrive等の専用サンプルをオンラインのみ／ローカル保持に切り替え、Availabilityの変化と、選択だけでは取得が始まらないことを確認する。同期エラー詳細はプロバイダー画面と照合する。
2. 専用の大きいファイルを共有フォルダーへコピーし、停止・再開・中止を試す。接続を戻した後にRecover saved transfersで再開し、元ファイルと結果を照合する。途中ファイルが最初から転送されることを確認する。
3. PowerToysを導入した環境で、専用ファイルをアプリが使用している状態のDiagnoseを実行する。対象プロセスが表示され、終了されないことを確認する。
4. 日本語変換中のパス欄・改名欄とMayaの別ビューで、QPEのショートカットが割り込まないことを確認する。4K／通常DPI間では候補ポップアップやプレビューの配置を確認する。
