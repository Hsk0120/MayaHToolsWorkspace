# 操作確認と動画の範囲

## 再実行

`tools/qpe_audit_runner.py` はスイートを独立プロセスで順番に実行します。結果・画像・ログは指定した出力先に保存します。同じ出力先は再利用せず、新しい実行IDを使ってください。

```powershell
python tools/test_qpe_organizer.py
python tools/test_qpe_advanced.py
python tools/test_qpe_productivity.py
python tools/qpe_audit_runner.py .maya-output/verification/qpe-review-standalone --python <PySide6のあるpython.exe>
python tools/qpe_audit_runner.py .maya-output/verification/qpe-review-maya2027 --maya 2027
python tools/qpe_audit_runner.py .maya-output/verification/qpe-review-maya2022 --maya 2022
python tools/qpe_dock_restore_test.py --version 2027
```

`qpe_ui_directory.py` はP0スイートから呼ぶ補助テスト、`qpe_ui_icons.py` はアイコン生成ツールです。これらを単独の受け入れテストとして数えません。旧C++比較用の`qpe_maya_suite.py`も現在のPython版全機能テストではありません。

`tools/qpe_record_chapters.py <新しい出力先>` は専用Maya 2027を起動し、専用ファイルを使って章別の操作動画を作成します。実際のQtウィジェットを自動操作し、ダイアログの実描画を合成します。デスクトップ全体・物理マウスの録画ではありません。保存先を選ぶOSダイアログは専用パスに固定し、処理本体と結果を検証します。操作IDと実時間の索引は各章の`operations.json`、旧録画スクリプトでは`timeline.json`／`frames.json`、結果は`result.json`です。

| 章 | 収録する操作 |
| --- | --- |
| navigation | 階層移動、履歴、パス、左右サイドバー、フィルター、ソート、お気に入り、タブ、文字/UIサイズ、第2ペイン、探索起点 |
| files | 作成、改名、コピー、切り取り、競合判断、Undo/Redo、複製、ごみ箱、一括改名、集計、ハッシュ、重複、履歴整理、フォルダー結合 |
| organize | タグ・評価・コレクション、検索保存、ラベル改名、ZIP作成・閲覧・展開、フォルダー比較・同期 |
| settings | 作業セット、固定タブ、設定の移植、待機転送の復元・破棄、失敗した転送の再試行、実行中の中止 |
| maya | Save As、Save、Export、Openのキャンセル・ダブルクリック、Import、Reference、名前空間、設定プリセット、サイドカー、ドッキング |
| advanced | サムネイル、メタデータ、グループ、タグ絞込、子階層込み表示、複合検索、キー設定、コマンド検索 |
| productivity | パス補完、選択時の情報欄、場所ロック、本文検索、ZIP内部、転送の順序・一時停止・再開、取得状態、診断 |
| finder | 右クリック対象と選択、縦横スクロール、列幅変更、改名・Open要求、複数Import/Referenceとキャンセル |

標準では8章を撮影します。`--chapters finder`のように対象章を指定できます。保存転送の動画は前回待機状態の記録を同一プロセス内で用意するため、強制終了後の復旧検証とは区別します。

## 修正時に追加した回帰条件

- A/B/探索起点を40回素早く切り替えても、Qtの遅延選択解除でカラムが空白にならない。
- 復元対象の先行タブが消えていても、保存したアクティブタブの場所を保持する。
- 固定タブは閉じるボタンも無効表示。前後に空白を入れた作業セット名で上書き確認を回避できない。
- ジョブ一覧の自動更新で選択対象が変わらず、待機停止の表示が実際の状態に一致する。
- 設定取込で表示倍率を即時反映し、予約キーと壊れたパス値は保存前に拒否する。
- 拡張子・名前フィルターで一覧が空になっても、解除・並べ替え後はファイル名列へ残り幅を配分する。
- 関連付けアプリの起動が拒否された場合は理由を表示し、Recentへ追加しない。
- Maya終了時は配置を先に保存し、Qtが有効なうちに監視・遅延更新を停止する。終了コードに加えクラッシュダンプを確認する。

## 実機で確認する項目

以下は自動イベントや模擬入力だけで合格としません。作業シーンや本番ファイルを避け、検証用コピーを使用してください。

