# WORK_LOG.md

Claude Code / ChatGPT Codex / GitHub Copilot を並行して使う際の作業状況共有ファイル。
これら3つのAIコーディングツールは互いを直接検知できないため、このファイルを介して
「今どのツールがどこを触っているか」を明示的に共有し、作業範囲の衝突を防ぐ。

## 運用ルール

- **作業開始前**: このファイルを読み、これから触る範囲が「進行中」の他ツールの行と
  重なっていないか確認する。重なる場合はユーザーに確認してから進める。
- **作業開始時**: 「進行中」の表に自分の行を追加する(ツール名・開始日時・対象範囲・内容)。
  対象範囲はディレクトリ/ファイル単位で、他ツールが読んで判断できる粒度にする。
- **作業完了時**: 該当行を「進行中」から削除し、「完了履歴」へ追記する(要約は簡潔に、
  詳細は git 履歴やコミットメッセージ側に譲ってよい)。
- **コミットの粒度は問わない**(こまめなコミットは必須にしない)。このファイルは
  コミット前の作業状況を共有するためのものなので、未コミットの変更があっても
  「進行中」に書いてある内容を正として扱う。
- 完了履歴は増え続けるため、古いものは適宜削除してよい(直近の履歴が分かれば十分)。

## 進行中



































| ツール | 開始日時 | 対象範囲 | 内容 |
| --- | --- | --- | --- |



















## hlib 修正予定（2026-10-02 追加レビュー）

- [x] Component._resolve_input: 単数解決で範囲を全ラッパーへ展開する前に要素数を検証する。Maya2027で441頂点生成後の拒否を再現。
- [x] Node.add_attribute: ベクトル型の分岐前にquery/edit禁止を検証し、通常型と例外の契約を揃える。
- [x] extensions._initialize: 拡張ごとのsys.modules削除をやめ、再読み込み対象の無効化とimport/登録を別段階にする。拡張AがBを継承すると、Bの再importでAの基底が登録済みBと別クラスになる。Maya2027の一時拡張2個で両方loaded・issubclass=Falseを再現。
- [x] 拡張の先行import: 初期化中のパッケージを未対応として確定しない。hlib_bifrostを先にimportするとHLIB_EXTENSION_API未定義の段階でskippedになることをMaya2027で再現。初期化完了後の登録経路とimport順のテストを追加する。宣言の順序変更だけでなく再入・二重importも防ぐ。

## 完了履歴

- Claude Code (2026-10-04): `WorkspaceLayout.captureDockingLayout/restoreDockingLayout/temporaryDockingLayout`を削除(ユーザー指示)。専用GUIでの調査で、cmds/melからworkspaceControlのドッキング先を照会する手段が無いことを確認(`workspaceControl -q -dockToMainWindow`はNone、`workspaceLayoutManager -parentWorkspaceControl`は空、`window -dockingLayout`/`-state`に含まれず復元しても戻らない、`saveAs`のJSONは現在の配置名を切り替えretain=Falseのドックを含まない、`floating=False`でも戻らない)。Qtを使えばできるがhlibはQt禁止のため不可。テストはモック2件を削除し、GUIテストをdock→undock→dockに変更、削除APIが無いことの確認を追加。docs(window_layouts.rst・hlib-api-design.md)とUiSnapshotのdocstringを更新。専用GUI unit 2022〜2027全passed(各99ファイル/941テスト、WindowGuiTest実行)、mayapy 2022〜2027全passed。未コミット。

- Claude Code (2026-10-04): 起動中Maya 2027でGUIテスト(visual 15件passed、GUI内run_all_tests 99ファイル)。GUI内でのみ失敗した3件を修正(test_cmds_interopのMEL `$tmp`がGUIでは文字列のグローバル変数、test_extensionsがGUIでは`sys.executable`=maya.exeを起動、test_hrig_bifrost_startupのバッチ判定未モック)。Maya未起動でもGUIテストできるよう`run_hlib_gui_versions.py`に`--suite all|unit|visual`(既定all)を追加し、新規`run_hlib_unit_gui_tests.py`で使い捨てGUI内にrun_all_tests一式(GUI専用ケース・test_scene_ui・test_window_layout含む)を実行。専用GUIは信頼済みプラグインの場所が未登録で警告ダイアログに止まるため、test_posedriverconnect_extensionはGUIで未登録ならskip(登録はしない)。2022〜2027でvisual全passed、unitは942テスト中`test_window_layout` 1件のみ失敗: `WorkspaceLayout.restoreDockingLayout()`が使う`window -dockingLayout`にworkspaceControlのドッキングが含まれず、浮動にしたウィンドウが戻らない(hlib本体の既存の問題。未修正)。mayapy 2022〜2027全passed。未コミット。

- Claude Code (2026-10-04): レビューの軽微な指摘3点を修正。docs/hlib-api-design.mdのimport群の並び(`import x`→`from x import`の各モジュール名順)と`__init__.py`の扱い(対象外は`hlib/__init__.py`のみ)を実態に合わせ、tools/check_hlib_layout.pyの`--fix`を内側のクラス(クラス内・関数内)にも対応(外側から深さ順)。docs/hlib-testing.mdに内側クラスと`--compare`が順序依存の変化を検出しない旨を追記。既存262ファイルは`--fix`で変更なし・違反0。mayapy 2022〜2027で全件passed。Copilotの整理と合わせてコミット・プッシュ。

- Claude Code (2026-10-04): CopilotのhlibPEP8レイアウト整理(170ファイル)をレビュー。HEADとのAST比較で関数・クラス本体・モジュール文は順序以外同一、モジュール/クラス本体の実行時参照・同名再束縛・dataclassフィールド順・説明コメントの付き先に変化なしを確認(削除コメントは区切り線のみ)。整形ツールの冪等性も確認。test_color.pyの`call.args`(Python3.8以降)を`call[0][0]`へ直し、mayapy 2022〜2027で全件passed(各98ファイル/933テスト)。GUI専用テスト(test_scene_ui等)はGUI未起動のため未実施。未コミット。

- GitHub Copilot (2026-10-04): hlib・hlib_bifrost・hlib_posedriverconnect(テスト除く170ファイル)をPEP8レイアウトへ整理。importをstdlib→maya→相対の3群・アルファベット順、`from maya import cmds`を`import maya.cmds as cmds`へ、定数・`__all__`をimport直後へ、クラス内を属性→`__init__`→特殊メソッド→classmethod→property→公開→非公開の順にしget/set対を隣接。名前・本文・デコレータ・docstringは不変(`tools/check_hlib_layout.py --compare`で確認)。規則をdocs/hlib-api-design.md・hlib-testing.mdへ追記し、検査・整形スクリプトtools/check_hlib_layout.pyを追加。mayapy 2022〜2027でrun_hlib_testsを実行し、2023〜2027はpassed(2027: 98ファイル/933テスト)。2022のtest_color.pyの1件はPython3.7に無い`mock.call.args`を使う既存テストの問題で今回の変更と無関係。GUIでのrun_all_tests.py・Bifrost/PoseDriverConnect実プラグインは未実施。未コミット。

- Codex (2026-10-04): ユーザー指示でQwen3-Coder30B・Llama3.3 70B・Qwen3-Coder-Next80Bを取得し、同一3問と再測定で回答・速度・メモリを比較。Python固定10例／組合せ1365例、Maya2027 standalone8条件で生成コードを検証。速度中央値185／2.14／41.2 token/s、Maya成功6／1／7件。回答全文・測定結果をdocs/research/localLlmComparison.mdとlocalLlmBenchmark/へローカル保存。終了時アンロード確認。Maya GUI併用・長文・費用削減額は未検証。他作業のhlib変更は保持。

- Codex (2026-10-03): ローカルLLM検討用にCPU・RAM・GPU・ディスク容量を読み取り確認。RTX3090Ti 24GB／RAM64GBを確認し、30B・70B・80B候補とMaya連携案をdocs/research/localLlmHardware.mdへローカル保存。モデル起動・ダウンロードなし。推論速度・Maya併用は未検証。

| Claude Code | 2026-10-03 | maya/modules/CharcoalEditor2.mod | 2023・2025のmllが2023/windows・2025/windowsに置かれたのでmodを確認。各版をmayapyでロードし、実際の版に合わせて2025=2.10.2・2027=2.8.1へ修正(2022/2023/2024=2.6.4、2026=2.7.6)。submoduleへのmll追加はsubmodule側で未コミット。 |

| Claude Code | 2026-10-03 | maya/modules/CharcoalEditor2.mod | 2023の項目を追加(2.6.4・2023/windows)。submoduleに2023用(と2025用)のmllが無いため、置くまでは2023ではロードできない。未コミット。 |

| Claude Code | 2026-10-03 | maya/inhouse/hedit Maya 2023対応・CLAUDE.md | hedit.mllを2023でビルド(警告0)、hedit.modに2023を追加、docs/README/撮影ツールの版の一覧に2023を追加。CLAUDE.mdの版の一覧・ツールセット(2023=v142)を更新し「2023未インストール」の記載を削除。2023でrun_tests・run_gui(全スイート)・run_startup・run_session・Sphinx -W 成功。未コミット。 |

| Claude Code | 2026-10-03 | maya/inhouse/hedit 出力欄のスクロール | 新しいログが表示されたら途中を見ていても必ず最下部へスクロール(選択範囲は保持)。テスト・usage/README/changelogを更新。5版ビルド警告0、run_tests 2024/2027・run_gui 2024/2027・output_format 2027・Sphinx -W 成功。未コミット。 |

- Codex (2026-10-03): ユーザー指示でGit除外対象外の残存変更を確認。.vscode/settings.jsonのWinAppKit CMake参照先をコミット・push。heditの2テストは内容差分がなくステージ操作で変更表示が解消。設定JSONと参照先の存在、差分チェックを確認。Mayaコード変更なし。

- Codex (2026-10-03): Maya2023対応とheditバイナリをコミット・push。HUDサブモジュールの2023バイナリを先行pushし親参照を更新。前回のhlib932テスト・GUI15件・hedit・追加Color9件・Sphinx成功記録と差分チェックを確認。既存のheditテスト変更と.vscodeは対象外。

- Codex (2026-10-03): Maya2023英語/日本語バッチと11個の.modを追加。Qt5.15のDebug参照補正とdevkitキャッシュ更新でHUD/heditの2023ビルド成功。両プラグイン・mGear・PoseDriverConnectのロード確認。2023のcolorIndex(0)照会を回避し、再生範囲Undo不可の既知制限を2023にも記載、GUIテストのSelection旧名を更新。hlib98ファイル932テストと追加Color9テスト、GUI15件、hedit単体/Maya/画面/専用GUI、Qt補正回帰、Sphinx警告なし成功。hrig/Bifrost拡張は2025以降向け、Charcoal/MetaHumanは2023バイナリなし。手動GUI操作・HUD描画・通常バッチからの起動は未検証。既存変更を保持、未コミット。

- Claude Code (2026-10-03): FramePlayerの色をニュートラルに正確再現。色情報(行列/範囲/色域/伝達関数/ビット数、mp4のcolrも自前で読む)を読み、Windowsの映像処理を通さず自前のHLSL(fxcで埋め込み)でYUV→RGB・縮小・色域変換・HDR(HDR画面は明るさそのまま、SDR画面はBT.2390で203cd/m²へ)・10bit(P010・scRGB出力)。右クリックで色の情報の表示と手動の指定。確認用動画の生成スクリプトとFramePlayerColorCheckで10本×SDR/HDR画面×GPU/CPU/縮小がすべて許容差内。実機のHDR画面での確認は未。mainへpush。

- Claude Code (2026-10-03): OpenRVを maya/external/openrv にsubmodule登録(浅いクローン)。色再現性の調査メモは docs/research/openrv_color.md(Git対象外)。mainへpush。

- Claude Code (2026-10-03): FramePlayerにMaya準拠のショートカット(Alt+V再生/停止・Alt+Shift+V範囲の最初へ・Esc停止・K+左ドラッグのスクラブ)とフルスクリーン(Ctrl+F・映像のダブルクリック・右クリックのメニュー、Escで戻る)を追加。実キー入力の自動操作で全項目を確認。mainへpush。

- Claude Code (2026-10-03): FramePlayerのVFR動画(Xbox Game Bar録画)のコマ落ちを修正。Video Processor MFTが色変換・縮小時に時刻を平均fpsの等間隔へ付け直し、約半数のコマが目次と照合できず捨てられていた。MF_XVP_DISABLE_FRCで変換を止めた。FramePlayerVerifyで対象動画693コマ(GPU/CPU・シーク含む)と縞の確認動画の不一致0。mainへpush。

- Codex (2026-10-03): パッケージ名汎用化の実装・拡張・Sphinx・回帰テストを公開対象として確定。差分チェックと前回のMaya5版・最終回帰3件・3名称Sphinxの成功記録を確認し、mainへコミット・push。他作業の変更は対象外。

- Codex (2026-10-03): コア内を相対import化し、拡張検出/reload/ロガーを実パッケージ名に追従。Bifrost/PoseDriverConnectは既知サフィックスを除いて接続先コアを解決。JSON形式・HLIB宣言は維持。Sphinxのタイトル/本文/API/継承図と生成物検査CLIを汎用化しpackage_names.rstに手順を追加。Maya5版全98ファイル成功（2022/24/25/26は930件、2027は931件）。最終3回帰テストは2022/2027成功：mlib/studio_libコピー、元名import禁止、Undo/fast/形状/JSON/拡張/reload、固定import検査、Sphinx変換。PoseDriverConnectの別名登録はSDKスタブによる検証。hlib/mlib/studio_libraryのSphinx -W、各482HTMLの資産検査/APIリンク存在確認、diff check成功。GUI・改名環境での実Bifrost/PoseDriverConnectプラグイン操作は未検証。未コミット・未push。詳細docs/research/packageNameImplementation.txt。

- Codex (2026-10-03): Sphinx本文10ページを実装/docstringと整合（space、cm、法線平均、Plug定義フラグ/要素実体化、数学型、BlendShapeエイリアス、JSON参照解決）。Sphinx -W成功、Python例164ブロックの構文確認、diff check成功。これまでの責務共通化・camelCase移行・利用側更新・docstringを合わせてmainへの公開対象とした。先行のMaya5版各929件成功を確認。今回の本文例のMaya実行/GUI確認は未実施。

- Codex (2026-10-03): hlib実装245ファイル・モジュール/クラス/関数/メソッドのdocstring 2,085件を抽出し、引数・旧名・戻り値を静的検査。実装との意味の照合により62ファイル145件を修正（法線平均、Plug有効性、数学型返却、単位、接続置換、JSON復元制限、旧名、引数説明）。全245ファイルでdocstring除外AST一致、引数照合指摘0、Sphinx -W成功、diff check成功。今回Maya内の動作・全使用例の実行は未実施。未コミット・未push。詳細docs/research/hlibDocstringResult.json。

- Codex (2026-10-03): hlib公開関数/メソッド/propertyの116種類の旧綴りをcamelCaseへ統一し、hlib_*・hrig・HTools・テスト・ドキュメントの使用側を更新。AGENTS/CLAUDE/API設計/開発ガイドへ命名例外・保持値/照会・単位/Undoのルールを明文化。旧名reload除去と保存キー維持の3テスト追加。Maya5版各929件失敗0(skip9/9/6/6/6)、hrig2027 47+69件成功、最終旧名除去3件成功、Sphinx -W成功・構文/差分確認済み。GUI実操作未検証、未コミット・未push。詳細docs/research/hlibCamelCaseImplementation.txt。

- Codex (2026-10-03): hlib全245 Pythonファイルの明示定義1,840件を静的棚卸しし、命名と処理内容を重点照合。法線API・Joint削除・型/回転順序の返却表現・UI作用範囲等を優先度別に整理。docs/research/hlibNamingAudit.txtへローカル保存（Git対象外）。既存テスト/Autodesk資料と静的照合、製品コード変更・Maya実行なし。

- Codex (2026-10-03): hlib責務委譲を実装。Plug書込み検証/値更新、ArrayPlug番号/編集用参照、geometryEditの単数・複数・Shape共通書込み、disconnectInput、hrig参照/単位委譲、JSON単位共有を整理。7テスト追加、Maya5版各926件失敗0(skip9/9/6/6/6)、2027hrig47+69成功、Sphinx -W成功・差分確認。2601点一括218.8ms対単数反復315.6ms、1点fast優位なし。GUI未実施、未コミット。詳細docs/research/hlibResponsibilityImplementation.txt。

- Codex (2026-10-03): hlibの責務・委譲・共通化を調査。Plug書込み、幾何編集、配列参照/作成、入力切断、呼出側の参照/単位往復、複合検証、JSON境界の7候補を実装から整理。所有クラスと段階別受入条件、共通化しない境界をdocs/research/hlibResponsibilityRefactoringPlan.txtへ保存（Git対象外）。本体変更・Maya実行なし。

- Codex (2026-10-03): hlibの追加om2移行13ファイルをコミット。並行作業でFramePlayerのステージが入り08b0ed4は混在コミットになり、分離作業中に別作業側からorigin/mainへ送信済み。リモートのhlib内容一致を確認し公開履歴を保持、ローカルも08b0ed4へ同期。既存作業ファイル保持。919テスト失敗0・6skip、コミット差分チェック成功。

- Codex (2026-10-03): AnimCurve.getInfinityをom2照会へ移行、setInfinity(fast=True)を追加。共通Plugバックエンドで通常Undo/fast直接更新を統一し、fast両側を更新前にロック・接続検証。全8型×5外挿方法を含む2テスト追加、5版各21件成功、2027全体919件・失敗0・6件skip。差分確認済み。GUI・性能計測・Sphinx未実施、未コミット。詳細docs/research/hlibOm2Infinity.txt。

- Codex (2026-10-03): Node.userAttributeNames/getExtraAttributesをom2定義列挙へ移行。複合配列を含むトップレベル一覧の失敗を修正し、配列を展開せず追加順を保持。4テスト追加、5版各73件成功、2027全体917件・失敗0・6件skip。100アトリビュートの名前列挙は限定計測0.899→0.304ms。GUI/Sphinx未実施、差分確認済み・未コミット。詳細はdocs/research/hlibOm2DynamicAttributes.txt。

- Codex (2026-10-03): hlib om2追加移行。scaleGeometryのom2一括照会・fast更新、aliasesのAPI照会、重み付きCVのワールド座標往復を修正。2022/2024/2025/2026各83件成功、2027全体913件・失敗0・6件skip。差分確認済み。GUI/性能計測は未実施。Sphinxは既存venvの実行元欠落・利用可能Pythonに依存なしのため未実行。未コミット。

- Codex (2026-10-03): プッシュ依頼対応。検証済みhlib om2リファクタリング・API単位/命名整理・hrig使用側移行・Bifrostロード状態判定修正と関連ドキュメントを送信対象に確定。FramePlayer作業中変更とdocs/researchのローカル調査メモは対象外。ステージ差分チェック成功。

- Codex (2026-10-03): Bifrost flowWedging失敗を調査。原因はサンドボックスによるLocalAppDataのFlowGraphEngineログ書込み拒否。承認済み通常権限でロード成功を確認。Plugin.loadにロード後の状態検証を追加し、例外なしの初期化失敗をRuntimeError／PluginPackageのload-failedとして扱う。回帰3テスト追加。Maya2025/2026/2027の全95ファイル・各908テスト失敗なし（GUI等6件スキップ）、Sphinx警告なし、差分チェック成功。セキュリティ設定・外部プラグインは未変更。GUI未実施、未コミット。ログは.maya-output/bifrost-load-verified/20261003_095921_758940。

- Codex (2026-10-03): hlibのコマンド層cmds基準／オブジェクト・数学層OpenMaya基準を実装。Plug・姿勢・座標・キーをcm/rad/秒へ統一、MSpace・lowerCamelCase・配列形・周期CV番号を整理。通常cmds Undo／fast om2の単位を共通化し、hrig使用側と移行文書を更新（旧別名なし）。Maya2022/2024は各905テスト失敗なし、2025/2026/2027は各905テスト中flowWedgingロード確認1件のみ失敗。GUI等は各6〜9件スキップ。hrig 47＋69テスト成功、257 Pythonファイル構文確認、Sphinx警告なし・差分チェック成功。GUI未実施、未コミット。詳細はdocs/research/hlibOm2PublicContract.txt。

- Codex (2026-10-03): om2優先リファクタリングを実装。Mesh/非周期CV取得、型付き配列読取り、JSON取得、表示色・スキン検証をAPI化し、fast配列作成/行列書込みのcmds往復を削減。単数Componentとベクトルadd_attributeの既知2件も修正。通常Undoと周期CV等の互換経路を維持。Maya2022全94ファイル900テスト成功、2027は既知のflowWedgingロード確認のみ失敗。2024/2025/2026は重点各38テスト失敗なし（GUI1スキップ）。Sphinx警告なし・差分チェック成功。2601頂点の公開取得は同条件の従来相当72〜74msから0.40〜0.57ms。詳細・計測はdocs/research/hlibOm2Implementation.txt。GUI未実施、未コミット。

- Codex (2026-10-03): hlibのom2優先方針で実装243ファイルを静的棚卸し（直接cmds呼出し472箇所・fast宣言122箇所）。共通基盤、座標取得、配列作成、JSON、スキン等を精読し、段階的移行計画とインベントリをdocs/researchへローカル保存。Maya2022/2027 standaloneの既存fast各8テスト成功、2601頂点取得の限定計測とfast中のgetAttr/接続境界を確認。本体変更・GUI検証・全テスト・コミットなし。

- Codex (2026-10-03): hlibリファクタリング計画相談のため設計規約・直近履歴・入力解決・add_attribute・JSON・初期化入口を確認。既知2件の修正、JSONの責務整理、初期化順序の明文化を候補化。実装変更・Maya実行なし。

- 2026-10-03 Claude Code: FramePlayerに自動再生(「ファイル」メニューで切替、設定AutoPlay、Maya連携モードでは再生しない)。WinAppSetupに関連付ける拡張子の選択画面(メモリ上で組み立てたダイアログ。拡張子ごと・すべて選択/解除・右クリック有無、更新時は前回の選択を引き継ぐ。--extensions/--no-context-menu)、確認画面のコマンドリンク化、完了画面の起動チェック既定オフと既定アプリの選び方(右クリック→プログラムから開く→別のプログラムを選択→常に使う)の案内、同一アプリのインストール/アンインストールの同時実行を防ぐ名前付きミューテックス、同じ版の「入れ直し」表示を追加。設定の「既定のアプリ」のアプリページ(ms-settings:defaultapps?registeredAppUser)は新規のユーザー単位登録では開かない(LaunchAdvancedAssociationUIもNOT_FOUND。置き場所・署名・スタートメニュー・URL関連付け・再起動でも同じ)ため、その機能は外した。Keyframe Pro・PowerDVDも利用者の選択で既定になっており、UCPDによりアプリからの既定変更は不可と確認。右クリックの「プログラムから開く」にFramePlayerが出ることをユーザーが確認。検証で作った試験の登録はすべて削除し、アンインストール後の状態がインストール前と一致(Storeアプリの版の差のみ)を確認。コミット・push済み。

- 2026-10-03 Claude Code: 汎用の自作インストーラー WinAppSetup を tools/WinAppKit に追加(Windows標準の機能だけ。1つのexeが --build でセットアップ作成・インストール・アンインストールを担当。アプリごとの設定はINI、中身はRCDATAにLZMS圧縮で埋め込み、アイコンも埋め込み)。ユーザー単位(%LOCALAPPDATA%\Programs、管理者不要)で、ファイル・「アプリ」一覧(Uninstall)・App Paths・スタートメニュー・関連付け(ProgId・OpenWithProgids・Applications・右クリック・Capabilities/RegisteredApplications)を登録し、作ったものを uninstall.wak に記録。アンインストールは記録だけを逆順に消す(共有キーは値だけ、途中のキー・フォルダは空なら)、一時フォルダへ自分を写して続行し最後に自分を消す。更新・失敗時の巻き戻し・起動中アプリの終了(Restart Manager)・危険なインストール先とデータ削除先(Idを含まない場所・共有フォルダ)の拒否。画面はタスクダイアログ、/S で無人。FramePlayerに installer/FramePlayer.wak.ini とVERSIONINFO(1.0.0)を追加し、セットアップはパッケージ直下の FramePlayerSetup.exe(Git管理対象)に出力、Maya側はインストール版もApp Pathsから探す。インストール・更新・起動中のアンインストール(前後でレジストリとファイルが完全一致)・データ削除の安全条件・画面操作を確認。winget list には出ない点は未調査。コミット・push済み。