| 操作 | 手順 | 合格条件 |
|---|---|---|
| 物理ホイール | 60件以上ある列の上下端を越えて回す。横ホイール／トラックパッドでも確認 | 別列と背後のMayaビューが動かない。横に戻した位置が読込完了で変わらない |
| 日本語IME | パス・フィルター・改名・名前空間の欄で変換中に矢印、Space、Enter、Escape、Ctrl+C/Vを使う | 変換・編集が優先され、ファイルを開いたり別階層へ移動したりしない |
| 非アクティブ時のクリック | 別アプリを前面にしてからQPEの項目をクリック。Mayaの別ビューでもキーを押す | ホストが配送したクリックのみ一度処理。QPE外のキーでQPEの操作が発火しない |
| 外部ドラッグ | Windows Explorer→QPE、QPE→Explorer、タブ、カラム、第2ペイン、Favoritesへドラッグ。Shift付きも実施 | 表示した行先へコピー／移動。Favoritesはリンク追加。外部アプリでの操作はQPEのUndo対象と混同しない |
| 混在DPI | 通常DPIと4K画面の間でフローティングQPEを移す。ドックでも確認 | 文字、アイコン、行高、境界、ボタンが欠けず、倍率が累積しない |
| ネットワーク中断 | 専用共有フォルダーへのコピー・検索中に接続を切り、中止・再接続を行う | 応答待ちを含め結果を記録。成功扱いにせず、原本と確認可能な履歴を残す |
| OneDrive等 | ローカル保持、オンラインのみ、同期中、プロバイダーの同期エラーを比較 | 自動プレビューでオンラインファイルを取得しない。取得状態とプロバイダーの同期エラーを混同しない |
| Everything | 導入済みのEverythingとes.exeを指定して検索し、実際の場所へ移動 | 結果のパスと条件が一致。未導入時はフォルダースキャンが使える |
| File Locksmith | 対応CLIを設定し、別アプリで開いた検証ファイルを診断 | 使用中プロセスの結果・未対応を区別。プロセスを終了しない |
| OS連携 | Windows Properties、Open with、外部ビューアーを検証ファイルで開く | 正しいファイルを渡す。キャンセルしても選択・原本が変わらない |
| Maya標準オプション | QPEのMaya optionsからOpen／Import／Reference／Save As／Export／Set Projectを開き、キャンセル | 対応するMaya標準画面が開く。通常作業環境へ不用意に設定を保存しない |
| 起動中転送と終了 | 検証コピーの途中でQPEを閉じる。待機ジョブを残してMayaを通常終了し再起動 | 実行中のQPE閉鎖は拒否。保存ジョブは明示再開するまで書き込まない |

P0のAT14・AT19・AT20は自動部分と実入力部分を分け、AT21はホストの実入力で確認します。クラッシュダンプが生成された場合は、終了コードが0でも終了検証の成功とは扱いません。

## ファイルを開く仕様の検証

`tools/qpe_ui_open.py`はOpen・ダブルクリック処理・Spaceの対象、選択だけでは起動しないこと、起動拒否・例外時のRecent保護を検証します。OS起動は捕捉テストと実機確認を区別します。隔離Mayaでは.ma／.mbを実際に保存・再読込し、外部起動が行われないことを確認します。画像・PDF・動画はOSの関連付けアプリを使用します。

## モダンUIの検証

`tools/qpe_ui_modern.py <出力先>` はViewのEscape閉鎖、条件の個別解除、文字と独立した行間、100/150/200%のUI倍率、狭い幅のフィルター表示、Maya読込設定の保持を確認します。これはUI倍率の検証であり、物理モニター間の混在DPI・実IME・物理ホイールの確認とは区別します。既存のtabs・sidebars・theme・inspectorも回帰対象です。

`QPE_RECORD_MODERN=1` と `QPE_FFMPEG` にFFmpeg実行ファイルを指定すると、この検証で実際のQtウィジェットを録画します。専用データだけを使い、Import設定の編集で実際の読込は実行しません。Mayaでは既存の隔離GUI実行器から本スクリプトのmainを呼び出します。デスクトップ全体や物理マウスの動画ではありません。

録画ヘルパーの変換処理は標準入力を継承せず60秒でタイムアウトします。2026-10-13のMaya 2027では子FFmpegの停止が発生したため、保存済みの `frames.txt` をMaya外のFFmpegで変換し、動画のデコードと実フレームを確認しました。原因は未特定です。録画付き実行の失敗をUIテストの合格に置き換えず、UI検証は録画なしで別途実行します。

## 大量項目の性能回帰

`tools/qpe_ui_performance.py <出力先>` は専用の200フォルダー・1,000画像を作り、最終件数と通知集約、一覧からサムネイルへのアイコン共有を検証します。アイコンのテストではOS取得だけを捕捉し、パスごとの分離、LRUの破棄順、サイズ変更による失効も確認します。Mayaでは既存の隔離GUI実行器で同じテストを実行できます。

`tools/qpe_ui_scale.py <出力先>` は32×32のPNG 1,000枚について、一覧とサムネイル切替の経過時間、イベント配送の最大間隔を記録します。GUI検証を並行起動せず、変更前後を新しい出力先で各3回実行し中央値を比較してください。録画・プロファイラーの負荷を含む結果とは分けます。ネットワーク共有・巨大画像・コールドディスクの性能保証ではありません。

2026-10-13のWindows/PySide6計測では、一覧表示の中央値は4.109→2.969秒、サムネイル切替は2.188→0.703秒でした。イベント間隔の記録は計測終了境界をまたぐ停止を含まないため、最大停止時間の改善を示す値としては扱いません。生データはローカルの `.maya-output/verification/qpe-performance/comparison.json` に保存しています。

## 保存・Maya標準履歴の検証

`tools/qpe_ui_scene.py` はDelete／Properties、Maya限定の上部Save Scene Asボタン、既定の.mbを確認します。隔離Mayaでは実際に.mbと.maを別名保存・再読込し、元ファイル保護、標準RecentFilesList／RecentFilesTypeListの一致、重複除去、キャンセル・失敗時の履歴保持を確認します。`QPE_RECORD_SCENE=1` で実画面のフレームと `frames.txt` を保存し、Maya外で動画へ変換できます。ユーザーの通常Maya設定は使用しません。

## 2026-10-13 用語統一

Tab set、File operation history、Extension、Extended details等の用語を統一。表示名Keep bothと内部action renameを分離し、競合ファイルを実際にコピーして元と別名コピーの両方を保持することを確認しました。保存キー・コマンドIDは維持しています。Windowsはadvanced/productivity/inspector/ux/tabs/scene、Maya2027はadvanced/ux/inspector/tabs、Maya2022はadvanced/inspectorが合格。配布exeを再ビルドし起動検証も合格しました。初回UXの旧メニュー名と、Maya2027 advancedの検証ウィンドウのアクティブ状態をテスト側で修正して再検証しています。結果は `.maya-output/verification/qpe-terms/verified-results.json`。今回は新規動画・実IME・混在DPIの検証は行っていません。

## 2026-10-13 New Scene

上部のNew SceneはMayaだけに表示。専用Maya2022/2027で実ボタンから新規作成し、未保存時のSave/Discard/Cancel、保存先取消相当、保存失敗、既存ファイル保護、変更なし時の確認省略を検証しました。Saveは実際に保存後のファイルを開き直し値を確認。保存先取消と失敗はテストで再現したもので、OS保存ダイアログの手動操作ではありません。Windows単体の非表示も合格。証跡は `.maya-output/verification/qpe-new-scene/verified-results.json`、画像は各Mayaの `scene/05.png`。新規録画は行っていません。

## 2026-10-20 ドライブとシーンフォルダー追従

Windows単体のinspector、Maya2022/2027のscene/inspectorでドライブ一覧とアイコン、実ホストのシーン読込後の移動、Save/New/Cancelで場所を維持することを検証。初回scriptJob遅延をkAfterOpenへ変更し、Qt5のドライブアイコン取得時のスタイル寿命問題をQFileIconProviderで解消して再検証しました。配布exeの再ビルド・起動も合格。証跡 `.maya-output/verification/qpe-drives/verified-results.json`。物理ドライブ抜差し・切断ネットワーク・iPad・新規録画は未実施。