- 2026-10-03 Claude Code: FramePlayerのアイコンを作成(D案: オレンジの角丸四角に白いF、下にタイムスライダーの目盛り)。元はSVG(resources/icon。32px以上用は8単位、24px・16px用は画素の升目で描き分け)。汎用の道具置き場 tools/WinAppKit を新設し、SVGから.icoを作るIconBuilder(Direct2DのSVG描画とWICだけで作成、サイズごとにSVGを指定可)を追加。.icoをFramePlayer.rcでexeに埋め込み、LoadIconMetricでタスクバー・タイトルバーに表示。Common Controls 6が前提。exeから取り出したアイコンとタイトルバーで確認。コミット・push済み。

- 2026-10-03 Claude Code: FramePlayerのUIを整理。全体範囲の欄を控えめな色にして再生範囲の欄と区別、バー内の重複した番号を削除、まとまりの間隔を16pxに統一、欄とボタンの高さ(24px)と文字(9pt/8pt)を統一。目盛りとバーで動画の外を暗く塗り、「範囲外」に動画の位置(比較中はオフセット込み)を添え、再生範囲外の現在フレームを目盛りの端に矢印付きで表示。全部品にツールチップ(ダーク、ショートカット付き)、ボタン・欄にホバー表示。コモンコントロール6をマニフェストで指定、uxthemeをリンク。キャプチャで確認(ホバーとツールチップは実際のカーソルを一時的に動かして確認し元に戻した)。コミット・push済み。

- 2026-10-03 Claude Code: FramePlayerのタイムレンジをMaya方式に変更。下段をMayaと同じ「全体範囲の最初・再生範囲の最初・バー・再生範囲の最後・全体範囲の最後」の入力欄に(矛盾する側を押して合わせ、再生範囲・I/O・連携で全体範囲の外を指定すると全体範囲を広げる)。タイムラインは動画の長さに縛られず(±1億)、動画は「動画の開始」(StartFrame、変えてもタイムラインの番号はそのまま)に置き、動画の外は「範囲外」表示。動画の外も動画のフレームレートで再生・ループ(範囲が動画の外にかかるときは音声なし)。バー上端に動画のある所を表示。キャッシュ表示は動画の中だけ数える。欄の入力・範囲外表示・動画の外をまたぐ再生とループ・動画の開始の変更・ダブルクリック・連携からの範囲外のframe/rangeを確認。コミット・push済み。

- 2026-10-03 Claude Code: FramePlayerの映像の上の中ボタンドラッグを追加(8px/1f)。比較中は右の映像で2本目のオフセット、左の映像で1本目だけを動かす(オフセットを逆に変えて右の表示は固定。表示コマとオフセットを描画スレッドと同じ鍵の中で同時に変える)。1本のときはコマを動かす。再生中は左右どちらのドラッグでも押した時点で止め、離した位置から再生を続ける。PlayerWindow.hのずれていたコメントを修正。メッセージ送信とキャプチャで確認。コミット・push済み。

- 2026-10-03 Claude Code: FramePlayerの「ずらし」を「オフセット」に改称(比較表示・Maya連携画面・README・コメント)し、フレームの量に単位fを付けた(比較表示「(オフセット +12f)」、Maya画面「オフセット [f]」、READMEのキー操作・遅れの数値)。位置を表す番号(現在フレーム・範囲・目盛り)は数字のみのまま。ビルドしてパッケージ直下のexeを更新、比較画面のキャプチャで確認。コミット・push済み。

- 2026-10-03 Claude Code: FramePlayerとMayaの連携を安全化。通常はポートを開かず、下段の「Maya連携」ボタン(または起動引数--sync、Maya側launchは既定でsync)で連携モードの時だけ127.0.0.1で待ち受け。%LOCALAPPDATA%\FramePlayer\sync.key(本人とSYSTEMのみの権限に明示設定)を鍵にチャレンジとHMAC-SHA256で相互認証、未認証は命令を受けず5秒で切断、未認証接続で認証済みを切らない、命令と数値(±1億)と行長を検査。セキュリティ確認17項目(FramePlayer側)・9項目(Maya側、偽物と鍵なしを拒否)・通常モードでポート/鍵なし・遅れ同等を確認。モジュール再読込時に連携画面を作り直すよう修正。コミット・push済み。

- 2026-10-03 Claude Code: FramePlayerをさらに最適化。目盛りを2枚(通常/現在区画)作り置きして写すだけに、コマ移動時は上段だけ描き直し、再生中・ドラッグ中のタイトル書き換えを1秒4回に間引き(60fps再生中の描画0.70→0.29ms、ドラッグ中0.82→0.34ms)。動画を開くとき目次作成とデコーダー準備を並行し、試しに読んだ先頭コマを再利用(4K60で0.24→0.15秒)。時刻記録をcore/TraceLog.h(FRAMEPLAYER_TRACE_LOG、旧名も可)へ移し開く各段階・描画を記録。確認用ツール全一致、画面操作・比較・連携の通信で変化なしを確認。前回のリファクタリングと合わせてコミット・push済み。

- 2026-10-03 Claude Code: FramePlayerの最適化とリファクタリング。操作部の描き直しを段ごとに(再生中は上段だけ)、停止中の不要な描き直しを削除、ブラシ・裏の画像を使い回し(60fps再生中の描画合計684→382ms、UIスレッドCPU約10→4%)。PlayerWindow.cpp(2056行)を本体806行と操作部PlayerWindowControls.cpp 930行に分割、色・GDI部品をUi、設定をSettings、重複していた時刻関数をcore/Util.hへ。動画を開く処理・レンジの当たり判定・Maya側の設定変換の重複を統合、未使用定数を削除。確認用ツール・画面操作・2本比較・連携の通信・Maya(画面からの接続と遅れの実測)で動作が変わらないことを確認。コミット・push済み。

- 2026-10-03 Claude Code: FramePlayerをmaya/inhouse/FramePlayer/へ移し、hlibに依存しない単体パッケージ化(exeはパッケージ直下、Maya側はpython/frameplayer、maya/modules/FramePlayer.mod、単体用FramePlayer.mod、HTools/animation/framePlayerSync.pyは入口のみ)。Mayaのタイムスライダーと双方向連携(FramePlayerが127.0.0.1:7010で待ち受け、frame/range/play/stop/stateを1行命令でやり取り、受け取った変化は両側で送り返さない、ずらし・倍率・範囲同期)。Maya 2026で双方向・再生追従・ずらし・切断を確認(確認後に終了)。同期の遅れを両側の時刻記録で実測(コマ送り→表示1.5ms、FP→Maya反映6〜35msはMayaの計算分、再生追従は24fpsで100%・遅れ0コマ、重い60fpsでも遅れ最大2コマ)。接続直後にFramePlayerの古い範囲でMayaを上書きする不具合を修正。FRAMEPLAYER_SYNC_LOGで時刻記録。CLAUDE.mdの構成に追記。タイムスライダーのMaya風構造と合わせてコミット・push済み(c9cde6d)。

- 2026-10-03 Claude Code: FramePlayerのタイムスライダーをMayaと同じ構造に変更(上段=再生範囲の目盛り・現在フレームの区画と番号・現在フレーム欄・再生ボタン、下段=開始フレーム欄・つまみ付きレンジバー・終了フレーム欄)。開始フレーム(既定1、設定StartFrame)、再生範囲(I/O・つまみ・ドラッグ・ダブルクリックで全体切替、範囲内ループと先読み)、Alt+,/.、Maya連携の窓口TimeSyncを追加。Maya 2026を起動して同条件のキャプチャで比較(確認後に終了)。release/のexe更新。未コミット。

- 2026-10-03 Claude Code: FramePlayerを軽量化。キャッシュ上限を1GB・30秒分・GPU予算の1/4・主メモリ不足時256MBの最小に(設定CacheMB/CacheSeconds)、再生中は変化時だけ描画しPresent(0)で空回り解消(画面合成が4Hzの環境で1コア→全体0.4%)、背面は前後2秒だけ先読み+低優先度/EcoQoS、最小化30秒/背面5分で休止(キャッシュとデコーダー解放)、キーフレームの縮小画像(幅320・RGB565・160MBまで)で仮表示。720p60・5分でGPUメモリ8.6GB→約1GB。確認用ツールに--thumbnailsを追加し全一致。コミット・push済み。

- 2026-10-03 Claude Code: FramePlayerの色合いをWindows 11の「メディア プレーヤー」に合わせた(Storeから導入して同じ動画を再生・キャプチャし画素を実測。地・タイトルバー#141414、バー#949494、強調#FF8232)。タイトルバーをDWMでダーク化、文字をSegoe UI Variableに。Keyframe Pro風UI・スライダー修正と合わせてコミット・push済み(15ac0b6)。

- 2026-10-03 Claude Code: FramePlayerの操作部をKeyframe Pro風に変更(映像下にスライダーの行=細い帯・現在コマ番号・総コマ数・fps(コマ落ち・ずらしの表示は削除し帯を右端近くまで延長)、下段に左ファイル/比較・中央の先頭/戻る/再生/進む/末尾・右に三角形の音量)。スライダー操作時にキャッシュ帯と現在コマ表示が行ったり来たりする問題を修正(ドラッグ中は前後対称に先読み、停止中の古い表示通知でUIを戻さない)。メッセージ送信+PrintWindowの連続キャプチャで確認。release/のexe更新。未コミット。

- 2026-10-03 Claude Code: FramePlayerの操作部左端に「ファイル」ボタンとメニュー(動画を開く/比較する動画を開く/比較を終了/最近使ったファイル(8件、HKCUのRecentFilesに保存、一覧を消去)/終了)を追加。メニュー項目と有効・無効を外から読み取って確認。release/のexe更新。未コミット。

- Codex (2026-10-02): 未コミット変更全体のコミット対象を確認。hlib構成/入力解決/拡張リロード、hrig利用側、文書/テスト/規約の223ファイル。生成物・外部調査ログなし。直近のMaya2022/2027各36テストとSphinx成功を確認し、末尾空行を整備。mainへコミット・pushを実行（結果はチャットで報告）。

- Codex (2026-10-02): 拡張のimport試行名を追跡し、親の初期化失敗後に残った子モジュールも次のreloadで一括解除。利用可否確認後に依存ソースを検証し、unavailableな拡張の非対応構文を解析しないよう修正。修正後初回reload/探索パス削除/利用可能時の構文検証の回帰テスト追加。Maya2022/2027は関連5ファイル各36テスト＋コマンド再読み込みスクリプト成功。Sphinx警告なし、対象差分チェック成功。GUI/他バージョン未実施、未push。

- 2026-10-02 Claude Code: FramePlayerに2画面比較(段階C)を追加。右半分へのドロップ・2ファイル同時ドロップ・「比較」ボタン/Ctrl+Shift+Oのファイル選択・起動引数で2本目を開く。コマ番号で同期し[ ]でずらし、範囲外は表示で知らせる。再生は両方のコマがそろってから進める。比較中は消音、キャッシュは半分ずつ(Clip::setCacheLimit)。メッセージ送信で表示・同期・ずらし・再生・終了・ファイル選択画面を確認(実際のドラッグ操作は未確認)。release/のexe更新。未コミット。

- Codex (2026-10-02): 拡張リロードを追加レビュー。Maya2022/2027で初期化例外後の孤立サブモジュールが残り、修正後最初のreloadでも古いconfig値を使うことを再現。Maya2022で利用不可の拡張も全ソース先行解析により新Python構文でerrorになることを再現（2027ではunavailable）。実装変更なし。

- Codex (2026-10-02): hlib.reloadで宣言済み拡張を先に一括解除し、本体再読み込み後に再検出・登録するよう変更。他拡張への静的import/ラッパー継承を拒否、初期化中reloadを拒否。Bifrostは宣言先行・サブパッケージ遅延importへ。Maya2022/2027の関連5ファイル各34テスト＋コマンド追加変更削除スクリプト成功、先行importの新規プロセス検証成功。Sphinx警告なし。GUI/他バージョン未実施、未push。Componentとadd_attributeの2項目は修正予定のまま。

- 2026-10-02 Claude Code: FramePlayerのタイムスライダーを、再生中に触ったらドラッグ中はそのコマを表示し、離したらその位置から再生を続けるよう変更(YouTube同様)。停止中は停止のまま。release/のexeを更新。未コミット。

- 2026-10-02 Claude Code: FramePlayerに音声再生(MF+WASAPI、映像を音声位置に同期・差±0.03ms)と音量UI(スピーカー/スライダー/M・↑↓、HKCUに保存)を追加。続けてキャッシュをGPUメモリ(NV12)へ移行(GpuDevice共有、D2Dで直接描画、予算の半分・最大8GB)。720pで約4600コマ保持・主メモリ約200MB。確認用ツール12通り全一致。デコード中にGPUの鍵を持つとデッドロックするため鍵は自前の写しと描画だけに限定。未コミット。

- Codex (2026-10-02): hlibの依存関係を追加レビュー。Maya2027 standaloneで拡張先行importの誤判定・拡張間継承のクラス不一致を再現。hlib本体2回reload後のモジュール直下クラス参照/直接基底に旧クラスなし。前回2件と計4件を修正予定へ記録。実装変更・GUI確認・全バージョン実行なし。

- Codex (2026-10-02): hlib参照構造変更後を追加レビュー。Maya2027 standaloneで単数Component解決が441要素生成後に範囲拒否すること、vector add_attributeのquery/edit共通検証漏れを確認。実装変更なし。

- Codex (2026-10-02): Objectへ汎用入力展開、Nodesへ展開済み列の混在検査を分配。Node.add_attributeからcmds逆参照を除き、addAttrはNode共通実装へ委譲。executeDeferredはDeferred.callへ委譲。_core.collectionのNodes参照を削除し実行方針をNodes._dispatch_sharedへ移動。公開API/Undo/独自call_eachを維持。Maya 2022全93ファイル成功、2027は既知のflowWedgingロード確認のみ失敗。追加を含む重点40テストは両版成功。Sphinx警告なし・差分チェック成功。GUI未実施、未push。

- Codex (2026-10-02): hlib実装243 Pythonファイルのimport・主要呼出しを静的レビュー。Object/Nodes間の入力処理、Node.add_attributeとDeferred.callのcmds依存、_core.collectionのNodes参照、root一括初期化を設計上の改善候補として整理。Node/Plug等の必要な相互参照と区別。実装変更・Maya再実行なし。

- Codex (2026-10-02): hlib/hlib_bifrost/hlib_posedriverconnectの公開別名、転送専用モジュール、動的属性、JSON読替え、フォールバックを追加監査。追加削除対象の旧互換入口は見つからず。現行の短縮フラグ・Mayaアトリビュートアクセス・任意拡張判定・リロード時の廃止名削除は維持。Maya 2027の関連5ファイル38テストは失敗なし（GUI1件スキップ）。実装変更なし、作業記録のみ更新。

- 2026-10-02 Claude Code: FramePlayerの映像をVideoView(子ウィンドウ+描画専用スレッド、D3D11+Direct2D、垂直同期)で表示するよう変更。再生の時間管理も描画スレッドへ移し、再生中は画面消灯を抑止。操作(コマ送り・スライダー・再生・終了)と番号一致を確認。リモートデスクトップ(画面32Hz)では24fpsのコマ落ち0、60fpsは画面の書き換え回数の上限で約半分落ちる。ローカル画面での60fps測定は未。CLAUDE.md/AGENTS.md/copilot-instructionsの日本語報告ルールを具体化。未コミット。

- Codex (2026-10-02): hlibと拡張の旧API互換を調査。Matrixのrotation引数/プロパティ・decomposeの重複rotationキー・_wrap_copy・to_mmatrix、SkinClusterのsinusoidal、JSONのTranslate/Rotate旧型タグ変換を削除。利用例と回帰テスト更新。短縮フラグ・Maya型変換・基底インターフェース・廃止名除去処理は維持。Maya 2022全93ファイル884テスト成功、2027は既知のflowWedgingロード確認のみ失敗。Sphinx警告なし、差分チェック成功。GUI未実施・未push。

- Codex (2026-10-02): generalをscene/ui/environment/eventsへ分割し、hlib_bifrostの導入管理もenvironmentへ移動。ObjectをNode/Plug/Componentの共通基底・種類判別入口として追加、coerceを削除して各基底に入力解決を集約。内製利用側、Sphinx、開発規約を更新。Maya 2022/2024は全93ファイル成功、2025/2026/2027は92/93成功（各883テスト、GUI等6〜9スキップ）。残る失敗はflowWedgingのロード確認（2027では変更前から記録あり）。hrig/Bifrost追加18テスト成功。Sphinx警告なし、差分チェック成功。GUI実操作・pushは未実施。

- 2026-10-02 Claude Code: FramePlayer高速化。GPU(D3D11)でデコード・色変換・縮小し4コマ先まで並行処理(4K60 80Mbpsで57→約200コマ/秒)、mp4/movのサンプルテーブル直読で目次作成(1時間36GBで開く約1秒)、キャッシュ解放をロック外へ、キャッシュ帯の計算を間引き。確認用ツールで全テスト動画の順・逆・ランダム一致。再生中のコマ落ちは現在のPC負荷由来(旧版・Keyframe Proも同条件で落ちる)。36GB検証ファイルは削除。未コミット。

- Codex (2026-10-02): 全体の責務を再確認。JSON保存形式とシーン更新の境界、SkinCluster保存経路、入力解決、テスト分離を優先する段階案を整理。便利API・数学型・登録機構は維持。実装変更・テスト実行なし。

- Codex (2026-10-02): 計算ノード21ファイルの値検証・設定41か所と接続45か所を既存_Calculationへ集約。公開signature・Undo・fast・戻り値を維持。Deferred.callはexecuteDeferredへ委譲しJSONは維持。Maya 2024全92ファイル成功、2027は91/92（Bifrost起動テストでflowWedgingのloaded確認が失敗）。追加回帰テスト成功、Sphinx警告なし。GUI未検証。

- 2026-10-02 Claude Code: FramePlayerを先読みキャッシュ方式へ移行(段階A)。デコードせずに表示時刻の目次を作り、デコード結果を目次と照合して番号を確定。上限4GBのキャッシュと再生ヘッド周辺の裏読み込み、スライダーにキャッシュ帯。確認用ツールで順・逆・ランダム×キャッシュ4GB/64MBの全コマ一致、7200コマ動画も一致・開く0.24s。未コミット。

- Codex (2026-10-02): nodesの単純Plug転送を静的調査。直接getを返す68メソッド、connect後selfを返す49メソッドを候補抽出。計算ノード中心の削減案と、配列生成・値検証・型変換・戻り値を維持する注意点を提示。実装変更・Maya実行なし。

- Codex (2026-10-02): hlibのクラス削減候補を実装・内製利用箇所から確認。標準API転送のみのクラス整理、状態を持たない計算クラスの関数化、所有権管理型の維持を提案。実装変更・Maya実行なし。

- Codex (2026-10-02): BulkCollectionを削除し、反復・一括実行・事前検証・Undo・signature共有をNodesへ移動。派生call_eachの委譲と既存sliceを維持。Maya 2024全92ファイル・876テスト（GUI等9スキップ）成功、Sphinx警告なし。

- 2026-10-02 Claude Code: FramePlayerに配布用exeのインストール手順(cmake --install → apps/FramePlayer/release/)を追加し、exeをコミット・push済み(faebb0a)。hlibの他の未コミット変更はユーザー指示によりpush対象外。

- Codex (2026-10-02): Plugins/Colors/DrivenKeysを削除。Plugin.loaded・DrivenKey.find・複数ノード色取得をlist化、利用側とドキュメント更新。Maya 2024全92ファイル成功、Sphinx警告なし。BulkCollectionはNodesへ一括実行機能を移して削除可能と確認し、今回は維持。

- 2026-10-02 Codex: 基底クラスによる共通化を検討。既存BulkCollectionへの重複集約、Maya継承に沿うGeometryFilter系、UI内部参照基底の候補と適用境界を確認。製品変更・Maya実行なし。

- 2026-10-02 Codex: hlibの不要処理を静的調査。製品231ファイル（init等除外）のAST・内製使用側・テスト参照から削除/統合候補と動的登録等の維持対象を区別。詳細はGit対象外docs/researchに保存。製品コード変更・Maya実行なし。

- 2026-10-02 Claude Code: FramePlayerにタイムスライダー(クリック/ドラッグ・目盛り)と再生ボタン(Space)、ループ再生を追加。高精度タイマーのスレッドでコマ境目に合わせて進め、再生中は簡易拡大縮小で描画。24/29.97fpsはコマ落ち0、60fpsは8秒で2コマ。操作はウィンドウへのメッセージ送信で確認。未コミット。

- 2026-10-01 Codex: hlib内部の責務を整理。SkinCluster検索共通化・DAG解決再利用、用途別Snapshotへの取得/検証/適用移動、Plug型読取/fast数値書込の定義共有、Bulkのsignature検証共有、bootstrap登録構築共通化とreload探索キャッシュ無効化。公開API/JSON形式/継承/部分失敗契約を維持。新規5テスト、5版対象134件（GUI1skip）成功、最終数値経路13件を5版再確認、2024全体92ファイル880件（9skip）成功。Sphinx -W成功、速度比較はほぼ同水準（詳細Git対象外）。GUI未実行・未コミット・未push。

- 2026-10-01 Claude Code: 単独動画プレイヤーapps/FramePlayer/(C++/Media Foundation/Win32、外部ライブラリなし)の段階1を新規作成。全コマ先読み方式で←→コマ送り、確認用ツールFramePlayerVerifyでH.264(Bフレーム・長GOP・mp4/mov)とMJPEGの全コマ一致を確認。GUIはキー操作とウィンドウ描画を確認。未コミット。

- 2026-10-01 Codex: hlibの共通基盤・Node/Plug・SkinCluster・JSONを読み取り確認し、既存API/継承/速度を維持する段階的リファクタリング計画を提示。製品コード変更・Maya実行なし。前回push済みの進行中行を解消。他ツールのapps作業は保持。

- 2026-10-01 Codex: 全未コミット変更の公開準備。hlib速度改善・回帰テスト・ドキュメントと既存作業ログをまとめて差分確認。検証済み結果を維持し、Git対象外の調査・生成物は除外。

- 2026-10-01 Claude Code: hrigフェイシャルモジュラーリグ（MetaHuman型・ゲームエンジン向け）の設計ドラフトをGit対象外docs/research/hrig-facial-design-20261001.mdに作成。製品コードは未変更。

- 2026-10-01 Codex: 追加最適化を実装。同一引数一括呼出の実関数別検証共有・不要結果配列削除、Node.plugのfunction set再利用、fast行列の直接MPlug更新、短縮フラグの入力形検証キャッシュ、influence検索表共有。ウェイト範囲書込は失敗時挙動が違うため逐次更新を維持。新規テストの失敗検出とPython3.7 Mock互換も修正。最終関連227件は2022/2024/2025/2026/2027成功、2024全体91ファイル875件（9skip）成功、Sphinx -W成功。再計測はGit対象外docs/research保存。GUI未検証・未コミット・未push。

- 2026-10-01 Codex: 追加の速度改善候補をコード調査。検討資料はGit対象外docs/researchに保存。既存の未コミット実装は保持し、新規の製品変更・再計測なし。

- 2026-10-01 Codex: hlib速度改善4項目を実装。keyword-only fastのbind省略と状態変更抑制、world行列のDAGパス取得、通常Undoの重複チャンク省略（transaction境界維持）、fastWriteの更新内function set共有。Maya2022/2024/2025/2026/2027で関連180件ずつ成功。2024全体90ファイル成功・870件実行（9skip）、Sphinx -W成功。再計測はGit対象外docs/researchに保存。GUI未検証、未コミット・未push。

- 2026-10-01 Codex: 速度改善候補を専用Mayaでプロファイル・試作比較し、検討資料をGit対象外docs/researchに保存。製品コードは未変更。

- 2026-10-01 Codex: 依頼された速度比較を専用Maya standaloneで実測し、値一致・Undo復元を検証。詳細と再現スクリプトはGit対象外のdocs/research内に保存。製品コード変更なし。

| Claude Code | 2026-10-01 | maya/inhouse/hedit 0.3.0 設計の見直し | 設計レビュー15件に対応(固定の出力先・自己ロードの廃止・アイコンのメモリ描画・meta_path位置・版情報/CFG/PDB・heditTest分離・状態の明示的な作成と破棄・Request/SymbolType・言語の列挙・エスケープ統一・CodeAssist分離・__file__・tabs/<id>.txtとpreferences.jsonとui.jsonの整理・Python例外の受け止め・出力取り込みの代替・ui_smokeの名前付き検査・.gitattributes)。5版ビルド警告0、run_tests/run_startup 5版・run_gui 2024/2027と各スイート・run_session 2024/2027・Sphinx -W 成功。 |

- 2026-10-01 Codex: ユーザーのpush依頼に基づき、hlib設計修正・Qt依存除去・関連hrig/テスト/ドキュメント/開発規則を公開対象として確認。差分検査と直近の対象テスト・Sphinx成功を確認。GUI未検証と既知の互換制限は上記作業記録のとおり。

- 2026-10-01 Codex: hlibのQt依存を除去。Window/WorkspaceControlの寿命をMaya API 2.0 MUiMessage削除通知で共有監視し、最終参照解放で解除。MainWindow.widgetを削除しhrig LayerEditorでQtのトップレベルUIから親を取得。テスト内のQt importも削除、再混入のAST検査を追加。AGENTS/CLAUDE/Copilotと設計・Sphinxへ方針を記載。2022/2027でhlib対象19件中16成功・GUI3skip（削除通知はmock）、hrig対象13件は2027成功。hrig2022は既存のPython3.10+型注釈でimport不可。Sphinx -Wと差分検査成功。実GUI削除通知・hrig親表示は未検証。未コミット・未push。

- 2026-10-01 Codex: hlib設計5項目を修正。ConstraintをTransform派生、表示APIをDagNode/DagNodesへ移動。一括公開を明示宣言化し更新は自身を返す。単位setterからsave除去、他の保存要求はbatchで変更前検証。UI参照はQt実体の寿命を検証しUiSnapshotで退避、配置APIはドッキング範囲を名称へ明示。関連テスト・Sphinx・設計基準更新。全体2022は88ファイル成功、2027は既知flowWedging失敗のみ。追加の対象テストは両版成功（実Qt削除検知含む）。Sphinx -W成功。専用GUIは2027ライセンス初期化失敗、2024起動100秒timeoutで所有プロセス終了、実ドッキング復元未検証。未コミット・未push。

| Claude Code | 2026-10-01 | maya/inhouse/hedit 設計レビュー(コード変更なし) | 配布・起動、画面スレッドでのPython同期呼出し、出力取り込みのMaya内部依存、自動保存の全書き直し、状態ファイル3種、グローバル状態、補完エンジンの型などを洗い出し、docs/research/hedit-design-review-20261001.md に記録。 |

- 2026-10-01 Codex: hlibのクラス設計をレビュー。継承・基底責務・複数形API・保存契約・UI参照寿命を確認。Maya 2027 standaloneでconstraintの実際の継承を照会。実装変更なし。

| Claude Code | 2026-10-01 | maya/inhouse/hedit ホバー | 名前にマウスを重ねる/Ctrl+K→Ctrl+Iで定義の見出しとdocstringを出すホバーを追加(core/docstrings・宣言の抽出・CompletionEngine::describe・bridge.describe・HoverPopup・hedit -describe)。tests/output_format_smoke.pyの末尾一致をMayaの遅延出力に強い判定へ修正。5版ビルド警告0、run_tests 5版・run_gui 2024/2027(+補完/整形/出力スイート)・run_session・run_startup・Sphinx -W 成功。未コミット。 |

- Codex (2026-10-01): hlibのノード/プラグ拡張・Preferences・Shelf・ウィンドウAPIと関連ドキュメント、hrigの単位API移行を公開コミット対象として確認。heditの進行中変更を除外。直近Sphinx -Wと対象テスト結果を確認し差分チェック成功。既知のBifrostテスト失敗・実GUI未検証は各作業記録のとおり。

- Codex (2026-10-01): generalにWindow/WorkspaceControl/WorkspaceLayout、共通内部基底と取得コマンドを追加。表示/位置/サイズ・ドッキング・全体ロック・名前付き保存/切替・同一配置内メモリ退避/例外時復元を実装。使用ガイドと専用GUIテスト追加。2022/2027各15件中13成功/GUI2skip（UI呼出はmock）、Sphinx -W成功。専用2024 GUIは起動120秒timeoutで所有プロセス終了、実UI保存復元未検証。未push。

- Codex (2026-10-01): Mayaウィンドウ設計を公式資料・標準MEL・既存hlibから調査。概念別クラスと一時退避/永続保存の区別を提案。調査メモはGit除外のdocs/research。実装変更・GUI実行・pushなし。

- Codex (2026-10-01): Shelf/ShelfButtonとgetShelf/createShelfを追加。タブ一覧・選択・ボタン取得/追加/編集/削除・clear・明示MEL保存、遅延ロード対応、Sphinxガイド追加。2027 standaloneで8件中7成功/GUI1skip（保存・UI照会はmock）、型公開確認とSphinx -W成功。専用GUI起動はライセンスセッション作成失敗で開始不可。実GUI操作・保存未検証、未push。

- Codex (2026-10-01): Preferencesの全setterにsave=False、save()を追加。ユーザー設定をoptionVarへ同期してMEL savePrefs -generalを呼ぶ。単位の既定値転記・シーン保存なし。2027の6テスト成功（保存呼出はmock）、Sphinx -W確認。standaloneではsavePrefsなしを確認しGUI専用の明示例外を追加。GUI実保存・再起動未検証、未push。

- Codex (2026-10-01): 設定の作用範囲と保存先のSphinx一覧を追加。Preferences全get/setに保存区分を記載し、概念別操作クラスとスナップショットの区別を設計基準へ追記。保存用optionVarの同期と永続化の制限を明記。Sphinx -W成功、差分確認済み。実行処理変更なし、Maya再起動検証なし、未push。

- Codex (2026-10-01): Preferencesへ単位・上方向・Undo・自動保存・選択順設定を追加。Unitsを廃止し変換はutils.units、一時切替はdecorators.native_unitsへ移行。Maya 2022全85ファイル成功、2027は84/85成功（既存Bifrost起動テスト失敗）。追加テスト成功、Sphinx警告なし。GUI未検証・未プッシュ。

| Codex | 2026-10-01 | Scene仕様確認 | Scene/getSceneの現行実装を確認して説明。コード変更・Maya実行なし。 |

| Claude Code | 2026-10-01 | maya/inhouse/hedit 調査(コード変更なし) | ウイルス誤検知の追加調査。uiScriptのloadPlugin+workspaceLayoutManager -saveによる再ロードの仕組み、meta_path先頭への差し込み、SVGの書き出し、非表示reporter、__import__/compile文字列、PDBの絶対パス、CFG無効などを洗い出して報告。 |

| Codex | 2026-10-01 | カーブ長の単位 | NurbsCurve.lengthの既定を現在のシーン単位へ変更、unitで距離単位を指定可能にした。既存Units.get_linearを案内しconvert_distanceを追加。2022/2027各5テストとSphinx -W成功。GUI未検証、未push。 |

| Codex | 2026-09-30 | NurbsCurveカーブ長 | length(tolerance, ws=False)へワールド空間照会を追加。メモリ内コピーで非均等スケール/シアー/有理曲線/インスタンス対応、元形状・Undoを変更しない。2022/2027各4テストとSphinx -W成功。GUI未検証、未push。 |

| Codex | 2026-09-30 | 計算ノード追加 | 提案22ノード＋2026以降のAddDL/MultDL＋Maya基底2型をnodes直下に追加。入力/接続/演算モード/配列/ランプ/行列/形状評価を実装。2022/2024/2025/2026/2027各12テスト成功。2027全体823ケース、83ファイル中82成功（既知のflowWedging起動確認のみ失敗）。Sphinx -W成功。GUI未検証、未push。 |

| Claude Code | 2026-09-30 | maya/inhouse/hedit 同梱Python起動 | 16進数変換(binascii.unhexlify)とexec(compile())をやめ、普通の文字列リテラル+importlib.abc.InspectLoaderで読み込むよう変更(ウイルス誤検知対策)。5版ビルド警告0、mllから該当文字列が消えたことを確認。run_tests/run_startup 5版・run_gui 2024/2027・Sphinx -W 成功。プッシュ済み。 |

| Codex | 2026-09-30 | ノード対応状況の確認 | 既存クラスと内製使用箇所を確認して追加方針を回答。実装変更なし。 |

| Codex | 2026-09-30 | マテリアル/シェーダー | nodes直下に14型を追加、Mayaの継承（2022の中間型差を含む）へ対応。作成・割当・フェース/インスタンス照会・テクスチャ接続を追加。2022/2027の対象5テスト成功。2027全体810ケース/82ファイル中81成功、既知のBifrost起動確認のみ失敗。Sphinx -W成功。GUI未検証、未push。 |
| Codex | 2026-09-30 | 通常visibility・未コミット公開 | 先行作業の全対象変更はe886528としてmainへpush済み。残っていた進行中行を整理。 |

| Codex | 2026-09-30 | エクストラアトリビュート | add_attributeの長短フラグ・ベクトル子自動生成、get_extra_attributes、9種類の専用Plugを追加。2022新規2テスト成功。2027全体はBifrost flowWedging起動確認のみ失敗し変更対象成功。Sphinx -W成功。GUI未検証、未push。 |

| Codex | 2026-09-30 | 通常visibility・未コミット公開準備 | get/set_visibilityをNodeへ集約。通常/アウトライナーの独立性とUndo検証成功。Maya2027全804ケース・80ファイル中79成功、既存Bifrost起動テストflowWedgingロード確認1件失敗。Sphinx -W成功。依頼済み全hlib変更をコミット/push対象に整理。GUI未検証。 |

| Codex | 2026-09-30 | Nodeアウトライナー可視性 | get/set_outliner_visibility追加。hiddenInOutlinerのみを変更し、複数形・Undo/Redo・fast対応。2022/2027 standalone各1テスト、Sphinx -W成功。GUI描画は未検証、未push。 |

| Codex | 2026-09-30 | Transform offsetParentMatrix API | get/set_offset_parent_matrixをMatrixPlug委譲で追加。Transforms/Jointsにも継承。2022/2027 standalone各3テストで値型・一括Undo・fast・ロック拒否を確認、Sphinx -W成功。GUI未検証、未push。 |

| Codex | 2026-09-30 | bindSkin改名・offsetParentMatrix検証 | createSkinClusterをbindSkinへ改名し使用側/型宣言/説明を更新。MatrixPlugは既存実装でget_matrixのMatrixを設定可能。値/型/Undo/fast・親とローカルを含む姿勢一致式を2022/2027各8テストで確認。Sphinx -W成功。GUI未検証、未push。 |

| Codex | 2026-09-30 | freeze/createSkinCluster/mirrorJoint | Transform/Transforms.freeze、形状ごとにSkinCluster(s)を返すcreateSkinCluster、生成Joint(s)を返すmirrorJointを追加。標準長短フラグ・Undo・型宣言対応。Maya2022/2027 standalone各32テスト、Sphinx -W、diff検査成功。GUI未検証、未push。 |

| Codex | 2026-09-30 | Joint inverseScale・radius | connect/disconnect_inverse_scale、get/set_radiusを追加。Jointsは既存bulkで対応。入力のみの切断・同一接続・親なし・一括Undo/Redo・radius fastを2022/2027 standalone各16テストで確認。Sphinx -W成功。GUI未検証、未push。 |

| Claude Code | 2026-09-30 | maya/inhouse/hedit 調査(コード変更なし) | 会社でのウイルス判定・勝手なロード/オートロード解除の原因調査。Maya TrustCenterの信頼が版ごとのフォルダー単位、失敗時にautoload解除、uiScript/requiredPluginでの自動ロード、未署名・版情報なし・hex+execの同梱Python起動を確認。ローカルDefenderでは検出なし。対策案を報告。 |

| Codex | 2026-09-30 | Transformリセット・ピボット・形状スケール | reset(attributes)/reset_pivotを追加。Shape/Transform.scale_geometryはメッシュ・NURBSカーブ/サーフェスのXYZ拡縮、空間・中心・要素指定に対応。Maya2022/2027 standalone各42テストとSphinx -W成功。GUI未検証、未push。 |

| Codex | 2026-09-30 | Transform/mathsミラー | 形状用をmirror_geometryへ改名、位置と向きのmirror_transformを追加。親/世界空間・offsetParentMatrix・UI距離単位・fast対応。数学型にmirror/mirroredを整備。2022/2027 standalone各108テスト成功、Sphinx -W成功。非ゼロピボット/Transform.rotateAxisは更新前に拒否。GUI未検証、未push。 |

| Codex | 2026-09-30 | Joint/Jointsのスケール補正 | get/set_segment_scale_compensateを追加。既存bulk経由の一括操作とUndo/Redo、fast更新をMaya2027 standaloneのJoint全14テストで検証。GUI・他バージョン未検証。ミラー作業は継続。 |

| Codex | 2026-09-30 | Joint/Jointsのスケール補正 | get/set_segment_scale_compensateを追加。既存bulk経由の一括操作とUndo/Redo、fast更新をMaya2027 standaloneのJoint全14テストで検証。GUI・他バージョン未検証。ミラー作業は継続。 |

| Codex | 2026-09-30 | Sphinx表示調整の公開準備 | hlib数学型図の横並び維持・幅追従、hrig/hedit寸法統一の5ファイルを確認。diff成功、既存ビルド検証を継続採用してmainへのコミット対象を確定。 |

| Codex | 2026-09-30 | hrig/hedit docsレイアウト | heditの独立CSSをhlibと同寸法へ更新、hrigは既存CSS共有を確認。全体1200/目次240/間隔28px・960px以下1列。両Sphinx -W成功、生成CSSのハッシュ一致・diff検査成功。ブラウザー目視/プッシュ未実施。 |

| Codex | 2026-09-30 | hlib数学型図の配置 | ユーザー指示で元のTBへ戻し4枝を横並びに維持。objectラベルと親幅追従は保持。ソース・diff確認済み、配置1行変更のみで再ビルド/プッシュ未実施。 |

| Codex | 2026-09-30 | hlib数学型図 | object（Python組み込み）へ表示変更。数学型図はLR配置で枝を縦に並べ、専用mermaid-fit指定で親幅以下へ追従。既存リンク維持。Sphinx -W・JS構文・diff検査成功。ブラウザー目視/プッシュ未実施。 |

| Codex | 2026-09-30 | hlib docsレイアウト公開準備 | CSSと作業ログの2ファイルを確認。diff検査成功、前回Sphinx -W成功を継続採用してmainへのコミット対象を確定。 |

| Codex | 2026-09-30 | hlib docsレイアウト | 全体1200px・右目次240px・列間28pxのGridへ変更し本文800px制限を解消。960px以下は1列、表/コード横スクロール・印刷対応。Sphinx -W・diff検査成功。ローカル表示のブラウザー制限があるため修正版目視未実施、未プッシュ。 |

| Codex | 2026-09-30 | hlib公開ページのレイアウト確認 | フルページ撮影を.maya-outputへ保存。本文max-width 800pxと外枠1600px/右固定メニューの組合せで余白が生じると確認。CSS修正・プッシュなし。 |

| Codex | 2026-09-30 | 数学型図の公開準備 | object→OpenMaya→hlibの図と公式リンクの2ファイル差分を確認。前回Maya2027継承確認・Sphinx成功を継続採用し、mainへのコミット対象を確定。 |

| Codex | 2026-09-30 | hlib docs数学型図 | Python組み込みobjectを共通の頂点としてOpenMaya4型→hlib4型の継承を接続。Maya2027 mayapyで4型の直接基底objectを確認、Sphinx -W・diff検査成功。プッシュ未実施。 |

| Codex | 2026-09-30 | hlib docs数学型の図 | OpenMaya MMatrix/MQuaternion/MEulerRotation/MVectorからの直接継承を図示しAutodesk Python API 2.0の公式リンク追加。4型の実装照合・公式ページ確認・Sphinx -W・diff検査成功。ブラウザー描画とプッシュは未実施。 |

| Codex | 2026-09-30 | hlib概要クラス図の公開準備 | 要約版クラス図と作業ログの2ファイルを確認。diff検査成功、前回の継承・リンク・Sphinx検証を継続採用しコミット対象を確定。 |

| Codex | 2026-09-30 | hlib docs/whyhlib | 概要ページの全135クラス図と文字ツリーを、ノード/Plug/コンポーネント/数学型の23代表クラス・4図へ要約。継承とリンク全件・Sphinx -W確認成功。修正版ブラウザー目視・プッシュ未実施。 |

| Codex | 2026-09-30 | hlib docs概要・クラス図の公開準備 | 4ファイルの差分検査を実施。前回Sphinx -W・135クラス網羅・リンク検証成功を確認し、mainへのコミット・プッシュ対象を確定。 |

| Codex | 2026-09-30 | hlib docs概要・クラス図 | PyMELのようにノードをオブジェクトとして扱う説明へ変更。公開図の横幅13587px・空白表示を確認し8分類のLR図へ分割。135クラス網羅・リンク先全件存在・Sphinx -W成功。ローカルURLはブラウザー制限のため修正版目視未確認、未プッシュ。 |

| Codex | 2026-09-30 | hlib説明・用語統一の公開準備 | なぜhlibの説明、アトリビュート表記統一、コンポーネント具体例をコミット対象として確認。最新Sphinx -W・diff検査成功。Mayaテストは前回2027全75ファイル成功を継続採用。 |

| Codex | 2026-09-30 | hlib docs/components説明 | ユーザー指示によりUnityへの言及3箇所を削除。Mayaの形状要素と具体例の説明を維持。残存検索・差分検査済み。文言削除のみのためビルド再実行なし。 |

| Codex | 2026-09-30 | hlib docs/components説明 | 概要・形状ガイド・API説明にコンポーネント（頂点・エッジ・フェース・CV・UV）とUnityとの概念の違いを明記。Sphinx -W・diff検査成功。説明のみの変更、Maya実行/公開なし。 |

| Codex | 2026-09-30 | hlib全体・関連規約 | 日本語表記をアトリビュートへ統一。docstring/コメント/メッセージ/テスト/Sphinxと3種ガイドを更新。対象ソース残存0・AST確認、2027全75ファイル成功、Sphinx -W成功。他版再実行/公開なし。 |

| Codex | 2026-09-30 | hlib/docs/whyhlib.rst | なぜhlibを説明資料へ拡充。主要/全体クラス図、設計・Node/Plug操作・行列/Quaternion例を掲載。2027で6例と行列復元/中間回転成功、Sphinx -W成功。GUI目視/Pages公開は未実施。 |

| Codex | 2026-09-30 | 本体未コミット全変更 | ユーザー依頼の全本体変更をコミット・プッシュ対象に整理。diff検査とrunner5テスト成功。Maya全テストは再実行なし。第三者リポジトリSIWeightEditorの2ファイル変更と外部Pythonキャッシュは保持・対象外。 |

| Claude Code | 2026-09-30 | maya/inhouse/hedit docs・docstring | Sphinxの各ページを実装と突き合わせて修正(メニュー順・Explorerの表示対象・Zoomの反映先・補完の上限・検索バーのobjectName・構成図など)。同梱Python・userSetup・テストの入口のdocstringをGoogle形式で実装に合わせた。5版ビルド警告0、run_tests 5版・run_gui 2027・Sphinx -W 成功。検索バーのVS Code対応と合わせてコミット・プッシュ。 |

| Codex | 2026-09-30 | hlib残件・runner・tests/docs | Undo/ScriptJobs/JSON二次障害対応、公開名衝突・拡張登録復旧、FBX子環境・件数/skip理由、signature呼出内共有を実装。入力/fast表とPlug低水準入口の維持を記載。5版各75ファイル785件成功、最終Undo保護は5版関連再実行成功、runner5件/discovery/Sphinx -W成功。GUI未実施、未コミット。 |

| Codex | 2026-09-30 | hlib残件整理 | 計画と実装を照合し未反映6項目・一部反映・撤回/維持をresearchへ整理。実装変更/テスト再実行なし。 |

| Claude Code | 2026-09-30 | maya/inhouse/hedit 検索バー・docs/tools | 検索バーをVS Codeの寸法(幅419/入力25/ボタン22/アイコン16)に合わせ、アイコンをC++描画でmllへ内蔵、色はhedit配色・文字はエディターのフォント。選択範囲内で検索・AB(大文字小文字を保つ置換)・不正な正規表現の吹き出しを追加。VS Code撮影ツール(docs/tools/vscode_capture)と比較スクリプト(findbar_compare.py)を追加。5版ビルド警告0、run_tests/run_startup 5版・run_gui(gui_smoke)2024/2027・他GUIスイート2027・Sphinx -W 成功。未コミット。 |

| Codex | 2026-09-30 | hlib collection/Joint/Plug/DagNode・tests/docs | Bulk反復/引数準備集約、Joint適用/Joints全件準備へ整理、Double3子参照再利用、親取得をDagNodeへ集約。2025/26/27全74ファイル成功、2022/24既存73成功+追加3件は丸め差のテスト修正後再実行成功。discovery/reload・Sphinx -W・diff成功。2023未導入/GUI未実施、未コミット。 |

| Codex | 2026-09-30 | hlib追加集約計画 | 複数形・Joint回転移送・Plug子参照の段階計画をresearch保存。mirror/Point/Constraintは既存委譲を維持。実装・Maya実行なし。 |

| Codex | 2026-09-30 | hlib DagNode・tests/docs | DagNode追加、Transform/Shapeのdag_path/dag_fn/parent_path集約。型登録維持・静的公開追加・説明更新。2027関連56テスト/reload成功、Sphinx -W成功、diff確認。他版/GUI未実施。 |

| Codex | 2026-09-30 | hlibベースクラス集約計画 | DAG重複・既存単複継承・Point系・Plug系を確認。API維持の5段階計画をresearch保存。実装変更/Maya実行なし。 |


| ツール | 完了日時 | 対象範囲 | 内容 |
| --- | --- | --- | --- |
| Codex | 2026-10-03 | docs/research/localLlmBenchmark* | ユーザー許可により3モデルをダウンロードし、同一問題の回答・速度・メモリを逐次比較。 |






| Codex | 2026-09-30 | hlib追加内部整理計画 | 後始末例外・登録衝突・bulk検証負荷・テスト環境再現性を実装から確認しresearchへ計画保存。公開API維持、実装変更・Maya実行なし。 |
| Codex | 2026-09-30 | hlib参照/入力契約・tests/docs・hrig使用側 | Node/Plug固定hashと比較、Joint特例廃止、Component比較、具象Node型保証、DAG消失時の切替禁止、名前/Node混在拒否を反映。破棄済みMObjectのis_aliveクラッシュを保持handleで修正。各版2022/24/25/26/27の72ファイル/773件実行成功(skip5/5/2/2/2)、GUI2027 102成功exit0、discovery/reload・Sphinx -W成功。hrig混在1箇所修正後50/51成功、残り外部FKベイクの既知接続属性エラー。規約/移行ガイド更新。他版GUI未実施、未コミット。 |
| Codex | 2026-09-30 | hlib設計固定前レビュー | Joint等価/hash特例、具象型生成、DAGパス切替、ls返却型、失敗契約を調査し候補をresearch保存。実装変更・Mayaテストなし。 |
| Codex | 2026-09-30 | hlib計画再検討 | Maya依存を分離基準にせず対象クラスへ処理を維持。混在入力禁止の適用範囲、単複/Undo/fast/初期化の整理計画をresearchで改訂。数値分離案撤回。実装変更・Maya実行なし。 |
| Codex | 2026-09-29 | hlibリファクタリング計画 | coerce・bulk・Undo/fast・SkinCluster/JSON・初期化/reloadの順で段階計画。公開APIと単複同居を維持。docs/researchへローカル保存。実装変更・Maya再実行なし。 |
| Claude Code | 2026-09-29 | maya/inhouse/hedit(src/・tests/・docs/・README・CMakeLists.txt・release/*.mll) | 補完をC++化: core/script_lexer(Python/MEL字句解析)・python_declarations(宣言抽出)・completion_engine・symbols・completion_types・script_file追加。Pythonはhedit.bridge(公開名/sys.path/組み込み名の窓口、印で変化なしなら送らない)とanalysisのみ、completion.pyとheditorを削除。構文強調を字句解析化(三重引用符の複数行・MEL予約語/$変数/ブロックコメント)。自動保存は変化時のみ、行番号は変化範囲だけ再描画、Explorerは別スレッドで列挙、user_pathsはキャッシュ、dockの調査ログと旧ドック名を削除、MainWindowをmain_window_menus.cppへ分割、設定キーを定数化、補完/解析はJSONでなく構造体で受け渡し。hedit -complete/-declarations(テスト用)追加。5,000行編集中の補完 約100ms→約5ms、cmds.補完p95 2.4〜16ms→1.4〜1.7ms。ast突き合わせ400ファイル一致。5版ビルド警告0、run_tests全5版、run_startup 25回、run_gui 4種×2024/2027、run_session 2024/2027、Sphinx -W成功。未コミット |
| Codex | 2026-09-29 | 全未コミット変更 | 全変更をmainへのコミット・プッシュ対象として整理。hlib/hedit/hrigとドキュメントを含む。差分チェック・サブモジュール参照不変を確認。Git除外の研究メモ/計測ログは対象外。今回Maya全テストは再実行していない。 |
| Codex | 2026-09-29 | README.md・.github/workflows/hlib-docs.yml | READMEへhrig Sphinx公開予定URLとソース/ビルド手順を追加。Pagesに/hrig/を生成するビルドと変更検知を追加。ローカルSphinx -E -a -W成功、diff確認。コミット/プッシュ/公開は未実施。 |
| Codex | 2026-09-29 | hrig/docs・README | 独立Sphinxサイトを追加。hlibとsphinxdoc/CSS共有、既存機能ページを目次へ登録。テスト方法・生成シーン仕様・20条件性能表・両版71件の既存検証記録と制限を掲載。Sphinx 8.2.3 -E -Wビルド、HTML参照先・CSS一致確認成功。Maya再実行・ブラウザ目視は未実施。 |
| Codex | 2026-09-29 | tools/benchmark_hrig_constraints.py・hrig計測docs | --modes指定、各反復前のCached Playback無効確認と照会値記録を追加。2027で5構成×Serial/Parallel×2配置の20条件（300拘束・120frame×5）を再計測、40姿勢条件一致、全条件cache無効/fallbackなし、exit0。無効化ガードと構文検証成功。研究結果はdocs/researchにローカル保存。CPU1スレッド固定・GUI描画/スキンは未測定。 |
| Claude Code | 2026-09-29 | maya/inhouse/hedit(src/editor/・tests/options_smoke.py・docs/preferences.rst・changelog・release/*.mll) | Edit > Preferences 末尾に「Reset to defaults…」を追加。確認(Reset/Cancel)のうえ13項目と文字サイズを初期値へ戻し、preferences.iniから項目を削除、全タブ・出力欄・Zoomへ即反映。タブ本文・ファイル・Explorer・tabs.jsonは不変。options_smokeにキャンセル不変・初期値復帰・ini削除・Reset zoom同等の検証を追加(モーダル後に前面化し直す処理も追加)。5版ビルド警告0、run_tests全5版、gui_smoke 2024/2027成功、Sphinx -W成功。preferences-menu.pngのスクリーンショットは未更新。未コミット |
| Claude Code | 2026-09-29 | maya/inhouse/hedit(src/・cmake/・tests/・docs/・README・CMakeLists.txt・release/*.mll)、docs/cpp-documentation.md | hedit C++を初心者向けの構成へリファクタリング(動作・保存形式は不変)。src/をcore/(Maya・画面非依存: 履歴整形・import走査・検索置換・tabs.json形式)・editor/(Qt画面を部品ごとに分割: MainWindow・CodeEditor・OutputPanel・FindBar等)・plugin/(Maya API: コマンド・出力購読・Python呼出・ドック・メニュー)へ分け、依存は一方向。createEditorの8引数をEditorServices構造体に、色をtheme.hに、版をversion.hの1か所に集約。埋め込みPythonをsrc/python/*.pyの実ファイルにしcmake/embed_python.cmakeでビルド時に配列化。_USE_MATH_DEFINESでC4005警告を解消(警告0)。ui_smoke.cppに検索置換・tabs.json・行編集の単体テスト追加。途中でテストがsetProperty('path')で保存先を書くことに依存していると判明し、pathは動的プロパティを正本に修正。5版ビルド、run_tests全5版、run_startup全5版×5段階、run_gui(gui_smoke/completion_output/formatting_spelling/output_format)2024/2027、run_session 2024/2027、Sphinx -W 成功。未コミット |
| Codex | 2026-09-29 | hrig C++/Bifrost行列追従・benchmark・hlib_bifrost MathBuilder・hlib/utils/undo・tests/docs | 単一入力のhrigMatrixFollowと倍精度Bifrostグラフを追加。C++2025/2027 Releaseビルド成功。2027で300拘束×120frame×5・5構成30条件を同一実行で比較、両版60姿勢条件一致。最終両版各71テスト成功（追加17/setup47/native7）。Parallelは標準OPMがC++より速く、1拘束1Bifrostグラフは重い。Bifrost構築Undo/Redoで専用Mayaが異常終了したためGUI/Undo有効時は拒否し検証用に限定。2025の大規模性能・描画/スキン・Bifrost配列一括は未測定。結果はGit対象外research、AST/RST/format/diff成功、既存変更保持・未コミット。 |
| Codex | 2026-09-29 | hrig拘束性能・MatrixFollow・専用計測ツール・tests/docs | 単一入力のmultMatrix→OPMセットアップと18条件の反復計測を追加。2025/2027各300拘束・120frame×5、各36姿勢条件一致。Parallelの300段階層でOPM約68〜71%短縮、独立配置は2027で改善なし。スカートparent→orient単純置換は姿勢差で不採用。両版setup47件成功、最終2027計測smoke成功、AST/RST/diff確認。初回スレッド数未取得は報告へ明記し照会修正。比較結果はGit対象外research、GUI/描画/スキン速度は未検証。既存変更保持、未コミット。 |
| Codex | 2026-09-28 | hlib追加提案・内製使用側・tests/docs | 推奨改名、入力/ウェイトgetter、Reference継承契約、influencesのNode返却、成分setterのws/fast/自身返却、members可変長入力を反映。旧別名なし・JSON形式維持。hlib関連489件を2022/2027で実行（486成功3skip/488成功1skip）、2027 GUI56件成功、hrig foundations13件成功。hrig追加51件中50成功・外部FKベイク1件失敗はHEAD隔離コピーでも同じ接続属性エラーを確認した既存問題。2022 hrigは既存Python型注釈制約で未検証。Sphinx -W・diff成功。他版Maya未実施、未コミット。 |
| Codex | 2026-09-28 | hlib追加調査4（読取） | Referenceのnamespace/set_namespace・is_root継承意味、members入力契約、ensure_loaded成功保証、kind/typeを調査。Git対象外researchへ保存。実装変更・Maya実行なし。 |
| Codex | 2026-09-28 | hlib追加調査3（読取） | influence返却型・Reference文字列照会名・属性API表記/順序操作・成分別setterの契約を確認。詳細はGit対象外docs/research。実装変更・Maya実行なし。 |
| Codex | 2026-09-28 | hlib追加命名調査（読取） | 戻り値が曖昧な名称3群、入力getter等の補完候補、回転/有効性/単複設定の意味が異なる例外を実装確認。詳細はGit対象外docs/researchに保存。実装変更・Maya実行なし。 |
| Codex | 2026-09-28 | hlib命名・内製使用側・tests/docs | TimeSlider/Units/UI/Workspace/ノードgetter、Plug取得名、Namespace/UiElement保持名propertyを統一。旧別名なし・戻り値維持、BlendColors.get_blender追加。使用側・Sphinx移行ガイド更新。Maya2022/2027 standalone関連各214件成功、2027数学型66件/hrig13件成功、GUI2027最終30件/exit0成功。GUI初回起動前exit251、再試行で旧名が残るテストを修正して成功。Sphinx -W成功・diff検証成功。他版GUI未実施、未コミット。 |
| Codex | 2026-09-28 | hlib命名読取・ローカル調査 | クラス明示API一覧と内部継承を確認し、get/set対・Plug/値・保持値property・意味を維持する例外を分類。候補と影響範囲をdocs/researchへ保存（Git対象外）。実装変更・Maya実行なし。 |
| Codex | 2026-09-28 | hlib複数形・Colors・tests/docs | Nodes→Transforms→Joints / Nodes→SkinClustersへ移行。型検証、DAGパス保持、参照copy/slice、色getterのColors返却・各色setter/全件事前検証・共有属性競合検出、bulk継承signature/禁止設定、instanced Joint削除のUUID単位処理を実装。ls返却規則は維持。Maya2022/2027 standalone各109件成功後、追加インスタンス削除含む関連18件を両版再検証成功（各110件相当）。Maya2027専用GUI最終32件/exit0成功、Sphinx -W警告0・継承図リンク・diff成功。初回GUIは起動前exit251、環境を変え再試行成功。描画色の目視・他版GUI未実施。設計規約/移行ガイド更新、未コミット。 |
| Claude Code | 2026-09-28 | maya/inhouse/hedit(src/editor.*・explorer.cpp・plugin.cpp・dock.cpp、tests/、docs/、release/*.mll) | 4K画面でUIが小さい件: setUiScale(MQtUtil::dpiScale)/scaled()で文字・余白・幅・アイコン寸法を全体的に拡大率へ追従、アイコンはMQtUtil::createIconで高解像度画像。Zoomのpxは100%基準で保存。併せて保存済み空ドックへの`hedit -show`でのクラッシュ(表示を先に行う順序へ)と、未ロード時の浮動ドック自動クローズで出る`Cannot find procedure "hedit"`(closeCommand/uiScriptをロード状態で分岐)を修正。200%で実機確認(コード28px・アイコン40px)。5版ビルド、run_tests/run_startup(浮動ドック段追加)全版、gui_smoke等2024/2027成功。システムのクリップボードが他アプリに占有されていたためコピー確認のみ使用不可時スキップに変更。Sphinx -W 警告ゼロ。未コミット |
| Codex | 2026-09-28 | hlib複数形クラス読取・ローカル調査 | BulkCollection/Joints/SkinClusters・色・ls・型解決/公開・コンポーネント継承・関連テストを調査。Nodes→Transforms→Joints、Colors連携、型/重複/インスタンス/Undo/戻り値の契約と段階的移行案をdocs/researchへ保存（Git対象外）。実装変更・Maya実行なし。 |
| Codex | 2026-09-28 | Color初期値・tests/docs | Color()を番号0/RGB同期で初期化。disabled/coerce(None)の無効状態を維持、Colors()は空。Maya2027 standalone関連28件成功、Sphinx -W警告0、diff成功。今回GUI/他版未実行。既存変更保持、未コミット。 |
| Codex | 2026-09-28 | general.Color/Colors・tests/docs | color.pyへColors追加・generalで公開。順序/重複保持、独立copy/slice、index/rgb列の全件事前検証と同期、既存bulk API対応。Maya2027 standalone関連27件成功、Sphinx -W警告0、diff成功。今回GUI/他版未実行。既存変更保持、未コミット。 |
| Codex | 2026-09-28 | hlib Color・色API・tests/docs | general.Color追加。index/RGB同期・指定形式保持・palette_source/再取得・copy。Node色getterをget系/Color返却へ統一、setterはColor対応と全属性事前検証。BlendColorsは数値を維持しcolor_plug/get_colorへ整理。使用側・Sphinx更新。Maya2027 GUI/standalone各24件成功（Undo/Redo・fast・ロック・複数形含む）、Sphinx -W警告0、diff成功。GUIの描画色目視・他版は未検証。バッチは標準パレットを使用。既存変更保持、未コミット。 |
| Codex | 2026-09-28 | hlib色API読取 | Node/BlendColorsの色取得・設定と既存テストを確認。名称と値/Plug返却の不一致、Noneの影響範囲を説明。実装変更・Maya実行なし。 |
| Codex | 2026-09-28 | hlib追加API整理・使用側・規約/tests/docs | 単数/複数クラス同居をAGENTS/CLAUDE/Copilotと設計規約へ明記。AnimCurveのkey_values/get_tangent/get_infinityと外挿部分更新、ピボット種別/preserveと読み書き空間統一（Joint設定は明示拒否）、SkinCluster移送の全組事前検証・解除bool検証、保持値property化を実装。移行ガイドと使用側更新。Maya2027 standalone全67ファイル実行65成功、旧呼出修正後にbulk4件/起動設定3件再検証成功（合計66ファイル相当成功、既存Bifrost起動の古いmaya_utils参照・flowWedging失敗残存）。追加回帰7件・hrig16件成功。Sphinx -W警告0、diff検査成功。GUI・他Maya版未実行、未コミット。 |
| Codex | 2026-09-28 | hlib追加読取調査 | 前回変更後のAPIを確認し、追加候補と統合しない操作をローカル調査メモへ整理。実装変更・Maya実行なし。 |
| Codex | 2026-09-28 | hlib API整理・main | 依頼された変更のコミット・push準備完了。差分検査成功、リモートと分岐なし。生成物・調査メモは対象外。実行検証・既知の失敗は直下の記録を参照。 |
| Codex | 2026-09-28 | hlib・使用側・tests/docs | 追加検討を実装。Double3Plugを属性読み書きに限定しPlugのws除去、set_flagsへ状態設定統合、Constraint対象事前検証、Joint.remove_influenceのtransfer_to_parent、orientation/version_tuple除去、座標軸内部共通化。使用側・移行ガイド更新。Maya2027 standalone: hlib66ファイル中65成功（追加契約テスト9件成功）、hrig16件成功、最終Joint/Version20件成功。既存Bifrost起動テストのmaya_utils参照・flowWedgingロード失敗は残存。Sphinx -W警告0、diff検査成功。GUI・他Maya版は今回未検証。 |
| Codex | 2026-09-28 | hlib追加調査 | Double3Plug責務差、Constraint事前検証、Jointフラグ・別名、状態設定統合など8候補をローカル調査メモへ整理。API変更・Maya実行なし |
| Codex | 2026-09-28 | hlib・hrig使用側・テスト・docs | 調査提案の推奨項目を実装。MatrixPlugの属性更新への責務限定、重複入口除去、個数/メンバー/親/IK/ウェイトAPI命名統一、set_visible/set_muted/Selection.select、PluginPackage保持値のproperty化。使用側と移行ガイド更新。Maya2027: hlib 66ファイル中65成功（追加回帰4件成功）、hrig関連16件成功。Bifrost起動テストは古いmaya_utils参照とflowWedgingロード確認で失敗。全体ランナーの--worker引数混入を避けた個別ドライバで検証。GUI未実行 |
| Codex | 2026-09-28 | hlib全体（読取調査） | 169ファイルのメソッド一覧と類似候補実装を確認。命名・責務差・フラグ統合の提案をローカル調査メモへ整理。API変更・Maya実行なし |
| Claude Code | 2026-09-28 | maya/inhouse/hedit(src/・tests/・docs/・README・release/*.mll) | hedit同梱Pythonのうち、CPython不要な部分をC++へ置き換え(段階1・2と補完のimport走査のC++化まで完了)。段階1: 起動時の出力履歴取得と整形(compactHistory)・出力用reporterの作成/破棄・タブ復元先の決定(hedit -sessionPath)をplugin.cppへ。段階2: docking.py/startup.py(MayaQWidgetDockableMixin)を廃止し、src/dock.cppでMELのworkspaceControl+MQtUtil::addWidgetToMayaLayoutによるドッキング、ui.jsonの保存、closeCommand/quitApplicationのscriptJob、起動時の復元を実装。hedit コマンドに -show/-floating/-restore/-saveState/-sessionPath(内部 -closed/-quitting)、メニューとuiScriptはMEL。Pythonのhedit.show()/restore()は互換窓口のみ。残るPythonは補完(ast/公開名)と構文チェック(compile)。途中で発見・修正: MELの整数/真偽値結果をexecuteCommandStringResultで取ると空になり-exists判定が常にfalse(段階1のreporter破棄漏れも同因)→melInt/melBool追加、ドック作成時のuiScriptで取り付けると画面が破棄される、Maya2027のaddWidgetToMayaLayoutの戻り値型、アンロード前の遅延ラムダ実行による落ちの予防(lifetime文脈)、PySideのQMainWindow型取り出しで古い削除済みラッパーが返る件(テスト補助tests/hedit_host.pyで回避)。全5版ビルド、run_startup全5版×3段階・run_tests全5版・gui_smoke 2024/2027各29項目・formatting/output_format 2027・session 2024/2027成功。Sphinx -W警告0、撮影ツール動作確認(画像は未更新)。追加(2026-09-28): 既存不具合だったcompletion_output_smokeを修正。原因は初回のimport補完でsys.path走査がPythonスレッドで未開始→候補空で約0.5秒後に出直し、走査中はGILで画面も引っかかる。C++化で解消: src/modulescan.cpp(ModuleScanner)がsys.pathのトップレベル名をC++スレッドで編集画面作成時から走査、初回は最大0.5秒待機、以後5秒間隔で裏で再走査。Pythonはsys.path/読込済み名の受け渡し(bridge.module_names)だけ、Index.scan_topは削除。ui_smoke.cppに走査・判定・並び・追従のC++テスト追加、test_completion/formatting_spellingを追随。テスト側の既存の手順漏れ(前面化せずCtrl+Space・前面化の非同期)も修正し、初回候補の中身は厳密に検証。completion_output全5版成功(2024×3・2027×4含む連続成功)、run_tests全5版、run_startup全5版、session 2024/2027、gui_smoke/formatting/output_format 2024/2027成功 |
| Codex | 2026-09-27 | 未コミット全体・main | ユーザー依頼で既存変更全体をコミットしてorigin/mainへ送信するための確認完了。リモートと分岐なし、差分検査成功。調査メモ・テスト生成物・submodule参照の追加なし。機能検証は直近の各実装記録を参照。 |
| Codex | 2026-09-27 | hlib cmds動詞命名・使用側・tests/docs | constraint→addConstraint、curve/group/ikHandle/sets→create系、node/plug/scene/UI/drivenKey→get系へ13入口を改名。lsはユーザー指定で維持。旧入口なしで使用側更新。生成/追加からquery/editを分離しConstraint/ObjectSet/Plugメソッドへ移行、Plug.set_enum_names追加。2022/2027共通各125件、2025標準69件、2027全体155件成功。専用GUI2027 30項目/exit0・画面確認、Sphinx -W・diff成功。既存変更保持。証跡.maya-output/command-names。 |
| Codex | 2026-09-27 | hlib cmds14件削除・使用側・tests/docs | 指定14コマンドをファイル/公開APIから削除。hrig/hlib_bifrost/テストをmaya.cmdsへ移行、必要なNode/Plug変換を使用側へ明示しconnectionsの平坦ペアを処理。旧APIテスト/ドキュメントとhrig境界ルールも更新。2022/2027共通各95件、2025標準リグ69件、2027全体155件成功。専用GUI2027 30項目/exit0・画面確認、Sphinx -W・diff成功。既存変更保持、未コミット。証跡.maya-output/remove-cmds。 |
| Codex | 2026-09-27 | hlib cmds/delete・Node.delete・tests/docs | 基底Node.deleteを追加し、hlib.deleteは名前から具象クラスへ解決して各node.delete()を呼ぶ。Joint専用のウェイト移送/子階層保持も適用。親削除済み/重複をスキップし、コンポーネントは標準削除。Maya2022/2027各117件（派生delete委譲、Joint子保持、Undo/Redo等）、2027標準リグ69件成功。Sphinx -W・diff確認成功。GUI操作は未検証。既存変更保持。証跡.maya-output/node-delete。 |
| Codex | 2026-09-27 | hlib createNurbs・NurbsSurface・hrig ControlShape・tests/docs | circle.pyを削除しcreateNurbs(type/typ)へ統合。Maya同梱メニューに対応する8種類、単一形状はNurbsCurve/NurbsSurface、cubeは6曲面・squareは4曲線のリスト。NurbsSurfaceラッパー追加、旧使用側を更新。Maya2022/2027各12件（全8種類×履歴有無、Undo/Redo、出力型等）、2025 setups39件、2027標準リグ69件、Sphinx -W・diff確認成功。GUI操作は今回未検証。既存変更保持。証跡.maya-output/create-nurbs。 |
| Codex | 2026-09-27 | hlib createPolygon・hrigデモ・tests/docs | polyCubeを削除しcreatePolygon(type/typ)へ統合。11種類の生成プリミティブ、長短フラグ、履歴に依存せず単一Meshを返す。Transform使用側をtransform()へ更新。Maya2022/2027各12テスト（全11種類×履歴有無、Undo/Redo等）、2027セットアップ39件・デモ高低Mesh/スキン生成成功。Sphinx -W・構文・diff確認成功。GUI操作は未検証。既存変更保持。証跡.maya-output/create-polygon。 |
| Codex | 2026-09-27 | hlib logger・constraint統合・hrig使用側・tests/docs | warning/error/info/printをutils.loggerへ集約、cmds/warningを削除。aim/orient/parent/poleVectorの個別コマンドを削除しconstraint(type=...)へ統合、専用フラグ・型付き照会・編集を維持。hrigの腕脚/スカート/視線を更新。Maya2022/2027共通各131件、2027標準リグ69件・setups39件成功、Undo/Redo確認。Sphinx -W、diff確認成功。未初期化mayapyのログAPI呼出防止・import成功。GUI操作は今回未検証。既存変更保持。証跡.maya-output/logger-entry。 |
| Codex | 2026-09-27 | hlib general/utils・hrig setups・Bifrost・tests/docs | animation廃止。DrivenKey/DrivenKeysをgeneralへ1クラス1ファイル化、CurveFit/DampedSpring/ScalarGraphをutilsへ。Soft IK/補助骨/空間切替/RBF/Spline設定/形状等11クラスとBifrost Soft IKをhrig.setupsへ、MathBuilderをhlib_bifrost.utilsへ。使用側・テスト11ファイル・仕様書9ページを移動し規約更新、互換なし。hrig内のcmds/OM/jsonをhlib APIへ置換、型付きcircle/curve追加。reload後の古いNode参照・参照同一性を修正。2027全155成功、2025標準69/セットアップ39成功、2022 hlib30と関連94件(93成功/GUI1skip)。2022のhrigセットアップ実行は既存の2025以降/Python型注釈制約で不可、対象2025で確認。隔離GUI2027は30項目・exit0・画像確認、Sphinx -W/AST/diff/旧import検索成功。実制作シーン・2025 GUI未検証、既存変更保持、未コミット。証跡.maya-output/rig-boundary。 |
| Codex | 2026-09-27 | hlib general/utils・hlib_bifrost・使用側/tests/docs | context/editors/events/files/namespaces/pluginsのクラスをgeneralへ集約、FBX/参照関数をutilsへ移動。ユーザー指定でdecoratorsは維持、runtime案はgeneralへ変更。公開15→10フォルダ、旧フォルダ/互換importなし、hrig/HTools/拡張/tests/docsと今後の配置規則を更新。2027全153、2022共通67、2025標準69成功。共通240件は239成功/GUI専用1skip（初回flowWedgingログ権限で1失敗、通常権限の32件再検証成功）。最終共通67成功。隔離GUI2027は30項目・exit0・画像確認、Sphinx -W警告0・AST/diff/旧参照検索成功。実制作シーンと2025 GUIは未検証。既存変更保持、未コミット。証跡.maya-output/general-layout。 |
| Codex | 2026-09-27 | hlib cmds/context/events/editors・hlib_bifrost・hrig・使用側/tests/docs | 生転送MayaCommands廃止、hlib.cmdsへ型付き検索/生成/属性/UIを追加（Node/Plug/Matrix/Vector/UiElement、短縮フラグ・Undo・typing公開対応）。maya.utilsはDeferred/executeDeferredへ。Workspace/Units/Selectionをcontext、Bifrostをnodes/plugs/animation/pluginsへ移動。追加指示に従い旧互換11ファイルとクラス再公開を削除、hrig SoftIK互換入口も廃止し使用側・tests・docs・ガイド更新。2022共通66、2025標準69、2027全体152件成功。環境/選択/相互運用/JSON追加97件中96成功・GUI専用1skip。隔離GUI2027は30項目・exit0・画像確認、Sphinx -W警告0、AST106/diff/旧参照検索成功。型付き生成後のmessage所有登録とmenu内local importを修正し再検証。実制作性能と2025 Bifrost評価は未検証。既存変更保持、未コミット。証跡.maya-output/typed-commands。 |
| Codex | 2026-09-27 | hrig・hlib editors/json・関連テスト/docs | MEL3か所をMainWindow.name/NodeEditor.show/GraphEditor.showへ移行。標準json使用9ファイルをhlib.json.JsonTextへ統一、従来の型付きhlib JSONと分離して既存属性形式・標準jsonオプションを維持。直接import再混入・batch拒否・JSON互換検証追加。2022共通64件/2027全体149件成功、GUI2027は26項目成功。初回GUIはエディターを開放したままの監視復元で失敗、起動確認を末尾へ分離して再検証成功（開放状態の監視不安定原因は未特定）。Sphinx -W/AST/diff成功。既存未コミット変更保持。証跡.maya-output/mel-migration。 |
| Codex | 2026-09-27 | hrig・hlib・関連テスト/docs | hrig本体/UI/startup/examplesのcmds・OpenMaya直接依存を除去。既存currentTime/setKeyframe/objExistsとmathsのMatrix/Vector/EulerRotationを再利用、専門フラグ・生戻り値用MayaCommands(24明示メソッド)、Qt親取得MainWindowをhlibへ追加。単位/属性検索契約と直接import再混入チェック追加。2022共通62件、2025標準69件、2027全体147件成功。隔離GUI2027変更後23項目・exit0・画像確認、Sphinx -W・AST53ファイル・diff成功。既存変更保持。実制作性能、2025 Bifrost実評価は未検証。証跡.maya-output/cmds-migration。 |
| Codex | 2026-09-27 | hrig・hlib・hlib_bifrost・関連テスト/docs | Container/ScalarGraph/ControlShape/SoftIK、message配列参照、属性型・単位、skin bind/転送をhlibへ還元しhrigで利用。BifrostのGraph/Node/Compound/Portを1クラス1ファイル化、MathBuilder/SoftIKへ共通化。従来import入口・標準バックエンド維持。2022共通60件、2025標準69件、2027全体145件成功。隔離GUI2027は23項目成功・画像確認・exit0。AST43ファイル/diff、Sphinx -W成功。Bifrost実評価は2027、2025 Bifrostと実制作性能は未検証。証跡.maya-output/common-rig。 |
| Claude Code | 2026-09-27 | maya/inhouse/hedit/docs/(*.rst・tools/capture_suite.py) | heditのSphinxを現行仕様へ修正。install(importフック方式、Windowメニュー項目名・アンロードで削除、mayapyでのloadPlugin→import、旧版更新時の注意)、session(保存先にtabs.json.lock/hedit.svg/startup-debug.log、空workspaceControl時の復元)、output(非表示中・Maya終了中の描画)、development(版更新箇所5か所、テスト一覧をrun_startup/run_gui --suite/test_rename含め現状化、期限、2024のArnold停止、再ロード時の扱い)、index/overview/limitations。既存の表示崩れ4件(空白始まり・入れ子リテラル等)も修正。capture_suite.pyが削除済みhedit.__file__に依存していたのを修正し、画像はコピーせず撮影のみ2027で成功確認(docs画像は未変更)。docs/.venvにrequirements導入、Sphinx -W警告0・HTML内の未描画マークアップ0。未コミット |
| Claude Code | 2026-09-27 | maya/inhouse/hedit/tests/session_smoke.py | Maya 2024でrun_session.pyのwriteが「Tabs were not autosaved」で失敗する件を調査。hedit(Qt5)の不具合ではなく、Maya 2024同梱Arnold(mtoa)の起動直後の遅延登録(registerArnoldRenderer._register→arnoldmenu.updateAvailable→arnoldPlugins)がGUIスレッドを約5.1秒停止させ、テストの壁時計5秒期限が停止中に切れ、停止明けに自動保存タイマーより先に確認が走っていた。心拍タイマー+faulthandlerで特定し、起動4秒後の編集では2027同様約2秒で保存、停止時も明けて約0.1秒で保存されることを確認。C++は変更せず(再ビルドなし)、待機をイベントループの回数(200ms×25回)で数えるよう修正。run_session.py 2024/2027のwrite/read全成功、run_tests.py 2022〜2027全成功。未コミット |
| Claude Code | 2026-09-27 | maya/inhouse/hedit(src/embedded_python.h新規・plugin.cpp・editor.cpp・CMakeLists.txt・scripts/・release/*.mll・tests/・docs) | hedit本体のPython(scripts/hedit/*.py)を.mllへ同梱(sys.meta_path先頭のimportフック、mayapyでも登録)。scripts/userSetup.pyはloadPlugin呼出しのみ。Windowメニュー登録/削除をC++/MEL化し、アイコンSVGも同梱して<userPrefDir>/hedit/へ書出し。初回ビルドで生文字列区切り子16文字超過を修正。evalDeferredがloadPlugin中に走りメニュー未登録→同期登録に修正。空の保存workspaceControlへshow()で差込むとuiScriptに破棄→表示のみでMaya側uiScriptに作らせるよう修正。Maya終了時に閉じた画面へ出力描画しQtアクセシビリティでクラッシュ(2022-2026)→非表示時の即時描画停止とkMayaExitingで転送停止。全5版ビルド、standalone(unit22/mod/offscreen UI)・test_rename全版成功、起動GUI3段階(メニュー/アイコン/メニューから起動/右ドック復元/非再表示/アンロードで削除)全版exit0、総合GUI 2024/2027各29項目成功、session 2027成功。session 2024の自動保存未実行はHEAD(b2cda9e)でも再現する既存不具合として別タスク化。Sphinxは環境に無く未確認。scripts/hedit/__pycache__の削除は権限拒否で残存(importフック優先で影響なしをGUIで確認)。証跡.maya-output/hedit-tests, hedit-startup/20260927_192323, hedit-gui。未コミット |
| Codex | 2026-09-27 | hrig指/Aim/Tweak/Splinefit/PoseEditor/上部menu/startup・hlib CurveFit/PoseRbf・テスト/docs | 指Curl/Spread＋FK、首/左右眼Aim、全モジュール局所Tweak、Spline FK→IK近似/実IK位置誤差/許容値拒否、スカートRBF登録追加/削除/編集UIを追加。hlibへ純Python CVフィットと外部接続保持のRBF再登録APIを還元。追加依頼の上部hrigメニューを起動登録、サンプル/編集入口と重複防止を実装。標準ノード、Enabled/LOD入力切断、保存/Undo対応。2022共通54件、2025標準69件、2027全体137件成功。隔離GUI2025/2027各23項目・exit0、画像確認、Sphinx -W、AST21ファイル/diff成功。指切替の変換ノード増加、Spline m単位fitを修正再検証。初回追加testの角度get期待単位誤りも修正。Splineは近似・中間Twist完全再現不可、ポーズUIはスカート骨補正、親指解剖配置/既存skinへのTweak自動追加/非一様scale/実制作性能は対象外。既存hlib set_matrixのm単位不具合は未修正、Splinefitは軸別APIを使用。証跡.maya-output/controls、hedit並行変更保持。 |
| Codex | 2026-09-27 | hlib.LengthCompensation・hrig腕脚/Spline伸縮レイヤー・UI/監視/テスト/docs | ユーザー指定のストレッチ/スクワッシュ/体積補正を独立レイヤーとして腕脚・Splineへ追加。上下限、方向別強度、逆平方根の断面近似、親断面の累積補償、Enabled/FK/LOD切断、Soft IK距離正規化と逆算、リバースフット合成、保存/Undo対応。腕脚squash初期0。Sphinx -W/構文12ファイル/diff成功。2022共通51件、2025標準62件＋最新変更対象8件、2027全体127件成功。隔離GUI最終2025/2027各16項目・exit0。初期Spline m単位の距離変換とFK複合属性ロック解除を修正。起動直後GUIでUndoキュー空の失敗2回、チャンク釣合い0を確認後、検証開始15秒遅延で両版再検証成功。Splineはスキン前追加、体積は近似、非一様scale/実制作品質・性能は未検証。mGear差分はGit対象外docs/research/mgear-gap-2026-09-27.md。証跡.maya-output/stretch。hedit並行変更保持。 |
| Claude Code | 2026-09-27 | maya/inhouse/hedit/scripts/hedit/startup.py | Maya再起動時にheditウィンドウが復元されなくなる不具合を修正。Maya自身のworkspaceControl復元(uiScript)が既にhedit.restore()で表示・状態記録を済ませた直後、hedit側のuserSetup起動処理が二重に検知してhedit.show()を呼び直し、一度close()してから開き直すためcloseCommandが誤発火、「閉じた」状態が一瞬保存されタイミング次第でそのまま確定していた。restore_previous()にworkspaceControlの表示済み判定を追加し、二重に開き直さないよう修正。原因特定用に開閉状態の追記ログ(prefs/hedit/startup-debug.log、動作へ影響なし)も追加。ユーザーの実セッションで再起動を繰り返し問題なしを確認済み。副次的にGUI自動テストが対話デスクトップと別の実行文脈からはライセンス窓口へ接続できないことが判明(mayapyヘッドレスは問題なし)、hedit本体の不具合ではない |
| Codex | 2026-09-27 | hlib.SplineIK・hrig.SplineRig/LayerEditor/監視・テスト/docs | 背骨+Y/尻尾+Z、骨3〜64本・CV control4〜32個・長さ指定、固定骨長の標準ikSplineSolverと両端Advanced Twistを追加。FK/IK計算/変形/コントロール/内部の階層分離。Mode/Enabled/LowでIK入力切断とFK経路へ変更、UIのIK→FK姿勢合わせ、message保存参照、Undo/Redo、スキン使用中削除拒否。2022共通49件、2025標準56件、2027全体119件成功。隔離GUI2025/2027各16項目・exit0、画面確認、Sphinx -W/構文10ファイル/diff成功。FK→IK自動フィット・伸縮・体積・非一様scale・実制作性能は未対応/未検証。m単位の既存hlib複合scale.setによるtranslate再変換を検証中に発見、軸別scale設定で正常を確認。既存共通処理は未修正とREADMEに明記。証跡.maya-output/spline（probeScale.pyに再現）。作業中のhedit/startup.py外部変更を保持。 |
| Codex | 2026-09-27 | hlib.DampedSpring/PoseRbf・hrig.SecondaryLayer/スカート/UI・テスト/docs | ローカル回転の減衰ばねベイクと標準DGの複数入力Gaussian RBF補正を追加。元の手付け骨を保持し別出力列へ合成、Enabled/LOD切断、再ベイク・保存復元対応。UIに2サンプルと再ベイクボタン。2022共通47件、2025標準49件、2027全体110件成功。隔離GUI2025/2027各18項目・exit0、画面確認、Sphinx -W/構文9ファイル/diff check成功。初回のPlug生成・pairBlend子属性名・全キー削除によるcurve消失を修正して再検証。初版はスカートのみ、揺れはライブ物理ではなくベイク、キー/設定/FPS変更は手動再ベイク。衝突/親移動の慣性/実制作性能は未対応・未検証。証跡.maya-output/secondary。既存変更保持。 |
| Codex | 2026-09-27 | hlib.RotationFollow・hrig.FollowLayer/腕脚/スカート/UI・テスト/docs | Twist/Swing/全回転をQuaternionで0〜100%追従する補助骨を実装。実ローカル行列、基準姿勢、割合のDG評価、Enabled/LOD出力切断、所有・保存参照を共通化。UIに3種サンプルと割合を追加。2022共通44件、2025標準46件、2027全体104件成功。隔離GUI2027/2025各19項目・exit0、Sphinx -W/diff/構文成功。2025初回の属性通知待ちを固定時間から状態待ちへ変更して再検証。旧腕脚の表示階層自動移行、既存スキン自動追加、非一様scale/180度境界は対象外。mGear/AdvancedSkeleton調査と次の優先「揺れ物＋ポーズ補正」はGit対象外docs/research/follow-rig-candidates.mdに整理（この2機能自体は未実装）。証跡.maya-output/follow。 |
| Codex | 2026-09-27 | hlib.RadialWeights・hrig.SkirtRig/ModuleRegistry/UI/監視・テスト/docs | 4/8方向ドライバーから円周の任意列へ隣接二方向の正弦比率を分配。標準parentConstraint回転のみ・各targetオフセット保持・全体Blend/Falloff、Enabled/LOD切断、message参照とスキン使用中削除拒否を追加。UIで列数/各列骨数/半径/長さ指定。2025標準43件（単位/並列評価含む）、2027全体97件、2022共通41件成功。隔離GUI最終2025/2027各14項目・exit0、Sphinx -W/diff成功。GUI初期テストのArnold/HIK遅延起動干渉を開始idle分離で解消し、Undo後の不要な更新も抑止してRedo確認。既存骨への後付け/スキン自動生成/衝突/非一様scale/実制作性能は未対応・未検証。証跡.maya-output/skirt。 |
| Codex | 2026-09-27 | hlib.SwingTwist・hrig.drivenLayer/sampleBuilder/layerEditor・HTools入口・テスト/docs | 基準ローカル回転をSwing/Twistへ標準ノード分解し、1成分→既存DrivenKey→単一属性をEnabled/LOD管理。サンプルモジュールと6種レイヤーの追加・使用チェック・Mode/LOD・SDK/Node Editor起動をPySideパネルに実装。保存参照・Undo・折りたたみ保持・監視解除対応。2025標準38件、2027全体91件、2022共通39件、隔離GUI2025/2027各23項目・exit0、Sphinx -W/diff成功。GUI初回のノード型/Plug比較を修正、後続クラッシュはdumpのQt TreeWidgetItemIterator内と特定し明示子走査へ置換して再検証。保存再読込はexecuteScriptNodes=False（Maya生成UIスクリプト実行時の待機は回避）。並替/削除/ドッキング/既存スキン追加は未対応。証跡.maya-output/layer-editor。 |
| Codex | 2026-09-27 | hlib.BendCorrection・hrig.bendLayer/デモ/チャンネル・関連テスト/docs | 標準ノードで50%回転補間骨と内外の押引き骨を追加。曲げ方向/基準角/内外距離と移動量をChannel Boxで編集、Enabled/LODで出力切断、デモ高詳細13influences・proxy3。XYZの90度超えと単位差を検証し、距離defaultの内部cm問題を修正。2025標準34件・2027全体85件・2022共通37件成功、隔離GUI2027 48項目/exit0、Sphinx -W/diff check成功。既存helperは保持、多軸関節・180度超え・実制作ウェイト品質は対象外。証跡.maya-output/bend-layer。 |
| Codex | 2026-09-27 | hlib.TwistDistribution/MatrixPlug.set_value・hrig.twistLayer/デモ/スキン・テスト/docs | 両端を除くN骨をi/(N+1)で配置し、Quaternion軸成分を標準ノードで分配。X/Y/Z・複合曲げ・最短回転を検証。デモは各区間3本（twist_count指定可）、Enabled/LOD切断、保存・Undo・未使用骨の本数再生成、バインド済み拒否を追加。高詳細にツイスト骨、proxyに基本3骨を使用。行列属性への直接書込をhlibへ追加。2025標準29件・2027全体77件・2022共通34件、隔離GUI2027 44項目/exit0、Sphinx -W/diff check成功。初回の属性版差・行列set委譲・container削除時のセット消失を修正し再検証。180度境界/多回転蓄積は未対応。証跡.maya-output/twist-layer。 |
| Codex | 2026-09-27 | hlib.animation.SpaceSwitch・hrig空間レイヤー・GUI監視・テスト/docs | 標準choice/multMatrixによる汎用空間登録と姿勢保持切替を共通化。IK local/world、Pole local/world/foot、任意target追加、Spaceチャンネル監視と常時有効spaceレイヤーを追加。Foot空間のIK合わせ順序も修正。Maya2025標準22件、2027全体67件、2022共通31件、隔離GUI2027 38項目/exit0成功。Sphinx -W/diff check成功。初期API依存走査が専用mayapyでクラッシュしたためcmds走査へ置換して再検証。旧シーン自動変更なし、構成切替のみで切替アニメーションは未対応。証跡.maya-output/space-layer。 |
| Codex | 2026-09-27 | hrig標準Soft IK・起動・関連テスト/docs | standardバックエンドを既定にし、condition/plusMinusAverage/multiplyDivideと標準containerでSoft IKを構築。起動時Bifrostロード廃止、任意の旧バックエンドとstandardへの交換は保持。Maya2025/2027でロード禁止下の標準スイート各17件成功（数値境界・デモ・LOD・Undo/Redo・保存再読込・削除）。2027交換含むBifrostスイート15件成功（Bifrost初期化由来の警告あり）。diff check成功。GUI実操作は未検証、既存シーン自動変更なし。証跡.maya-output/standard-rig。 |
| Codex | 2026-09-27 | 未コミット変更全体 | ユーザー指示でhlib/hrigの実装・テスト・Sphinx・規約の変更をコミット対象として確認。origin/mainとの乖離なし、diff checkと既存のMaya2022/2027・Sphinx成功記録を確認。研究資料とテスト生成物はGit除外を維持。コミット・プッシュ結果はGit履歴を参照。 |
| Codex | 2026-09-27 | hlib外の利用側コード・参照 | hrig/HTools/hedit/hlib拡張/tools/外部ツールを検索し旧モジュールimport残存なし。Git除外資料も検索しdocs/research/hlib-submodule-review-2026-09-24.mdのarrayPlugへのリンクを修正。実行コードは追加変更不要。diff check成功、Maya再実行なし。ワークスペース外は未調査。 |
| Codex | 2026-09-27 | hlibの19モジュール・import/テスト/docs・AGENTS/API規約 | eulerRotation/scriptJob/channelBox/arrayPlug等へ改名し、内部_coreとdocs補助もlowerCamelCase化。hlib_*にも同規則を明記。テスト探索名/特殊名/パッケージ名/Maya nodeType名とメソッド名は維持。旧構成を読込済みのMaya2027プロセスからhlib.reload移行成功、旧モジュール除去とregistry確認。Maya2022関連192件、2027 Bifrostリグ15件成功。残存旧importなし、Sphinx -Wとdiff check成功。GUI操作とPoseDriverConnectバイナリは今回未検証。証跡.maya-output/camel-modules。 |
| Codex | 2026-09-27 | hlib/utils/version・plugins・hrig起動・版番号テスト/docs | 不変Version値クラスを1ファイルに実装。parts/suffix/major/minor/patch/build・parse・replace・比較/hashを集約。Plugin/Module.versionとPackageの版照会をVersion化、生文字列version_textと既存version_tupleを提供。utils/versions関数を廃止し利用箇所/ドキュメントを更新。Maya2027関連60件成功、2022は56成功4skip、hlib.reload・diff check・Sphinx -W成功。GUI未実施。証跡.maya-output/version-class。 |
| Codex | 2026-09-27 | hlib/plugins・utils/versions・Node作成・hrig起動・テスト/docs | Pluginsをplugins.pyへ分割。standard.ensure_node_pluginをPluginクラスメソッド、package._maya_yearをクラス内へ移動。versionsをutilsへ移し旧plugins関数公開を削除、呼出/規約/ガイド更新。Maya2022 plugin35件(2skip)+bulk4件・共通28件成功、2027 plugin35+bulk4件成功、reload旧名除去/構造/diff検証とSphinx -W成功。初回2027 flowWedgingはユーザーログ先へのsandbox書込拒否で失敗、旧実装でも再現し許可付き隔離mayapyで再検証成功。GUI未実施。証跡.maya-output/plugins-layout。 |
| Codex | 2026-09-27 | hlib/events・test_events | ScriptJobをscript_job.py、ScriptJobsをscript_jobs.pyへ分割し、__init__は再公開のみ。公開API維持。Maya2022共通28件成功、hlib.reload後のクラス再公開一致確認、diff check成功。GUI発火の再検証は未実施（実装本体変更なし）。 |
| Codex | 2026-09-27 | hlib/events・plug・Transform・hrig・AGENTS/docs・関連テスト | hrigの生成/属性/接続/行列をhlib公開APIへ移行。ScriptJob/ScriptJobs、hlib.plug、Plug.set_if_changedを共通化。行列適用の角度単位を修正。hrig本体の書式・日本語Google docstringを統一しdocs/hrig-development.mdとAGENTSへ規約追加。Maya2022共通28件、2025 native7件、2027 Bifrost統合15件、隔離GUI29項目成功。GUIはdirty化試験を含めexit0。Sphinx -W成功・diff check成功。2025GUI未実施。初期の親参照/rename戻り値の移行不備は修正して再検証済み。証跡.maya-output/hrig-hlib。 |
| Claude Code | 2026-09-27 | maya/inhouse/hedit/docs/(新規) | heditのSphinxドキュメント(利用ガイド・Preferences13項目の詳細・補完/出力/復元・開発)とスクリーンショット7枚(docs/tools/run_capture.pyで専用GUIから再撮影可)。Sphinx -W 警告0でビルド確認。hedit本体のソースは未編集。未コミット |
| Codex | 2026-09-27 | hrig/channel_controls・limb/animation・startup・demo・README・関連テスト・tools/run_hlib_gui_versions.py | modules_grp配下のMode/Lod/Match On Switch・レイヤーEnabled/Activeを標準チャンネルへ公開。GUI scriptJobで接続更新とUndo圧縮、読込/Undo後に再登録、無効状態グレー。FK合わせのxformワールド指定がRedoで崩れる問題をローカルTRS適用へ修正。2027 GUI23項目成功・画像確認、standalone15成功、2025 native7成功。終了直前にdirty化する試験でも専用GUIは保存確認なしexit0(.maya-output/rig-channels/gui-13)。終了時はdeferred内でmodified解除とquit forceを連続実行。普段のMayaは対象外。2025GUI・別プロセス初回起動での自動再登録は未検証。初期GUI試行の停止/失敗あり、最終版で正常終了。未コミット |
| Codex | 2026-09-27 | hrig naming/limb/reverse_foot/examples・README・テスト | RigNamingRule.maを読取参照しrig/geo_grp/jnt_grp/ctrl_grpとjnt/ctrl/ctrl_ofs/Shape命名を適用。モジュール/レイヤーDAG整理と階層化選択セット、setup非表示、整理group TRSロック。controlをゼロ化しローカルmatrixにoffset合成、FK/IKマッチ・足・backend交換を維持。2027 grouped15テスト、2025 native5、最終2027回帰10成功(exit0)。確認シーン.maya-output/rig-naming/hrig-demo.ma保存。GUI目視未実施、既存リグ自動移行なし、参照シーン/他作業変更なし。 |
| Claude Code | 2026-09-27 | hlib/plugins/{versions,module,package}.py(新規)・plugin.py・__init__・hlib/cmds/requirePlugins.py(新規)・hrig/startup/(新規)・maya/modules/hrig_startup.mod(新規)・関連テスト/docs | Maya 2025以降の起動時にBifrost 3.0.0以降を確認してロードし、無ければ警告ダイアログ。確認処理をhlibへ汎用化: Plugin.version_tuple/is_version_at_least、Module(登録モジュールの版)、PluginPackage(導入確認・ロード・警告)、hlib.requirePlugins。hrigのstartupはその薄いラッパー。2025/2026/2027のGUIで実機確認。 |
| Codex | 2026-09-27 | AGENTS.md・CLAUDE.md・.github/copilot-instructions.md・docs/aider-workflow.md・Ollamaモデル | ユーザー指示でAider委譲を停止、明示再開までOllama自動起動/ロードも禁止。qwen2.5-coder:32bをunload、API models空を確認。GPU空き22666 MiB。環境/モデルファイルは保持。文書差分確認、Maya実行なし。 |
| Codex | 2026-09-27 | docs/research/ollama-cuda-2026-09-27.md（Git対象外）・Ollama診断 | CUDA不正メモリアクセスはOllama llama-serverで発生。単体4k/11k各768トークン・Aider再試験1998トークン生成/一時ファイル編集は成功しCUDA未再現。GPU空き約1.2GB、同時Maya負荷との因果は未確定。Aider終了時の要約shutdown警告は別件。設定・ドライバー・製品コード非変更。 |
| Codex | 2026-09-27 | hrig（startup除外）・hlib_bifrost・hlib files/fbx・HIK5型/標準plugin生成管理・utils/evaluation・関連テスト/docs・tools/test_rig_packages.py | 検証版: 3関節FK/IK/Soft IK/補助骨、Bifrost/C++交換、LOD経路切断、リバースフット、proxyスキン、外部3骨FK/IKベイク。2027統合37成功・最終参照修正後14成功、2022関連22成功、2025 native5成功。C++2025/27ビルド・Sphinx -W成功、デモ保存成功。DG計測でSoft IK/補助骨の無効経路compute0、有効103。AiderはCUDA障害で中止し直接実装。GUI・実制作HIK retarget未検証。グラフUI/SplineIK/RBF/自動メッシュ削減/汎用増分構築は残件、docs/research/hrig-implementation-2026-09-27.mdに記録。別タスクstartup非変更、未コミット |
| Codex | 2026-09-27 | AGENTS.md・CLAUDE.md・.github/copilot-instructions.md・docs/aider-workflow.md | トークン削減が見込める場合のAider利用方針を共通化。対象限定・自動コミット無効・依頼元レビュー/検証・直接作業への切替を明記。参照先、ローカルCLI引数、差分確認済み。文書のみ、Aider/Maya再実行なし |
| Claude Code | 2026-09-27 | hlib(plugs・_core・nodes・cmds・selection・maths・json・docs)・CLAUDE/AGENTS/copilot | (1) maya.cmdsへの受け渡しを正式仕様化: Plug文字列を一意化(重複短名の不具合修正)、属性型判定をom2化(シーン変更・Mayaクラッシュ解消)、hlibコマンドがPlug/Component/MObject/MDagPath/MPlugを受付、cmds_interop.rst。(2) hlib.mathsをom2型継承に変更(Vector→MVector等、om2の演算意味論・可変・ハッシュ不可)。行列積約55µs→約1µs、get_matrix約7倍速。全版55ファイル成功。 |
| Codex + Aider | 2026-09-27 | maya/inhouse/hedit/scripts/hedit/docking.py | Aider実装後、Codexで重複importと再利用時の更新漏れを修正。既存__version__をドック/浮動タイトルへ表示。Python3.7構文・差分確認成功。Maya接続口なしでGUI未検証。Aider使用量4.0k入力/438出力(ローカルOllama)、自動コミットなし |
| Codex | 2026-09-27 | docs/research/mgear-custom-nodes.md | mGear公式FAQと専用ノード実装を調査。カプセル化・構築簡素化・性能・診断性の理由、IK/FK内部分岐と上流停止の違いを記録。外部コード非変更、Maya実行・計測なし |
| Codex | 2026-09-27 | docs/research/bifrost-rig-examples.md | ベルト・FABRIK・衝突変形・feedback・ML連動・追従チェーンの一次資料を調査しGit除外先へ保存。サンプル未実行、実装なし |
| Codex | 2026-09-27 | docs/research/bifrost-compatibility-2026-09-27.md | VNN Python APIを公式資料で確認。hlib設計規約を読み、任意依存の薄いBifrostラッパー案とhrigのMaya2025以降方針をローカル記録。実装なし |
| Codex | 2026-09-27 | docs/research/bifrost-compatibility-2026-09-27.md | 基礎ループと2.9以降の数学・Transform・キャッシュ機能の差を公式資料で確認し追記。実装・実機検証なし |
| Codex | 2026-09-27 | docs/research/bifrost-compatibility-2026-09-27.md | 公式リリースノートの提供対象・更新状況を調査してGit除外先に保存。実装・インストール・Maya実行なし |
| Codex | 2026-09-27 | maya/inhouse/hrig/ | モジュラーリギング用の最小パッケージ(__init__.py・README.md)を新設。既存PYTHONPATHを利用。Maya2027 mayapyでimport成功、差分チェック成功。Maya GUI未実行 |
| Claude Code | 2026-09-26 | maya/inhouse/hedit(旧HEditor)・maya/modules/hedit.mod・docs/cpp-documentation.md・CLAUDE/AGENTS/copilot-instructions・tools/build_maya_plugin.py | ユーザー指示でCodexの未コミット作業(HEditor→hedit改名・0.2.10・C++ドキュメント規約・--generate-only)をそのままコミット/push。事前に機密情報・第三者素材が無いことを確認 |
| Claude Code | 2026-09-26 | maya/modules(metahuman_for_maya.mod・pose_driver_connect.mod新設、Epic製.mod削除)・hlib/utils/{progress,optionvar,naming}.py・hlib/maths/easing.py・hlib/nodes/skinCluster.py・hlib/docs(conf.py・_static・_templates・rebuild.bat・README・development.rst)・tools/{check_hlib_docs,run_hlib_extension_gui}.py・hlib-docs.yml・HTools/rigging/{lib_/controllerShapeManager,controllerShapeManagerUI}.py・MayaCinematicCameraHUD・対応テスト・公開履歴 | 権利監査の指摘対応。第三者由来(Stack Overflow・maya-skinning-tools/Penner・cymel・paya・sphinx-autoapi・rig101・Maya devkitサンプル)のコードを独自設計で再実装し、APIを変更(progress_bar: label/width/stream、easing: ease()/CURVES、OptionVar: JSON保存・prefix必須、legalize_name: コロン区間ごと、controllerShapeManager: タブ/関数名変更)。mermaid同梱をやめjsDelivrの固定版+SRIに。Epic製.modを独自記述へ置換。公開履歴を書き換え(作者情報をnoreplyへ、調査資料・Epic .mod・mermaid・autoapiコピーを全コミットから削除)してforce push。各ツールは作業前に git fetch と reset/再clone が必要 |
| Codex | 2026-09-26 | hedit 単一画面/開き直し | 明示showで既存本文close→host非表示→同じhost再表示。取消時保持、workspaceControl非破棄で配置保持。reload時host保持/Qtツリーから回収、再入ガード、余分なhost非表示。GUI2027/2024各29成功(165032/165303)。3回連続・reload・参照消失後の同一host/未保存本文/可視host1個を検証。2024でcloseイベント3回も検証、Qt5テストの無効化ラッパーは再取得。README/構文/差分確認。Pythonのみ・再ビルド不要。今回2022/25/26のGUI再実行はなし。未プッシュ。 |
| Codex | 2026-09-26 | hedit 全版ビルド/自動ロード | 2022/24/25/26/27ビルド成功。startup.initializeでGUI時プラグイン自動ロード+メニュー、既存.mod/userSetupを利用。maya_core・永続autoload設定は非変更。全版GUI各28正常終了(164041/164229/164349/164459/164614)。単体22・移行1各版成功、standaloneロード解除各版成功(hedit-tests/164418)。旧offscreenテストがフォーカス不足で終了8→テスト側activate/focusを明示し全版0(hedit-ui-recheck/164907)。2022/Python3.7のSyntaxWarning差と旧configuration参照をテスト修正。2023未導入。GUIは隔離下で実userSetup明示実行、ユーザー外部ツール込みbat自体は未実行。README更新、未プッシュ。 |
| Codex | 2026-09-26 | hedit 名称統一 | maya/inhouse/HEditor→hedit、scripts/hedit、hedit.mod/mll/コマンド/C++名前空間/UI/テスト/READMEを変更。旧バイナリは.maya-output/hedit-legacy-binariesへ退避、配布は新名2版のみ。旧tabs/ui/preferencesを新保存先へ未存在時のみコピー、旧workspace uiScript専用heditor.restoreと旧control検出を保持。2024/27ビルド成功(既存マクロ警告)、GUI各27成功(154230/154328)。2027再起動3段階成功(hedit-startup/154417)。補完22+移行1テスト/26Python構文成功。旧ユーザー実環境からのドック移行、2022/25/26は未検証。未プッシュ。 |
| Codex | 2026-09-26 | HEditor 空画面復元修正 | 既存workspaceControlへの挿入後に親ホストもsetVisible(True)。復元先を生成前に確定、誤った親も再表示時に修復。専用reporter生成後にMayaのUI親を復元。再起動テストで従来の非表示ホストを検出し、親子関係/アクティブタブ可視を追加。2024/27の保存→再起動表示→閉じた状態の全6起動正常終了(heditor-startup/20260926_152032)、未保存Python/MEL・右ドック復元成功。2027画像確認。README/構文/差分確認。Pythonのみ変更・再ビルド不要、ユーザー設定非削除、未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.2.10 標準ログ表記 | Maya専用非表示reporterのQt文書追記を差分取得し、//・#・複数行・空行を標準通りに表示。種別通知で色/フィルタ維持、独自末尾//を廃止。専用文書5000行上限・接続解除/破棄を実装。2024/27ビルド成功(既存Qt/Mayaマクロ警告)。GUI各27項目正常終了(2027:151005、2024:151335)、読込中描画/色/解除含む。13種の標準文書完全一致:2024:151134、2027:151255。2027は5100行保持上限も成功。比較試験の初回タイマー未消化を有界一致待ちに修正。README・構文・差分確認。初回過去履歴の圧縮制約は従来通り。2022/25/26と実制作シーンは未検証、未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.2.9 読込中ログ | 25msタイマーだけでなくメインスレッドのMCommandMessage通知から最大40fpsでキュー取得/viewport再描画。mutex解放後に実行、再入防止、processEvents不使用、他スレッドは従来キュー。2024/27ビルド成功(Qt/Maya mathマクロ再定義警告あり)。GUI各27項目正常終了(2027:145134、2024:145422)、file openが戻る前の3行の本文更新とPaintを検証。2027はテスト用scriptNode、保存するテストはscriptNode不要のBeforeOpenコールバックへ変更して2024確認。READMEに他スレッド/末尾バッファの遅延制約を記載。ユーザーの実制作シーンは未検証。差分確認済み、未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.2.8 リアルタイム検索 | 検索欄textEditedで即時一致選択・件数更新。選択先頭を基準に絞込み、フォーカス維持、空欄/不一致/不正式を処理。Enter/F3は次一致を維持。2024/27ビルド成功。2027 GUI26項目正常終了(144210)、実キーh→hl→hli→hlib各段階の選択/件数/フォーカス、Enter、全削除、不一致と既存検索置換回帰成功。2024GUIは今回未実施。README/差分確認済み、未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.2.7 バー配置 | Output専用見出し/保存/クリアボタンと空欄プレースホルダーを削除、表示モードを上段アイコン直後へ移動(150px)。検索を470px、Tt/Abc/.*のフラット表示・左右矢印・小さい余白へ調整。従来のクリアメニュー/アイコン/右クリックは維持。2024/27ビルド成功、GUI各26項目正常終了(2027:143325、最終文字サイズ調整後2024:143458)。両版画像確認、検索/置換/モード/補完等回帰成功。READMEと差分確認済み、未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.2.6 Output・検索UI | Output右上にNormal/Output only/Warnings + Errors/Errors only、表示ログUTF-8保存、全モードクリアを追加。元ログ最大1Mi文字保持でモード復帰、Maya設定非変更。警告#ffff00/エラー#ff0000。検索を入力欄右上overlayへ移動、リサイズ追従、置換展開ボタン/既存検索機能維持。2024/27ビルド成功、GUI各26項目成功(2027:142204、2024:142309)、検索位置/モード復帰/保存一致/クリア/色/補完等を検証。2027画像目視。初回保存試験失敗はパスとQtダイアログ自動操作を修正。READMEに保持上限と初期履歴種別の制約を記載。差分確認済み、他ツール変更保持・未プッシュ。 |
| Codex | 2026-09-26 | HEditor サブパッケージ補完 | from . import nodesが静的解析で自己参照しhlib.nodes候補が空になる問題を修正。相対サブパッケージを直接解決、絶対再公開の自己参照を回避、TYPE_CHECKING宣言を非実行で解析。単体22件成功(別名import/未importパッケージ含む)。Maya2027 GUI24項目成功/正常終了(140437)、hlib.nodesのpopup表示とNode/Joint/SkinCluster/Transform候補を検証。Python補完のみ変更、C++再ビルド不要。差分確認済み、未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.2.5 Output・入力負荷 | 初期履歴で空行とprint断片の分断を再現。Qt文書も通知境界を含むため履歴専用の空行省略・空白通知接続を追加、ライブ空行保持。過去の任意断片/意図的空行の完全復元不可をREADME明記。補完のパス列挙を同一プロセスの背景スレッドへ移動(最短5秒)、宣言ASTキャッシュ/最大4再試行/20万文字制限、全モジュール属性の一括JSON廃止。C++で250ms debounce/全文コピー削減/入力停止1.5秒以後に復元保存。5000行構文未完成の旧相当解析1269ms→3.31ms。単体20件成功、2024/27ビルド成功。Output対象GUI2024:135222・2027:135127正常終了。最終2027:135502で遅い走査800ms注入時GUI最大timer間隔92ms、3項目成功/正常終了。初期Output画像確認。2027全体GUI23項目成功/正常終了(135548)。初回再現試験は失敗、134704は終了timeout所有PID停止。差分確認済み、他ツール変更保持・未プッシュ。 |
| Codex | 2026-09-26 | テスト時クラッシュ通知の切り分け | ユーザーがテスト中の通知と確認。通常TEMPのMayaCrashLog260926.1336/1337/1338.logはMaya2022 mayapyの終了処理(RtlExitUserProcess→DynSlice TnClothShape::sCleanupClass→属性解放)でのクラッシュ。正確な起動元・原因は未特定。HEditor対象GUIは2024/27で直近結果は正常終了、同一障害とは断定しない。調査時maya/mayapy稼働なし。既存hlibランナーはuninitialize・分離TEMP・timeout・終了コード判定あり、今回のログはその分離TEMP外。他ツール進行中の対応テストには変更せず、診断のみ共有。製品コード変更・追加Maya起動なし。 |
| Codex | 2026-09-26 | HEditor 0.2.4 Output/スペルチェック | 初期履歴をMayaのQt文書から読み余分な通知区切りを除去、CRLF正規化、分割printと意図した空行保持。Output標準12px/NoWrap、Preferencesで折返し切替、ASCIIタイトルと既存ドックlabel更新。Windows en-US辞書(COM)で表示範囲最大8000字・450ms debounce・語キャッシュ・camel/snake分割の青波線を追加、標準ON/設定保存/OFF取消。外部Python/辞書同梱なし、日本語校正/候補/ユーザー辞書未対応をREADME記載。2024/27ビルド成功、対象GUI成功・正常終了(2027:133258/11ms、2024:133350/16ms)、2027画像確認。2027全体GUI23項目正常終了(133446)、既存補完/ログ/コピー/実行/解除回帰成功。差分確認済み、他ツール変更保持・未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.2.3 補完/Output履歴 | 候補挿入中の再補完予約を抑止。初回にcmdScrollFieldReporterから最大512Ki文字のMaya保持履歴を取り込んでから購読開始、Result/Warning/Errorを//ラベル:本文//表記へ。2024/27ビルド成功、対象GUI各3項目成功(2027:123608、2024:123850):表示前履歴が1回、Result表記、hlib確定後Enter改行、次の補完。2027画像で起動ログ表示確認。両版終了60秒timeoutで所有PID監視停止、正常終了は未確認。全体GUI123113は120秒timeoutのため全体回帰成功とはしない。初期試験のMEL/API呼出を修正。READMEへ保持履歴/Charcoal独自ログの限界記載、構文/差分確認成功、未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.2.2 メニュー/ツールバー | テキストボタンをMaya同梱標準アイコンのツールバーへ変更。File/Edit/History/View/CommandのActionを共有し、開く/保存/クリア/表示切替/実行/Explorerを配置。入力消去はUndo可能、Refresh completionはCommandへ。Dark+維持。2024/27ビルド成功、GUI各21項目exit0(2027:114641、2024:114706)、2027画像で標準アイコン表示確認。入力消去Undo・表示切替と既存操作回帰成功。README/差分確認済み、未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.2.1 Output行番号 | Outputの行番号/余白を初期非表示、PreferencesのShow output line numbersで切替・保存。コード行番号維持。2024/27ビルド成功、2027 GUI20項目exit0(114351)、画像で非表示確認。設定数の既存テストを11へ更新。2024GUIは今回未実施。README更新、既存変更保持・未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.2.0・C++開発ガイド | 中断分を再開。Ctrl+G、正規表現キャプチャ置換、MEL実行/言語切替、Explorer/Open/Add Folder、タブスクロール、Windowメニュー、起動時開閉/ドック復元、アクティブPythonのみ解析を実装。VS生成バッチ/--generate-onlyを追加し生成物のGit除外確認。日本語DoxygenをHEditor C++全体へ追加、3種のエージェントMDと規約を更新。2024/27ビルド・各17単体/standalone/offscreen成功(111600)。最終GUI各20項目exit0(2024:113643、2027:113742)。Qt5で閉じたドック再生成時のクラッシュを遅延生成で修正、失敗試行の所有プロセスは監視停止。両版3プロセスの再起動試験成功(heditor-startup/113757):右ドック、未保存Python/MEL、閉じた状態を復元。通常userSetup自動呼出自体は未検証で同じinitializeを明示実行。Python21ファイル構文/差分確認成功。既存変更保持・未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.1.13行番号 | コード/出力の行番号をNumberedTextへ共通化、桁数・フォント・スクロールへ追従。本文とは別描画のためコピー対象外。2024/27ビルド成功、GUI各18項目exit0(2027:103059、2024:103254)、両版の画像で行番号表示を確認。選択/コピー/ズーム等の回帰成功、README更新、差分チェック成功。未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.1.12出力選択 | 読取専用Outputにマウス/キーボード選択とCopy/SelectAllのShortcutOverrideを明示。追記専用cursorと選択端点を分離、選択・スクロールを保持し非選択末尾時のみ追従。2024/27ビルド、GUI各18項目exit0(2027:102738、2024:102831)。ダブルクリック/Shift選択、Ctrl+C/A、日本語コピー、追記時選択保持、読取専用、過去ログ位置と末尾追従を確認。READMEと差分チェック成功。未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.1.11出力色 | 文字列判定をやめMCommandMessage種別を保持したキュー/文字書式へ変更。Warning黄・Error赤・Result緑・Info水色・History灰・Display明灰。複数行、通常色復帰、バッファ上限を維持。Qt5 QCharRef差を修正し2024/27ビルド成功。各17単体/standalone/offscreen成功(102339、結果/履歴/通常色fixture含む)、GUI各17項目exit0(2027:102403、2024:102456)、実Warning/Error/Info/printの色を検証、2027画像目視。通常printの文字列による推測はしない旨README記載。差分チェック成功。未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.1.10編集補助 | Aa/単語/正規表現検索・一致番号を追加。元テキストで一致を確定して後方から一括置換、1Undo。不正/ゼロ長/10万件超は変更前拒否、置換後方参照は非対応と明記。Viewの10〜28pxズーム/リセットとCtrl+=/-/0、ini保持を追加。2024/27ビルド成功、GUI各16項目exit0(2027:101834、2024:101932)。検索条件・折り返し・日本語置換・不正regex・Undo・倍率キーを検証、既存機能回帰成功。README更新、差分チェック成功。未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.1.9外観 | 全体の独自スタイルを除去しメニュー/タブ/ツールバー/ステータスをMaya標準へ。codeEditor/outputのみConsolas14pxとhlib Sphinx Dark+色へ限定、変数/クラスと出力警告/エラー色を追加。2024/27ビルド、GUI各15項目exit0(2027:101406、2024:101452)。両版maya-dark-plus.pngを目視確認、差分チェック成功。色分類は簡易構文解析で完全なPygments互換ではない。未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.1.8静的解析 | Maya同梱Pythonのcompileによる構文エラー/SyntaxWarning診断を追加(実行/importなし)。初期offの永続設定、800ms debounce、active tabだけ診断、off時取消、問題一覧クリックで行ジャンプ、100万文字超/2万行以上skip。型/未定義名/API検証は対象外とREADME明記。2024/27ビルド・各17単体/standalone/offscreen成功(100932)、GUI各15項目・exit0(2027:100956、2024:101049)。構文診断/修正/行移動、off時未呼出と待機取消を確認。差分チェック成功。未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.1.7補完・設定 | 補完要求ごとに対象のlive公開名とsys.pathを取得、既知ソースの変更を静的再解析、import候補の追加/削除追従。自動import/reloadなし。Edit/Preferencesに文字/ドット補完・keyword/builtin・smart indent・backspace・空白表示・保存時整形の9設定を追加しini永続化。2024/27ビルド、各13単体・standalone・offscreen成功(100515)。GUI各15項目・exit0(2027:100538、2024:100621)、設定切替・手動補完・整形Undo・ini保存を検証。比較メモはGit対象外docs/researchのみ、GUIでの外部製品操作は未実施。未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.1.6タブ復元 | Maya prefs/heditor/tabs.jsonへ1秒周期・終了通知・解除時にQSaveFileで保存。本文/パス/modified/選択/タブ順/active復元、元ファイル非更新。QLockFileで多重起動の上書き防止、不正ファイル保持と通知、保存不可時は従来の確認へ戻す。2024/27ビルド・独立GUIプロセス2回による保存/再起動復元各成功・exit0(heditor-session/095845)。初回試験はテスト側setPlainTextによるmodified解除を修正。2027既存GUI14項目成功・exit0(100036)。ロック競合/破損/ディスクエラーの実機注入は未検証。旧版から最初の更新時は手動保存が必要とREADME記載。未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.1.5部分実行 | Ctrl+Return/Ctrl+テンキーEnter/テンキーEnterをコード欄で直接処理。既存の選択のみ/未選択時全体実行を維持し、通常Enterは改行。READMEにCtrl+Lからの行実行・範囲保持・制限を追記。2024/2027ビルド成功、各GUI14項目・exit0(2024:095333、2027:095247)。実キーで実行回数・複数行選択・選択保持・全体実行・通常Enterを検証、既存補完/ログ/ドックも成功。差分チェック成功。他Maya版・標準エディタ全機能互換は未対応。未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.1.4ショートカット | VS Code系のコメント・行移動/複製/削除・インデント・行選択/コピー・Redo・検索置換・タブ操作・折り返し・保存/行ジャンプを追加。Ctrl+Enterは実行を維持。Ctrl+Wの受信と遅延破棄を調整。2024/27ビルド、各単体9件・standalone・offscreen成功(094937)、GUI各13項目成功・exit0(2024:094840、2027:095017)。実キー操作とテキストUndo確認。ファイル/行番号ダイアログ操作、他Maya版は未検証。READMEへ一覧と制限を記載、差分チェック成功。未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.1.3 UI・補完・ドッキング | 補完をMaya内の直接呼び出しへ変更しQProcess/JSONLワーカーを撤去、worker.pyをcompletion.pyへ整理。出力上・コード下、右クリックClear output、MayaQWidgetDockableMixinホストとworkspaceControl/uiScript復元を追加。Qt5のreparent時Pythonラッパー無効化に対応。2024/27ビルド、各unit9件・standalone・offscreen成功(093520)。GUI各12項目成功、両版exit0(2024:093749、2027:093827)。Maya再起動を跨ぐ編集タブ復元は未対応、同期補完中はMayaが待機する制限をREADMEへ記載。未プッシュ。 |
| Codex | 2026-09-26 | docs/research/ | 依頼された外部ツール調査を実施しGit対象外へ記録。製品コードの変更なし。 |
| Codex | 2026-09-26 | HEditor 0.1.2ログ共有・GUI検証再開 | コミット済み途中実装(Maya共通Python実行/MCommandMessage購読/UTF-8)を再起動後に検証。2027 GUI 092214・2024 GUI 092711で双方向ログ・変数共有・日本語・警告/例外・重複なし・補完/選択実行/アンロード計9項目成功、両版exit0。PySide2にqWaitがないテスト不具合をQEventLoopへ修正。Charcoal実機試験092439は未信頼プラグイン確認で停止とアクセシビリティから確認、設定を変更せず120秒監視で所有PIDのみ停止。連携未確認をREADMEに明記し未検証の試作テストは除去。今回追加分は未プッシュ。 |
| Claude Code | 2026-09-26 | pyrightconfig.json・tools/setup_maya_typings.py・.gitignore・hlib/__init__/cmds/nodes の TYPE_CHECKING・nodes/node.py・test_typing_exports.py・HTools controllerShapeManager・docs/vscode.md・CLAUDE/AGENTS/copilot-instructions | 静的解析エラーの調査と解消。原因: (1)maya.cmds/OpenMaya にスタブが無い、(2)hlib.createNode等が動的公開で名前解決できない、(3)Node.__getattr__がPlug推論でメソッド呼び出しが全て not callable、(4)extraPathsの欠落。types-maya配置・pyrightconfig集約・TYPE_CHECKING宣言と一致テスト追加で 3632件→エラー0(警告750)。HTools/rigging/lib_/controllerShapeManager.py の存在しない HTools.decorator import を hlib.decorators.undo へ修正。 |
| Claude Code | 2026-09-26 | maya/modules/hlib.mod・maya/external/mgear5・.gitmodules | hlib.modが inhouse/hlib をPYTHONPATHへ追加し標準jsonを隠していた問題を修正(hlib.jsonのloadsエラー)。mgear5をmasterの最新(5.3.5・Python 3.13対応)へ更新し、.gitmodulesのbranchをmasterへ変更。2027/2024のmayapyで import mgear と mgear.shifter.guide を確認。 |
| Codex | 2026-09-26 | HEditor 0.1.1自動補完修正 | 旧版GUIで新規タブcmds.の自動補完失敗を再現(064854)。ready後再要求、ロード済み名はディスク走査不要、常設状態表示を追加。連続更新時の候補モデル解放後参照も発見・再利用方式へ修正。テストexeのWERダイアログを出してしまったため所有テストPID停止、以後テストexeだけSetErrorModeで終了コード監視。使用中旧DLLを上書きしない版別0.1.1配置とmod/loader更新。2024/27各unit10件・standalone成功、最終C++5回連続候補更新テスト両版exit0。2027 GUIでCtrl+Spaceなしのcmds.自動表示・Enter確定等6項目成功(070108)、終了処理は60秒timeoutで所有PID停止。ユーザーMayaは保持。反映には保存後Maya再起動が必要、未プッシュ。 |
| Codex | 2026-09-26 | HEditor/tests/run_gui.py・gui_smoke.py・README | GUIテストのmodule pathをHEditorだけの一時modディレクトリに分離し起動停止を解消。GUI実機で表示/全体実行/候補表示/Enter確定/選択実行/close+unloadの6項目を2024・2027で成功、両方exit0正常終了（35.69秒・42.49秒）。画像も確認。2024: .maya-output/heditor-gui/20260926_063534、2027: 063644。終了停止があった先行回も隠さず、GUI結果と監視結果をrun-result.jsonに分離記録、timeout引数を追加。ユーザー設定・信頼設定・普段の全mod構成は変更なし。全外部ツール有効時の互換性・個別の停止原因までは未特定。未プッシュ。 |
| Codex | 2026-09-26 | maya/inhouse/HEditor・maya/modules/HEditor.mod | 独立したC++/Qtエディタ初期版を追加。VS Code風配色、タブ/行番号/UTF-8開閉保存/検索/選択実行/出力、ロード済み公開名＋別mayapyのstdlib AST補完（キャッシュ/要求統合/10秒timeout）。追加Python依存なし。2024/2027ビルド成功、各9ユニットテスト・standaloneでmod/ロード解除/実在名補完/実行・offscreenで補完挿入/実行/画像確認成功。最終フォント変更後も両UIテスト成功。結果 .maya-output/heditor-tests/20260926_062123。専用2027 GUIは制限環境exit251、通常環境もstartup120秒timeoutで所有プロセス停止、GUI内操作未確認。型推論/MEL等の制限をREADMEに記載。既存のClaude変更を保持、未プッシュ。 |
| Claude Code | 2026-09-26 | tools/run_hlib_gui_versions.py・docs/hlib-gui-testing.md | GUIテストの終了時セキュリティダイアログ(MASH userSetup.py)の原因を特定: 専用userPrefs.melにヘッダー(//Maya Preference行と optionVar -version 3)が無くMayaに無視され、SafeModeExecUserSetupScript=0が効いていなかった。ヘッダーを付与して解消(2022/2024/2025/2026は通常実行で、2027は単独実行でクリーン終了を確認)。終了待ち既定を120秒へ延長(Mayaのメモリ解放が遅く前バージョンの後始末と重なると60秒超)。 |
| Codex | 2026-09-25 | プラグイン開発基盤の情報取得 | CLAUDE/AGENTS・ビルド/devkitスクリプト・HUD CMake/.mod・VS Codeタスク・履歴を確認。--listでVS18(v142/v143/v145)と5版のMaya/devkit、2023未導入を確認。5版mll存在、HUD d5ec888でclean。記録上5版build/load済みだがbuild_maya_plugin.pyのVERIFIEDは2022/24/26のままという表示不整合を把握。今回は再ビルド・ロード・実装変更なし。 |
| Claude Code | 2026-09-25 | maya/inhouse/MayaCinematicCameraHUD(release/plug-ins/windows/2022・2024・2026) | ユーザー指示でコミット済みだった2022/2024/2026のmllを現在のソースから再ビルドし、HUDリポジトリへコミット・push。これで2022〜2027の全mllが同一ソース由来。警告0件、5版すべてmayapyでロード確認。親リポジトリのsubmodule参照も更新。 |
| Claude Code | 2026-09-25 | .gitignore・maya/inhouse/MayaCinematicCameraHUD/.gitignore, 全未コミット | C++プラグイン開発用に.gitignoreを整理(build_*/・.vs/・CMake/MSVC生成物・pdb等を除外。.mllはリリース物として無視しない。親リポジトリは.maya-output/で既にビルド/devkitを除外済み)。HUDリポジトリをコミット・push(652f21b: 警告修正・Qt6を2025以上・2025/2027ビルド追加・.gitignore)。親リポジトリは事前にrun_hlib_tests.py(新規mayapy 2027)全件成功を確認のうえ、Codexの未コミット分(hlib拡張・PoseDriverConnect mod等)も含めてコミット・push。|
| Claude Code | 2026-09-25 | maya/inhouse/MayaCinematicCameraHUD(src・CMakeLists.txt), maya/inhouse/HTools/system/checkWorkspacePluginTrust.py(新規), hlib/__tests__/test_htools_check_plugin_trust.py(新規), CLAUDE.md・AGENTS.md | ユーザー指示でHUDのコンパイル警告修正とセキュリティ警告対策。警告: Shift-JISだった4ファイルをUTF-8化(コメントのみ日本語で動作影響なし)、float→unsigned intを明示キャスト、CMakeにproject()追加・cmake_minimum_requiredを3.15へ・MSVCに/utf-8を明示(2022/2024の旧pluginEntryは/utf-8無しでC4819が出ていたため)。5版クリーンビルドでコンパイラ・CMake警告0件、各版mayapyでロード確認。セキュリティ警告: 信頼済みの場所(optionVar SafeModeAllowedlistPaths)はMayaのSafeModeがスクリプトからの変更を拒否する(追記の戻り値1・値不変・セキュリティログにreject/Deny)ことを隔離環境で確認したため、自動登録は不可と判断し迂回しない方針にした。代替として読み取り専用のHTools/system/checkWorkspacePluginTrust(inhouse配下の未登録場所を一覧しPreferencesを開く)を追加、登録手順(Preferences>Securityで手動、または警告ダイアログのApply to all plugins in this locationにチェック)をCLAUDE.mdに記載。テスト5件成功。HUD側は未コミット(CMake・ソース変更、2025/2027のmll新規)、コミット済み2022/2024/2026 mllは元に戻した。GUIでのPreferences画面表示・警告ダイアログの実挙動は未確認 |
| Codex | 2026-09-25 | PoseDriverConnect GUI/.mod検証補足 | 名前指定ロードはMetaHuman側の同名バイナリを選ぶことを確認。.modのmoduleInfoルートから対象バイナリを明示しロード元も検証するようGUIランナーを修正。standaloneで2022/24のPoseDriverConnect実バイナリ・専用取得を再確認、5版の.mod検出成功（.maya-output/mod-probe-20260925-explicit）。GUI未完了の結論は変更なし。 |
| Codex | 2026-09-25 | tools/run_hlib_extension_gui.py・GUIランナー・PoseDriverConnect.mod・README | 実.modを読む専用GUIスイートと起動診断ログを追加。Windows2024用PoseDriverConnect定義を補完。standaloneで2022/24/25/26/27の.mod検出、2022/24の名前指定プラグインロード・専用ノード取得成功（.maya-output/mod-probe-20260925）。GUIは全版試行、制限外でも再試行したがスイート開始前に停止。初回2022認証エラー、2026/27ライセンスセッション生成失敗、他は起動timeout。2024は認証通過後240秒timeout、GUI操作・画像検証未完了。全所有プロセス監視停止済み（extension-gui/20260925_225111・225310・225612・225716・225858）。監視5テスト・3.7構文・差分確認成功。既存Mayaと他ツールの変更を保持、未プッシュ。 |
| Claude Code | 2026-09-25 | tools/maya_devkit.py(新規), tools/build_maya_plugin.py, maya/modules/MayaCinematicCameraHUD.mod, CLAUDE.md, maya/inhouse/MayaCinematicCameraHUD/CMakeLists.txt | ユーザー指示で全Mayaバージョンのビルド環境を整備。Maya 2025/2027はdevkitが別配布だが、インストール先のヘッダ・lib・moc・Qt用zipから.maya-output/devkit/<年>/にローカルdevkitを自動生成する方式にした(Program Files非改変・管理者権限不要、Qt6のcmake設定が参照するbin/lib類は実物ハードリンク/空ダミーで充足)。Qt5系(2022/2024)は既存の展開済みインストール先を利用。HUDのCMakeをQt6判定を2025以上に修正。2022/2024/2025/2026/2027の5版で実ビルド成功、各版のmayapyで.mod経由のloadPlugin/unloadPlugin(ノード型CameraHud)を確認。Maya 2023は未インストールのため未対応。2025/2027のツールセット(v143/v145)は実ビルド・ロードで問題なしを確認。HUD側は未コミット(CMake修正・2025/2027のmll新規)、コミット済みの2022/2024/2026 mllは元に戻した。GUI Mayaでのロードは未確認 |
| Claude Code | 2026-09-25 | .gitmodules, maya/inhouse/MayaCinematicCameraHUD(新規submodule), tools/build_maya_plugin.py(新規), maya/modules/MayaCinematicCameraHUD.mod(新規), MayaHToolsWorkspace.code-workspace, CLAUDE.md・AGENTS.md・copilot-instructions.md | C++プラグインの編集・ビルド・ロード基盤をMayaCinematicCameraHUDで整備(hlib分離・補完エンジンは対象外)。HUDは編集対象のためinhouse配下にsubmodule追加(規則: 編集するもの=inhouse、使うだけ=external)。汎用ビルドスクリプトはvswhereでVS/CMake/ツールセットを自動検出し、ビルドフォルダを.maya-output/plugin-build配下に分離。Maya2026で実ビルド成功、.modのMAYA_PLUG_IN_PATH経由でmayapy 2026からloadPlugin/unloadPlugin(ノード型CameraHud)を確認。Maya2025/2027はdevkitが別配布のため環境変数MAYA_DEVKIT_<年>が必要。HUD側CMakeLists.txtの出力先(../release→ソース基準、/pdb→ビルド基準)を修正(HUDリポジトリ内で未コミット)。VS Codeにビルドタスクと簡易IntelliSense設定を追加。Maya GUIでのロードは未確認(信頼警告のため) |
| Codex | 2026-09-25 | hlib.extensions・hlib_posedriverconnect・mod・テスト・文書 | hlib_*自動検出、API宣言/依存確認、衝突時の拡張単位拒否、状態照会、reload対応を追加。専用scripts配置で.mod有効化、UERBFSolverNode/UEPoseBlenderNodeとUndo対応set_radiusを実装。2022/24/25/26/27各50ファイル成功（20260925_224543_566503）、2022/24は実外部プラグインで取得/Undo/Redo/reload成功。2025〜27はsix未導入のエラー隔離確認後、実ノード試験スキップ（対応バイナリも未配置）。コマンド検出単体・Sphinx -W・差分確認成功。GUI/.mod起動経路は未検証・未プッシュ。外部ソース変更なし。 |
| Claude Code | 2026-09-25 | リポジトリ全体(未コミット約110ファイル) | ユーザー指示で未コミット分(Codexの命名規則リファクタ・delete_constraints等を含む)をまとめてコミット・プッシュ。事前にrun_all_tests.pyを実行し49ファイル中48成功。test_datatypes.pyのみ失敗したが、Maya常駐セッションに残った旧`hlib_math_test`モジュールキャッシュが原因で、sys.modulesから除去して再実行すると32件全成功(コード側の問題なし)。 |
| Codex | 2026-09-25 | Transform・test_shapes_constraints・guide_nodes | delete_constraints追加。入力側constraintと経由pairBlendのみ削除、共有出力/参照/ノードロックを事前拒否。4ケースで直接接続・pairBlend・animCurve保持・拘束先保持・共有拒否・Undo/Redoを確認。2022/24/25/26/27各48ファイル成功（20260925_140508_081652）、Sphinx -Wと差分確認成功。姿勢維持/再接続なしを明記。GUI未実行・未プッシュ。 |
| Codex | 2026-09-25 | docs/hlib-api-design.md | パッケージ・Mayaコマンド・ノードファイル・その他ファイル・クラス・独自メソッドの命名規則と例を表で明文化。内容・差分確認済み。Markdownのみ、Maya実行不要・未プッシュ。 |
| Codex | 2026-09-25 | SkinClusters・テスト・Sphinx | remove_jointsをjointノードを残すinfluence解除として追加。remove_influences共通化、祖先移送/標準再配分/全解除の事前拒否、対象skin限定とUndo/Redoを検証。2022/24/25/26/27各48ファイル成功（.maya-output/version-tests/20260925_134157_977670）、Sphinx -W成功、差分確認成功。GUI未実行・未プッシュ。 |
| Codex | 2026-09-25 | docs/hlib-api-design.md・3種のAI作業ガイド | Maya照会はメソッド、保持値はプロパティの基準を具体例・キャッシュ/数学型/Plug属性アクセスの判断とともに明文化。AGENTS/CLAUDE/Copilotに同一文言で参照を追記。Markdown差分と参照先を確認。コード変更なし・Maya再テスト不要・未プッシュ。 |
| Codex | 2026-09-25 | hlib命名・公開API整理 | inputsの継承衝突解消、Joint親子名の明示、SkinClusters削除処理を_core内部へ分離、compose統合、release_srt改名、照会propertyをmethodへ変更、座標API整理、Translation/EulerRotation/NurbsCurveSnapshotとsnake_caseモジュールへ統一。呼出・例・移行表更新、旧名reload残存を解消。2022/24/25/26/27各47ファイル成功（.maya-output/version-tests/20260925_133409_544757）、コマンド自動登録検証とSphinx -Wクリーンビルド成功、公開例90ブロック構文確認。GUI2024は15件成功・終了15秒timeoutで所有プロセス停止、2022ライセンスエラー、2025起動180秒timeout、2026/27はGUI開始前終了。2023未導入、GUI画像の全数目視未実施。未プッシュ、既存変更を保持。 |
| Codex | 2026-09-25 | hlib全体・命名レビュー | Python定義を静的走査し、継承で意味が変わるinputs、SkinClustersの削除責務、Joint親子の名前返却、compose/release_srt、取得名/プロパティ/モジュールの揺れを確認。実装変更なし、Mayaテスト未実施。既存未コミット変更を保持。 |
| Codex | 2026-09-25 | hlibフラグ別名・属性別名ガイド | Mayaのコマンド別helpを初回のみ取得して8コマンドの短名を長名へ正規化。constraint/add_constraintはtyp/mo対応、bulk事前検査も対応。二重指定は本体実行前にTypeError。lsのtypでも専用コレクションを維持。標準/ユーザー定義属性の長短名を回帰検証。2022/24/25/26/27各46ファイル成功、コマンド自動登録単体検証成功、Sphinx -W成功。2023未導入・GUI未実施・未プッシュ。 |
| Codex | 2026-09-25 | hlib docstring・Sphinx全体見直し | 835関数の引数構造とArgs記載を走査、公開29ページと117コードブロックを構文確認。ベイク既定値/短縮フラグ、fastとUndo、単位、Quaternion.inverse、SDK実装済み案内、スキン復元制限、同名ノード/配列編集例、コマンド/JSON詳細を修正。主要9ガイド36例はMaya2022/2027で成功（必要な既存ノードをテスト用に用意）。28Pythonファイルはdocstring除外AST一致で動作変更なし。Sphinx -W成功、git diff --check成功。GUI/全例の副作用を伴う実行は未実施、未プッシュ。 |
| Codex | 2026-09-25 | 未コミット変更全体の公開 | ユーザー依頼でJoint回転移送/フリーズ・fastモード・viewport_offとベイク適用・テスト・ドキュメントをまとめてコミットしmainへpushする。各実装時の検証結果を引き継ぎ、差分チェック成功。 |
| Codex | 2026-09-25 | decorators/viewport・bakeResults・テスト・docs | viewport_off()をcontextmanagerで公開しbakeResultsへ適用。既存Viewport.suspendのmanage方式を再利用、batchはno-op、入れ子/元非表示/例外伝播と再実行なし。通常テスト2022/2027各45ファイル成功。2027 GUI15件成功・cleanup成功、終了は15秒timeoutで所有プロセス停止（正常終了ではない）。Sphinx -W成功。GUI画像の目視レビューは未実施。未プッシュ。 |
| Codex | 2026-09-25 | hlib値更新API・fastモード・テスト・docs | 対応するPlug/Transform/Joint/座標/色/utility/skin値更新にfast=False追加。TrueはOpenMaya直接更新でUndoなし、既存Undo設定維持。skinは未指定ウェイトを保つMPlug方式。形状は入力履歴・周期カーブを拒否。範囲/ロック/接続検査。全44ファイルが2022/24/25/26/27で成功（2023未導入）、追加8テストで値・単位・Undo履歴・bulk・API専用経路・疎なinfluence検証。Sphinx -W成功。3721頂点参考計測0.419秒→0.047秒。GUI未実行・未プッシュ。 |
| Codex | 2026-09-25 | joint.py・test_joint_orient_to_rotate.py・guide_rigging | Joint/Joints.freeze_rotation追加。R*JOをXYZのJOへ合成してrotateを0化、逆方向と検証/計算を共通化。6回転順序/2角度単位/SSC/負スケール/rotateAxisと、スキニング3方式×単体/複数でメッシュ・matrix・ウェイト・bindPreMatrix保持とUndo/Redo確認。2022/24/25/26/27全43ファイル成功、Sphinx警告なし。GUI未実行・未プッシュ。 |
| Codex | 2026-09-25 | joint.py・test_joint_orient_to_rotate.py・guide_rigging | Joint/Joints.joint_orient_to_rotate追加。R*JO合成、JOはXYZ固定・rotateOrder/角度単位対応。全対象のロック/入力接続を事前検証、姿勢と子のworld matrix保持、Undo/Redo対応。新規4テスト（6回転順序×2単位×SSC有無含む）、2022/24/25/26/27全43ファイル成功。Sphinx警告なし。GUI未実行、未プッシュ。 |
| Codex | 2026-09-25 | tools/GUIプロセス監視・検証済み変更の公開 | 起動/テスト/終了を外部監視し、終了待ち15秒で所有PIDと子のみ停止。途中例外時も後始末。専用prefsでuserSetup実行禁止、使い捨てシーンのmodified解除とMEL終了。監視実プロセステスト5件をPython3.7/3.13で成功。通常テスト各42ファイル・GUI各14件が2022/24/25/26/27で成功。最新GUI2022正常終了、24/25/26/27は終了timeoutの自動停止確認（ダイアログ完全抑止とは区別）。結果 .maya-output/gui-version-tests/20260925_085220_956484。Sphinx警告なし。ChannelBox等の画像/手動操作未確認、2023未導入。途中の手動クリック回は無人終了の証拠にしない。 |
| Codex | 2026-09-25 | tools/run_hlib_gui_versions.py・run_hlib_gui_tests.py・docs/hlib-gui-testing.md | 2022/2024/2025/2026/2027の通常テスト各42ファイル＋コマンド登録独立テスト成功。専用GUI起動ランナー追加、各14件成功・cleanup成功、各11画像で色/Undo/Redo/表示/CV選択確認。2023未導入。制限環境のライセンス起動失敗は通常環境で再実行。2024/2025/2027はテスト終了後のMaya終了が180秒timeout、専用プロセス停止（2022/2026正常終了）。ChannelBox画像・階層・通知・マウス操作等は未確認。集約結果 .maya-output/test-review-20260925.md。Python3.7構文確認。未プッシュ |
| Claude Code | 2026-09-25 | .gitmodules, maya/external/tqdm・tabulate・natsort(新規submodule), maya/modules_disabled/rich.mod・pyyaml.mod・tqdm.mod・tabulate.mod・natsort.mod(新規), CLAUDE.md | ユーザー指示で汎用Pythonライブラリ3件(tqdm、tabulate、natsort)をGit submoduleとして追加。前回追加のrich/pyyaml含め計5件について、既存の`maya/modules_disabled/`規約(未登録.modの置き場、有効化にはmodules/へ移動)に沿った`.mod`を用意(2022/2024/2025/2026/2027の各MAYAVERSIONブロック)。pyyamlはトップレベルの`yaml/`がCython版ソースで実体は`lib/yaml`だったため、PYTHONPATHを`./lib`に設定(setup.pyのpackage_dirと一致確認)。5件とも実際にsys.pathへ追加してimport成功をMaya実機で確認。CLAUDE.mdのディレクトリ構成図にmodules_disabled/を追記、外部ツール一覧を37個に更新。未コミット・未プッシュ |
| Codex | 2026-09-25 | nodes/skinCluster.py・joint.py・test_skin_weight_editing.py・guide_deformers.rst | 親へ加算してinfluence登録のみ除去、Joint.remove_influence、normalize_weights(decimals)、max_influences/set_max_influences(prune)追加。正規化OFFでも親の既存値へ加算。ロック・ゼロ合計等を事前検証、独自プラグインなし・Undo対応。Maya2022/2027一括成功（新規7ケース含む）、Sphinx警告なし。GUI未実行・未プッシュ |
| Codex | 2026-09-25 | nodes/joint.py・test_joint_delete.py | Joint.deleteを追加しJoints.deleteへ委譲。無効jointは例外。単複両入口の未スキニング・標準削除比較・親influence移送・子再親付け・Undo/Redo・失敗伝播を11件で確認。Maya2027全41ファイル成功、Sphinx警告なし。GUI未実行・未プッシュ |
| Claude Code | 2026-09-25 | .gitmodules, maya/external/rich(新規submodule), maya/external/pyyaml(新規submodule), CLAUDE.md | ユーザー指示により汎用Pythonライブラリ2件をGit submoduleとして追加(rich: Textualize/rich、pyyaml: yaml/pyyaml、いずれも直近タグ)。指示通り`maya/modules/`への`.mod`登録は行わず、起動時の自動ロード対象外のまま。CLAUDE.mdの外部ツール一覧(32→34個)に新カテゴリ「汎用Pythonライブラリ」として追記。未コミット・未プッシュ |
| Codex | 2026-09-25 | json/_editor_command.py削除・json/editors.py・JSON/Undoテスト・docs/json.rst | 独自プラグインを撤去。EditorSnapshotは保存・読込・比較のみ、applyは変更前にNotImplementedError。既存プラグインは自動アンロードしない。Maya2022の範囲Undoテスト2件をネイティブ非Undo仕様へ更新。Maya2022/2027の全41ファイル成功、Sphinx警告なし、hlib Python内のMFnPlugin/MPxCommand/MPxNode実装残存なし。GUI未実行・未プッシュ |
| Codex | 2026-09-25 | AGENTS.md・CLAUDE.md・copilot-instructions.md | 内部Mayaプラグイン禁止方針を同一文言へ統一。Undo目的も禁止、既存実装も解消対象、既存プラグインの管理APIとは区別。JSONの_editor_command.pyは残存を確認。文書のみ変更・差分確認、未プッシュ |
| Claude Code | 2026-09-25 | _core/type_hierarchy.py(新規), _core/registry.py, _core/bootstrap.py, _core/_playback_range_command.py(削除), editors/timeSlider.py, __tests__/test_registry.py・test_node_creation.py, docs/development.rst, docs/hlib-testing.md, CLAUDE.md, AGENTS.md, .github/copilot-instructions.md | cymel比較調査の残り2項目のうち、ノードタイプ継承キャッシュ(isDerivedNodeType相当)を実装。NodeRegistryにresolve_inherited_types(nodeレジストリのみ有効、plugレジストリは従来通り完全一致のみ)を追加し、完全一致が無い場合はcmds.nodeType(inherited=True)をキャッシュした継承チェーンを辿って最も近い登録済み祖先型のクラスを返す。組み込みairFieldノード(hlib未登録、transformを継承)がTransformで解決されることを実機確認。ユーザー指示により、唯一のカスタムMPxCommandだった_PlaybackRangeCommand(Maya2022のplaybackOptions非Undo対策)を削除し、hlib内で独自Mayaプラグインを用意しない方針をdevelopment.rst/CLAUDE.md/AGENTS.md/copilot-instructions.mdに明文化(理由: 初回ロード時のMaya「信頼されていない場所からのロード」警告が送信実行を止めるため)。Maya2022でのplaybackOptions変更は今後Undo非対応のまま(ネイティブ制限として文書化)。もう1項目(汎用Undo対応MPxCommand基盤)は上記方針と矛盾するため実装せず。run_all_tests.py 41ファイル中40成功(test_json.pyはCodex側未完成コードで対象外)、Sphinx `-W --keep-going`で警告ゼロ。**注意**: hlib/json/_editor_command.py(Codex進行中)も独自MPxCommandプラグインを登録しており、今回の方針と矛盾する。Codexへの反映要否はユーザー判断待ち |
| Codex | 2026-09-25 | 全変更の公開準備 | 既存実装・JSON・GUI検証基盤・ドキュメントをまとめてコミット。調査資料と生成物は除外し、研究専用の作業ログはローカル保存。 |
| Claude Code | 2026-09-25 | plugs/plug.py, nodes/reference.py, files/scene.py, files/references.py, namespaces/namespace.py, maths/quaternion.py, maths/eulerRotation.py, decorators/undo.py・__init__.py, utils/optionvar.py(新規), __tests__/test_*(新規・追加多数), docs/development.rst | 共通APIの8項目を実装。Plugの配列setAttr(scalar/length-prefixed型判定)、force接続時の一時アンロック、Reference Edits照会(edit_strings/edit_nodes/edit_attrs)・ネスト参照階層(children/root/is_root)・シーンimport(Scene.import_file)・新規reference作成(create_reference、ネスト参照混入を除外して特定)、カレントネームスペース(current/set_as_current/as_currentコンテキスト)、optionVar永続設定ラッパー(OptionVar、NUL文字はMEL文字列で切れるため専用トークンで回避)、例外時自動ロールバックのundo_transaction(空チャンクのままcmds.undo()すると無関係な直前操作を巻き戻すMaya既定挙動をダミーノード作成/削除のガードで回避)、Quaternion.to_euler()の全6回転順序対応(行列経由・ジンバルロック分岐込み、sympyで機械的に導出しom2と往復検証)、Quaternion.to_swing_twist()によるボーン曲げ/捻り分解。副産物として、EulerRotation.to_quaternion()の汎用フォールバック(xyz以外の5順序)が軸合成方向を逆に実装していた既存バグを発見・修正(xyzだけ別の閉形式式で元々正しかったため顕在化していなかった)。全項目Maya実機(om2比較含む)でテスト済み、run_all_tests.py 41ファイル中40成功(test_json.pyはCodex側未完成コードで対象外)、Sphinx `-W --keep-going`で警告ゼロ |
| Codex | 2026-09-25 | hlib/json・__init__.py・test_json.py・docs/json.rst | 型付きJSON/一時・置換保存/参照解決/事前計画/選択・属性・ポーズ・カーブ・スキン・AnimCurve・既存SDK・Editor Snapshotを追加。既存対象更新、Undo必須、単位・接続・トポロジー不一致拒否。Maya2022/24/25/26/27でJSON各14件成功+GUI1skip、2027全41ファイル成功、Sphinx警告なし。GUI送信は300秒timeoutで未確認・自動再送なし（Maya側は未キャンセル）。外部調査ログ非公開、未プッシュ |
| Codex | 2026-09-25 | tools/run_hlib_gui_tests.py・test_hlib_gui.py・docs/hlib-gui-testing.md・test_channel_box.py | GUI対象一覧と遅延実行・最終結果待機・画像保存を整備。Channel BoxのGUIテストを専用ランナーへ移管。Maya2027で13件成功、別途属性解決2件成功。色/Undo/Redo/カーブ表示/CV選択は画像確認。Channel Box画像・階層展開・通知・マウス操作・他バージョンGUIは未確認として手順化。結果 .maya-output/gui-tests/20260925_044055_827776、削除処理成功。未プッシュ |
| Codex | 2026-09-25 | Maya2027 GUI・.maya-output/gui_colors | 専用Outliner/ビューポートで赤インデックス13・RGBシアン/オレンジと文字色を描画画像で確認。解除→Undo復元→Redo解除も画像確認。Qtウィンドウ取得ではGPU部が空になるためM3dView描画バッファを別保存。検証ノード/ウィンドウを削除し選択を復元。既存シーン保存・新規化なし、検証操作はUndo履歴に残る。他バージョンGUI未検証 |
| Claude Code | 2026-09-25 | components/component.py, point_component.py, maths/matrix.py, nodes/constraint.py, nodes/node.py, nodes/skinCluster.py, namespaces/namespace.py, cmds/setKeyframe.py, cmds/select.py, cmds/outliner.py, cmds/viewport.py, editors/_editor.py, selection.py | hlib全体(nodes/plugs/components/maths/files/namespaces/plugins/editors/decorators/cmds/utils/_core)のdocstringを5並列agentで実装と突き合わせ監査、実際に食い違っていた14箇所を修正(主にRaises記載漏れ、move_attributeの説明範囲誤り、「scene.namespace」という旧パッケージ名を指す誤ったコメント3箇所、Selectionの重複排除の未記載)。run_all_tests.py 40ファイル中39成功(既知の無関係な失敗のみ)、Sphinx `-W --keep-going`で警告ゼロ |
| Claude Code | 2026-09-25 | nodes/animCurve.py（読み取りのみ、Maya実機検証） | 前タスクで疑ったAnimCurve.infinity()/set_infinity()の数値マッピング(値2欠番)を調査した結果、誤検知と判明。Mayaのpre/postInfinity属性自体が`attributeQuery(listEnum=True)`で`Cycle=3`と明示的に2を欠番にしたenumであることを実機のsetAttr/getAttr往復で確認。hlibの既存実装は実際のMaya enumと完全一致しており修正不要。コード変更なし |
| Codex | 2026-09-24 | nodes/skinCluster.py・node.py・test_influences_colors.py・docs | add_influencesをウェイト0・重複除外・全対象事前検査で追加。Outliner RGB、overrideインデックス/RGB/無効化・取得をNodeに追加、Undo対応。正規化3モード×最大influence制限有無で非正規化を含む既存rawウェイト保持を検証。2022/2024/2025/2026/2027各39ファイル成功（.maya-output/version-tests/20260924_234032_392735）、Sphinx警告なし。2023未導入、GUIの色表示は未検証・未プッシュ |
| Codex | 2026-09-24 | editors/timeSlider.py・_core/_playback_range_command.py・nodes/transform.py・test_version_compatibility.py・docs/hlib-testing.md | 2022のplaybackOptions非Undoをcmds実行専用MPxCommandで補完。同一親/既にworldの非インスタンス親変更をno-op化、無効ノードの例外維持。2024以降も再生範囲の自動拡張を明示編集してUndo復元。reload後Undo・Redo・親変更回帰テスト追加。2022/2024/2025/2026/2027各38ファイル成功、2023未導入。結果.maya-output/version-tests/20260924_233304_782360。Sphinx警告なし、GUI除外・未プッシュ |
| Codex | 2026-09-24 | tools/run_hlib_tests.py/.bat・test_run_hlib_tests.py・docs/hlib-testing.md・README.md | Maya2022～2027を個別/一括mayapy実行する環境を追加。ユーザー設定分離・英語固定・実バージョン照合・タイムアウト・結果JSON/ログ保存。ランナー4テスト成功。実行結果:2025/2026/2027各37ファイル成功、2022はedit_undo/shapes_constraints失敗、2024はshapes_constraints失敗、2023未インストール。詳細.maya-output/version-tests/20260924_232219_690401。GUI/外部投稿等の除外は明記。hlib互換性修正は未実施・未プッシュ |
| Codex | 2026-09-24 | nodes/blendColors.py・test_blend_colors.py・docs/blend_colors.rst・usage.rst | BlendColorsを自動登録。入力色/補間係数の設定・Plug接続・出力取得を追加。Maya2027 standalone37ファイル失敗なし（新規3件で補間・Undo/Redo・接続置換・不正値検証、GUI専用1ファイル除外・1件スキップ）、Sphinx警告なし。GUI未検証・未プッシュ |
| Codex | 2026-09-24 | animation/・cmds/drivenKey.py・test_driven_key.py・docs/driven_keys.rst・usage.rst | DrivenKey/DrivenKeysとhlib.drivenKeyを追加。関係取得・カーブ照会・キー設定・駆動先からの検索・一括編集に対応。単位変換とblendWeightedの入力を走査、未知の接続編集は拒否。キー更新後の評価キャッシュをdgdirtyで更新。Maya2027 standalone36ファイル失敗なし（新規5件、GUI専用1ファイル除外・1件スキップ）、Sphinx警告なし。GUI未検証・未プッシュ |
| Codex | 2026-09-24 | nodes/skinCluster.py・test_dag_pose.py・docs/dag_pose.rst | ユーザー指示でbind_pose/restore_bind_pose/reset_bind_poseを追加。復元は全メンバー、更新は当該influenceのみ、bindPreMatrix不変。SkinClusters自動転送・Undo/Redo・未接続例外・更新範囲を検証。Maya2027 standalone35ファイル失敗なし（GUI専用1ファイル除外・1件スキップ）、Sphinx警告なし。GUI未検証・未プッシュ |
| Codex | 2026-09-24 | nodes/dagPose.py・test_dag_pose.py・docs/dag_pose.rst・usage.rst | DagPoseの保存/復元/更新・メンバー編集・行列照会・skinCluster接続照会を追加。既存skinCluster.pyは競合回避で編集せず、取得はDagPose.from_skin_clusterで提供。Maya標準のRedo時名前空間脱落をrename分離で回避。Maya2027 standalone35ファイル失敗なし（DagPose7件成功、GUI専用1ファイル除外・1件スキップ）、Sphinx警告なし。GUI未検証・未プッシュ |
| Codex | 2026-09-24 | .github/workflows/hlib-docs.yml, tools/check_hlib_docs.py, tools/docs-browser-requirements.txt, hlib/docs/_static/custom.css | 公開前後のChromiumテスト(PC/モバイル各4ケース)、コミット・HTML/JS/CSSハッシュ確認、失敗注記・画面・trace保存を追加。実検証で見つかったモバイル固定幅によるクリックずれを修正。187c1a4のActions run 36007110999でbuild/deploy/verify-publication全成功。認証情報の取得は承認審査拒否で未実行、公開APIの注記で診断完了 |
| Codex | 2026-09-24 | hlib/docs/_mermaid_classes.py・class.rst | 各クラス継承図と全体図へ相対リンク追加。85クラス・332リンクのHTMLとアンカー検証、Sphinx警告なし。外部クラスにはリンクを生成しない。実ブラウザでのクリック未検証 |
| Codex | 2026-09-24 | hlib/docs/getting_started.rst, guide_*.rst, usage.rst, index.rst | 入門を92行に縮小、詳細を11ページへ分割。36節・Python39例を保持して機能別ガイドへ整理。Sphinx警告なし・差分検査済み。コード変更なし、Maya再実行なし |
| Codex | 2026-09-24 | hlib/docs/installation.rst | 指定された閲覧・自動公開・手動再公開の3節を削除。Sphinx警告なし、生成HTMLから削除を確認。公開ワークフロー自体は変更なし |
| Codex | 2026-09-24 | hlib/docs/common_methods.rst, index.rst, matrices.rst | 共通処理ページ自体を削除、目次・関連リンクも除去。クリーンビルド警告なし、旧HTML・検索項目が残らないことを確認 |
| Codex | 2026-09-24 | .gitignore・公開ドキュメント・作業ガイド | 調査資料をローカル保持しGit追跡・Sphinx公開から除外。使用方法の説明は保持。再登録防止ルール追加、クリーンビルド警告なし・検索とダウンロード非掲載確認。履歴書換えなし |
| Codex | 2026-09-24 | hlib/docs/conf.py | docs補助モジュールの検索パスを明示。GitHub Pagesと同じルート起点のSphinx -E -a -Wビルド成功。行列ガイド・継承図は8df225bでorigin/mainへpush済み、この修正も追送 |
| Codex | 2026-09-24 | hlib/docs, Git | 行列ガイド・各クラス継承図更新をコミット対象に集約。Sphinx警告なし・差分検査済み、origin/mainと同期確認。ユーザー指示により本コミットをpushする |
| Codex | 2026-09-24 | hlib/docs/_mermaid_classes.py, _templates/autoapi/python/class.rst | 既存継承図に見出し・矢印説明と直接派生クラスを追加。全85クラスHTMLとAnimCurve8派生・Joint祖先を検証、Sphinx警告なし。ブラウザのfile URLはポリシー拒否のため描画未検証。未プッシュ |
| Codex | 2026-09-24 | hlib/docs/matrices.rst, index.rst, getting_started.rst | 行列取得・Plug・合成分解・積と逆行列・座標変換・適用・API変換のガイド追加。Maya2027 standaloneで掲載8ブロックと数値結果・Undo確認、Sphinx警告なし。GUI未検証・未プッシュ |
| Codex | 2026-09-24 | hlib/docs, nodes/node.py, cmds/setKeyframe.py | 使用例をplug()に統一、attr()説明はplugへの互換参照に集約。Nodeのdocstring除外AST一致、Sphinx警告なしで再ビルド。処理変更なし・Maya未実行。未コミット |
| Claude Code | 2026-09-24 | maya/inhouse/hlib/docs/conf.py, _mermaid_classes.py(新規), _templates/autoapi/python/class.rst, development.rst, _static/mermaid.min.js・mermaid.css・mermaid-init.js(新規), .claude/launch.json(新規), .gitignore | 各クラスページに継承チェーンのMermaid図を追加(astのみで静的解析、hlib/Mayaはimportしない)。development.rstに全85クラスの全体クラス図を追加(サブパッケージ単位でnamespace分け)。ベースクラスへのリンクは既存のlink_objsをそのまま使用(図自体はクリック不可、視覚的な補助)。mermaid.jsは_staticにバンドルしCDN依存なし。classDiagramのclassDef複数プロパティがパースエラーになる不具合を回避、SVGサイズがコンテナ幅に潰れる問題をJSで実サイズ指定して解決。Sphinx `-W --keep-going`で警告ゼロを確認、ローカルhttpサーバー+ブラウザでMermaid実描画(テキストラベル・寸法)を確認 |
| Claude Code | 2026-09-24 | maya/inhouse/hlib/docs/_templates/autoapi/python/class.rst | 「ベースクラス:」行が常にプレーンテキスト`:py:obj:\`...\`` のまま表示され、実際にはリンクになっていなかった既存バグを修正(自分の直前作業でraw::htmlブロックに適用したのと同じ原因: `.. py:class::` 直後の空白テンプレート行がJinjaのtrim_blocksで消費され、後続の「ベースクラス:」行がシグネチャの続きとして誤認識され、role記法が一切解決されていなかった)。obj.bases if-block内に明示的な空白行を追加して修正。Joint等で実際にクリック可能なリンク(`<a href="../transform/Transform.html#...">`)になることをブラウザで確認、bases無し/外部クラス(logging.Handler)のケースも回帰なし、Sphinx `-W --keep-going`で警告ゼロ |
| Codex | 2026-09-24 | hlib/_core/collection.py, nodes/joint.py, nodes/skinCluster.py, plugins/plugin.py, __tests__/test_bulk_collections.py, docs/bulk_collections.rst, docs/index.rst | Joints/SkinClusters/Pluginsに単体公開APIの同名一括呼び出し、読取プロパティ列、call_each・sliceを追加。固有メソッド維持。dump/load_weightsは要素別パス指定のみ。Maya2027 standalone317成功・GUI1件スキップ、Sphinx警告なし。Pluginロードはmock境界検証。未コミット |
| Codex | 2026-09-24 | hlib/components/component.py, point_component.py, uv.py, __tests__/test_component_collections.py, docs/component_collections.rst, docs/index.rst | Vertices/CVs/UVsの位置取得・同一座標設定・保持順座標設定、XYZ/UV軸の一括編集とfull_names追加。Edges/Facesは既存vertices経由で対応。ノード系コレクションは対象外。Maya2027 standalone313件成功・GUI1件スキップ、Sphinx警告なし。未コミット |
| Claude Code | 2026-09-24 | maya/inhouse/HTools/rigging/advancedOrientJointUI.py | 新設した`preserved_skin_shape`をこのツールに適用。手動の`_preserve_enable/restore_move_joints_mode`/`_preserve_recache_bind_matrices`/`_compute_skin_clusters_from_joints`(自前実装)を削除し、hlib版へ置き換え。実UI経由(joint+skinCluster+mesh)でjointOrient変更後もメッシュ頂点が完全に不動であることを確認、run_all_tests.pyも既知の無関係な失敗以外は全て成功 |
| Claude Code | 2026-09-24 | maya/inhouse/hlib/decorators/skin.py(新規), decorators/__init__.py, __tests__/test_decorators.py | skinCluster変形を保ったままjointの姿勢を編集する`preserved_skin_shape`を追加(moveJointsMode+recacheBindMatrices、HTools/rigging/advancedOrientJointUI.pyと同じMaya標準機構)。頂点位置編集は既存のcmds.xformベースVertex/CV.set_positionで既に安全と確認。16テスト成功、run_all_tests.pyでも既知の無関係な失敗(test_channel_box.py)以外は全て成功 |
| Codex | 2026-09-24 | hlib/nodes/joint.py, nodes/skinCluster.py, __tests__/test_joint_delete.py | 直前の仕様を更新。同じskinClusterの祖先influenceがある場合のみ加算し、それ以外はcmds.deleteの標準処理へ委譲。単一influence・親なし・混在skinで標準削除と比較、Undo/Redo確認。レイヤー検出の不要なPlug生成を除去。Maya2027 standalone32ファイル失敗なし（GUI1件スキップ）、Sphinx警告なし。未コミット |
| Codex | 2026-09-24 | hlib/nodes/joint.py, nodes/skinCluster.py, __tests__/test_joint_delete.py | Joints.deleteが未スキニング・ルートjointも削除し、子Transformを親/worldへ退避。全skinの移送先を事前検査、実行失敗は対象・段階付きRuntimeErrorで伝播（自動ロールバックなし）。Maya2027 standaloneで32テストファイル失敗なし・GUI1件スキップ、Sphinx警告なし。未コミット |
| Codex | 2026-09-24 | joint.py / skinCluster.py（読み取りのみ） | Joints.deleteのウェイト移送・influence解除・子joint再親付け・削除条件を確認。移送先なしのskinClusterが予定数から除外される点も説明。実装変更・Maya実行なし |
| Codex | 2026-09-24 | maya/inhouse/hlib/nodes/animCurve*.py, nodes/blendWeighted.py, __tests__/test_animation_nodes.py, docs/animation_nodes*.rst, docs/index.rst | 連携ルール確認時に直前の完了作業を追記。AnimCurve基底・8具象型とBlendWeighted、Undo対応編集を追加。Maya 2027 standaloneで既存分含む299テスト成功・GUI1件スキップ、Sphinx警告なし。未コミット |
| Codex | 2026-09-24 | maya/inhouse/hlib/editors/channelBox.py, editors/__init__.py, selection.py, cmds/channelBox.py, cmds/captureSelection.py, __tests__/test_channel_box.py, __tests__/test_selection.py, docs/selection_and_channelbox.rst | 連携ルール確認時に完了作業を追記。ChannelBoxとSelectionを追加。選択復元・Undo・属性解決をstandaloneで検証。ChannelBoxの実UI選択・解除は未検証。未コミット |
| Claude Code | 2026-09-24 | maya/inhouse/hlib/nodes/node.py, skinCluster.py, maths/matrix.py, maths/easing.py(新規), utils/naming.py(新規), plugs/plug.py | 属性並び替え(move_attribute)・非線形ウェイト再分配(redistribute_weights)・行列ミラー(Matrix.mirrored)・名前サニタイズ(legalize_name)を追加。plug.py の attrType() 呼び出し漏れバグを修正 |
| Claude Code | 2026-09-24 | WORK_LOG.md(新規), CLAUDE.md, AGENTS.md, .github/copilot-instructions.md | Claude Code/Codex/Copilot並行運用のためのハンドオフファイル(WORK_LOG.md)を新設し、3つの指示ファイルに参照ルールを追記 |
