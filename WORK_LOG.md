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






















| Codex | 2026-10-11 | 配布方式の相談（README・起動バッチ・submoduleの参照のみ） | SourceTreeとGit不要の配布・更新方式を比較。 |
| Codex | 2026-10-09 | mlib判定の衝突名・省略入口 | 衝突しない59入口とSphinxは実装・検証完了。source/type/root/element/loaded/new/currentの既存意味を変えるか、ユーザーの回答待ち。既存入口は保持中。 |




















## mlib 修正予定（2026-10-02 追加レビュー）

- [x] 2026-10-08の全体検証で確認した一括API登録漏れをユーザー指示で修正。DagNodesのreadsへgetSkinClusters/getBindPoses、TransformsのreadsへgetUnusedIntermediateShapes、writesへdeleteUnusedIntermediateShapesを追加しJointsへ継承。既存Joints.getSkinClustersの集約を維持。関連テストはMaya2022/2027各18件成功。

- [x] Component._resolve_input: 単数解決で範囲を全ラッパーへ展開する前に要素数を検証する。Maya2027で441頂点生成後の拒否を再現。
- [x] Node.add_attribute: ベクトル型の分岐前にquery/edit禁止を検証し、通常型と例外の契約を揃える。
- [x] extensions._initialize: 拡張ごとのsys.modules削除をやめ、再読み込み対象の無効化とimport/登録を別段階にする。拡張AがBを継承すると、Bの再importでAの基底が登録済みBと別クラスになる。Maya2027の一時拡張2個で両方loaded・issubclass=Falseを再現。
- [x] 拡張の先行import: 初期化中のパッケージを未対応として確定しない。mlib_bifrostを先にimportするとMLIB_EXTENSION_API未定義の段階でskippedになることをMaya2027で再現。初期化完了後の登録経路とimport順のテストを追加する。宣言の順序変更だけでなく再入・二重importも防ぐ。

## 完了履歴

- Claude Code (2026-10-30): mlib 6.0.0 を実装。時間の数値をフレーム既定(timeUnit="sec" で秒)、getTranslate/setTranslate を getTranslation/setTranslation へ改名、点の位置を Vector の list、ls を常に集まり(Plugs を追加、混在は list)、Nodes/Components に + == sort、getNextAvailable は Plug、Mesh.setPoints 追加、getRotate(unit)・Joint の名前取得・Plug の getAttrName/lock/unlock/mute/unmute を削除、isHidden を hide に対応、getConnections の既定で変換ノードを飛ばす、ミラー軸は x と YZ の両表記、エラー文の改善、mlib 内の外部ライブラリ名の記述を削除。changelog に移行表。runStatic 160件、Maya 2022〜2027 全6版で178ファイル・2189テスト、mlrig 710件、Sphinx(-W)と文書検査が合格。直下 tests/mlib_integration の6ファイルの失敗は 5.0.0 から同じ(今回は未修正)。
- Claude Code (2026-10-30): mlib 改修の検討のみ(実装なし)。モデラー・アニメーター・リガー・TA の捨てスクリプト56本を Maya 2027 で実行し、似たメソッドのずれを横断監査。黙って誤る2件(AnimCurve の時間が秒、get/setTranslate の既定がピボット基準)ほか22件と、決めてもらう論点10件を docs/research/mlib-review-7h-2026-10-30.md に整理。足す候補は Mesh.setPoints のみ。mlib のコードは変更なし。
- Claude Code (2026-10-30): mlib の pyright 警告を2件解消(動作の変更なし)。Matrix の rotate 引数の docstring に om2.MEulerRotation・om2.MQuaternion を明記し、_merge_flags の pairs の短名を str | None に。スタブを再生成。runStatic 160件が合格。
- Claude Code (2026-10-30): mlib 本体の pyright 警告を動作を変えずに削減(550件→157件。残りは主に Maya の型スタブ側の誤りと、スタブと本体の二重化)。docstring の型を実装に合わせ、内部だけに型注釈を追加。Node.mnode() の型を直し、generic への MTransformationMatrix 設定の不具合を修正。スタブ生成に setter・contextmanager のデコレーター利用・getType のオーバーロードを追加。runStatic、Maya 2022/2027 の mlib 全件、mlrig 710件が合格。
- Codex (2026-10-30): MCE Outputの行頭Error/Warning/Result着色・配色・枠線・選択色・独立ズームと設定移行を修正。専用Maya2022/2027のQt/API各34項目、出力書式各26件＋保持、C++各29件が合格。全6版ビルドと日英Sphinx成功。2022の既存静的解析速度テストは変更前5.14秒／変更後5.16秒で5秒基準超過を確認し未解決として記録。実OS入力は未実施。比較画像・14.75秒動画を非公開Driveへ保存し読戻し確認。詳細 .maya-output/mce-output-fix-20261030/verification.json。ユーザー指定でソース・テスト・文書・全6版配布物をコミット／プッシュ対象へ集約。

- Codex (2026-10-30): QPEのFBX読込と操作別サイドバーをユーザー依頼でコミット・プッシュ対象へ選定。専用Maya2022/2027各70項目・単体UI10項目の結果、構文、差分を確認。共有WORK_LOGは今回QPE分のみをステージし、他担当と過去作業の未コミット記録を保持。

- Codex (2026-10-30): QPE右ペインをOpen/Import/Reference/Save別に整理し、設定の下へ実行ボタンを配置。ネームスペース直接編集、追加設定と詳細の折りたたみ、FBX更新ボタン名、タブ切替時のスクロール復帰、拡大時の長文ラベルを改善。専用Maya2022/2027各UI26・表示6・名前空間7・FBX31、単体UI10件合格。Qt操作動画と画像を非公開Driveへ保存し読戻し確認。Windows実入力はアクセス拒否で未実施。詳細.maya-output/qpe-sidebar-20261030/verification.json。ユーザー指定でコミット・プッシュ対象へ集約。

- Codex (2026-10-30): QPEのFBXダブルクリックを現在のMayaへ変更。右サイドバーと上部メニューに通常オープン／追加／アニメーション更新等の5モードと再生範囲設定を追加し、標準FBX設定を成功・失敗時に復元。Maya2022/2027の専用GUI各31件、Qt5/6のモード切替各7件、単体UI回帰10件が合格。Windows実入力は画面取得エラーで未実施。Qt操作動画を非公開Driveへ保存・読戻し確認。詳細.maya-output/qpe-fbx-20261030/verification.txt。ユーザー指定でコミット・プッシュ対象へ集約。

- Claude Code (2026-10-30): mlrig夜間タスク。楕円体コライダーへの柔らかい押し出し EllipsoidCollision を追加(setups/ellipsoidCollision.py。標準ノードのみ。中心のtransformの回転を軸とし、軸ごとの半径 radiusX/Y/Z。放射方向の半径 R = 1/|(lx/rx, ly/ry, lz/rz)| と d = |p-c| - R に SphereCollision と同じ柔らかい押し出し。出力 matrix・distance・push・penetration・directionRadius。逆回転はクォータニオンの共役で作り matrixNodes に依存しない)。Setup Samples 1項目、test_setup_ellipsoid_collision.py 9件、文書 docs/ellipsoid_collision.rst、検証デモ tools/demo_ellipsoid_collision.py。隔離Maya 2027で setups 569件・standard 76件OK、Sphinx -W 成功、検証動画294フレーム判定OK。コミット・プッシュ(このコミット)。
- Claude Code (2026-10-29): mlib 5.0.0。リギング作業の使い勝手調査で決めた36項目を実装(角度の既定を度、node.tx=5 の書き込み、joint の inverseScale、nextAvailable を Maya の規則に、型名 multDL/addDL の読み替え、エラー文と Script Editor の発生場所、再実行向け safe=True、Joint.orient/mirror・IkHandle.create・BlendShape・スキンの頂点単位/ミラー/刈り込み・カーブ作成・setColor・enum の名前設定・setLimits 等)。mlrig 等の利用側も追従、logger を lowerCamelCase に(AGENTS.md も更新)。Maya 2022〜2027 の mlib 全件、mlrig 701件、静的検査、Sphinx(-W)が合格。調査と決定はローカルの docs/research/mlib-usability-rigging-2026-10-29.md。
- Codex (2026-10-29): MCEの補完順位・Literal/TypedDict文字列候補、番号付きスニペット、位置付き型/引数ヒント、モジュール改名/import追従、新規モジュールへの移動、最後の変更セットUndo/Redoを実装。2022/2027をビルドし単体/standalone/UI回帰、専用GUI各77項目、Sphinx警告エラー化ビルド合格。2027でWindows実入力の補完/確定/Undoも確認し動画保存。複雑なスニペット形式等の制限は文書化。2023〜2026未検証。ユーザー指定でコード・テスト・文書・2022/2027配布物をコミットとプッシュの対象へ集約。他担当範囲は変更なし。

- Codex (2026-10-29): MCE 0.9.2で改行差5ケース・本文Undoのカーソル復帰と、Python/MEL実行がcmds/mlibのシーンUndoを無効化する問題を修正。mlib本体は変更なし。2022〜2027全6版ビルド・単体/standalone/offscreen、2022/2027専用GUIの編集各52・シーンUndo各14項目、日英文書-Wが合格。既存編集比較137ケースの本文/位置差0。実OS入力と全mlib APIは未網羅。非公開動画・再現手順・制限は.maya-output/mce-enter-five-20261029/verification.txt。ユーザー指定で修正・検証・6版配布物をコミットとプッシュの対象へ集約。他作業変更を保持。
- Codex (2026-10-29): MCE 0.9.1で補完確定直後の入力保持、改行時の本文保全、字下げ・選択・行/単語操作、引用符補完、検索の入力境界を修正。Sphinx見出し警告を解消。2022〜2027の配布ビルド・単体/standalone/offscreen、専用2022/2027のGUI編集32・補完37・前面化後の検索10項目、日英文書ビルドが合格。Windows実入力は検索/置換/Undo等を別途確認。比較で残る改行5件と未実施範囲、動画は.maya-output/mce-vscode-three-hour-20261029/verification.txtに記録。完全一致は未達。他作業変更を保持。
- Codex (2026-10-29): MCE 0.9.0に別プロセスの型解析・全文/未保存タブの補完/診断・定義/参照・リネーム・auto import・コードアクション・型色/行末ヒント、隔離コピー上の変数/関数抽出・モジュール移動・import整理を追加。取消/世代/破棄/下見/Undoを保護し、監視の不要な再解析を修正。2022〜2027ビルド・単体/standalone/offscreen合格（2022/2023の負荷時速度超過は同じ基準で再測定合格）。専用Maya 2022/2027のQt GUI各57チェック、隔離リファクタリング7件合格。撮影時のQt5一時ウィジェット参照を限定し再確認。詳細・制限・非公開動画リンクは.maya-output/mce-pylance-gap-20261029/verification.txt。ユーザー指定でコード・テスト・6版配布物をコミット対象へ集約。他ツールの変更を保持。

- Claude Code (2026-10-29): VS Code 補完用に、mlib の docstring から型スタブ(.pyi)を各 .py の隣へ作る tools/generate_mlib_stubs.py・.bat を追加し、生成した 145 ファイルを Git 管理に(mlib本体のコードは変更なし、pyrightconfig の exclude で解析対象外)。ls・createNode・getConnections・getSource・getDestinations は引数ごとの戻り値を @overload で補い、Joints 等は要素型で反復。test_static_stub_generation.py が古いスタブを検出。runStatic 160件、Maya 2022・2027 の mlib 全件が合格。pyright の言語サーバーで補完・引数ヒント・ホバーを確認(VS Code の画面での確認は未実施)。
- Codex (2026-10-29): MCE入力支援の機能調査を完了。隔離Maya2027/MCE0.8.3で補完15・診断5・定義位置1ケースを採取。詳細はローカルdocs/researchと.maya-output/mce-pylance-gap-20261029へ保存。製品コード変更・GUI再検証・プッシュなし。

- Claude Code (2026-10-29): mlrig夜間タスク。カプセル(線分)コライダーへの柔らかい押し出し CapsuleCollision を追加(setups/capsuleCollision.py。標準ノードのみ。t = clamp(dot(p-a,b-a)/|b-a|^2,0,1)、q = a+t(b-a)、両端で半径を変えられる r(t) の先細り、SphereCollision と同じ指数の押し出し、matrix・distance・push・penetration・parameter を出力)。SphereCollision の押し出し部分を _radialGraph へ切り出して共有、Setup Samplesに1項目、文書 capsule_collision.rst と検証デモ tools/demo_capsule_collision.py を追加。隔離Maya 2027で test_setup_capsule_collision 9件・setups 560件・standard 76件OK、Sphinx -W 警告0、検証動画354フレーム判定OK。コミット・プッシュ(このコミット)。

- Claude Code (2026-10-29): mlib 4.1.0。MultiPlug に論理番号・要素Plugの存在を返す `in` を追加し、Plug の repr を実際のラッパー型名の表示(`MultiPlug('pma.input1D')`・`<DoubleLinearPlug invalid>` 等)に変更。`len()` は cmds が位置0〜len-1の並びとして展開し論理番号と違う値を黙って返すと確認したため追加せず、設計文書・CLAUDE.md に理由を記載。Maya 2022〜2027 の mlib 全件、2027 の mlrig 692 件、静的検査・Sphinx(-W)が合格。

- Codex (2026-10-29): ユーザー指定でMCE 0.8.3のコード・テスト・6版バイナリ・配布定義を91a95835としてorigin/mainへプッシュ。リモートHEADの一致を確認。既存のローカル調査記録とtrialを保持。

- Codex (2026-10-29): MCE 0.8.3。f文字列の式/書式指定を共有解析し色分け・補完・引数ヒント・自動ペアへ適用。キーワード引数候補、指定済み除外、静的/クラス/インスタンスの束縛、同一行の宣言と既存=の再利用を追加。2022〜2027の全6版を再ビルド、各43単体・20コア検証群とMaya/入力回帰成功。専用GUIは2022/2027各35項目、Windows実キーは2027で5ケース確認。途中の2023中間オブジェクト混在を再コンパイルで解消し再現検証3回成功。証拠・非公開動画リンクは `.maya-output/mce-editing-fix-20261028/verification.json`。既存変更を保持、未コミット・未プッシュ。

| Codex | 2026-10-28 | MCE編集挙動の比較調査を完了。Maya 2027/MCE 0.8.2で25ケースをQt操作、VS Codeは専用新規ウィンドウで主要ケースをWindows入力確認。引数名候補・f文字列の式解析・同一行の宣言検出に差を確認。自動候補タイミングは拡張の影響未分離。調査メモはdocs/research、証拠は.maya-outputへ保存。製品コード変更・プッシュなし。 |

- Claude Code (2026-10-28): mlib 4.0.0。ArrayPlug→MultiPlug(plugs/multiPlug.py)、Plug.isArray/isElement/getArray→isMulti/isMultiElement/getMulti に改名(互換の別名なし)。説明文・docstring・例外メッセージの呼び名をMayaのコマンドに合わせて「マルチアトリビュート」「要素」「論理番号」「コンパウンドアトリビュート」「子」に統一し、docs/mlib-api-design.md 冒頭に mlib/Mayaコマンド/OpenMaya の対応表を追加。Maya 2022〜2027 で mlib 全件、2027 で mlrig 692 件、静的検査・Sphinx(-W)が合格。

- Codex (2026-10-28): MCEのm一文字補完を同じ4入力でVS Code/Pylanceと比較。Windows実操作でも空タブのmはMCE0.8.2が6件、VS Code1.140.0が同じ6件＋matchの7件と確認。VS Codeの言語サービス返却33件と画面の絞り込み後7件を区別。過剰候補はこの条件で未再現のため本体変更なし、実際の候補例・MCE版をユーザーへ依頼。専用Maya/VS Codeを終了、ユーザー環境と既存変更を保持。証拠・非公開比較クリップURLは`.maya-output/mce-letter-m-20261028/`およびGit対象外`docs/research/mce-letter-m-20261028.md`。未コミット・未プッシュ。

- Codex (2026-10-28): MayaCodeEditor 0.8.2。VS Code 1.140.0/Pylance 2026.4.1の専用拡張テストホストで11ケース比較し、未importモジュール・別名元名・別関数内importを補完へ混ぜる経路を修正。型推論でも未宣言の外部名を解決しない。def/class/asの新しい名前を入力する場所では通常候補を抑制し、import文・組み込み・参照式・既存の変数/Enter修正は維持。2022〜2027の6版を再ビルドしunit/Maya/UI回帰すべて成功、補完39テスト、専用Maya2022/2027のQt GUI自動操作各18項目成功。実入力/IME未実施。調査メモはGit対象外のdocs/research、結果と非公開Drive動画URLは`.maya-output/mce-suggest-20261028/verification.json`。ユーザーMayaと他変更を保持、未コミット・未プッシュ。

- Codex (2026-10-28): MayaCodeEditor 0.8.1。補完専用のスコープ抽出を追加し、現在/外側関数の引数・変数、制御ブロック・分割代入の名前を候補へ反映。完全一致の候補でEnterを改行へ流していた分岐を除去し、確定と次の改行を分離。現行mlibのJoints/Nodesに既存補完テストを追従。2022〜2027の6版を再ビルドしunit/Maya/UI回帰すべて成功、専用Maya2022/2027のQt GUI自動操作は各11項目成功。Windows実入力・IMEは今回未実施。証拠と非公開Drive動画URLは`.maya-output/mce-completion-20261028/verification.json`。ユーザーMaya・他タスクの変更を保持、未コミット・未プッシュ。

- Claude Code (2026-10-28): mlib の Undo 網羅テスト `__tests__/integration/test_undo_coverage.py` を追加(公開の書込み 175 ケースを通常経路で実行→Undo 1回で変更前・Redo で変更後に戻ることを確認、fast 119 ケースは Undo キューが空のままを確認、書込み API の網羅の番人 144 件・除外 17 件)。Maya 2027・2022 で全件合格。ユーザー報告の createNode の Undo 不具合は mayapy・使い捨て GUI・commandPort 経由のいずれでも再現せず。

- Claude Code (2026-10-28): mlib 3.0.0 コード縮小。外部(mlrig・HTools・tools・拡張)で未使用の BlendShape・計算ノードのラッパー約15種・HIK・Transformation・Cycle・DagPose の大半・コンポーネントの書込みを削除、fast を中核の操作に限定(duplicate・select・Namespace・mute・matchTransform・influence除去の fast を削除)、複数形クラスの転送メソッドと Transforms/DagNodes を削除、短縮名の別名引数を Maya フラグの入口だけに限定(mlrig の ws= 約15か所を worldSpace= へ)。本体 37,323→27,156 行、テスト 50,147→43,317 行。Maya 2022〜2027 で mlib 全件、2027 で mlrig 692 件、静的検査・Sphinx(-W)・文書検査が合格。

- Codex (2026-10-28): SimpleCloth・SimplePhysics本体、HTools/phsycs、対応mod・説明書・担当履歴の24ファイルをae16774dとしてコミットしorigin/mainへプッシュ。リモートのコミット一致を確認。並行作業のmlib変更と既存ステージを保持。

- Codex (2026-10-28): Simple Cloth / Simple PhysicsのHTools入口をriggingからユーザー指定のphsycsカテゴリへ移動し、両READMEの起動案内を更新。既存userSetupのフォルダ探索仕様、移動先モジュール解決・Python構文・旧入口の除去を確認。Maya GUI未起動のためメニュー表示・クリックは未確認。次回起動時に反映。既存変更を保持、未コミット・未プッシュ。

- Claude Code (2026-10-28): mlrig夜間タスク。球コライダーへの柔らかい押し出し SphereCollision を追加(setups/sphereCollision.py。標準ノードのみ。d=|p-c|-radius に PlaneCollision と同じ指数の押し出し、matrix・distance・push・penetration を出力、中心一致は押し出さない)。PlaneCollision の押し出し部分を_pushGraph へ切り出して共有、Setup Samplesに1項目、文書 sphere_collision.rst と検証デモ tools/demo_sphere_collision.py を追加。隔離Maya 2027で test_setup_sphere_collision 8件・setups 551件・standard 76件OK、Sphinx -W 警告0、検証動画294フレーム判定OK。コミット・プッシュ(このコミット)。

- Codex (2026-10-27): Simple Cloth 0.1.0を独立したPython API 2.0メッシュプラグインとして追加。XPBD伸び/曲げ近似、Max Distanceペイント、固定頂点、Backstop、風、球/カプセル/平面、粒子セルフコリジョン、プリセット、独立blendShapeベイク、設定UI・HTools入口・READMEを実装。UEコードの組込みなし。Maya2027 mayapyで13件成功（スキン入力、時刻/過去キー、DG/Serial/Parallel、cm/m、UV、保存再読込、Undo、ベイク独立性）。専用GUIでペイントFlood/Undo、微小係数の実操作/Undo、HTools入口を確認。99頂点・145フレーム録画の固定/移動上限/点の球クリアランス検証成功（最大伸び残差7.62%）。成果物verification/20261027-223426-5a369998、.maya-output/simple-cloth/。動画をDriveへ保存しサイズ335246 bytesを読み戻し確認。Drive共有UIが「現在、共有できません」と返すため一般リンク共有のみ未完了、所有者限定を記録。Python性能・点衝突・Chaos完全互換なし等を明記。他担当の変更を保持、未コミット・未プッシュ。

- Claude Code (2026-10-27): mlib 2.2.0。内部メソッド名・引数・処理の書き方のブレを調査(nodes/plugs/components/common/core/cmds/maths を 4 並列で読了)し統一: bool 検査・別名解消・無効ノード検査・ロック拒否・プラグ遡上を decorator/util/core の共通ヘルパーへ集約(約 650 箇所)、例外を 4 分類(型/値/状態/未対応)に揃え日本語メッセージ約 70 件を英語化、Undo チャンク名を mlib<Class><Method> に統一、内部名を _require_/_resolve_/_<method>_fast|_cmds 規則へ改名、Plug.set の Template Method 化・Nodes.__init_subclass__ での一括宣言合成、docstring 402 件を固定文・用語・項目順に整形。mlib.reload() の親パッケージ依存の順序不良を修正。規則は docs/mlib-api-design.md「内部実装の定型」。Maya 2022〜2027 で mlib 全件、2027 で mlrig 685 件、静的検査・Sphinx(-W)・文書検査が合格。

- Codex (2026-10-27): Simple Physics 0.1.0を独立したMaya Python API 2.0プラグインとして追加。Kawaii Physicsを参考にした係数・ランプ・根元/除外/仮想ボーン、球/カプセル/平面、角度/平面/距離拘束、固定時間評価、プリセット、別階層へのベイク、設定UIとHTools入口を実装。MIT通知・使い方・未対応機能を記載。Maya2027の専用mayapyで15件成功、専用GUIでHTools入口・係数の実操作、DG/Parallelの145フレーム一致、最終動画145フレームの骨長/角度/点のクリアランス検証を確認。動画をDriveのMaya検証動画へ保存しリンク閲覧権限とサイズを読み戻し確認。拘束競合時の残留貫通、既存スキン自動付替えなし、Python性能制限を明記。成果物は.maya-output/simple-physics/とverification/20261027-215600-c2b27d33/。他担当のmlib変更を保持、未コミット・未プッシュ。

- Codex (2026-10-27): プッシュ依頼に対応し、KawaiiPhysics・UnrealEngineのサブモジュール設定/参照と担当履歴を公開対象に整理。origin/mainとの一致、両サブモジュールの未変更、調査メモのGit除外、ステージ差分を確認。並行作業中のmlib等と他担当の作業ログは対象外として保持。

- Codex (2026-10-27): ユーザー指示でUnrealEngineの限定展開を解除。固定済みUE 5.8.4（f45729c0b6）の全224,010追跡ファイルを展開。sparseCheckout=false・skip-worktree 0件・取得済み参照の不足Gitオブジェクト0件・上流差分なしを確認。履歴はdepth 1を維持、Setup依存バイナリ取得・ビルドは未実行。既存変更を保持。

- Codex (2026-10-27): UE公式リポジトリをmaya/external/UnrealEngineへサブモジュール追加。releaseの5.8.4（f45729c0b6f097038e72b52d366a62baeca3275b）を固定。depth 1・blob:none・ローカルsparse checkoutでChaos/Cloth関連ソースを展開。gitlink・取得元・クリーン状態・差分検査を確認。Setup・ビルド・Mayaロードは未実行。既存変更を保持、未コミット・未プッシュ。

- Codex (2026-10-27): 依頼されたKawaiiPhysicsをmaya/external/KawaiiPhysicsへ浅いサブモジュールとして追加（feee5fe727261ba9cfe725c4af280aa9e381c31d）。gitlink・取得元・上流の未変更を確認。Maya実装や自動ロード設定は未追加、Maya/UE実行は未実施。調査メモはGit対象外docs/research/へ保存。既存変更を保持、未コミット・未プッシュ。

- Claude Code (2026-10-27): mlib 2.1.0。2.0.0 で次版へ送った項目を対応。計算ノード系・removeInfluences・Namespace・select・setMuted・duplicate・matchTransform(position/pivots)に fast を追加(cmds と同じ結果にできない指定は変更前に NotImplementedError)。isSettable・resetAttrs 絞込み・getHistory・getPlugs・IkHandle.getJoints・listReferences 等の読み取りを om2 化し test_cmds_parity.py で突き合わせ。influence 除去の fast の再配分を cmds の距離規則に一致させた(既存不具合)。公開引数を lowerCamelCase へ改名(test_static_public_args.py で検査)、cameraFn/meshFn/curveFn/referenceFn・SkinCluster.fn を mfn() へ統合、_ContainerMixin 化、仕様テストを機能別のファイル名へ改名し NamespaceCase へ統合。changelog・版番号・api-design・CLAUDE.md を更新。Maya 2022〜2027 で mlib 全件、2027 で mlrig 685件、静的検査・Sphinx(-W)・文書検査が合格。

- Claude Code (2026-10-27): mlib 2.0.0 をリリース。未登録ノードタイプの動的クラス生成(基底は最寄りの登録クラス、`mlib.nodes.<TypeName>`)、作成を `mlib.createNode` に一本化(`Node.create`・`create=True` 廃止)、cymel に近いメソッドの統合・廃止(getPath系→getFullName/getName、dagFn/transformFn→mfn、getExtraAttrs→getPlugs(userDefined=)、Transform.reset→resetAttrs、getEuler→getRotate(order=)、Plug.getDataType→getType 等)、追加(setLocked・getRoot/getSiblings/getBoundingBox の DagNode 化・Plug 演算子 `>>`/`<<`/`//`・getAlias/getArray/getIndex/getEnumNames・uiUnits)。仕様テスト9ファイル追加・既存テストと mlrig の呼出しを移行。版番号・changelog.rst・Sphinx ガイド・api-design・CLAUDE.md を更新。Maya 2022〜2027 で mlib 全件、2027 で mlrig 685件、静的検査・Sphinx(-W)・文書検査が合格。fast の追加・om2 読み取り置換(Phase 3)と snake_case 引数の改名は次版へ送った。

- Codex (2026-10-27): プッシュ依頼に対応し、QPEの6時間検証修正・B02終了クラッシュ修正・既定文字12pxと関連QPE/MCE回帰テストを公開対象に整理。既存GUI検証証拠、差分、Python構文と監査ランナー単体テストを確認。mlib/mlrig等の並行変更と他担当の作業ログをコミット対象から除外し、手元に保持。

- Codex (2026-10-27): QPEの既定文字サイズを13pxから12pxへ変更し、Standard/Restore Defaultsも統一。保存済み指定・Large/Largest・DPI倍率を維持。Qt5.15.2/Qt6.8.3の専用設定で表示、標準復帰、15px/125%の再読込とDPI2倍を確認。Maya GUIは今回は未実施。6秒の比較画像動画をDriveへ非公開保存・サイズ/URL/権限を読戻し。証拠 `.maya-output/qpe-font-size-20261027/`。未プッシュ。

- Codex (2026-10-27): QPE B02終了時クラッシュを切り分け、QWidget.style()が保持する共有QStyleSheetStyle参照とShiboken破棄順の衝突を修正。標準delegate描画・部品寸法による列幅計算・アプリstyleからの標準アイコン取得へ変更。最小Qt再現は旧条件3/16回AV・参照なし0/16回、修正QPE単体CDB監視12回成功。Maya2022/2027で16プロセス・128回再生成の終了検証、navigation/theme/tabs/dock_lifetime/MCE併用10スイート合格。専用テストとREADMEを追加。Qt自動操作の再生成画像を16秒動画化し、Drive所有者限定・サイズ/URL読戻し確認。実第三者ツール全組合せ・今回修正後2023〜2026・実IME/物理DPIは未確認。MCE製品C++変更なし。証拠 `.maya-output/qpe-shutdown-20261027/diagnosis.txt`・`final-summary.json`。検証用Maya残存0。既存差分を保持し、未コミット・未プッシュ。

- Codex (2026-10-27): QPE/Maya Code Editorの6時間検証を04:20 JSTで終了。QPEのキー伝播、自己参照誤成功、再生成時のQt内部部品参照、破棄済みタイマー、改名後フォーカス、狭幅UIを修正。2022/2027の併用・シーン操作・同時異常終了後の本文復元・最終20回再生成と実Windows入力を検証し、2023〜2026は併用回帰を確認。終了時ShibokenクラッシュB02は未解決。共有タブの実ドラッグ・複雑IME・実他ツール・混在物理DPI等は未確認。MCE製品C++変更なし。期限後は新規テスト/製品修正なし、稼働Mayaなしを確認、両自動化停止済み。詳細/証拠/再現手順は `.maya-output/qpe-mce-six-hour-20261026/final-report.txt` と `progress.json`。他タスク変更を保持し、未コミット・未プッシュ。

- Codex (2026-10-26): Maya Code Editor 0.8.0。先着Mayaだけの復元ロックと本文削除を廃止し、不変の圧縮本文・親世代付きスナップショットへ追記保存。本文変更直後の同期保存、並行編集の両方復元、破損時の親世代回収、履歴の追加復元、保存失敗の常時表示を実装。旧復元データを.maya-output/mce-recovery-20261026/user-backupへ保護。全6版ビルド・ストア多重プロセス/破損/失敗テスト合格。2022/2027 GUIで2重起動・入力直後の強制終了・2回再起動・履歴復元・通常解除復元、2027で保存失敗/再試行/ドック再生成と30タブ性能を検証。C++ UI/補完等の回帰も両版合格（廃止済みmlib色APIの期待を現行getVisibilityへ更新）。テストのダイアログ選択/古いQtラッパー参照を修正後再実行。結果.maya-output/mce-recovery-20261026/verification.json。動画 https://drive.google.com/file/d/18WPjF2BCC2WdwE4Gcvi1dxCgDeC8SQeQ/view 。電源断・物理IME入力・2023〜2026のGUI未検証。公開前に全6版の検証済みバイナリのSHA256一致と差分検査を再確認。MCE 0.8.0のみ公開対象とし、QPE差分と他作業の記録は保持。
- Codex (2026-10-26): QPEの監視を本体と専用workspaceControlへ限定し、共有タブの制約変更を廃止。再生成前の監視解除、現在の内容/親の確認、旧close通知の世代排除、Qt5親ラッパーの寿命保持を追加。配置補正は明示表示/復元時に分離。Maya2022/2027で削除・即再生成・uiScript復元・共有親不変・閉じる/再表示・右/下/共有タブ縮小を検証し、2027の4段階再起動復元も成功。結果.maya-output/verification/qpe-dock-safe-20261026/verified-results.json。他ツール固有の例外手順と物理入力は未確認。公開前に検証結果・構文・差分を再確認し、QPEの修正と回帰テストを公開対象として整理。
- Codex (2026-10-26): QPEのQt寿命を調査。隔離Maya2022/2027で削除直後の再生成が旧watcherを再利用し、イベントループ復帰後に新画面だけ残る不具合と、制御用共有タブで破棄時のサイズ制約復元漏れを再現。Maya Code Editorとの差分・共有親監視・未検証リスクをdocs/research/qpe-qt-lifetime-20261026.txtへ記録（Git対象外）。他ツール固有の例外・クラッシュは未再現。製品コード・ユーザー設定は変更なし。証拠は.maya-output/qpe-qt-investigation-20261026/。

- Claude Code (2026-10-26): 仕様固めのテストで見つかった食い違い・不具合26件を修正(AngleBetween.getAxisの評価、Reference.getFilenameの引数、mlib.deleteのアトリビュート名の拒否、fastの丸め・型の検証を通常経路に統一、ピボットのロックを両経路で拒否、型の登録にdagNode/shape、作成前の型検査、削除直後のDAG参照の例外、enumの例外の統一、BlendMatrix.setTargetのfastなど)。テストを新しい約束に更新。Maya 2022〜2027でmlib全件・mlrig setups合格。

- Claude Code (2026-10-26): mlibの仕様を固めるテストを追加(__tests__ の test_spec_{A,B,C,D}_*.py・test_static_spec_D_numeric.py、23ファイル・約630件)。計算ノード・Plug・シーンのノード・cmds/common/maths/components/decorator/core の公開APIの引数・戻り値・例外・Undo・fast/safe・不正入力を確認し、テストに一度も出ない公開APIを0件に。docstringとの食い違い26件と不具合(AngleBetween.getAxis・Reference.getFilename)はローカルの .maya-output/mlib-spec-tests/FINDINGS_*.md に記録(テストは今の振る舞いを固定)。test_contract_changes_C の時間の比較の上限を6倍に緩和(揺れ対策)。Maya 2022〜2027で全件合格。

- Claude Code (2026-10-26): スキンされたjointの解除・削除で親influenceへウェイトを加算する処理(mlibのremoveInfluence(s)・Joint.delete、HToolsのremoveSelectedJoints)を、複数階層・複数joint・複数skinCluster・Undo/fastなどで確認。期待値と変更前(aff37f0)の両方と一致し、壊れていないことを確認。試験 mlib/__tests__/integration/test_skin_weight_transfer_complex.py(19件)と tools/test_htools_remove_selected_joints.py(9件)を追加。

- 2026-10-26 Codex: ユーザーのpush指示に基づき、基本操作の単体45件/結合10件、Transformの反転不能な親の更新前検査、テストREADMEと作業記録の7ファイルをcommit/push対象として確認。隔離Maya2022〜2027各1338件（既存skip除く失敗0）・静的100件の成功記録と追加55メソッドを照合。構文・git diff --check成功、origin/mainとの分岐なし。生成物/調査資料は対象外、追加のMaya/GUI/Sphinx起動なし。

- 2026-10-26 Codex: 削除11件・Plug18件・Transform16件の単体と、DG評価/接続/親変更/削除/Undoの結合10件、計55件を4ファイルへ追加。失敗時の状態保持、safe部分更新、fastと通常Undoの境界、保持参照、疎配列・単位も確認。新規テストで判明したワールドsetMatrixの反転不能な親の検査欠落を、共有変換処理のOpenMaya isSingular検査で修正（公開署名不変、微小でも反転可能な親は許可）。HEADの旧処理では同じ回帰テストが失敗し、修正後の成功を隔離Maya2027で比較。READMEへ重点単体/結合の実行例を追加。隔離Maya2022〜2027の全6版で各139ファイル・1338件、失敗0（既存のGUI/環境条件skipのみ2〜4件、新規55件skip0）。静的100件・検出先分離・git diff --check成功。GUI実行なし、未commit/push。証拠: `.maya-output/mlib-basic-tests-20261026/result.json`。

- 2026-10-26 Codex: ユーザーのpush指示に基づき、Selectionの定数配置・Transformの内部メソッド順・BlendShapeのpathlib利用と作業記録の4ファイルをcommit/push対象として確認。直近の静的100件・隔離Maya2022/2027各156件の成功記録と現在差分を照合し、git diff --check成功。生成物と調査資料は対象外、origin/mainとの分岐なし。追加のMaya/GUI/Sphinx実行なし。

- 2026-10-26 Codex: ユーザー指示で既存チェックを実行し、Selectionの_NAME_CHUNKを定義前へ移動、Transformの内部メソッドを既存--fixで公開メソッド後へ整理、BlendShape保存先の親フォルダー取得をPath(destination).parentへ変更。保存先の絶対化・一時ファイル置換・失敗時cleanup・既存APIは保持。並び替え段階で170ファイルのsnapshot差分0、Selection/Transform全関数の本文/署名不変も確認。最終runStatic100件全成功、公開不一致0、layout170ファイル違反0・pathlib候補0（初期化順保護の情報5件）。隔離Maya2022/2027で保存復元・Selection・Transform・直近契約/速度改善の既存9ファイルを各156件成功（合計312件、失敗/skip0）。git diff --check成功、GUI/Sphinx未実行、未commit/push。証拠: `.maya-output/mlib-check-fix-20261026/result.json`。

- Claude Code (2026-10-26): mlibの約束の変更4件(disconnectは渡されたPlug/切断前の接続元を返す、削除を1回のcmds.delete/MDagModifierにまとめ削除できないものが含まれれば何も消さない、setRotateはrotateだけ・setMatrix/setTransformationは値の変わるチャンネルだけ書く、ls/Selection/getHistoryの名前をまとめて解決)と不具合4件(fastで既定ノード削除の異常終了、削除済みanimCurveのfast操作の異常終了、ObjectSet.isMemberのDGノード/アトリビュート、getHistoryの例外をRuntimeErrorへ)を修正。あわせて破棄済みノードのgetType等の異常終了も修正。試験 test_contract_changes_{A,B,C}.py を追加。Maya 2022〜2027でmlib全件・mlrig setups合格。未コミット。docs/mlib-api-design.md への反映はCodexの未コミットの変更があるため未実施。

- Claude Code (2026-10-25〜26): mlibの高速化(第0〜14回、未コミット)。意味(Undo/fast/safe・例外・戻り値・単位・公開API)を変えずに、スキンウェイト・blendShapeウェイトの範囲setAttr、Undo無効時と外側のundoTransaction内のundoChunk省略、double3のまとめた書込み、ラッパー作成の名前の再解決の省略(ls・階層・接続一覧・ヒストリー等)、Transformation・ArrayPlug・AnimCurve・import時の拡張探索などを短縮。変更: mlib の cmds/{delete,getNode,ls}.py・common/{namespace,selection}.py・core/{extensions,fastWrite,nodeEdit}.py・decorator.py・logger.py・util.py・maths/{matrix,transformation,vector}.py・nodes/{animCurve,blendShape,container,dagNode,dagPose,displayLayer,mesh,node,shadingEngine,skinCluster,transform}.py・plugs/{arrayPlug,compoundPlug,double3Plug,plug}.py、テスト integration/test_speedup_contracts.py・unit/test_skin_weight_ranges.py(新規)・integration/test_backlog_contracts.py、tools/test_rig_packages.py(--suite mlib のパス)。Maya 2022〜2027 で mlib 全1247件合格、mlrig 全スイート合格。ユーザー判断待ちの候補と既存の不具合は docs/research/mlib-speed-8h/SUMMARY.md(ローカル)。

- 2026-10-26 Claude Code(夜間タスク): mlrigに四節リンク機構 FourBarLinkage(`setups/fourBarLinkage.py`)を追加。クランクのピンとロッカーの支点から、カプラーとロッカーの関節を2円の交点(生成時の枝を固定)として標準ノードだけで求め、rockerMatrix・couplerMatrix・jointMatrix・excess(閉ループが作れない量)・transmissionAngle を出力。Python版 `jointPosition()`。Setup Samplesに1項目、文書 `docs/four_bar_linkage.rst`、検証デモ `tools/demo_four_bar_linkage.py`。試験 `test_setup_four_bar_linkage.py` 8件、隔離Maya 2027で setups 543件・standard 76件OK、Sphinx -W 警告0。検証動画は隔離GUIで360フレーム判定OK、Driveの同期フォルダー `Maya検証動画/mlrig-nightly` へ保存(リンク共有はコネクター非対応で未設定)。バックエンドは標準ノードのみ。コミット・プッシュ(このコミット)。

- 2026-10-25 Codex: 既存layoutへL040（公開入口の冒頭の入力assert候補）・L041（単純列挙の確認候補）・L042（os.pathのpathlib置換候補）・L043（判定できるテキストI/Oのencoding未指定）を追加。L041/L042は情報表示。assertは対象ファイル/行とTypeErrorまたはValueErrorを明示する--fix-assertsで修正でき、コメント・共有行・不明な行・例外名再定義は保存前に拒否。最適化時も有効なraiseと失敗時だけのメッセージ評価、BOM/CRLFを検証。Maya名・添字更新・内部/テストassert・バイナリ・不明なmode/引数等を一律変換しない。17テスト追加、runStatic100件成功、最後の引数展開除外後は関連42件再成功。最終layout170ファイル違反0、初期化情報5件/pathlib確認候補1件。正式規則/README/3ガイド同期・git diff --check成功。Maya未起動、並行する製品コードの変更は編集せず保持。未commit/push。証拠: `.maya-output/mlib-modern-checks-20261025/result.json`。

- 2026-10-25 Codex: 既存check_mlib_layout.pyの--checkへL030〜L034（代入/比較、カンマ/括弧、既定値/キーワードの=、行末コメント、名前へ直接代入するlambda）を追加。AST/tokenizeで型注釈・UTF-8位置・コールバックlambda・複数行・文字列/f-string対象外を区別し、Sphinxの#:記法を保護。新規5規則は検査のみ、既存--fixの変更範囲は維持。17テスト追加、runStaticは83件全成功・公開不一致0・本体170ファイル違反0/情報5件。構文・3ガイド同期・README見出し・git diff --check成功。README/API設計/AGENTS/CLAUDE/Copilotを同期。Maya未起動、並行するClaude Codeの製品速度改善差分は編集せず保持。未commit/push。証拠: `.maya-output/mlib-layout-spacing-20261025/result.json`。

- 2026-10-25 Codex: 指定5規則（importの先頭配置・標準/外部/内部の分類・理由コメント付き関数内import・複数モジュール分離/ワイルドカード禁止・4スペース/末尾空白なし/括弧内改行）をdocs/mlib-api-design.mdへ統合し、AGENTS/CLAUDE/Copilotへ同一方針を同期。reload初期化順・TYPE_CHECKING・既存__all__位置を保持し、既存検査の対象範囲とsnapshot比較の限界も明記。5項目と3ガイドの一致・参照先・差分/空白を確認。製品コード/検査ツール変更なし、Maya/Sphinx未実行。Claude Codeの速度改善作業行と既存差分を保持、未commit/push。

- 2026-10-25 Codex: ユーザー指示でmlibの既存runStatic.pyを実行し、公開不一致0、レイアウト170ファイル違反0（初期化順保護の情報5件）、静的66テスト全成功。既存layout --fixも実行して変更0/170、事前snapshotとの比較170ファイル差分0、git diff --check成功。修正対象がなかったため本体変更なし。新PEP 8規則・検査は追加せず、Maya未起動。既存WORK_LOG差分保持。証拠: `.maya-output/mlib-existing-checks-20261025/result.json`。

- 2026-10-25 Codex: PEP 8公式とmlib既存規則・レイアウト検査を照合。本体170ファイルのimport配置をAST集計し、先頭配置・理由付き遅延import・空白/改行/行長等の提案をGit対象外`docs/research/mlib-pep8-20261025.md`へ保存。関数内201 import文は違反とは扱わず、標準ライブラリ4候補の周囲とNode循環回避・reload初期化順を確認。既存layout検査は170ファイル違反0・情報5件、関数内import非検査と絶対名mlibの分類差を小さなプローブで確認。正式規則・本体は変更せず、Maya未起動。証拠: `.maya-output/mlib-pep8-20261025/`。

- Codex (2026-10-25): ユーザー依頼で説明用語統一・ls中心の入門・Maya2027参照・単体配置の実行環境案内を一括commit/push対象として確認。実行AST170Python・API参照2041件・継承図159件の不変を再照合し、Sphinx332ページ/22855リンク・静的66件・Maya2022/2027の説明例・6画面条件の成功記録を確認。調査資料/生成HTML/画像/専用Maya設定は除外。今回Maya/ブラウザの再起動なし。

- Codex (2026-10-25): CGWORLDのMaya Matrix/リギング記事と用語表記を調査し、mlibの38Pythonファイル/198docstringとコメント・ガイドの行列/変換行列→マトリクス、拘束→コンストレイント、四元数→クォータニオンを整備。逆/回転/転置/空間等の意味とdeterminantの「行列式」を保持し、拘束元はターゲットへ。入門のObject直呼出し例を名前/選択/型/アトリビュート/頂点範囲のmlib.lsへ変更し、リスト/空結果/範囲展開を説明。Objectは共通基底のAPI説明を維持して検索先をlsへ案内。Autodeskの4リンクと表記をMaya2027へ変更し実ページを確認。API設計文書と共有用語方針も同期。実行AST170Python・API参照2041件不変、継承図159件はリンク年以外不変。Sphinx332HTML警告0、掲載旧語0（行列式を除く）、22855ローカルリンク/素材に不備0、静的66件成功。RST本文14コードブロックと検索仕様3項目を隔離Maya2022/2027で各3テスト成功。Edgeの3ページ×1440/1024pxの6条件で横はみ出しなし、画像も確認。Maya2023〜2026・実GUIでの例実行は未実施。実行メッセージ3箇所は実行AST保持のため変更なし、未commit/push。調査/証跡 .maya-output/mlib-terminology-20261025/。

- Codex (2026-10-25): mlib入門の実行環境からworkspace起動バッチ依存の説明を除き、mlibフォルダの親をPYTHONPATH/sys.pathへ追加する案内と短い例へ変更。Maya2022〜2027/Python3の対象とWindows付属Pythonの系統（3.7/3.9/3.10/3.11/3.13）を追記し、各版mayapyのsys.versionで照合。Sphinx332HTML警告0・get/is参照0不一致・Mermaid参照・生成本文検査に成功。製品コード変更/GUI起動なし、未commit/push。

- Codex (2026-10-25): ユーザー依頼で失敗ログのターミナル表示・回帰テスト・READMEの8ファイルをcommit/push対象として確認。静的66件を再実行して成功、隔離Maya2022/2027での意図的失敗/正常終了の記録を照合。ローカルサンプル/生成ログはGit対象外を維持し、製品コードは変更なし。今回Maya/GUIの再起動なし。

- Codex (2026-10-25): テスト失敗時に詳細ログの絶対パス・失敗ファイル名・traceback/期待値差・終了コードを起動元ターミナルへ表示。run_all_testsが失敗ファイルの捕捉出力を結果へ保持し、mayapy/GUIランナーへ渡す。成功ファイルの詳細は従来どおりログのみ。READMEを同期し、静的66件（値不一致/例外/成功出力抑制/親ターミナル/GUI入口/起動異常/timeout）成功。隔離Maya2022/2027で意図的失敗は各1件・終了1・ログパスとAssertionError表示、正しい期待値は各1件成功・終了0を確認。証跡 __tests__/_output/failure-demo/terminal-failed・terminal-passed。実GUIは今回未起動、GUIの親表示は模擬結果で確認。製品コード変更なし、未commit/push。

- Codex (2026-10-25): ユーザー依頼で意図的な失敗サンプルを__tests__/_output/failure-demoへ用意。translateX=5に期待値10を指定し、隔離Maya2027で1件失敗・AssertionError: 5.0 != 10.0・status failed・終了1を確認。同じ操作の期待値5は1件成功・終了0。再実行READMEとログをGit対象外へ保存し、通常テスト/製品/ユーザーGUIは変更なし。他Maya版は未実施、commit/pushなし。

- Codex (2026-10-25): ユーザー依頼でテスト整理一式をcommit/push対象として最終確認。静的61件を再実行して成功、既存のMaya2022/2027・単独コピー1182件・GUI・Sphinx検証記録と参照更新を照合。テスト本体・workspace連携・利用側/CI/案内の更新をまとめ、生成物/専用Preferences/調査資料/submoduleを除外。Mayaは今回再起動せず、2023〜2026と利用側GUIデモは未再実行。

- Codex (2026-10-25): ユーザー指示でmlibテストを別リポジトリへ持ち出せる構成へ整理。__tests__/unit・integrationの2区分とrun.bat/runMaya/runStatic/runGui、checks/support/manual、READMEへ集約し、結果は同梱_outputへ保存。mlrig/HTools/cymel/拡張/外部投稿の連携をworkspaceのtests/mlib_integrationへ切出し、本体との混在メソッドも分離。旧tools入口の互換ファイルは残さずCI/案内/78利用側のimport参照を追従し、利用側は参照/説明以外のAST不変を照合。静的61件、2027単体899/結合283、mlibだけのコピーで1182件、2022全体1180+追加対象3件、2027 GUI単体897/結合283/表示3件を確認。連携13ファイル49件成功（GUI専用と未導入バイナリはskip）。開始時の旧_docs/conf.py参照による1失敗は実装配置へ修正し、旧アサーション5680件の欠落0を確認。製品170Python不変、Sphinx332ページ/159図不変・参照検査成功。2023〜2026、利用側GUIデモの再実行、手動投稿は未実施。未commit/push。証跡 .maya-output/mlib-tests-portable-20261025/result.json。

- Codex (2026-10-25): ユーザー指示による一括push対象として、mlib文書の日本語化・source/_ext配置整理・セットアップバッチ、mlrigのCSS独立化、完了済みHToolsの「?」ヘルプ変更と共有参照を確認。既存24テスト・公開/文書/Mermaid検査・変更Python10ファイル構文・HTools Sphinx警告0を再確認し、全5パッケージのビルド/34768リンク、332ページ/159継承図/16画面条件、隔離Python3.13セットアップの成功記録を照合。HToolsは既存の隔離Maya2027成功/終了0記録を確認し、GUIは今回再実行なし。生成HTML・venv・調査資料・submoduleは含めない。ローカルとorigin/mainは作業前0/0。push読戻し証跡は .maya-output/docs-push-20261025/ に保存。

- Codex (2026-10-25): mlib/_docsにsetup.batを追加。Python 3.11以上を検出して専用venvを作成/再利用し、requirementsのSphinx/AutoAPI導入・pip整合・CLIを確認。READMEへPython公式リンク、setup→rebuild→HTMLの初回手順、手動実行と障害対処を追加。現行継承図はMermaidのためGraphviz/Node.js/Maya不要と明記。隔離した日本語/空白パスでPython3.13の初回・再実行、332ページ/警告0・API参照0不一致・Mermaid参照検査に成功。Python未検出/既存venv破損/pip失敗は終了1で既存環境保持。Python本体の新規インストールと対話pauseは未実行。製品315Python不変、未commit/push。証跡 .maya-output/mlib-docs-setup-20261025/result.json。

- Claude Code (2026-10-25): HToolsメニューのツール名の右端に「?」を追加(`searchable_menu.py` の `HelpIconMixin`/`ToolMenu`)。押すとそのツールの説明ページを開き、ツールは実行しない。検索結果にも付く。末尾の Help は「HTools Documentation」だけにした。隔離Maya 2027で「?」・通常の実行・検索結果を確認。

- Codex (2026-10-25): 承認済みのmlib文書構成へ整理。本文/設定/素材を_docs/source、固有ビルド処理を_extへ分離し、概要図4部品をinclude、CSSをtheme/layout/code/mermaid、JSを専用フォルダに分類。CI・検査・README参照と配置名反映を追従。332ページ/2041参照/159継承図と16画面条件の表示を維持、18162ローカルリンク・既存24テスト・公開/構文検査・標準rebuild・別配置名の隔離ビルド成功。製品315Python不変。既存Plugの390px表示時の横スクロール(445px)は変更前後で同じ。証跡 .maya-output/mlib-docs-source-layout-20261025/result.json。

- Codex (2026-10-25): 追加指示で文書CSSをパッケージごとに独立化。共有参照があったmlrigへ3CSSを自前配置し、conf/testing.rst/該当英訳を同期。mlib/HTools/MayaCodeEditor/FramePlayerは既に自前配置であることを全5設定・CSSファイルで確認し、他4パッケージのCSSを変更せず保持。mlrigはmlibを置かない隔離フォルダでも日英各80ページ/警告0、他3パッケージの対象5ビルドも警告0。全体8出力592ページの34768ローカルリンク/素材参照・mlrigの4画面条件・CSS規則不変を確認。Maya未起動、未commit/push。証跡 .maya-output/docs-css-independence-20261025/result.json。

- Claude Code (2026-10-25): HToolsのSphinx説明ページ `maya/inhouse/HTools/_docs/` を追加(35ツール各1ページ・画面のスクリーンショット53枚、GitHub Pagesの `htools/` へ公開する手順をmlib-docs.ymlに1つ追加、README・CLAUDE.mdに案内)。`HTools/toolHelp.py` を追加し、HToolsメニュー末尾にHelp(全ツールのページ)、画面のある11ツールに Help メニュー/ボタンを追加。メニューは `_` で始まるフォルダーをカテゴリにしないよう変更。

- Codex (2026-10-25): mlib/_docsの階層整理を提案。隠しファイル・venv・生成物を含む6689ファイル/1697フォルダを列挙し、自作18ファイルの本文と参照を確認。sourceへの本文/設定/素材集約、図4部品のinclude化、custom.cssの配色と配置への分割、旧生成物/未使用候補、CI/検査/配置名追従への影響を記録。提案のみで製品ファイルの移動・変更/ビルド/Maya起動なし。詳細 .maya-output/mlib-docs-layout-proposal-20261025/proposal.txt、全配置 inventory.json。

- Codex (2026-10-25 17:48 JST): ユーザー指示でmlib文書を日本語のみに整理。英訳PO/MO・言語切替テンプレート・gettext設定・英語タイトル補正・英訳手順を削除し、共有翻訳CLIはmlibを更新前に拒否。共有workflowはユーザー承認の3行削除だけを適用しHTools追加/他3ツールの翻訳を保持。日本語332HTML/警告0、切替以外のDOMと2041参照・159図不変、18162ローカルリンク/ブラウザ4条件/既存24テスト成功。標準ローカルHTMLを同期し旧en出力を除去。製品315Python不変、Maya未起動・未commit/push。証跡 .maya-output/mlib-docs-ja-only-20261025/。

- Codex (2026-10-25 17:38 JST): mlib/_docsを初心者向けに整理。conf.pyを197→67行の設定中心にし、既存の継承図/署名補完/表示補正を_extへ集約。READMEへ編集先・初回準備・直接Sphinxビルド・英訳・検査の手順、_extへ処理の案内を追加。Git対象外の旧調査4ファイルをdocs/researchへ保存移動。前後の日英各332HTMLと各2041参照が一致、各159図/全37652ローカルリンク・ブラウザ8条件/既存24テスト・公開検査成功。製品/テスト315Pythonのhash不変、Maya未起動・未commit/push。証跡 .maya-output/mlib-docs-beginner-20261025/。

- Codex (2026-10-25): ユーザー指示で残り未コミット全4ファイル（QuickPathExplorerの共有タブ/ドックサイズ・列幅修正、GUI検証スクリプト、共有作業ログ）をコミット・push対象として確認。Python3ファイルの構文と差分検査成功、既存Maya2027専用GUIの5確認成功・終了0・crash dumpなしの記録を確認。今回はGUIを再実行せず、生成物/調査資料はGit対象外を維持。

- Codex (2026-10-25 11:22 JST): ユーザー指示でSphinx導入説明復元・全体幅/右目次調整の6ファイルと今回の記録をコミットし、c74751cをorigin/mainへpush。ls-remoteのSHA一致とahead/behind 0/0を確認。日英Sphinx警告0・32表示条件の検証済み差分と一致し、別作業のQPE/共有WORK_LOG差分を保持。

- Codex (2026-10-25): mlib Sphinxの導入3ページを再構成し、なぜmlibの責務表・継承図・操作例を復元して現行API/英訳へ同期。全体最大幅1600px・右目次280〜360px・長名折返し・ナビ回り込み修正を適用し、継承図の配置/寸法を維持。日英各332HTML/警告0・全参照・7画面幅を含む32表示条件を検証。

- Codex (2026-10-25): 承認済みのmlib Sphinx全体幅/右目次調整をcustom.cssへ実装。最大1600px、目次280〜360px、目次の長名折返し、ナビfloat包含を適用。継承図のソース/寸法/配置を維持し、日英各332HTML/警告0・全参照、7画面幅を含む32表示条件と目次14クリックを確認。標準ローカルHTMLを同期、他文書/英訳/実装は今回無変更。未commit/push。証跡 .maya-output/mlib-layout-width-20261025/result.json。

- Codex (2026-10-25): mlib Sphinx全体幅・右目次を検討。図の配置/寸法は維持し、最大幅1200→1600px、目次240→280〜360px、目次内の長名折返しとナビfloatの包含を試作。Joint/whyを390〜1920pxの7幅14条件で確認し、目次はみ出し/ページ横スクロール0、図寸法不変。1366px以上の確認幅では数学図全体も表示可能。検討のみで製品CSS/文書は未変更。証跡 .maya-output/mlib-page-width-20261025/result.json。

- Codex (2026-10-25): mlibクラス図のはみ出しを調査。数学図937pxに対し本文892px/スマホ356pxを確認。数学4型の小図をPC2列/狭幅1列にする案と空欄省略を隔離ブラウザ5幅（320〜1440px）で試作し、文字実寸/はみ出し0/8リンク保持を確認。API大図は一律縮小しない方針を提案。検討・試作のみ、製品文書/実装は変更なし。証跡 .maya-output/mlib-class-diagrams-20261025/result.json。

- Codex (2026-10-25): mlibのSphinxを指定3ページ・19小見出しへ再構成。なぜmlibの説明/責務表/4継承図/操作例を復元し現行APIと照合、入門とモジュール分類も復元。英訳同期、日英各332HTML/警告0、参照とPC/スマホ幅の図・クリックを確認。数学図は実寸と横スクロールへ統一。170実装hash不変、13コード例は構文/実装照合まで（Maya未実行）。標準HTML同期済み、未commit/push。詳細 .maya-output/mlib-docs-restore-20261025/result.json。

- Codex (2026-10-25 10:27 JST): ユーザー指示でmlib文書修正126ファイルをcommit/push。`ba32d28`をorigin/mainへ送信しリモートSHA一致・ahead/behind 0/0を確認。実行170AST不変、直前の公開/diff検査成功、日英各332HTML/警告0の完了証拠を確認。共有WORK_LOGは今回の文書完了行だけコミットし、別作業と生成物は保持。

- Codex (2026-10-25 10:00 JST): mlib文書3時間枠を連続作業で完了。指定4項目へ整理し独立39章を削除。docstring 261件を実体へ同期、変更本文約19%短縮。日英各332HTML/警告0、全ローカル参照・英訳・170ファイルの実行AST/署名/既定値不変を確認。実読/修正1082定義、未確認624定義と未実測の実装懸念4件を台帳へ保持。Maya/commit/push/公開なし。詳細 .maya-output/mlib-docs-3h-20261025/result.json。 スケジュールmlib-6は削除成功と設定ファイル消失を確認。

- Codex (2026-10-25 09:46 JST): mlib文書3h 第6段階batch7。Matrix再構成失敗時の部分更新、Quaternionのspin/鏡映、BlendShapeの復元試行とNodeの並び替え不要時の条件を実態へ同期。日英各332HTML/警告0、全参照・英訳・実行AST/署名不変を確認し、標準html/en出力も同期。最終監査・台帳集約を継続、未commit/push。

- Claude Code (2026-10-25): mlrig 12時間拡張 第33回。`mlrig.setups.BoxRoll`(正方形の断面の箱を角度 roll で縁から縁へ転がす。floor で90度の段に分けて支点の縁を進める標準DG)を追加。試験7件(2027/2025)、setups回帰535件(2027/2025)、Setup Samples に1項目(計58、隔離2027 GUIで全項目確認)、Sphinx警告0、検証動画をローカルとDriveへ保存。未コミット。

- Codex (2026-10-25 09:38 JST): mlib文書3h 第6段階batch6。内部回転変換のrotate以外XYZという規則と、チャンネル設定のsafe捕捉範囲/委譲先を訂正。日英Sphinx・英訳・参照・実行AST/署名不変を検証し、全体最終確認へ。未commit/push。

- Codex (2026-10-25 09:33 JST): mlib文書3h 第6段階batch5。Transformationの保持参照と独立値/成分置換3件、Nodeの削除済みplug案内と子override説明2件を本文へ同期。Component55定義は重大差なしとして無変更維持。日英Sphinx/新16訳・Args表示・全ローカル参照・170実行AST/署名不変を確認。未commit/push、期限まで最終収束。
- Claude Code (2026-10-25 09:30 JST): mlrig 12時間拡張・第32回完了。`setups/hipSwing.py`(振りのコントロールの回転で腰だけを支点の周りに振り、背骨の根元から上の向きを stabilize の割合で保つ。支点の枠で見た回転の差の行列の式、逆行列ノード不使用)と試験7件・rst・`tools/demo_hip_swing.py`を追加し、setups/__init__・docs/index・setup_samples(.py/.rst)・test_setup_samples・tools/test_rig_packages.py へ行を追加(Setup Samples 57項目)。Maya 2027/2025で新規7件・samples・setups回帰528件合格、Sphinx警告0、隔離GUIでメニュー全項目と録画を確認。未コミット。

- Codex (2026-10-25 09:26 JST): mlib文書3h 第6段階batch4。addAttrの全87引数を保持し、型優先・子override・fast追加・返却を明確化。Transformの拘束入力/フリーズ/mirror、PluginPackageの版有無での分岐/例外/結果定数、logger通知を簡潔化。13doc（属性doc3含む）を同期し、日英Sphinx・英訳・ローカル参照・実行AST/署名/定数値不変を検証。未実測のfast time子懸念は別記録、期限まで継続・未commit/push。

- Codex (2026-10-25 09:17 JST): mlib文書3h 第6段階batch3。ピボット・形状/Joint/Skin/Set/Container/DagPoseの説明を実装順へ同期。既存fast拒否前更新2経路は未解消課題として記録し製品実装を変更せず。日英Sphinx・新訳・参照・実行AST/署名不変を検証。期限まで継続、未commit/push。
- Claude Code (2026-10-25 09:12 JST): mlrig 12時間拡張・第31回完了。`setups/unevenGround.py`(平らな床で付けた足と腰を、足ごとの地面の平面の高さ・傾きへ接地させる後処理。腰は低い方の足に合わせる)と試験8件・rst・`tools/demo_uneven_ground.py`・Setup Samplesの項目(計56)を追加。試験 2027/2025 8件OK、setups回帰 2027/2025 521件OK、Sphinx警告0、隔離GUIでメニュー56項目の作成・選択・1枚絵OK。未コミット。


- Codex (2026-10-25 09:08 JST): mlib文書3h 第6段階batch2。演算13ファイル88 docstringを本文照合し、重複Undo説明をクラスへ集約。有限行列保証・ターゲット削除時の接続保持という誤記を修正。19492→17505字。新76訳＋関連既存誤訳1件、日英332HTML/警告0・176要約＋入門2assert・4checker・170実行AST/署名不変・diff検査成功。期限まで継続、未commit/push。
- Codex (2026-10-25 08:57 JST): mlib文書3時間・第6段階batch1完了、全体作業は継続。Node/Nodes・commonの21説明と入門1文を修正。全件事前検査と保持順検査、参照/容器、名前空間復元、ScriptJob登録寿命、単位の数値を照合。実行170AST/署名/py37不変、日英332HTMLずつ・警告0、catalog7542（新87/削除88/共通7455訳不変）、本文44確認/4checker成功。Maya未起動、commit/pushなし。詳細.maya-output/mlib-docs-3h-20261025/run6/batch1/。

- Codex (2026-10-25 08:45 JST): mlib文書3時間・第5段階完了。数学/core/decorator/utilの23説明を11178→7316文字へ整理。演算/所有権/Itを維持し、UI単位切替・非Joint拒否・Undo復旧・reload保持参照/拡張・登録検証範囲を照合。空行末尾空白を修正しdiff成功、実行170AST/署名/py37不変、公開0/layout186違反0、日英332HTMLずつ・警告0、catalog7543（新89/削除110/共通7454訳不変）。Maya未起動、commit/pushなし。詳細.maya-output/mlib-docs-3h-20261025/run5/。

- Codex (2026-10-25 08:37 JST): mlib文書3時間・第4段階完了。Component/UV/Mesh/NurbsCurve/SkinCluster/BlendShape/AnimCurveの21説明を10296→9179文字へ整理。通常Undo/fast、周期CV/保持順、reorder無変更時、aliasとinfluence番号/配列順を照合。実行170AST/署名/py37不変、日英332HTMLずつ・警告0、catalog7564（新116/削除104/共通7448訳不変）、未訳/fuzzy/記法0。Maya未起動、commit/pushなし。詳細.maya-output/mlib-docs-3h-20261025/run4/。

- Codex (2026-10-25 08:28 JST): mlib文書3時間・第3段階完了。Plug関連27説明を13016→10755文字へ整理。safe部分更新・単位・接続既定・配列番号・Message旧名を照合。実行170AST/署名/py37不変、公開0/layout186違反0、日英332HTMLずつ・警告0、catalog7552（新159/削除157/共通7393訳不変）、未訳/fuzzy/記法0。確認50定義修正/27定義確認/1629未確認。Maya未起動、commit/pushなし。ユーザー指示で待機なし連続作業へ変更。詳細.maya-output/mlib-docs-3h-20261025/run3/。

- Claude Code (2026-10-25 08:50): mlrig 12時間拡張 第30回。OverShoulderCamera がカメラ自身の parentInverseMatrix を translate の計算に使う形を、親の移動・offsetParentMatrix・キーの時間・DG/serial/parallel の各評価で確認(再現せず、誤差1.4e-6cm=単精度の丸め。駆動するのは translate・rotate で offsetParentMatrix ではないため循環しない)→試験を1件追加しコメントで理由を明記。ほかの setups の parentInverseMatrix・parentMatrix の使用(leafJoints・limbPin・bowString・piston・outlineBank)も確認し問題なし。ネットの情報(Catch light・Blinn-Phong の half vector など)から、目のハイライトをカメラと光の中間の向きの眼球の表面へ置く `mlrig/setups/eyeHighlight.py`(EyeHighlight。follow・radius・weight、aimMatrix等の標準ノードのみ)と試験9件・docs/eye_highlight.rst・tools/demo_eye_highlight.py・Setup Samples の項目(計55)を追加。2027/2025で setups回帰513件OK、Sphinx警告0、隔離GUIで検証動画とメニュー全項目を確認。未commit。
- Claude Code (2026-10-25 08:27): mlrig 12時間拡張 第29回。既存のモジュラーリグ(mGearのミラーポーズ、MIT、コード流用なし)の考え方で、片側のコントロールのワールド行列を対称面(キャラクターのルート等)で鏡に映し反対側のコントロールの offsetParentMatrix へ常に写す `mlrig/setups/liveMirror.py`(LiveMirror。flip=behavior/x/y/z、maintainOffset、weight、target自身のTRSは上乗せ用に空ける、multMatrix・blendMatrixのみ)と試験7件・docs/live_mirror.rst・tools/demo_live_mirror.py・Setup Samples の項目(計54)を追加。2027/2025で試験・samples合格、setups回帰503件OK、Sphinx警告0、隔離GUIで検証動画とメニュー全項目を確認。未commit。
- Codex (2026-10-25 08:04 JST): mlib文書3時間整理の第2枠。Node/DagNode/Transform/Jointの20docstringsを実装へ照合し10127→8381文字へ整理。Node.createの親入力/共有返却/長短競合/Shapeの暗黙親、DAGパス借用/親・子の探索/同一性、OPMのlocal/world差・Euler解/get/safe/fast、Jointの回転移送とinverseScale接続を明確化。getClassificationの分類なしを空リストとする誤説明を現実装の[空文字列]へ訂正。日英各332ページ/警告0、20説明の40要約読戻し・4項目ナビ・旧39章/リンク不在・両言語4検査成功。catalog7550件、新111/削除98/共通7439訳保持、未訳/fuzzy/記法問題0。実行170ファイルのAST/署名/デコレーター不変とPython3.7構文、公開/layout186/diff検査成功。Maya・ブラウザ未実行、未コミット。証拠: `.maya-output/mlib-docs-3h-20261025/run2/`。

- Claude Code (2026-10-25 08:06): mlrig 12時間拡張 第28回。会話する2人の頭の位置から肩越しのカメラの位置・向きを決める `mlrig/setups/overShoulderCamera.py`(OverShoulderCamera。2人を結ぶ線の片側に角度・距離・高さで置き、写す人物の頭をフィルムゲートの指定位置(三分割など)へ写すよう平行移動、作成時の姿勢から weight で補間、標準ノードのみ)と試験7件・rst・検証デモ・Setup Samples の項目(計53)を追加。2027/2025で試験・samples合格、setups回帰496件OK、Sphinx警告0、隔離GUIでメニュー全項目確認。未commit。
- Claude Code (2026-10-25 07:52): mlrig 12時間拡張 第27回。ネットの事例(Wikipedia「Dolly zoom」等)からカメラのドリーズーム `mlrig/setups/dollyZoom.py`(視線方向の距離に比例した焦点距離・横の画角、標準ノードのみ)と試験 test_setup_dolly_zoom(7件)・docs/dolly_zoom.rst・tools/demo_dolly_zoom.py を追加。Setup Samples に「DollyZoom - camera keeps the subject size」を追加(52項目、隔離Maya 2027 GUIで全項目確認)。setups回帰 2027/2025とも489件OK、Sphinx警告0。未コミット。
- Codex (2026-10-25 07:34 JST): mlib文書3時間整理の第1枠。公開の手書き章を指定4項目へ整理し、インストール・パッケージ名変更を含む39章を削除。残る本文633→134行、7コマンドの重複説明8506→1801文字。Object/Node/Plugの説明を実装照合し、返却型・Undo有効時・safe例外・長短名の併用規則等の過剰な断定と古い参照を修正。API参照325ページは維持。日英Sphinx各332ページ/警告0、4項目ナビ・旧章/リンク不在・継承図リンク・get/is名/7入口の署名検査を確認。共通7467訳を保持し、新70訳/削除1526件、未訳/fuzzy/記法問題0。実行170ファイルのAST不変/Python3.7構文、ホスト53テスト、公開/layout186/diff検査成功。Maya・ブラウザ未実行、未コミット。証拠: `.maya-output/mlib-docs-3h-20261025/run1/`。
- Claude Code (2026-10-25 07:30): mlrig 12時間拡張 第26回。体節の質量の割合から全身の重心・床への投影・両足の中点からのずれ(balance)を求める `setups/centerOfMass.py`(CenterOfMass、wtAddMatrixの重みで加重平均、plusMinusAverage・multiplyDivide・clamp・decomposeMatrix・composeMatrix・distanceBetween、人体の体節の表 DEMPSTER、Python版 center())を追加。試験 `test_setup_center_of_mass.py` 7件(2027/2025合格)、setups回帰 482件(2027/2025)、Setup Samplesに「CenterOfMass - stick figure balance」を追加(51項目、test_setup_samples合格・隔離GUIで全項目確認)、docs/center_of_mass.rst(Sphinx警告0)、tools/demo_center_of_mass.py。未コミット。
- Claude Code (2026-10-25 07:12): mlrig 12時間拡張 第25回。水面に浮かぶ物体を時間で進むトロコイド波の和の面に乗せる `setups/waveFloat.py`(WaveFloat、composeMatrix+vectorProductのsin/cos、変位の偏微分から面の法線、blendMatrixで傾きの割合、時間の積分なし・既定の振幅0で作成時に跳ねない)を追加。Setup Samplesに「WaveFloat - boat on waves」(計50項目)。試験7件・samples 6件を2027/2025で合格、setups回帰2027/2025とも475件OK、Sphinx警告0、隔離2027 GUIで検証動画(passed)とメニュー50項目の作成・選択・1枚絵を確認。未commit。
- Claude Code (2026-10-25 06:52): mlrig 12時間拡張 第24回。頭のコントロールの回転を首の関節へ累積の割合で分配し、頭はコントロールの向きに合わせる `setups/neckHeadSplit.py`(NeckHeadSplit、multMatrix・pickMatrix・blendMatrix、各関節のワールド行列を出力)を追加。試験 `test_setup_neck_head_split.py` 7件、Setup Samples の項目(計49)、`docs/neck_head_split.rst`、`tools/demo_neck_head_split.py`。2027/2025で setups 468件OK、Sphinx警告0、隔離GUIでメニュー全項目を確認。未コミット。

- Codex (2026-10-25): mlib完了分をcommit/push（このコミット）。本体・日英説明・引数/fast/safe明示化と必要なmlrig JointHierarchy使用側を対象とし、別作業のmlrig追加・QuickPathExplorer・submoduleを保持。前回検証時のPython318素材とJointHierarchyの一致、公開/layout/diffの成功を確認。前回全Maya2022〜2027各1227件/計7362件（既存条件27skip）・使用側383件・日英各371ページ/警告0の証拠を再利用。今回は製品の追加修正なし。横断複雑性をソースと既存テストで調べ、複数形の準備/実行、値更新、TRS、Component、定義追加等の保守候補と仕様判断が必要な保証を区分してGit対象外へ記録。調査によるMaya再起動・性能測定はなし。証拠: `.maya-output/mlib-complexity-audit-20261025/`。

- Claude Code (2026-10-25 06:40): mlrig 12時間拡張 第23回。兄弟として並べたコントロールを、前のコントロールの子のように動かす仮想のFK階層 `setups/virtualChain.py`(VirtualChain、multMatrix + blendMatrix で offsetParentMatrix へ接続、つなぎごとの follow)を追加。試験 `test_setup_virtual_chain.py`、Setup Samples の項目(計48)、`docs/virtual_chain.rst`、`tools/demo_virtual_chain.py`。2027/2025で setups 461件OK、Sphinx警告0、隔離GUIでメニュー全項目を確認。未コミット。
- Claude Code (2026-10-25 06:22): mlrig 12時間拡張 第22回。補正シェイプ・補助骨用に、複数のウェイトの組み合わせ(積/最小)と途中の山形のウェイトを標準ノード(clamp・animBlendNodeAdditive・condition)で求める `setups/comboWeight.py`(ComboWeight)を追加。試験 `test_setup_combo_weight.py` 8件(実際のブレンドシェイプでの補正を含む)は Maya 2027/2025 とも合格、setups回帰 454件OK(2027/2025)。`setupSamples.py` に「ComboWeight - smile combo corrective」(計47項目)と test_setup_samples・tools/test_rig_packages.py・docs(combo_weight.rst・index・setup_samples)へ追加、Sphinx警告0。`tools/demo_combo_weight.py` で隔離Maya 2027 GUIの検証動画(312フレーム全ok)と、メニュー全47項目の作成・選択・1枚絵をGUIで確認。未コミット。
- Claude Code (2026-10-25 06:00): mlrig 12時間拡張 第21回。ネットの公開資料(lesterbanks.comのシザーアームのリグの記事、The Rookiesの手続き的なシザーリフトの解説、Autodesk Forumsのシザー機構のスレッド)を参考に、台の高さ1つからX字の腕・台・滑る足のワールド行列を三平方の式で求める `mlrig/setups/scissorLift.py`(ScissorLift、標準ノードのみ・IKなし)を追加。試験8件(2027/2025合格)、setups回帰 2027/2025 各446件OK、Setup Samplesへ追加(46項目、隔離2027 GUIで全項目の作成・選択・1枚絵を確認)、rst追加・Sphinx警告0、検証動画(全フレームok)をローカルとDriveに保存。未コミット。
- Claude Code (2026-10-25 05:52): mlrig 12時間拡張 第20回。既存のモジュラーリグ(mikanのbank、MIT、コード流用なし)の考え方で、底の輪郭の曲線の上を傾けた向きに合わせて支点が動く傾き `mlrig/setups/outlineBank.py`(OutlineBank)を追加。標準ノード(composeMatrix・multMatrix・vectorProduct・nearestPointOnCurve 等)のみ、回転0で跳ねない。試験8件、setups回帰 2027/2025 各438件OK、Setup Samplesへ追加(45項目、隔離2027 GUIで全項目の作成・選択・1枚絵を確認)、rst追加・Sphinx警告0、検証動画をローカルとDriveに保存。未コミット。
- Claude Code (2026-10-25): mlrig 12時間拡張 第19回。体格のパラメーター(clamp付き、正負で別の量)で体格調整用の骨の移動・スケールを変える `setups/bodyProportion.py`(BodyProportion)を標準ノードで追加。Setup Samplesメニューに1項目追加(計44)、試験9件(2027/2025合格)、setups回帰430件OK(2027/2025)、Sphinx警告0、隔離Maya 2027 GUIでメニュー全項目と検証動画を確認。未コミット。
- Claude Code (2026-10-25 05:08): mlrig 12時間拡張 第18回。ネットの公開資料(Lester Banksのアッカーマンのステアリングの記事、Firgelli・edumechのアッカーマンの原理の解説)を参考に、`mlrig.setups.AckermannSteering`(1つの切れ角またはハンドルの回転から、左右の前輪の角度を内輪 atan(L/(R-T/2))・外輪 atan(L/(R+T/2)) で求め、ackermannの割合で平行の切れ方と混ぜる。標準ノードのみ)・試験8件・ackermann_steering.rst・tools/demo_ackermann_steering.py・Setup Samplesに1項目(計43、隔離GUIで全項目の作成・選択・1枚絵を確認)。試験は2027/2025全件合格、setups回帰421件OK(2027/2025)、Sphinx警告0、検証動画をローカルとDriveへ保存。未コミット。
- Claude Code (2026-10-25): mlrig 12時間拡張 第17回。`mlrig/setups/limbPin.py`(LimbPin: 2関節の中間・先端の骨の長さを、合計を保つslideと、肘・膝を極ベクトルの操作子へ留めるpinで駆動。標準ノードのみ、IKは標準のikRPsolverのまま)・試験7件・limb_pin.rst・tools/demo_limb_pin.py・Setup Samplesに1項目(計42)。試験は2027/2025全件合格、setups回帰413件OK(2027/2025)、Sphinx警告0、検証動画をローカルとDriveへ保存。未コミット。
- Claude Code (2026-10-25 04:30): mlrig 12時間拡張 第16回。不均一なscaleを扱えない書き出し先向けの一般的な方法(階層の末端の葉のjointにscaleを持たせる)を参考に、`mlrig.setups.LeafJoints`(入力の節ごとに位置と回転だけの枝のjointと、その子でscaleだけを受け持つ葉のjointを作り、pickMatrix・multMatrix・decomposeMatrixで入力のワールド行列へ追従。jointOrient 0・segmentScaleCompensateオフで親子の積だけの書き出し先でも一致、標準ノードのみ)を追加。Setup Samplesメニューに1項目(計41、隔離GUIで全項目の作成・選択・1枚絵を確認)、試験8件(2027/2025合格)、samples 6件・setups回帰406件(2027/2025)、Sphinx警告0、検証動画(隔離Maya 2027、全フレームok)。未コミット。
- Claude Code (2026-10-25 04:20): mlrig夜間タスク(1日1モジュール)は実装せず終了。同じClaude Codeの「mlrig 12時間拡張」(11:00ごろまで、未コミット運用)が mlrig/setups・setups/__init__.py・docs/index.rst・setup_samples.rst・tools/test_rig_packages.py を約15分ごとに編集中で、新しいモジュール/レイヤーの登録先と重なるため。コード変更・コミット・プッシュなし。
- Claude Code (2026-10-25 04:10): mlrig 12時間拡張 第15回。ネットの公開資料(80.lvのMayaの手続き的な懸垂線の記事、John D. Cookのケーブルの垂れの近似の記事)を参考に、`mlrig.setups.CableSag`(2つの留め具の間で長さlengthを保って垂れるケーブルの点のワールド行列。深さはJ. S. Frameの懸垂線の近似 h²=(L-D)(2L+D)/8、形は放物線、枠はケーブルに沿うX・重力と反対側のY、標準ノードのみ)を追加。Setup Samplesメニューに1項目(計40)、試験9件(2027/2025合格)、samples 6件・setups回帰398件(2027/2025)、Sphinx警告0、検証動画(隔離Maya 2027、全フレームok)。未コミット。
- Claude Code (2026-10-25 03:58): mlrig 12時間拡張 第14回。既存のモジュラーリグ(mgear5のchain_net_01、MIT・考え方のみ)を参考に、`mlrig.setups.ChainNet`(2本の親チェーンの各節の生成時からの差を、間の子チェーンの同じ番号の節へblendMatrixでbiasの割合に混ぜ、子の節の生成時のローカル空間でoffsetParentMatrixへ加える。子の手付けは上に重なる。標準ノードのみ)を追加。試験 `test_setup_chain_net.py` 8件・samples 6件を2027/2025で合格、setups回帰389件OK(2027/2025)、Sphinx警告0、検証動画 `tools/demo_chain_net.py`。Setup Samplesメニューへ「ChainNet - fin with two master chains」を追加(39項目、隔離GUIで全項目確認)。未コミット。
- Claude Code (2026-10-25 03:42): mlrig 12時間拡張 第13回。機械のリグでピストン・クランクを連動させる一般的な作り方を参考に、`mlrig/setups/crankSlider.py`(CrankSlider: クランクのピンの位置からロッドの長さの球とシリンダーの軸の交点でピストンの移動量を求め、ピストンとロッドのワールド行列を標準ノードで出力)を追加。試験 test_setup_crank_slider 8件、setups回帰381件(2027/2025)、Sphinx警告0、検証動画(ローカル・Drive)。Setup Samplesに1項目追加(計38)し、隔離Maya 2027 GUIで全項目の作成・選択・画像を確認。未コミット。
- Claude Code (2026-10-25 03:23): mlrig 12時間拡張 第12回。ネットの公開資料(tech-artists.orgのmotion pathの履帯のスレッド、Lester Banksの戦車のリグ・動く支点(dynamic pivot)の記事)を参考に、`mlrig.setups.TreadBelt`(閉じた曲線の上にcount枚の板を弧長で等間隔に並べ、distance/曲線の長さの割合をcycleの外挿のanimCurveUUで0〜1へ折り返してmotionPath(fractionMode・objectRotationの上方向)で巡回させる。driverの変化量で送り、板は裏返らない)と`mlrig.setups.RockerRoll`(半径radiusの円弧の底をroll角だけ滑らずに転がし、支点を円弧上の接地点へ移す行列)を標準ノードで追加。Setup Samplesに2項目(計37)、試験8件・6件、tools/demo_tread_belt.py・demo_rocker_roll.py、rst 2件。2027/2025で新規試験・samples・cmds境界・setups回帰373件成功、Sphinx警告0、検証動画2本(全フレームok)。共有ファイルは行の追加のみ。未コミット。
- Claude Code (2026-10-25 03:05): mlrig 12時間拡張 第11回。既存のモジュラーリグ(mgear5のui_slider_01、crabのsticky_patch、いずれもMIT・考え方のみ)を参考に、`mlrig.setups.UiSlider`(枠の中だけを動くスライダーのコントロールをtransformLimitsで制限し、size で正規化した位置・方向ごと・角ごとの0〜1の重みを出力)と `mlrig.setups.StickyControl`(proximityPinでコントロールを変形するメッシュの表面に貼り付け、offsetParentMatrixへ接続。形のデータが持つ変換行列を生成時に打ち消し、前の段のデフォーマーの出力を渡して二重の変形を避けられる)を追加。Setup Samplesに2項目(計35項目)、試験(各8件)・rst・検証デモ(tools/demo_ui_slider.py・demo_sticky_control.py)を追加。隔離Maya 2027 GUIでメニュー35項目の作成・選択・1枚絵を確認。2027/2025のsetups回帰合格。未コミット。
- Claude Code (2026-10-25 02:36): mlrig 12時間拡張 第10回。補助骨の一般的な使い方(脚を上げるとスカートの根元を自動でずらして、めり込んでいない姿勢から揺れ物を始める・既存の補助骨の挙動を制御用の値で加算的に増幅する)を元に、`mlrig.setups.SkirtLegOffset`(骨ごとの開く面へ写した脚の角度からclearance・spread・maxAngleで開く角度を求め、offsetParentMatrixへ接続できる回転を出す)と`mlrig.setups.PumpUp`(補助骨の生成時からの位置・スケールの変化をpump×gainで増やしoffsetを足す)を標準ノードで追加。Setup Samplesに2項目(計33)、試験8件・7件・samplesは2027/2025合格、setups回帰343件OK(2027/2025)、Sphinx警告0、検証動画2本(全フレームok)。共有ファイルは行の追加のみ。未コミット。
- Claude Code (2026-10-25 02:06): mlrig 12時間拡張 第9回。ネットの公開資料(no-flip kneeのチュートリアル・フォーラム・Mayaヘルプ、歯車の比で駆動する講座)を参考に、`mlrig.setups.NoFlipPole`(付け根→先端の軸と足のコントロールの前の向きのaimMatrixの枠から、脚の軸に垂直な面上にポールを置く。midで生成時の膝の向きをoffsetに入れ跳ねない、kneeTwistで回す)と`mlrig.setups.GearTrain`(歯数の比でかみ合う/同じ軸の歯車を駆動側の回転に連動、animBlendNodeAdditiveDAで単位変換なし)を追加。Setup Samplesに2項目(計31、隔離GUIで全項目確認)。試験8+8件・samples・cmds境界は2027/2025合格、setups回帰328件OK(2027/2025)、Sphinx警告0、検証動画2本(全フレームok)。未コミット。
- Claude Code (2026-10-25 01:45): mlrig 12時間拡張 第8回。既存のモジュラーリグ(mgear5のchain_01、mikanのslide FK chain、いずれもMIT・考え方のみ)を参考に、`mlrig.setups.FkIkChain`(FK/IKの2チェーンをblendで切り替え。親の節に対する相対行列を混ぜて節の長さを保つ既定とworld、表示の切り替え出力、matchFkToIk)と `mlrig.setups.SlidingFk`(チェーン上の位置とfalloffを持つFKコントロールの回転を正規化した三角形の重みで節へ割り振る)を標準ノードで追加。試験(9件・8件)・rst・tools/demo_fk_ik_chain.py・tools/demo_sliding_fk.py・Setup Samplesの2項目を追加。setups回帰は2027/2025とも312件OK、Sphinx警告0、検証動画は全フレームok。未コミット。
- Claude Code (2026-10-25 01:25): mlrig 12時間拡張 第7回。隔離Maya 2027 GUIでmlrigメニューの「Setup Samples」を確認(26項目→追加後27項目、全項目の作成・選択・1枚絵OK)。カメラの角度に応じて顔の補正を混ぜる一般的な方法を元に `mlrig.setups.CameraAngleReader`(頭から見たカメラの水平角・垂直角と、正面・左・右・上・下・後ろの和が1で連続な重み、標準ノードのみ)を追加し、メニューのサンプル・test_setup_camera_angle_reader(8件)・test_setup_samples・tools/test_rig_packages.py・Sphinx(camera_angle_reader.rst)・tools/demo_camera_angle_reader.py を更新。2027/2025でsetups 295件合格、Sphinx警告0。未コミット。
- Claude Code (2026-10-25 01:10): mlrig 12時間拡張 第6回。ネットの公開記事・ドキュメント(行列ノードによる床との接触、cmt(MIT)のblendMatrixによる空間切り替え、maya-pulseのSpaces)を参考に、`mlrig.setups.PlaneCollision`(平面からの距離をsoftnessの帯で指数的に漸近させて法線方向へ押し出す)と`SpaceBlend`(空間ごとのoffset付き追従先をblendMatrixで混ぜ、割合w_i/(w_0+…+w_i)で重み付き平均にする)を標準ノードで追加。setupSamplesに2項目(計26)、試験8件・8件、tools/demo_plane_collision.py・demo_space_blend.py、rst 2件。Maya2027/2025で新規試験・samples・setups回帰287件成功、Sphinx警告0、検証動画2本(全フレームok)をローカルとDriveの検証動画フォルダへ保存。共有ファイル(setups/__init__.py・docs/index.rst・setup_samples.rst・test_setup_samples.py・tools/test_rig_packages.py)は行の追加のみ。未コミット。

- Claude Code (2026-10-25): mlrig 12時間拡張 第5回。既存のモジュラーリグ(mgear5の唇リグと4辺のsquash部品、いずれもMIT・考え方のみ)を参考に、`mlrig.setups.LipZip`(上唇・下唇を口角から順に閉じ合わせる)と`SquashBox`(4辺の押し引きによる体積近似付きの潰し・伸ばし)を標準ノードで追加。setupSamplesに2項目(計24)、試験6件・8件、setups回帰2027/2025とも271件OK、Sphinx警告0、検証動画2本(ローカルとDrive)。未コミット。
- Claude Code (2026-10-25): mlrig 12時間拡張 第4回。補助骨で筋肉の膨らみを表す一般的な方法を元に `setups/muscleBulge.py`(子の関節の曲げ量で親の骨の上の補助骨を開始角付きsmoothstepで膨らませ押し出す)、4足の接地に合わせて腰を傾ける一般的な方法を元に `setups/groundTilt.py`(4本の足の面の回転差をslerpで胴体へ加え、平均の高さの変化で上下)を標準ノードで追加。setupSamplesへ2項目(計22)、試験9件・6件、rst 2件、tools/demo_muscle_bulge.py・demo_ground_tilt.py。Maya2027/2025で新規試験・samples・setups回帰257件成功、Sphinx警告0、検証動画2本(全フレームok)をローカルとDriveの検証動画フォルダへ保存。未コミット。

- 2026-10-25 00:10 Claude Code: mlrigに`mlrig/setups/footRoll.py`(FootRoll、1つのrollでかかと→母指球→breakAngle超過でつま先へ支点を移す逆足。bankで内外の縁、swivel・toeTapは母指球中心。clamp・composeMatrix・multMatrixの行列の積で逆足の階層と同じ計算、標準ノードのみ)を追加。試験(rotatePivotの逆足の階層と比較)・rst・`tools/demo_foot_roll.py`を追加し、Setup Samplesメニューに1項目を追加(setupSamples.py・test_setup_samples.py・setups/__init__.py・docs/index.rst・setup_samples.rst・tools/test_rig_packages.pyは行の追加のみ)。試験 foot_roll 9件・samples 6件、setups回帰242件を2027/2025で合格、Sphinx警告0。未コミット。

- Codex (2026-10-25 00:04 JST): mlibの長短フラグ引数を明示化。`_flag_aliases`製品151箇所とhelp実行時解析/別名メタデータを撤去し、通常のdefと本文で省略/競合を検証。長短名・位置引数順・実行時既定値/単位/返却・fast/safeを維持。予約語as/isだけ辞書指定、内部_UNSETは省略判定専用。callEachの形式は全件先行検査、長短競合/必須sentinelは各単数本文で保持順検査とし、後続失敗時の先行変更/通常1回Undo・fast履歴不変を説明/検証。初回の旧署名/例外型期待3ファイルと重点ランナーのreload順を修正。Maya2022〜2027各137ファイル/1227件、合計7362件・失敗0/既存条件27skip、利用側は並行追加を含む59ファイル/383件成功（前回54/347との差を区別）。host53件・公開/Python3.7/layout/diff成功。日英各371ページSphinx警告0、155署名と重要説明を照合、PO8993件/既存残存訳変更・未訳/fuzzy/記法0。Maya native説明の型/既定値/親指定/fast制限も実装照合して修正。既存差分・他作業・submodule保持、未commit/未push。GUI・速度未計測。証拠: `.maya-output/mlib-explicit-flags-20261024/result.json`。

- 2026-10-24 23:55 Claude Code: mlrigに新セットアップ2件を追加。`mlrig/setups/ribbon.py`(コントロールを断面にしたloftの帯とuvPinで中心線上の行列を出すリボン、標準ノードのみ)と`mlrig/setups/metaSpread.py`(両端jointの回転差をblendMatrixで間のjointへ割合で分配)。試験・rst・`tools/demo_ribbon.py`・`tools/demo_meta_spread.py`を追加し、Setup Samplesメニューに2項目を追加(setupSamples.py・test_setup_samples.pyは行の追加のみ)。試験 ribbon 9件・meta_spread 6件・samples 6件、setups回帰233件を2027/2025で合格、Sphinx警告0。未コミット。
- 2026-10-24 23:25 Claude Code: mlrigメニューに「Setup Samples」サブメニューを追加(`mlrig/setupSamples.py`新規、menu.pyは項目と`setup:`分岐の追加のみ)。setupsの17種類を現在のシーンへ作って試せる。新セットアップ `mlrig/setups/bowString.py`(弓の弦の向き・長さ・引き量、標準ノードのみ)と試験・rst・`tools/demo_bow_string.py`を追加。試験 test_setup_samples 6件・test_setup_bow_string 7件、setups回帰218件を2027/2025で合格、Sphinx警告0。未コミット。

| Codex | 2026-10-24 | mlib fast/safeの明示化 | `_fast_edit`171箇所・`_safe_edit`5箇所と暗黙fast状態を撤去。本文の分岐・更新先へのfast/safe受渡し・通常Undo範囲を明示し、Plug安全再試行と未対応型事前拒否を維持。公開署名不変、mlrig使用側と日英説明を同期。初回に見つけた接線引数検査への誤転送を修正、関連15件再成功。Maya2022〜2027各137ファイル/1222件失敗0（合計7332件・環境/GUI等27skip）、使用側54ファイル347件成功。host53件・公開/構文/layout・日英各371ページSphinx警告0。既存の別作業と未コミット成果を保持、未commit/未push。GUI・速度未計測。証拠: `.maya-output/mlib-explicit-edit-20261024/result.json`。 |

- Codex (2026-10-24): _flag_aliases(attrs=attributes)と_fast_editの役割を定義・Transform.reset/Node.resetAttrs/Plug.reset・Undo連携で照合。前者はmlib独自の引数別名と重複検証、後者はfastのbool検証・入れ子への文脈継承・例外時の復元であり、OM2実装やUndo無効化そのものではない。独自別名の削減は公開API変更として別途判断、現仕様のfast共通機構は維持を推奨。説明のみで実装・テスト・Sphinx変更やMaya起動なし。

- Codex (2026-10-24 21:16 JST): 追加9時間の第18枠完了（18/18）。新規gettext→日本語→英語Sphinxを逐次-Wでビルドし、最終警告0・日英各371HTML、正式API等4検査/数学本文36assert/公開・layout・diff検査成功。英訳catalog8636件はPOTと完全一致、未訳/fuzzy/記法違反0、既存訳変更なし。更新した掲載名・署名・本文の独立最終レビューと9時間集計の独立監査成功。170製品実装と7テスト入口の状態は第17枠の全版回帰後から不変、Maya再起動不要。mlib-6をPAUSEDへ変更し、保存設定を読戻し、名前/指示/時刻/対象を保全確認。9時間サイクルは全18枠で終了。成果は33実装ファイルの固有docstring198箇所（既存定義194＋新内部1＋module3、編集イベント201と区別）、safe+fast未対応型preflight/共有typed表の小修正、回帰3件追加と既存7テストのmain入口追加。Maya2022〜2027各1222件/計7332件・失敗0、環境skip27はGUI12/Bifrost条件12/PoseDriver対応binary不足3、使用側snapshot339件/host53件成功。公開API・単位・返却・番号・数学所有権不変。台帳251/1713確認・未確認1462を維持し、全定義完了とはしない。common/decorator/型登録/reload/拡張の全定義説明、Container外側fast等の追加専用実測、GUI/ブラウザ目視/性能と後続mlrig並行追加は残件。旧境界33指摘は他担当64e8d46の実装25件/限定許可8件変更を含む現在の条件でpassしたと区別。詳細.maya-output/mlib-refactor-9h-20261024/cycle-summary.json とrun18/、前6時間12枠履歴SHA不変。他作業/未コミット/submodule保持、commit/push/PR/外部公開なし。

- Codex (2026-10-24 20:53 JST): 追加9時間の第17枠完了（17/18）。隔離mayapy2022〜2027の初回全回帰は各137ファイル/1181件・失敗0。独立ログ照合でmain入口のない既存7ファイル/41件が読込みだけと判明し、補足loaderで全6版41件ずつ成功を確認後、7ファイル末尾へ標準unittest.main入口のみ追加。既存assert/本文/doc/署名はAST不変、正式run_allを全6版再実行し各137ファイル/1222件、総7332件/失敗・error0、環境skip27は前回理由と同一。初回1178件との差はrun7の新規3件と既存41件の有効化。datatype/Transformationの所有権・Undo/fast/safe・複数形/型登録/reload/拡張を既存回帰で確認。専用command discovery成功、ホスト53件成功、170実装のPython3.7構文/公開契約不変、製品実装は今回変更なし。layoutは同梱拡張を含む186ファイル/違反0・既存情報5。使用側allは453素材固定snapshotでMaya2027の339件成功/skip0、実行中原本変更なし。旧境界33指摘は他担当64e8d46で実装25件置換＋2ファイル限定許可8件変更済みという前提を分離し、現在の境界監査passを確認。Bifrost非致命warningあり。日英文書/POはrun16 hash不変、最終ビルドは次枠。定義レビューは251/1713、未確認1462で維持。GUI/性能未実測、Container外側fast制限は未実測のまま。証拠.maya-output/mlib-refactor-9h-20261024/run17/、前回12枠履歴SHA不変。他作業/未コミット差分保持、commit/pushなし。
- 2026-10-24 20:57 Claude Code: RotationMinimizingFramesへfromCurve(NURBS曲線のpointOnCurveInfoの位置・normalizedTangentから同じdouble reflectionでフレームを作る入口)を追加(未コミット)。createの挙動は変えず、ノード組み立てを内部補助_Operatorsへ移して共有、frames()に任意のtangents引数を追加。テスト17件(既存9+fromCurve8)・setupsスイート205件がMaya 2027/2025でOK(fromCurveの初回はテスト側でpointOnCurveのワールド値へさらにワールド行列を掛けていた誤りで3件失敗→修正)。rstへfromCurveとSplineIK・リボンへのつなぎ方の例を追記しSphinx -W警告0。検証動画.maya-output/verification/20261024-205143-4ff492d4(264フレーム全合格、判定は前回と同じ0.05度)。G:\マイドライブ\Maya検証動画\RotationMinimizingFramesへコピー、Driveのリンク共有は未設定。
- 2026-10-24 20:48 Claude Code: mlrigへRotationMinimizingFrames(setups/rotationMinimizingFrames.py)を追加(未コミット)。Wang・Jüttler・Zheng・Liu「Computation of Rotation Minimizing Frames」(TOG 2008)のdouble reflection法を、論文の式から標準ノードで組み立て、点列の各点にねじれの少ないフレームを出力(keepOffsetで生成時の姿勢を保つ)。テスト9件・setupsスイート197件がMaya 2027/2025でOK(細かい分割の参照との比較は、最初の版の絶対角度の比較が接線近似の差で失敗したため、間の点のねじれの増え方の比較へ直した)。docs/rotation_minimizing_frames.rstをindexへ追加しSphinx -W警告0。検証動画.maya-output/verification/20261024-204143-ecc99928(312フレーム全合格。単精度のためDGとPython版の差の判定は0.05度。初回録画は0.01度の判定と誤った性質の判定で失敗)。G:\マイドライブ\Maya検証動画\RotationMinimizingFramesへコピー、Driveのリンク共有は未設定。
- 2026-10-24 20:35 Claude Code: mlrigへ顔以外のモジュール4つを追加(未コミット)。Piston(setups/piston.py。シリンダーとロッドをaimMatrixで互いへ向け、共通の上方向で同一平面に保ち、length・extension・overStroke(ストローク超過、値のみ)を出力)、WaveChain(setups/waveChain.py。joint列へ位相をずらした正弦波の回転を重ねる尻尾・触手のうねり。正弦はcomposeMatrix+vectorProductで求める)、WheelRoll(setups/wheelRoll.py。車体の前進距離/半径で車輪を自転、接地点が滑らない。前進方向は親空間の固定軸)、PoleVectorPlacement(setups/poleVectorPlacement.py。3関節の平面上で付け根-先端の線に垂直な向きへポール位置を出力、一直線では中間関節)。いずれも標準ノードのみ・container所有・生成時の姿勢で跳ねない(WaveChainは既定振幅0)。setups/__init__.py・tools/test_rig_packages.pyへ登録。テスト7/7/7/6件、setupsスイート188件がMaya 2027/2025でOK、standardスイート76件(2027)OK。docs/piston・wave_chain・wheel_roll・pole_vector_placement.rstをindexへ追加しSphinx -W警告0。検証動画は全フレーム合格: .maya-output/verification/20261024-201231-a67ab85f・20261024-201822-2cad8706・20261024-202436-15da1eb8・20261024-203024-4175bcc4。G:\マイドライブ\Maya検証動画\Piston・WaveChain・WheelRoll・PoleVectorPlacementへコピー、Driveのリンク共有は未設定。

- Codex (2026-10-24 20:16 JST): 追加9時間の第16枠完了（16/18）。持越し数学型とutilの5ファイル12docstringを修正、関連8内部定義も照合。Matrixの行優先16値/4x4コピー・分解時の元Matrix平行移動・位置w=1/方向w=0・MPoint元w無視/透視除算なし・OpenMaya特異性判定と独立逆行列、Quaternionのコピー正規化とVector.rotateByの直接委譲の差、Eulerの度換算/回転周期非保持を具体化。util._copy_stateは数学成分作成を呼出側が担当し追加Python状態だけを浅く/深く写す責務と自己参照memoを説明。非公開utilの文書投影は増やしていない。全170実装のdocstring除外AST/署名等不変、Python3.7構文・公開・layout・diff検査成功。gettext/日英Sphinx逐次-W警告0、日英各371HTML・正式API等4検査・本文36assert・18ページ独立読戻し成功。英訳新42/旧31・共通8,594訳保持、未訳/fuzzy/記法違反0、16枠までの翻訳同期を再照合。台帳は今回20定義/累積251/1,713確認、未確認1,462。Maya/GUI/性能の再実測なし。既存datatype/Transformation所有権テストを読取確認し次枠全版回帰を準備。common/decorator/登録/reload/拡張全体は未確認を残し、次2枠は回帰・最終文書確認を優先。既存Container外側fast制限は未実測のまま保持。証拠.maya-output/mlib-refactor-9h-20261024/run16/、前回12枠履歴SHA不変。他作業/未コミット差分保持、commit/pushなし。
- 2026-10-24 20:10 Claude Code: mlrigへ顔のモジュール2つを追加(未コミット)。EyelidFollow(setups/eyelidFollow.py。目のPitch/Yawの一部を上下のまぶたへ移し、blinkで閉じ、追従の差で上下が交差する入力は開き0で止める)とJawHinge(setups/jawHinge.py。閉じた姿勢を越える入力を-softness度へ漸近させ、開き角に比例して前へスライド、Yaw・Rollは保持)。どちらも標準ノードのみ・container所有・生成時の姿勢で跳ねない。setups/__init__.py・tools/test_rig_packages.pyへ登録。テストtest_setup_eyelid_follow.py 10件・test_setup_jaw_hinge.py 9件、setupsスイート161件がMaya 2027/2025でOK。docs/eyelid_follow.rst・jaw_hinge.rstをindexへ追加しSphinx -W警告0。検証動画tools/demo_eyelid_follow.py(474フレーム)・demo_jaw_hinge.py(384フレーム)全フレーム合格、.maya-output/verification/20261024-195405-1692c904・20261024-200339-aee13669。G:\マイドライブ\Maya検証動画\EyelidFollow・JawHingeへコピー、Driveのリンク共有は未設定。

- Codex (2026-10-24 19:43 JST): 追加9時間の第15枠完了（15/18）。持越しConstraint/ObjectSet/Container/DagPoseの4ファイル17docstringを修正、関連12定義も照合。ConstraintのMaya順/完全名照合・生weight逐次更新とfastでもcmds照会、ObjectSetの非flatten/Plug・Component文字列/範囲全件判定、Containerの直接所属・公開名→内部Plug参照・箱解除、DagPoseの疎番号/保存Matrixコピー/reset・restore・mergeの責務を具体化。merge競合拒否はcurrentPose=False限定、復旧二次失敗はwarning/元例外優先、標準joint.bindPose保存入力の削除許可を明記。Container.createNodeの外側fast混在は既存の未実測制限として説明し、一律のUndo復旧保証を避けた。全170実装のdocstring除外AST/署名等不変、Python3.7構文・公開・layout・diff検査成功。gettext/日英Sphinx逐次-W警告0、日英各371HTML・正式API等4検査・本文/概要58assertと16ページ独立読戻し成功。英訳新65/旧42・共通8,560訳保持、未訳/fuzzy/記法違反0。台帳は今回29定義/累積231/1,713確認、未確認1,482。Maya/GUI/テスト再実行/性能検証なし。Container外側fast/Undo無効・復旧二次失敗、SetのPlug/nested/instance、Constraint別instance等の追加専用実測は未実施。数学型を次回優先へ持越す。証拠.maya-output/mlib-refactor-9h-20261024/run15/、前回12枠履歴SHA不変。他作業/未コミット差分保持、commit/pushなし。

- Codex (2026-10-24 19:13 JST): 追加9時間の第14枠完了（14/18）。持越しAnimCurve/DrivenKeyを優先し2ファイル14docstring修正、関連8定義も照合。AnimCurveのT/U入力とA/L/T/U出力の内部単位・独立値リスト、カーブ単体評価/時間出力の版差補正、角度rad/接線weight API値・キー別lock/全体weightedTangents、同時flag優先と検証・fast既存/新規キーの適用順・非rollbackを具体化。float受理と厳密キー番号を区別。DrivenKeyの保持参照/接続探索と各Plug定義による単位変換、dgdirty、通常Undoチャンクと外側fastでもcmdsのUndo記録は無効化しない境界を明記。全170実装のdocstring除外AST/署名等不変、Python3.7構文・公開・layout・diff検査成功。gettext/日英Sphinx逐次-W警告0、日英各371HTML・正式API等4検査・本文/概要46assertと日英8ページ独立読戻し成功。英訳新70/旧35・共通8,532訳保持、未訳/fuzzy/記法違反0、文書持越しなし。台帳は今回22定義/累積202/1,713確認、未確認1,511。DrivenKey異種単位/UI変更/time入力・外側fast・dgdirty後失敗、未知API接線型や後半失敗等の専用追加実測なし。説明のみでMaya/GUI/テスト再実行/性能検証なし。Constraint/Set/Container/DagPoseを次回優先へ持越す。証拠.maya-output/mlib-refactor-9h-20261024/run14/、前回12枠履歴SHA不変。他ツールによるmlrig境界修正・テスト許可一覧の変更は保持し、現在の回帰件数/指摘は最終回に再確認。commit/pushなし。

- Codex (2026-10-24 18:42 JST): 追加9時間の第13枠完了（13/18）。持越しBlendShapeを優先し、nodes/blendShape.pyの14docstringを修正、関連6内部定義も照合。全alias投影と実ターゲット番号一覧、getOutputGeometry順と最小base論理番号、group/item存在検査、0/0.8を含み得る6000以外の項目列挙、頂点マスク既定値1とコピー/Plug参照の違いを明記。setTargetWeightsの全入力検証と逐次書込、後半失敗の先行更新保持、外側fast継承/Undo有効時チャンクを説明。全170実装のdocstring除外AST/署名等不変、Python3.7構文・公開・layout・diff検査成功。gettext/日英Sphinx逐次-W警告0、日英各371HTML・正式API等4検査・本文/概要38assertと独立読戻し成功。英訳新55/旧33・共通8,512訳保持、未訳/fuzzy/記法違反0、文書持越しなし。台帳は今回20定義/累積180/1,713確認、未確認1,533。非weight alias混在順・異なるbase集合・mask全境界/後半失敗/instanceの追加専用実測なし。説明のみでMaya/GUI/テスト再実行/性能検証なし。AnimCurve/DrivenKeyを次回優先へ持越す。証拠.maya-output/mlib-refactor-9h-20261024/run13/、前回12枠履歴SHA不変、他作業/未コミット差分保持、commit/pushなし。

- Codex (2026-10-24 18:24 JST): 追加9時間の第12枠を完了（12/18）。持越しSkinClusterテーマを優先し、skinCluster.pyの13定義＋module計14docstringを修正、取得/検索/編集制約の6定義も既存説明と実装を照合。skinCluster自身の関数セットと先頭geometry名/DAGパスの保持責務、全頂点×指定列順flat/broadcast、取得の物理番号と疎weights[]書込の論理番号を明記。setWeightsのNone返却/非正規化・liw/layer非検査・未指定値維持、通常逐次cmds/fast全対象検査後の逐次setDoubleと非rollbackを説明。normalize/pruneの全体検査・名前/型によるlayer推定、Decimal最大剰余/物理順tie/float保存誤差、prune非登録削除、設定2Plug先行→値適用の責務を整理。_jnt_index旧UUID優先表現をOR一致の先頭物理番号へ修正。独立レビューの関数セット帰属の指摘を日英へ反映。全170実装のdocstring除外AST/署名等不変、Python3.7構文・公開・layout・差分検査成功。gettext/日英Sphinx-W警告0、日英各371HTML・正式名/署名等4検査と日英4ページの本文/field-list読戻し成功。英訳新74/旧51・共通8,471中8,470訳保持、関連する既存のlock/接続/layerを拒否する説明の英訳反転1件を訂正、未訳/fuzzy/記法違反0。第1〜12枠の翻訳/文書持越し0と実装未完了0をチェックポイントへ記録。台帳は今回19定義/累積160/1,713確認・未確認1,553、更新module説明3件。説明のみでMaya/GUI/性能/既存テスト再実行なし。getter異常入力・全round/prune境界・書込失敗注入の専用追加実測は未実施。BlendShapeを次回優先へ持越し。証拠.maya-output/mlib-refactor-9h-20261024/run12/、前回12枠の進捗SHA不変。他ツールのmlrig全テスト/hingeIK・planarIK修正差分を保持し、旧境界監査33指摘は現在値と断定せず最終回に再確認。コミット・pushなし。

- 2026-10-24 Claude Code: mlrigの全スイート(setups/standard/native/matrix-plugins/bifrost、Maya 2027)を確認。失敗はsetupsのtest_maya_command_boundary_in_mlrigの1件のみ(setups/hingeIK.py・planarIK.pyがOpenMaya直接importと許可外のcmdsを使用)。両ファイルをmlib.maths・Node/Plug経由へ書き換え、mlibに入口が無いikHandle・joint・spaceLocator・poleVectorConstraint・orientConstraintをテストの許可一覧に追加。setups 142件(2027/2025)・コミット済みmlibの別worktreeで135件OK。
- Codex (2026-10-24 17:50 JST): 追加9時間の第11枠を完了（11/18）。持越しの形状座標テーマを優先し、PointComponent/PointComponents・UV/UVsとgeometryEditの3ファイル17docstringを修正、内部座標/番号変換5定義は既存説明と実装を照合。XYZのcm固定とShape object/保持DAG path world、値の独立tuple/list、CV w保持、共有Shapeの全instanceへの影響、行別setPositionsと同値絶対座標setPositionを具体化。通常cmdsのUI単位換算/Undo有効時のチャンクと逐次更新、fastの履歴/周期/ロック制限・Undo設定不変、件数/有限値/番号検証と全書込み可否の区別・後半失敗の非rollbackを説明。UVは現在セット/無次元/0〜1非限定、空標準経路とoverride委譲、Shape lock/履歴検査と個別UV-set Plug非検査の境界を明記。geometryの親ロック/入力接続と対象自身のwritable検査を独立レビューにより精密化。全170実装のdocstring除外AST/署名等不変、Python3.7構文・公開・layout・差分検査成功。gettext/日英Sphinx-W警告0、日英各371HTML・正式名/署名等4検査と5ページ×日英の静的本文/field-list確認成功。英訳新102/旧53・共通8,420中8,418訳保持、関連する既存2訳（自動復元なしをUndo不能とする誤訳/点番号の件数をjoint数とする誤訳）を訂正、未訳/fuzzy/記法違反0。補助英訳草稿は隔離ファイルだけに分担し、rootが採否/結合/正式PO更新を担当、前半を独立レビュー。台帳は今回22定義/累積141/1,713確認・未確認1,572。説明のみでMaya/GUI/性能/既存テスト再実行なし。UV fastの個別lock/非選択UVやAPI更新失敗注入・特異閾値の追加実測なしと区別。ノード側の全形状APIは確認完了に含めず、SkinClusterを次回優先へ持越し。証拠.maya-output/mlib-refactor-9h-20261024/run11/、前回12枠の進捗SHA不変。他ツールのspline_spine作業/既存未コミット保持、コミット・pushなし。

- 2026-10-24 Claude Code: mlrig.examples.spline_spine(mGear spine_S_shape風のスプラインIKの背骨のサンプル、標準ノード)を追加。腰・接線2つ・胸の4コントローラーをCVにSplineIK、FKを階層で重ね、maxStretch/maxSquash・volume・lockOri・tangent倍率をcogに置く。stretch=Falseで伸縮・体積なしのシンプル版。テスト9件(2022/2025/2027)・setups登録・docs/spline_spine_example.rst・tools/demo_spline_spine.py(通常版384・シンプル版312フレーム全合格の検証動画)。
- Codex (2026-10-24 17:11 JST): 追加9時間の第10枠を完了（10/18）。持越しComponentテーマを優先し、component.py/cv.pyの16docstringを修正、CVの名前取得3定義は既存説明と実装/テスト根拠の一致を確認。単数のMaya実番号と複数形のPython位置/slice/負数・bool差、__index__受理と実番号bool拒否、初出順の重複除去・構築時の番号固定、共有Shape/保持tupleそのものとプロパティ無再検証を説明。遅延iterの各参照構築時検証と途中yield、completeの現在Shape全件・明示API番号順、単数解決の展開前判定/展開後一件確認を明記。CVはNurbsCurveのみ、OpenMaya番号保持と周期cmds名対応/非圧縮の境界を説明。独立レビューでgetCompactNamesのMaya側結果順保証へ読める旧文を、ソートせず保持順+1連続区間だけ圧縮する責務へ限定。実行処理は変えず、全170実装のdocstring除外AST/署名等不変、Python3.7構文・公開・layout・差分検査成功。gettext/日英Sphinx-W警告0、日英各371HTML・正式名/署名等4検査、4クラス×日英の静的表示26本文assertと独立読戻し成功。英訳新57/旧39・共通8,416訳保持、未訳/fuzzy/記法違反0。台帳は今回19定義/累積119/1,713確認・未確認1,594。説明のみのためMaya/GUI/性能/既存テスト再実行なし。bool位置・indices同一性/入力list変更・多次元拒否/completeData不一致の専用回帰は未実施と区別。Mesh/NurbsCurve/UV座標テーマを次回優先へ持越し。証拠.maya-output/mlib-refactor-9h-20261024/run10/、前回12枠の進捗SHA不変、他作業・既存未コミット保持、コミット・pushなし。

- Codex (2026-10-24 16:44 JST): 追加9時間の第9枠を完了（9/18）。持越しのArrayPlug/CompoundPlugを優先し、2ファイル14docstringを修正、getElementの既存説明1件も実装照合。multiの疎な論理番号とCompoundの直接子定義順、参照の新ラッパー/共有Node/保持DAGパス不変更、反復時の参照一覧とgetのdict/tuple・子getter依存/非平坦化/DG評価を説明。worldSpaceインスタンス補完のgetIndicesとraw既存のみの候補探索/要素削除を区別し、getNextAvailableIndexの型/上限非検証・非予約も現実装通り記載。Compoundの旧fullName表記をgetFullName()へ修正。独立レビューで複合要素のcmds文字列化を補足し、bool拒否条件の曖昧な既存共用英訳1件を訂正。実行ASTは全170実装で不変、Python3.7構文・公開・layout・差分検査成功。最初の空行末尾空白は除去して再検査成功。gettext/日英Sphinx-W警告0、日英各371HTML・正式名/署名等4検査・2クラス×日英の静的表示/コードliteral確認成功（読戻し補助のsmart quote正規化も修正）。英訳新62/旧37・共通8,393中8,392訳保持、関係する既存訳1件のみ修正、未訳/fuzzy/記法違反0。台帳は今回15定義/累積100/1,713確認・未確認1,613。説明のみのためMaya/GUI/性能/テスト再実行なし。入れ子値の専用実測・接続付き要素削除/通常UndoRedoの追加実測は未実施と区別。Componentテーマを次回優先へ持越し。証拠.maya-output/mlib-refactor-9h-20261024/run9/、前回12枠の進捗SHA不変、他作業・既存未コミット保持、コミット・pushなし。

- Codex (2026-10-24 16:17 JST): 追加9時間の第8枠を完了（8/18）。前回持越しのPlug接続テーマを優先し、plug.pyの説明10箇所を実装/既存テストと照合して修正。getSource/getDestinationsとgetConnectionsのskip既定差、kwargsの子/要素非展開とgetSourceのindex=0固定、(自身側,相手側)ペア/相手だけNode化/型filter・初出重複統合後のPython添字を明記。dst.connect(src)とsrc.connectTo(dst)、naの0からの入力/lock検査と定数/出力要素再利用、forceの接続先/上位だけの解除とlock復元、返却参照のPython同一性非保証を説明。単数disconnectは入力元/naは接続先要素list、Input/Allはself、非再帰/変換ノード非削除/通常Undo有効時とfast非記録、逐次失敗の非rollbackを明記。復元失敗で残り停止/復元例外送出/編集例外contextの既存契約を保持。全170実装のdocstring除外AST/署名等は不変、Python3.7構文・公開・layout・差分検査成功。Sphinxの委譲例のinline strong警告はコードliteralの前後空白で修正し、失敗ログを保持、検査は緩和せず最終gettext/日英-Wを成功。日英各371HTML、HTML/正式名/署名4検査・10項目の独立DOM読戻しとコードliteral表示成功、最終警告0。英訳新54/旧28・共通8,376訳保持、未訳/fuzzy/記法違反0。第1〜8枠の英訳チェックポイントを確認し文書持越しなし。台帳は今回10定義/累積85/1,713確認・未確認1,628。getter kwargs/na既存要素/fast失敗注入/多段変換の追加実測は未実施として記録。説明のみのため今回はMaya/GUI/性能/テスト再実行なし。元の配列テーマは次回優先へ持越す。証拠.maya-output/mlib-refactor-9h-20261024/run8/、前回12枠の進捗SHA不変。他作業・未コミット保持、コミット・pushなし。

- Codex (2026-10-24 15:46 JST): 追加9時間の第7枠を完了（7/18）。前回の既存不整合SAFE_FAST_UNSUPPORTED_COMPOUNDを優先修正。core.fastWriteへ型定義だけを再帰確認するprivate helperを追加し、safe=Trueのfast複合値ではロック/値変換より先に未対応の子を拒否する。typed配列factory表はprepare_dataと共有し、既存NUMERIC_WRITERS/所有権/保持を維持。子再試行のNIEも再送出。通常safeとsafe=Falseの経路/公開引数・戻り値は維持。3回帰を追加し、ロック有無×先行値正常/不正4組・入れ子で未対応型を全値未更新のままNIE拒否、対応型ではUI m→cm部分更新/safe=1/lock/Undo非干渉を確認。隔離Maya2022/2027は順次各7ファイル62件、失敗/skip0、exit0。独立監査が両版全14ログと型表AST一致/所有権/通常側の既存Undo・safe=0/1も確認。実行変更は実装2ファイル、説明変更を含む4ファイルとテスト1ファイル。全170実装のPython3.7構文/既存署名・decorator・import・基底・公開/登録は不変、公開/layout/差分検査成功。説明4箇所を同期し、日英Sphinxは順番に-W各371HTML、HTML/正式名/署名4検査・対象6ページ独立読戻し成功、警告0。英訳新10（参照2/説明8）・旧4、共通8,394訳保持、未訳/fuzzy/記法違反0。台帳は新private定義1で総数1,713へ増分記録し、今回6定義再確認/累積75確認・未確認1,638。前回の再現記録は履歴として保持、run7の解消記録とprogressへ反映。接続方向/変換ノード/force/lock復元の予定テーマは未着手として次回優先へ明記。Maya2023〜2026/全suite/GUI/性能は今回未実施。証拠.maya-output/mlib-refactor-9h-20261024/run7/、前回12枠の進捗SHA不変。他作業・未コミット保持、コミット・pushなし。

- Codex (2026-10-24 15:12 JST): 追加9時間の第6枠の説明修正/検証を完了（6/18）。Plug/CompoundPlug/Double3Plug/MatrixPlug・decorator・fastWriteの9docstringsを修正。入力変換と書込み可否/型準備、通常Undo有効時のチャンクとfastの非Undo/設定不変、safeの初回例外と子再試行/失敗数の限界/先行変更保持、Matrix一件の0/1、setIfChangedの厳密比較/同値False/対象だけ再lock試行、resetの定義順/後続失敗時の非rollbackを明記。全170実装のdocstring除外AST/公開署名等不変、Python3.7構文・公開・layout・差分検査成功。日英Sphinxは順番に-W各371HTML、静的HTML/正式名/署名4検査・対象10ページ独立レビュー成功、警告0。英訳新49/旧26、共通8,349中8,348訳保持、関連する共用UI単位のreturns誤訳1件をusesへ補正してEN再build/検査/読戻し成功、未訳/fuzzy/記法違反0、英訳持越しなし。重要な既存不整合SAFE_FAST_UNSUPPORTED_COMPOUNDを発見: ロックをきっかけにsafe子再試行へ入ると、書ける子の更新後に未対応fast例外が1へ変換され得る。隔離Maya2027の2対照を1worker/7.56秒/exit0で実測、ロックありで中央8→2/戻り1、ロックなしでNIE/全値不変。両方でlock/Undo設定・キュー不変。今回は実行処理を変えず、証拠run6/safe-fast-boundary.jsonとprobeへ記録し、次回は予定テーマより先に修正設計と回帰を優先する。台帳は今回9定義/累積72/1,712確認、未確認1,640維持。広範な回帰・他Maya版・GUI/性能は未実施。証拠.maya-output/mlib-refactor-9h-20261024/run6/、前回12枠の進捗SHA不変。他作業・未コミットを保持、コミット・pushなし。

- Codex (2026-10-24 14:45 JST): 追加9時間の第5枠を完了（5/18）。getPlug/Plug/Double3Plug/attributeTypeの説明13箇所（module1+定義12）を実装照合して修正。参照取得と実体化/値評価、保持Node/MPlug参照と独立数学値、Python型と定義型/generic、読取関数だけの保持と毎回のDG評価、cm/rad/秒とUI単位、multiの論理番号dictと型付き配列のlist/XYZ/XYZW/16成分を明記。typed_dataはAPI参照で独立Python値への変換は呼出元と修正し、非掲載の内部補助を公開へ拡大せず維持。全170実装のdocstring除外AST/公開署名等は不変、Python3.7構文・公開・layout・差分検査成功。日英Sphinxは順番に-W各371HTML、静的HTML/正式名/署名4検査と独立本文レビュー成功、警告0。英訳新28/旧17を同期し、value_reader冒頭の既存逆訳1件だけを補正、共通8,347件中8,346訳保持。補正後EN再build/検査/実HTML読戻し成功、未訳/本文fuzzy/記法不一致0、同期持越しなし。台帳は累積63/1,712定義確認、未確認1,649定義を維持。関連helperの参照読みは全件完了と数えず、型付き配列等の追加実測は未実施と記録。証拠.maya-output/mlib-refactor-9h-20261024/run5/、前回12枠の進捗SHA不変。説明のみのため今回Maya/GUI/性能検証は未実施。他作業・未コミットを保持、コミット・pushなし。次回15:00 JSTはPlug更新の通常Undo/fast/safe/返却。

- Codex (2026-10-24 14:15 JST): 追加9時間の第4枠を完了（4/18）。Joint/Joints/Transformの説明14箇所を修正。SSCフラグとinverseScale接続/実補償の責務、JOのXYZ/radとinverseScaleの無次元XYZ・独立値/無効時ゼロ、回転移送元ゼロ時の書込み検証省略、複数Jointの全件準備→保持順と通常Undo対fast/自動rollbackなしを明記。Quaternionの合成順/単一書込み先/Euler順序/取得設定の非対称と非JointでのgetJointOrientQuaternion、内部行列適用のcm/rad/Plug委譲を説明し誤ったUI度前提を除去。全170実装のdocstring除外AST/公開署名等は不変、Python3.7構文・公開・layout・差分検査成功。日英Sphinxは順番に-W各371HTML、静的HTML/正式名/署名4検査と独立実ページレビュー成功、警告0。複数freezeRotate冒頭も合成と明示し、単純copyと読めた英訳をcomposeへ同期して日英再build/検査成功。最終英訳新30/旧20・共通8,334訳保持、未訳/本文fuzzy/記法違反0。第1〜4枠の文書同期持越しなし。台帳は今回14定義、累積51/1,712定義確認・未確認1,661定義を維持。無効時ゼロ/専用fast接続等の追加実測は未実施と記録。証拠.maya-output/mlib-refactor-9h-20261024/run4/、前回12枠の進捗SHA不変。説明のみのため今回Maya/GUI/性能検証は未実施。他作業・未コミットを保持、コミット・pushなし。次回14:30 JSTはPlug参照/型/内部・UI単位/値評価。

- Codex (2026-10-24 13:41 JST): 追加9時間の第3枠を完了（3/18）。Transformの説明13箇所を修正。担当範囲・cm/rad/UI単位、PivotのkPreTransformと親側の位置基準、独立した取得値と明示書戻し、getMatrixのp/ws別取得、safeの目標行列一致/巻戻し非保証とget予定値が最終予測でない点、at<=0の差分計算、Scale XYZ/Shear XY-XZ-YZの無次元と当該チャンネルだけの書込みを明記。全170実装のdocstring除外AST/公開署名等は不変、Python3.7構文・公開・layout・差分検査成功。日英Sphinxは順番に-W各371HTML、静的HTML/正式名/署名4検査と独立実ページレビュー成功、警告0。英訳新47/旧29を同期し、関連する既存getMatrix訳のnamespace誤訳1件だけcoordinate spaceへ補正。共通8,307件中8,306訳保持、未訳/本文fuzzy/記法違反0、補正後EN再build/検査成功。台帳は今回13定義、累積37/1,712定義確認・未確認1,675定義を維持。Quaternion/内部helperとp/inv専用実測の未確認を記録。証拠.maya-output/mlib-refactor-9h-20261024/run3/、前回12枠の進捗SHA不変。説明のみのため今回Maya/GUI/性能検証は未実施。他作業・未コミットを保持、コミット・pushなし。次回14:00 JSTはJointの回転軸/jointOrient/segmentScaleCompensate。

- Codex (2026-10-24 13:08 JST): 追加9時間の第2枠を完了（2/18）。DagNode/Nodeの2実装・説明12箇所を修正。mpathの内部可変パス借用とコピー条件、getInstancesのAPI順/self再利用、getParentsの親ノード対パス単位/代表パスと列挙順、getChildrenの中間除外下の探索停止/保持パス/4bool検証、全/部分パスの例外とNode全体無効時の空文字の違いを明記。全170実装のdocstring除外AST/公開署名等は不変、Python3.7構文・公開・layout・差分検査成功。日英Sphinxは順番に-W各371HTML、静的HTML/正式名/署名の4検査と実ページ独立レビュー成功、警告なし。英訳新42/旧20、共通8,294訳保持、未訳/本文fuzzy/記法違反0。台帳は今回16定義（修正12・確認のみ4）、累積24/1,712定義確認・未確認1,688定義。sameNode/sameInstance等の残候補と未網羅テストを記録。検査用pickle配置の初回不一致は同一ビルドのSHA一致コピーで解消し再検査成功、製品/検査内容は変更なし。証拠.maya-output/mlib-refactor-9h-20261024/run2/、前回12枠の進捗SHA不変。説明のみのため今回Maya/GUI/性能検証は未実施。他作業・未コミットを保持、コミット・pushなし。次回13:30 JSTはTransformの座標空間/TRS/ピボット/行列。

- Codex (2026-10-24 12:44 JST): 追加9時間の第1枠を完了（1/18）。Object/Node/getNodeの3実装・説明8箇所を実装照合し、Objectの無検証同一参照とNode/getNodeの新ラッパー、登録済み祖先型の選択順、所有ノード/シェイプ・DAGパス、作成時の通常Undo/外側fast継承と例外をMaya基準の日本語へ修正。無関係なUI定型文を除去。全170実装のdocstring除外AST/公開署名等は不変、Python3.7構文・公開・layout成功。日英Sphinxは順番に-W各371HTML、静的HTML/掲載get・is名/署名の4検査と独立レビュー成功、警告なし。英訳は新29/旧20を同期、共通8,285項目の訳文/flag保持、未訳/本文fuzzy/記法違反0。確認台帳は7定義修正+1定義確認済み、未確認1,704定義を維持。証拠.maya-output/mlib-refactor-9h-20261024/run1/、前回12枠の進捗SHA不変。説明のみのため今回Maya/GUI/性能検証は未実施。他作業・未コミットを保持、コミット・pushなし。次回13:00 JSTはDAGの名前/完全パス/階層/インスタンス。

- Codex (2026-10-24 12:27 JST): ユーザーの追加9時間依頼に基づき、既存heartbeat mlib-6を更新してACTIVE/同じタスクへの継続を読戻し確認。本日12:30〜21:30 JSTの30分ごと18枠、最終開始21:00・各25分以内・最終回停止。Maya完全上級/Python中級（クラス/責務/decorator/context理解済み）へ前提を更新し、Maya基準の日本語Google形式docstringを重点化。対象/空間/単位/論理・物理番号/評価と実体化/所有権/失敗・Undo/fast/safeを実装と照合し、小さな責務整理も行う。18枠をObject/Node→DAG/TRS/Joint→Plug/接続/配列→Component/形状→Skin/BlendShape/Anim/関係型→数学/共通基盤→最後2枠の回帰/日英Sphinx/収束へ配分。英訳は小分け同期し、確認台帳で実際に確認した定義と未確認を区別。前回全12枠の進捗SHAと170実装の不変を確認し、未コミット/QuickPathExplorer/AutoClavicle等の他作業を保持。計画/進捗/対象台帳は.maya-output/mlib-refactor-9h-20261024/のplan.txt・progress.json・coverage.json、今回の製品変更/Maya検証/コミット/pushなし。

- Codex (2026-10-24): QPEの共有タブ最小サイズ制約を表示中だけ緩和し、他タブでは復元。破棄済みsplitter参照と共有タブの自動分離を修正。階層列幅に矢印・縦バー分を確保。Maya2027専用GUIでタブ縮小/復元、長い名前、右/下ドック、浮動表示を検証済み。証跡: .maya-output/qpe-sizing/final/。

- Codex (2026-10-24 04:48 JST): 6時間枠のリファクタリングを第12枠まで全12回完了。最終枠は既存matrixArray説明2行と英訳POを同期し、全170実装の実行AST/公開契約は開始前と不変。英訳は新4/旧17整理・共通8,301項目の訳/flag保持、日本語未訳/本文fuzzy/記法違反0。日英Sphinx-W各371HTML、掲載名/署名/静的HTML、更新説明の表示と旧3定義anchor不在を検証。最終ソースで隔離Maya2022〜2027全6版各137ファイル/1,178件成功（skip6/6/6/3/3/3）、ホスト53件・Python3.7構文/公開/layout/差分検査成功。並行追加を含む現在のmlrig275件中274成功・既存境界監査1失敗/33指摘は対象ソースSHAと指摘集合が開始前と一致し検査を維持。他作業AutoClavicle等7ファイルは保持。累積では未使用3定義を削除し、Node/Plug入力・参照寿命、更新前検証/Undo・fast・safe、Component/形状操作、数学値/単位変換を明示分岐/ループ/具体名へ整理。実装170ファイル・変更11実装、33,015→32,944物理行（純減71）、公開引数/単位/返却/所有権・複数形/reload/型登録/拡張自動探索は維持。文書同期4件と実装の未完了なし。結果.maya-output/mlib-hourly-refactor-20261023/result.jsonとsummary.txt、既存mlib-6をネイティブ機能でPAUSEDへ更新し停止を読戻し確認。GUI/性能/ブラウザー操作は未実施、コミット・push・外部公開なし。

- Claude Code (2026-10-24 04:10〜, 夜間タスク): mlrig.setups.AutoClavicle(上腕の曲げ角が開始角を超えた分の一部を鎖骨へ分配。c=max·(1-exp(-weight·max(θ-start,0)/max))、鎖骨+=U0⁻¹·S^k·U0、上腕はT·S^(1-k)·U0で上腕のワールド回転は入力のまま、標準ノードのみ)を追加。setups/autoClavicle.py・setups/__init__.py(追記)・__tests__/test_setup_auto_clavicle.py(7件)・docs/auto_clavicle.rst・docs/index.rst(追記)・tools/test_rig_packages.py(追記)・tools/demo_auto_clavicle.py。HEADに自分の変更だけを載せた別worktreeの隔離mayapy 2027でsetups 205件・standard 76件OK、Sphinx -W成功。検証動画384フレーム全OK(Drive同期フォルダーへ保存、リンク共有は未設定)。自分の分だけコミット・プッシュ(このコミット)。他ツールの未コミット変更(mlib・QuickPathExplorer・WORK_LOGの他行)は含めていない。

- Codex (2026-10-24 04:13 JST): 30分リファクタリング第11枠を完了。製品の新変更は始めず第1〜10枠の累積差分を収束検証。隔離Maya2022〜2027全6版で各137ファイル/1,178件成功（skip6/6/6/3/3/3）、Maya不要53件・Python3.7構文170実装・公開・全mlib/拡張layout186ファイル・差分検査成功。別mayapyでコマンド追加/変更/削除・root reloadの既存検証もexit0/PASS。mlrig/拡張268件中267成功・境界監査1失敗は開始前と同じ33指摘で、実監査抽出値・対象3ソースSHA・mlrig全体の無変更を照合し、検査/whitelistは維持。独立累積レビューで保持署名/基底/型表/登録/import/Undo/fast/safe/所有権の意図しない変更なし、削除は未使用3定義のみ・未完成実装なし。実装170ファイル33,015→32,944行、変更11ファイル。結果.maya-output/mlib-hourly-refactor-20261023/run11/、完了11/12・次回04:36は文書同期4件/日英Sphinx/成果整理/スケジュール停止。前回差分を保持。GUI/性能/今回Sphinxは未実施、コミット・pushなし。

- Codex (2026-10-24 03:41 JST): 30分リファクタリング第10枠を完了。attributeType._convert_unitsの単位ローカル4名を具体化し、数値の内部/UI方向を通常if/elseへ、_read_arrayの要素tuple化/list化を明示ifへ整理。既存単位オブジェクトを再構築しない理由を補足。utilの派生状態/slot/循環コピー/キャッシュは理由を確認して維持。単位/UI照会順・compound遅延順・入力同一性・Maya2023 kInvalid・null/配列形式・借用handle解放・公開契約/Undo/fastは保持。全170実装の正規化ASTは対象名と2分岐以外一致、他169ファイル不変。独立実関数比較88構成/720条件と読取レビューで指摘なし。隔離Maya2022/2023/2027各137ファイル/1,178件成功（skip6/6/3）、Python3.7構文・公開・layout・差分検査成功。結果.maya-output/mlib-hourly-refactor-20261023/run10/、完了10/12・次回04:06は全体回帰/収束。既存matrixArrayの説明補足を最終文書同期へ追加し前回予定を保持、未完成実装なし。他3版/GUI/性能/今回Sphinxは未実施、コミット・pushなし。

- Codex (2026-10-24 03:12 JST): 30分リファクタリング第9枠を完了。Transformationの数学成分コピー/補助値保持とEuler入力/数値列入力の選択を通常if/elseへ展開し、独立コピーと回転順序の扱いを明示。OM2基底生成・メモリ対策・可変/非hash・コピー/自身更新・成分参照/計算結果の所有権を維持。全170実装の正規化ASTは2条件式の展開以外一致、他169ファイル不変。独立した実2メソッドの504条件で結果・呼出順・コピー所有権・例外が一致。隔離Maya2022/2027各137ファイル/1,178件成功（数学型テスト含む、skip6/3）、Python3.7構文・公開・layout・差分検査成功。結果.maya-output/mlib-hourly-refactor-20261023/run9/、完了9/12・次回03:36はutil/中立な値変換。前回差分と最終回文書同期予定を保持、未完成実装なし。他4版/GUI/性能/今回Sphinxは未実施、コミット・pushなし。

- Codex (2026-10-24 02:41 JST): 30分リファクタリング第8枠を完了。geometryEdit.positionsのMesh/CV単点・全点取得を明示if/elseへ、PointComponents.mirrorの二重内包を点/座標成分ループへ整理。既存の検証/空間変換/適用の責務分離を維持し、取得→全計算→設定、軸反転式・保持順・CVのw/周期番号・単位・override・通常Undo/fastを保持。全170実装で署名/decorator/基底/文書/登録と変更2関数外ASTは一致、他168ファイル不変。独立実関数比較の座標取得392条件・ミラー82構成/970条件で座標/返却/例外/呼出順・回数が一致。隔離Maya2022/2027各137ファイル/1,178件成功（skip6/3）、Python3.7構文・公開・layout・差分検査成功。結果.maya-output/mlib-hourly-refactor-20261023/run8/、完了8/12・次回03:06は数学値/コピー/所有権。前回差分と最終回文書同期予定を保持、未完成実装なし。他4版/GUI/性能/今回Sphinxは未実施、コミット・pushなし。

- Codex (2026-10-24 02:10 JST): 30分リファクタリング第7枠を完了。Component._from_apiのcomplete全要素/明示番号列選択と_resolve_inputの要素数照会を通常if/elseへ展開し、OM2の範囲表現と単数範囲の早期拒否手順を明示。公開引数/返却/番号/CV対応/保持順、単数二段階検証、型表、標準高速経路とgenerator/custom __index__/constructorの逐次処理を維持。全170実装の正規化ASTは2条件式の展開以外一致、他169ファイル不変。独立した実2関数の84構成/902条件で返却型・番号・順序・例外・呼出順/回数が一致。隔離Maya2022/2027各137ファイル/1,178件成功（skip6/3）、Python3.7構文・公開・layout・差分検査成功。結果.maya-output/mlib-hourly-refactor-20261023/run7/、完了7/12・次回02:36は形状操作の責務/処理順。前回差分と最終回文書同期予定を保持、未完成実装なし。他4版/GUI/性能/今回Sphinxは未実施、コミット・pushなし。

- Codex (2026-10-24 01:41 JST): 30分リファクタリング第6枠を完了。decorator._safe_editのUI成分変換とNodes._execute_callsのUndo文脈選択を通常if/elseへ展開し、全件fast/通常/混在/空列の扱いをコメントで明示。fast継承/bool検証/ContextVar復元、safe失敗数/部分更新/未対応拒否、空列のUndo方針、保持順・返却規則を維持。全170実装の正規化ASTは条件式2箇所の展開以外一致、他168ファイル不変。独立した実関数比較でsafe5,200条件・一括1,064条件の戻り/例外context/呼出順・回数が一致。隔離Maya2022/2027各137ファイル/1,178件成功（skip6/3）、Python3.7構文・公開・layout・差分検査成功。結果.maya-output/mlib-hourly-refactor-20261023/run6/。完了6/12で停止せず残り6枠を継続、次回02:06はComponent列挙/番号/範囲。前回差分と最終回の翻訳/Sphinx同期予定を保持。未完成実装なし、他4版/GUI/性能/今回Sphinxは未実施、コミット・pushなし。

- Codex (2026-10-24 01:11 JST): 30分リファクタリング第5枠を完了。attributeEdit._buildの固定4範囲を文字列getattrからMaya標準setterの明示ifへ整理。fastWrite.writableのFunction Set再利用と_prepared_writesの型選択を通常分岐へ展開し、準備列の所有権説明を補足。公開引数・単位・返却/所有権、値取得→method取得→呼出順、falsey Function Set再利用、全成分検証後だけ書込む構成とUndo/fastを維持。独立した実AST比較で範囲設定16,848条件・fastWrite502条件の戻り/例外/呼出順・回数が一致。全170実装の署名/decorator/基底/登録と変更3関数外のAST一致、他168ファイルは開始前と同一。初回回帰中に値取得順を厳密保持する最終修正を入れ、確定ソースで隔離Maya2022/2027各137ファイル/1,178件を再実行して成功（skip6/3）。Python3.7構文・公開・layout・差分検査成功。結果.maya-output/mlib-hourly-refactor-20261023/run5/、完了5/12・次回01:36は通常Undo/fast/safe分岐。英訳/Sphinx同期は最終回、前回差分を保持、未完成実装なし。他4版/GUI/性能は未実施、コミット・pushなし。

- Codex (2026-10-24 00:41 JST): 30分リファクタリング第4枠を完了。Plug._attribute_existsを静的/無効ハンドル/動的定義照会の明示分岐へ、_require_validを所有Node検証後に静的早期returnする形へ整理し、危険なAPIへ進まない検証順を読みやすくした。Node.isValidの説明にノード全体と保持インスタンスのパス有効性の違いを補足。公開契約、Maya照会順/回数、例外、isAlive/比較/固定hash、getFullNameの直接判定・インスタンス・Undoは保持。全170実装の正規化AST比較で判定2件と説明以外は一致、他168ファイルは開始前と同一。独立レビューの実関数抽出480条件で戻り値/例外/呼出順/回数が一致し、隔離Maya2022/2027各137ファイル/1,178件成功（環境依存skip6/3）。Python3.7構文・公開・layout・差分検査成功。結果.maya-output/mlib-hourly-refactor-20261023/run4/、完了4/12・次回01:06は更新前検証/処理順。追加docstringの英訳とSphinxは最終回に同期。前回差分を保持、未完成実装なし、他4版/GUI/性能は未実施。コミット・pushなし。

- Codex (2026-10-24 00:11 JST): 30分リファクタリング第3枠を完了。Plug._resolve_inputのObject._classes経由と別名をNode/Plugの明示参照へ整理し、未対応型を早期拒否して文字列解決の主経路を1段浅くした。_mplug_nameもNodeを別名なしで参照。公開契約、既存Plugの同一性、MPlugの空/削除済み所有者拒否、文字列内例外context、DAGインスタンス優先順を維持。構築/型選択/パス解析/generic未評価/未作成配列参照は未変更。全170実装を比較し、同じ型参照と早期拒否だけを正規化したASTが一致、他169ファイルは開始前と同一。隔離Maya2022/2027各137ファイル/1,178件成功（環境依存skip6/3）、Python3.7構文・公開・layout・差分検査成功、独立レビュー2担当で阻害なし。結果.maya-output/mlib-hourly-refactor-20261023/run3/、完了3/12・次回00:36は参照寿命/有効性/例外経路。前回差分を保持、未完了なし、他4版/GUI/性能/今回Sphinxは未実施。コミット・pushなし。

- Codex (2026-10-23 23:40 JST): 30分リファクタリング第2枠を完了。Node._resolve_inputのObject._classes経由をNode/Plug/Component(s)の明示分岐へ整理し、_resolve_nodeのPlug重複import/別名と_input_nameのObject再importを削減。入力型と所有ノードの対応をその場で追えるようにした。公開引数・返却・単位・所有権、削除済み参照の例外差、インスタンスパス、登録/reload/複数形/拡張を維持。jointEditで再同期に使う_resolveと初期化は保持。全170実装を比較し、当該3箇所の同一型参照/import/固定一覧展開だけを正規化したASTが一致、他169ファイルは開始前と同一。隔離Maya2022/2027各137ファイル/1,178件成功（環境依存skip6/3）、Python3.7構文・公開・layout・差分検査成功、独立レビュー2担当で阻害なし。結果.maya-output/mlib-hourly-refactor-20261023/run2/、完了2/12・次回00:06はPlug入力解決。前回の差分を保持、未完了なし、他4版/GUI/性能/今回Sphinxは未実施。コミット・pushなし。

- Codex (2026-10-23 23:24 JST): ユーザー指定で既存heartbeat mlib-6を30分間隔へ更新し、ACTIVE・同じタスク・期限を読戻し確認。完了済み第1枠を保持し、次回10/23 23:36から毎時06分/36分、最終10/24 04:36開始、期限05:04の最大12枠（残り11枠）へ変更。各回25分以内、Node/Plug・更新・Component・数学/utilの主題を小分けにし、最後2枠を回帰/文書/収束へ充てる。進捗JSONへ旧計画を保持し、完了数1と既存検証結果を維持。今回の製品コード変更なし、既存3ファイルの差分を保持。コミット・pushなし。

- Codex (2026-10-23 23:14 JST): 毎時リファクタリング1/6を実施。未使用閉包のcore.nodeEdit.create_group、Node._add_attribute、core.attributeEdit.add_attributeを削除し、旧グループ/追加アトリビュート実装の追跡先を減らした（定義120物理行、余白整理込み125行減）。公開Node.create/addAttrの実経路と_build/_attach/create_extra_attributeは保持。内製利用側・動的呼出し・bulk/型登録・公開一覧の参照なしを独立監査し、全170実装のASTが削除3定義以外で開始前と完全一致。Maya2022/2027各137ファイル/1,178件成功（環境依存skip6/3）、Python3.7構文・公開・layout・差分検査成功。結果.maya-output/mlib-hourly-refactor-20261023/run1/。旧private処理由来の英訳catalog3項目は最終回の文書再生成で整理、他4版/GUI/性能/今回Sphinxは未実施。次回はNode/Plug入力解決。開始前のスケジュール記録差分を保持し、製品3ファイルとWORK_LOGのみ未コミット、コミット・pushなし。

- Codex (2026-10-23): ユーザー依頼により、このタスクのheartbeat「mlibを保守しやすく整理（6時間）」(mlib-6)を作成・ACTIVE/6回を読戻し確認。日本時間10/23 23:06開始、以後1時間ごとに10/24 04:06まで計6回、作業期限05:04。Maya上級/Python初〜中級者が追える通常の関数・明示的分岐を優先し、decorator/contextは可。不要内部処理→Node/Plug入力解決→更新/Undo・fast・safe→Component→数学/util→全体検証の6段階、各回おおむね50分以内、公開契約/並行差分/拡張を維持しコミット・pushなし。進捗.maya-output/mlib-hourly-refactor-20261023/progress.json。今回ターンはスケジュール設定のみで製品コード変更なし。

- Codex (2026-10-23): ユーザー指定の_core→core、直下decorator/util集約と小ファイルの責務移管を実装。fast/safe/flagsをdecorator、公開3/内部8関数をutil、単位変換をattributeType、型継承cacheをregistry、集合戻り判定をNodesへ集約しCommandResultを既存resolverへ置換。実装181→170ファイル（common19/core12）、33,188→33,015物理行。旧互換入口を残さず利用側・テスト・公開検査・日英Sphinx・作業指針を更新。Maya2022〜2027各137ファイル/1,178件成功（環境依存skip旧3版6/新3版3）、隔離2027のコマンド追加/変更/削除・root直接reload成功。mlrig/拡張は268件中267成功・境界監査1失敗で、未変更HingeIK/PlanarIKのcmds31/OM2 import2の計33指摘が開始前ソースでも一致することを確認し対象外として保持。Maya不要53件、Python3.7構文/公開/layout、日英Sphinx-W各371HTML/署名/静的検査成功、既存英訳8,197件維持・日本語未訳/fuzzy0。独立レビューは既存署名差0・1,527関数の正規化AST一致・155クラス基底/型表/865内部import照合成功。初回のfastWrite相対import漏れは修正後に全6版を再実行し解消。詳細.maya-output/mlib-layout-20261023/、レビュー.maya-output/mlib-util-plan-20261023/decorators/。研究メモ/生成物はGit・Sphinx対象外、GUI操作/性能測定は未実施。既存WORK_LOG履歴を保持。

- Codex (2026-10-23): 最新指定の直下util.py・_core→coreを前提にdecorator/common/coreの配置を調査。fast/safe/flagsをdecorator、汎用5モジュールを直下util（公開3/内部8関数）、core小4モジュールを既存担当へ寄せる案を作成し、実装181→170（common24→19/core19→12、新util1追加）を独立したpath集合で検算。旧import/遅延再公開終了、フォルダ名と公開契約の分離、reloadのcore旧名削除・固定テスト・拡張/型/pickle・日英Sphinx/利用側の更新範囲を明記。詳細docs/research/mlibDecoratorUtilCorePlan20261023.txt、根拠.maya-output/mlib-util-plan-20261023/（Git/Sphinx対象外）。181製品実装SHA不変、AST/現行公開検査/独立レビュー/差分検査成功。調査のみで製品/正式文書/既存テスト変更、Maya/新配置Sphinx実行、コミット/pushなし。既存WORK_LOG差分を保持。

- Codex (2026-10-23): core確定前に_core19ファイル2,860物理行99定義と参照/値/編集/拡張境界を調査。次の配列番号の型・上限、fast改名の別namespace Shape変更、同秒同サイズpycのreload反映を再現し、Joint自己/子孫の親付け計画が受理されることも確認（実適用なし）。Plug改名と固定hash、生SDK借用、generic配列の形、bulk override、reload部分失敗/拡張配布形式は現契約と明文化・明示変更を分離。forceの二段階修復を不具合と扱わず、未使用4定義約130行と文書/試験のずれも候補化。Maya2022/2027で最小probe、2027で通常/fast計6条件、付属Python3.7.7/3.13.9でMaya未importの実関数probeを実行。181製品実装SHA不変、独立レビュー・差分検査成功。詳細docs/research/mlibCoreFreezeAudit20261023.txtと.maya-output/mlib-core-freeze-20261023/（研究/生成物はGit・Sphinx対象外）。製品/正式文書/既存テスト変更と全件回帰/GUI/性能測定/コミット/pushなし。既存WORK_LOG差分を保持。

- Claude Code (2026-10-23): mlrigに `HingeIK`(膝の向きをヒンジ軸へ合わせ自由度を1軸にしたRotate Plane IK)と `PlanarIK`(回転中心に作った平面のIK用チェーンで解き、元のjointへorientConstraintで回転だけ渡す)を追加。どちらも作成時に姿勢が跳ねない(preferredAngleは現在値、ポールベクターは作成時のpoleVectorの延長上)。試験15項目をMaya2025/2027で確認。Sphinx(hinge_ik/planar_ik)、検証動画デモ tools/demo_offset_leg_ik.py(384フレーム全判定成功、赤の普通IKは膝が最大約70度の多軸回転)、Drive「Maya検証動画/HingeIK_PlanarIK」へ保存。コミット 983e5b6 をプッシュ。Driveの動画はリンク共有が未設定(コネクターで設定できないため)。

- Codex (2026-10-23): ユーザーのpush依頼に基づき、mlib縮小A・Bと追加上2案、依存するmlrig・検査ツール・日英文書の269ファイルをコミット対象に選定。直前のMaya2022〜2027・mlrig253件・Maya不要53件・日英Sphinxの検証結果と差分を照合し、研究メモ/生成物と並行するhingeIK/planarIKの追加・共有ファイル編集を除外。共有WORK_LOGはCodexの今回分完了履歴だけをstageへ反映。詳細.maya-output/mlib-shrink-push20261023/。

- Codex (2026-10-23): ユーザー指定の追加縮小上2案を実装。演算14型はクラス/継承/公開/型登録を維持して71専用メソッドを終了し、Maya標準名のPlug操作へ統一。is省略57入口（undo.enabled含む）と専用helper/Sphinx投影を廃止し正式is名を使用。保持1,562定義の引数/decorator/実行本体と全156クラスの基底、nodes/plugs公開・型表が開始前と一致し、複数形/reload/自動探索/数学所有権/単位/通常Undo・fastと専門編集・保存・小便利/Cを維持。181実装33,188物理行、今回分2,013行（docstring等を含む）/code617行減。Maya2022〜2027各137ファイル/1,178件を実行し、旧3版の型未登録フォールバックに対するテスト期待値を修正後、該当4件を全6版で再実行して失敗を解消（全体の環境依存skipは旧版6/新版3）。mlrig2027統合253件、Maya不要53件成功。日英Sphinxを-Wでビルドし各383HTML/正式get・is参照/7コマンド署名の検査成功。英訳未訳/fuzzy/記法エラー0、mlrig PO保持。Python3.7構文/公開/レイアウト/独立レビュー/差分検査成功。GUI・性能測定は未実施、ブラウザー表示はPlaywright未導入で未検証。結果.maya-output/mlib-top2-20261023/result.json。既存A+Bと他作業差分を保持、未コミット・未プッシュ。

- Codex (2026-10-23): A・B後のmlib182実装35,201物理行を再調査し、拡張性を維持した追加縮小案をdocs/research/mlibExtensionShrinkPlan20261023.txtへローカル保存。演算14型の専用API終了（型クラス保持）1,178行＋判定alias56入口/専用helper732行を第一候補とし、専門編集/保存/再配分と小便利群まで含む重複控除後の対象を3,747物理/doc2,140/code1,423（10.64%）と試算。移行追加前であり、A+B/C・移設のみの535行・docだけ短縮は非計上。Node/Plug登録、Nodes、reload、自動探索、数学所有権/単位/Undo・fastを維持。拡張登録基盤661行・薄い型群は削減非推奨、API保持の内部整理は22行程度。182実装SHA不変、独立union/依存レビュー・公開入口不一致0・差分検査成功。成果は.maya-output/mlib-extension-shrink-20261023/。製品/正式文書/テスト変更、Maya実行、コミット/pushなし。既存A+B未コミット変更と他作業を保持。

- Claude Code (2026-10-23): `HTools/rigging/ueCollisionGuide.py` を追加。UEのコリジョン(カプセル・球・箱)のガイドメッシュを作り、半径・長さ(円柱部分。UEと同じ)・分割数・箱の寸法をトランスフォームのアトリビュートから作成履歴へつないで後から変えられる。原点に作る・選択(メッシュ/頂点/辺/面)を包む(simpleCollisionFromSelectionのOBBを利用)・2つのジョイント間で追従(長さはエクスプレッション)の3通り。名前はUCP_/USP_/UBX_+対象名+_01。mlib非依存(cmds・OpenMaya)。Maya2022/2027のmayapyで寸法・包含・追従・cm/m・bake・Undoを確認し、2027のGUIで画面とHToolsメニューを確認。未コミット。

- Codex (2026-10-23): ユーザー指定のmlib縮小案A・Bを実装。汎用UI/設定/型付きJSON・Snapshot/専用色/Scene・Workspace・FBX/mlib版OBBを廃止しcmds37→7入口へ集約。mlrigは標準json/cmds/mel・既存オブジェクトAPIへ移行し、viewportOffの状態復帰とHTools既存OBBを維持。旧互換入口・型付き保存形式readerなし。mlib実装244→182ファイル、42,909→35,201物理行（docstring等を含む7,708行/17.96%減、code3,097行減）。CのMesh/DagPose機能、保持APIの引数・単位・返却・数学所有権・複数形/reload/拡張探索/Undo・fastは維持。Maya2022〜2027各138ファイル/1,191件成功（旧版6/新版3skip）、mlrig2027統合253件、専用GUI2022/2027各20項目、Maya不要54件成功。mlrig2022全件は既存2025+制限50件・DLL不足4件のエラーと未変更Soft IK旧版精度の119subtest失敗を確認し対象外として保持。mlib/mlrig日英Sphinxを-Wでビルドし、mlib日英各384HTML・正式取得名・公開入口・書式・差分検査成功。英訳は廃止項目を除き未訳0、mlrig POと別作業変更を保持。結果.maya-output/mlib-ab20261023/result.json。性能測定・リグ動画検証は未実施。未コミット・未プッシュ。

- 2026-10-23 Claude Code: HTools > rigging > createTwistJoints を追加。根本と末端のジョイントの間を個数+1等分した位置に、根本の子で回転・jointOrient・rotateAxis が0のジョイントを作る(rotateOrderは根本に合わせる、1回のUndo)。mlib非依存(cmds・OpenMaya 2.0のみ)。mayapy 2022/2027で40項目、GUI(runpyで開いてCreate)を2022/2027で確認。
- 2026-10-23: Codex がmlibの提供機能縮小を検討。UI/設定/JSON＋BS単体delta/色/Scene・Workspace・FBX/mlib版OBBの提供終了案Aは6,516物理/code2,635行、cmds37→7の案Bは累計7,544/code2,948、Mesh頂点番号再構築/DagPose統合の案Cは累計8,107/code3,394を重複なし対象として集計（移行追加控除前）。JsonText12files26callsのstdlib移行、GUI起動/viewportOffの代替、旧型付きJSON保存契約終了、HTools既存OBB保持を条件へ明記。複数形/reload/拡張探索/数学/Undo・fastと小便利を維持。詳細はGit対象外docs/research/mlibFeatureScopePlan20261023.txt。244実装SHA一致、依存閉包・集計の独立レビュー成功。製品/正式文書変更なし、静的検討のみでMaya未実行、既存他作業差分を保持。

- 2026-10-23: Codex がad1ab27後のmlib大幅縮小候補を追加調査。244実装42,909物理行をdoc20,982/code17,992等へ分離し、重複本体・主要型・内製利用側を確認。OBB二重実装は内製全体約370〜390物理行、Joint不要内部定義は42〜63行の純減候補。UI/設定/Snapshotの計3,416物理/code1,312行は機能範囲変更の場合だけの規模として、doc短縮・外部移動と区別。確定API/数学/Undo/fast/複数形/reload/自動探索を維持する条件を整理。詳細はGit対象外docs/research/mlibLargeShrinkAudit20261023.txt。244実装SHA一致と独立レビュー確認、製品コード・正式文書変更なし、静的調査のみでMaya未実行。既存の他作業変更を保持。

- 2026-10-23: Codex がユーザー依頼によりmlib整理一式と依存するmlrig/HTools/文書/テストをコミット・push対象に選定。共有3ファイルはJointHierarchyとAim設定テストの登録だけをindexへ反映し、別作業Swing/Twist系と外部submodule差分を保持。検証済みmlib244実装のSHA一致、indexだけから取り出した構成のMaya2027 setups93件、ステージ差分検査が成功。Aim設定テストを既存ランナーへ登録。調査メモ/生成物はGit対象外。詳細.maya-output/mlib-maintenance-push20261023/。

- 2026-10-23: Codex が保守性整理を実装。固定Plug/接続転送9入口を廃止し設定18項目をAimAxisConversionへ移譲。ArrayPlug.getIndicesへ列挙、Plug範囲照会/頂点集約/JSON値・CV・SDK接続/HToolsスキン保護を既存基盤へ集約。検証付き算術/範囲/alias便利APIと確定引数・単位・返却・Undo/fast・overrideを維持。日英Sphinxと利用側/テストを追従。mlib実装244本43,019→42,909物理行、公開入口は9廃止/1追加。Maya2022〜2027各153ファイル1,343件失敗0（旧版11/new版8skip）、移譲Aim設定各3件、HTools旧/new8条件、Maya不要49件、日英各489HTML/公開入口/レイアウト/Python3.7構文/差分検査と独立レビュー成功。結果.maya-output/mlib-maintenance20261023/result.json。GUI実操作・性能測定は未実施。既存未コミット/他作業変更を保持、未コミット・未プッシュ。
- Codex (2026-10-23): QPEの内容最小サイズがMayaドックへ伝播する問題をスクロールコンテナで修正。固定行より下で縮小不能になる配置を補正し、Qt5の再ドック時の無効親ラッパーも回避。Maya 2022/2027で右・下ドックの反復縮小/拡大と境界のマウスイベント、2027でシーン操作と4段階の再起動復元を検証。結果は.maya-output/verification/qpe-dock-size/。実マウス・複数DPI環境は未検証。ユーザー依頼によりQPE関連差分をコミット・プッシュ対象に選定。
- Claude Code (2026-10-23 08:50〜, 夜間タスク2回目): mlrig.setups.AsymmetricSwingLimit(直交2軸の+側・-側で別の限界角を持つ象限ごとの楕円コーンのソフトなSwing制限、標準ノードのみ)を追加。SwingLimitを_build/_limitGraphに整理しexcessAngle出力を追加(既存テスト通過)。setups/asymmetricSwingLimit.py・setups/swingLimit.py・setups/__init__.py(追記)・__tests__/test_setup_asymmetric_swing_limit.py(6件)・docs/asymmetric_swing_limit.rst・docs/index.rst・docs/swing_limit.rst・tools/test_rig_packages.py(追記)・tools/demo_asymmetric_swing_limit.py。隔離mayapyでsetups 108件・standard 76件OK、Sphinx -W成功、検証動画744フレーム全OK(Drive同期フォルダーへ保存、リンク共有は未設定)。Codexのmlib/mlrig未コミット変更と前夜分を保持。**未コミット**。

- 2026-10-23: Codex がmlibの削除・共通化候補を調査。先行9メソッド76行、条件付き算術入力12メソッド等と内部委譲候補を整理。詳細はGit対象外のdocs/research/mlibApiShrinkCandidates20261023.txt。製品コード/APIは未変更、静的調査のみでMaya未実行。

- Codex (2026-10-23): コーディング規則調査の全候補を修正。getSettingPlugs/getOutputPlugsと内部helperを正式名へ更新し旧aliasなし、内製利用側・テスト・Sphinx・翻訳カタログ識別子も追従。内部名・OpenMaya別名・重複/未使用import・contextmanager・logging遅延書式・引用符・単純な埋込み・docstring引数順/区切/Returns/fast説明を統一。空間検証の重複5箇所と軸12入口の転送を整理。旧規則文書の矛盾、通常例外と通知/stream出力の境界をAGENTS/API設計/Sphinxへ明文化。layoutは既知の判定aliasとTYPE_CHECKING注釈の依存を保持し、classスキップ27→0、5classを整列。244実装の並び替えsnapshot差0、公開引数維持、Maya2022実Pythonで244構文成功。Maya2022～2027各151ファイル/1,325件の回帰と各41件の修正箇所再検証により失敗解消（旧版11/new版8skip）。旧Pythonのf-string引用符問題、旧回復案内の期待、logging fakeを修正済み。mlrig/拡張246件、Maya不要54件、mlib/mlrig日英Sphinx -W、各489HTMLの公開取得名/配布検査成功。結果.maya-output/style-unify-20261023/result.json。確定引数/単位/返却/例外/Undo/fastと既存未コミット変更を保持。GUI・性能測定は未実施、未コミット・未プッシュ。

- Codex (2026-10-23): 現在のmlib全実装244ファイル42,060行をAST・ソース・既存規則で確認。確定ルール、意図した例外、旧規則文書の矛盾、get未付与の取得名候補、内部名/import/文字列/docstringの揺れ、通常例外と通知・stream進捗出力の境界を整理。統一候補と全ファイル一覧をdocs/research/mlib-coding-rules-20261023.txtへローカル保存（Git対象外）。公開入口検査は不一致0、レイアウト検査244files/違反0/情報32（import群5・class順序27の検査スキップを区別）。製品コード・公開仕様・正式規則の変更、Maya実行、コミット/pushなし。既存未コミット変更を保持。

- Codex (2026-10-23): 複雑性調査の整理を実装。getAttr廃止・getPlug/値/状態照会へ分離、配列getterのcreate/addElementとdisconnectのbool方向/dstを廃止、generic参照は非評価の基底Plugへ統一。Joint削除は標準化し、ウェイト移送/子保持はmlrig.setups.JointHierarchyへ移譲。moveAttrOrderの定義/短名/soft limits/alias/接続/途中失敗復元、addAttr事前検証、fast接続ロック復元を修正。Transformの計算と書込み、bulk管理表、root型登録初期化（bootstrap廃止）、拡張可用性検査を整理。確定Transform引数・数学値所有権・fast継承、複数形/reload/自動探索は維持。Maya2022～2027各151ファイル/1,324件で失敗0（旧版11件、新版8件skip）、Maya2027のmlrig/拡張/連携245件と追加17件、独立コマンド探索に成功。日英Sphinx警告エラー扱いビルド、公開入口/書式/構文/文書検査も成功。元のmoveAttrOrder再現2ケースの解消を再確認。mlib実装247→244ファイル、42,485→42,060物理行（docstring等含む）。結果.maya-output/mlib-complexity20261023/result.json。GUI・性能測定は未実施。既存SwingLimit/TwistLimit変更を保持し、未コミット・未プッシュ。

- Claude Code (2026-10-23, 夜間タスク): mlrig.setups.TwistLimit(Twistの非対称ソフト可動域制限、標準ノードのみ、excessTwist出力)を追加。setups/twistLimit.py・setups/__init__.py・__tests__/test_setup_twist_limit.py(6件)・docs/twist_limit.rst・docs/index.rst・docs/swing_limit.rst(案内1文)・tools/test_rig_packages.py・tools/demo_twist_limit.py。隔離mayapyでsetups 82件・standard 76件OK、Sphinx -W成功、検証動画528フレーム全OK(Driveへ保存、リンク共有は未設定)。前夜のSwingLimitの未コミット変更を保持。**未コミット**。

- Codex (2026-10-22): mlibに残る暗黙動作・多重モード・失敗時挙動を追加調査。隔離Maya2027 standaloneでmoveAttrOrderの短名/soft limit消失と対象内接続の再作成失敗を2ケース再現し、手動Undoでの復元を確認。getAttr/配列要素/値依存Plug/Joint削除/接続/Transform/数学値/fastとUndo/addAttrを整理し、複数形・reload・拡張自動探索を維持する内部管理の整理候補も確認。公開仕様変更案と互換な内部整理を区別してdocs/research/mlibComplexityAudit20261022.txtへ保存（Git対象外）。製品コード・公開仕様・Sphinx変更、全件回帰、他Maya版検証、コミット/pushなし。並行するmlrigの変更を保持。

- Codex (2026-10-22): ユーザー指定により複数形class一式・reload・拡張自動探索を維持する前提へ縮小案を改訂。廃止/list化/手動登録必須化の案を撤回し、残る周辺機能の候補を55ファイル6,243行（docstring含む、代替実装控除前）へ再集計。bulkExecution/reload/extensions等が削減対象に混在しないことを照合。docs/research/mlibSmallCoreDesign20261022.txtを更新（Git対象外）。製品コード・公開仕様変更、Maya実行、コミット/pushなし。並行作業の変更を保持。

- Codex (2026-10-22): AIなし保守を目的にmlibの大幅縮小案を静的調査。ノード複数形5class3,024行/179defと転送・署名・管理表の同期負担、未使用UI/設定/Snapshot、cmds入口、reload/拡張自動探索、省略判定入口の廃止候補を整理。重複除外した候補量10,080行（docstring5,237行含む、代替実装控除前）と内製利用・失う機能を確認。Node/Plug/Components/数学・Undo/fast・実使用JSON/イベント等を維持し、ノード/メソッド追加だけで拡張する推奨設計をdocs/research/mlibSmallCoreDesign20261022.txtへ保存（Git対象外）。公開入口検査は不一致0。製品コード・公開仕様変更、Maya実行、性能計測、コミット/pushなし。並行するmlrigの変更を保持。

- Claude Code (2026-10-22): 夜間タスクで `mlrig.setups.SwingLimit`(楕円コーンのソフトなスイング可動域制限、標準ノードのみ)を追加。setups/swingLimit.py・setups/__init__.py・__tests__/test_setup_swing_limit.py・docs/swing_limit.rst・docs/index.rst・tools/test_rig_packages.py(setupsへ登録)・tools/demo_swing_limit.py。setups/standardスイートOK、Sphinx警告なし、隔離GUIで600フレームの検証動画(ok=True)をDrive同期フォルダーへ保存(リンク共有は未設定)。未コミット。

- Codex (2026-10-22): mlibの前回統合後を静的再調査。247実装ファイル42,485行・公開メソッド定義1,322件を確認し、入力再解決、一括照会、形状/AnimCurve参照再構築、Transformationコピー、fast検証と複数形の引数再検証、Plug/DAG/監視の責務移譲を次段階案として整理。優先順位・維持契約・既存テスト・計測条件をdocs/research/mlibRefactorNext20261022.txtへローカル保存（Git対象外）。公開入口検査は不一致0。製品コード・公開仕様・Sphinxの変更、新規Maya実行・性能計測、コミット/pushなし。

- Codex (2026-10-22): ユーザー指示で未コミット全変更をGit反映対象として確認。残っていたQuickPathExplorer/launch_python.batのMaya2027固定起動への変更を含め、作業ログとともにコミット対象へ追加。mayapy・Qtプラットフォームディレクトリ・起動対象スクリプトの存在と差分チェックを確認。GUI起動は未実行。

- Codex (2026-10-22): ユーザー指示でmlibリファクタリング・使用側・テスト・文書をコミット/プッシュ対象として確認。Maya2022〜2027の成功記録と差分・公開入口を再確認し、最終レビューでnative MPlug.nameの誤置換とextensions.__all__の削除済み名を修正、文書のgetDiagnostics表記も統一。関連11テスト成功。研究メモ・生成物・submodule参照更新は含めず、既存QuickPathExplorer/launch_python.bat変更を保持。

- Codex (2026-10-22): mlibの取得をgetへ統一し省略入口576件・単純演算アクセサー68件を削除、使用側・テスト・Sphinxを移行。接続/単位フラグ、getChildrenへの列挙統合、ControlHierarchyのmlrig移譲、OM2照会とUndo/fast更新を実装。fast未対応条件は変更前に拒否し文書化。Maya2022〜2027の全体回帰成功、最終2027は147ファイル/1,311テストで失敗0。接線/単位等の追加24件は2022/2023/2027で成功、mlrig/拡張186件は失敗0（1skip）。文書15コード例、Sphinx警告エラー扱いビルド、公開入口/文書/レイアウト検査に成功。GUI・対応バイナリ不在の検証はskip。既存QuickPathExplorer変更を保持し、未コミット・未プッシュ。

- Codex (2026-10-22): ユーザー指定を反映したmlib縮小とOpenMaya化の計画をdocs/research/mlibRefactorPlan20261022.mdへローカル保存。get省略576件/is省略62件を分離、単位と接続のフラグ案、Transform系を除く演算アクセサー削減、DAG列挙共通化、mlrigへの移譲と更新/削除のfast不足を精査。Undo保全・Joint削除・pivot空間差・API非対応の例外を明記。公開入口検査は不一致0。本体変更・Maya実行・性能計測・コミット/pushなし。既存WORK_LOGとQuickPathExplorer変更を保持。

- Claude Code (2026-10-22): `tools/video_summary.py` に `--num-gpu`(OllamaでGPUに載せる層の数)と、CUDAエラー時の1回の言い直しを追加。手元の環境ではOllama 0.35.1のgemma3:27bを全層GPUに載せると画像の読み取りが意味のない記号になり、62層にすると直った。

- Codex (2026-10-21): mlibの静的棚卸しと縮小案を作成。実装256ファイル51,142行、公開メソッド定義1,924（省略入口623）、演算ノード22ファイル430入口を確認。二重入口・専用アクセサー・DAG内部列挙・複合セットアップを候補化し、単位/回転順序/接続方向等の意味が異なるAPIは維持対象に分類。ローカル調査メモはdocs/research/mlibRefactorAudit20261021.md。公開宣言検査は不一致0。Maya未実行、本体変更・コミット・pushなし。既存QuickPathExplorer変更を保持。

- 2026-10-20 Codex: ユーザー指示でQPEのドライブ一覧・シーン読込後のフォルダー追従と関連テスト/文書をコミット・プッシュ対象として確認。Windows/Maya2022/2027の既存成功結果と差分検査を確認。既存launch_python.bat変更と生成物は対象外。

- 2026-10-20 Codex: 専用Mayaで操作録画・数値判定を実施し、MP4の実フレームを確認。Drive保存後にサイズ・閲覧URL・非公開権限を確認。生成物はGit対象外。iPad再生は未確認。

- 2026-10-20 Codex: QPE左サイドバーにDrivesを追加。MSceneMessage kAfterOpenで標準/スクリプト/QPEからのシーン読込後に保存先へ移動、保存・新規・取消では場所維持。通知はウィジェット破棄時解除。初回scriptJobの遅延とMaya2022のQProxyStyleアイコン取得エラーを修正。Windows inspector、Maya2022/2027 scene/inspector合格、exe再ビルド・起動合格。証跡.maya-output/verification/qpe-drives/verified-results.json。新規録画・実ドライブ抜差し・切断ネットワーク・iPad未検証。既存launch_python.bat差分保持、未コミット・未プッシュ。

- Claude Code (2026-10-19): 動画をローカルだけで文字起こし・画面の文字の読み取り・要約する `tools/video_summary.py` を追加(ffmpegで音声とコマを取り出し、faster-whisper large-v3で文字起こし、Ollamaのgemma3:27bで画面の文字と日本語の要約)。ffmpeg(winget)・gemma3:27b・専用venv(.maya-output/video-summary/venv、Git対象外)を導入。手元の動画(英語音声と日本語字幕の動画・日本語音声の約26分の動画(全体を7分44秒で処理)・無音の画面録画)で確認。Ollamaの一時的な500(token repeat limit)に備えて1コマずつ言い直し、文字起こしはtranscript.jsonで再利用。2026-10-20: 日本語以外の音声は文字起こしをOllamaで日本語へ訳しtranscript_ja.txt/.srtを出力(30行ずつ訳し、行数が合わなければ1行ずつ。--no-translateで省略、訳もtranscript_ja.jsonで再利用)。手元の英語の動画5分で34行の訳と再利用を確認。端末の文字コード(cp932)で表せない文字のログで止まる問題、要約の繰り返し打ち切り(token repeat limit)で止まる問題を修正(設定を変えて1回言い直す)。画面の文字もscreen_text.jsonで再利用。手元の約74分の動画で全体を確認。

- Claude Code (2026-10-19): FramePlayerのドキュメントの画像10枚を拡大率100%の画面で撮り直し(右クリックメニューの「Show Time」、既定でオンの時刻表示を反映)。トップの画像の説明に時刻の表示を追記(英訳1文は手で追加)。未コミット。

- Claude Code (2026-10-19): FramePlayerのフルスクリーンで、操作が無いと3秒で操作部とカーソルを隠す(YouTubeと同じ。再生中も停止中も、マウス・キーで出す、操作部の上・ドラッグ中・入力中・メニュー中は隠さない)。操作部を子ウィンドウ(マウス素通し)にして映像に重ね、半透明で薄くしながら隠す(マニフェストでWindows 8以降を宣言)。動きを子ウィンドウの表示の有無で確認し、動画を .maya-output/frameplayer-autohide-demo(Git対象外)に作成。ドキュメント・README・配布用exeとセットアップを更新。未コミット。

- Claude Code (2026-10-19): FramePlayerに実時間の表示を追加(右クリックの「Show Time」で映像の右上に「経過時刻 / 長さ」。既定はオン。目次の各コマの表示時刻から計算、比較中は左右それぞれ、設定ShowTimeで保存)。最初の窓を表示の拡大率に合わせた大きさで開く(作業領域に収まらなければ9割に縮めて中央)。完成イメージ動画は .maya-output/frameplayer-time-demo(Git対象外)。ドキュメント(英訳5文は手で追加)・README・配布用exeとセットアップを更新。未コミット。

- 2026-10-14 Codex: asString追加の差分・検証結果を確認し、コミットしてorigin/mainへプッシュする。

- 2026-10-14 Codex: Object.asString()を追加しNode・Plug・単数Componentで共通化。strと同じ現在名を返し、既存の添字アクセスを維持。受け渡しドキュメント更新。Maya 2027 standaloneの関連4テスト成功、公開漏れ検査0件。

- 2026-10-13 Claude Code: Maya Code Editor 0.7.2。起動時にuiScriptがプラグインのロードより前に動くと、表示されたままの空のドックを「復元済み」とみなしてopen:falseを保存し、再表示されなかった。中身が無ければロード時に入れる・uiScriptの遅延の非表示はロード済みなら何もしない・ロード時の復元をevalDeferred -lowestPriority(内部フラグ -restorePrevious)へ移した。回帰テスト tests/restore_order_smoke.py を追加。
- 2026-10-13 Codex: Maya 2027 standaloneでPlug特殊メソッド4条件×7操作を検証。__getitem__のみ除去するとgetAttr/setAttr/connectAttr等の直接入力が成功、__iter__除去のみでは失敗。正式実装変更なし。結果は.maya-output/plug-protocol-probe/result.json。

- 2026-10-13 Codex: cymel方式のmlib試作で反復開始時に状態解除し、list後の複合/配列Plug添字取得を修正。Maya 2027 standaloneで確認。正式実装への導入は未実施。len単独とsetAttr直接入力の制限は残る。

- 2026-10-13 Codex: Maya 2027 standaloneでcymel Plugを検証。getAttr直接入力成功、setAttr double3直接入力失敗。mlib一時適用ではlist後の添字取得が親を返す副作用を再現。正式実装変更なし。結果は.maya-output/cymel-interop/result.json。

| Codex | 2026-10-10 | mlib cmds相互運用調査 | Maya 2027 standaloneで既存3テスト成功。Node・単一Plug・Componentの直接入力と、複合/配列Plugのstr変換が必要な条件を確認。実装変更なし。 |

- 2026-10-13 Codex: QPEの用語統一、Save Scene As/New Scene、既定mb、Maya Recent Files連携と関連テスト・文書をコミット対象として整理。Windows/Maya2022/2027の既存成功結果と差分を確認。ユーザー指示によりmainへプッシュする。調査資料・動画等の生成物は対象外。

- 2026-10-13 Codex: Maya QPE上部にNew Sceneボタンを追加（Windows単体非表示）。既存の未保存確認を再利用しSave/Discard/Cancelを処理。専用Maya2022/2027で実新規作成・実保存・Cancel/保存取消/保存失敗のシーン維持・Discardの既存ファイル保護・未変更時の確認省略を検証、Windows非表示も合格。証跡.maya-output/verification/qpe-new-scene/verified-results.json。新規録画なし。未コミット・未プッシュ。

- 2026-10-13 Claude Code: Maya Code Editor 0.7.1。画面の一番下(コマンドラインの下)へドックすると高さを変えられない(Maya標準の部品でも同じ)ため、自分でドックするときはタイムスライダーの上に入れ、一番下に残ったドックは開いたときに移すようにした(src/plugin/dock.cpp)。回帰テスト tests/dock_resize_smoke.py を追加。mlib改名で壊れていた search_smoke の期待値と、gui_smoke の出力待ちのタイミングも修正。
- 2026-10-13 Codex: QPE用語監査15項目を反映。Tab set/操作履歴/一方向コピー/拡張子/探索起点/付随情報/名前空間/詳細一覧等を統一。Recent itemsとRecent foldersは対象を区別。競合表示Keep bothを内部renameと分離し、実コピーで両方保持を検証。保存キー・コマンドID維持。Windows6、Maya2027 4、Maya2022 2スイートと再ビルドexe起動合格。初回UXの旧ラベル、Maya2027 advancedのテストウィンドウ非アクティブを修正して再検証。証跡.maya-output/verification/qpe-terms/verified-results.json。新規録画なし、前回動画は今回文言未反映。未コミット・未プッシュ。

- 2026-10-13 Codex: QPEの画面・メニュー・ダイアログ用語を静的監査。Windows/Maya一次資料と比較し、Workspace/File historyの概念衝突、競合rename、一方向同期等15候補をdocs/research/qpe-terminology-audit-20261013.txtへ保存（Git対象外）。製品コード変更・GUI検証・新規録画なし。既存の未コミット実装を保持。

- 2026-10-13 Codex: QPE表示をWindows/Maya用語へ変更(Delete/Properties/Save Scene As等、内部履歴ID維持)。Maya限定の上部Save Scene Asボタン、既定mb、明示ma選択、標準addRecentFileによるOpen/Save成功後のRecent登録を実装。長い保存先で入力欄が潰れる高さ計算も修正。専用Maya2022/2027で実保存・元ファイル保護・履歴重複/形式・失敗/取消を確認。Windows8、Maya各5スイート合格、exe再ビルド・起動合格。初回UXの旧ma期待値と管理外modern検証画面の終了破棄を修正して再検証。動画/画像は既存非公開Driveへ保存: https://drive.google.com/file/d/1tryXOjlz3W-HDbsAqusBDBVaGJsuZnhW/view?usp=drivesdk 。証跡.maya-output/verification/qpe-scene/verified-results.json。実IME/混在DPI/iPadは未確認。未コミット・未プッシュ。

- 2026-10-13 Claude Code: 体の回避をUE RBFで学習する版(`tail_shared_avoid.buildRbfDelta`、`motion="*_rbf"`)を追加し4方式を比較。前腕のコーンの右側の向きと、コーンの外での aimConstraint の跳びを修正(demo_tail_twist_cancel・demo_tail_layers)。
- 2026-10-13 Codex: ユーザー依頼に基づきQPE高速化・共有LRU・表示更新集約・性能回帰テスト・録画補助修正をコミット／プッシュ対象として整理。既存Windows16、Maya2022/2027各7、exeの成功記録を確認。無関係なリグ変更と他担当の作業記録は保持して対象外とする。

- 2026-10-13 Claude Code: 体の回避をConeReaderで簡易化した版(`tail_shared_avoid.buildConeDelta`、`motion="*_compare"`)を区間のclampと比較。跳びと食い込みが残り、ノードは約25%減に留まるため区間の方式を基準に残す。
- 2026-10-13 Codex: QPEを計測して高速化。アイコンをウィンドウ内共有・上限2048件のLRUへ整理し、カラム装飾と件数の連続通知を集約。ローカルPNG1000枚を各3回計測し、一覧中央値4.109→2.969秒、サムネイル切替2.188→0.703秒。性能回帰を標準スイートへ追加。Windows16、Maya2022/2027各7スイート合格、exe再ビルド・起動合格。初回Maya2027のショートカット検証はフォーカス確定を待つ形へ修正し再検証合格。録画ヘルパーに入力継承防止と60秒タイムアウトを追加したがMaya2027子FFmpegの停止原因は未特定。保存フレームをMaya外で変換・確認、UIは録画なし再検証。動画は既存非公開Driveへ保存。2027動画 https://drive.google.com/file/d/1NTIC0ZfVQCMRPIODdeRUWrmfQc0CXSO9/view?usp=drivesdk 。証跡.maya-output/verification/qpe-performance/verified-results.json。実IME/物理ホイール/混在DPI/ネットワーク共有は未検証。無関係なリグツール変更は保持。未コミット・未プッシュ。

- 2026-10-13 Codex: 承認済みQPEモダンUIの実装・アイコン・説明書・回帰テストをコミット対象として確認。既存の24 UIスイートとexe起動の検証記録、差分チェックを確認し、origin/mainへの反映作業。動画・調査資料・配布生成物はGit対象外。
- 2026-10-13 Codex: QPEモダンUIを実装。共通の余白/枠/フォーカス/矢印、13px既定文字と行間切替、Viewへの表示設定集約、個別解除フィルター、右ペイン情報→操作/読込設定の折畳み/縦スクロールに対応。Windows14、Maya2022/2027各5 UIスイート合格、配布exe再ビルド・起動合格。Maya2022の管理外テスト画面の終了クラッシュは検証側の明示破棄で修正し再検証済み。動画2本と画像を確認し既存非公開Driveへ保存。Maya動画 https://drive.google.com/file/d/1y-P8dhhq-4I0vHVGhIl_1GqKEdT0HHno/view 。証跡.maya-output/verification/qpe-modern。物理4K/混在DPI/実IME/iPadは未確認。未コミット・未プッシュ。
- 2026-10-13 Codex: QPEの保存済み実操作画像・テーマ実装とFluent公式の余白/文字/色指針を比較。Apple/Materialも参照し取得制限を記録。高密度を維持した部品・状態・操作行整理を提案。調査はdocs/research/qpe-modern-ui-20261013.txtにGit対象外で保存。製品変更・新規実機検証/録画なし。
- 2026-10-13 Codex: ユーザーのプッシュ依頼に合わせ、QPEの機能追加・関連付けアプリで開く動作・UX修正・検証コード・説明書をコミット対象として整理。既存検証記録と差分チェックを確認し、動画・ローカル成果物・調査資料を除外。origin/mainへの反映作業。

- 2026-10-12 Codex: QPE全操作レビューと不具合修正。階層往復、欠損タブ復元、固定タブ、転送行選択、設定検証、空フィルター後の列幅、終了時shibokenクラッシュを修正。Open/ダブルクリック/Spaceは.ma/.mbのみ現在Maya、他形式と単体版はOS関連付け。独自ビューアーを撤去。バックエンド60、単体14スイート、隔離Maya2022/2027各16スイート合格。両Mayaのドック再起動・停止中転送からの終了も確認。exe再ビルド・起動合格。実UI8章約6分、関連付け実機確認画像動画、索引、未実施手順を非公開Driveへ保存。実IME/物理ホイール/混在DPI/ネットワーク断等は未実施。証跡qpe-full-audit・qpe-associated・qpe-full-review-r3/r4。全編 https://drive.google.com/file/d/1Cvhls4fMV9bS2cBvdd0dxU5Xk49T0mQr/view 。今後のQPEレビュー報告には毎回動画リンクを添付。未コミット・未プッシュ。

- 2026-10-12 Claude Code: 尻尾のレイヤー構造(効果ごとの関節を重ね、tailLayers_CTRL で ON/OFF)と段階の並列表示のデモ `tools/demo_tail_layers.py` を追加。HToolsのサンプル一覧・docs/verification-videos.md に追記。
- 2026-10-12 Claude Code: 案D＋前腕のコーンに3本共通の体の回避 Δ を追加(`tools/tail_shared_avoid.py`、`motion="*_avoid"`)。撮影を上面・正面・パースの3視点に。食い込みは付け根から8cmより先と近くを分けて数える。HToolsのサンプル一覧・docs/verification-videos.md に追記。
- 2026-10-12 Codex: QPE第3回8項目に対応。共通プレビュー/キー統一、非同期パス補完/履歴、既存tabSetsの固定・ロック拡張、転送停止/順序/永続復元、本文検索、ZIP選択抽出、任意File Locksmith診断、Windows属性/Cloud Files API状態表示と自動取得抑止。転送再開は項目単位、曖昧な確定は停止。撮影で発見したQWidget.move名衝突と設定9列の移植検証、短時間の記録書込み拒否を修正。新規コア16、独立Qt10、隔離Maya2022/2027各10、既存コア30+14/UI14+11/ナビ14/タブ8合格。単体exe再ビルド・PDFsmoke合格。54秒実UI動画とPNGを既存非公開Driveへ保存。実クラウド/PowerToys接続/ネットワーク断/IME/混在DPI/iPad再生未確認。証跡qpe-productivity-*、操作手順ORGANIZER_GUIDE.md。未コミット・未プッシュ。

- 2026-10-12 Claude Code: 案Dに前腕のConeReaderを足す検証(`motion="align_cone"`・`"cross_cone"`・`"problem_cone"`)を `tools/demo_tail_twist_cancel.py` に追加。Dの向きが前腕の軸に入ったらコーンの縁(ローカル値の側)へ押し出す。HToolsのサンプル一覧・docs/verification-videos.md に追記。
- 2026-10-12 Codex: QPE追加実装後を再調査。操作/プレビュー統一、パス補完、作業セット、転送回復、本文検索、ZIP内部閲覧、失敗原因診断、クラウド状態の8候補を公式資料とコードで照合。docs/research/qpe-third-gap-20261012.txtへローカル保存。製品変更・実機再検証なし。

- 2026-10-12 Claude Code: 尻尾の交差対策に案D(rx = ローカル値、ry = -肘の曲げ)を追加し、比較の4列目を C(半分)から D に入れ替え。DはA(平行)と同じ向きでロールの反転なし。
- 2026-10-12 Codex: 隔離Maya2027でQPE追加機能の75秒字幕付き操作動画を撮影。サムネイル/タグ/階層横断/検索/画像比較/PDF/Markdown/設定/コマンド検索を実UIで記録し、MP4抽出フレーム確認。Drive既存非公開QPEフォルダへMP4・スクショ保存。証跡qpe-advanced-video-20261012、iPad再生は未確認。

- 2026-10-12 Codex: QPE追加調査12項目を実装。下段サムネイル/Metadata/タグ/画像寸法/場所別表示/フラット表示、拡張検索、コピー結合/個別競合、ジョブ予約/失敗再試行、履歴/Redo/期限容量整理、容量集計、PDF/Markdown/画像比較、コマンド検索/キー設定、設定移植。同期の部分失敗表示を修正。既存30+追加14のバックエンド、Maya2022/2027各14の追加UI、既存整理11/ナビ14/タブ8が合格。単体exe起動と同梱PDF描画合格。1000小PNGの切替2.2秒・イベント間隔最大0.19秒。Maya用PDF依存はQPE専用ユーザーディレクトリへ配置。実IME/複数DPI/ネットワーク切断は未検証。証跡.maya-output/verification/qpe-advanced-*、使い方QPE/ORGANIZER_GUIDE.md。バージョン整理は除外、未プッシュ。

- 2026-10-12 Claude Code: 肘を曲げて腕をひねると尻尾どうしが交差する再現(`motion="cross"`)と、交差を防ぐ3案(平行・スイングのみ・半分、`motion="cross_fix"`・`"problem_fix"`)を `tools/demo_tail_twist_cancel.py` に追加し、HToolsのサンプル一覧・docs/verification-videos.md に追記。
- 2026-10-12 Claude Code: 尻尾6本のツイスト打ち消しにローカル値方式(rx = -120 - 合算した rotateX)と食い込む姿勢の上面3列比較(`demo_tail_twist_cancel.main(motion="problem", view="top")`)を追加し、HToolsのサンプル一覧に登録。
- 2026-10-12 Codex: QPE追加実装後の不足を公式資料と現行コードで再調査。表示切替/タグ可視化/結合/キュー/フラット表示等12項目と品質課題をdocs/research/qpe-followup-gap-20261012.txtへローカル保存。バージョン整理は除外。製品変更・今回の実機比較なし。

- 2026-10-12 Codex: QPEにファイル操作/永続Undo、再帰・保存検索/任意Everything、タブ復元、DnD、2ペイン、タグ/評価、一括改名、ZIP/重複/一方向同期、動画/EXR/連番プレビュー、Maya読込プリセット/シーン付随情報、単体exe配布を実装。バージョン整理は対象外。コア30件、隔離Maya2022/2027各13項目、独立Qt UI11項目、メディア3項目、配布exe起動合格。既存UXの幅180px判定は変更前にも失敗、実入力/ネットワーク/Everything実接続は未検証。使い方と制限はQPE/ORGANIZER_GUIDE.md、証跡は.maya-output/verification/qpe-organizer-*。未コミット・未プッシュ。

- 2026-10-12 Claude Code: mlrig.examples.humanoid で胸(spine_03)のプロキシが作られていなかった不具合を修正(LENGTH_CHILD で首までの円柱)。test_example_humanoid に確認を追加。尻尾6本のツイスト打ち消しだけでの食い込みを調査(.maya-output/survey_twist_cancel.py、結果はローカルのみ)。
- 2026-10-12 Claude Code: 全身骨格(Aポーズ)の左右6本の尻尾(初期 rx=-120)と腕ツイストの打ち消し(スイング・ツイスト分解)のデモ `tools/demo_tail_twist_cancel.py` を追加。HToolsのサンプル一覧・docs/verification-videos.md・demo_interactive のウィンドウ/HUD一覧に追記。
- 2026-10-12 Codex: QPE実装とExplorer/Finder/Files/Opus/PowerToys/Everythingの公式資料を比較。不足機能・優先度・Maya向け提案をdocs/research/qpe-feature-gap-20261012.mdへローカル保存。製品変更・実機検証なし。

- 2026-10-12 Codex: Maya2027 QPEの現状操作を字幕付き約43秒に収録。フォルダー移動/戻る、Import/Reference設定、左右開閉、タブ、プレビュー、絞込、保存設定。実読込/保存なし。MP4デコードとフレーム確認済み、動画とPNGを既存非公開Driveへ保存。証跡.maya-output/verification/qpe-overview-20261012。録画時に名前列が狭い表示も観察、製品修正は未実施。

- 2026-10-12 Claude Code: 尻尾の案1に球ごとの ConeReader による切り替え(体が回転面に掛からなければ元の向き)を追加。`demo_humanoid_tail_avoid.main(case="raise")`、HToolsのサンプル一覧・docs/verification-videos.md に追記。
- 2026-10-12 Codex: QPE関連18ファイルを8e27cd5としてorigin/mainへpush。テーマ/タブ/アイコン、Maya読込設定/配置復元、サイドバー描画修正と検証スクリプトを含む。構文39ファイル・差分チェック成功、既存実機検証結果を確認。無関係な変更と共有WORK_LOGの未コミット内容は保持。

- Claude Code (2026-10-12): FramePlayerの右クリックのメニューに「Copy Path」を追加(クリップボードへパスを写す。連番画像は表示中のコマの画像、比較中は1st・2ndを選ぶ)。動画・連番・比較の2本目で、写った文字をクリップボードから読み戻して確認。ドキュメント(使い方・画像・英訳2文は手で追加)・README・配布用exeとセットアップを更新。未コミット。

- 2026-10-12 Codex: QPE左右サイドバー開閉時の中間描画を抑止し、配置確定後に必要な横スクロールだけ適用。階層移動用scrollToの二重実行/アニメーションを開閉経路から除去。Qt5/6・Maya2022/2027で20回開閉・末端可視性・Paintイベント時の列位置が一定・手動スクロール維持を検証成功。Qt6階層14件も成功。証跡.maya-output/verification/qpe-smooth-paint-*。未コミット。

- 2026-10-12 Codex: QPE左サイドバー表示時も末端子カラムを可視化。右表示/非表示の両条件、左右各20回の幅維持、後続の手動スクロール維持をQt5/6単体・専用Maya2022/2027で検証成功。証跡.maya-output/verification/qpe-left-sidebar-*。未コミット。

- 2026-10-12 Codex: QPE左右サイドバー開閉を共通化し反対側の幅を維持、ハンドル幅を除いた中央領域だけ再配分。右表示時のみ末端の子カラムを可視化。Qt5/6単体・専用Maya2022/2027で各20回の左右開閉、末端可視化、以後の手動スクロール維持を確認。Qt6既存階層14件・インスペクター10件も成功。証跡.maya-output/verification/qpe-sidebars-*。README/回帰テストtools/qpe_ui_sidebars.py追加。未コミット。
- Claude Code (2026-10-12): demo_humanoid_tail_avoid.py に view="top"（既定、真上からの平行投影）を追加し、Aポーズのケースを撮り直し（541フレーム、ok、避けない尻尾103フレーム食い込み・案1は0）。尻尾の線をalwaysDrawOnTop、プロキシの透明度0.72、上面ではグリッドなし、並びを上面用に。動画は .maya-output/verification/20261012-121606-dfd134eb とDrive Maya検証動画/Humanoid。未コミット。

- Claude Code (2026-10-12): mlrig.examples.humanoid.build に pose="A"（腕を肩から45度下ろしたAポーズを回転0の基準に）を追加し、テストを1件追加（6件OK）・docsを更新。demo_humanoid_tail_avoid.py をケース化し、既定の case="apose" はAポーズでupperarm_lだけを動かし（rx±60・ry±50・rz±25）、肘はIK想定の1軸（lowerarm_lのrx・rzをロック、伸ばしたまま）。録画（541フレーム、ok）で避けない尻尾は103フレーム最大12.8cm食い込み、案1は食い込み0・最大変化1.8度。前回の動きは case="tpose_twist" として残した。HToolsのtailAvoidanceSamplesを2件に分けた。docs/verification-videos.md に追記。動画は .maya-output/verification/20261012-121028-a59146cf とDrive Maya検証動画/Humanoid。未コミット。


- 2026-10-12 Codex: QPEのworkspaceControlをretain/uiScriptで保持・再構築。qpeDockで版別の浮動位置/サイズ/開閉状態を保存し、quitApplication後の破棄で上書きしない。ドック/タブ配置はMaya標準ワークスペースで復元。専用Maya2022/2027各4回の再起動で位置・サイズ、閉じて再表示、右ドック復元、閉じた状態維持を確認。証跡.maya-output/verification/qpe-dock-2022、qpe-dock-2027-final。複雑な入れ子/複数画面は未検証。テスト再実行: python tools/qpe_dock_restore_test.py --version 2027。未コミット。
- Claude Code (2026-10-12): HTools rigging/tailAvoidanceSamples のウィンドウを高さ720pxのスクロール表示にした（scrollLayout、前回の大きさを使わない）。折り返す説明文をMayaが1行分の高さで数えて最下部のChecksが見えなかったため、説明文の高さを36pxに固定。Maya 2027で最下部までスクロールしてChecksの2項目が見えることを確認。未コミット。

- Claude Code (2026-10-12): tools/demo_humanoid_tail_avoid.py を追加。mlrig.examples.humanoid の左肘から斜め後ろ下（前腕空間rx=−135）へ45cmの尻尾を出し、骨盤・spine・太ももの球で当たり判定、腕を下ろして振り・肘・前腕ひねり・背骨を重ねる動きで、案1の実行時版（胴の中心へaimConstraint、狙う軸は胴の平均方向156度、左右別ドリブンキー）を録画（541フレーム、ok）。避けない尻尾は129フレーム最大15.5cm食い込み、案1は食い込み0・最大変化5.7度。+Y固定の狙いではTポーズで±180度の境目に来るため平均方向に変更、尻尾の元の向きも同じ周に合わせた。斜め後ろから撮るので並びを左右反転して配置。HToolsのtailAvoidanceSamplesに追加。docs/verification-videos.md に追記。動画は .maya-output/verification/20261012-115433-da7319da とDrive Maya検証動画/Humanoid。未コミット。


- 2026-10-12 Codex: QPEカラムの固定文字幅下限を廃止し内容に応じ80pxまで縮小。右サイドバーにImport/Reference設定（namespace・衝突・グループ・読込等）を追加しボタン/右クリック共通適用。親namespace欠落のMaya挙動を補正。Qt5/6階層テスト各14項目、専用Maya2022/2027実読込テスト各7項目合格。Maya2027画像/操作動画を非公開Driveへ保存。証跡は.maya-output/verification/qpe-read-*。mayapy standaloneは起動時無出力終了のためGUIへ切替。形式固有設定の埋込・標準設定同期は未対応、READMEに記載。未コミット。
- Claude Code (2026-10-12): mlrig.examples.humanoid.build を追加（UEマネキン/MetaHuman風の名前の全身骨格53関節（指なし23）、身長約170cmのTポーズ、子の方向をX、右は左のmirrorBehavior鏡像、骨ごとの簡易プロキシメッシュを関節の子にリファレンス表示）。mirrorJointの名前置換が"_l"をすべて置き換える問題を、一時名で作って最後に付け直すことで回避。単体テスト test_example_humanoid.py（5件OK、setupsスイート登録）、mlrig/docs/humanoid_example.rst、HTools rigging/buildHumanoidSkeleton.py を追加。Maya 2027 GUIで2体作成・ポーズ付けを撮影しDrive Maya検証動画/Humanoidへ保存。未コミット。


- 2026-10-12 Codex: QPE上段カラムを左フォルダーアイコン・名前・右矢印に変更。列幅計算も調整。Qt5/Qt6の階層操作テスト各14件合格、Maya2027実機表示・操作録画を確認。証跡: .maya-output/verification/qpe-left-folder-maya2027。PNG/MP4を既存の非公開Drive調査フォルダーへ保存。
- Claude Code (2026-10-12): tools/demo_runtime_avoid.py を追加。尻尾を前腕に固定（rx0=90）したまま、腕と前腕のひねりで体が尻尾を越える動きで、案1の実行時版（お腹へaimConstraintしたグループのrotateX=θ、rel=rx0−(θ+180)、clamp(rel,−L−,L+)、L±は肘とお腹の距離から左右別のドリブンキー）を録画検証（541フレーム、ok）。何もしないと185フレーム食い込む動きで、案1は食い込み0・最大変化4.2度（今の仕組みは0・22.0度）。左右同じLでは21フレーム最大0.61cm食い込んだため左右別にした。全体ロジックの図をDriveに保存。HToolsのtailAvoidanceSamplesに追加。docs/verification-videos.md に追記。動画は .maya-output/verification/20261012-112431-f4008765 とDrive RootDirectionLimit。未コミット。


- 2026-10-12 Codex: 専用Maya 2027のqpeHost.showで全体スクショと約25秒の字幕付き操作動画を撮影。タブ追加/切替/閉じる、サイドバー、テキストプレビュー、絞り込み、保存パネルを記録。MP4デコードと実フレームを確認し非公開Driveへ保存。既存ユーザーシーンは未操作。

- 2026-10-12 Codex: QPEタブをWindows風の角丸・左寄せ・OSフォルダーアイコンへ変更。四角い閉じるボタンを28px操作領域の線画×と控えめなホバーへ変更。カラム右端もOSフォルダーアイコンへ統一。Qt5/Qt6で実クリックを含む8項目、専用Maya 2022/2027で既存7項目合格。明暗と変更前後の比較画像を非公開Driveへ保存。
- Claude Code (2026-10-12): tools/demo_space_target.py を追加。案1（お腹へaimConstraintしたrotateXだけのグループの下のコントローラーをclamp(±L)、Lは肘とお腹の距離からドリブンキー6点）と案2（同じグループから見たターゲットの角度をclamp）を今の仕組みと4列で録画（541フレーム、ok）。案1は食い込み0・最大変化19.0度・中心付近0.3度・今の仕組みとの差平均2.8度最大11.7度。案2は真裏を越えるたびに反対側へ切り替わり最大155度、左右非対称の体で19フレーム最大0.21cm食い込み。HToolsのtailAvoidanceSamplesに追加。docs/verification-videos.md に追記。動画は .maya-output/verification/20261012-110259-18e89d3c とDrive RootDirectionLimit。未コミット。


- 2026-10-12 Codex: Windows標準とQPEのタブ比較画像（3/6/9枚）・比較動画（約51秒、1→9→1枚）を撮影。Windowsはデスクトップ領域録画、QPEは実ウィジェット連続撮影。個別撮影の編集比較で速度比較ではない旨を明記。デコード・実フレームを確認して非公開Driveへ保存。
- Claude Code (2026-10-12): tools/demo_simple_cone_rbf.py を追加。簡易版（お腹の球へaimConstraintしたグループにConeReader×2（±35度・半角65度）、2つのweightをドライバージョイントのtranslateに入れてUE RBF（半径0.2・23ポーズ、目標は接線の少し手前）、出力はPose Editor互換のドリブン）を今の仕組みと比較録画。中心を越える入力（541フレーム）で簡易版は144フレーム・最大2.39cm食い込み・最大変化75度、越えない入力（inputs="no_cross"、511フレーム）でも138フレーム・最大1.06cm食い込み（体の動きでHが32〜74度と変わるのに追従できない）。今の仕組みはどちらも食い込み0。chain._buildPoseBlenderに角度プラグの引数を追加。HToolsのtailAvoidanceSamplesに2件追加。docs/verification-videos.md に追記。動画は .maya-output/verification/20261012-103921-855a9c74・20261012-104041-0abaf75d とDrive RootDirectionLimit。未コミット。


- 2026-10-12 Codex: Windows Explorerを実機観察しQPEタブを標準240px→最小100pxの均等縮小へ変更。末尾の+、下限時の横送り、枚数/ウィンドウ幅/UI倍率追従を実装。Qt5/Qt6・専用Maya 2022/2027で各7項目合格。3/6/14枚の比較画像を非公開Driveへ保存。

- 2026-10-12 Codex: QPEの詳細欄をプレビュー→操作→種類/サイズ/場所/更新日時へ整理。Windows Shellアイコン、独立履歴のフォルダータブ、件数/選択サイズのフッターを追加。Qt5/Qt6・専用Maya 2022/2027でタブ5項目、既存階層14項目・詳細10項目を検証。比較画像は非公開Driveへ保存。

- 2026-10-12 Codex: Windows標準Explorerで同じma選択＋詳細ペインの白黒を撮影。QPE Windows Light/Darkの一覧/選択/詳細/preview色を実画像基準で調整、新規単体既定をWindows Lightへ。Maya配色維持。Qt5/6各3項目（ペイン/選択色・状態保持）、専用Maya2022/2027各2項目成功。比較PNGを非公開Driveへ保存/読戻し。OS明暗は元のDarkへ復元（Apps/Systemとも0確認）。証拠: .maya-output/verification/qpe-windows-details-*、docs/research/qpe-windows-details-colors-20261012.txt。
- Claude Code (2026-10-12): demo_joint_chain_rbf.py に回転ベースのRBFドライバー（rotate=(rel/3, 0, H×0.667)、inputMode=Rotation・Quaternion距離・半径4.7）と case="rotation"（入力・位置ベース・回転ベース）を追加。1軸twistでもrotateX=190と−170が同じ重みになることをmayapyで確認し、relを1/3に縮めて回避。2本×各1軸twistは重みがほぼ均等で不成立。録画検証（541フレーム、ok、両列とも交差0、回転ベースの中心付近0.57度・式との差2.34度、位置ベースとの差最大0.32度）。verify_pose_editor_rbf.py をcase/prefix指定に対応させ、回転ベース・位置ベースとも11項目合格。HToolsのtailAvoidanceSamplesにサンプルとChecksを追加。docs/verification-videos.md に追記。動画は .maya-output/verification/20261012-095626-eca4625f とDrive RootDirectionLimit。未コミット。


- 2026-10-12 Codex: Finder Light配色を追加（白一覧・グレー周辺/祖先選択・青選択・行縞）。新規単体設定はFinder、既存設定を保持してAa→Colorで選択。Mayaダーク分岐維持。Qt5/6各3項目成功、選択/フォーカス/スクロール維持。動画約16.5秒・PNGを確認し非公開Drive保存/読戻し。証拠: .maya-output/verification/qpe-finder-*。今回Maya再実行なし、macOS半透明や色実測の再現ではなく近似。

- 2026-10-12 Codex: QPEにWindowsテーマ追従（アプリ明暗・アクセント）とLight/Dark固定、Mayaダーク固定を実装。操作アイコン・一覧・選択・メニュー・余白をホスト内だけ着色。AaのColorで選択、OS設定変更なし。Qt5/6各3項目、専用Maya2022/2027各2項目、単体階層14項目成功。配色変更で選択/スクロール/フォーカス/ホストパレット維持を検証。白テーマMP4とPNGを非公開Drive保存・読戻し。証拠: .maya-output/verification/qpe-theme-*、qpe-windows-light-final-20261012。OS設定変更通知は読取関数差替えで検証、iPad/4K実機未検証。

- 2026-10-12 Codex: QPE Windows単体Qt6画面の9状態・110フレーム（約16.5秒）を撮影。Maya GUI外、mayapyランタイム利用。完成MP4のフレームを確認し、動画とPNGを非公開Driveへ保存・メタデータ読戻し。証跡: .maya-output/verification/qpe-windows-video-20261012/。iPad再生未確認。製品コード変更なし。
- Claude Code (2026-10-12): MetaHuman Pose Editorとの互換性確認を tools/verify_pose_editor_rbf.py として残した（.modのPYTHONPATH/PATH追加、Pose Editor APIで認識・全ポーズ名・編集→Update→出力変化・接続復帰・画面の11項目、結果JSONとInputs/Poses画像、失敗時は例外、Pose Editorを開き直す前に前のウィンドウを閉じてUtilitiesの重複表示を回避）。HToolsのtailAvoidanceSamplesに「Checks > Run check」を追加。検証用Maya 2027で直接実行・HToolsボタンともに11項目すべて合格（.maya-output/verification/20261012-091939-a0c4d121、20261012-092013-b11660f3）。docs/verification-videos.md に追記。未コミット。

- Claude Code (2026-10-12): demo_joint_chain_rbf.py のUE RBF列をMetaHuman Pose Editorで編集できる構成に変更。ポーズ名rel±NNN_HNNN、外向きで回る<列>TailOutward_GRP下の<列>TailDriven_JNTをUEPoseBlenderNode（Pose Editorと同じメッセージ接続・weights・outMatrix→_dmt）で回し、尻尾は外向き+clamp(ドリブンrx)。ポーズごとの乗算ノード約770個を削除。Pose Editorで385ポーズ・ドライバー・ドリブンが表示され、Edit→ポーズ選択→ドリブン回転→Update→編集終了でf200の出力が137.5→128.1度に変わることを確認。mixed再録画（541フレーム、ok、交差0、従来との差最大0.48度）、activation/soft_entry/cone_c/cone_rbfも再録画しすべてok（数値はほぼ不変、docsを更新）。動画は .maya-output/verification/20261012-090400-e343aa31 ほか、Drive RootDirectionLimit。未コミット。


- 2026-10-12 Codex: 見出し撤去後のQPEを専用Maya2027で撮影。9状態・107フレーム（約16秒）、終了0。完成MP4の9秒フレームで見出しなし・右端記号・サイドバーを確認。動画とPNGを既存非公開Drive調査フォルダーへ保存。証拠: .maya-output/verification/qpe-no-headers-video-20261012/。iPad実機は未確認。

- 2026-10-12 Codex: ユーザー指定でQPEのカラム上部固定見出しを撤去し、一覧の高さを回復。右端フォルダー＋矢印と列境界は維持。単体Qt6の階層テスト14項目合格・navigation.pngで表示確認。今回Maya GUIは未実施。証拠: .maya-output/verification/qpe-no-column-headers/。

- 2026-10-12 Codex: QPEカラム右端を既存予約幅内のフォルダー＋矢印へ変更し、各列に親名＋アイコンの固定見出しを追加。列幅・行テキスト幅を維持。Qt5/6階層各14、専用Maya2022/2027各18項目合格。100/150%画像と操作動画をレビューし非公開Driveへ保存。docs/research/qpe-column-headers-20261012.txt参照。
- Claude Code (2026-10-12): MetaHuman Pose Editor 1.12.2 と demo_joint_chain_rbf のUE RBFの互換性を確認（検証用Maya 2027、.modのPYTHONPATH/PATHをスクリプトで追加）。現状はソルバー・ドライバージョイント・ソルバー設定は認識されるが、ポーズ名が空のため385ポーズが一覧に出ず、ドリブンもない（独自ノードでrotateXを作るため）ので編集不可。試作として、ポーズ名を付け、外向きで回るグループ下のドリブンジョイントをPose EditorのAPI（add_driven_joints）でUEPoseBlenderNodeに登録し、ポーズ値を回転行列で入れると、385ポーズとドライバー/ドリブンが表示され、編集モード→ポーズへ移動→ドリブン回転→Update→編集終了で出力が変わる（f200で137.5→128.1度）ことを確認。行列で混ぜる版と従来の差は最大0.36度。ポーズへ移動してもドライバージョイントは接続のため動かない。試作はデモへ未反映（.maya-output/test_pose_editor_native.py）。


- 2026-10-12 Codex: QPEを上下40:60・保存名全幅・情報上寄せへ改善。左側はユーザー追記によりFavorites/Recentのみ、フォルダー/ファイルのアイコンとファイルお気に入り対応。Qt5スタイル寿命エラー修正。単体Qt5/6各10・専用Maya2022/2027各12・階層14項目合格。最後の連続クリック安定化はQt5/6再確認。最終画像・動画を非公開Driveへ保存。docs/research/qpe-ux-improvements-20261012.txt参照。
- Claude Code (2026-10-12): demo_joint_chain_rbf.py のUE RBFのドライバーを専用ジョイント <列>RbfDriver_JNT（translate=(rel/20, H/10)、joint.matrix→inputs[0]）に置き換え、列の左下にポーズ格子とともに表示。mixedを撮り直し（541フレーム、ok=True）、前回（composeMatrix版）とRBF出力の差0.0度。activation・soft_entry・cone_c・demo_cone_rbf もBuildで確認。docs/verification-videos.md に追記。動画は .maya-output/verification/20261012-074804-894cbec0 とDrive RootDirectionLimit。未コミット。


- 2026-10-11 Codex: QPE現状UXを専用Maya2027で9場面撮影。約16秒MP4と初期/保存/150%画像を非公開Driveへ保存・権限確認。上下配分、狭幅/拡大時の中央圧迫、保存名入力幅を最優先課題に整理。製品コード変更なし。docs/research/qpe-current-ux-review-20261011.txt参照。

- 2026-10-11 Codex: QPE本体・登録・アイコン・検証48ファイルを1bc166bにコミットしorigin/mainへプッシュ完了。構文・差分チェックとQt6 UI9項目合格。共有WORK_LOGと無関係なリグ変更・ローカル調査資料は送信対象外。

- 2026-10-11 Codex: QPEのType列を非同期更新後も表示・内容幅へ復元。MA/MB/MELをMayaシアン、他のアプリ形式を共通配色へ整理。FBXはユーザー確認後、FBX Reviewの参照アイコンに合わせ青緑系へ変更。Qt5ライト環境の一覧文字も明色に修正。Qt5/6単体で列表示と名前幅を確認、画像を非公開Driveへ保存。Maya内は今回未実行。

- 2026-10-11 Codex: QuickPathExplorerの未選択ダブルクリックを対象固定で実行。右全高サイドバーを初期非表示・ボタン切替にし交互背景色を復元。非同期読込後の列幅リセットを修正、名前列を可変幅に。非表示中Quick Look・テキストプレビューも改善。Qt5/6各9項目、専用Maya2022/2027各11項目、階層回帰14項目合格。画像2枚と動画を非公開Driveへ保存。docs/research/qpe-inspector-20261011.txt参照。

- 2026-10-11 Codex: QuickPathExplorerのカラムに常設1px区切り線を追加。Segoe UI通常ウェイト・共通文字サイズ・22px基準行高・入力部余白を統一。動的列には列所有のdelegateを用い階層矢印を維持。Qt5/6と専用Maya2022/2027でフォント・行高一致、区切り線ピクセル、100/150/100倍率を確認。階層14項目回帰合格。通常/150%の画像を非公開Driveへ保存。docs/research/qpe-typography-20261011.txt参照。

- Claude Code (2026-10-11): tools/demo_cone_rbf.py を追加。ConeReader×3（尻尾の入力が矢印、コーンはspine2追従、1フレーム目で体の中心(半角H+20)と左右の接線(半角80)へ向ける）の0〜1だけをUE RBF（72ポーズ、Additive半径0.1）のドライバーにし、幾何ドライバー(rel,H)のRBFとチェーンの動きで比較録画（541フレーム、ok=True=Aの非交差・重み合計）。Dは195フレーム・最大2.43cm食い込み、中心付近で120中118フレーム食い込み、最大変化70.2度（フリップ）、学習姿勢から遠く重みがほぼ0の3フレーム（補正なしのガードを追加）。左右コーン30度では中心で補正が平均され最大70度ずれた。HToolsのtailAvoidanceSamplesに追加。docs/verification-videos.md に追記。動画は .maya-output/verification/20261011-222833-aa6f0658 とDrive RootDirectionLimit。未コミット。

- 2026-10-11 Codex: QuickPathExplorerの上段・サイドバーのフォルダーアイコンを省略し、拡張子別文字／色アイコンを追加。スクロールバーを7px基準・必要時表示へ変更。空末尾列を省略し直近4列の名前幅を保持。サイズはQLocale.systemの単位・桁区切りでQt標準モデルと一致、数値ソート維持。単体Qt5/6の階層14項目ずつ、Qt6のP0自動範囲、専用Maya2022/2027の表示・サイズ比較8項目ずつ合格。スクリーンショットを既存の非公開Driveへ保存。詳細docs/research/qpe-appearance-20261011.txt。

- Claude Code (2026-10-11): mlrig.setups.ConeReader を追加（coneReader.py）。矢印（<name>_driver_GRP→_driver）とコーン（<name>_cone_GRP→_cone、coneAngleに連動して開く表示）のtransformを作り、GRPを指定ジョイントへparentConstraint。containerのweightは clamp(1-angle/coneAngle)（falloff=smoothでt²(3-2t)）、angleはなす角（度）。標準ノードのみ。単体テスト test_setup_cone_reader.py（7件OK、setupsスイートに登録）、docs/cone_reader.rst、HTools rigging/coneReaderUI.py（選択から作成）を追加。検証動画 tools/demo_cone_reader.py（456フレーム、ok=True、独立計算との差最大1e-7）。動画は .maya-output/verification/20261011-221743-4e9dc035 とDrive Maya検証動画/ConeReader。未コミット。

- Claude Code (2026-10-11): demo_joint_chain_rbf.py に case="cone_c" を追加。前半を肘からのコーン（A球=asin(R/d)、C固定角γ0、C距離補正γ0·d0/d）で求め、同じUE RBFへ渡す4列を録画検証（541フレーム、ok=True、全列で食い込み0）。距離補正コーンは球との半幅の差−0.6〜+7.7度・出力の差最大2.0度、固定角は最大21.4度大きく出力の差18.9度。一次近似γ0+k(d0-d)は下に凸のため最大19度小さくなり不採用。一般的なコーンドライバーの0〜1出力はHUDに参考表示のみ。HToolsのtailAvoidanceSamplesに追加。docs/verification-videos.md に追記。動画は .maya-output/verification/20261011-220447-a792a93a とDrive RootDirectionLimit。未コミット。

- 2026-10-11 Codex: QuickPathExplorer残P0のディレクトリ世代管理を実装。両一覧の旧成功・旧失敗・A→B→A・100回切替・終了失効を実データとログで検証。録画レビューで検出した子列非表示・残留列・祖先選択表示も修正。Windows単体Qt5/6、Maya2022/2027×floating/dockで各17ケース＋3ケースの自動部分が合格。実入力4ケースは確認待ち。最終回帰53項目合格、Mayaシーン操作10項目は列補正前に合格。P0_MANUAL_TESTS.txt、専用データ生成tools/qpe_manual_p0.py、44.3秒の動画と証跡を用意。詳細はdocs/research/finder-p0-generation-report-20261011.txt。

- Claude Code (2026-10-11): demo_joint_chain_rbf.py のUE RBF列にも球の交わり始めをなだらかに効かせる対策（soft）を入れ、soft_entry を4列（入力・直す前・直した後の接線止め・直した後のUE RBF）にした。3ケースを撮り直し（soft_entry 511・activation 511・mixed 541フレーム、すべてok）。RBFの交わり始めの最大変化 23.1度→10.4度、食い込み2フレーム・最大0.07cm。mixedではRBFの食い込み0、中心付近の最大変化0.47度。docs/verification-videos.md を更新。動画は .maya-output/verification/20261011-213546-a7e6ae57・20261011-213639-4204fd9d・20261011-213728-53bb6db3 とDrive RootDirectionLimit。未コミット。

- Claude Code (2026-10-11): demo_joint_chain_rbf.py に跳びの対策 soft（回転面の入り込み深さ q=(R+gap-|cx|)/(R+gap) から w=smoothstep(q/0.25) を求め、球を範囲へ足す前後を w で混ぜる）と case="soft_entry"（直す前と後の比較）を追加。録画検証（511フレーム、ok=True、両列とも独立計算と一致）。太ももの球が交わる場面で1フレームの最大変化が24.6度→11.5度（約3〜4フレームに分散）、代わりに26フレーム・最大0.18cmの食い込み。q/0.5では8.4度・121フレーム・0.42cm。ρを重みに使うと掛かり始めに急増して効果が小さい（15.6度）ことも確認。HToolsのtailAvoidanceSamplesに追加。docs/verification-videos.md に追記。動画は .maya-output/verification/20261011-213226-15dd29b8 とDrive RootDirectionLimit。未コミット。

- 2026-10-11 Codex: QuickPathExplorerのFinder P0を部分実装。メニュー対象／外側押下、斜め両軸、横基準列保持、プレビュー世代・終了失効、IME改名ガード。単体Qt5/6・専用Maya2022 floating/2027 dockで自動検証。最終14ケース合格、7ケースは未実施部分あり。ディレクトリ列挙の世代管理と実入力確認は未完了。詳細はGit対象外 docs/research/finder-p0-implementation-20261011.txt。


- Claude Code (2026-10-11): demo_joint_chain_rbf.py に case="activation" を追加（背骨前屈20度・腕の前振り0〜70度・太ももの球を追加し、尻尾を接線に当てて待たせる）。録画検証（511フレーム、ok=True、交差0）。3つの体の球だけなら交わり始めの範囲の変化は2.9度で実質跳ばない。方向の離れた太ももの球では広がった側の接線にいると1フレーム24.6度（RBF 23.1度）跳び、外れるときも同量、反対側では0度。HUDに BALL ENTERED/LEFT を追加し、JUMP表示を15度以上に変更。HToolsのtailAvoidanceSamplesに追加。docs/verification-videos.md に追記。動画は .maya-output/verification/20261011-211503-3cf17b98 とDrive RootDirectionLimit。未コミット。

- Claude Code (2026-10-11): tools/demo_joint_chain_rbf.py を追加。hip・spine0〜2・l_shoulder・l_upperArm・l_lowerArmのチェーンを正弦波で同時に動かし、3球（hip・spine1・spine2）の塞がれる範囲を合わせた接線止めとUE RBF（ドライバー(rel/20,H/10)、385ポーズ）を比較する録画検証（541フレーム、ok=True、両列とも交差0、接線止めは独立計算と一致）。HToolsのtailAvoidanceSamplesに追加。docs/verification-videos.md に節を追加。動画は .maya-output/verification/20261011-205517-8b89b514 とDrive RootDirectionLimit。リンク共有設定はユーザー操作待ち。未コミット。

- Claude Code (2026-10-11): HToolsに rigging/tailAvoidanceSamples.py を追加。尻尾1軸回避の4サンプル（tools/demo_joint_side_keep・cone_soft・rbf_pose・sweep_compare）を一覧からBuild（録画なし、タイムライン連動でHUD更新）/Record（従来の録画検証）できる。各デモに main(record=True) と tools/demo_interactive.py（timeChanged連動・既存HUDの退避と復元）を追加し、既存HUDを全削除していた処理を退避・復元へ変更。Maya 2027でBuild 4種・HUD復元（×で閉じた場合含む）・メニュー経由の録画（631フレーム ok）を確認。docs/verification-videos.md に節を追加。未コミット。

- Claude Code (2026-10-11): tools/demo_joint_rbf_pose.py を追加。MetaHuman同梱のUE RBFソルバー（UERBFSolverNode、Additive・ガウス・半径0.7、ドライバー=(rel/20, h/10)、245ポーズ）で尻尾1軸回避をポーズ補間し、入力・球の接線止めと3列で録画検証（631フレーム、ok=True、交差0、安全clamp作動0、式との差最大3.5度）。Interpolativeは重み0・階段状になり不採用。docs/verification-videos.md に節を追加。動画は .maya-output/verification/20261011-194505-d4ba4c2c とDrive RootDirectionLimit。リンク共有設定はユーザー操作待ち。未コミット。

- Codex 2026-10-11: QuickPathExplorerをFinder寄りに改善。右クリック対象と選択を分離・輪郭表示・空白メニュー・複数選択/Import/Reference・Return改名/Space拡大プレビュー・列ごとの縦/階層の横スクロール・名前幅モード/境界ドラッグを追加。録画レビューで祖先色と探索起点復帰時の古い子列残留を修正。単体Qt5/6・Maya2022/2027を検証、最終Maya2027の9項目と保存読込回帰10項目成功。13.3秒動画とPNG3枚をDrive保存・サイズ/権限読戻し済み。証跡: .maya-output/verification/qpe-finder-final2-20261011/self-review.json。物理トラックパッド・4K・iPad実機未確認。

- Codex 2026-10-11: Finder参考動画3本の該当場面・文字起こしとApple公式資料をQPE実装と比較。右クリック対象と選択の分離、列幅モード、スクロール/フォーカスなど15項目と比較シナリオをGit対象外docs/research/finder-interaction-review-20261011.txtへ保存。Mac実機・慣性数値は未確認。製品コード変更なし。

- Codex 2026-10-11: QuickPathExplorerのUX改善全項目を反映。近い階層の列幅優先・探索起点・件数/空状態・インライン改名・テキスト新規作成・読込/保存タブ分離・表示プリセット・クイック移動・全名tooltipを追加。3回の録画レビューで起点解除/子列非表示/余白を修正。単体Qt5/6・Maya2022/2027のUXと既存ナビ/保存読込回帰成功。最終21.2秒MP4とPNG3枚をDriveへ保存、サイズ/URL読戻し済み。証跡: .maya-output/verification/qpe-ux-final-20261011/self-review.json。4K実機・iPad実機未確認。

- Claude Code (2026-10-11): tools/demo_joint_cone_soft.py を追加。身体固定コーン（軸=身体-X、半角40度）への入り具合で rotateX をなだらかに避ける方式（h=acos(cosγ/s)、start+m*depth/(depth+m)、入った側を保持）を、入力・球の接線止め・コーン版の3列で録画検証（631フレーム、ok=True、コーン侵入0、肘が近く斜めの位置で球と25フレーム交差）。docs/verification-videos.md に節を追加。動画は .maya-output/verification/20261011-180548-722f0b83 とDrive RootDirectionLimit。リンク共有設定はユーザー操作待ち。未コミット。

- Claude Code (2026-10-11): tools/demo_joint_side_keep.py を追加。尻尾1軸回避で入った側の接線を保持する方式（連続な外向き角＋折り返さない相対角のclamp）を、入力・従来・新方式の3列で録画検証（631フレーム、ok=True、新方式は交差0・中心通過時の最大変化7.0度、従来は最大100度のフリップ）。docs/verification-videos.md に節を追加。動画は .maya-output/verification/20261011-172805-7dcbb96e とDrive RootDirectionLimit。リンク共有設定はユーザー操作待ち。未コミット。

- Codex 2026-10-11: QuickPathExplorerに右クリック/F2リネーム・空ファイル/フォルダー作成・Import/Reference・Aa表示設定を追加。MayaCodeEditor同様MQtUtil.dpiScaleで文字/寸法を拡大。Windows監視ハンドルによる改名失敗を修正し、履歴/お気に入りも更新。単体Qt5/6・Maya2022/2027で新機能と保存/読込回帰成功。200%倍率模擬確認、4K実機未検証。約49秒の動画とメニュー/設定画面PNGをDriveへ保存・サイズ読戻し確認。証跡: .maya-output/qpe-ui/context-final-maya2027、context-final2022、context-regression2027、.maya-output/verification/qpe-context-popup-20261011/review。

- Codex 2026-10-11: QuickPathExplorerのカラム幅を階層数・画面幅で210〜100pxへ自動調整。Qtの列配置・スクロール残留も修正。単体Qt5/6・Maya2022/2027の14項目成功。操作動画と画像をDriveのQuickPathExplorerへ保存、iPad実機再生は未確認。

- 2026-10-11 Codex: QuickPathExplorerの子カラム表示と履歴復元の競合・即時移動後の列更新・訪問済みフォルダー混入を修正。実クリック／キー操作13シナリオをMaya 2022/2027で確認、保存・読込回帰も合格。字幕付き操作動画約37秒とPNG2枚をDriveのMaya検証動画/QuickPathExplorerへ保存（所有者アカウント限定）。証跡: .maya-output/qpe-ui/thorough-parent2022、thorough-parent2027、final-file-operations2027、.maya-output/verification/qpe-review-20261011/review。

- Claude Code (2026-10-11): tools/demo_joint_sweep_compare.py を追加。尻尾1軸回避を方式ごとの5列（入力・従来・外側を回す・先回り・コーン押し出し）に横並びで比較し、同一入力で上面から録画。Maya2027 GUIで541フレーム、標準DG出力と独立計算が全列一致、緑・水色の体との交差0件、コーンは155フレームで貫通（+側から接近時、仕様どおり）。入力回転と肘移動の段階で最大1フレーム変化は従来98.5°（フリップ）、外側36.5°、先回り22.1°、コーン16.5°。腕傾斜で体が回転平面から外れる瞬間は外側45.7°・先回り63.5°（原理的制約、docs/verification-videos.mdに記載）。動画2本をGoogleドライブ同期フォルダ経由でMaya検証動画/RootDirectionLimitへ保存。リンク共有はブラウザ未ログインのためユーザー操作待ち。未コミット。

- 2026-10-11 Codex: QuickPathExplorer最上段にパス欄・移動／サイドバーアイコンを追加。列幅グリップを非表示化、同一ウィンドウ内のフォルダー別スクロール・列幅を復元。Qtの自動移動アニメーション競合を解消。単体Qt5/6とMaya 2022/2027で検証。証跡 .maya-output/qpe-ui/pathbar-instant2027、pathbar-maya2022。

- 2026-10-11 Codex: QuickPathExplorerをカラム主体へ整理。サイドバー切替SVG・初期非表示、上部バー／パス説明削除、操作と詳細統合。単体Qt5とMaya 2027で切替・読込・保存を確認。証跡 .maya-output/qpe-ui/compact-final2027。

- 2026-10-11 Codex: QuickPathExplorerのPython/Qt版2段UI・お気に入り・プレビュー・Maya操作・Windowメニュー・SVG/PNG/ICOを実装。単体Qt5/6と専用Maya 2022/2027で主要操作を検証。Qt5のQProxyStyle寿命問題を修正。証跡: .maya-output/qpe-ui/。
- Claude Code (2026-10-11): hrigをmlrig（Modular Layered Rig）へ改名。フォルダ・startup・.mod・HTools/rigging/mlrigLayerEditor.py・tools/test_mlrig_*・docs/mlrig-development.md・mlib/mlib_bifrostの言及まで137ファイル695か所を置換し、保存アトリビュート（mlrigOwned等）・環境変数（MLRIG_*）・C++ノード（mlrigSoftIK/mlrigMatrixFollow、型IDは不変）・プラグイン（mlrigNodes.mll、2025/2027再ビルド）もそろえ、旧hrig互換は置かない（旧シーンは非対応）。test_standardのstartupテストを2025のshibokenで動くようModuleType差し替えに修正。mayapy 2025/2027でtest_rig_packages全201件・test_mlrig_bifrost_startup 8件成功、日英Sphinx -W成功。GUI専用テスト未実行、Pages公開URLは/mlrig/、docs/research・.maya-outputは未変更、未コミット。

- Codex 2026-10-11: QuickPathExplorerの画面参考としてOneCommander/Finder/Windows Explorer/Maya File Browser/Adobe Bridge/Directory OpusをWeb画像と公式資料で調査。OneCommander標準配置が上段カラム・下段一覧案に近い。docs/research/qpe-ui-references.txtへ出典URLと設計観点をローカル保存。画像ダウンロード・実装変更・公開なし。

- Codex 2026-10-11: QuickPathExplorerのC++ Qt DLL/単体EXE・Python PySide版・共通Mayaドック接続を仮実装。Windows単体/Maya2027 GUIで各6回、100/1000/10000件・12階層・再訪問を検証成功。最終測定152743は単体起動中央値C++253ms/Python603ms、1万件2078/2146ms、Maya内2196/2212ms。専用GUIでキー/クリック・ドック・実ma Open/Import/Reference・未保存Openキャンセル保持を確認、終了0。Qt6.8.3を共有し単体はMaya同梱ランタイム使用、Mayaなし配布/旧版/NASは未検証。docs/research/quick-path-explorer-comparison-20261011.txtに比較をローカル保存。既存変更保持、コミット/公開なし。

- Codex 2026-10-11: QuickFinder等4候補の名称重複をWeb・GitHub API・PyPI/npm/NuGetで調査。QuickFinderは複数の既存利用、他3候補は同名未確認。docs/research/explorer-name-check-20261011.txtにローカル記録。登録・公開なし。

- Codex 2026-10-11: Windows/Maya共通ファイルエクスプローラの初期設計を相談。対象はファイル・フォルダーと確認。Qt/Maya公式資料と既存構成を参照し、共通UI・単体起動/Mayaドック・操作仕様と段階的試作を提案。実装・Maya実行なし。

- Claude Code (2026-10-11): Maya Code Editor から旧名 hedit の互換処理と記載を削除(ユーザー指示)。<prefs>/hedit からの設定の写し・旧ドックの削除とそのテストを外し、C++・CMake・テストのコメント、変更履歴(過去の版の記載は Maya Code Editor・mayaCodeEditor 等へ置き換え、旧名の節と互換の説明を削除)、インストールの注意、README(パッケージ・直下)、英訳(MayaCodeEditor・FramePlayer・mlib の誤訳3件)から旧名を除いた(WORK_LOG の過去の記録と docs/research のローカルメモは残す)。Codex の未コミットの mlib 改名と混ざらないよう、HEAD+自分の変更だけの worktree で全6版ビルド(警告0)・単体テスト・GUI 全スイート(2022/2024/2027)・日英 Sphinx -W(MayaCodeEditor・FramePlayer)を確認。コミット・プッシュ済み。

- Codex 2026-10-11: mlib旧名・旧互換を1157ファイルとローカル生成物で監査。配布MayaCodeEditorバイナリ6個のスペルチェック許可語に旧名残存、ソースは改名済み。管理対象テキスト・base64データに旧名なし。Maya2027で旧import不可・旧JSON拒否を確認。docs/research/mlib-removal-audit.mdへ記録。実装変更・再ビルドなし。

- Codex 2026-10-11: mlib/mlib_*へ完全改名。利用側・Mayaモジュール・検査ツール・CI・文書・保存形式mlib.json・MLIB_EXTENSION_APIを更新し、旧パッケージ/旧形式の互換なし。Maya2027全体141ファイル1258件（skip8）失敗0、HTools12シナリオ成功。Maya2022は既存SoftIKの失敗を改名前でも再現、改名/数学pickleの個別5件成功。日本語/英語Sphinx計1002ページと公開名/文書整合性検査成功。内製Python651ファイル構文検査成功。GUI・他PC未検証、コミット/公開なし。古い生成キャッシュ削除は自動承認レビューで拒否され未実施、検証記録はローカル保持。

- Codex 2026-10-11: mlib追加調査。拡張候補mlib_*のimport先行判定・旧版混在・保存済みコード等の移行注意を確認。Maya2022/2027 mayapyで既存改名テスト各3件成功。docs/research/mlib-name-review.mdへ追記、実装変更・改名・公開なし。

- Codex 2026-10-11: 4文字の改名候補34件をPyPIで一次確認し、一部をGitHub/Webで追加調査。myol/myaw/hmya/mylxを比較、完全な未使用保証はなし。Maya2027 mayapyで4候補は未検出。docs/research/four-letter-library-names.mdにローカル保存、改名なし。

- Codex 2026-10-11: mlib/mayalibの既存利用・改名範囲を調査。PyPIとMaya関連の同名利用あり。Maya2022〜2027のmayapyでは同名モジュール未検出。調査メモはdocs/research/mlib-name-review.mdへローカル保存。実装変更・改名・コミットなし。

- Claude Code (2026-10-11): hedit を Maya Code Editor へ改名(0.7.0)。フォルダー maya/inhouse/MayaCodeEditor・プラグイン/コマンド mayaCodeEditor(テスト用 mayaCodeEditorTest)・Python maya_code_editor・C++ 名前空間 mce・MCE_* マクロ/環境変数・maya/modules/MayaCodeEditor.mod・保存先 <prefs>/MayaCodeEditor(初回に <prefs>/hedit から写す)・旧 heditDockWorkspaceControl はロード時に削除。旧名の互換入口は置かない。Windowメニューのアイコンを緑の地に < > (案A)に変更。ドキュメントの配色を maya-code-editor.css に分離(エディターと同じ地・緑の強調色)、favicon 追加、公開先を .../maya-code-editor/ に(workflow・README)。変更履歴の過去の記録は旧名のまま。全6版ビルド(警告0)・単体テスト(core 19・Python 35・保存先 3・UI)合格、GUI全スイートを2022・2024・2027で合格(旧名のドック削除・設定の写しのテストを追加)、日英 Sphinx -W 合格。コミット・プッシュ済み。

- Codex 2026-10-11: editSkinJointsのMatch対応と専用テスト2件を3d4aeb2でコミットしorigin/mainへpush成功。差分チェックと専用GUI33項目の成功結果を確認。git commit --onlyで対象3ファイルに限定し、他作業のステージ済み変更・共有WORK_LOGは保持。

- Codex 2026-10-11: editSkinJointsのPreserve Childrenを標準Match・TRS/ピボット等の直接編集へ拡張。選択骨のMatch結果と未選択の子を保持し、親孫選択の中間骨も対応。SSC/rotateAxis/jointOrientを除いてローカル値を復元し、非均一スケール時の誤差とxformのRedo問題を解消。Undo/Redo・時刻変更をAPIイベントで除外し終了時に解除。Maya2027 standalone回帰と6回転順序・SSC両設定・負スケール・OPM・ピボット・cm/mmの24組成功。専用GUI33項目（標準Matchコマンド5種×選択4構成と連続2Undo/2Redo、時刻変更、既存安全設計等）成功。MatchPivotsはjointで標準動作が無変更のケースを含む。最終結果は.maya-output/preserve-children-gui/match-1791677554/result.json。実メニューのマウス操作・他Maya版は未検証。未コミット・未push。

- Claude Code (2026-10-11): advancedOrientJointUIを網羅検証し不具合を修正。仕様からの独立した期待値で全設定(Primary48×Secondary32×Third17)×10ジョイント=26万件をmayapy 2022/2027で照合(修正前は向きの誤り34,758件・縮退時4,990件→0件)。修正: 親がジョイント以外(グループ)だと親の回転を無視、rotateAxisがあると解き方の順序が逆、親の非一様スケール(segmentScaleCompensate)未考慮、角度単位ラジアンで度をそのまま書込、子孫ジョイントの姿勢保持(xform -m)がrotateAxis/jointOrient持ちで崩れる→translate/rotateを行列から解いて復元、複数選択で子を先に処理すると崩れる→親から処理、Thirdの参照が残り軸と直交時に誤差で反転が揺れる→反転しない、開発用ログを既定OFF。Apply処理(スキン形状・子の姿勢・rotate=0・Undo1回・複数選択・不正指定・単位rad/mm・ログON)を各3,000件超で確認(修正前は678/3000失敗)、GUI 2022/2027で実画面の値を切り替えて194件全件成功。制限: 打ち消されない非一様スケールの親空間では軸が歪み厳密には合わせられない。未コミット。

- Codex 2026-10-11: editSkinJointsの安全設計・不要ボタン削除と専用テスト2件を5fdeb3fでコミットしorigin/mainへpush成功。構文3件・staged差分チェック成功、既存GUI12項目成功結果を確認。他作業のadvancedOrientJointUI変更と共有WORK_LOGはローカル保持。

- Codex 2026-10-11: editSkinJointsのPause Edit / Discard SessionボタンをUIから削除。終了・保存時の自動一時停止と復旧処理は保持。構文解析・git diff --check成功。Maya GUIでの再表示は未検証。

- Codex 2026-10-11: editSkinJointsの安全設計を更新。mayaモジュール上の所有者でimport/reload/runpyをまたぐ単一UI、終了時に監視/API callback解放・標準ツール設定復元。専用JSONへPID別の元設定を記録し次回起動時に終了済みプロセス分だけ復旧。close/saveで自動確定せずenvelope復元・paused記録、Beginで再開、Discardで骨を保持して記録終了。保存中Undo無効にも対応、復旧不可時は保存拒否。Maya2027 standalone回帰とUUID改名復旧/保存拒否テスト、専用GUI12項目（子保持・Undo/Redo・監視解除・多重起動・疑似クラッシュ復旧・保存/再読込/再開）が成功。実クラッシュ/4K表示は未検証。他作業のadvancedOrientJointUI変更は保持、未コミット・未push。

- Codex 2026-10-11: ユーザー指示による残存変更の登録準備。RootDirectionLimit・検証デモ/録画スクリプト・公開説明用静止画3枚・関連文書・作業ログを確認。Maya2027 standaloneの方向制限10テスト、動画ツール4テスト、mlib公開検査、差分チェック成功。動画/画像連番は含めず、GUI録画は今回再実行していない。

- Claude Code (2026-10-11): advancedOrientJointUIにThird Settings(Use Third Settings既定OFF。ON時は外積で決まる残りの軸がThird Direction/Source/Reference Axisの方向と逆ならSecondaryを反転、Primaryは不変)と、Axis SourceのNext/Children First/Second(Primary/Secondary/Third共通、2本目が無いジョイントは警告してスキップ)を追加。Third OFF・First選択時はHEAD版のNext/Childrenと全ケース一致。mayapy 2022/2027で48項目、GUI 2022/2027でUIの既定・有効切替・Third Axis表示・Apply・Undo・スキップを確認。未コミット。

- Codex 2026-10-11: ユーザー指示でeditSkinJoints.pyと専用テスト2件を14b39efとしてコミットしorigin/mainへpush成功。staged差分チェック成功、既存のMaya2027 standalone/専用GUI検証結果を確認。他作業の変更と共有WORK_LOGはローカル保持。

- Codex 2026-10-11: editSkinJoints.py内のUI所有scriptJobで選択jointのjointOrient直接編集時に子のワールド行列を保持。compressUndoと同値書込回避により単一Undo/Redo対応。選択・時刻・Undo/Redoで監視更新、UI終了で解放。専用Maya2027 GUIの自動アトリビュート編集で子/孫保持、単一Undo、Redo、連続編集、無効化、選択変更、再表示、終了後解放の8項目成功。既存standalone回帰成功。Channel Boxの実マウス入力とロック/接続付きの子は未検証（後者は補正前に拒否）。プラグイン追加なし、ユーザーGUI不変更。

- Codex 2026-10-11: Preserve ChildrenボタンのON/OFF/Mixed接尾表示を削除し、Begin/Endの固定ラベルと赤/グレー表示を維持。構文確認成功。

- Codex 2026-10-11: Preserve ChildrenをBegin/Endの2ボタンへ変更。開始は3標準ツールをON、終了はOFFへ揃え、有効中の開始ボタン赤表示を維持。構文確認成功、GUI操作は未検証。

- Codex 2026-10-11: editSkinJointsのExtraにPreserve Childrenトグル追加。標準Move/Rotate/ScaleのpreserveChildPositionを一括切替し、ON赤/OFFグレー・混在表示・ToolChanged時の再照会に対応。チャンネル直接編集には適用されない旨をUIに明記。構文確認成功、Maya GUI操作は未検証。

- Codex 2026-10-11: editSkinJointsにExtra/Freeze Selected Joint Rotationsを追加。選択jointのrotateをjointOrientへ合成し位置/scaleと未選択子を保持。対象インフルエンスのbindPreMatrixとbindPoseの該当メンバーを更新、1回Undo対応。Maya2027 standaloneで6回転順序・rotateAxis併用・子ワールド/チャンネル保持・bind行列/poseのUndo/Redoと既存回帰を検証成功。GUI表示は未検証。

- Claude Code (2026-10-11): HToolsのmlib直接importを全廃(21ファイル、各ツールで完結。convertAimAxes・controllerShapeManagerのhrig経由とhrigLayerEditorは維持)。OBB計算・循環検出・ジョイント削除とウェイト移送・preservedSkinShape・頂点隣接などをcmds/OpenMayaで各ファイルへ移植。既存バグ修正: createCurveFromSelectedClustersの単位ズレ、duplicateAnimCurveの切り離し、duplicateInputsのprint/引数、simpleCollisionのmm時の寸法とピボット、removeSelectedJointsのウェイトが加算されず他インフルエンスが増える不具合(5万頂点で155秒→1.75秒)、import時に実行される6ファイル(advancedOrientJointUI・transferUvchannelToMap含む)に__main__ガード、複数操作をUndo1回に。mlibをブロックしたmayapy 2022/2027でHEAD版(mlibあり)と同じ入力の結果を比較し一致(意図した修正点を除く)。全モジュールのimport・Python3.7コンパイル、GUI Maya 2022/2027で主要6ツールのrun_name="__main__"実行とウィンドウ表示を確認。未追跡のrigging/editSkinJoints.pyは別作業のため未変更。未コミット。

- Codex 2026-10-11: 環境共有についてREADME・起動バッチ・submodule構成と公式のGitクライアント/権限資料を確認。SourceTreeでの取得更新と、Git不要の版別ZIP・起動時更新方式を比較提案。実装変更・配布実行なし。

- Codex 2026-10-11: editSkinJointsの待機時Begin/Finishを同じ明示グレーに統一し黒表示を回避。formLayoutでスクロール領域を四辺追従、resizeToFitChildren=False、サイズ設定削除を停止しMayaのwindowPrefを保持。構文確認成功、GUI実操作は未検証。

- Codex 2026-10-11: editSkinJointsの初期サイズ拡張・当該UIの旧windowPref解除・スクロール領域・説明文の折り返し・左右余白を追加。Maya標準cmds UIにDPIスケーリングを委ね独自倍率は適用しない。構文確認成功。Maya GUI/4K高DPI実機での表示は未検証。

- Codex 2026-10-11: editSkinJointsのBegin Editボタンを編集中は赤、完了後は作成時の標準色へ復元。既存refresh経由でUndo/Redo・再表示にも追従。構文確認成功、Maya GUIの色表示は未検証。

- Codex 2026-10-11: editSkinJointsの共有bindPoseエラーを解消し、共有するskinClusterを自動収集。複数選択・複数bindPoseに対応し、対象一覧を追加。UI・独自警告/例外・Undo表示を英語化。Maya2027 standaloneで既存3方式に加え、別階層の共有先・複数選択・無関係対象の除外・ロックされた共有先の事前拒否・Undo/Redoを検証成功。GUI実操作は未検証。

- Codex 2026-10-11: HTools/rigging/editSkinJoints.pyを追加。選択階層のskinClusterを一時停止し、全インフルエンスの逆行列・bindPose更新後にenvelope復元。開始/完了のUndo・Redoとシーン内セッション保持に対応。tools/test_edit_skin_joints.pyをMaya2027 standaloneで実行し、Linear/DQ/Blended・複数メッシュ・形状/ウェイト保持・編集後変形・Undo/Redo・不正フレーム/ゼロスケール拒否・envelope復元が成功。GUI操作は未検証。既存HTools改修対象は変更せず、コミット・pushなし。

- Codex 2026-10-10: ユーザー指示で両方向最近接接線の上面ジョイント版(20261010-184255-9c129c72)を専用Maya GUIで再読込。twistOnlyLimitあり/片側固定・連続制限ノードなし、3姿勢の実出力を元の記録と照合しフレーム1へ戻した。片側版と連続制限版のコード/動画/シーン保持。コミット・pushなし。

- Codex 2026-10-10: ユーザー指示で片側固定・フリップ再現シーン(20261010-185730-c9eb532f)へ検証状態を復元。Maya終了済みのため隔離GUI PID42256を起動して保存maを開き、continuousElbowOutputなし/固定接線ノードあり/最初の30度超フリップ再現を確認しフレーム1へ戻した。連続制限版のコード・動画・シーンは比較用に保持。既存変更を破棄せず、コミット・pushなし。

- Codex 2026-10-10: largeMotion=Trueの説明入力を追加。初期姿勢・安全な距離8cm/位置角±25度/腕傾斜30度・尻尾入力±100度往復・距離3.2cmで-60度上限貫通保持・初期復帰を32秒/769フレームでMaya2027実録画。灰色初期姿勢を保持、橙旧方式は比較段階のみ表示。共通録画にpresentation_stage大文字字幕追加。安全/往復段階の補正交差0、大きな跳びなし(緑max5.921度/フレーム、橙58.58度)、上限貫通113フレーム、最終初期姿勢一致を検証。3段階MP4画像/全デコード確認、録画ツール4テスト成功、Drive 1gKWRVBMOS7NDF26dsrsD5B6QkSVfCmD3をanyone/reader共有。既存動画保持、未コミット・未プッシュ。

- Claude Code (2026-10-10): pipパッケージをグループ化。maya/requirements/<名前>.txt(slack_sdk・numpy・scipy・robust_laplacian・potpourri3d・libigl・py_dem_bones・ipctk・simkit・fast_cody・geometric_kernels)→site-packages/<年>/<名前>(Git対象外)、PYTHONPATHはpip_<名前>.modだけ(modules=有効、modules_disabled=無効、初期有効はslack_sdkのみ)。起動バッチは有効グループの未取得・変更時のみ自動取得、失敗は<名前>.failedで再試行せずWARN。取得処理はグループ単位・同梱パッケージ除外・旧配置の削除・.mod自動作成・同一ファイルのハードリンク化(11.4GB→約6GB)・空.whl削除。全グループを2022〜2027へ取得し、各版mayapyでimport(一部は計算)を確認。robust_laplacianはscipy未宣言のため追加、py_dem_bones(3.7のDLL不良)・fast_cody(3.10構文)はpython_versionで限定。起動チェック0.1秒、失敗記録グループのWARN、GUI Maya 2026で有効グループの自動取得・.modによる2グループのみのパス追加・無効グループ非表示を確認。macOS未実行。未コミット。

- Codex 2026-10-10: ユーザーの「よくなる方で」を受けcontinuousElbowSide/maximumAngle追加。危険/安全切替を廃し、接線の無符号角から負側の連続可動域[-60,bound]へclamp。Maya2027実録画973フレームで前4フリップ条件の大きな跳びなし(最大step1.279度)、末尾で-60度保持/意図した貫通57フレームを確認。保存ma再読込・逆順DG/Serial/Parallel全一致、ry/rz0・片側範囲保持。緑新方式/橙旧固定方式のMP4確認・全デコード成功、Drive 1CxApBRLKBQa_wPevt8gc_iOfU5rLCC6eをanyone/reader共有。安全入力も制限/断面なしも可動域維持など代替方針の制限を文書化。既存モード保持、未コミット・未プッシュ。

- Claude Code (2026-10-10): 起動バッチ(maya_core.bat/.command)でPYTHONPATHを組む前に、requirements.txtと取得時の写しが異なる(未取得含む)ときだけそのバージョンのinstall_packagesを呼んで自動取得するよう変更(従来の[WARN]表示を置換)。失敗時は[WARN]で前回の取得結果のまま起動。mayapyへ差し替えた一時コピーで、変更なし(取得なし・0.8秒)、未取得(自動取得し同じ起動でimport可)、requirements変更(再取得)、取得失敗(WARNで継続・旧パッケージでimport可)を確認。site-packages/2026を消してMaya 2026 GUIを起動バッチで起動し、自動取得とGUI上のslack_sdk読み込みを確認。macOSの.commandは未実行。README・CLAUDE.md更新。未コミット。

- Codex 2026-10-10: reproduceFlip=True追加。固定側の逆安全境界をA入力44/40度・B距離4.3/4.7cm・C肘位置角±2度・D腕傾斜0/25度で往復し、中心方向往復を対照にした上面動画をMaya2027で実録画。865フレームの式/1軸/非交差検証成功、補正交差0、30度超の跳び11回、4ケース全部再現、対照は跳び0。HUDにFLIP角と境界を表示、完成MP4全デコード確認。Drive 1JAN7RlB30f1M84nf0EeOa77p9JNlb9kPをanyone/reader共有。再現用ma/最新ポインタ分離、既存サンプル保持。未コミット・未プッシュ。

- Codex 2026-10-10: fixedElbowSide=True追加。初期肘ガイドの接線方向内積でsideを固定し、危険範囲だけoutward+side*limitへ補正。緑固定/橙最近接/黄色肘ガイドの上面比較をMaya2027で505フレーム検証、補正交差0。最大フレーム回転差は固定3.33度/最近接84.65度、保存ma再読込後逆順DG/Serial/Parallel全出力一致。完成MP4デコード確認、Drive 1sJTZS0lHUmEfHX8VKuqHjMJDWnRL6--nをanyone/reader共有。逆側安全境界の不連続・初期側固定の制限を文書化。既存モード保持、未コミット・未プッシュ。

- Codex 2026-10-10: ジョイントX軸回避にmain(topView=True)追加。同一DG・入力505フレームを上面固定正投影でMaya2027実録画、全判定成功・補正中心線の球交差0。既定斜め版・既存動画保持。MP4/HUD表示確認、Drive 1DibRGyggJB-X2uSh39pYTmk7WRypqbUXをanyone/reader共有。最新上面ポインタを分離。構文/diff確認、未コミット・未プッシュ。

- Codex 2026-10-10: ユーザー指定の腕ローカルX軸1軸に対応するdemo_joint_twist_tangent.py追加。腕/尻尾/末端をjoint化し、補正はtailCorrected_JNT.rxだけ、ry/rzロック・移動0保持。腕姿勢を含むローカルYZ平面と球の断面から標準DGで接線停止、断面なしは入力通過。Maya2027実録画505フレーム成功(未補正364交差/補正0、最大角誤差2.24e-5度)。保存ma再読込DG/Serial/Parallel全フレーム一致。HUD・斜め固定カメラ・MP4確認、Drive 1WRCWDaarsJEai1cyaZb3G8UDW8FgkVLVをanyone/reader共有。球近似・無スケール・腕軸に垂直な直線尾・根元球外など制約を文書化。既存サンプル保持、未コミット・未プッシュ。

- Claude Code (2026-10-10): pipパッケージ取得を追加。maya/requirements.txt(初期はslack_sdk)、maya/install_packages.bat/.command、tools/install_maya_packages.py(各mayapyで--target取得、Maya同梱パッケージはpip list --pathの版に固定して取得先から除外、新フォルダーへ取得後に入れ替え)。maya_core.bat/.commandはsite-packages/<年>があればPYTHONPATHへ追加し、未取得・requirements変更時に[WARN]。PYTHONNOUSERSITEは設定せずユーザー領域と共存。Maya2022〜2027で取得成功、numpy指定時に2025〜2027は同梱版へ固定して除外・2022は取得、同梱と矛盾する指定は失敗して前の取得結果を保持、起動バッチ(mayapyへ差し替えた一時コピー)でslack_sdkの読み込み・ユーザー領域の共存・WARN表示を確認。macOSの.commandは未実行。追加で起動バッチからMaya 2022/2027 GUIを起動し(一時userSetup.melで確認スクリプトを遅延実行して自動終了)、site-packages/<年>がsys.pathに入りslack_sdkを読み込めること、2022でユーザー領域が共存すること、2027のnumpyがMaya同梱版のままであること、HToolsメニューが作られることを確認。

- Codex 2026-10-10: 固定サンプルを変更せずdemo_top_view_moving_tangent.py追加。標準DGで距離・外向き・接線角・相対角wrapを更新。Maya2027実録画541フレーム成功、未補正249交差/補正0。保存ma再読込後のDG/Serial/Parallel全541フレーム出力一致。HUD・完成MP4確認、Drive 1Cf19faH7HnCcoUKUJMHU-2SDfx9Vl4dMをanyone/reader共有。angleBetween既定Y成分による初回不一致を修正。根元が円外・2D・±180側切替の制限を文書化。未コミット・未プッシュ。

- Codex 2026-10-10: 共通ワークフロー指示4ファイル・詳細手順・録画共通ツール/4件テストを7af777aでmainへpush。独立indexを使用し、他ツールのstage済みsubmodule/CLAUDE一覧更新と既存リグ変更を保持。リモートmainの一致確認。

- Codex 2026-10-10: AGENTS.md・CLAUDE.md・Copilot全体/VS Code用指示の4ファイルへ同一のリグ検証共通ワークフローを追記。docs/verification-videos.mdへ標準工程・HUD表示要件を記載。参照先・差分を確認しdiff --check成功。文書のみ、Maya再実行なし。既存変更保持、未コミット・未プッシュ。

- Claude Code (2026-10-10): 3DCG数学論文調査の公開実装31個をmaya/external/へshallow submoduleで追加(index登録のみ・未コミット)。Mayaで直接読めるものは無く.modは作成せず。AI4Animation(約5.5GB・非商用)はユーザー判断で除外。CLAUDE.mdの外部ツール一覧へ追記。

- Codex 2026-10-10: 接線停止デモにMaya HUDで基準方向・半径/距離・asin式・制限角・入力/実DG出力を表示。Maya2027 GUI実録画469フレーム全検証成功、完成MP4の表示を確認。Drive 1T1IbrsLOEWaXhCZJpGPR4ugfK7Be0dGBへ保存しanyone/reader確認。未コミット・未プッシュ。

- Codex (2026-10-10): 意図修正に合わせ外向きconeを使わない接線停止の上面デモを新規作成。円r3/根元r4.5固定、表示余裕0.03cm、±137.675度で標準clamp＋unitConversion2個が停止。左右の接触前/停止保持/復帰と腕の平面移動を469frame検証。Maya2027全成功、非接触方向誤差最大6.3e-6度、赤201frame交差/緑0frame。動画デコード成功、top-tangent-stop.ma保存。Drive fileId=1XPOKipzavZN8xxb-div6eUVQE6N9V1mUに保存しanyone/reader/discovery=false確認、結果HTML登録。固定半径/固定距離の検証用で一般リグAPIは未実装、未コミット・未プッシュ。

- Codex (2026-10-10): 既存3Dデモを使用せず新規シーンからXZ上面のみの検証を作成。円r3/肘r4.5/曲げた青い腕/12cm赤緑線/固定正投影、回転はYのみ。既存RootDirectionLimitを新規構築。Maya2027で325frame数値成功（平面性/根元位置/cone/円交差）、赤199frame交差/緑0frame。900x900/13.54秒H.264とtop-view.ma保存、動画デコード成功。Drive fileId=1bhqTQcgGCUNEJHPKvtBLjJZDcWXhmANW、anyone/reader/discovery=false確認、結果HTML登録。未コミット・未プッシュ。

- Claude Code (2026-10-10): 3DCG表現の数学的に新しい論文(2020〜2026中心)を形状処理・PDE・変形15、曲線曲面・陰関数・新表現12、シミュレーション・動き14の項目に整理しdocs/research/cg-math-papers-2026-10-10.md(ローカル)へ保存。hrigでの使い方区分・公開実装・ライセンス付き。コード変更なし。

- Codex (2026-10-10): 尻尾方向表示を6→18cmへ延長し、肘90度/腕捻り165度で体を横断する未補正赤と補正緑を比較する停止付き14秒動画を作成。カメラ幅50、表示長/カメラ/姿勢を復元。337frame数値成功、赤の中心線155frame交差/緑0frame交差（検証時のみのoracle）。凡例/交差状態をFFmpegで映像へ焼込、デコード/登録4テスト/構文確認成功。Drive fileId=1J9KCCbKOMQ-bnMRvPNS3dtPd4Ox4fRwT、anyone/reader/discovery=false確認、結果HTMLへ登録。未コミット・未プッシュ。

- Codex (2026-10-10): 肘90度の腕移動動画を生成。録画ツールにelbowBendを追加して角度を復元、HUDを赤=未補正/緑=補正後/青=腕へ明確化。Maya2027で337frame数値成功、H.264デコード成功、14.04秒/272173bytes。Drive fileId=16ZFFXGa0Wnk38BQ-gJUI01vONzWc0feKに保存、anyone/reader/allowFileDiscovery=false確認、結果HTMLへ登録。未コミット・未プッシュ。

- Codex (2026-10-10): 腕移動動画を追加。record_root_direction_limit.main(armMotion=True)で胴体固定の腕持上げ/前後スイング/150度捻りを連続記録。Maya2027で337frame全成功、最大cone角44.9943度、14.04秒/272258bytes H.264。デコード成功。Drive fileId=1GF472iWDDFJ696xu2IaNv9KKvHLl0w1pに保存しanyone/reader/allowFileDiscovery=falseを読み戻し、結果HTMLへ登録。Drive再生用処理待ち、未コミット・未プッシュ。

- Codex (2026-10-10): 検証動画の記録・結果HTML・Driveメタデータ登録を実装。Maya2027の193frameで数値成功、8.04秒/171073bytesのMP4を専用Driveフォルダへ保存。動画デコード・登録4テスト・Sphinxビルド成功。共有UIでリンクを知っている全員/閲覧者へ設定し、Driveメタデータでanyone/reader/allowFileDiscovery=falseを確認。fileId=1Vy7v8o6YXd8BxaFHDiOti5BIVnNkrc41。録画とクラウド送信は別処理、iPad実機再生未確認、未コミット・未プッシュ。

- Codex (2026-10-10): Maya検証動画の記録とiPad閲覧を調査。playblast連番→MP4＋結果HTML、非公開Tailscale Serve／公開サンプルは既存Sphinx Pagesの構成を提案。Claude Remote Control・Maya・Tailscale・Pagesの公式資料確認。調査メモはGit対象外docs/researchへ保存。録画実装・アップロード・iPad再生は未実施。

- Codex (2026-10-10): hrig.setups.RootDirectionLimitを標準DGで実装。胴体guideの連続重み/局所径方向/cone制約で根元姿勢を生成、位置/一様scale維持、180度付近の軸反射・退化fallback・messageからの再取得・単一Undo対応。RBF/実行時Python/衝突ノードなし。Maya2025/2027各10テスト成功、2027セットアップ統合57成功、DG/Serial/Parallel・単位・保存/Undo確認。2027 GUIの4姿勢で根元位置誤差0cm、末端ローカル維持、腕捻り/前屈/側屈の未補正中心線は腹部交差・補正後交差なし（交差oracleは検証時のみ）。実viewport3画像と使用法/制限をSphinxへ追加し-E -a -Wビルド成功。専用.ma/4画像/実Mayaウィンドウ画像/数値証跡は.maya-outputへ保存。実キャラクター/全頂点の非貫通/性能/他版GUIは未検証。未コミット・未プッシュ、他ツールの差分保持。

- Claude Code (2026-10-10): RBF補間に関連する数学的手法の論文32件(散布データ補間16・回転多様体上の補間/重み付け16)を調査しdocs/research/rbf-interpolation-math-2026-10-10.md(ローカル)へ保存。Maya2027でmultiplyDivide・plusMinusAverage・remapValue・clampの入出力がfloat(単精度)、multiply・sum・power・blendWeighted出力がdoubleであることを確認し、poseRbfの悪条件時の桁落ちリスクとして記載。コード変更なし。

- Codex (2026-10-10): 尻尾根元の回転のみ・RBF/登録ポーズなしの案へ更新。胸/腹/骨盤の局所軸と肘への径方向から動的外向きベクトルを計算し、根元方向をcone内へ直接制限する構成を検討。ConePSD重みとの役割差、guide連続補間/side参照/退化時fallback/非貫通の限界を一次資料とsourceで確認。式のみJS doubleの20002方向でfinite/cone条件確認、専用researchのanalytic-*へローカル保存。製品/Maya設定/index未変更、Maya実行・速度計測なし。

- Codex (2026-10-09): 肘から生える尻尾の根元をコリジョンなしで体から逃がす方法を調査。hrigと既存mGear/cmt/EccentricConePSD等のsource・一次資料を確認し、付け根固定、捻り継承調整、胴体相対の姿勢補正、根元の最終方向制限を提案。専用docs/research/elbow-tail-avoidance-2026-10-09/へローカル保存。製品/submodule/Maya設定/indexは未変更、Maya実行・性能計測なし。

- Claude Code (2026-10-09): 研究論文調査の公開実装19個(GitHub18・GitLab1)をmaya/external/へshallow submoduleで追加(index登録のみ・未コミット)。Mayaで読めるMetaHuman-DNA-Calibrationのみmaya/modules_disabled/へ.modを作成し、一時MAYA_MODULE_PATHでMaya2022〜2024のmayapyでembeddedRL4・MayaUERBFPluginのロードとdna/dnacalib/dna_viewerのimportを確認。CLAUDE.mdの外部ツール一覧へ追記。

- Claude Code (2026-10-09): hrig参考の研究論文・制作発表を調査しdocs/research/rig-research-papers-2026-10-09.md(ローカル)へ保存。変形9・補正7・二次動作4・操作性/IK9・構築/性能/データ5・自動リギング4の分類で、標準ノード/事前計算/C++・Bifrostの区分と公開実装・ライセンスを整理。コード変更なし。

- Codex (2026-10-09): 検証済みexprespy導入・hrig Soft IK微小倍率修正・新7テスト/登録・日英Sphinx比較結果をd1667e5へコミットしorigin/mainへpush完了（20ファイル）。公開前に独立監査、startup6件、完成JSON/日英HTML130数値セル・結果件数/導線・差分検査を再確認して成功。直前のMaya2025/2027各148件・cross-save54入力差0・日英Sphinx成功証拠を確認。Claudeの約45サブモジュール追加と.gitmodules/WORK_LOG並行差分を専用indexで切り分け、共有indexの他stageを保持。docs/vscode.md・研究資料/生成物・他ツール記録を含めず保持。GUI描画性能/正式exprespy backend等の制限は文書へ記載済み。

- Claude Code (2026-10-09): リグ手法調査の49リポジトリをmaya/external/へshallow submoduleで追加(index登録のみ・未コミット。.gitmodulesには別作業のmaya_exprespy追加も同居)。Maya用27個の.modをmaya/modules_disabled/へ作成(maya_*.batからはパスが通らない)。一時MAYA_MODULE_PATHでMaya2022/2026/2027のmayapy確認: ビルド済みプラグイン(boneDynamicsNode・perseus・colDetectionNode・nyCollisionDeformer・iDeform・cmt_py・FDDADeformer)は版が合えばロード成功、SrtRbfNode(Maya2020向け)は失敗。要ビルド/依存不足(Simplex・dem-bones系・ssds・dm2skin、2022のimpulse/aniseed)以外のPythonパッケージはimport成功、Bifrost設定とMELパスも反映。CLAUDE.mdの外部ツール一覧に追記。

- Codex (2026-10-09): ユーザー指定でSoft IK倍率異常を修正し日英Sphinxへ結果掲載。Maya2025/2027のmultiplyDivide微小分母のoutput100000を実測し、SoftIK専用の標準double演算へ置換、nativeUnits/変換ノード所有で版差を吸収。公開署名・クランプ・距離0・Undo・参照式・ScalarGraphを維持。新5+2をstandard/allへ登録し公開4suite両版各148件全成功/終了0/skipなし、2025 cm/m/mm保存→2027読込54入力差0。最終scalar350/通常リグ12構成/微小実Limb60（3397数値finite）を再確認し倍率正常、Maya標準RPチェーンと192条件一致で原点残差は制限として記載。修正後Limb30を4方式×3mode・240frame×7再測定し12条件84反復/終了0、cache無効/fallbackなし/max差2.3981e-6。Sphinxは初回Matrix24条件168反復と別実行Limbを区別して掲載、日英-E -a -W/各18HTML成功、130数値セルと結果件数/導線を生JSON照合。英訳242保持/146追加/未訳0、独立レビュー・署名/AST/sourceSHA/差分検査成功。旧保存DGは再構築が必要。GUI描画/他版速度/正式exprespy backend等は未検証、未コミット/未プッシュ。研究・生データはGit対象外、既存exprespy導入と並行差分を保持。

- Claude Code (2026-10-09): GitHubのリグ手法を調査しdocs/research/rig-setup-techniques-2026-10-09.md(ローカル)へ保存。RBF・ポーズ補正9件、IK/骨制御9件、揺れ物・衝突・変形8件、行列リグ・構築の仕組み7件をライセンス区分付きで整理し、現poseRbf(Gaussian厳密補間)との差と標準ノード化の可否を記載。コード変更なし。

- Claude Code (2026-10-09): hedit 0.6.0(0.5.2のホバー0.3秒を含む)。操作感の調査の提案11件に対応: 補完の待ち時間250ms→40ms(.の直後は0ms)、大文字小文字を区別しない単語の頭からのあいまい一致と度合いの順(core/fuzzy_match 新設、補完エンジン・import名も同じ規則)、一覧12行、コメント・文字列・数字で始まる語では自動補完しない、閉じた状態のBackspaceで開き直さない、同じ名前の候補ではEnterで改行、Home(空白の後⇔行頭)、Ctrl+↑↓で1行スクロール、選択なしCtrl+C/Xの行は行の上へ貼る、Enterの規則(return等で浅く・開き括弧で深く・括弧の間・空白だけの行・コメント内の:)、else:等の:で1段浅く、自動で入れた閉じ括弧だけ上書き・対で削除、スペルは入力中の単語に付けずスクロール後60msで検査、検索の初期値に単語・コード欄のEscで検索バーを閉じる・Alt+C/W/R/P、キャレット2px、見出しの固定表示の下に隠れない。全6版ビルド(警告0)・単体テスト(core 19・Python 35・UI)合格、GUI全スイートを2022・2024・2027で合格、日本語ドキュメントのSphinx -W合格。実測(2027): 補完の窓 291→83ms、.の後 283→50ms、ホイール後に画面が止まるまで 484→92ms。コミット・プッシュ済み。

- Claude Code (2026-10-09): hedit・VS Code・Charcoal Editor 2 の操作感の比較調査。キー/ホイール/マウスを送って画素が変わるまでを同じ条件で実測(隔離した VS Code、テスト用 Maya 2027)。入力は3つとも1コマ(Charcoalは6,000行で約0.3秒)、hedit は補完の窓が約0.25秒遅い(250msの待ち)・スペルの波線が打つたびに消えて約0.45秒後に戻る。細部の比較と改善の提案11件を docs/research/hedit-feel-20261009/README.md(ローカル)にまとめた。コードは変更なし。

- Claude Code (2026-10-09): hedit のリファクタリング検討の深掘り。テスト・Python側とビルド・C++全体の書き方を読み、前回の未確認の指摘を mayapy で再現(9件確定。BOMは不具合でない)。新たに埋め込みPythonが作業コピーの改行に左右されmllのハッシュがcloneで変わる件・Qt6でQT_NO_DEBUG未定義・Pythonのエラー文が補完以外で捨てられる件など13件、テストの環境依存と作りの問題を docs/research/hedit-refactor-structure-20261009.md(ローカル)に追記。コードは変更なし。

- Claude Code (2026-10-09): hedit 0.5.2。ホバーを出すまでの待ち時間を0.5秒→0.3秒(VS Codeの既定)に短縮(実測で止めてから約0.3秒)。vscode_features_smoke のホバーの手順は、本物のカーソルを動かす QTest.mouseMove をやめてイベントを直接送る方式にし、マウスが上にある印(WA_UnderMouse)を立て、手順の間はOSからのマウスのイベントを捨てる(別アプリの窓が前面でも、カーソルをどこに置いても通る。カーソルを左上へ置いた確認も2022・2027で合格)、構文チェックを先に済ませてから測るようにした。全6版ビルド(警告0)・単体テスト合格、GUI全スイート(gui_smoke・completion_output・formatting_spelling・output_format・output_fallback・vscode_features・perf・session・startup)を2022・2024・2027で合格。2024 gui_smoke の不安定な失敗(PySide2 が消えた QListWidgetItem の包みを残し、同じアドレスの補完の窓を古い項目として返す)は、テストで item() を使わずモデルから読むよう options・vscode_features・perf を修正し、3回連続合格。0.6.0 に含めてコミット・プッシュ済み。

- Claude Code (2026-10-09): hedit のリファクタリング検討(構造・保守性)。src 全体を3分担で読み、段階0(不具合15件: 復元時のCRLF/BOMで未保存の印・名前空間フォルダーが同名.pyを隠す・小窓のスタイル外れ ほか)・段階1(小さな分割14件)・段階2(中規模8件)・段階3を docs/research/hedit-refactor-structure-20261009.md(ローカル)にまとめた。コードは変更なし。

- Codex (2026-10-09): hrigの標準ノード/exprespy/Bifrost/C++をMaya2027隔離standaloneで比較。研究用差し替えでMatrixFollow300個（独立/300段）・実LimbRig30個のSoft IKを3評価モードで計測、120frame warmup/240frame×7・36条件252反復を完走し終了0。全36条件でcache無効/fallbackなし/全出力finite・数値照合成功、最大差1.214e-6。行列12+12条件/拒否5、SoftIK各70scalar×5実装とFK/IK/LOD/停止再開・削除も検証。微小距離実Limb60ケース収集/全3397数値finiteでは、標準DGのratio100000と全方式の原点近傍IK不一致を確認して未修正として記録。独立方法レビューと集計の不正データ拒否検査を実施、表/CSV/生JSONをdocs/research/hrig-exprespy-2026-10-09/report.md等へ保存（Git対象外）。製品API/ソース・外部本体・ユーザーシーン/設定は無変更、性能から描画/スキンを除外。GUI/他Maya版/正式exprespy backend/Undo保存対応は未検証、既存exprespy導入とhedit差分を保持。

- Codex (2026-10-09): ryusas/maya_exprespyをmaya/external/maya_exprespyへサブモジュール追加（88bd0a8）。exprespy.modでWindows/Maya2022〜2027のPy3用.mll/Python/MEL/NEテンプレートを登録し、独立MayaExprespy startupでGUI遅延ロード・重複防止・失敗警告/再試行を追加。通常ユーザー設定/SafeMode/外部本体は無変更。境界テスト6件を通常Python/2022で成功、全6版standaloneで正しいバイナリ・補助パス・式追従/コード更新成功、2022/2027隔離GUIで手動ロード前の自動ロードと式評価成功。初回GUI検証は既存ランナーが起動スクリプトを無効にする設定で失敗し、隔離テストprefsだけ有効化して再検証成功。独立パス監査/差分検査成功、README追記。通常環境全体/他版GUI/AE・NE目視は未検証。記録はdocs/research/exprespy-integration-2026-10-09/implemented.md（Git対象外）、未コミット/未プッシュ。hedit並行差分を保持。

- Codex (2026-10-09): mlibの内部改善R01〜R09と利用者向け改善U01〜U10・追加API・日英ガイド/英訳・検証を28c486aへコミットしorigin/mainへpush完了（87ファイル）。直前のMaya2022/2027各1,258件・実GUI ScriptJob各2件・日英Sphinx成功記録を確認し、公開入口/文書fixture30件/staged差分検査を再実行して成功。関連差分を独立監査、共有ログはCodex完了記録だけを部分stage。研究資料/生成物・hedit進行中差分・docs/vscode.md・他作業ログは含めず保持、判定衝突名待ちも維持。

- Codex (2026-10-09): mlib利用者向け改善U01〜U10と具体的な追加入口を実装。weight Plug/Vertex入力、正式component名/getter、デルタ単体IO・追加、skin集約、settable/valid、Snapshot.capture/適用判定、ScriptJobs.temporary、拡張診断、通知詳細と復元警告、目的別ガイドを追加。Namespace親指定は今回の全対応指示に基づき作成先/存在判定/返却を一致。既存2,307署名はgetter委譲化以外の変更0。Maya2022/2027各141files/1,258件を実行し失敗0（条件付きskip11/8）、実GUI ScriptJob各2件成功。静的fixture30件・公開入口/layout20files/日英Sphinx -Wと各501HTML/差分検査成功、英訳12,271件維持・295件追加。実施記録はdocs/research/mlib-usability-2026-10-09/implemented.md（Git対象外）。実HumanIK全身リターゲット・他Maya版・手動目視・今回の性能/IDE実測は未検証。未コミット/未プッシュ、R01〜R09・hedit差分・判定衝突名待ちは保持。

- Codex (2026-10-09): mlib/mlib_*の利用者視点のリファクタリング検討。全製品Python272files/51,138行の実装本文・公開説明を4分担で読了し、読了漏れ/重複/SHA差分0を確認。返却weight Plugとターゲット操作、選択Vertexとスキン操作、Selection正式名、component正式getter、デルタ単体IO、目的別の連続例を優先案としてdocs/research/mlib-usability-2026-10-09/report.mdへ保存（Git対象外）。HumanIK成功後の欠落メソッド呼出と古い回復案内を確認、Namespace親指定は文書化済みの意味変更として区別。隔離Maya2027で代表利用例・単位・保存・状態を実証、通知/モード切替は障害注入。GUI/他版/性能/実HumanIK成功は今回未検証。製品・正式文書の変更/コミット/プッシュなし。既存R01〜R09未コミット変更・他ツールのhedit変更・判定衝突名待ちは保持。

- Codex (2026-10-09): mlib全体検討R01〜R09を実装。未使用接続helper除去、Plugロック復元共有、Components/UV/Edges/Faces一括照会、addAttr/Transformation/Weights/DagPoseの内部段階分割、bulk結果方針分離、extension/registry責務整理、UI/JSON照会と保存対応表共有、math共通補助移動、Bifrost port検証共有、未知型cacheとPlugin正常更新境界を整理。公開構成・2307署名・戻り値・保存形式・Undo/fast/途中更新を維持。追加テストを含むMaya2022/2027 standalone各131files/1198件成功（条件付きskip）、使い捨てGUI各15件成功、2027/Bifrost native8件成功、移動前pickle35/42件成功。静的fixture45件・公開入口/日英Sphinx -W/各501HTML・layout25files/差分検査成功。既存英訳12118件維持/153件追加。性能をHEADと隔離比較し、実施記録をdocs/research/mlib-refactoring-2026-10-09/implemented.mdへ保存（Git対象外）。手動GUI・他Maya版・CI/公開未実施、未コミット。他ツールのhedit変更・判定衝突名待ちは保持。

- Codex (2026-10-09): mlib/mlib_*全体のリファクタリング検討。製品Python270ファイルをASTで棚卸しし、分野別の実装・既存テストを確認。公開構成・署名・戻り値・Undoを維持する9候補と実施順を docs/research/mlib-refactoring-2026-10-09/report.md に整理した。設計資料の古い説明、未使用Node接続helper、Plugロック復元、コンポーネント一括照会、複雑な編集処理の分解を優先候補とした。公開入口検査の不一致0・Maya不要fixture45件成功、製品270ファイルのSHA-256不変。Maya/GUIの新規実行・速度測定なし。研究資料はGit対象外、製品変更・コミット・プッシュなし。他ツールのhedit変更と判定衝突名の回答待ちは保持。

- Codex (2026-10-09): 検証済みのmlib接続方向・get/is省略とSphinx表示・Translate/Rotate/Scale命名・Node create、およびhrig/HTools利用側・方針/日英文書・CI検査を4aaad14へコミットしorigin/mainへpush完了（145ファイル）。公開checker・文書fixture29件・staged差分検査成功、直前のMaya2022/2027 standalone各1162件と日英Sphinxの成功結果を確認。mlib外の関連15ファイルも独立監査し無関係差分なし。生成物・研究メモ・外部submoduleを含めず、is衝突名の確認待ちは保持。

- Codex (2026-10-09): 単数Node constructorへキーワード専用create=Falseを追加。Trueは現在のexact型登録と指定名で新規作成し、既存Node.createのcmds・標準plugin・名前/親・Undo処理を共有。既定Falseの既存入力解決を維持し、未知引数・非bool・基底/抽象/未登録/複数登録型・SkinClusterを生成前に拒否。製品変更はNode/SkinCluster/registryの3ソース。新規17件を含むMaya2022/2027 standalone各123ファイル1162件成功（GUI/版等の条件付きskipあり）、新規説明3ブロックもMaya2027で成功。空meshの頂点数照会例は訂正後再検証。日英Sphinx -W成功、条件付き基底を含むNode89クラスのcreate署名/他系統105署名保持、625省略入口/13cmds二署名・各499HTML検査成功。文書fixture16+13件・公開入口・layout・差分検査成功。英訳12079件維持/39件追加。GUI/他版・CI/サイト公開は未実行、未コミット。is衝突名の確認待ちは保持。

- Codex (2026-10-09): mlib.cmds公開get13種の省略関数・同名ファイル・呼出時委譲・cmds/root両公開を確認（実装追加漏れなし）。Sphinxの取得13ページにmlib.x/mlib.cmds.xの二署名を共通説明で掲載し、cmds.getX旧xref/アンカーを短名へ対応。一覧と使用例2ページ・設計説明を更新し、HTML署名/既定値/kwonly境界・両公開名/旧参照の検査追加。文書fixture13件、日英Sphinx -W・625入口と13cmds二署名・各499HTML・公開入口/差分検査成功。既存説明204コードブロックとcmds製品ソースを維持、英訳12058件保持/21件追加。初回gettextの見出し線不足は修正後再検証成功。今回はMaya/GUI再実行・CI/公開未実行、未コミット。is衝突確認待ちは保持。

- Codex (2026-10-09): mlibのTranslation→Translate・EulerRotation→EulerRotate、独自Translation/Rotation/Scaling→Translate/Rotate/Scaleを、正式getter/setter・省略入口・複数形管理表・ファイル名・内製利用側まで統一。Quaternion.asEulerRotateを標準変換への委譲で追加。Maya標準名/useEulerRotation・引数/単位/Undo/JSON保存タグを維持し、旧名/旧importは廃止（改名前pickleは非対応）。本番337ソースの既存3210関数は改名/docstring以外AST差分0、既存説明203コードブロックも改名以外差分0。Maya2022/2027 standalone各122ファイル1145件、hrig/Aim関連70件、文書fixture12件、日英Sphinx -W・625入口/新クラス参照/各499ページ検査、公開入口・mlib変更18files layout・差分検査成功。英訳11816件維持/242件追加。GUI/他版・CI/サイト公開未実行、未コミット。is衝突名の確認待ちは保持。

- Codex (2026-10-09): is判定68定義を棚卸しし、衝突9定義を除く59省略入口（mathsの実定義4件含む）を通常defの遅延委譲で追加。既存get/is本体・引数/返値/接続方向/フラグ維持、bulk短名9件の事前検査登録追加。Sphinxの署名/本文/戻り型/旧isリンク・アンカーを省略名へ集約し、Plugin/ReferenceのisLoaded・WorkspaceLayout/SceneのisCurrentを文脈で区別。手書き説明15ページと形式案内更新、旧200ブロックは判定名以外のAST差分0・新規例1ブロック。Maya2022/2027で新8件＋既存156件が各成功（初回の新規接続テストの向き誤りを訂正後8件再実行）、文書fixture12件・日英Sphinx -W・625入口の文書検査・各499ページのMermaid検査・公開入口/差分検査成功。既存英訳11663件維持/153件追加、既存2546関数AST維持（_call_targetの説明更新を除く）、layout25files違反0/定義参照によるクラス順スキップ25。GUI/他版・CI/サイト公開は未実行、未コミット。衝突7名の上書きは別途確認待ち。

- Codex (2026-10-09): mlibの説明・使用例・Sphinx API一覧をget省略名へ統一。566入口へ本体の署名・説明・戻り型を掲載し、get付きxref/既存アンカー・コマンドURLを維持。13取得コマンドの同名再公開関数とモジュールを区別し、概要と引数表示を修正。Maya標準名・引数・JSONキーを維持し、使用例200ブロックのASTを確認。文書fixture7件、日英Sphinx -W、566入口の署名/参照/HTML検査、各499ページのMermaid検査、公開入口/差分/新規補助layout検査成功。英訳965件追加・既存10698件保持、CI検査追加。今回API本体は変更せず、Maya実行/サイト公開/CI実行は対象外、未コミット。

- Codex (2026-10-09): Plug.getConnections/connectionsにsrc/source・dst/destination別名を追加し、isConnected/isConnectedTo/disconnectAllにキーワード専用の方向boolを統一。既存getConnectionsの位置引数・s/sourceとd/destinationのAND、disconnectの既定/戻り値、直接接続の範囲とUndoを維持。方向固定APIは変更せず、isConnectedToの削除済み相手Plug検査漏れを修正。新規14件と関連172件がMaya2022/2027 standalone各186件成功。日英Sphinx -W警告0、英訳49件追加/既存10649件保持、公開入口不一致0・差分/レイアウト違反0（Plug内の並びは既存L023でスキップ）。GUI/他版未検証、未コミット。

- Codex (2026-10-09): mlibの配置/公開/型対応/複数形API整理、566 get省略入口、getAttrのPlug返却、disconnect方向指定、スキンウェイト修復とforce解除、および関連利用側・docs/CI設定をfc143dbにコミットしorigin/mainへpush完了（468ファイル）。公開checker/fixture16件・差分検査成功、直前のMaya2022/2027 standalone/日英Sphinx検証を確認。使用中でない古いGit index.lockを.maya-outputへ退避して公開を実行。hedit・外部submodule・研究/生成物を含めず保持。

- Claude Code (2026-10-09): hedit 0.5.1。/Brepro・/Zi→/Z7・リンク前に前回のpdbを削除の3点でhedit.mllを再現可能にした(全6版で再ビルド・クリーンビルドとも同じハッシュ)。スマートアプリコントロールONでは.mllは止まらずテスト用の未署名exeが止まることを確認。6版の単体テスト、2022/2027のgui_smoke・session・startup合格。未コミット。

- Codex (2026-10-09): ユーザーの一律追加・既存名上書き指定により、独自get[A-Z]全566定義へ通常defの省略入口を追加（class553、cmds/root13）。元getter全件AST不変、呼出時self/cls/getモジュールへ委譲し署名/フラグmetadataを共通補助で保持。static17件は省略側のみclassmethod、class2件と派生override/個体差替えへ追従。bulk短名76件を両管理表へ明示しcallEachの検証は現在の正式getterで実施、空集合/専用集約/既存封鎖/Undoを維持。同名アトリビュートはmethod優先とし既存直接Plug4参照＋conversion.inputと説明例をgetPlug化、旧短名不在テストを更新。Maya2022/2027全119ファイル各1116ケースは118ファイル成功・新規テストのcmds参照元誤りのみ失敗、専用nounモジュール参照へ補正後9ケースが両版成功。変更対象のunittest直接実行でmlib58ケース（比較6件はcymel実在名へテストだけ補正し再実行成功）が両版で成功、hrig22件は2027で成功。日英Sphinx -W警告0、英訳620件更新/対象外10029件保持、公開宣言/構文/差分検査成功。layout219files違反0、クラス内getter参照96クラスの並びはL023で検査スキップを維持。GUI/他版未検証、外部submodule無変更、未コミット。

- Codex (2026-10-08): mlib.getAttr/cmds.getAttrの照会フラグなし呼出しをgetPlugへ委譲し、型付きPlug・既存Plug identityを返すよう変更。target引数と既存照会フラグを維持し、明示kwargs（False/time/silent含む）は従来のUI単位値・状態と数学型を返す。値取得の利用側をget/getuへ移行し、hrigのUI単位変換を保持。全6231 PythonファイルのAST棚卸し、入力/疎配列非実体化/Undo不登録/型/単位/照会別名の新5件とmlib関連計83件がMaya2022/2027で各成功。hrig関連22件は2027で成功、2022は19件成功・腕脚3件は既存Maya2025以降制限で実行不可。日英Sphinx -W警告0、英訳16件更新/対象外10013件保持、構文/公開宣言/対象新規layout/差分検査成功。GUI/他版未検証、未コミット。

- Codex (2026-10-08): 値取得用Plug.getは既存実装で、公開16型すべてから呼べることを確認。数値/bool/文字列・Translation/Matrix・疎配列dict・compound tupleを隔離Maya2027で実行確認。既存get入口・内部単位・返却型を維持し、製品ソース/公開docs/テスト追加なし。GUI/他版は今回未実行。

- Codex (2026-10-08): SkinCluster/Joint.removeInfluence・SkinClusters.removeInfluences・既存removeUnusedInfluencesへキーワード専用forceと短縮fを追加。不正ウェイトを除去してから既存解除を実行し、従来引数/返値/移送を維持。removeInvalidWeights（単数/複数self）を追加し、rawweightListの負値・NaN/±inf・未登録論理番号だけを除去。正規化/0補填/1超切捨て/ロック解除/レイヤー回避なし。通常cmds Undo・fast MDGModifier Undoなし、全対象readonly事前検証、最後/allzero拒否、NURBS単独修復と未対応祖先移送の修復前拒否を確認。Maya2022/2027新12＋既存81の各93件成功、日英Sphinx -W警告0・翻訳57件/非対象保持・構文/公開宣言/layout/差分検査成功。複数geometryの第二形状の既存MayaウェイトAPIは隔離probeで異常終了し今回の独立編集対象外、祖先移送は従来の先頭mesh制限を維持。GUI/他版未検証、未コミット。

- Codex (2026-10-08): Plug.disconnectへsrc/sourceのbool入力指定とキーワード専用dst/destinationのbool出力指定を追加。既定入力のみ・指定入力Plug/MPlug/文字列・既存の位置引数/force/f/naと戻り値を維持し、方向モードは直接の相手Plugリスト・未接続/両Falseは空リスト。全出力・ロック/親/共有配列親の復元・複数切断の単一Undo/Redo・変換/子接続保持・strict不一致/別名競合・配列返却例外を検証。Maya2022/2027で新11件＋既存関連78件（各89件）とAPIメソッド手動assert成功、2027はNode API54件も成功。日英Sphinx -W警告0、公開宣言不一致0・layout違反0・構文/差分検査成功。実行ファイル名の誤指定1件は訂正して別実行成功。GUI/他Maya版は未検証、未コミット。

- Codex (2026-10-08): mlib全240実装ファイル39390行からget[A-Z]566実定義（293名）を棚卸し。nodes420/plugs34/components28/common71/cmds13、maths/json独自get候補0。全件CSV/JSON・領域別の署名/返型/副作用/継承/判断と修正案をdocs/research/mlib-getter-aliases-20261008*へGit対象外で保存。Maya2027の型属性照合77型で43種類/54宣言元の標準アトリビュート衝突を確認、Joint.radiusとCompoundPlug同名子がPlugからmethodへ変わる事例を隔離プロセスで再現。静的Python短名衝突0、型未照合/staticmethod束縛/UI読込/複数形集約を別分類。get本体＋通常def委譲、衝突名原則除外、任意attrの意味2案と検証計画を提案。製品コード/公開docs/利用側変更なし、GUI/他Maya版未検証。

- Claude Code (2026-10-08): hedit 0.5.0。高速化・軽量化レビューの全項目を実装(core・Python・画面全体は別作業コピーで並行し3方向で統合)。1キーの入力16→3ms、self.補完114→0.3ms、構文チェック2万行9→0.7秒、30タブ復元460→66ms、閉じている間の出力の負担≒0など。開発中に見つけたMaya 2022のクラッシュ(QTextDocument::clear中の通知でQTextCursorを解放)を修正。6版ビルド・単体、GUI 9種を2022/2024/2027で合格。未コミット。

- Codex (2026-10-08): mlibのクラス/コマンド公開を明示importと__all__へ移行（commonは明示遅延公開を維持）、Node/Plugと外部拡張の型対応を_WRAPPER_CLASSESへ集約。型の自動選択・既存Undo/reload契約を維持し、登録デコレーター/discoveryとbulk生成を撤去。146一括入口を通常defから共通dispatchへ委譲し、raw引数・空集合・単数署名・要素別指定専用の封鎖を維持。公開漏れ/衝突/参照元/補完/型表のAST検査を追加しCIへ組込。管理表/実入口の整合検査と署名付随のlayout処理を追加。変更前後の公開名・型表・8269署名一致。Maya2022/2027全115ファイル各1076/1077件成功、最終関連40件＋公開/補完7件と独立コマンド検証も各成功。検査fixture16件・製品不一致0・layout違反0・日英Sphinx警告0・各484HTML/Mermaid検査成功。GUI操作/他バージョン未検証、hedit無変更、未コミット。

- Codex (2026-10-08): 公開6フォルダのクラス自動公開案をASTで確認。候補183クラス、同名衝突なし、現行未公開はDeletedAttributeErrorのみ。外部型MSpace・非公開指定・common遅延import・静的補完の扱いを整理し、管理負担への懸念から明示公開と漏れ検査の案もローカル調査メモへ記録。製品コード変更・Maya実行なし。

- Codex (2026-10-08): mlibの公開/型登録/型選択/一括生成を分け、PyMEL1.5.0同梱ソースとcymel同梱版/本家main0.36を比較。PyMELの標準メソッド事前ソース生成、cymelの主要クラス明示登録と必要時の型生成、両者の通常list取得を確認。mlibは公開・複数形メソッドを明示し型選択は維持する案をdocs/research/mlib-auto-registration-20261008.mdへローカル保存。製品コード・外部submodule変更/Maya実行なし。

- Codex (2026-10-08): 一括APIの4宣言漏れを既存bulk_apiへ追加。型/コマンドの自動検出と一括転送の宣言に基づく自動生成の区別を実装確認し、日英の複数形APIガイドへ追記。登録網羅検査をNodes/DagNodes/Transformsにも拡大し、関係照会の対象順・二重リスト・Joints既存集約・複数対象削除の単一Undo/Redoを回帰検証。Maya2022/2027の全体114ファイル実行は各113成功、追加テストの作成順に関する誤った期待のみ失敗したため既存契約に合わせて修正し、関連3ファイル各18件再実行で成功（登録漏れ失敗解消）。日英Sphinx -W警告ゼロ、layout・差分検査成功。今回はGUI未実行、未コミット。

- Codex (2026-10-08): mlibのscene/environment/ui/events/utilsをcommonへ統合、公開6コンテキスト関数をroot decorator.py、通知をroot logger.py、Object/extensions実装を_core、docsを_docsへ移動。追加ユーザー指示でmlib.Object/mlib.extensionsのroot公開も撤去し_core入口へ更新。内製利用側・Bifrost分類・テスト・ガイド・CI・補完設定を追従、旧互換入口なし。common遅延公開、Selection/Cycleのreload参照、旧loggerハンドラ除去に対応。公開1494定義の引数/デコレーター一致。Maya2022/2027各1069テスト・114ファイル実行、各113ファイル成功、既存の上記bulk登録漏れ1件だけ失敗。Maya2027 GUI自動15件、Bifrost5件、hrig19件、command discovery独立実行成功。日英Sphinx警告ゼロ、HTMLリンク・layout・差分検査成功。手動GUI操作/文書ブラウザ描画は未検証。旧cache/初期化ファイルは.maya-outputへ保存、未コミット。

- Claude Code (2026-10-08): hedit全コード(約16,400行)を高速化・軽量化の観点でレビュー。キー入力ごとの全文再構築・非表示時の出力タイマーとカーソル移動での保存・型推論の行ごとの正規表現コンパイル等を確認し、段階別の改善案と計測方法をdocs/research/hedit-refactor-perf-20261008.md(ローカル)へ記録。コード変更なし。

- Codex (2026-10-08): logger直接通知呼出は本体の6ファイルと確認し、Node経由の利用・hrig/HTools利用も整理。decorator.pyと並ぶmlib直下logger.py案を構成資料へ反映。通知/例外契約、初期化順、改名済みセッションのハンドラ重複検証を記録。製品ソース変更・Maya実行なし。

- Codex (2026-10-08): extensions.pyを_coreへ配置する案を構成資料へ反映。探索・登録・reloadの内部責務、外部拡張の公開登録/状態照会入口、__package__由来の接頭辞への影響を確認。正式な公開入口は配置と別に整理する条件を記録。製品ソース変更・Maya実行なし。

- Codex (2026-10-08): ユーザー方針によりObject名称・Node/Plug/単数Componentの共通基底契約を維持。_core/object.pyへの実装配置とmlib.Objectの正式公開入口維持を構成資料へ反映し、撤去/改名候補を不採用として整理。製品ソース変更・Maya実行なし。

- Codex (2026-10-08): Object公開基底/factoryを外し、各基底の型別解決とlsの検索・列挙へ分担する案を検討。単数取得とlsの差、既存Plug/Component構築仕様、cmds向け内部正規化の移管条件を調査資料へ追記。製品ソース変更・Maya実行なし。

- Codex (2026-10-08): Objectのfactory・内部入力正規化と既存テストを読取確認。Node/Plug/単数Componentの契約を維持し、common全体への継承拡張は入力契約が不整合になる点を整理。使用例と判断をローカル調査資料へ保存。製品ソース変更・Maya実行なし。

- Codex (2026-10-08): 最新方針の最終構成案を更新。_core維持、資料は_docs、json/decorator.pyはルート、その他の公開共通機能はcommonに統合する配置を整理。製品ソース変更・Maya実行なし。

- Codex (2026-10-08): _coreの14実装ファイルを登録・検証・変換・更新等に分類。docs→_docsと_core→coreの命名案、公開保証との区別、CI/探索除外/旧core除去処理の更新範囲をローカル資料へ記録。製品ソース変更・Maya実行なし。

- Codex (2026-10-08): ユーザーの検討方針に合わせDecoratorクラス案を撤回し、公開6関数をmlib直下decorator.pyへまとめる案に更新。jsonのルート配置を維持し、直接関数importとモジュール利用を例示。製品ソース変更・Maya実行なし。

- Codex (2026-10-08): Decoratorの静的メソッドから各呼出のcontextmanagerを返す案を検討。jsonはmlib直下の共通保存基盤として維持し、common/decorator.py案を構成資料へ反映。with/@・退避状態・既存契約・Maya依存の説明を確認。製品ソース変更・Maya実行なし。

- Codex (2026-10-08): json/decoratorsの現行実装を確認。JSONはSnapshot派生・保存参照・適用計画など16クラス、decoratorsは独自クラスなし・公開6関数のcontextmanager群。JSONは複数機能のまとまり、decoratorsは関数の目的別分割と整理。製品ソース変更・Maya実行なし。

- Codex (2026-10-08): 基本5領域を直下維持し、scene/environment/ui/events/utilsをcommonへ統合、json/decoratorsをcommon配下に残す最終配置案をローカル資料へ保存。現行ファイルとの対応・同名衝突・公開入口・移行範囲を確認。製品ソース変更・Maya実行なし。

- Codex (2026-10-07): mlibの現行フォルダと公開型を確認。Sessionはルートsession.py、取得入口はcmds/getSession.pyとする未実装の配置案を整理。既存の機能別フォルダは維持する案。製品コード変更・Maya実行なし。

- Codex (2026-10-07): 中核4型以外を操作クラスと対象・状態オブジェクトの二層に統一する設計案をローカル調査資料へ記録。static方式と共有インスタンス方式を比較し、対象解決・with・拡張判断・既存API移行条件を整理。実装変更・Maya実行なし。

| Codex | 2026-10-07 | mlibの中核4型以外（読取）・docs/research | 全体操作・対象参照・保存値・登録管理に分類し、TimeSlider/Viewport/Scene等の責務混在と内製利用箇所を調査。ローカル調査資料を保存。実装変更・Maya実行なし。 |

- Codex (2026-10-07): UI/scene/environmentのクラス設計を読取確認。Outliner/ChannelBox/Shelf/Window等は対象参照、GraphEditor/NodeEditor/MainWindowとPreferences/Workspaceは静的な操作窓口、TimeSlider/Viewport/WorkspaceLayoutは個別参照と全体操作を併有。関数化ではなくクラスの操作範囲とインスタンス要否を統一する方針を提案。製品コード変更・Maya実行なし。

- Codex (2026-10-07): スキニング関係照会・未使用中間Shape取得/削除・delete(safe=False)と関連テスト/資料をコミット対象に集約。origin/main同期・差分検査成功、直前のMaya2022/2027各35テストとSphinx検証結果を確認。ユーザー指示により本コミットをpushする。

- Codex (2026-10-07): Node/Nodes・Joint/Jointsにdelete(*, safe=False)を追加。safe=Trueは自身とDAG子孫の入出力/message/Set接続をOMで検査し削除をスキップ、Jointのウェイト移送/再親付けも抑止。既定削除・None戻り値・Undo維持、forceはsafe=Falseと重複するため追加なし。既存削除テストのNode/文字列混在入力を確定済み入力規則に合わせ、混在拒否も検証。先行2機能を含むMaya2022/2027 standalone各35件成功、Sphinx -W・layout・差分検査成功。GUI未検証、未コミット。

- Codex (2026-10-07): Transform.getUnusedIntermediateShapes/deleteUnusedIntermediateShapesを追加。直下の中間Shapeで標準SG所属以外の出力がないものを対象とし、使用中・参照・ロック・直接/間接インスタンス・子DAGは除外。入力接続をcmdsで外してからShapeのみ削除し、上流履歴と親Transformを保持。Undo/Redo・失敗時巻き戻し対応。Maya2022/2027 standalone各6テスト成功、Sphinx -W・layout・差分検査成功。GUI未検証、未コミット。先行のスキニング関係照会API変更も保持。

- Codex (2026-10-07): DagNodeにgetSkinClusters/getBindPosesを追加しShape/Transformへ共通提供。Transform直下の非中間Shapeが出力先であるSkinClusterをOMの上流幅優先検索で取得し、別形状の履歴を除外。DagPoseは重複/未接続を除外、Joint既存influence照会を維持。Mesh・NURBS曲線/面・複数Shape/直列skin・インスタンス・別形状除外・読取無変更の新規6件と既存DagNode/DagPoseをMaya2022/2027 standalone各25件検証成功。Sphinx -W・layout・差分検査成功。GUI未検証、未コミット。

- Codex (2026-10-07): Mesh/NURBS共通の取得経路を実装確認。Node.getHistory(type="skinCluster")とSkinCluster.getBindPoseは既存、Shape/Transformの専用getSkinClusters/getBindPosesは未実装。履歴検索と直接変形関係の違いを説明。製品コード変更・Maya実行なし。

- Claude Code (2026-10-07): ユーザー指示でビルド済みpluginLoadProbe.mll(Maya2022〜2027、各版mayapyでロード確認済み)をコミット。tools/plugin_load_probe/.gitignoreを削除し、README・CMakeListsの「Git対象外」記述を更新してpush。

- Codex (2026-10-07): DagPose.mergeとcurrentPose/deleteSources（既定True）の実装・テスト・資料をコミット対象に集約。ログ競合は既に両方の記録を保持して解消済み、origin/main同期・差分検査成功。直前のMaya2022/2027各17テスト成功を確認し、ユーザー指示で本コミットをpushする。

- Claude Code (2026-10-07): origin/mainをpull(pluginLoadProbe追加分)。tools/plugin_load_probeをこのPCでMaya2022〜2027向けに全てビルド成功(警告はMSB8029のみ)。各版のmayapyで%TEMP%配下とリポジトリ内release/の両方からloadPlugin/unloadPlugin成功、ロード時の表示も確認。比較のhedit.mll 0.4.0も全版ロード成功。GUIでのロード(信頼済み場所の警告ダイアログ)は未確認。コード変更なし。

- Codex (2026-10-07): ユーザー指定でDagPose.mergeのdeleteSources既定値をTrueへ変更。元ポーズ保持のテストはFalseを明示し、省略時の削除・skinCluster再接続・Undo/Redoを検証。Maya2022/2027 standalone各17件成功。既存WORK_LOGの競合は保持、GUI未検証・未コミット。

- Codex (2026-10-07): DagPose.merge(sources, *, currentPose=False, deleteSources=False)を追加。保存済みxform内部情報・親関係を保持して統合、currentPoseは既存メンバー含む現在姿勢保存。skinCluster接続統一・任意の元ポーズ削除・事前競合/外部接続検査・Undo/Redo/失敗時巻き戻しに対応。ウェイト・bindPreMatrix・joint.bindPose・現在の変形を維持。Maya2022/2027 standalone各17テスト成功（新規8件）、Sphinx -W・layout・差分検査成功。GUI未検証、未コミット。

- Codex (2026-10-07): DagPose・SkinCluster・Plug接続APIを確認。専用統合APIは未実装。全対象が保存姿勢にある場合のメンバー追加とskinCluster接続統一例、保存姿勢の競合とaddMembersの現在姿勢保存の制限を説明。製品コード変更・Maya実行なし。

- Claude Code 2026-10-06: `.mll`のロードがWindowsの組織ポリシーに止められる原因を切り分ける、デバッグ用の最小C++プラグイン `tools/plugin_load_probe/` を追加(OpenMaya/Foundationのみ、自動ロードなし)。CLAUDE.md・AGENTS.mdの構成表に追記。Linux上でスタブのヘッダーによる構文確認のみで、Windowsでのビルド・Mayaでのロードは未確認。

- Codex (2026-10-07): 今回のBlendShape編集・createBlendShape・lsコンポーネント対応・Mesh頂点順序合わせと関連テスト/資料をコミット対象に集約。origin/mainとの同期・差分検査を確認。既記載のMaya2022/2027テストとSphinx検証結果を維持し、ユーザー指示により本コミットをpushする。

- Codex (2026-10-07): Mesh.reorderVerticesにkeyword-only match="uv"/"position"とworldSpace=False（ws別名）を追加。既存引数維持、位置照合は許容距離cm内の一意対応を空間セル検索で検証。対象UV・割り当ては維持。位置/空間/許容誤差/曖昧対応/Undo・fastの4テスト追加、Maya2022/2027各16件成功、Sphinx -W・layout・差分確認成功。履歴・tweak等の既存制限維持。GUI・大規模性能未検証、未コミット。

- Codex (2026-10-07): Mesh.reorderVertices(reference, uv_set="map1", tolerance=1e-6, *, fast=False)を追加。面頂点UV群の一意対応と面接続/向きを検証し、対象の形状・面順・複数UV・硬軟/固定法線・面マテリアルを保持。通常cmds Undo/Redoと失敗時ロールバック、fast OpenMaya更新。通常の非ゼロtweakはUndo復元制約で変更前拒否（fastのみ対応）。履歴・下流形状接続・インスタンス・色/クリース等は未対応として拒否。Maya2022/2027各12テスト成功、Sphinx -W・layout・差分検査成功。GUI・大規模性能未検証、未コミット。

- Codex (2026-10-07): BlendShape.targetEdit(target=None, state=True, full_weight=1.0)を追加。番号/エイリアスとboolで開始終了、既存in-between指定、標準sculptTargetによるUndo/Redo、自身を返す。関連2テスト追加、Maya2022/2027各52テスト成功。Sphinx -W・layout・差分検査成功。Shape Editor GUI表示は未検証、未コミット。

- Codex (2026-10-07): createBlendShape(base, targets=None, **kwargs)を追加。単一ベースへの空/初期ターゲット付き作成、Node入力、標準長短フラグ、通常Undo対応、BlendShapeを返す。ルート/cmds静的宣言・ガイド更新。新規4テストと公開宣言検査を含むMaya2022/2027各112テスト成功、Sphinx -W・layout・差分検査成功。GUI未実施、未コミット。

- Codex (2026-10-06): ユーザー指示によりremoveTargetDeltasをresetTargetVerticesへ改名。引数・動作は維持、reduceTargetDeltasからの呼出・Undo名・テスト・ドキュメントを更新し旧名の別名なし。Maya2027関連105テスト・Sphinx -W・layout・差分検査成功。GUIと他バージョンの今回再実行なし、未コミット。

- Codex (2026-10-06): ユーザー指示によりremoveTargetDeltas/reduceTargetDeltasの既定disconnect=Falseを接続維持のターゲット形状自動編集へ変更。絶対デルタを接続元座標へ変換して差し引き、未接続時・明示disconnect=True・setTargetDeltasは従来動作維持。local/world origin、通常Undo/Redo、履歴なしfast、接続中in-betweenを検証。post-deformation等の制限と浮動小数点誤差を文書化。Maya2022/2027各105テスト成功、layout・差分・Sphinx -W成功。GUI未実施、未コミット。

- Codex (2026-10-06): ユーザー指定によりlsのtype/typへvertex/edge/face/uv/controlVertexを統合。component引数は追加せず、選択・範囲・複数メッシュを単体Componentリストで返す。既存Node/Plug（ArrayPlugを含む）と専用コレクションを維持。4テスト追加、Maya2022/2027各101件成功。最初の一括discoverでリロードにより旧クラス参照が混在したため、ファイル単位の検証に修正して成功。Sphinx -W・layout・差分検査成功。GUI未実施、未コミット。

- Codex (2026-10-06): 選択頂点取得の設計検討。既存captureSelection().filter(type="vtx")はSelectionとしてremoveTargetDeltasへ直接渡せる。lsは現状CommandResult経由でNode/Plugのみ解決。新規component名前空間よりlsへのコンポーネント対応とcomponent絞り込み追加を提案。製品コード変更・Maya実行なし。

- Codex (2026-10-06): BlendShape.reduceTargetDeltasを追加。絶対デルタ長がtolerance以下の格納済み頂点を除外（既定0）、通常Undo/Redo・fast OpenMaya・in-between・接続切断指定に対応。関連3テスト追加、Maya2022/2027 standalone各46件成功。layout・差分検査・Sphinx -W成功。GUI未実施、未コミット。

- Codex (2026-10-06): BlendShape.removeTargetDeltasを追加。頂点番号/Vertex/Verticesで絶対・相対補助デルタから指定頂点のみ除外し、通常cmds Undo/Redo・fast OpenMaya更新に対応。残りのデルタ・マスク・他項目を保持。関連テスト5件追加、Maya2022/2027 standalone各43件成功。layout・差分検査とSphinx -W成功。GUI未実施、未コミット。

- Codex 2026-10-06: BlendShape.getTargetVertices(target, base=None, full_weight=1.0, *, tolerance=0.0)を追加。非ゼロ絶対デルタのベースVerticesを昇順で返し、微小値除外・in-between・複数ベースへ対応。デルタ単体JSONの保存/整数キー復元/新規ターゲットへの再現例を文書化。Maya2022/2027の各38テスト成功、OpenMaya照会・ゼロ/マスク/接続入力・JSON形状再現を検証。日本語Sphinx警告なし、レイアウト・差分確認成功。GUIと中間4版の今回再実行なし。

- Codex 2026-10-06: BlendShapeの照会をOpenMayaへ統一し、replaceTarget/setTargetWeights/setTargetDeltas/duplicateTarget/loadTargetsへkeyword-only fast=Falseを追加。通常cmds/MELのUndoを維持し、fastはMPlug・MFnデータ・MDGModifierで更新。API2に同等操作のない追加/削除/ミラーはfast非対応として明記。Maya2022〜2027の関連33テスト成功（cmds/MEL禁止下の読取/fast、通常との変形一致、Undo履歴不変、ロック保持を含む）。日本語Sphinx警告なし、レイアウト・差分確認成功。GUI・今回の全体回帰再実行なし。

- Codex 2026-10-06: BlendShapeへターゲット削除・置換・複製・ミラー/反転、in-between、頂点ウェイト、デルタ、JSON保存復元の16 APIを追加。既存5メソッドのAST同一を確認。追加22件を含む関連26テストとMaya2022〜2027の各109ファイル/991テスト成功（2025〜2027のBifrostログ書込は制限外で再検証）。日本語Sphinx警告なし、レイアウト・差分確認成功。GUI専用項目は未実行。保存/複製は通常ポリゴン用でpost-deformation・正規化グループ等の制限を文書化。

- Codex 2026-10-06: mlib BlendShape・Plug実装と既存テストを参照し、現在の制御APIと専用API未対応範囲を整理。製品コード変更なし、Maya実行なし。

- Codex 2026-10-06: Ollama利用方針の3ファイルを差分確認し、プッシュ対象として確定。FramePlayerの既存変更は対象外として保持。文書のみの変更のためMaya検証は不要。

- Codex 2026-10-06: ユーザーのOllama利用再開許可をAGENTS.md・CLAUDE.mdへ反映。トークン削減に有効な翻訳・要約等へ使用し、Mayaとの競合回避・終了後のモデル解放・担当エージェントによる検証を維持。ルール変更のみでOllama起動・モデルロードなし。

- Codex 2026-10-06: mlibのget/set・Attr/Attrs・Extra・as命名、短縮アクセサー廃止、数学値のコピー/It更新とmlib戻り型、引数長短別名を実装。HTools/hrig/mlib拡張・テスト・使用例を移行し、AGENTSとAPI仕様を更新。日本語docstring/Sphinxを修正し、このLLMで英訳120件を作成（Ollama未起動）、mlib/hrig未訳0・日英Sphinx警告なし。Maya2022～2027の各108ファイル/969テスト、hrig/Bifrost180テスト、HTools大型55ケースと通常ツール、Aim17/Cycle7テスト成功。レイアウト違反0、変更Python構文・差分検査成功。GUI専用テストは未実行。


- Codex 2026-10-06: ローカル仕様案へExtra・Attr/Attrs・get/set・as統一、短縮アクセサー双方とdeterminant削除方針を反映。コピー廃止案を撤回し、コピー/It付き自身更新を併存、OpenMaya標準例外を維持する指定を記録。仕様整理のみ、実装変更・Maya再実行なし。

- Claude Code (2026-10-06): FramePlayerのSphinxドキュメント(maya/inhouse/FramePlayer/docs、13ページ・画像10枚、heditと同じ作りで色だけFramePlayerの黒と#FF8232)を追加。画像はdocs/tools/capture_docs.pyでFramePlayerとセットアップの窓だけを撮る(設定は撮影後に戻す)。英語版はtools/translate_docs.py(qwen3-coder:30b)で481文を英訳(1件は手で補訂、見出しの大文字化)。GitHub Pagesの/frameplayer/へ載るようmlib-docs.ymlに追加し、README.mdにリンク。FramePlayer単体の利用者向けにmaya/FramePlayerMayaSync.py(Mayaへドラッグ&ドロップで連携パネルとシェルフのボタン)を追加しセットアップに同梱。セットアップとFramePlayerのWindows標準の部品(Cancel・ファイル選択など)も英語で出るようにした。未コミット。

- Codex 2026-10-06: 戻り型をmlibへ統一するユーザー方針をローカル調査資料へ反映。継承メソッド・複合結果・自身を返す処理・生API取得入口の扱いと検証項目を整理。指定どおり仕様整理のみで、製品コードの変更・Maya実行なし。

- Codex 2026-10-06: ユーザー指定で実装せず、引数長短名の両対応方針とメソッド名/OpenMaya比較をdocs/researchへ保存（Git対象外）。250ファイルの定義・別名・動的転送宣言を一覧化し、Maya2027の実OpenMayaと数学パッケージでMRO・継承元・戻り型・ゼロ値処理を確認。Mesh.getNormalsの意味差、Attr/Attribute・Extra/User、as/to・in-place命名を分類。mlib変更なし、シーン操作・旧Maya版検証は未実施。

- Claude Code (2026-10-06): FramePlayerに連番画像を追加(1枚から連番を検出・欠けの表示・既定60fpsで操作部から変更・最初の番号を開始に)。png/jpg/tif/bmp/gif/jxr(標準)とwebp/heif/avif/jxl(拡張機能)はWIC、OpenEXRは自前(走査線/タイル/multipart、half/float/uint、NONE〜DWAA/DWABの全圧縮、zlib展開も自前、色域ACES含む)。28種の連番でコマ番号(GPU/CPU)、色14枚、EXR40通りでoiiotoolの読み込みと一致(DWAは0.1%の画素で半精度1段)。4K EXRはチャンク並列・縮小並列で1枚約60ms。WinAppKitに関連付けの前提条件(Require.<拡張子>=wic/mfvideo:FOURCC)を追加し、拡張機能が無い形式は関連付けない。FramePlayer・Maya側パネル・インストーラーの画面の文字を英語に統一(ユーザー指示)。確認用スクリプト(make_sequence_testdata.py・run_sequence_check.py・run_exr_check.py・FramePlayerImageConvert)を追加。全コーデックの回帰確認も一致。未コミット。

- Codex 2026-10-06: mlib本番250ファイル・1,746定義を静的走査し、命名・引数・内部ロジックの改善候補をdocs/research/mlib-consistency-audit-2026-10-06.mdへローカル保存（Git対象外）。配列番号の検証抜けをMaya境界のスタブによる分離検証で確認。接続/Undo経路差・探索重複・検証/版比較/マテリアル収集の共通化候補と、維持すべき仕様差を区別。mlib実装変更なし。Maya内の実動作は未検証。

- Claude Code (2026-10-06): FramePlayerでMedia Foundationの全コーデックを確認。公式拡張機能を全部導入(Web Media・WebP・JPEG XLを追加)。H.264/HEVC/AV1/VP9/VP8/MPEG-1/2/MPEG-4 Part2/H.263/MS-MPEG4/WMV7/8/MJPEG/DV/Theoraの37通り(mp4・mov・mkv・webm・avi・ts・m2ts・mpg・vob・3gp・wmv)でコマ番号(GPU/CPU)、19本で色が一致。修正: aviは出た順番で番号、ts/m2tsはシーク先を確かめて戻る、MPEG-1/2は時刻欠けのためデコードで目次を作り基準を決めて順番で番号(CPUでデコード)、DVはYUY2のまま受け取り画素の縦横比を表示に反映、MJPEGはBT.601、YUY2のシェーダーの誤り、読み込みが止まったときの作り直し(非同期で10秒)。確認用スクリプト(make_codec_testdata.py・run_codec_check.py)を追加。Windows側の制限(MPEG-4のBフレーム・movのDV・ogg・短い映像だけのmpg)はREADMEに記載。mainへpush。

- Codex 2026-10-05: 記載整理のプッシュ指示を受け、文書・関連テストの改名と参照更新、日英ビルド結果、差分を最終確認。FramePlayerの変更を除外してコミット対象を確定。

- Codex 2026-10-05: ユーザー指示で公開APIの比較表現をmlib自身の仕様説明へ変更。引数・メソッド文書と関連テストをapi_arguments/api_methods/api_convenienceへ改名し、参照・英語カタログも更新。外部ライブラリの実体・登録設定・比較テストのimport・過去の作業履歴は保持。製品コードのdocstring除外AST一致、差分チェック、英訳未訳0件、日英Sphinx警告なしを確認。日本語ビルドは自動生成ファイルの並行処理競合後に単独再実行で成功。Mayaテストは未再実行。未コミット・未プッシュ。

- Codex 2026-10-05: ユーザーのプッシュ指示により、このスレッドのTransformation・便利API・角括弧アクセス・docstring・Sphinx英訳をコミット対象として確認。差分チェックと3サイトの英語版ビルド成功を確認済み。FramePlayerの並行作業は対象外として保持。

- Codex 2026-10-05: ユーザー指定のローカルLLMでmlib/hrig/heditのSphinx英語カタログを更新。qwen3-coder:30bのCUDAエラー後はqwen2.5-coder:32bへ切替え、未訳を分割再翻訳。日本語原文7,352件の未訳・記法検査エラー0件、再抽出後も3サイト未訳0件、英語版-Wビルドすべて成功。cymel_methodsの見出し前空行を補正。翻訳スクリプトに生成上限・打切り応答の拒否・10件ごとの保存を追加し、制限と記法検査を検証。モデル解放済み。日本語docstring・APIの挙動変更なし、コミット・プッシュ未実施。

- Codex 2026-10-05: HTools・連携・MayaCommandPortsを含む内製Pythonへdocstring整備を拡張。254関数の不足説明を補い、Slack/mGear・ウェイト処理の旧形式を日本語Google形式へ整理。534ファイルの構文とdocstring除外ASTの一致、差分チェック、Sphinxビルドを確認。実行コード・引数仕様は変更なし。Maya動作テスト・外部送信は未実行。テストへの定型docstring一括追加は行わず、外部submoduleと他エージェント作業中のFramePlayerは対象外（FramePlayerはユーザー回答待ち）。

- Codex 2026-10-05: mlib/mlib_*/hrigの本番316ファイルをdocstring監査。143メソッドの短縮戻り値説明をGoogle形式へ整理し、公開引数説明の不足・Shape取得条件・接続照会の返却型・Bifrostの生成/接続説明を修正。プロパティの型付き短文とMaya/Qt APIは維持。docstring除外ASTが全316ファイルで一致、公開引数説明の静的不足0件、差分・Sphinx警告なし。実行コード変更なしのためMaya動作テストは未実行。HToolsは今回対象外。

- Codex 2026-10-05: 角括弧統一後を再監査。mlib複合Plugの旧child利用は残存なし。ArrayPlug.elementの公開入口・実体化/存在検査テスト、およびmlib_bifrost Compound.child（内部ノード参照）は残存。Maya API/Qt childと区別して報告。実装変更なし、静的確認のみ。

- Codex 2026-10-05: ユーザー指示によりCompoundPlug.childを角括弧へ統一。番号・長短名・反復に対応し、mlib/hrig・safe処理・テスト・公開文書を移行。maya.cmdsへ複合Plugを渡す際はstr/fullNameを明示。Maya2022〜2027各8件、関連23スイート229件成功。478ファイル構文・差分・Sphinx確認済み。GUI未実行。Maya API/Qt/Bifrostノードのchildは別APIのため維持。

- Codex 2026-10-05: mlib/hrig/HTools本番335ファイルの配列アクセスを監査。element・内部参照メソッド・文字列内番号による通常アクセスを角括弧へ統一し、欠番の例外を維持。テスト例・公開ドキュメントも更新。低レベルAPI/明示実体化の契約テスト/複合childは維持。Maya2027で23スイート229件成功、最終変更の該当再検証・構文・差分・Sphinx成功。GUI/他バージョンは今回未実行。

- Codex 2026-10-05: Plug.setAlias/setKey/animLayers、DAG.instances/parents/幅優先・深さ優先走査を追加。Matrix.toTransformationはmlib値型返却に変更しMatrix/MatrixPlugへの入力も対応。配列[index]は未作成要素を非実体化で参照し反復は既存要素のみ。複合の子はcmds直接渡しを維持するためchildのまま。Maya2022〜2027各7件、2027既存関連236件が成功。Sphinx・構文・差分確認済み、GUI未実行。

- Claude Code (2026-10-05): VP9 Video Extensionsを入れて検証。VP9デコーダーは8bitでもP010を受け付け、読むとGPUでE_OUTOFMEMORY・CPUで停止したので、P010はmp4の設定ボックス(hvcC/vpcC/av1C)のビット数で10bitと分かったときだけ求めるよう修正。途中の形式変更(10bitのVP9)にも追従。vpcCの色情報も読む。VP9 3本を色の確認に追加し13本×GPU/CPU/縮小がすべて一致、コマ番号の確認も一致。mainへpush。

- Codex 2026-10-05: Transformation追加後のmlib/cymel利用者視点の残存差分を調査。配列番号・未作成要素・get戻り値・addAttr・Vectorの7操作をMaya2027 standaloneで比較。作成入口/未対応APIもソース確認しdocs/researchへ記録。実装変更なし、GUI未操作。

- Codex 2026-10-05: mlib.maths.TransformationとTransformのgetTransformation/setTransformation（getX/setX）を追加。TRS・補助回転・ピボット・SSCの保持、ws指定、Undo、safe/getとコレクションに対応。既存Matrix APIは維持。Maya2022〜2027で新規各11件、2027で既存105件が成功。構文・差分・Sphinx警告なしを確認。GUI未実行。

- Codex 2026-10-05: cymelに合わせhasAttr/parent/children/longName/delete/mnode/mpath等へ改名、Plug.node()・名前/enum・変換ノードを省略する接続照会・短縮Transformメソッド・フラグ操作を実装。利用側は直結探索を明示して挙動を維持。配列addElementは指定番号・リスト返却に統一（実体化Undoとmessageは未対応）。API設計・AGENTS参照先・ドキュメントを更新。Maya2027で530件、2022〜2026各6件、HTools変更前比較55件、Sphinx警告なし。GUI未実行。

- Codex 2026-10-05: mlib/cymelのNode・DAG・Transform・Plug中心にメソッド名/意味を比較。5項目をMaya2027 standaloneで実測し、docs/research/cymelMethodDifferences-2026-10-05.mdへ保存（Git対象外）。API変更なし。

- Codex 2026-10-05: AGENTS.mdへmlibの確定済み引数・既定値・単位・戻り値の変更禁止を追記。対象仕様へのユーザーの明示指示がある場合のみ変更可能とし、addAttrの既定Plug返却も明記。参照先と差分を確認（文書のみ）。

- Codex 2026-10-05: Node.addAttrの既定戻り値をPlugへ変更。利用側のgetPlug=Trueを整理し、複合アトリビュート内部は明示Falseで構築。仕様・例・テストを更新。Maya standalone 2027で78件、2022で7件成功、Sphinx警告なし。GUI未実行。

- Codex (2026-10-05): 調査したcymel差分をmlibへ反映。Plug.connectを入力元指定へ変更しconnectTo追加、disconnectは入力のみ、disconnectAllを明示化。force/f・lock/l・nextAvailable/na、safe、getu/setuを追加。Transformのat既定2、Quaternionのra/r/jo、getMatrixのp/inv、setterのget/safe、getScaling/setScaling/getShearing/setShearing、Node.addAttr(type/subType/子名/proxy/getPlug)・rename(ignoreShape)へ統一。既存呼出側はconnectTo・at=4・getPlug=True等へ移行し、Qt/Bifrostの別APIは保持。型・通常setterのself戻り値・行列の近いEuler解はmlib規則を維持し、setMatrix(get=True)は設定値dict。配列接続のロック探索・切断後のMPlug再解決とアニメーション付き行列更新も修正。Maya2027の54スイート406テスト、2022〜2026の各7テスト（計35）、HTools旧実装との55ケース比較が成功。Sphinx警告エラー扱いビルド・169コード例の構文・差分チェック成功。旧sceneコマンド廃止のテストは正式sceneパッケージと区別して修正。GUIは今回未実行。証跡.maya-output/cymel-alignment-summary.json。既存の未コミット変更とClaudeのhedit/hrig翻訳作業を保持。未コミット。

- Codex (2026-10-05): 同梱cymelと作業ツリーのmlibを利用者視点で比較。接続/切断方向、位置・回転の基準、safe/get/fast、単位・位置引数・短縮フラグの差を実装から確認。docs/research/cymelArgumentComparison.txtへ調査保存（Git対象外）。実装変更・Maya実行なし。

- Codex (2026-10-05): mlibのTransform/Shape/Mesh/NurbsCurve/PointComponent/DagPose/SkinClusterの空間引数をworldSpaceへ変更し、既存flag_aliasesでws対応。形状情報ノードのconnectCurve/connectSurfaceも統一。旧space/world_spaceキーワードの互換入口は残さず、HTools/hrig/テスト・設計書・RST例をws表記へ更新。resetPivot/restoreBindPose/形状接続のワールド既定は維持、OpenMaya直接APIのMSpaceは維持。Maya2027で29ファイル316テスト成功（各ファイルを独立プロセスで実行しreloadの干渉を回避）、HTools大型55ケース比較成功、Maya2022〜2026でも新規4テストずつ成功。RST Python例・変更Python構文・差分チェック成功。今回GUI/Sphinxビルドは未実行。既存大型ツール変更と途中で観測したscene/cycle.pyのimport変更を保持。証跡.maya-output/space-summary.jsonほか。未コミット。

- Codex (2026-10-05): HTools大型8モジュール（OBB2本・ジョイント方向・コントローラ形状・2影響帯スムージング・スキン複製・ウェイト統合・PBDベイク）のノード/Plug操作をmlibへ移行。OBB計算をutils.orientedBounds、隣接グラフをMesh.getVertexAdjacency、カーブ差し替えをhrig.ControlShape.replaceCurvesへ共通化。行列分解・skinPercent・コピー関連付け・時間/キー操作の既存挙動を維持。hrig.definitionの型注釈遅延で2022/2023 import対応。旧OBBのMPointArray解放後参照を点コピーで修正（baseline比較も所有権のみ補正）。Maya2022〜2027で各55ケース比較（21形状の新規/差し替え含む）と共有API検証成功、2022/2027専用GUIで度/radのJoint Orient・スキン保持・画面生成比較成功。definition4テストと構文/対象差分チェック成功。GUIの2023〜2026は未実行。全条件の同一性は未保証、cmds全面廃止ではない。証跡.maya-output/htools-large-*.txt・htools-large-gui/20261005_071155。調査メモとbaselineはGit対象外。heditの並行作業は変更せず保持。

- Codex (2026-10-05): ユーザー依頼のプッシュ対象を整理。HToolsのmlib移行、Aim/Container/DagContainer/CycleのAPIと関連テスト・説明をコミット対象として確認。heditの並行変更・調査資料・実行ログは除外。ステージ済み差分チェック成功。

- Codex (2026-10-05): Cycleの他バージョン検証。Maya2022〜2026それぞれstandaloneの7テスト成功（計35件）、専用GUIの空結果表示・保存・エラー復帰とシーンパス検証も各版成功、全プロセスexit 0。既存2027結果と合わせ2022〜2027で検証済み。コード修正なし、ユーザーシーン変更なし。証跡: .maya-output/cycle-versions/20261005_004108/summary.json、standalone各版ログ。

- Codex (2026-10-05): CycleCheckを廃止しmlib.scene.Cycleへ置換。findはlist[Cycle]、plugsはtuple[Plug]、getConnections/getParentsは現在の関係をmlib型で照会。HToolsが計測・文字列レポートを担当。旧入口なし。Maya2027 standaloneの7テストと専用GUIの表示/保存/エラー復帰を含む3項目が成功。差分確認済み。他バージョン未検証。

- Codex (2026-10-05): mlib.nodes.DagContainerを追加。TransformとContainerの操作を継承し、自動型解決・型公開・仕様を整備。Maya2027 standaloneで新規3件とContainer/型公開の計11テスト成功。所属解除時はMaya標準のローカル値保持（ワールド姿勢は変わり得る）を維持し、Undoによる階層/姿勢復元も確認。差分チェック成功。他バージョン・GUI未検証。

- Codex (2026-10-05): HTools移行第1段階として11ツールのノード/Plug操作・拘束・スキン照会・シェーダー/カーブ生成・シーンパスをmlibへ置換。サイクル照会をmlib.scene.CycleCheck.inspectへ移動（旧関数入口なし）。Plug.connectにunlock=Falseを追加しMaya標準のロック保持を維持。cymel依存をgetPivotで置換し従来の回転ピボット位置を保持。Maya2027で変更前スナップショットとの12ケース比較、サイクル5テスト、接続ロック1テスト、専用GUI3項目成功。構文/差分確認済み。大型ツールの未移行範囲とmlib/hrig候補をdocs/research/htoolsMigration.txtへ保存（Git対象外）。他バージョン・全HToolsの移行・全状況の同一性は未検証。既存変更と並行作業のhedit変更は保持。

- Codex (2026-10-05): ContainerへremoveMembers/removeContainer・公開名/Bind/解除/一覧APIを追加。removeContainer単独で未接続DGが消える2027の挙動を確認し、先に所属を外して保持。ScalarGraphへ生成関数注入を追加してNode/Plug操作へ整理。Aimの一時Containerを廃止しArrayPlugのmessage APIで記録/復元。Container5テスト（SoftIK含む）、Aim17テスト、専用GUI8項目が2027で成功。公開済みContainerをnamespace一括削除するとMayaが異常終了するテスト後片付けは、Containerの標準削除後にnamespaceを除去する手順へ修正。差分確認済み。他バージョン・Sphinx未検証。Black Box/ロック専用API・dagContainer・汎用NodeGraphは未追加。

- Codex (2026-10-04): AimConstraintにrotationConnections/settingPlugs/getOutputRotationとRest Rotate・Offsetのgetter/setterを追加。直接接続・設定列挙・角度照会をAim軸変換とUIから移譲し、保存形式・hrigの検証/復元責務を維持。setterは有限値・入力・ロック・参照を事前検証。Maya2027でmlib新規4テスト、Aim回帰17テスト、専用GUI8項目成功。差分チェック成功。他バージョン・Sphinx未検証、ユーザーシーン変更なし。

- Codex (2026-10-04): AimConstraint/Constraint実装を確認し、直接出力接続・標準設定Plug・Rest Rotate/Offset・評価出力の照会編集をAimConstraintへ移譲する案をcontainerDesign.txtへ追記。変換可否・保存方針・復元とグラフ構築はhrigに保持。実装変更・Maya実行なし。

- Codex (2026-10-04): 共有会話・Autodesk仕様・既存Container/ScalarGraph/ArrayPlug/Snapshot/hrig利用先を調査。Containerの所属解除・Publish/Bind拡充、ScalarGraphの生成関数注入、既存message API再利用を優先する設計案をdocs/research/containerDesign.txtへ保存（Git対象外）。生成物管理・単位境界・サイクル照会の候補とhrigに残す責務、移行・検証計画を整理。製品実装・Mayaシーン変更・新規実行テストなし。

- Codex (2026-10-04): Aim軸変換に「生成ノードをコンテナ化する」を追加。オフでは演算ノードから直接接続し、networkのmessage接続で復元情報と生成物を管理。構成切替・復元・Undo/Redo・改名・保存読込を含むMaya 2027の17テストと専用GUIの8項目が成功。GUI初回はライセンス初期化失敗、実行制限外で再実行して成功。他のMayaバージョンは未検証。

- Codex (2026-10-04): Aim軸変換・元Aim構造/設定の復元・サイクル調査ツールと関連テスト/説明を公開対象に確定。最終2027のAim15テスト・GUI6項目、サイクル5テスト・GUI成功記録を確認。調査メモと.maya-outputは除外し、差分確認後にコミット・プッシュする。Sphinxビルドは未実施。

- Codex (2026-10-04): ユーザー訂正に従い、Aimの補正付き復元を撤回。restore()は元Aimの直接接続・保存値を復元し、変換/補正ノードとcontainerを全削除。元Aimの未接続設定（Offset/Rest Rotate/Aim/Up/World Up/ウェイト等）を記録・復元し、旧形式の未記録値は推測せず保持。旧mode=restの補正も除去可能。UIを「元のAim構造・設定へ戻す」へ変更、README・hrig説明更新。2027で15テストと専用GUI6項目成功（ノード集合の完全復元・設定値・直接接続・旧補正削除を含む）。起動中Mayaへの再読込はport7002の接続拒否で未実施。ユーザーシーンへの復元操作も未実施。他バージョン・Sphinxは今回未検証。未コミット。

- Codex (2026-10-04): Aim軸変換の復元を、元Aim直結から初期Rest Rotate近傍の等価XYZを選ぶ補正付き追従へ変更（ユーザー回答に基づく）。初回Rest Rotateのスナップショットを方式切替で維持し、旧保存形式は元AimのRest Rotateから取得。内部切替用restore(stabilize=False)は従来の厳密な接続復元を保持。復元後も補正containerを残し、UI表示・README・hrig説明を更新。2027で15テストと専用GUI6項目成功（90度通過の追従、360度基準、旧形式、Undo等）。起動中シーンを読み取り確認後、実装・UIのみ再読込。ユーザーシーンへの復元操作・他バージョン・Sphinxビルドは未実施。未コミット。

- Codex (2026-10-04): hrig.setups.AimAxisConversionとHTools/rigging/convertAimAxesを追加。選択した既存AimをEuler等価解・1/2軸方向・軸別Twistの3方式で変換し、元接続復元と切替、Undo/Redo、message参照による改名・保存読込に対応。mlibのNode/Plug/Container/ScalarGraphを使用。参照・ロック・他入力・間接接続を拒否、validで範囲曖昧/特異点/回転順変更を診断。2027/2026各13テスト、2025先行11テスト成功。専用2027 GUIで3方式・設定再読込・復元・不正方向の6項目成功、スクリーンショットを目視確認（.maya-output/aim-axis-gui/20261004_222750）。起動中Mayaには画面のみ表示し、ユーザーシーンは未変換。README/hrig利用説明更新、構文・差分確認済み。Sphinxは利用可能pythonにモジュールがなくビルド未実施。2022〜2024・ユーザー実リグ・大規模性能は未検証。DAG込みcycleCheckは標準Aim自体も拘束対象の子にあるだけで候補を返すことを隔離検証で確認。元の循環接続の修復は本機能の対象外。未コミット。

- Codex (2026-10-04): Aimの1〜2軸出力ツールの方式を検討。共有会話本文・Autodesk仕様・hrig SwingTwist/ScalarGraph等を確認。Euler別解式をMaya2027 APIで6回転順×1000例検証し行列誤差1.79e-15未満。方法1はXYZ一組の別解選択後に軸抽出、方法2はヒンジ/首振り/Twistの動作定義が必要と整理。docs/research/aimAxisDecomposition.txtとProbe.py/jsonへローカル保存。方式・軸・可動域はユーザーへ質問中で製品実装は未着手、現在のMayaシーン変更なし。

- Codex (2026-10-04): HTools/rigging/inspectCycles.pyへサイクル原因調査UIを追加。Maya cycleCheckで全体・選択・名前指定を検索し、mlibのNode/Plugでノード型・直接接続を照会。DAG親子関係、経路別表示、ノード選択、UTF-8レポート保存に対応。READMEへ使用方法と検出制限を記載。Maya2027 standaloneで実DG/DAG循環・複数経路・循環なし・入力拒否の5テスト成功。起動中2027 GUIで生成・空結果・失敗復帰・保存を確認、画面画像を目視確認（.maya-output/cycle-inspector.png）。他バージョン・大規模実シーン・手動操作は未検証。2027でmlib.ObjectのDGノード名解決がnull MPlugを扱う問題を確認したため、本ツールはNode/getPlugを明示使用（mlib本体は未変更）。未コミット。

- Claude Code (2026-10-04): `WorkspaceLayout.captureDockingLayout/restoreDockingLayout/temporaryDockingLayout`を削除(ユーザー指示)。専用GUIでの調査で、cmds/melからworkspaceControlのドッキング先を照会する手段が無いことを確認(`workspaceControl -q -dockToMainWindow`はNone、`workspaceLayoutManager -parentWorkspaceControl`は空、`window -dockingLayout`/`-state`に含まれず復元しても戻らない、`saveAs`のJSONは現在の配置名を切り替えretain=Falseのドックを含まない、`floating=False`でも戻らない)。Qtを使えばできるがmlibはQt禁止のため不可。テストはモック2件を削除し、GUIテストをdock→undock→dockに変更、削除APIが無いことの確認を追加。docs(window_layouts.rst・mlib-api-design.md)とUiSnapshotのdocstringを更新。専用GUI unit 2022〜2027全passed(各99ファイル/941テスト、WindowGuiTest実行)、mayapy 2022〜2027全passed。未コミット。

- Claude Code (2026-10-04): 起動中Maya 2027でGUIテスト(visual 15件passed、GUI内run_all_tests 99ファイル)。GUI内でのみ失敗した3件を修正(test_cmds_interopのMEL `$tmp`がGUIでは文字列のグローバル変数、test_extensionsがGUIでは`sys.executable`=maya.exeを起動、test_hrig_bifrost_startupのバッチ判定未モック)。Maya未起動でもGUIテストできるよう`run_mlib_gui_versions.py`に`--suite all|unit|visual`(既定all)を追加し、新規`run_mlib_unit_gui_tests.py`で使い捨てGUI内にrun_all_tests一式(GUI専用ケース・test_scene_ui・test_window_layout含む)を実行。専用GUIは信頼済みプラグインの場所が未登録で警告ダイアログに止まるため、test_posedriverconnect_extensionはGUIで未登録ならskip(登録はしない)。2022〜2027でvisual全passed、unitは942テスト中`test_window_layout` 1件のみ失敗: `WorkspaceLayout.restoreDockingLayout()`が使う`window -dockingLayout`にworkspaceControlのドッキングが含まれず、浮動にしたウィンドウが戻らない(mlib本体の既存の問題。未修正)。mayapy 2022〜2027全passed。未コミット。

- Claude Code (2026-10-04): レビューの軽微な指摘3点を修正。docs/mlib-api-design.mdのimport群の並び(`import x`→`from x import`の各モジュール名順)と`__init__.py`の扱い(対象外は`mlib/__init__.py`のみ)を実態に合わせ、tools/check_mlib_layout.pyの`--fix`を内側のクラス(クラス内・関数内)にも対応(外側から深さ順)。docs/mlib-testing.mdに内側クラスと`--compare`が順序依存の変化を検出しない旨を追記。既存262ファイルは`--fix`で変更なし・違反0。mayapy 2022〜2027で全件passed。Copilotの整理と合わせてコミット・プッシュ。

- Claude Code (2026-10-04): CopilotのmlibPEP8レイアウト整理(170ファイル)をレビュー。HEADとのAST比較で関数・クラス本体・モジュール文は順序以外同一、モジュール/クラス本体の実行時参照・同名再束縛・dataclassフィールド順・説明コメントの付き先に変化なしを確認(削除コメントは区切り線のみ)。整形ツールの冪等性も確認。test_color.pyの`call.args`(Python3.8以降)を`call[0][0]`へ直し、mayapy 2022〜2027で全件passed(各98ファイル/933テスト)。GUI専用テスト(test_scene_ui等)はGUI未起動のため未実施。未コミット。

- GitHub Copilot (2026-10-04): mlib・mlib_bifrost・mlib_posedriverconnect(テスト除く170ファイル)をPEP8レイアウトへ整理。importをstdlib→maya→相対の3群・アルファベット順、`from maya import cmds`を`import maya.cmds as cmds`へ、定数・`__all__`をimport直後へ、クラス内を属性→`__init__`→特殊メソッド→classmethod→property→公開→非公開の順にしget/set対を隣接。名前・本文・デコレータ・docstringは不変(`tools/check_mlib_layout.py --compare`で確認)。規則をdocs/mlib-api-design.md・mlib-testing.mdへ追記し、検査・整形スクリプトtools/check_mlib_layout.pyを追加。mayapy 2022〜2027でrun_mlib_testsを実行し、2023〜2027はpassed(2027: 98ファイル/933テスト)。2022のtest_color.pyの1件はPython3.7に無い`mock.call.args`を使う既存テストの問題で今回の変更と無関係。GUIでのrun_all_tests.py・Bifrost/PoseDriverConnect実プラグインは未実施。未コミット。

- Codex (2026-10-04): ユーザー指示でQwen3-Coder30B・Llama3.3 70B・Qwen3-Coder-Next80Bを取得し、同一3問と再測定で回答・速度・メモリを比較。Python固定10例／組合せ1365例、Maya2027 standalone8条件で生成コードを検証。速度中央値185／2.14／41.2 token/s、Maya成功6／1／7件。回答全文・測定結果をdocs/research/localLlmComparison.mdとlocalLlmBenchmark/へローカル保存。終了時アンロード確認。Maya GUI併用・長文・費用削減額は未検証。他作業のmlib変更は保持。

- Codex (2026-10-03): ローカルLLM検討用にCPU・RAM・GPU・ディスク容量を読み取り確認。RTX3090Ti 24GB／RAM64GBを確認し、30B・70B・80B候補とMaya連携案をdocs/research/localLlmHardware.mdへローカル保存。モデル起動・ダウンロードなし。推論速度・Maya併用は未検証。

| Claude Code | 2026-10-03 | maya/modules/CharcoalEditor2.mod | 2023・2025のmllが2023/windows・2025/windowsに置かれたのでmodを確認。各版をmayapyでロードし、実際の版に合わせて2025=2.10.2・2027=2.8.1へ修正(2022/2023/2024=2.6.4、2026=2.7.6)。submoduleへのmll追加はsubmodule側で未コミット。 |

| Claude Code | 2026-10-03 | maya/modules/CharcoalEditor2.mod | 2023の項目を追加(2.6.4・2023/windows)。submoduleに2023用(と2025用)のmllが無いため、置くまでは2023ではロードできない。未コミット。 |

| Claude Code | 2026-10-03 | maya/inhouse/hedit Maya 2023対応・CLAUDE.md | hedit.mllを2023でビルド(警告0)、hedit.modに2023を追加、docs/README/撮影ツールの版の一覧に2023を追加。CLAUDE.mdの版の一覧・ツールセット(2023=v142)を更新し「2023未インストール」の記載を削除。2023でrun_tests・run_gui(全スイート)・run_startup・run_session・Sphinx -W 成功。未コミット。 |

| Claude Code | 2026-10-03 | maya/inhouse/hedit 出力欄のスクロール | 新しいログが表示されたら途中を見ていても必ず最下部へスクロール(選択範囲は保持)。テスト・usage/README/changelogを更新。5版ビルド警告0、run_tests 2024/2027・run_gui 2024/2027・output_format 2027・Sphinx -W 成功。未コミット。 |

- Codex (2026-10-03): ユーザー指示でGit除外対象外の残存変更を確認。.vscode/settings.jsonのWinAppKit CMake参照先をコミット・push。heditの2テストは内容差分がなくステージ操作で変更表示が解消。設定JSONと参照先の存在、差分チェックを確認。Mayaコード変更なし。

- Codex (2026-10-03): Maya2023対応とheditバイナリをコミット・push。HUDサブモジュールの2023バイナリを先行pushし親参照を更新。前回のmlib932テスト・GUI15件・hedit・追加Color9件・Sphinx成功記録と差分チェックを確認。既存のheditテスト変更と.vscodeは対象外。

- Codex (2026-10-03): Maya2023英語/日本語バッチと11個の.modを追加。Qt5.15のDebug参照補正とdevkitキャッシュ更新でHUD/heditの2023ビルド成功。両プラグイン・mGear・PoseDriverConnectのロード確認。2023のcolorIndex(0)照会を回避し、再生範囲Undo不可の既知制限を2023にも記載、GUIテストのSelection旧名を更新。mlib98ファイル932テストと追加Color9テスト、GUI15件、hedit単体/Maya/画面/専用GUI、Qt補正回帰、Sphinx警告なし成功。hrig/Bifrost拡張は2025以降向け、Charcoal/MetaHumanは2023バイナリなし。手動GUI操作・HUD描画・通常バッチからの起動は未検証。既存変更を保持、未コミット。

- Claude Code (2026-10-03): FramePlayerの色をニュートラルに正確再現。色情報(行列/範囲/色域/伝達関数/ビット数、mp4のcolrも自前で読む)を読み、Windowsの映像処理を通さず自前のHLSL(fxcで埋め込み)でYUV→RGB・縮小・色域変換・HDR(HDR画面は明るさそのまま、SDR画面はBT.2390で203cd/m²へ)・10bit(P010・scRGB出力)。右クリックで色の情報の表示と手動の指定。確認用動画の生成スクリプトとFramePlayerColorCheckで10本×SDR/HDR画面×GPU/CPU/縮小がすべて許容差内。実機のHDR画面での確認は未。mainへpush。

- Claude Code (2026-10-03): OpenRVを maya/external/openrv にsubmodule登録(浅いクローン)。色再現性の調査メモは docs/research/openrv_color.md(Git対象外)。mainへpush。

- Claude Code (2026-10-03): FramePlayerにMaya準拠のショートカット(Alt+V再生/停止・Alt+Shift+V範囲の最初へ・Esc停止・K+左ドラッグのスクラブ)とフルスクリーン(Ctrl+F・映像のダブルクリック・右クリックのメニュー、Escで戻る)を追加。実キー入力の自動操作で全項目を確認。mainへpush。

- Claude Code (2026-10-03): FramePlayerのVFR動画(Xbox Game Bar録画)のコマ落ちを修正。Video Processor MFTが色変換・縮小時に時刻を平均fpsの等間隔へ付け直し、約半数のコマが目次と照合できず捨てられていた。MF_XVP_DISABLE_FRCで変換を止めた。FramePlayerVerifyで対象動画693コマ(GPU/CPU・シーク含む)と縞の確認動画の不一致0。mainへpush。

- Codex (2026-10-03): パッケージ名汎用化の実装・拡張・Sphinx・回帰テストを公開対象として確定。差分チェックと前回のMaya5版・最終回帰3件・3名称Sphinxの成功記録を確認し、mainへコミット・push。他作業の変更は対象外。

- Codex (2026-10-03): コア内を相対import化し、拡張検出/reload/ロガーを実パッケージ名に追従。Bifrost/PoseDriverConnectは既知サフィックスを除いて接続先コアを解決。JSON形式・MLIB宣言は維持。Sphinxのタイトル/本文/API/継承図と生成物検査CLIを汎用化しpackage_names.rstに手順を追加。Maya5版全98ファイル成功（2022/24/25/26は930件、2027は931件）。最終3回帰テストは2022/2027成功：mlib/studio_libコピー、元名import禁止、Undo/fast/形状/JSON/拡張/reload、固定import検査、Sphinx変換。PoseDriverConnectの別名登録はSDKスタブによる検証。mlib/mlib/studio_libraryのSphinx -W、各482HTMLの資産検査/APIリンク存在確認、diff check成功。GUI・改名環境での実Bifrost/PoseDriverConnectプラグイン操作は未検証。未コミット・未push。詳細docs/research/packageNameImplementation.txt。

- Codex (2026-10-03): Sphinx本文10ページを実装/docstringと整合（space、cm、法線平均、Plug定義フラグ/要素実体化、数学型、BlendShapeエイリアス、JSON参照解決）。Sphinx -W成功、Python例164ブロックの構文確認、diff check成功。これまでの責務共通化・camelCase移行・利用側更新・docstringを合わせてmainへの公開対象とした。先行のMaya5版各929件成功を確認。今回の本文例のMaya実行/GUI確認は未実施。

- Codex (2026-10-03): mlib実装245ファイル・モジュール/クラス/関数/メソッドのdocstring 2,085件を抽出し、引数・旧名・戻り値を静的検査。実装との意味の照合により62ファイル145件を修正（法線平均、Plug有効性、数学型返却、単位、接続置換、JSON復元制限、旧名、引数説明）。全245ファイルでdocstring除外AST一致、引数照合指摘0、Sphinx -W成功、diff check成功。今回Maya内の動作・全使用例の実行は未実施。未コミット・未push。詳細docs/research/mlibDocstringResult.json。

- Codex (2026-10-03): mlib公開関数/メソッド/propertyの116種類の旧綴りをcamelCaseへ統一し、mlib_*・hrig・HTools・テスト・ドキュメントの使用側を更新。AGENTS/CLAUDE/API設計/開発ガイドへ命名例外・保持値/照会・単位/Undoのルールを明文化。旧名reload除去と保存キー維持の3テスト追加。Maya5版各929件失敗0(skip9/9/6/6/6)、hrig2027 47+69件成功、最終旧名除去3件成功、Sphinx -W成功・構文/差分確認済み。GUI実操作未検証、未コミット・未push。詳細docs/research/mlibCamelCaseImplementation.txt。

- Codex (2026-10-03): mlib全245 Pythonファイルの明示定義1,840件を静的棚卸しし、命名と処理内容を重点照合。法線API・Joint削除・型/回転順序の返却表現・UI作用範囲等を優先度別に整理。docs/research/mlibNamingAudit.txtへローカル保存（Git対象外）。既存テスト/Autodesk資料と静的照合、製品コード変更・Maya実行なし。

- Codex (2026-10-03): mlib責務委譲を実装。Plug書込み検証/値更新、ArrayPlug番号/編集用参照、geometryEditの単数・複数・Shape共通書込み、disconnectInput、hrig参照/単位委譲、JSON単位共有を整理。7テスト追加、Maya5版各926件失敗0(skip9/9/6/6/6)、2027hrig47+69成功、Sphinx -W成功・差分確認。2601点一括218.8ms対単数反復315.6ms、1点fast優位なし。GUI未実施、未コミット。詳細docs/research/mlibResponsibilityImplementation.txt。

- Codex (2026-10-03): mlibの責務・委譲・共通化を調査。Plug書込み、幾何編集、配列参照/作成、入力切断、呼出側の参照/単位往復、複合検証、JSON境界の7候補を実装から整理。所有クラスと段階別受入条件、共通化しない境界をdocs/research/mlibResponsibilityRefactoringPlan.txtへ保存（Git対象外）。本体変更・Maya実行なし。

- Codex (2026-10-03): mlibの追加om2移行13ファイルをコミット。並行作業でFramePlayerのステージが入り08b0ed4は混在コミットになり、分離作業中に別作業側からorigin/mainへ送信済み。リモートのmlib内容一致を確認し公開履歴を保持、ローカルも08b0ed4へ同期。既存作業ファイル保持。919テスト失敗0・6skip、コミット差分チェック成功。

- Codex (2026-10-03): AnimCurve.getInfinityをom2照会へ移行、setInfinity(fast=True)を追加。共通Plugバックエンドで通常Undo/fast直接更新を統一し、fast両側を更新前にロック・接続検証。全8型×5外挿方法を含む2テスト追加、5版各21件成功、2027全体919件・失敗0・6件skip。差分確認済み。GUI・性能計測・Sphinx未実施、未コミット。詳細docs/research/mlibOm2Infinity.txt。

- Codex (2026-10-03): Node.userAttributeNames/getExtraAttributesをom2定義列挙へ移行。複合配列を含むトップレベル一覧の失敗を修正し、配列を展開せず追加順を保持。4テスト追加、5版各73件成功、2027全体917件・失敗0・6件skip。100アトリビュートの名前列挙は限定計測0.899→0.304ms。GUI/Sphinx未実施、差分確認済み・未コミット。詳細はdocs/research/mlibOm2DynamicAttributes.txt。

- Codex (2026-10-03): mlib om2追加移行。scaleGeometryのom2一括照会・fast更新、aliasesのAPI照会、重み付きCVのワールド座標往復を修正。2022/2024/2025/2026各83件成功、2027全体913件・失敗0・6件skip。差分確認済み。GUI/性能計測は未実施。Sphinxは既存venvの実行元欠落・利用可能Pythonに依存なしのため未実行。未コミット。

- Codex (2026-10-03): プッシュ依頼対応。検証済みmlib om2リファクタリング・API単位/命名整理・hrig使用側移行・Bifrostロード状態判定修正と関連ドキュメントを送信対象に確定。FramePlayer作業中変更とdocs/researchのローカル調査メモは対象外。ステージ差分チェック成功。

- Codex (2026-10-03): Bifrost flowWedging失敗を調査。原因はサンドボックスによるLocalAppDataのFlowGraphEngineログ書込み拒否。承認済み通常権限でロード成功を確認。Plugin.loadにロード後の状態検証を追加し、例外なしの初期化失敗をRuntimeError／PluginPackageのload-failedとして扱う。回帰3テスト追加。Maya2025/2026/2027の全95ファイル・各908テスト失敗なし（GUI等6件スキップ）、Sphinx警告なし、差分チェック成功。セキュリティ設定・外部プラグインは未変更。GUI未実施、未コミット。ログは.maya-output/bifrost-load-verified/20261003_095921_758940。

- Codex (2026-10-03): mlibのコマンド層cmds基準／オブジェクト・数学層OpenMaya基準を実装。Plug・姿勢・座標・キーをcm/rad/秒へ統一、MSpace・lowerCamelCase・配列形・周期CV番号を整理。通常cmds Undo／fast om2の単位を共通化し、hrig使用側と移行文書を更新（旧別名なし）。Maya2022/2024は各905テスト失敗なし、2025/2026/2027は各905テスト中flowWedgingロード確認1件のみ失敗。GUI等は各6〜9件スキップ。hrig 47＋69テスト成功、257 Pythonファイル構文確認、Sphinx警告なし・差分チェック成功。GUI未実施、未コミット。詳細はdocs/research/mlibOm2PublicContract.txt。

- Codex (2026-10-03): om2優先リファクタリングを実装。Mesh/非周期CV取得、型付き配列読取り、JSON取得、表示色・スキン検証をAPI化し、fast配列作成/行列書込みのcmds往復を削減。単数Componentとベクトルadd_attributeの既知2件も修正。通常Undoと周期CV等の互換経路を維持。Maya2022全94ファイル900テスト成功、2027は既知のflowWedgingロード確認のみ失敗。2024/2025/2026は重点各38テスト失敗なし（GUI1スキップ）。Sphinx警告なし・差分チェック成功。2601頂点の公開取得は同条件の従来相当72〜74msから0.40〜0.57ms。詳細・計測はdocs/research/mlibOm2Implementation.txt。GUI未実施、未コミット。

- Codex (2026-10-03): mlibのom2優先方針で実装243ファイルを静的棚卸し（直接cmds呼出し472箇所・fast宣言122箇所）。共通基盤、座標取得、配列作成、JSON、スキン等を精読し、段階的移行計画とインベントリをdocs/researchへローカル保存。Maya2022/2027 standaloneの既存fast各8テスト成功、2601頂点取得の限定計測とfast中のgetAttr/接続境界を確認。本体変更・GUI検証・全テスト・コミットなし。

- Codex (2026-10-03): mlibリファクタリング計画相談のため設計規約・直近履歴・入力解決・add_attribute・JSON・初期化入口を確認。既知2件の修正、JSONの責務整理、初期化順序の明文化を候補化。実装変更・Maya実行なし。

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

- 2026-10-03 Claude Code: FramePlayerをmaya/inhouse/FramePlayer/へ移し、mlibに依存しない単体パッケージ化(exeはパッケージ直下、Maya側はpython/frameplayer、maya/modules/FramePlayer.mod、単体用FramePlayer.mod、HTools/animation/framePlayerSync.pyは入口のみ)。Mayaのタイムスライダーと双方向連携(FramePlayerが127.0.0.1:7010で待ち受け、frame/range/play/stop/stateを1行命令でやり取り、受け取った変化は両側で送り返さない、ずらし・倍率・範囲同期)。Maya 2026で双方向・再生追従・ずらし・切断を確認(確認後に終了)。同期の遅れを両側の時刻記録で実測(コマ送り→表示1.5ms、FP→Maya反映6〜35msはMayaの計算分、再生追従は24fpsで100%・遅れ0コマ、重い60fpsでも遅れ最大2コマ)。接続直後にFramePlayerの古い範囲でMayaを上書きする不具合を修正。FRAMEPLAYER_SYNC_LOGで時刻記録。CLAUDE.mdの構成に追記。タイムスライダーのMaya風構造と合わせてコミット・push済み(c9cde6d)。

- 2026-10-03 Claude Code: FramePlayerのタイムスライダーをMayaと同じ構造に変更(上段=再生範囲の目盛り・現在フレームの区画と番号・現在フレーム欄・再生ボタン、下段=開始フレーム欄・つまみ付きレンジバー・終了フレーム欄)。開始フレーム(既定1、設定StartFrame)、再生範囲(I/O・つまみ・ドラッグ・ダブルクリックで全体切替、範囲内ループと先読み)、Alt+,/.、Maya連携の窓口TimeSyncを追加。Maya 2026を起動して同条件のキャプチャで比較(確認後に終了)。release/のexe更新。未コミット。

- 2026-10-03 Claude Code: FramePlayerを軽量化。キャッシュ上限を1GB・30秒分・GPU予算の1/4・主メモリ不足時256MBの最小に(設定CacheMB/CacheSeconds)、再生中は変化時だけ描画しPresent(0)で空回り解消(画面合成が4Hzの環境で1コア→全体0.4%)、背面は前後2秒だけ先読み+低優先度/EcoQoS、最小化30秒/背面5分で休止(キャッシュとデコーダー解放)、キーフレームの縮小画像(幅320・RGB565・160MBまで)で仮表示。720p60・5分でGPUメモリ8.6GB→約1GB。確認用ツールに--thumbnailsを追加し全一致。コミット・push済み。

- 2026-10-03 Claude Code: FramePlayerの色合いをWindows 11の「メディア プレーヤー」に合わせた(Storeから導入して同じ動画を再生・キャプチャし画素を実測。地・タイトルバー#141414、バー#949494、強調#FF8232)。タイトルバーをDWMでダーク化、文字をSegoe UI Variableに。Keyframe Pro風UI・スライダー修正と合わせてコミット・push済み(15ac0b6)。

- 2026-10-03 Claude Code: FramePlayerの操作部をKeyframe Pro風に変更(映像下にスライダーの行=細い帯・現在コマ番号・総コマ数・fps(コマ落ち・ずらしの表示は削除し帯を右端近くまで延長)、下段に左ファイル/比較・中央の先頭/戻る/再生/進む/末尾・右に三角形の音量)。スライダー操作時にキャッシュ帯と現在コマ表示が行ったり来たりする問題を修正(ドラッグ中は前後対称に先読み、停止中の古い表示通知でUIを戻さない)。メッセージ送信+PrintWindowの連続キャプチャで確認。release/のexe更新。未コミット。

- 2026-10-03 Claude Code: FramePlayerの操作部左端に「ファイル」ボタンとメニュー(動画を開く/比較する動画を開く/比較を終了/最近使ったファイル(8件、HKCUのRecentFilesに保存、一覧を消去)/終了)を追加。メニュー項目と有効・無効を外から読み取って確認。release/のexe更新。未コミット。

- Codex (2026-10-02): 未コミット変更全体のコミット対象を確認。mlib構成/入力解決/拡張リロード、hrig利用側、文書/テスト/規約の223ファイル。生成物・外部調査ログなし。直近のMaya2022/2027各36テストとSphinx成功を確認し、末尾空行を整備。mainへコミット・pushを実行（結果はチャットで報告）。

- Codex (2026-10-02): 拡張のimport試行名を追跡し、親の初期化失敗後に残った子モジュールも次のreloadで一括解除。利用可否確認後に依存ソースを検証し、unavailableな拡張の非対応構文を解析しないよう修正。修正後初回reload/探索パス削除/利用可能時の構文検証の回帰テスト追加。Maya2022/2027は関連5ファイル各36テスト＋コマンド再読み込みスクリプト成功。Sphinx警告なし、対象差分チェック成功。GUI/他バージョン未実施、未push。

- 2026-10-02 Claude Code: FramePlayerに2画面比較(段階C)を追加。右半分へのドロップ・2ファイル同時ドロップ・「比較」ボタン/Ctrl+Shift+Oのファイル選択・起動引数で2本目を開く。コマ番号で同期し[ ]でずらし、範囲外は表示で知らせる。再生は両方のコマがそろってから進める。比較中は消音、キャッシュは半分ずつ(Clip::setCacheLimit)。メッセージ送信で表示・同期・ずらし・再生・終了・ファイル選択画面を確認(実際のドラッグ操作は未確認)。release/のexe更新。未コミット。

- Codex (2026-10-02): 拡張リロードを追加レビュー。Maya2022/2027で初期化例外後の孤立サブモジュールが残り、修正後最初のreloadでも古いconfig値を使うことを再現。Maya2022で利用不可の拡張も全ソース先行解析により新Python構文でerrorになることを再現（2027ではunavailable）。実装変更なし。

- Codex (2026-10-02): mlib.reloadで宣言済み拡張を先に一括解除し、本体再読み込み後に再検出・登録するよう変更。他拡張への静的import/ラッパー継承を拒否、初期化中reloadを拒否。Bifrostは宣言先行・サブパッケージ遅延importへ。Maya2022/2027の関連5ファイル各34テスト＋コマンド追加変更削除スクリプト成功、先行importの新規プロセス検証成功。Sphinx警告なし。GUI/他バージョン未実施、未push。Componentとadd_attributeの2項目は修正予定のまま。

- 2026-10-02 Claude Code: FramePlayerのタイムスライダーを、再生中に触ったらドラッグ中はそのコマを表示し、離したらその位置から再生を続けるよう変更(YouTube同様)。停止中は停止のまま。release/のexeを更新。未コミット。

- 2026-10-02 Claude Code: FramePlayerに音声再生(MF+WASAPI、映像を音声位置に同期・差±0.03ms)と音量UI(スピーカー/スライダー/M・↑↓、HKCUに保存)を追加。続けてキャッシュをGPUメモリ(NV12)へ移行(GpuDevice共有、D2Dで直接描画、予算の半分・最大8GB)。720pで約4600コマ保持・主メモリ約200MB。確認用ツール12通り全一致。デコード中にGPUの鍵を持つとデッドロックするため鍵は自前の写しと描画だけに限定。未コミット。

- Codex (2026-10-02): mlibの依存関係を追加レビュー。Maya2027 standaloneで拡張先行importの誤判定・拡張間継承のクラス不一致を再現。mlib本体2回reload後のモジュール直下クラス参照/直接基底に旧クラスなし。前回2件と計4件を修正予定へ記録。実装変更・GUI確認・全バージョン実行なし。

- Codex (2026-10-02): mlib参照構造変更後を追加レビュー。Maya2027 standaloneで単数Component解決が441要素生成後に範囲拒否すること、vector add_attributeのquery/edit共通検証漏れを確認。実装変更なし。

- Codex (2026-10-02): Objectへ汎用入力展開、Nodesへ展開済み列の混在検査を分配。Node.add_attributeからcmds逆参照を除き、addAttrはNode共通実装へ委譲。executeDeferredはDeferred.callへ委譲。_core.collectionのNodes参照を削除し実行方針をNodes._dispatch_sharedへ移動。公開API/Undo/独自call_eachを維持。Maya 2022全93ファイル成功、2027は既知のflowWedgingロード確認のみ失敗。追加を含む重点40テストは両版成功。Sphinx警告なし・差分チェック成功。GUI未実施、未push。

- Codex (2026-10-02): mlib実装243 Pythonファイルのimport・主要呼出しを静的レビュー。Object/Nodes間の入力処理、Node.add_attributeとDeferred.callのcmds依存、_core.collectionのNodes参照、root一括初期化を設計上の改善候補として整理。Node/Plug等の必要な相互参照と区別。実装変更・Maya再実行なし。

- Codex (2026-10-02): mlib/mlib_bifrost/mlib_posedriverconnectの公開別名、転送専用モジュール、動的属性、JSON読替え、フォールバックを追加監査。追加削除対象の旧互換入口は見つからず。現行の短縮フラグ・Mayaアトリビュートアクセス・任意拡張判定・リロード時の廃止名削除は維持。Maya 2027の関連5ファイル38テストは失敗なし（GUI1件スキップ）。実装変更なし、作業記録のみ更新。

- 2026-10-02 Claude Code: FramePlayerの映像をVideoView(子ウィンドウ+描画専用スレッド、D3D11+Direct2D、垂直同期)で表示するよう変更。再生の時間管理も描画スレッドへ移し、再生中は画面消灯を抑止。操作(コマ送り・スライダー・再生・終了)と番号一致を確認。リモートデスクトップ(画面32Hz)では24fpsのコマ落ち0、60fpsは画面の書き換え回数の上限で約半分落ちる。ローカル画面での60fps測定は未。CLAUDE.md/AGENTS.md/copilot-instructionsの日本語報告ルールを具体化。未コミット。

- Codex (2026-10-02): mlibと拡張の旧API互換を調査。Matrixのrotation引数/プロパティ・decomposeの重複rotationキー・_wrap_copy・to_mmatrix、SkinClusterのsinusoidal、JSONのTranslate/Rotate旧型タグ変換を削除。利用例と回帰テスト更新。短縮フラグ・Maya型変換・基底インターフェース・廃止名除去処理は維持。Maya 2022全93ファイル884テスト成功、2027は既知のflowWedgingロード確認のみ失敗。Sphinx警告なし、差分チェック成功。GUI未実施・未push。

- Codex (2026-10-02): generalをscene/ui/environment/eventsへ分割し、mlib_bifrostの導入管理もenvironmentへ移動。ObjectをNode/Plug/Componentの共通基底・種類判別入口として追加、coerceを削除して各基底に入力解決を集約。内製利用側、Sphinx、開発規約を更新。Maya 2022/2024は全93ファイル成功、2025/2026/2027は92/93成功（各883テスト、GUI等6〜9スキップ）。残る失敗はflowWedgingのロード確認（2027では変更前から記録あり）。hrig/Bifrost追加18テスト成功。Sphinx警告なし、差分チェック成功。GUI実操作・pushは未実施。

- 2026-10-02 Claude Code: FramePlayer高速化。GPU(D3D11)でデコード・色変換・縮小し4コマ先まで並行処理(4K60 80Mbpsで57→約200コマ/秒)、mp4/movのサンプルテーブル直読で目次作成(1時間36GBで開く約1秒)、キャッシュ解放をロック外へ、キャッシュ帯の計算を間引き。確認用ツールで全テスト動画の順・逆・ランダム一致。再生中のコマ落ちは現在のPC負荷由来(旧版・Keyframe Proも同条件で落ちる)。36GB検証ファイルは削除。未コミット。

- Codex (2026-10-02): 全体の責務を再確認。JSON保存形式とシーン更新の境界、SkinCluster保存経路、入力解決、テスト分離を優先する段階案を整理。便利API・数学型・登録機構は維持。実装変更・テスト実行なし。

- Codex (2026-10-02): 計算ノード21ファイルの値検証・設定41か所と接続45か所を既存_Calculationへ集約。公開signature・Undo・fast・戻り値を維持。Deferred.callはexecuteDeferredへ委譲しJSONは維持。Maya 2024全92ファイル成功、2027は91/92（Bifrost起動テストでflowWedgingのloaded確認が失敗）。追加回帰テスト成功、Sphinx警告なし。GUI未検証。

- 2026-10-02 Claude Code: FramePlayerを先読みキャッシュ方式へ移行(段階A)。デコードせずに表示時刻の目次を作り、デコード結果を目次と照合して番号を確定。上限4GBのキャッシュと再生ヘッド周辺の裏読み込み、スライダーにキャッシュ帯。確認用ツールで順・逆・ランダム×キャッシュ4GB/64MBの全コマ一致、7200コマ動画も一致・開く0.24s。未コミット。

- Codex (2026-10-02): nodesの単純Plug転送を静的調査。直接getを返す68メソッド、connect後selfを返す49メソッドを候補抽出。計算ノード中心の削減案と、配列生成・値検証・型変換・戻り値を維持する注意点を提示。実装変更・Maya実行なし。

- Codex (2026-10-02): mlibのクラス削減候補を実装・内製利用箇所から確認。標準API転送のみのクラス整理、状態を持たない計算クラスの関数化、所有権管理型の維持を提案。実装変更・Maya実行なし。

- Codex (2026-10-02): BulkCollectionを削除し、反復・一括実行・事前検証・Undo・signature共有をNodesへ移動。派生call_eachの委譲と既存sliceを維持。Maya 2024全92ファイル・876テスト（GUI等9スキップ）成功、Sphinx警告なし。

- 2026-10-02 Claude Code: FramePlayerに配布用exeのインストール手順(cmake --install → apps/FramePlayer/release/)を追加し、exeをコミット・push済み(faebb0a)。mlibの他の未コミット変更はユーザー指示によりpush対象外。

- Codex (2026-10-02): Plugins/Colors/DrivenKeysを削除。Plugin.loaded・DrivenKey.find・複数ノード色取得をlist化、利用側とドキュメント更新。Maya 2024全92ファイル成功、Sphinx警告なし。BulkCollectionはNodesへ一括実行機能を移して削除可能と確認し、今回は維持。

- 2026-10-02 Codex: 基底クラスによる共通化を検討。既存BulkCollectionへの重複集約、Maya継承に沿うGeometryFilter系、UI内部参照基底の候補と適用境界を確認。製品変更・Maya実行なし。

- 2026-10-02 Codex: mlibの不要処理を静的調査。製品231ファイル（init等除外）のAST・内製使用側・テスト参照から削除/統合候補と動的登録等の維持対象を区別。詳細はGit対象外docs/researchに保存。製品コード変更・Maya実行なし。

- 2026-10-02 Claude Code: FramePlayerにタイムスライダー(クリック/ドラッグ・目盛り)と再生ボタン(Space)、ループ再生を追加。高精度タイマーのスレッドでコマ境目に合わせて進め、再生中は簡易拡大縮小で描画。24/29.97fpsはコマ落ち0、60fpsは8秒で2コマ。操作はウィンドウへのメッセージ送信で確認。未コミット。

- 2026-10-01 Codex: mlib内部の責務を整理。SkinCluster検索共通化・DAG解決再利用、用途別Snapshotへの取得/検証/適用移動、Plug型読取/fast数値書込の定義共有、Bulkのsignature検証共有、bootstrap登録構築共通化とreload探索キャッシュ無効化。公開API/JSON形式/継承/部分失敗契約を維持。新規5テスト、5版対象134件（GUI1skip）成功、最終数値経路13件を5版再確認、2024全体92ファイル880件（9skip）成功。Sphinx -W成功、速度比較はほぼ同水準（詳細Git対象外）。GUI未実行・未コミット・未push。

- 2026-10-01 Claude Code: 単独動画プレイヤーapps/FramePlayer/(C++/Media Foundation/Win32、外部ライブラリなし)の段階1を新規作成。全コマ先読み方式で←→コマ送り、確認用ツールFramePlayerVerifyでH.264(Bフレーム・長GOP・mp4/mov)とMJPEGの全コマ一致を確認。GUIはキー操作とウィンドウ描画を確認。未コミット。

- 2026-10-01 Codex: mlibの共通基盤・Node/Plug・SkinCluster・JSONを読み取り確認し、既存API/継承/速度を維持する段階的リファクタリング計画を提示。製品コード変更・Maya実行なし。前回push済みの進行中行を解消。他ツールのapps作業は保持。

- 2026-10-01 Codex: 全未コミット変更の公開準備。mlib速度改善・回帰テスト・ドキュメントと既存作業ログをまとめて差分確認。検証済み結果を維持し、Git対象外の調査・生成物は除外。

- 2026-10-01 Claude Code: hrigフェイシャルモジュラーリグ（MetaHuman型・ゲームエンジン向け）の設計ドラフトをGit対象外docs/research/hrig-facial-design-20261001.mdに作成。製品コードは未変更。

- 2026-10-01 Codex: 追加最適化を実装。同一引数一括呼出の実関数別検証共有・不要結果配列削除、Node.plugのfunction set再利用、fast行列の直接MPlug更新、短縮フラグの入力形検証キャッシュ、influence検索表共有。ウェイト範囲書込は失敗時挙動が違うため逐次更新を維持。新規テストの失敗検出とPython3.7 Mock互換も修正。最終関連227件は2022/2024/2025/2026/2027成功、2024全体91ファイル875件（9skip）成功、Sphinx -W成功。再計測はGit対象外docs/research保存。GUI未検証・未コミット・未push。

- 2026-10-01 Codex: 追加の速度改善候補をコード調査。検討資料はGit対象外docs/researchに保存。既存の未コミット実装は保持し、新規の製品変更・再計測なし。

- 2026-10-01 Codex: mlib速度改善4項目を実装。keyword-only fastのbind省略と状態変更抑制、world行列のDAGパス取得、通常Undoの重複チャンク省略（transaction境界維持）、fastWriteの更新内function set共有。Maya2022/2024/2025/2026/2027で関連180件ずつ成功。2024全体90ファイル成功・870件実行（9skip）、Sphinx -W成功。再計測はGit対象外docs/researchに保存。GUI未検証、未コミット・未push。

- 2026-10-01 Codex: 速度改善候補を専用Mayaでプロファイル・試作比較し、検討資料をGit対象外docs/researchに保存。製品コードは未変更。

- 2026-10-01 Codex: 依頼された速度比較を専用Maya standaloneで実測し、値一致・Undo復元を検証。詳細と再現スクリプトはGit対象外のdocs/research内に保存。製品コード変更なし。

| Claude Code | 2026-10-01 | maya/inhouse/hedit 0.3.0 設計の見直し | 設計レビュー15件に対応(固定の出力先・自己ロードの廃止・アイコンのメモリ描画・meta_path位置・版情報/CFG/PDB・heditTest分離・状態の明示的な作成と破棄・Request/SymbolType・言語の列挙・エスケープ統一・CodeAssist分離・__file__・tabs/<id>.txtとpreferences.jsonとui.jsonの整理・Python例外の受け止め・出力取り込みの代替・ui_smokeの名前付き検査・.gitattributes)。5版ビルド警告0、run_tests/run_startup 5版・run_gui 2024/2027と各スイート・run_session 2024/2027・Sphinx -W 成功。 |

- 2026-10-01 Codex: ユーザーのpush依頼に基づき、mlib設計修正・Qt依存除去・関連hrig/テスト/ドキュメント/開発規則を公開対象として確認。差分検査と直近の対象テスト・Sphinx成功を確認。GUI未検証と既知の互換制限は上記作業記録のとおり。

- 2026-10-01 Codex: mlibのQt依存を除去。Window/WorkspaceControlの寿命をMaya API 2.0 MUiMessage削除通知で共有監視し、最終参照解放で解除。MainWindow.widgetを削除しhrig LayerEditorでQtのトップレベルUIから親を取得。テスト内のQt importも削除、再混入のAST検査を追加。AGENTS/CLAUDE/Copilotと設計・Sphinxへ方針を記載。2022/2027でmlib対象19件中16成功・GUI3skip（削除通知はmock）、hrig対象13件は2027成功。hrig2022は既存のPython3.10+型注釈でimport不可。Sphinx -Wと差分検査成功。実GUI削除通知・hrig親表示は未検証。未コミット・未push。

- 2026-10-01 Codex: mlib設計5項目を修正。ConstraintをTransform派生、表示APIをDagNode/DagNodesへ移動。一括公開を明示宣言化し更新は自身を返す。単位setterからsave除去、他の保存要求はbatchで変更前検証。UI参照はQt実体の寿命を検証しUiSnapshotで退避、配置APIはドッキング範囲を名称へ明示。関連テスト・Sphinx・設計基準更新。全体2022は88ファイル成功、2027は既知flowWedging失敗のみ。追加の対象テストは両版成功（実Qt削除検知含む）。Sphinx -W成功。専用GUIは2027ライセンス初期化失敗、2024起動100秒timeoutで所有プロセス終了、実ドッキング復元未検証。未コミット・未push。

| Claude Code | 2026-10-01 | maya/inhouse/hedit 設計レビュー(コード変更なし) | 配布・起動、画面スレッドでのPython同期呼出し、出力取り込みのMaya内部依存、自動保存の全書き直し、状態ファイル3種、グローバル状態、補完エンジンの型などを洗い出し、docs/research/hedit-design-review-20261001.md に記録。 |

- 2026-10-01 Codex: mlibのクラス設計をレビュー。継承・基底責務・複数形API・保存契約・UI参照寿命を確認。Maya 2027 standaloneでconstraintの実際の継承を照会。実装変更なし。

| Claude Code | 2026-10-01 | maya/inhouse/hedit ホバー | 名前にマウスを重ねる/Ctrl+K→Ctrl+Iで定義の見出しとdocstringを出すホバーを追加(core/docstrings・宣言の抽出・CompletionEngine::describe・bridge.describe・HoverPopup・hedit -describe)。tests/output_format_smoke.pyの末尾一致をMayaの遅延出力に強い判定へ修正。5版ビルド警告0、run_tests 5版・run_gui 2024/2027(+補完/整形/出力スイート)・run_session・run_startup・Sphinx -W 成功。未コミット。 |

- Codex (2026-10-01): mlibのノード/プラグ拡張・Preferences・Shelf・ウィンドウAPIと関連ドキュメント、hrigの単位API移行を公開コミット対象として確認。heditの進行中変更を除外。直近Sphinx -Wと対象テスト結果を確認し差分チェック成功。既知のBifrostテスト失敗・実GUI未検証は各作業記録のとおり。

- Codex (2026-10-01): generalにWindow/WorkspaceControl/WorkspaceLayout、共通内部基底と取得コマンドを追加。表示/位置/サイズ・ドッキング・全体ロック・名前付き保存/切替・同一配置内メモリ退避/例外時復元を実装。使用ガイドと専用GUIテスト追加。2022/2027各15件中13成功/GUI2skip（UI呼出はmock）、Sphinx -W成功。専用2024 GUIは起動120秒timeoutで所有プロセス終了、実UI保存復元未検証。未push。

- Codex (2026-10-01): Mayaウィンドウ設計を公式資料・標準MEL・既存mlibから調査。概念別クラスと一時退避/永続保存の区別を提案。調査メモはGit除外のdocs/research。実装変更・GUI実行・pushなし。

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

| Codex | 2026-09-30 | 通常visibility・未コミット公開準備 | get/set_visibilityをNodeへ集約。通常/アウトライナーの独立性とUndo検証成功。Maya2027全804ケース・80ファイル中79成功、既存Bifrost起動テストflowWedgingロード確認1件失敗。Sphinx -W成功。依頼済み全mlib変更をコミット/push対象に整理。GUI未検証。 |

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

| Codex | 2026-09-30 | Sphinx表示調整の公開準備 | mlib数学型図の横並び維持・幅追従、hrig/hedit寸法統一の5ファイルを確認。diff成功、既存ビルド検証を継続採用してmainへのコミット対象を確定。 |

| Codex | 2026-09-30 | hrig/hedit docsレイアウト | heditの独立CSSをmlibと同寸法へ更新、hrigは既存CSS共有を確認。全体1200/目次240/間隔28px・960px以下1列。両Sphinx -W成功、生成CSSのハッシュ一致・diff検査成功。ブラウザー目視/プッシュ未実施。 |

| Codex | 2026-09-30 | mlib数学型図の配置 | ユーザー指示で元のTBへ戻し4枝を横並びに維持。objectラベルと親幅追従は保持。ソース・diff確認済み、配置1行変更のみで再ビルド/プッシュ未実施。 |

| Codex | 2026-09-30 | mlib数学型図 | object（Python組み込み）へ表示変更。数学型図はLR配置で枝を縦に並べ、専用mermaid-fit指定で親幅以下へ追従。既存リンク維持。Sphinx -W・JS構文・diff検査成功。ブラウザー目視/プッシュ未実施。 |

| Codex | 2026-09-30 | mlib docsレイアウト公開準備 | CSSと作業ログの2ファイルを確認。diff検査成功、前回Sphinx -W成功を継続採用してmainへのコミット対象を確定。 |

| Codex | 2026-09-30 | mlib docsレイアウト | 全体1200px・右目次240px・列間28pxのGridへ変更し本文800px制限を解消。960px以下は1列、表/コード横スクロール・印刷対応。Sphinx -W・diff検査成功。ローカル表示のブラウザー制限があるため修正版目視未実施、未プッシュ。 |

| Codex | 2026-09-30 | mlib公開ページのレイアウト確認 | フルページ撮影を.maya-outputへ保存。本文max-width 800pxと外枠1600px/右固定メニューの組合せで余白が生じると確認。CSS修正・プッシュなし。 |

| Codex | 2026-09-30 | 数学型図の公開準備 | object→OpenMaya→mlibの図と公式リンクの2ファイル差分を確認。前回Maya2027継承確認・Sphinx成功を継続採用し、mainへのコミット対象を確定。 |

| Codex | 2026-09-30 | mlib docs数学型図 | Python組み込みobjectを共通の頂点としてOpenMaya4型→mlib4型の継承を接続。Maya2027 mayapyで4型の直接基底objectを確認、Sphinx -W・diff検査成功。プッシュ未実施。 |

| Codex | 2026-09-30 | mlib docs数学型の図 | OpenMaya MMatrix/MQuaternion/MEulerRotation/MVectorからの直接継承を図示しAutodesk Python API 2.0の公式リンク追加。4型の実装照合・公式ページ確認・Sphinx -W・diff検査成功。ブラウザー描画とプッシュは未実施。 |

| Codex | 2026-09-30 | mlib概要クラス図の公開準備 | 要約版クラス図と作業ログの2ファイルを確認。diff検査成功、前回の継承・リンク・Sphinx検証を継続採用しコミット対象を確定。 |

| Codex | 2026-09-30 | mlib docs/whymlib | 概要ページの全135クラス図と文字ツリーを、ノード/Plug/コンポーネント/数学型の23代表クラス・4図へ要約。継承とリンク全件・Sphinx -W確認成功。修正版ブラウザー目視・プッシュ未実施。 |

| Codex | 2026-09-30 | mlib docs概要・クラス図の公開準備 | 4ファイルの差分検査を実施。前回Sphinx -W・135クラス網羅・リンク検証成功を確認し、mainへのコミット・プッシュ対象を確定。 |

| Codex | 2026-09-30 | mlib docs概要・クラス図 | PyMELのようにノードをオブジェクトとして扱う説明へ変更。公開図の横幅13587px・空白表示を確認し8分類のLR図へ分割。135クラス網羅・リンク先全件存在・Sphinx -W成功。ローカルURLはブラウザー制限のため修正版目視未確認、未プッシュ。 |

| Codex | 2026-09-30 | mlib説明・用語統一の公開準備 | なぜmlibの説明、アトリビュート表記統一、コンポーネント具体例をコミット対象として確認。最新Sphinx -W・diff検査成功。Mayaテストは前回2027全75ファイル成功を継続採用。 |

| Codex | 2026-09-30 | mlib docs/components説明 | ユーザー指示によりUnityへの言及3箇所を削除。Mayaの形状要素と具体例の説明を維持。残存検索・差分検査済み。文言削除のみのためビルド再実行なし。 |

| Codex | 2026-09-30 | mlib docs/components説明 | 概要・形状ガイド・API説明にコンポーネント（頂点・エッジ・フェース・CV・UV）とUnityとの概念の違いを明記。Sphinx -W・diff検査成功。説明のみの変更、Maya実行/公開なし。 |

| Codex | 2026-09-30 | mlib全体・関連規約 | 日本語表記をアトリビュートへ統一。docstring/コメント/メッセージ/テスト/Sphinxと3種ガイドを更新。対象ソース残存0・AST確認、2027全75ファイル成功、Sphinx -W成功。他版再実行/公開なし。 |

| Codex | 2026-09-30 | mlib/docs/whymlib.rst | なぜmlibを説明資料へ拡充。主要/全体クラス図、設計・Node/Plug操作・行列/Quaternion例を掲載。2027で6例と行列復元/中間回転成功、Sphinx -W成功。GUI目視/Pages公開は未実施。 |

| Codex | 2026-09-30 | 本体未コミット全変更 | ユーザー依頼の全本体変更をコミット・プッシュ対象に整理。diff検査とrunner5テスト成功。Maya全テストは再実行なし。第三者リポジトリSIWeightEditorの2ファイル変更と外部Pythonキャッシュは保持・対象外。 |

| Claude Code | 2026-09-30 | maya/inhouse/hedit docs・docstring | Sphinxの各ページを実装と突き合わせて修正(メニュー順・Explorerの表示対象・Zoomの反映先・補完の上限・検索バーのobjectName・構成図など)。同梱Python・userSetup・テストの入口のdocstringをGoogle形式で実装に合わせた。5版ビルド警告0、run_tests 5版・run_gui 2027・Sphinx -W 成功。検索バーのVS Code対応と合わせてコミット・プッシュ。 |

| Codex | 2026-09-30 | mlib残件・runner・tests/docs | Undo/ScriptJobs/JSON二次障害対応、公開名衝突・拡張登録復旧、FBX子環境・件数/skip理由、signature呼出内共有を実装。入力/fast表とPlug低水準入口の維持を記載。5版各75ファイル785件成功、最終Undo保護は5版関連再実行成功、runner5件/discovery/Sphinx -W成功。GUI未実施、未コミット。 |

| Codex | 2026-09-30 | mlib残件整理 | 計画と実装を照合し未反映6項目・一部反映・撤回/維持をresearchへ整理。実装変更/テスト再実行なし。 |

| Claude Code | 2026-09-30 | maya/inhouse/hedit 検索バー・docs/tools | 検索バーをVS Codeの寸法(幅419/入力25/ボタン22/アイコン16)に合わせ、アイコンをC++描画でmllへ内蔵、色はhedit配色・文字はエディターのフォント。選択範囲内で検索・AB(大文字小文字を保つ置換)・不正な正規表現の吹き出しを追加。VS Code撮影ツール(docs/tools/vscode_capture)と比較スクリプト(findbar_compare.py)を追加。5版ビルド警告0、run_tests/run_startup 5版・run_gui(gui_smoke)2024/2027・他GUIスイート2027・Sphinx -W 成功。未コミット。 |

| Codex | 2026-09-30 | mlib collection/Joint/Plug/DagNode・tests/docs | Bulk反復/引数準備集約、Joint適用/Joints全件準備へ整理、Double3子参照再利用、親取得をDagNodeへ集約。2025/26/27全74ファイル成功、2022/24既存73成功+追加3件は丸め差のテスト修正後再実行成功。discovery/reload・Sphinx -W・diff成功。2023未導入/GUI未実施、未コミット。 |

| Codex | 2026-09-30 | mlib追加集約計画 | 複数形・Joint回転移送・Plug子参照の段階計画をresearch保存。mirror/Point/Constraintは既存委譲を維持。実装・Maya実行なし。 |

| Codex | 2026-09-30 | mlib DagNode・tests/docs | DagNode追加、Transform/Shapeのdag_path/dag_fn/parent_path集約。型登録維持・静的公開追加・説明更新。2027関連56テスト/reload成功、Sphinx -W成功、diff確認。他版/GUI未実施。 |

| Codex | 2026-09-30 | mlibベースクラス集約計画 | DAG重複・既存単複継承・Point系・Plug系を確認。API維持の5段階計画をresearch保存。実装変更/Maya実行なし。 |


| ツール | 完了日時 | 対象範囲 | 内容 |
| --- | --- | --- | --- |




| Codex | 2026-10-12 | QuickPathExplorer・関連テスト | バージョン整理を除く不足機能の実装と検証。 |






| Codex | 2026-10-11 | 配布方式の相談（README・起動バッチ・submoduleの参照のみ） | SourceTreeとGit不要の配布・更新方式を比較。 |
| Claude Code | 2026-10-08 | maya/inhouse/hedit(src/editor/code_editor.*・tests/vscode_features_smoke.py・docs・release/*.mll)・maya/modules/hedit.mod | hedit 0.4.2: MayaのHelp→Popup Helpがオフだとホバーが出ない問題を修正(Mayaが QEvent::ToolTip を止めるため、マウス移動から0.5秒の自前タイマーで出す)。2022〜2027でビルド・単体テスト合格、Popup Helpオフでのホバーを含むGUIテストを2022/2024/2027で合格。未コミット。 |
| Claude Code | 2026-10-07 | maya/inhouse/hedit(src/editor/output_panel.*・src/plugin/output_capture.cpp・src/core/history_text.cpp・tests/ui_smoke.cpp・docs・release/*.mll) | 出力欄のさらなる高速化(0.4.1に追加): 出力が続くほど描き直しの間隔を広げる、5,000行を超える分は最初から入れない、取り込みの軽量化。2027でエラー5,000件(8行)4.7秒→3.9秒(基準3.4秒)。2022〜2027でビルド・単体テスト合格、出力のGUIテストは2022/2024/2027合格。未コミット。 |
| Claude Code | 2026-10-07 | maya/inhouse/hedit(src/plugin/output_capture.*・editor_host.cpp・src/core/history_text.*・src/editor/output_panel.cpp・editor_preferences.*・main_window*.cpp・editor.h・tests・docs・release/*.mll)・maya/modules/hedit.mod | hedit 0.4.1: 出力欄の高速化。既定の取り込みを非表示reporterからMCommandMessageの整形に変更(Exact Script Editor output formatで旧方式)、その場の描き直しを100msごとに、Maya 2022の書き方に対応。2027でエラー5,000件(8行)8.5秒→4.7秒(標準SE 7.1秒)。2022〜2027でビルド・単体テスト合格、出力のGUIテストは2022/2024/2027(output_formatは2023/2025/2026も)合格。未コミット。 |
| Claude Code | 2026-10-07 | docs/research/hedit-output-perf-20261007.md(ローカル)・計測用スクリプトはscratchpad | hedit出力欄と標準Script Editorの速度比較(Maya 2027/2024、displayError 5,000回)。heditは表示時に標準より1〜4割遅く、閉じていても非表示reporterの分の時間がかかる。コード変更なし。 |
| Claude Code | 2026-10-05 | maya/inhouse/mlib/docs(conf.py・_templates/layout.html・locale)・.github/workflows/mlib-docs.yml・tools/translate_docs.py・hedit/hrig docs.po | mlibドキュメントの英語版: 本文とAutoAPIのdocstringの文(9019件中日本語6092件)をOllamaのqwen3-coder:30bで英訳し6044件を保存(残りは記法が崩れたため日本語のまま)。サイト直下が日本語版、en/が英語版で、上部の帯で切り替え。CIでen/もビルド。英訳で末尾が_の単語が参照の記法になる問題をtranslate_docs.pyで\_に置き換えて防止。ja・enとも-Wビルドで警告なし、Mermaid確認980ページ合格。 |
| Claude Code | 2026-10-05 | maya/inhouse/HTools(20ファイル)・tools/test_htools_cycles_gui.py・README.md・hrig/docs/aim_axis_conversion.rst・CLAUDE.md・hedit/hrig docs.po | HToolsの画面・warning・print・error・ログ・例外のメッセージ170件を英語化(コメント・docstringは日本語のまま)。convertAimAxesは英語ラベルが切れないようラベル列を240pxに。README・hrig docsのボタン名を英語の表示名へ。CLAUDE.mdに英語の決まりを追記。Maya2027で使い捨てGUI(Aim 8項目・サイクル調査)、mayapy(サイクル7・Aim17・大型ツール55)合格。ドキュメントの差分も英訳。 |
| Claude Code | 2026-10-05 | CLAUDE.md・.gitignore・tools/translate_docs.py・.github/workflows/mlib-docs.yml・maya/inhouse/hedit/docs・maya/inhouse/hrig/docs(conf.py・_templates・locale) | hedit・hrigドキュメントの英語版: Sphinxのgettextで文を.poへ取り出し、Ollamaのqwen3-coder:30b(ユーザー許可・CLAUDE.mdに例外を追記)で英訳(hedit 1047件中1034件、hrig 242件中240件。残りは記法が崩れたため日本語のまま)。上部の帯に日本語/Englishの切り替え。CIで/en/もビルド。英語版の-Wビルドは両方警告なし。未コミット。 |
| Claude Code | 2026-10-05 | maya/inhouse/hedit(src・tests・docs・release/*.mll)・maya/modules/hedit.mod | hedit 0.4.0: VS Code比較メモのおすすめ1〜10を実装(同じ名前・括弧の強調、括弧の自動で閉じる、引数のヒント、縦線、スクロールバーの印、補完の種類と説明、記号へ移動・アウトライン、定義へ移動・その場で見る、選択範囲の拡大、未定義の名前と波線・F8、最近開いたもの・Ctrl+P、折りたたみ、見出しの固定表示、保存前との差分)。2022〜2027でビルド(警告0)と単体テスト合格、新GUIテスト(vscode_features_smoke)は2022/2024/2026/2027、既存GUIテストは2024/2027、session・startupも合格。未コミット。 |
| Claude Code | 2026-10-05 | maya/inhouse/hedit/docs/tools/vscode_capture(capture.py・extension.js)・docs/research/hedit-ux-20261005(ローカル) | VS Codeの操作を25場面撮影し、heditとのUI/UXの差と優先順をローカルメモにまとめた。撮影ツールに拡張機能のコピー(files/extensions)と完了を待たないコマンド(noWait)を追加。hedit本体は未変更。未コミット。 |
| Claude Code | 2026-10-04 | maya/inhouse/hedit(src/editor/code_editor.*・main_window.cpp・code_assist.cpp・tests/ui_smoke.cpp・docs/changelog.rst・release/*.mll) | Shift+Enter・貼り付けで入るU+2028(行区切り)を普通の改行にし、実行・補完へ渡す文字列でも改行へ変換。2022〜2027でビルドと単体テスト合格。 |
| Claude Code | 2026-10-04 | maya/inhouse/hedit(src/editor/code_editor.cpp・src/core/completion_engine.*・src/core/symbols.*・src/core/python_declarations.cpp・src/python/hedit/bridge.py・tests・docs・release/*.mll) | 補完のEnter確定でフォーカスがアウトライナ等へ飛ぶ問題を修正。代入(x = pkg.Class(...))・変数/引数の型ヒントからの型推論を追加し、親クラスのメンバーも補完・ホバー。2022〜2027でビルドと単体テスト合格、補完GUIテスト(新しいEnter確認を含む)は2027で合格。 |
| Codex | 2026-10-03 | docs/research/localLlmBenchmark* | ユーザー許可により3モデルをダウンロードし、同一問題の回答・速度・メモリを逐次比較。 |






| Codex | 2026-09-30 | mlib追加内部整理計画 | 後始末例外・登録衝突・bulk検証負荷・テスト環境再現性を実装から確認しresearchへ計画保存。公開API維持、実装変更・Maya実行なし。 |
| Codex | 2026-09-30 | mlib参照/入力契約・tests/docs・hrig使用側 | Node/Plug固定hashと比較、Joint特例廃止、Component比較、具象Node型保証、DAG消失時の切替禁止、名前/Node混在拒否を反映。破棄済みMObjectのis_aliveクラッシュを保持handleで修正。各版2022/24/25/26/27の72ファイル/773件実行成功(skip5/5/2/2/2)、GUI2027 102成功exit0、discovery/reload・Sphinx -W成功。hrig混在1箇所修正後50/51成功、残り外部FKベイクの既知接続属性エラー。規約/移行ガイド更新。他版GUI未実施、未コミット。 |
| Codex | 2026-09-30 | mlib設計固定前レビュー | Joint等価/hash特例、具象型生成、DAGパス切替、ls返却型、失敗契約を調査し候補をresearch保存。実装変更・Mayaテストなし。 |
| Codex | 2026-09-30 | mlib計画再検討 | Maya依存を分離基準にせず対象クラスへ処理を維持。混在入力禁止の適用範囲、単複/Undo/fast/初期化の整理計画をresearchで改訂。数値分離案撤回。実装変更・Maya実行なし。 |
| Codex | 2026-09-29 | mlibリファクタリング計画 | coerce・bulk・Undo/fast・SkinCluster/JSON・初期化/reloadの順で段階計画。公開APIと単複同居を維持。docs/researchへローカル保存。実装変更・Maya再実行なし。 |
| Claude Code | 2026-09-29 | maya/inhouse/hedit(src/・tests/・docs/・README・CMakeLists.txt・release/*.mll) | 補完をC++化: core/script_lexer(Python/MEL字句解析)・python_declarations(宣言抽出)・completion_engine・symbols・completion_types・script_file追加。Pythonはhedit.bridge(公開名/sys.path/組み込み名の窓口、印で変化なしなら送らない)とanalysisのみ、completion.pyとheditorを削除。構文強調を字句解析化(三重引用符の複数行・MEL予約語/$変数/ブロックコメント)。自動保存は変化時のみ、行番号は変化範囲だけ再描画、Explorerは別スレッドで列挙、user_pathsはキャッシュ、dockの調査ログと旧ドック名を削除、MainWindowをmain_window_menus.cppへ分割、設定キーを定数化、補完/解析はJSONでなく構造体で受け渡し。hedit -complete/-declarations(テスト用)追加。5,000行編集中の補完 約100ms→約5ms、cmds.補完p95 2.4〜16ms→1.4〜1.7ms。ast突き合わせ400ファイル一致。5版ビルド警告0、run_tests全5版、run_startup 25回、run_gui 4種×2024/2027、run_session 2024/2027、Sphinx -W成功。未コミット |
| Codex | 2026-09-29 | 全未コミット変更 | 全変更をmainへのコミット・プッシュ対象として整理。mlib/hedit/hrigとドキュメントを含む。差分チェック・サブモジュール参照不変を確認。Git除外の研究メモ/計測ログは対象外。今回Maya全テストは再実行していない。 |
| Codex | 2026-09-29 | README.md・.github/workflows/mlib-docs.yml | READMEへhrig Sphinx公開予定URLとソース/ビルド手順を追加。Pagesに/hrig/を生成するビルドと変更検知を追加。ローカルSphinx -E -a -W成功、diff確認。コミット/プッシュ/公開は未実施。 |
| Codex | 2026-09-29 | hrig/docs・README | 独立Sphinxサイトを追加。mlibとsphinxdoc/CSS共有、既存機能ページを目次へ登録。テスト方法・生成シーン仕様・20条件性能表・両版71件の既存検証記録と制限を掲載。Sphinx 8.2.3 -E -Wビルド、HTML参照先・CSS一致確認成功。Maya再実行・ブラウザ目視は未実施。 |
| Codex | 2026-09-29 | tools/benchmark_hrig_constraints.py・hrig計測docs | --modes指定、各反復前のCached Playback無効確認と照会値記録を追加。2027で5構成×Serial/Parallel×2配置の20条件（300拘束・120frame×5）を再計測、40姿勢条件一致、全条件cache無効/fallbackなし、exit0。無効化ガードと構文検証成功。研究結果はdocs/researchにローカル保存。CPU1スレッド固定・GUI描画/スキンは未測定。 |
| Claude Code | 2026-09-29 | maya/inhouse/hedit(src/editor/・tests/options_smoke.py・docs/preferences.rst・changelog・release/*.mll) | Edit > Preferences 末尾に「Reset to defaults…」を追加。確認(Reset/Cancel)のうえ13項目と文字サイズを初期値へ戻し、preferences.iniから項目を削除、全タブ・出力欄・Zoomへ即反映。タブ本文・ファイル・Explorer・tabs.jsonは不変。options_smokeにキャンセル不変・初期値復帰・ini削除・Reset zoom同等の検証を追加(モーダル後に前面化し直す処理も追加)。5版ビルド警告0、run_tests全5版、gui_smoke 2024/2027成功、Sphinx -W成功。preferences-menu.pngのスクリーンショットは未更新。未コミット |
| Claude Code | 2026-09-29 | maya/inhouse/hedit(src/・cmake/・tests/・docs/・README・CMakeLists.txt・release/*.mll)、docs/cpp-documentation.md | hedit C++を初心者向けの構成へリファクタリング(動作・保存形式は不変)。src/をcore/(Maya・画面非依存: 履歴整形・import走査・検索置換・tabs.json形式)・editor/(Qt画面を部品ごとに分割: MainWindow・CodeEditor・OutputPanel・FindBar等)・plugin/(Maya API: コマンド・出力購読・Python呼出・ドック・メニュー)へ分け、依存は一方向。createEditorの8引数をEditorServices構造体に、色をtheme.hに、版をversion.hの1か所に集約。埋め込みPythonをsrc/python/*.pyの実ファイルにしcmake/embed_python.cmakeでビルド時に配列化。_USE_MATH_DEFINESでC4005警告を解消(警告0)。ui_smoke.cppに検索置換・tabs.json・行編集の単体テスト追加。途中でテストがsetProperty('path')で保存先を書くことに依存していると判明し、pathは動的プロパティを正本に修正。5版ビルド、run_tests全5版、run_startup全5版×5段階、run_gui(gui_smoke/completion_output/formatting_spelling/output_format)2024/2027、run_session 2024/2027、Sphinx -W 成功。未コミット |
| Codex | 2026-09-29 | hrig C++/Bifrost行列追従・benchmark・mlib_bifrost MathBuilder・mlib/utils/undo・tests/docs | 単一入力のhrigMatrixFollowと倍精度Bifrostグラフを追加。C++2025/2027 Releaseビルド成功。2027で300拘束×120frame×5・5構成30条件を同一実行で比較、両版60姿勢条件一致。最終両版各71テスト成功（追加17/setup47/native7）。Parallelは標準OPMがC++より速く、1拘束1Bifrostグラフは重い。Bifrost構築Undo/Redoで専用Mayaが異常終了したためGUI/Undo有効時は拒否し検証用に限定。2025の大規模性能・描画/スキン・Bifrost配列一括は未測定。結果はGit対象外research、AST/RST/format/diff成功、既存変更保持・未コミット。 |
| Codex | 2026-09-29 | hrig拘束性能・MatrixFollow・専用計測ツール・tests/docs | 単一入力のmultMatrix→OPMセットアップと18条件の反復計測を追加。2025/2027各300拘束・120frame×5、各36姿勢条件一致。Parallelの300段階層でOPM約68〜71%短縮、独立配置は2027で改善なし。スカートparent→orient単純置換は姿勢差で不採用。両版setup47件成功、最終2027計測smoke成功、AST/RST/diff確認。初回スレッド数未取得は報告へ明記し照会修正。比較結果はGit対象外research、GUI/描画/スキン速度は未検証。既存変更保持、未コミット。 |
| Codex | 2026-09-28 | mlib追加提案・内製使用側・tests/docs | 推奨改名、入力/ウェイトgetter、Reference継承契約、influencesのNode返却、成分setterのws/fast/自身返却、members可変長入力を反映。旧別名なし・JSON形式維持。mlib関連489件を2022/2027で実行（486成功3skip/488成功1skip）、2027 GUI56件成功、hrig foundations13件成功。hrig追加51件中50成功・外部FKベイク1件失敗はHEAD隔離コピーでも同じ接続属性エラーを確認した既存問題。2022 hrigは既存Python型注釈制約で未検証。Sphinx -W・diff成功。他版Maya未実施、未コミット。 |
| Codex | 2026-09-28 | mlib追加調査4（読取） | Referenceのnamespace/set_namespace・is_root継承意味、members入力契約、ensure_loaded成功保証、kind/typeを調査。Git対象外researchへ保存。実装変更・Maya実行なし。 |
| Codex | 2026-09-28 | mlib追加調査3（読取） | influence返却型・Reference文字列照会名・属性API表記/順序操作・成分別setterの契約を確認。詳細はGit対象外docs/research。実装変更・Maya実行なし。 |
| Codex | 2026-09-28 | mlib追加命名調査（読取） | 戻り値が曖昧な名称3群、入力getter等の補完候補、回転/有効性/単複設定の意味が異なる例外を実装確認。詳細はGit対象外docs/researchに保存。実装変更・Maya実行なし。 |
| Codex | 2026-09-28 | mlib命名・内製使用側・tests/docs | TimeSlider/Units/UI/Workspace/ノードgetter、Plug取得名、Namespace/UiElement保持名propertyを統一。旧別名なし・戻り値維持、BlendColors.get_blender追加。使用側・Sphinx移行ガイド更新。Maya2022/2027 standalone関連各214件成功、2027数学型66件/hrig13件成功、GUI2027最終30件/exit0成功。GUI初回起動前exit251、再試行で旧名が残るテストを修正して成功。Sphinx -W成功・diff検証成功。他版GUI未実施、未コミット。 |
| Codex | 2026-09-28 | mlib命名読取・ローカル調査 | クラス明示API一覧と内部継承を確認し、get/set対・Plug/値・保持値property・意味を維持する例外を分類。候補と影響範囲をdocs/researchへ保存（Git対象外）。実装変更・Maya実行なし。 |
| Codex | 2026-09-28 | mlib複数形・Colors・tests/docs | Nodes→Transforms→Joints / Nodes→SkinClustersへ移行。型検証、DAGパス保持、参照copy/slice、色getterのColors返却・各色setter/全件事前検証・共有属性競合検出、bulk継承signature/禁止設定、instanced Joint削除のUUID単位処理を実装。ls返却規則は維持。Maya2022/2027 standalone各109件成功後、追加インスタンス削除含む関連18件を両版再検証成功（各110件相当）。Maya2027専用GUI最終32件/exit0成功、Sphinx -W警告0・継承図リンク・diff成功。初回GUIは起動前exit251、環境を変え再試行成功。描画色の目視・他版GUI未実施。設計規約/移行ガイド更新、未コミット。 |
| Claude Code | 2026-09-28 | maya/inhouse/hedit(src/editor.*・explorer.cpp・plugin.cpp・dock.cpp、tests/、docs/、release/*.mll) | 4K画面でUIが小さい件: setUiScale(MQtUtil::dpiScale)/scaled()で文字・余白・幅・アイコン寸法を全体的に拡大率へ追従、アイコンはMQtUtil::createIconで高解像度画像。Zoomのpxは100%基準で保存。併せて保存済み空ドックへの`hedit -show`でのクラッシュ(表示を先に行う順序へ)と、未ロード時の浮動ドック自動クローズで出る`Cannot find procedure "hedit"`(closeCommand/uiScriptをロード状態で分岐)を修正。200%で実機確認(コード28px・アイコン40px)。5版ビルド、run_tests/run_startup(浮動ドック段追加)全版、gui_smoke等2024/2027成功。システムのクリップボードが他アプリに占有されていたためコピー確認のみ使用不可時スキップに変更。Sphinx -W 警告ゼロ。未コミット |
| Codex | 2026-09-28 | mlib複数形クラス読取・ローカル調査 | BulkCollection/Joints/SkinClusters・色・ls・型解決/公開・コンポーネント継承・関連テストを調査。Nodes→Transforms→Joints、Colors連携、型/重複/インスタンス/Undo/戻り値の契約と段階的移行案をdocs/researchへ保存（Git対象外）。実装変更・Maya実行なし。 |
| Codex | 2026-09-28 | Color初期値・tests/docs | Color()を番号0/RGB同期で初期化。disabled/coerce(None)の無効状態を維持、Colors()は空。Maya2027 standalone関連28件成功、Sphinx -W警告0、diff成功。今回GUI/他版未実行。既存変更保持、未コミット。 |
| Codex | 2026-09-28 | general.Color/Colors・tests/docs | color.pyへColors追加・generalで公開。順序/重複保持、独立copy/slice、index/rgb列の全件事前検証と同期、既存bulk API対応。Maya2027 standalone関連27件成功、Sphinx -W警告0、diff成功。今回GUI/他版未実行。既存変更保持、未コミット。 |
| Codex | 2026-09-28 | mlib Color・色API・tests/docs | general.Color追加。index/RGB同期・指定形式保持・palette_source/再取得・copy。Node色getterをget系/Color返却へ統一、setterはColor対応と全属性事前検証。BlendColorsは数値を維持しcolor_plug/get_colorへ整理。使用側・Sphinx更新。Maya2027 GUI/standalone各24件成功（Undo/Redo・fast・ロック・複数形含む）、Sphinx -W警告0、diff成功。GUIの描画色目視・他版は未検証。バッチは標準パレットを使用。既存変更保持、未コミット。 |
| Codex | 2026-09-28 | mlib色API読取 | Node/BlendColorsの色取得・設定と既存テストを確認。名称と値/Plug返却の不一致、Noneの影響範囲を説明。実装変更・Maya実行なし。 |
| Codex | 2026-09-28 | mlib追加API整理・使用側・規約/tests/docs | 単数/複数クラス同居をAGENTS/CLAUDE/Copilotと設計規約へ明記。AnimCurveのkey_values/get_tangent/get_infinityと外挿部分更新、ピボット種別/preserveと読み書き空間統一（Joint設定は明示拒否）、SkinCluster移送の全組事前検証・解除bool検証、保持値property化を実装。移行ガイドと使用側更新。Maya2027 standalone全67ファイル実行65成功、旧呼出修正後にbulk4件/起動設定3件再検証成功（合計66ファイル相当成功、既存Bifrost起動の古いmaya_utils参照・flowWedging失敗残存）。追加回帰7件・hrig16件成功。Sphinx -W警告0、diff検査成功。GUI・他Maya版未実行、未コミット。 |
| Codex | 2026-09-28 | mlib追加読取調査 | 前回変更後のAPIを確認し、追加候補と統合しない操作をローカル調査メモへ整理。実装変更・Maya実行なし。 |
| Codex | 2026-09-28 | mlib API整理・main | 依頼された変更のコミット・push準備完了。差分検査成功、リモートと分岐なし。生成物・調査メモは対象外。実行検証・既知の失敗は直下の記録を参照。 |
| Codex | 2026-09-28 | mlib・使用側・tests/docs | 追加検討を実装。Double3Plugを属性読み書きに限定しPlugのws除去、set_flagsへ状態設定統合、Constraint対象事前検証、Joint.remove_influenceのtransfer_to_parent、orientation/version_tuple除去、座標軸内部共通化。使用側・移行ガイド更新。Maya2027 standalone: mlib66ファイル中65成功（追加契約テスト9件成功）、hrig16件成功、最終Joint/Version20件成功。既存Bifrost起動テストのmaya_utils参照・flowWedgingロード失敗は残存。Sphinx -W警告0、diff検査成功。GUI・他Maya版は今回未検証。 |
| Codex | 2026-09-28 | mlib追加調査 | Double3Plug責務差、Constraint事前検証、Jointフラグ・別名、状態設定統合など8候補をローカル調査メモへ整理。API変更・Maya実行なし |
| Codex | 2026-09-28 | mlib・hrig使用側・テスト・docs | 調査提案の推奨項目を実装。MatrixPlugの属性更新への責務限定、重複入口除去、個数/メンバー/親/IK/ウェイトAPI命名統一、set_visible/set_muted/Selection.select、PluginPackage保持値のproperty化。使用側と移行ガイド更新。Maya2027: mlib 66ファイル中65成功（追加回帰4件成功）、hrig関連16件成功。Bifrost起動テストは古いmaya_utils参照とflowWedgingロード確認で失敗。全体ランナーの--worker引数混入を避けた個別ドライバで検証。GUI未実行 |
| Codex | 2026-09-28 | mlib全体（読取調査） | 169ファイルのメソッド一覧と類似候補実装を確認。命名・責務差・フラグ統合の提案をローカル調査メモへ整理。API変更・Maya実行なし |
| Claude Code | 2026-09-28 | maya/inhouse/hedit(src/・tests/・docs/・README・release/*.mll) | hedit同梱Pythonのうち、CPython不要な部分をC++へ置き換え(段階1・2と補完のimport走査のC++化まで完了)。段階1: 起動時の出力履歴取得と整形(compactHistory)・出力用reporterの作成/破棄・タブ復元先の決定(hedit -sessionPath)をplugin.cppへ。段階2: docking.py/startup.py(MayaQWidgetDockableMixin)を廃止し、src/dock.cppでMELのworkspaceControl+MQtUtil::addWidgetToMayaLayoutによるドッキング、ui.jsonの保存、closeCommand/quitApplicationのscriptJob、起動時の復元を実装。hedit コマンドに -show/-floating/-restore/-saveState/-sessionPath(内部 -closed/-quitting)、メニューとuiScriptはMEL。Pythonのhedit.show()/restore()は互換窓口のみ。残るPythonは補完(ast/公開名)と構文チェック(compile)。途中で発見・修正: MELの整数/真偽値結果をexecuteCommandStringResultで取ると空になり-exists判定が常にfalse(段階1のreporter破棄漏れも同因)→melInt/melBool追加、ドック作成時のuiScriptで取り付けると画面が破棄される、Maya2027のaddWidgetToMayaLayoutの戻り値型、アンロード前の遅延ラムダ実行による落ちの予防(lifetime文脈)、PySideのQMainWindow型取り出しで古い削除済みラッパーが返る件(テスト補助tests/hedit_host.pyで回避)。全5版ビルド、run_startup全5版×3段階・run_tests全5版・gui_smoke 2024/2027各29項目・formatting/output_format 2027・session 2024/2027成功。Sphinx -W警告0、撮影ツール動作確認(画像は未更新)。追加(2026-09-28): 既存不具合だったcompletion_output_smokeを修正。原因は初回のimport補完でsys.path走査がPythonスレッドで未開始→候補空で約0.5秒後に出直し、走査中はGILで画面も引っかかる。C++化で解消: src/modulescan.cpp(ModuleScanner)がsys.pathのトップレベル名をC++スレッドで編集画面作成時から走査、初回は最大0.5秒待機、以後5秒間隔で裏で再走査。Pythonはsys.path/読込済み名の受け渡し(bridge.module_names)だけ、Index.scan_topは削除。ui_smoke.cppに走査・判定・並び・追従のC++テスト追加、test_completion/formatting_spellingを追随。テスト側の既存の手順漏れ(前面化せずCtrl+Space・前面化の非同期)も修正し、初回候補の中身は厳密に検証。completion_output全5版成功(2024×3・2027×4含む連続成功)、run_tests全5版、run_startup全5版、session 2024/2027、gui_smoke/formatting/output_format 2024/2027成功 |
| Codex | 2026-09-27 | 未コミット全体・main | ユーザー依頼で既存変更全体をコミットしてorigin/mainへ送信するための確認完了。リモートと分岐なし、差分検査成功。調査メモ・テスト生成物・submodule参照の追加なし。機能検証は直近の各実装記録を参照。 |
| Codex | 2026-09-27 | mlib cmds動詞命名・使用側・tests/docs | constraint→addConstraint、curve/group/ikHandle/sets→create系、node/plug/scene/UI/drivenKey→get系へ13入口を改名。lsはユーザー指定で維持。旧入口なしで使用側更新。生成/追加からquery/editを分離しConstraint/ObjectSet/Plugメソッドへ移行、Plug.set_enum_names追加。2022/2027共通各125件、2025標準69件、2027全体155件成功。専用GUI2027 30項目/exit0・画面確認、Sphinx -W・diff成功。既存変更保持。証跡.maya-output/command-names。 |
| Codex | 2026-09-27 | mlib cmds14件削除・使用側・tests/docs | 指定14コマンドをファイル/公開APIから削除。hrig/mlib_bifrost/テストをmaya.cmdsへ移行、必要なNode/Plug変換を使用側へ明示しconnectionsの平坦ペアを処理。旧APIテスト/ドキュメントとhrig境界ルールも更新。2022/2027共通各95件、2025標準リグ69件、2027全体155件成功。専用GUI2027 30項目/exit0・画面確認、Sphinx -W・diff成功。既存変更保持、未コミット。証跡.maya-output/remove-cmds。 |
| Codex | 2026-09-27 | mlib cmds/delete・Node.delete・tests/docs | 基底Node.deleteを追加し、mlib.deleteは名前から具象クラスへ解決して各node.delete()を呼ぶ。Joint専用のウェイト移送/子階層保持も適用。親削除済み/重複をスキップし、コンポーネントは標準削除。Maya2022/2027各117件（派生delete委譲、Joint子保持、Undo/Redo等）、2027標準リグ69件成功。Sphinx -W・diff確認成功。GUI操作は未検証。既存変更保持。証跡.maya-output/node-delete。 |
| Codex | 2026-09-27 | mlib createNurbs・NurbsSurface・hrig ControlShape・tests/docs | circle.pyを削除しcreateNurbs(type/typ)へ統合。Maya同梱メニューに対応する8種類、単一形状はNurbsCurve/NurbsSurface、cubeは6曲面・squareは4曲線のリスト。NurbsSurfaceラッパー追加、旧使用側を更新。Maya2022/2027各12件（全8種類×履歴有無、Undo/Redo、出力型等）、2025 setups39件、2027標準リグ69件、Sphinx -W・diff確認成功。GUI操作は今回未検証。既存変更保持。証跡.maya-output/create-nurbs。 |
| Codex | 2026-09-27 | mlib createPolygon・hrigデモ・tests/docs | polyCubeを削除しcreatePolygon(type/typ)へ統合。11種類の生成プリミティブ、長短フラグ、履歴に依存せず単一Meshを返す。Transform使用側をtransform()へ更新。Maya2022/2027各12テスト（全11種類×履歴有無、Undo/Redo等）、2027セットアップ39件・デモ高低Mesh/スキン生成成功。Sphinx -W・構文・diff確認成功。GUI操作は未検証。既存変更保持。証跡.maya-output/create-polygon。 |
| Codex | 2026-09-27 | mlib logger・constraint統合・hrig使用側・tests/docs | warning/error/info/printをutils.loggerへ集約、cmds/warningを削除。aim/orient/parent/poleVectorの個別コマンドを削除しconstraint(type=...)へ統合、専用フラグ・型付き照会・編集を維持。hrigの腕脚/スカート/視線を更新。Maya2022/2027共通各131件、2027標準リグ69件・setups39件成功、Undo/Redo確認。Sphinx -W、diff確認成功。未初期化mayapyのログAPI呼出防止・import成功。GUI操作は今回未検証。既存変更保持。証跡.maya-output/logger-entry。 |
| Codex | 2026-09-27 | mlib general/utils・hrig setups・Bifrost・tests/docs | animation廃止。DrivenKey/DrivenKeysをgeneralへ1クラス1ファイル化、CurveFit/DampedSpring/ScalarGraphをutilsへ。Soft IK/補助骨/空間切替/RBF/Spline設定/形状等11クラスとBifrost Soft IKをhrig.setupsへ、MathBuilderをmlib_bifrost.utilsへ。使用側・テスト11ファイル・仕様書9ページを移動し規約更新、互換なし。hrig内のcmds/OM/jsonをmlib APIへ置換、型付きcircle/curve追加。reload後の古いNode参照・参照同一性を修正。2027全155成功、2025標準69/セットアップ39成功、2022 mlib30と関連94件(93成功/GUI1skip)。2022のhrigセットアップ実行は既存の2025以降/Python型注釈制約で不可、対象2025で確認。隔離GUI2027は30項目・exit0・画像確認、Sphinx -W/AST/diff/旧import検索成功。実制作シーン・2025 GUI未検証、既存変更保持、未コミット。証跡.maya-output/rig-boundary。 |
| Codex | 2026-09-27 | mlib general/utils・mlib_bifrost・使用側/tests/docs | context/editors/events/files/namespaces/pluginsのクラスをgeneralへ集約、FBX/参照関数をutilsへ移動。ユーザー指定でdecoratorsは維持、runtime案はgeneralへ変更。公開15→10フォルダ、旧フォルダ/互換importなし、hrig/HTools/拡張/tests/docsと今後の配置規則を更新。2027全153、2022共通67、2025標準69成功。共通240件は239成功/GUI専用1skip（初回flowWedgingログ権限で1失敗、通常権限の32件再検証成功）。最終共通67成功。隔離GUI2027は30項目・exit0・画像確認、Sphinx -W警告0・AST/diff/旧参照検索成功。実制作シーンと2025 GUIは未検証。既存変更保持、未コミット。証跡.maya-output/general-layout。 |
| Codex | 2026-09-27 | mlib cmds/context/events/editors・mlib_bifrost・hrig・使用側/tests/docs | 生転送MayaCommands廃止、mlib.cmdsへ型付き検索/生成/属性/UIを追加（Node/Plug/Matrix/Vector/UiElement、短縮フラグ・Undo・typing公開対応）。maya.utilsはDeferred/executeDeferredへ。Workspace/Units/Selectionをcontext、Bifrostをnodes/plugs/animation/pluginsへ移動。追加指示に従い旧互換11ファイルとクラス再公開を削除、hrig SoftIK互換入口も廃止し使用側・tests・docs・ガイド更新。2022共通66、2025標準69、2027全体152件成功。環境/選択/相互運用/JSON追加97件中96成功・GUI専用1skip。隔離GUI2027は30項目・exit0・画像確認、Sphinx -W警告0、AST106/diff/旧参照検索成功。型付き生成後のmessage所有登録とmenu内local importを修正し再検証。実制作性能と2025 Bifrost評価は未検証。既存変更保持、未コミット。証跡.maya-output/typed-commands。 |
| Codex | 2026-09-27 | hrig・mlib editors/json・関連テスト/docs | MEL3か所をMainWindow.name/NodeEditor.show/GraphEditor.showへ移行。標準json使用9ファイルをmlib.json.JsonTextへ統一、従来の型付きmlib JSONと分離して既存属性形式・標準jsonオプションを維持。直接import再混入・batch拒否・JSON互換検証追加。2022共通64件/2027全体149件成功、GUI2027は26項目成功。初回GUIはエディターを開放したままの監視復元で失敗、起動確認を末尾へ分離して再検証成功（開放状態の監視不安定原因は未特定）。Sphinx -W/AST/diff成功。既存未コミット変更保持。証跡.maya-output/mel-migration。 |
| Codex | 2026-09-27 | hrig・mlib・関連テスト/docs | hrig本体/UI/startup/examplesのcmds・OpenMaya直接依存を除去。既存currentTime/setKeyframe/objExistsとmathsのMatrix/Vector/EulerRotationを再利用、専門フラグ・生戻り値用MayaCommands(24明示メソッド)、Qt親取得MainWindowをmlibへ追加。単位/属性検索契約と直接import再混入チェック追加。2022共通62件、2025標準69件、2027全体147件成功。隔離GUI2027変更後23項目・exit0・画像確認、Sphinx -W・AST53ファイル・diff成功。既存変更保持。実制作性能、2025 Bifrost実評価は未検証。証跡.maya-output/cmds-migration。 |
| Codex | 2026-09-27 | hrig・mlib・mlib_bifrost・関連テスト/docs | Container/ScalarGraph/ControlShape/SoftIK、message配列参照、属性型・単位、skin bind/転送をmlibへ還元しhrigで利用。BifrostのGraph/Node/Compound/Portを1クラス1ファイル化、MathBuilder/SoftIKへ共通化。従来import入口・標準バックエンド維持。2022共通60件、2025標準69件、2027全体145件成功。隔離GUI2027は23項目成功・画像確認・exit0。AST43ファイル/diff、Sphinx -W成功。Bifrost実評価は2027、2025 Bifrostと実制作性能は未検証。証跡.maya-output/common-rig。 |
| Claude Code | 2026-09-27 | maya/inhouse/hedit/docs/(*.rst・tools/capture_suite.py) | heditのSphinxを現行仕様へ修正。install(importフック方式、Windowメニュー項目名・アンロードで削除、mayapyでのloadPlugin→import、旧版更新時の注意)、session(保存先にtabs.json.lock/hedit.svg/startup-debug.log、空workspaceControl時の復元)、output(非表示中・Maya終了中の描画)、development(版更新箇所5か所、テスト一覧をrun_startup/run_gui --suite/test_rename含め現状化、期限、2024のArnold停止、再ロード時の扱い)、index/overview/limitations。既存の表示崩れ4件(空白始まり・入れ子リテラル等)も修正。capture_suite.pyが削除済みhedit.__file__に依存していたのを修正し、画像はコピーせず撮影のみ2027で成功確認(docs画像は未変更)。docs/.venvにrequirements導入、Sphinx -W警告0・HTML内の未描画マークアップ0。未コミット |
| Claude Code | 2026-09-27 | maya/inhouse/hedit/tests/session_smoke.py | Maya 2024でrun_session.pyのwriteが「Tabs were not autosaved」で失敗する件を調査。hedit(Qt5)の不具合ではなく、Maya 2024同梱Arnold(mtoa)の起動直後の遅延登録(registerArnoldRenderer._register→arnoldmenu.updateAvailable→arnoldPlugins)がGUIスレッドを約5.1秒停止させ、テストの壁時計5秒期限が停止中に切れ、停止明けに自動保存タイマーより先に確認が走っていた。心拍タイマー+faulthandlerで特定し、起動4秒後の編集では2027同様約2秒で保存、停止時も明けて約0.1秒で保存されることを確認。C++は変更せず(再ビルドなし)、待機をイベントループの回数(200ms×25回)で数えるよう修正。run_session.py 2024/2027のwrite/read全成功、run_tests.py 2022〜2027全成功。未コミット |
| Claude Code | 2026-09-27 | maya/inhouse/hedit(src/embedded_python.h新規・plugin.cpp・editor.cpp・CMakeLists.txt・scripts/・release/*.mll・tests/・docs) | hedit本体のPython(scripts/hedit/*.py)を.mllへ同梱(sys.meta_path先頭のimportフック、mayapyでも登録)。scripts/userSetup.pyはloadPlugin呼出しのみ。Windowメニュー登録/削除をC++/MEL化し、アイコンSVGも同梱して<userPrefDir>/hedit/へ書出し。初回ビルドで生文字列区切り子16文字超過を修正。evalDeferredがloadPlugin中に走りメニュー未登録→同期登録に修正。空の保存workspaceControlへshow()で差込むとuiScriptに破棄→表示のみでMaya側uiScriptに作らせるよう修正。Maya終了時に閉じた画面へ出力描画しQtアクセシビリティでクラッシュ(2022-2026)→非表示時の即時描画停止とkMayaExitingで転送停止。全5版ビルド、standalone(unit22/mod/offscreen UI)・test_rename全版成功、起動GUI3段階(メニュー/アイコン/メニューから起動/右ドック復元/非再表示/アンロードで削除)全版exit0、総合GUI 2024/2027各29項目成功、session 2027成功。session 2024の自動保存未実行はHEAD(b2cda9e)でも再現する既存不具合として別タスク化。Sphinxは環境に無く未確認。scripts/hedit/__pycache__の削除は権限拒否で残存(importフック優先で影響なしをGUIで確認)。証跡.maya-output/hedit-tests, hedit-startup/20260927_192323, hedit-gui。未コミット |
| Codex | 2026-09-27 | hrig指/Aim/Tweak/Splinefit/PoseEditor/上部menu/startup・mlib CurveFit/PoseRbf・テスト/docs | 指Curl/Spread＋FK、首/左右眼Aim、全モジュール局所Tweak、Spline FK→IK近似/実IK位置誤差/許容値拒否、スカートRBF登録追加/削除/編集UIを追加。mlibへ純Python CVフィットと外部接続保持のRBF再登録APIを還元。追加依頼の上部hrigメニューを起動登録、サンプル/編集入口と重複防止を実装。標準ノード、Enabled/LOD入力切断、保存/Undo対応。2022共通54件、2025標準69件、2027全体137件成功。隔離GUI2025/2027各23項目・exit0、画像確認、Sphinx -W、AST21ファイル/diff成功。指切替の変換ノード増加、Spline m単位fitを修正再検証。初回追加testの角度get期待単位誤りも修正。Splineは近似・中間Twist完全再現不可、ポーズUIはスカート骨補正、親指解剖配置/既存skinへのTweak自動追加/非一様scale/実制作性能は対象外。既存mlib set_matrixのm単位不具合は未修正、Splinefitは軸別APIを使用。証跡.maya-output/controls、hedit並行変更保持。 |
| Codex | 2026-09-27 | mlib.LengthCompensation・hrig腕脚/Spline伸縮レイヤー・UI/監視/テスト/docs | ユーザー指定のストレッチ/スクワッシュ/体積補正を独立レイヤーとして腕脚・Splineへ追加。上下限、方向別強度、逆平方根の断面近似、親断面の累積補償、Enabled/FK/LOD切断、Soft IK距離正規化と逆算、リバースフット合成、保存/Undo対応。腕脚squash初期0。Sphinx -W/構文12ファイル/diff成功。2022共通51件、2025標準62件＋最新変更対象8件、2027全体127件成功。隔離GUI最終2025/2027各16項目・exit0。初期Spline m単位の距離変換とFK複合属性ロック解除を修正。起動直後GUIでUndoキュー空の失敗2回、チャンク釣合い0を確認後、検証開始15秒遅延で両版再検証成功。Splineはスキン前追加、体積は近似、非一様scale/実制作品質・性能は未検証。mGear差分はGit対象外docs/research/mgear-gap-2026-09-27.md。証跡.maya-output/stretch。hedit並行変更保持。 |
| Claude Code | 2026-09-27 | maya/inhouse/hedit/scripts/hedit/startup.py | Maya再起動時にheditウィンドウが復元されなくなる不具合を修正。Maya自身のworkspaceControl復元(uiScript)が既にhedit.restore()で表示・状態記録を済ませた直後、hedit側のuserSetup起動処理が二重に検知してhedit.show()を呼び直し、一度close()してから開き直すためcloseCommandが誤発火、「閉じた」状態が一瞬保存されタイミング次第でそのまま確定していた。restore_previous()にworkspaceControlの表示済み判定を追加し、二重に開き直さないよう修正。原因特定用に開閉状態の追記ログ(prefs/hedit/startup-debug.log、動作へ影響なし)も追加。ユーザーの実セッションで再起動を繰り返し問題なしを確認済み。副次的にGUI自動テストが対話デスクトップと別の実行文脈からはライセンス窓口へ接続できないことが判明(mayapyヘッドレスは問題なし)、hedit本体の不具合ではない |
| Codex | 2026-09-27 | mlib.SplineIK・hrig.SplineRig/LayerEditor/監視・テスト/docs | 背骨+Y/尻尾+Z、骨3〜64本・CV control4〜32個・長さ指定、固定骨長の標準ikSplineSolverと両端Advanced Twistを追加。FK/IK計算/変形/コントロール/内部の階層分離。Mode/Enabled/LowでIK入力切断とFK経路へ変更、UIのIK→FK姿勢合わせ、message保存参照、Undo/Redo、スキン使用中削除拒否。2022共通49件、2025標準56件、2027全体119件成功。隔離GUI2025/2027各16項目・exit0、画面確認、Sphinx -W/構文10ファイル/diff成功。FK→IK自動フィット・伸縮・体積・非一様scale・実制作性能は未対応/未検証。m単位の既存mlib複合scale.setによるtranslate再変換を検証中に発見、軸別scale設定で正常を確認。既存共通処理は未修正とREADMEに明記。証跡.maya-output/spline（probeScale.pyに再現）。作業中のhedit/startup.py外部変更を保持。 |
| Codex | 2026-09-27 | mlib.DampedSpring/PoseRbf・hrig.SecondaryLayer/スカート/UI・テスト/docs | ローカル回転の減衰ばねベイクと標準DGの複数入力Gaussian RBF補正を追加。元の手付け骨を保持し別出力列へ合成、Enabled/LOD切断、再ベイク・保存復元対応。UIに2サンプルと再ベイクボタン。2022共通47件、2025標準49件、2027全体110件成功。隔離GUI2025/2027各18項目・exit0、画面確認、Sphinx -W/構文9ファイル/diff check成功。初回のPlug生成・pairBlend子属性名・全キー削除によるcurve消失を修正して再検証。初版はスカートのみ、揺れはライブ物理ではなくベイク、キー/設定/FPS変更は手動再ベイク。衝突/親移動の慣性/実制作性能は未対応・未検証。証跡.maya-output/secondary。既存変更保持。 |
| Codex | 2026-09-27 | mlib.RotationFollow・hrig.FollowLayer/腕脚/スカート/UI・テスト/docs | Twist/Swing/全回転をQuaternionで0〜100%追従する補助骨を実装。実ローカル行列、基準姿勢、割合のDG評価、Enabled/LOD出力切断、所有・保存参照を共通化。UIに3種サンプルと割合を追加。2022共通44件、2025標準46件、2027全体104件成功。隔離GUI2027/2025各19項目・exit0、Sphinx -W/diff/構文成功。2025初回の属性通知待ちを固定時間から状態待ちへ変更して再検証。旧腕脚の表示階層自動移行、既存スキン自動追加、非一様scale/180度境界は対象外。mGear/AdvancedSkeleton調査と次の優先「揺れ物＋ポーズ補正」はGit対象外docs/research/follow-rig-candidates.mdに整理（この2機能自体は未実装）。証跡.maya-output/follow。 |
| Codex | 2026-09-27 | mlib.RadialWeights・hrig.SkirtRig/ModuleRegistry/UI/監視・テスト/docs | 4/8方向ドライバーから円周の任意列へ隣接二方向の正弦比率を分配。標準parentConstraint回転のみ・各targetオフセット保持・全体Blend/Falloff、Enabled/LOD切断、message参照とスキン使用中削除拒否を追加。UIで列数/各列骨数/半径/長さ指定。2025標準43件（単位/並列評価含む）、2027全体97件、2022共通41件成功。隔離GUI最終2025/2027各14項目・exit0、Sphinx -W/diff成功。GUI初期テストのArnold/HIK遅延起動干渉を開始idle分離で解消し、Undo後の不要な更新も抑止してRedo確認。既存骨への後付け/スキン自動生成/衝突/非一様scale/実制作性能は未対応・未検証。証跡.maya-output/skirt。 |
| Codex | 2026-09-27 | mlib.SwingTwist・hrig.drivenLayer/sampleBuilder/layerEditor・HTools入口・テスト/docs | 基準ローカル回転をSwing/Twistへ標準ノード分解し、1成分→既存DrivenKey→単一属性をEnabled/LOD管理。サンプルモジュールと6種レイヤーの追加・使用チェック・Mode/LOD・SDK/Node Editor起動をPySideパネルに実装。保存参照・Undo・折りたたみ保持・監視解除対応。2025標準38件、2027全体91件、2022共通39件、隔離GUI2025/2027各23項目・exit0、Sphinx -W/diff成功。GUI初回のノード型/Plug比較を修正、後続クラッシュはdumpのQt TreeWidgetItemIterator内と特定し明示子走査へ置換して再検証。保存再読込はexecuteScriptNodes=False（Maya生成UIスクリプト実行時の待機は回避）。並替/削除/ドッキング/既存スキン追加は未対応。証跡.maya-output/layer-editor。 |
| Codex | 2026-09-27 | mlib.BendCorrection・hrig.bendLayer/デモ/チャンネル・関連テスト/docs | 標準ノードで50%回転補間骨と内外の押引き骨を追加。曲げ方向/基準角/内外距離と移動量をChannel Boxで編集、Enabled/LODで出力切断、デモ高詳細13influences・proxy3。XYZの90度超えと単位差を検証し、距離defaultの内部cm問題を修正。2025標準34件・2027全体85件・2022共通37件成功、隔離GUI2027 48項目/exit0、Sphinx -W/diff check成功。既存helperは保持、多軸関節・180度超え・実制作ウェイト品質は対象外。証跡.maya-output/bend-layer。 |
| Codex | 2026-09-27 | mlib.TwistDistribution/MatrixPlug.set_value・hrig.twistLayer/デモ/スキン・テスト/docs | 両端を除くN骨をi/(N+1)で配置し、Quaternion軸成分を標準ノードで分配。X/Y/Z・複合曲げ・最短回転を検証。デモは各区間3本（twist_count指定可）、Enabled/LOD切断、保存・Undo・未使用骨の本数再生成、バインド済み拒否を追加。高詳細にツイスト骨、proxyに基本3骨を使用。行列属性への直接書込をmlibへ追加。2025標準29件・2027全体77件・2022共通34件、隔離GUI2027 44項目/exit0、Sphinx -W/diff check成功。初回の属性版差・行列set委譲・container削除時のセット消失を修正し再検証。180度境界/多回転蓄積は未対応。証跡.maya-output/twist-layer。 |
| Codex | 2026-09-27 | mlib.animation.SpaceSwitch・hrig空間レイヤー・GUI監視・テスト/docs | 標準choice/multMatrixによる汎用空間登録と姿勢保持切替を共通化。IK local/world、Pole local/world/foot、任意target追加、Spaceチャンネル監視と常時有効spaceレイヤーを追加。Foot空間のIK合わせ順序も修正。Maya2025標準22件、2027全体67件、2022共通31件、隔離GUI2027 38項目/exit0成功。Sphinx -W/diff check成功。初期API依存走査が専用mayapyでクラッシュしたためcmds走査へ置換して再検証。旧シーン自動変更なし、構成切替のみで切替アニメーションは未対応。証跡.maya-output/space-layer。 |
| Codex | 2026-09-27 | hrig標準Soft IK・起動・関連テスト/docs | standardバックエンドを既定にし、condition/plusMinusAverage/multiplyDivideと標準containerでSoft IKを構築。起動時Bifrostロード廃止、任意の旧バックエンドとstandardへの交換は保持。Maya2025/2027でロード禁止下の標準スイート各17件成功（数値境界・デモ・LOD・Undo/Redo・保存再読込・削除）。2027交換含むBifrostスイート15件成功（Bifrost初期化由来の警告あり）。diff check成功。GUI実操作は未検証、既存シーン自動変更なし。証跡.maya-output/standard-rig。 |
| Codex | 2026-09-27 | 未コミット変更全体 | ユーザー指示でmlib/hrigの実装・テスト・Sphinx・規約の変更をコミット対象として確認。origin/mainとの乖離なし、diff checkと既存のMaya2022/2027・Sphinx成功記録を確認。研究資料とテスト生成物はGit除外を維持。コミット・プッシュ結果はGit履歴を参照。 |
| Codex | 2026-09-27 | mlib外の利用側コード・参照 | hrig/HTools/hedit/mlib拡張/tools/外部ツールを検索し旧モジュールimport残存なし。Git除外資料も検索しdocs/research/mlib-submodule-review-2026-09-24.mdのarrayPlugへのリンクを修正。実行コードは追加変更不要。diff check成功、Maya再実行なし。ワークスペース外は未調査。 |
| Codex | 2026-09-27 | mlibの19モジュール・import/テスト/docs・AGENTS/API規約 | eulerRotation/scriptJob/channelBox/arrayPlug等へ改名し、内部_coreとdocs補助もlowerCamelCase化。mlib_*にも同規則を明記。テスト探索名/特殊名/パッケージ名/Maya nodeType名とメソッド名は維持。旧構成を読込済みのMaya2027プロセスからmlib.reload移行成功、旧モジュール除去とregistry確認。Maya2022関連192件、2027 Bifrostリグ15件成功。残存旧importなし、Sphinx -Wとdiff check成功。GUI操作とPoseDriverConnectバイナリは今回未検証。証跡.maya-output/camel-modules。 |
| Codex | 2026-09-27 | mlib/utils/version・plugins・hrig起動・版番号テスト/docs | 不変Version値クラスを1ファイルに実装。parts/suffix/major/minor/patch/build・parse・replace・比較/hashを集約。Plugin/Module.versionとPackageの版照会をVersion化、生文字列version_textと既存version_tupleを提供。utils/versions関数を廃止し利用箇所/ドキュメントを更新。Maya2027関連60件成功、2022は56成功4skip、mlib.reload・diff check・Sphinx -W成功。GUI未実施。証跡.maya-output/version-class。 |
| Codex | 2026-09-27 | mlib/plugins・utils/versions・Node作成・hrig起動・テスト/docs | Pluginsをplugins.pyへ分割。standard.ensure_node_pluginをPluginクラスメソッド、package._maya_yearをクラス内へ移動。versionsをutilsへ移し旧plugins関数公開を削除、呼出/規約/ガイド更新。Maya2022 plugin35件(2skip)+bulk4件・共通28件成功、2027 plugin35+bulk4件成功、reload旧名除去/構造/diff検証とSphinx -W成功。初回2027 flowWedgingはユーザーログ先へのsandbox書込拒否で失敗、旧実装でも再現し許可付き隔離mayapyで再検証成功。GUI未実施。証跡.maya-output/plugins-layout。 |
| Codex | 2026-09-27 | mlib/events・test_events | ScriptJobをscript_job.py、ScriptJobsをscript_jobs.pyへ分割し、__init__は再公開のみ。公開API維持。Maya2022共通28件成功、mlib.reload後のクラス再公開一致確認、diff check成功。GUI発火の再検証は未実施（実装本体変更なし）。 |
| Codex | 2026-09-27 | mlib/events・plug・Transform・hrig・AGENTS/docs・関連テスト | hrigの生成/属性/接続/行列をmlib公開APIへ移行。ScriptJob/ScriptJobs、mlib.plug、Plug.set_if_changedを共通化。行列適用の角度単位を修正。hrig本体の書式・日本語Google docstringを統一しdocs/hrig-development.mdとAGENTSへ規約追加。Maya2022共通28件、2025 native7件、2027 Bifrost統合15件、隔離GUI29項目成功。GUIはdirty化試験を含めexit0。Sphinx -W成功・diff check成功。2025GUI未実施。初期の親参照/rename戻り値の移行不備は修正して再検証済み。証跡.maya-output/hrig-mlib。 |
| Claude Code | 2026-09-27 | maya/inhouse/hedit/docs/(新規) | heditのSphinxドキュメント(利用ガイド・Preferences13項目の詳細・補完/出力/復元・開発)とスクリーンショット7枚(docs/tools/run_capture.pyで専用GUIから再撮影可)。Sphinx -W 警告0でビルド確認。hedit本体のソースは未編集。未コミット |
| Codex | 2026-09-27 | hrig/channel_controls・limb/animation・startup・demo・README・関連テスト・tools/run_mlib_gui_versions.py | modules_grp配下のMode/Lod/Match On Switch・レイヤーEnabled/Activeを標準チャンネルへ公開。GUI scriptJobで接続更新とUndo圧縮、読込/Undo後に再登録、無効状態グレー。FK合わせのxformワールド指定がRedoで崩れる問題をローカルTRS適用へ修正。2027 GUI23項目成功・画像確認、standalone15成功、2025 native7成功。終了直前にdirty化する試験でも専用GUIは保存確認なしexit0(.maya-output/rig-channels/gui-13)。終了時はdeferred内でmodified解除とquit forceを連続実行。普段のMayaは対象外。2025GUI・別プロセス初回起動での自動再登録は未検証。初期GUI試行の停止/失敗あり、最終版で正常終了。未コミット |
| Codex | 2026-09-27 | hrig naming/limb/reverse_foot/examples・README・テスト | RigNamingRule.maを読取参照しrig/geo_grp/jnt_grp/ctrl_grpとjnt/ctrl/ctrl_ofs/Shape命名を適用。モジュール/レイヤーDAG整理と階層化選択セット、setup非表示、整理group TRSロック。controlをゼロ化しローカルmatrixにoffset合成、FK/IKマッチ・足・backend交換を維持。2027 grouped15テスト、2025 native5、最終2027回帰10成功(exit0)。確認シーン.maya-output/rig-naming/hrig-demo.ma保存。GUI目視未実施、既存リグ自動移行なし、参照シーン/他作業変更なし。 |
| Claude Code | 2026-09-27 | mlib/plugins/{versions,module,package}.py(新規)・plugin.py・__init__・mlib/cmds/requirePlugins.py(新規)・hrig/startup/(新規)・maya/modules/hrig_startup.mod(新規)・関連テスト/docs | Maya 2025以降の起動時にBifrost 3.0.0以降を確認してロードし、無ければ警告ダイアログ。確認処理をmlibへ汎用化: Plugin.version_tuple/is_version_at_least、Module(登録モジュールの版)、PluginPackage(導入確認・ロード・警告)、mlib.requirePlugins。hrigのstartupはその薄いラッパー。2025/2026/2027のGUIで実機確認。 |
| Codex | 2026-09-27 | AGENTS.md・CLAUDE.md・.github/copilot-instructions.md・docs/aider-workflow.md・Ollamaモデル | ユーザー指示でAider委譲を停止、明示再開までOllama自動起動/ロードも禁止。qwen2.5-coder:32bをunload、API models空を確認。GPU空き22666 MiB。環境/モデルファイルは保持。文書差分確認、Maya実行なし。 |
| Codex | 2026-09-27 | docs/research/ollama-cuda-2026-09-27.md（Git対象外）・Ollama診断 | CUDA不正メモリアクセスはOllama llama-serverで発生。単体4k/11k各768トークン・Aider再試験1998トークン生成/一時ファイル編集は成功しCUDA未再現。GPU空き約1.2GB、同時Maya負荷との因果は未確定。Aider終了時の要約shutdown警告は別件。設定・ドライバー・製品コード非変更。 |
| Codex | 2026-09-27 | hrig（startup除外）・mlib_bifrost・mlib files/fbx・HIK5型/標準plugin生成管理・utils/evaluation・関連テスト/docs・tools/test_rig_packages.py | 検証版: 3関節FK/IK/Soft IK/補助骨、Bifrost/C++交換、LOD経路切断、リバースフット、proxyスキン、外部3骨FK/IKベイク。2027統合37成功・最終参照修正後14成功、2022関連22成功、2025 native5成功。C++2025/27ビルド・Sphinx -W成功、デモ保存成功。DG計測でSoft IK/補助骨の無効経路compute0、有効103。AiderはCUDA障害で中止し直接実装。GUI・実制作HIK retarget未検証。グラフUI/SplineIK/RBF/自動メッシュ削減/汎用増分構築は残件、docs/research/hrig-implementation-2026-09-27.mdに記録。別タスクstartup非変更、未コミット |
| Codex | 2026-09-27 | AGENTS.md・CLAUDE.md・.github/copilot-instructions.md・docs/aider-workflow.md | トークン削減が見込める場合のAider利用方針を共通化。対象限定・自動コミット無効・依頼元レビュー/検証・直接作業への切替を明記。参照先、ローカルCLI引数、差分確認済み。文書のみ、Aider/Maya再実行なし |
| Claude Code | 2026-09-27 | mlib(plugs・_core・nodes・cmds・selection・maths・json・docs)・CLAUDE/AGENTS/copilot | (1) maya.cmdsへの受け渡しを正式仕様化: Plug文字列を一意化(重複短名の不具合修正)、属性型判定をom2化(シーン変更・Mayaクラッシュ解消)、mlibコマンドがPlug/Component/MObject/MDagPath/MPlugを受付、cmds_interop.rst。(2) mlib.mathsをom2型継承に変更(Vector→MVector等、om2の演算意味論・可変・ハッシュ不可)。行列積約55µs→約1µs、get_matrix約7倍速。全版55ファイル成功。 |
| Codex + Aider | 2026-09-27 | maya/inhouse/hedit/scripts/hedit/docking.py | Aider実装後、Codexで重複importと再利用時の更新漏れを修正。既存__version__をドック/浮動タイトルへ表示。Python3.7構文・差分確認成功。Maya接続口なしでGUI未検証。Aider使用量4.0k入力/438出力(ローカルOllama)、自動コミットなし |
| Codex | 2026-09-27 | docs/research/mgear-custom-nodes.md | mGear公式FAQと専用ノード実装を調査。カプセル化・構築簡素化・性能・診断性の理由、IK/FK内部分岐と上流停止の違いを記録。外部コード非変更、Maya実行・計測なし |
| Codex | 2026-09-27 | docs/research/bifrost-rig-examples.md | ベルト・FABRIK・衝突変形・feedback・ML連動・追従チェーンの一次資料を調査しGit除外先へ保存。サンプル未実行、実装なし |
| Codex | 2026-09-27 | docs/research/bifrost-compatibility-2026-09-27.md | VNN Python APIを公式資料で確認。mlib設計規約を読み、任意依存の薄いBifrostラッパー案とhrigのMaya2025以降方針をローカル記録。実装なし |
| Codex | 2026-09-27 | docs/research/bifrost-compatibility-2026-09-27.md | 基礎ループと2.9以降の数学・Transform・キャッシュ機能の差を公式資料で確認し追記。実装・実機検証なし |
| Codex | 2026-09-27 | docs/research/bifrost-compatibility-2026-09-27.md | 公式リリースノートの提供対象・更新状況を調査してGit除外先に保存。実装・インストール・Maya実行なし |
| Codex | 2026-09-27 | maya/inhouse/hrig/ | モジュラーリギング用の最小パッケージ(__init__.py・README.md)を新設。既存PYTHONPATHを利用。Maya2027 mayapyでimport成功、差分チェック成功。Maya GUI未実行 |
| Claude Code | 2026-09-26 | maya/inhouse/hedit(旧HEditor)・maya/modules/hedit.mod・docs/cpp-documentation.md・CLAUDE/AGENTS/copilot-instructions・tools/build_maya_plugin.py | ユーザー指示でCodexの未コミット作業(HEditor→hedit改名・0.2.10・C++ドキュメント規約・--generate-only)をそのままコミット/push。事前に機密情報・第三者素材が無いことを確認 |
| Claude Code | 2026-09-26 | maya/modules(metahuman_for_maya.mod・pose_driver_connect.mod新設、Epic製.mod削除)・mlib/utils/{progress,optionvar,naming}.py・mlib/maths/easing.py・mlib/nodes/skinCluster.py・mlib/docs(conf.py・_static・_templates・rebuild.bat・README・development.rst)・tools/{check_mlib_docs,run_mlib_extension_gui}.py・mlib-docs.yml・HTools/rigging/{lib_/controllerShapeManager,controllerShapeManagerUI}.py・MayaCinematicCameraHUD・対応テスト・公開履歴 | 権利監査の指摘対応。第三者由来(Stack Overflow・maya-skinning-tools/Penner・cymel・paya・sphinx-autoapi・rig101・Maya devkitサンプル)のコードを独自設計で再実装し、APIを変更(progress_bar: label/width/stream、easing: ease()/CURVES、OptionVar: JSON保存・prefix必須、legalize_name: コロン区間ごと、controllerShapeManager: タブ/関数名変更)。mermaid同梱をやめjsDelivrの固定版+SRIに。Epic製.modを独自記述へ置換。公開履歴を書き換え(作者情報をnoreplyへ、調査資料・Epic .mod・mermaid・autoapiコピーを全コミットから削除)してforce push。各ツールは作業前に git fetch と reset/再clone が必要 |
| Codex | 2026-09-26 | hedit 単一画面/開き直し | 明示showで既存本文close→host非表示→同じhost再表示。取消時保持、workspaceControl非破棄で配置保持。reload時host保持/Qtツリーから回収、再入ガード、余分なhost非表示。GUI2027/2024各29成功(165032/165303)。3回連続・reload・参照消失後の同一host/未保存本文/可視host1個を検証。2024でcloseイベント3回も検証、Qt5テストの無効化ラッパーは再取得。README/構文/差分確認。Pythonのみ・再ビルド不要。今回2022/25/26のGUI再実行はなし。未プッシュ。 |
| Codex | 2026-09-26 | hedit 全版ビルド/自動ロード | 2022/24/25/26/27ビルド成功。startup.initializeでGUI時プラグイン自動ロード+メニュー、既存.mod/userSetupを利用。maya_core・永続autoload設定は非変更。全版GUI各28正常終了(164041/164229/164349/164459/164614)。単体22・移行1各版成功、standaloneロード解除各版成功(hedit-tests/164418)。旧offscreenテストがフォーカス不足で終了8→テスト側activate/focusを明示し全版0(hedit-ui-recheck/164907)。2022/Python3.7のSyntaxWarning差と旧configuration参照をテスト修正。2023未導入。GUIは隔離下で実userSetup明示実行、ユーザー外部ツール込みbat自体は未実行。README更新、未プッシュ。 |
| Codex | 2026-09-26 | hedit 名称統一 | maya/inhouse/HEditor→hedit、scripts/hedit、hedit.mod/mll/コマンド/C++名前空間/UI/テスト/READMEを変更。旧バイナリは.maya-output/hedit-legacy-binariesへ退避、配布は新名2版のみ。旧tabs/ui/preferencesを新保存先へ未存在時のみコピー、旧workspace uiScript専用heditor.restoreと旧control検出を保持。2024/27ビルド成功(既存マクロ警告)、GUI各27成功(154230/154328)。2027再起動3段階成功(hedit-startup/154417)。補完22+移行1テスト/26Python構文成功。旧ユーザー実環境からのドック移行、2022/25/26は未検証。未プッシュ。 |
| Codex | 2026-09-26 | HEditor 空画面復元修正 | 既存workspaceControlへの挿入後に親ホストもsetVisible(True)。復元先を生成前に確定、誤った親も再表示時に修復。専用reporter生成後にMayaのUI親を復元。再起動テストで従来の非表示ホストを検出し、親子関係/アクティブタブ可視を追加。2024/27の保存→再起動表示→閉じた状態の全6起動正常終了(heditor-startup/20260926_152032)、未保存Python/MEL・右ドック復元成功。2027画像確認。README/構文/差分確認。Pythonのみ変更・再ビルド不要、ユーザー設定非削除、未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.2.10 標準ログ表記 | Maya専用非表示reporterのQt文書追記を差分取得し、//・#・複数行・空行を標準通りに表示。種別通知で色/フィルタ維持、独自末尾//を廃止。専用文書5000行上限・接続解除/破棄を実装。2024/27ビルド成功(既存Qt/Mayaマクロ警告)。GUI各27項目正常終了(2027:151005、2024:151335)、読込中描画/色/解除含む。13種の標準文書完全一致:2024:151134、2027:151255。2027は5100行保持上限も成功。比較試験の初回タイマー未消化を有界一致待ちに修正。README・構文・差分確認。初回過去履歴の圧縮制約は従来通り。2022/25/26と実制作シーンは未検証、未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.2.9 読込中ログ | 25msタイマーだけでなくメインスレッドのMCommandMessage通知から最大40fpsでキュー取得/viewport再描画。mutex解放後に実行、再入防止、processEvents不使用、他スレッドは従来キュー。2024/27ビルド成功(Qt/Maya mathマクロ再定義警告あり)。GUI各27項目正常終了(2027:145134、2024:145422)、file openが戻る前の3行の本文更新とPaintを検証。2027はテスト用scriptNode、保存するテストはscriptNode不要のBeforeOpenコールバックへ変更して2024確認。READMEに他スレッド/末尾バッファの遅延制約を記載。ユーザーの実制作シーンは未検証。差分確認済み、未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.2.8 リアルタイム検索 | 検索欄textEditedで即時一致選択・件数更新。選択先頭を基準に絞込み、フォーカス維持、空欄/不一致/不正式を処理。Enter/F3は次一致を維持。2024/27ビルド成功。2027 GUI26項目正常終了(144210)、実キーh→hl→hli→mlib各段階の選択/件数/フォーカス、Enter、全削除、不一致と既存検索置換回帰成功。2024GUIは今回未実施。README/差分確認済み、未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.2.7 バー配置 | Output専用見出し/保存/クリアボタンと空欄プレースホルダーを削除、表示モードを上段アイコン直後へ移動(150px)。検索を470px、Tt/Abc/.*のフラット表示・左右矢印・小さい余白へ調整。従来のクリアメニュー/アイコン/右クリックは維持。2024/27ビルド成功、GUI各26項目正常終了(2027:143325、最終文字サイズ調整後2024:143458)。両版画像確認、検索/置換/モード/補完等回帰成功。READMEと差分確認済み、未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.2.6 Output・検索UI | Output右上にNormal/Output only/Warnings + Errors/Errors only、表示ログUTF-8保存、全モードクリアを追加。元ログ最大1Mi文字保持でモード復帰、Maya設定非変更。警告#ffff00/エラー#ff0000。検索を入力欄右上overlayへ移動、リサイズ追従、置換展開ボタン/既存検索機能維持。2024/27ビルド成功、GUI各26項目成功(2027:142204、2024:142309)、検索位置/モード復帰/保存一致/クリア/色/補完等を検証。2027画像目視。初回保存試験失敗はパスとQtダイアログ自動操作を修正。READMEに保持上限と初期履歴種別の制約を記載。差分確認済み、他ツール変更保持・未プッシュ。 |
| Codex | 2026-09-26 | HEditor サブパッケージ補完 | from . import nodesが静的解析で自己参照しmlib.nodes候補が空になる問題を修正。相対サブパッケージを直接解決、絶対再公開の自己参照を回避、TYPE_CHECKING宣言を非実行で解析。単体22件成功(別名import/未importパッケージ含む)。Maya2027 GUI24項目成功/正常終了(140437)、mlib.nodesのpopup表示とNode/Joint/SkinCluster/Transform候補を検証。Python補完のみ変更、C++再ビルド不要。差分確認済み、未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.2.5 Output・入力負荷 | 初期履歴で空行とprint断片の分断を再現。Qt文書も通知境界を含むため履歴専用の空行省略・空白通知接続を追加、ライブ空行保持。過去の任意断片/意図的空行の完全復元不可をREADME明記。補完のパス列挙を同一プロセスの背景スレッドへ移動(最短5秒)、宣言ASTキャッシュ/最大4再試行/20万文字制限、全モジュール属性の一括JSON廃止。C++で250ms debounce/全文コピー削減/入力停止1.5秒以後に復元保存。5000行構文未完成の旧相当解析1269ms→3.31ms。単体20件成功、2024/27ビルド成功。Output対象GUI2024:135222・2027:135127正常終了。最終2027:135502で遅い走査800ms注入時GUI最大timer間隔92ms、3項目成功/正常終了。初期Output画像確認。2027全体GUI23項目成功/正常終了(135548)。初回再現試験は失敗、134704は終了timeout所有PID停止。差分確認済み、他ツール変更保持・未プッシュ。 |
| Codex | 2026-09-26 | テスト時クラッシュ通知の切り分け | ユーザーがテスト中の通知と確認。通常TEMPのMayaCrashLog260926.1336/1337/1338.logはMaya2022 mayapyの終了処理(RtlExitUserProcess→DynSlice TnClothShape::sCleanupClass→属性解放)でのクラッシュ。正確な起動元・原因は未特定。HEditor対象GUIは2024/27で直近結果は正常終了、同一障害とは断定しない。調査時maya/mayapy稼働なし。既存mlibランナーはuninitialize・分離TEMP・timeout・終了コード判定あり、今回のログはその分離TEMP外。他ツール進行中の対応テストには変更せず、診断のみ共有。製品コード変更・追加Maya起動なし。 |
| Codex | 2026-09-26 | HEditor 0.2.4 Output/スペルチェック | 初期履歴をMayaのQt文書から読み余分な通知区切りを除去、CRLF正規化、分割printと意図した空行保持。Output標準12px/NoWrap、Preferencesで折返し切替、ASCIIタイトルと既存ドックlabel更新。Windows en-US辞書(COM)で表示範囲最大8000字・450ms debounce・語キャッシュ・camel/snake分割の青波線を追加、標準ON/設定保存/OFF取消。外部Python/辞書同梱なし、日本語校正/候補/ユーザー辞書未対応をREADME記載。2024/27ビルド成功、対象GUI成功・正常終了(2027:133258/11ms、2024:133350/16ms)、2027画像確認。2027全体GUI23項目正常終了(133446)、既存補完/ログ/コピー/実行/解除回帰成功。差分確認済み、他ツール変更保持・未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.2.3 補完/Output履歴 | 候補挿入中の再補完予約を抑止。初回にcmdScrollFieldReporterから最大512Ki文字のMaya保持履歴を取り込んでから購読開始、Result/Warning/Errorを//ラベル:本文//表記へ。2024/27ビルド成功、対象GUI各3項目成功(2027:123608、2024:123850):表示前履歴が1回、Result表記、mlib確定後Enter改行、次の補完。2027画像で起動ログ表示確認。両版終了60秒timeoutで所有PID監視停止、正常終了は未確認。全体GUI123113は120秒timeoutのため全体回帰成功とはしない。初期試験のMEL/API呼出を修正。READMEへ保持履歴/Charcoal独自ログの限界記載、構文/差分確認成功、未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.2.2 メニュー/ツールバー | テキストボタンをMaya同梱標準アイコンのツールバーへ変更。File/Edit/History/View/CommandのActionを共有し、開く/保存/クリア/表示切替/実行/Explorerを配置。入力消去はUndo可能、Refresh completionはCommandへ。Dark+維持。2024/27ビルド成功、GUI各21項目exit0(2027:114641、2024:114706)、2027画像で標準アイコン表示確認。入力消去Undo・表示切替と既存操作回帰成功。README/差分確認済み、未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.2.1 Output行番号 | Outputの行番号/余白を初期非表示、PreferencesのShow output line numbersで切替・保存。コード行番号維持。2024/27ビルド成功、2027 GUI20項目exit0(114351)、画像で非表示確認。設定数の既存テストを11へ更新。2024GUIは今回未実施。README更新、既存変更保持・未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.2.0・C++開発ガイド | 中断分を再開。Ctrl+G、正規表現キャプチャ置換、MEL実行/言語切替、Explorer/Open/Add Folder、タブスクロール、Windowメニュー、起動時開閉/ドック復元、アクティブPythonのみ解析を実装。VS生成バッチ/--generate-onlyを追加し生成物のGit除外確認。日本語DoxygenをHEditor C++全体へ追加、3種のエージェントMDと規約を更新。2024/27ビルド・各17単体/standalone/offscreen成功(111600)。最終GUI各20項目exit0(2024:113643、2027:113742)。Qt5で閉じたドック再生成時のクラッシュを遅延生成で修正、失敗試行の所有プロセスは監視停止。両版3プロセスの再起動試験成功(heditor-startup/113757):右ドック、未保存Python/MEL、閉じた状態を復元。通常userSetup自動呼出自体は未検証で同じinitializeを明示実行。Python21ファイル構文/差分確認成功。既存変更保持・未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.1.13行番号 | コード/出力の行番号をNumberedTextへ共通化、桁数・フォント・スクロールへ追従。本文とは別描画のためコピー対象外。2024/27ビルド成功、GUI各18項目exit0(2027:103059、2024:103254)、両版の画像で行番号表示を確認。選択/コピー/ズーム等の回帰成功、README更新、差分チェック成功。未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.1.12出力選択 | 読取専用Outputにマウス/キーボード選択とCopy/SelectAllのShortcutOverrideを明示。追記専用cursorと選択端点を分離、選択・スクロールを保持し非選択末尾時のみ追従。2024/27ビルド、GUI各18項目exit0(2027:102738、2024:102831)。ダブルクリック/Shift選択、Ctrl+C/A、日本語コピー、追記時選択保持、読取専用、過去ログ位置と末尾追従を確認。READMEと差分チェック成功。未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.1.11出力色 | 文字列判定をやめMCommandMessage種別を保持したキュー/文字書式へ変更。Warning黄・Error赤・Result緑・Info水色・History灰・Display明灰。複数行、通常色復帰、バッファ上限を維持。Qt5 QCharRef差を修正し2024/27ビルド成功。各17単体/standalone/offscreen成功(102339、結果/履歴/通常色fixture含む)、GUI各17項目exit0(2027:102403、2024:102456)、実Warning/Error/Info/printの色を検証、2027画像目視。通常printの文字列による推測はしない旨README記載。差分チェック成功。未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.1.10編集補助 | Aa/単語/正規表現検索・一致番号を追加。元テキストで一致を確定して後方から一括置換、1Undo。不正/ゼロ長/10万件超は変更前拒否、置換後方参照は非対応と明記。Viewの10〜28pxズーム/リセットとCtrl+=/-/0、ini保持を追加。2024/27ビルド成功、GUI各16項目exit0(2027:101834、2024:101932)。検索条件・折り返し・日本語置換・不正regex・Undo・倍率キーを検証、既存機能回帰成功。README更新、差分チェック成功。未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.1.9外観 | 全体の独自スタイルを除去しメニュー/タブ/ツールバー/ステータスをMaya標準へ。codeEditor/outputのみConsolas14pxとmlib Sphinx Dark+色へ限定、変数/クラスと出力警告/エラー色を追加。2024/27ビルド、GUI各15項目exit0(2027:101406、2024:101452)。両版maya-dark-plus.pngを目視確認、差分チェック成功。色分類は簡易構文解析で完全なPygments互換ではない。未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.1.8静的解析 | Maya同梱Pythonのcompileによる構文エラー/SyntaxWarning診断を追加(実行/importなし)。初期offの永続設定、800ms debounce、active tabだけ診断、off時取消、問題一覧クリックで行ジャンプ、100万文字超/2万行以上skip。型/未定義名/API検証は対象外とREADME明記。2024/27ビルド・各17単体/standalone/offscreen成功(100932)、GUI各15項目・exit0(2027:100956、2024:101049)。構文診断/修正/行移動、off時未呼出と待機取消を確認。差分チェック成功。未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.1.7補完・設定 | 補完要求ごとに対象のlive公開名とsys.pathを取得、既知ソースの変更を静的再解析、import候補の追加/削除追従。自動import/reloadなし。Edit/Preferencesに文字/ドット補完・keyword/builtin・smart indent・backspace・空白表示・保存時整形の9設定を追加しini永続化。2024/27ビルド、各13単体・standalone・offscreen成功(100515)。GUI各15項目・exit0(2027:100538、2024:100621)、設定切替・手動補完・整形Undo・ini保存を検証。比較メモはGit対象外docs/researchのみ、GUIでの外部製品操作は未実施。未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.1.6タブ復元 | Maya prefs/heditor/tabs.jsonへ1秒周期・終了通知・解除時にQSaveFileで保存。本文/パス/modified/選択/タブ順/active復元、元ファイル非更新。QLockFileで多重起動の上書き防止、不正ファイル保持と通知、保存不可時は従来の確認へ戻す。2024/27ビルド・独立GUIプロセス2回による保存/再起動復元各成功・exit0(heditor-session/095845)。初回試験はテスト側setPlainTextによるmodified解除を修正。2027既存GUI14項目成功・exit0(100036)。ロック競合/破損/ディスクエラーの実機注入は未検証。旧版から最初の更新時は手動保存が必要とREADME記載。未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.1.5部分実行 | Ctrl+Return/Ctrl+テンキーEnter/テンキーEnterをコード欄で直接処理。既存の選択のみ/未選択時全体実行を維持し、通常Enterは改行。READMEにCtrl+Lからの行実行・範囲保持・制限を追記。2024/2027ビルド成功、各GUI14項目・exit0(2024:095333、2027:095247)。実キーで実行回数・複数行選択・選択保持・全体実行・通常Enterを検証、既存補完/ログ/ドックも成功。差分チェック成功。他Maya版・標準エディタ全機能互換は未対応。未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.1.4ショートカット | VS Code系のコメント・行移動/複製/削除・インデント・行選択/コピー・Redo・検索置換・タブ操作・折り返し・保存/行ジャンプを追加。Ctrl+Enterは実行を維持。Ctrl+Wの受信と遅延破棄を調整。2024/27ビルド、各単体9件・standalone・offscreen成功(094937)、GUI各13項目成功・exit0(2024:094840、2027:095017)。実キー操作とテキストUndo確認。ファイル/行番号ダイアログ操作、他Maya版は未検証。READMEへ一覧と制限を記載、差分チェック成功。未プッシュ。 |
| Codex | 2026-09-26 | HEditor 0.1.3 UI・補完・ドッキング | 補完をMaya内の直接呼び出しへ変更しQProcess/JSONLワーカーを撤去、worker.pyをcompletion.pyへ整理。出力上・コード下、右クリックClear output、MayaQWidgetDockableMixinホストとworkspaceControl/uiScript復元を追加。Qt5のreparent時Pythonラッパー無効化に対応。2024/27ビルド、各unit9件・standalone・offscreen成功(093520)。GUI各12項目成功、両版exit0(2024:093749、2027:093827)。Maya再起動を跨ぐ編集タブ復元は未対応、同期補完中はMayaが待機する制限をREADMEへ記載。未プッシュ。 |
| Codex | 2026-09-26 | docs/research/ | 依頼された外部ツール調査を実施しGit対象外へ記録。製品コードの変更なし。 |
| Codex | 2026-09-26 | HEditor 0.1.2ログ共有・GUI検証再開 | コミット済み途中実装(Maya共通Python実行/MCommandMessage購読/UTF-8)を再起動後に検証。2027 GUI 092214・2024 GUI 092711で双方向ログ・変数共有・日本語・警告/例外・重複なし・補完/選択実行/アンロード計9項目成功、両版exit0。PySide2にqWaitがないテスト不具合をQEventLoopへ修正。Charcoal実機試験092439は未信頼プラグイン確認で停止とアクセシビリティから確認、設定を変更せず120秒監視で所有PIDのみ停止。連携未確認をREADMEに明記し未検証の試作テストは除去。今回追加分は未プッシュ。 |
| Claude Code | 2026-09-26 | pyrightconfig.json・tools/setup_maya_typings.py・.gitignore・mlib/__init__/cmds/nodes の TYPE_CHECKING・nodes/node.py・test_typing_exports.py・HTools controllerShapeManager・docs/vscode.md・CLAUDE/AGENTS/copilot-instructions | 静的解析エラーの調査と解消。原因: (1)maya.cmds/OpenMaya にスタブが無い、(2)mlib.createNode等が動的公開で名前解決できない、(3)Node.__getattr__がPlug推論でメソッド呼び出しが全て not callable、(4)extraPathsの欠落。types-maya配置・pyrightconfig集約・TYPE_CHECKING宣言と一致テスト追加で 3632件→エラー0(警告750)。HTools/rigging/lib_/controllerShapeManager.py の存在しない HTools.decorator import を mlib.decorators.undo へ修正。 |
| Claude Code | 2026-09-26 | maya/modules/mlib.mod・maya/external/mgear5・.gitmodules | mlib.modが inhouse/mlib をPYTHONPATHへ追加し標準jsonを隠していた問題を修正(mlib.jsonのloadsエラー)。mgear5をmasterの最新(5.3.5・Python 3.13対応)へ更新し、.gitmodulesのbranchをmasterへ変更。2027/2024のmayapyで import mgear と mgear.shifter.guide を確認。 |
| Codex | 2026-09-26 | HEditor 0.1.1自動補完修正 | 旧版GUIで新規タブcmds.の自動補完失敗を再現(064854)。ready後再要求、ロード済み名はディスク走査不要、常設状態表示を追加。連続更新時の候補モデル解放後参照も発見・再利用方式へ修正。テストexeのWERダイアログを出してしまったため所有テストPID停止、以後テストexeだけSetErrorModeで終了コード監視。使用中旧DLLを上書きしない版別0.1.1配置とmod/loader更新。2024/27各unit10件・standalone成功、最終C++5回連続候補更新テスト両版exit0。2027 GUIでCtrl+Spaceなしのcmds.自動表示・Enter確定等6項目成功(070108)、終了処理は60秒timeoutで所有PID停止。ユーザーMayaは保持。反映には保存後Maya再起動が必要、未プッシュ。 |
| Codex | 2026-09-26 | HEditor/tests/run_gui.py・gui_smoke.py・README | GUIテストのmodule pathをHEditorだけの一時modディレクトリに分離し起動停止を解消。GUI実機で表示/全体実行/候補表示/Enter確定/選択実行/close+unloadの6項目を2024・2027で成功、両方exit0正常終了（35.69秒・42.49秒）。画像も確認。2024: .maya-output/heditor-gui/20260926_063534、2027: 063644。終了停止があった先行回も隠さず、GUI結果と監視結果をrun-result.jsonに分離記録、timeout引数を追加。ユーザー設定・信頼設定・普段の全mod構成は変更なし。全外部ツール有効時の互換性・個別の停止原因までは未特定。未プッシュ。 |
| Codex | 2026-09-26 | maya/inhouse/HEditor・maya/modules/HEditor.mod | 独立したC++/Qtエディタ初期版を追加。VS Code風配色、タブ/行番号/UTF-8開閉保存/検索/選択実行/出力、ロード済み公開名＋別mayapyのstdlib AST補完（キャッシュ/要求統合/10秒timeout）。追加Python依存なし。2024/2027ビルド成功、各9ユニットテスト・standaloneでmod/ロード解除/実在名補完/実行・offscreenで補完挿入/実行/画像確認成功。最終フォント変更後も両UIテスト成功。結果 .maya-output/heditor-tests/20260926_062123。専用2027 GUIは制限環境exit251、通常環境もstartup120秒timeoutで所有プロセス停止、GUI内操作未確認。型推論/MEL等の制限をREADMEに記載。既存のClaude変更を保持、未プッシュ。 |
| Claude Code | 2026-09-26 | tools/run_mlib_gui_versions.py・docs/mlib-gui-testing.md | GUIテストの終了時セキュリティダイアログ(MASH userSetup.py)の原因を特定: 専用userPrefs.melにヘッダー(//Maya Preference行と optionVar -version 3)が無くMayaに無視され、SafeModeExecUserSetupScript=0が効いていなかった。ヘッダーを付与して解消(2022/2024/2025/2026は通常実行で、2027は単独実行でクリーン終了を確認)。終了待ち既定を120秒へ延長(Mayaのメモリ解放が遅く前バージョンの後始末と重なると60秒超)。 |
| Codex | 2026-09-25 | プラグイン開発基盤の情報取得 | CLAUDE/AGENTS・ビルド/devkitスクリプト・HUD CMake/.mod・VS Codeタスク・履歴を確認。--listでVS18(v142/v143/v145)と5版のMaya/devkit、2023未導入を確認。5版mll存在、HUD d5ec888でclean。記録上5版build/load済みだがbuild_maya_plugin.pyのVERIFIEDは2022/24/26のままという表示不整合を把握。今回は再ビルド・ロード・実装変更なし。 |
| Claude Code | 2026-09-25 | maya/inhouse/MayaCinematicCameraHUD(release/plug-ins/windows/2022・2024・2026) | ユーザー指示でコミット済みだった2022/2024/2026のmllを現在のソースから再ビルドし、HUDリポジトリへコミット・push。これで2022〜2027の全mllが同一ソース由来。警告0件、5版すべてmayapyでロード確認。親リポジトリのsubmodule参照も更新。 |
| Claude Code | 2026-09-25 | .gitignore・maya/inhouse/MayaCinematicCameraHUD/.gitignore, 全未コミット | C++プラグイン開発用に.gitignoreを整理(build_*/・.vs/・CMake/MSVC生成物・pdb等を除外。.mllはリリース物として無視しない。親リポジトリは.maya-output/で既にビルド/devkitを除外済み)。HUDリポジトリをコミット・push(652f21b: 警告修正・Qt6を2025以上・2025/2027ビルド追加・.gitignore)。親リポジトリは事前にrun_mlib_tests.py(新規mayapy 2027)全件成功を確認のうえ、Codexの未コミット分(mlib拡張・PoseDriverConnect mod等)も含めてコミット・push。|
| Claude Code | 2026-09-25 | maya/inhouse/MayaCinematicCameraHUD(src・CMakeLists.txt), maya/inhouse/HTools/system/checkWorkspacePluginTrust.py(新規), mlib/__tests__/test_htools_check_plugin_trust.py(新規), CLAUDE.md・AGENTS.md | ユーザー指示でHUDのコンパイル警告修正とセキュリティ警告対策。警告: Shift-JISだった4ファイルをUTF-8化(コメントのみ日本語で動作影響なし)、float→unsigned intを明示キャスト、CMakeにproject()追加・cmake_minimum_requiredを3.15へ・MSVCに/utf-8を明示(2022/2024の旧pluginEntryは/utf-8無しでC4819が出ていたため)。5版クリーンビルドでコンパイラ・CMake警告0件、各版mayapyでロード確認。セキュリティ警告: 信頼済みの場所(optionVar SafeModeAllowedlistPaths)はMayaのSafeModeがスクリプトからの変更を拒否する(追記の戻り値1・値不変・セキュリティログにreject/Deny)ことを隔離環境で確認したため、自動登録は不可と判断し迂回しない方針にした。代替として読み取り専用のHTools/system/checkWorkspacePluginTrust(inhouse配下の未登録場所を一覧しPreferencesを開く)を追加、登録手順(Preferences>Securityで手動、または警告ダイアログのApply to all plugins in this locationにチェック)をCLAUDE.mdに記載。テスト5件成功。HUD側は未コミット(CMake・ソース変更、2025/2027のmll新規)、コミット済み2022/2024/2026 mllは元に戻した。GUIでのPreferences画面表示・警告ダイアログの実挙動は未確認 |
| Codex | 2026-09-25 | PoseDriverConnect GUI/.mod検証補足 | 名前指定ロードはMetaHuman側の同名バイナリを選ぶことを確認。.modのmoduleInfoルートから対象バイナリを明示しロード元も検証するようGUIランナーを修正。standaloneで2022/24のPoseDriverConnect実バイナリ・専用取得を再確認、5版の.mod検出成功（.maya-output/mod-probe-20260925-explicit）。GUI未完了の結論は変更なし。 |
| Codex | 2026-09-25 | tools/run_mlib_extension_gui.py・GUIランナー・PoseDriverConnect.mod・README | 実.modを読む専用GUIスイートと起動診断ログを追加。Windows2024用PoseDriverConnect定義を補完。standaloneで2022/24/25/26/27の.mod検出、2022/24の名前指定プラグインロード・専用ノード取得成功（.maya-output/mod-probe-20260925）。GUIは全版試行、制限外でも再試行したがスイート開始前に停止。初回2022認証エラー、2026/27ライセンスセッション生成失敗、他は起動timeout。2024は認証通過後240秒timeout、GUI操作・画像検証未完了。全所有プロセス監視停止済み（extension-gui/20260925_225111・225310・225612・225716・225858）。監視5テスト・3.7構文・差分確認成功。既存Mayaと他ツールの変更を保持、未プッシュ。 |
| Claude Code | 2026-09-25 | tools/maya_devkit.py(新規), tools/build_maya_plugin.py, maya/modules/MayaCinematicCameraHUD.mod, CLAUDE.md, maya/inhouse/MayaCinematicCameraHUD/CMakeLists.txt | ユーザー指示で全Mayaバージョンのビルド環境を整備。Maya 2025/2027はdevkitが別配布だが、インストール先のヘッダ・lib・moc・Qt用zipから.maya-output/devkit/<年>/にローカルdevkitを自動生成する方式にした(Program Files非改変・管理者権限不要、Qt6のcmake設定が参照するbin/lib類は実物ハードリンク/空ダミーで充足)。Qt5系(2022/2024)は既存の展開済みインストール先を利用。HUDのCMakeをQt6判定を2025以上に修正。2022/2024/2025/2026/2027の5版で実ビルド成功、各版のmayapyで.mod経由のloadPlugin/unloadPlugin(ノード型CameraHud)を確認。Maya 2023は未インストールのため未対応。2025/2027のツールセット(v143/v145)は実ビルド・ロードで問題なしを確認。HUD側は未コミット(CMake修正・2025/2027のmll新規)、コミット済みの2022/2024/2026 mllは元に戻した。GUI Mayaでのロードは未確認 |
| Claude Code | 2026-09-25 | .gitmodules, maya/inhouse/MayaCinematicCameraHUD(新規submodule), tools/build_maya_plugin.py(新規), maya/modules/MayaCinematicCameraHUD.mod(新規), MayaHToolsWorkspace.code-workspace, CLAUDE.md・AGENTS.md・copilot-instructions.md | C++プラグインの編集・ビルド・ロード基盤をMayaCinematicCameraHUDで整備(mlib分離・補完エンジンは対象外)。HUDは編集対象のためinhouse配下にsubmodule追加(規則: 編集するもの=inhouse、使うだけ=external)。汎用ビルドスクリプトはvswhereでVS/CMake/ツールセットを自動検出し、ビルドフォルダを.maya-output/plugin-build配下に分離。Maya2026で実ビルド成功、.modのMAYA_PLUG_IN_PATH経由でmayapy 2026からloadPlugin/unloadPlugin(ノード型CameraHud)を確認。Maya2025/2027はdevkitが別配布のため環境変数MAYA_DEVKIT_<年>が必要。HUD側CMakeLists.txtの出力先(../release→ソース基準、/pdb→ビルド基準)を修正(HUDリポジトリ内で未コミット)。VS Codeにビルドタスクと簡易IntelliSense設定を追加。Maya GUIでのロードは未確認(信頼警告のため) |
| Codex | 2026-09-25 | mlib.extensions・mlib_posedriverconnect・mod・テスト・文書 | mlib_*自動検出、API宣言/依存確認、衝突時の拡張単位拒否、状態照会、reload対応を追加。専用scripts配置で.mod有効化、UERBFSolverNode/UEPoseBlenderNodeとUndo対応set_radiusを実装。2022/24/25/26/27各50ファイル成功（20260925_224543_566503）、2022/24は実外部プラグインで取得/Undo/Redo/reload成功。2025〜27はsix未導入のエラー隔離確認後、実ノード試験スキップ（対応バイナリも未配置）。コマンド検出単体・Sphinx -W・差分確認成功。GUI/.mod起動経路は未検証・未プッシュ。外部ソース変更なし。 |
| Claude Code | 2026-09-25 | リポジトリ全体(未コミット約110ファイル) | ユーザー指示で未コミット分(Codexの命名規則リファクタ・delete_constraints等を含む)をまとめてコミット・プッシュ。事前にrun_all_tests.pyを実行し49ファイル中48成功。test_datatypes.pyのみ失敗したが、Maya常駐セッションに残った旧`mlib_math_test`モジュールキャッシュが原因で、sys.modulesから除去して再実行すると32件全成功(コード側の問題なし)。 |
| Codex | 2026-09-25 | Transform・test_shapes_constraints・guide_nodes | delete_constraints追加。入力側constraintと経由pairBlendのみ削除、共有出力/参照/ノードロックを事前拒否。4ケースで直接接続・pairBlend・animCurve保持・拘束先保持・共有拒否・Undo/Redoを確認。2022/24/25/26/27各48ファイル成功（20260925_140508_081652）、Sphinx -Wと差分確認成功。姿勢維持/再接続なしを明記。GUI未実行・未プッシュ。 |
| Codex | 2026-09-25 | docs/mlib-api-design.md | パッケージ・Mayaコマンド・ノードファイル・その他ファイル・クラス・独自メソッドの命名規則と例を表で明文化。内容・差分確認済み。Markdownのみ、Maya実行不要・未プッシュ。 |
| Codex | 2026-09-25 | SkinClusters・テスト・Sphinx | remove_jointsをjointノードを残すinfluence解除として追加。remove_influences共通化、祖先移送/標準再配分/全解除の事前拒否、対象skin限定とUndo/Redoを検証。2022/24/25/26/27各48ファイル成功（.maya-output/version-tests/20260925_134157_977670）、Sphinx -W成功、差分確認成功。GUI未実行・未プッシュ。 |
| Codex | 2026-09-25 | docs/mlib-api-design.md・3種のAI作業ガイド | Maya照会はメソッド、保持値はプロパティの基準を具体例・キャッシュ/数学型/Plug属性アクセスの判断とともに明文化。AGENTS/CLAUDE/Copilotに同一文言で参照を追記。Markdown差分と参照先を確認。コード変更なし・Maya再テスト不要・未プッシュ。 |
| Codex | 2026-09-25 | mlib命名・公開API整理 | inputsの継承衝突解消、Joint親子名の明示、SkinClusters削除処理を_core内部へ分離、compose統合、release_srt改名、照会propertyをmethodへ変更、座標API整理、Translation/EulerRotation/NurbsCurveSnapshotとsnake_caseモジュールへ統一。呼出・例・移行表更新、旧名reload残存を解消。2022/24/25/26/27各47ファイル成功（.maya-output/version-tests/20260925_133409_544757）、コマンド自動登録検証とSphinx -Wクリーンビルド成功、公開例90ブロック構文確認。GUI2024は15件成功・終了15秒timeoutで所有プロセス停止、2022ライセンスエラー、2025起動180秒timeout、2026/27はGUI開始前終了。2023未導入、GUI画像の全数目視未実施。未プッシュ、既存変更を保持。 |
| Codex | 2026-09-25 | mlib全体・命名レビュー | Python定義を静的走査し、継承で意味が変わるinputs、SkinClustersの削除責務、Joint親子の名前返却、compose/release_srt、取得名/プロパティ/モジュールの揺れを確認。実装変更なし、Mayaテスト未実施。既存未コミット変更を保持。 |
| Codex | 2026-09-25 | mlibフラグ別名・属性別名ガイド | Mayaのコマンド別helpを初回のみ取得して8コマンドの短名を長名へ正規化。constraint/add_constraintはtyp/mo対応、bulk事前検査も対応。二重指定は本体実行前にTypeError。lsのtypでも専用コレクションを維持。標準/ユーザー定義属性の長短名を回帰検証。2022/24/25/26/27各46ファイル成功、コマンド自動登録単体検証成功、Sphinx -W成功。2023未導入・GUI未実施・未プッシュ。 |
| Codex | 2026-09-25 | mlib docstring・Sphinx全体見直し | 835関数の引数構造とArgs記載を走査、公開29ページと117コードブロックを構文確認。ベイク既定値/短縮フラグ、fastとUndo、単位、Quaternion.inverse、SDK実装済み案内、スキン復元制限、同名ノード/配列編集例、コマンド/JSON詳細を修正。主要9ガイド36例はMaya2022/2027で成功（必要な既存ノードをテスト用に用意）。28Pythonファイルはdocstring除外AST一致で動作変更なし。Sphinx -W成功、git diff --check成功。GUI/全例の副作用を伴う実行は未実施、未プッシュ。 |
| Codex | 2026-09-25 | 未コミット変更全体の公開 | ユーザー依頼でJoint回転移送/フリーズ・fastモード・viewport_offとベイク適用・テスト・ドキュメントをまとめてコミットしmainへpushする。各実装時の検証結果を引き継ぎ、差分チェック成功。 |
| Codex | 2026-09-25 | decorators/viewport・bakeResults・テスト・docs | viewport_off()をcontextmanagerで公開しbakeResultsへ適用。既存Viewport.suspendのmanage方式を再利用、batchはno-op、入れ子/元非表示/例外伝播と再実行なし。通常テスト2022/2027各45ファイル成功。2027 GUI15件成功・cleanup成功、終了は15秒timeoutで所有プロセス停止（正常終了ではない）。Sphinx -W成功。GUI画像の目視レビューは未実施。未プッシュ。 |
| Codex | 2026-09-25 | mlib値更新API・fastモード・テスト・docs | 対応するPlug/Transform/Joint/座標/色/utility/skin値更新にfast=False追加。TrueはOpenMaya直接更新でUndoなし、既存Undo設定維持。skinは未指定ウェイトを保つMPlug方式。形状は入力履歴・周期カーブを拒否。範囲/ロック/接続検査。全44ファイルが2022/24/25/26/27で成功（2023未導入）、追加8テストで値・単位・Undo履歴・bulk・API専用経路・疎なinfluence検証。Sphinx -W成功。3721頂点参考計測0.419秒→0.047秒。GUI未実行・未プッシュ。 |
| Codex | 2026-09-25 | joint.py・test_joint_orient_to_rotate.py・guide_rigging | Joint/Joints.freeze_rotation追加。R*JOをXYZのJOへ合成してrotateを0化、逆方向と検証/計算を共通化。6回転順序/2角度単位/SSC/負スケール/rotateAxisと、スキニング3方式×単体/複数でメッシュ・matrix・ウェイト・bindPreMatrix保持とUndo/Redo確認。2022/24/25/26/27全43ファイル成功、Sphinx警告なし。GUI未実行・未プッシュ。 |
| Codex | 2026-09-25 | joint.py・test_joint_orient_to_rotate.py・guide_rigging | Joint/Joints.joint_orient_to_rotate追加。R*JO合成、JOはXYZ固定・rotateOrder/角度単位対応。全対象のロック/入力接続を事前検証、姿勢と子のworld matrix保持、Undo/Redo対応。新規4テスト（6回転順序×2単位×SSC有無含む）、2022/24/25/26/27全43ファイル成功。Sphinx警告なし。GUI未実行、未プッシュ。 |
| Codex | 2026-09-25 | tools/GUIプロセス監視・検証済み変更の公開 | 起動/テスト/終了を外部監視し、終了待ち15秒で所有PIDと子のみ停止。途中例外時も後始末。専用prefsでuserSetup実行禁止、使い捨てシーンのmodified解除とMEL終了。監視実プロセステスト5件をPython3.7/3.13で成功。通常テスト各42ファイル・GUI各14件が2022/24/25/26/27で成功。最新GUI2022正常終了、24/25/26/27は終了timeoutの自動停止確認（ダイアログ完全抑止とは区別）。結果 .maya-output/gui-version-tests/20260925_085220_956484。Sphinx警告なし。ChannelBox等の画像/手動操作未確認、2023未導入。途中の手動クリック回は無人終了の証拠にしない。 |
| Codex | 2026-09-25 | tools/run_mlib_gui_versions.py・run_mlib_gui_tests.py・docs/mlib-gui-testing.md | 2022/2024/2025/2026/2027の通常テスト各42ファイル＋コマンド登録独立テスト成功。専用GUI起動ランナー追加、各14件成功・cleanup成功、各11画像で色/Undo/Redo/表示/CV選択確認。2023未導入。制限環境のライセンス起動失敗は通常環境で再実行。2024/2025/2027はテスト終了後のMaya終了が180秒timeout、専用プロセス停止（2022/2026正常終了）。ChannelBox画像・階層・通知・マウス操作等は未確認。集約結果 .maya-output/test-review-20260925.md。Python3.7構文確認。未プッシュ |
| Claude Code | 2026-09-25 | .gitmodules, maya/external/tqdm・tabulate・natsort(新規submodule), maya/modules_disabled/rich.mod・pyyaml.mod・tqdm.mod・tabulate.mod・natsort.mod(新規), CLAUDE.md | ユーザー指示で汎用Pythonライブラリ3件(tqdm、tabulate、natsort)をGit submoduleとして追加。前回追加のrich/pyyaml含め計5件について、既存の`maya/modules_disabled/`規約(未登録.modの置き場、有効化にはmodules/へ移動)に沿った`.mod`を用意(2022/2024/2025/2026/2027の各MAYAVERSIONブロック)。pyyamlはトップレベルの`yaml/`がCython版ソースで実体は`lib/yaml`だったため、PYTHONPATHを`./lib`に設定(setup.pyのpackage_dirと一致確認)。5件とも実際にsys.pathへ追加してimport成功をMaya実機で確認。CLAUDE.mdのディレクトリ構成図にmodules_disabled/を追記、外部ツール一覧を37個に更新。未コミット・未プッシュ |
| Codex | 2026-09-25 | nodes/skinCluster.py・joint.py・test_skin_weight_editing.py・guide_deformers.rst | 親へ加算してinfluence登録のみ除去、Joint.remove_influence、normalize_weights(decimals)、max_influences/set_max_influences(prune)追加。正規化OFFでも親の既存値へ加算。ロック・ゼロ合計等を事前検証、独自プラグインなし・Undo対応。Maya2022/2027一括成功（新規7ケース含む）、Sphinx警告なし。GUI未実行・未プッシュ |
| Codex | 2026-09-25 | nodes/joint.py・test_joint_delete.py | Joint.deleteを追加しJoints.deleteへ委譲。無効jointは例外。単複両入口の未スキニング・標準削除比較・親influence移送・子再親付け・Undo/Redo・失敗伝播を11件で確認。Maya2027全41ファイル成功、Sphinx警告なし。GUI未実行・未プッシュ |
| Claude Code | 2026-09-25 | .gitmodules, maya/external/rich(新規submodule), maya/external/pyyaml(新規submodule), CLAUDE.md | ユーザー指示により汎用Pythonライブラリ2件をGit submoduleとして追加(rich: Textualize/rich、pyyaml: yaml/pyyaml、いずれも直近タグ)。指示通り`maya/modules/`への`.mod`登録は行わず、起動時の自動ロード対象外のまま。CLAUDE.mdの外部ツール一覧(32→34個)に新カテゴリ「汎用Pythonライブラリ」として追記。未コミット・未プッシュ |
| Codex | 2026-09-25 | json/_editor_command.py削除・json/editors.py・JSON/Undoテスト・docs/json.rst | 独自プラグインを撤去。EditorSnapshotは保存・読込・比較のみ、applyは変更前にNotImplementedError。既存プラグインは自動アンロードしない。Maya2022の範囲Undoテスト2件をネイティブ非Undo仕様へ更新。Maya2022/2027の全41ファイル成功、Sphinx警告なし、mlib Python内のMFnPlugin/MPxCommand/MPxNode実装残存なし。GUI未実行・未プッシュ |
| Codex | 2026-09-25 | AGENTS.md・CLAUDE.md・copilot-instructions.md | 内部Mayaプラグイン禁止方針を同一文言へ統一。Undo目的も禁止、既存実装も解消対象、既存プラグインの管理APIとは区別。JSONの_editor_command.pyは残存を確認。文書のみ変更・差分確認、未プッシュ |
| Claude Code | 2026-09-25 | _core/type_hierarchy.py(新規), _core/registry.py, _core/bootstrap.py, _core/_playback_range_command.py(削除), editors/timeSlider.py, __tests__/test_registry.py・test_node_creation.py, docs/development.rst, docs/mlib-testing.md, CLAUDE.md, AGENTS.md, .github/copilot-instructions.md | cymel比較調査の残り2項目のうち、ノードタイプ継承キャッシュ(isDerivedNodeType相当)を実装。NodeRegistryにresolve_inherited_types(nodeレジストリのみ有効、plugレジストリは従来通り完全一致のみ)を追加し、完全一致が無い場合はcmds.nodeType(inherited=True)をキャッシュした継承チェーンを辿って最も近い登録済み祖先型のクラスを返す。組み込みairFieldノード(mlib未登録、transformを継承)がTransformで解決されることを実機確認。ユーザー指示により、唯一のカスタムMPxCommandだった_PlaybackRangeCommand(Maya2022のplaybackOptions非Undo対策)を削除し、mlib内で独自Mayaプラグインを用意しない方針をdevelopment.rst/CLAUDE.md/AGENTS.md/copilot-instructions.mdに明文化(理由: 初回ロード時のMaya「信頼されていない場所からのロード」警告が送信実行を止めるため)。Maya2022でのplaybackOptions変更は今後Undo非対応のまま(ネイティブ制限として文書化)。もう1項目(汎用Undo対応MPxCommand基盤)は上記方針と矛盾するため実装せず。run_all_tests.py 41ファイル中40成功(test_json.pyはCodex側未完成コードで対象外)、Sphinx `-W --keep-going`で警告ゼロ。**注意**: mlib/json/_editor_command.py(Codex進行中)も独自MPxCommandプラグインを登録しており、今回の方針と矛盾する。Codexへの反映要否はユーザー判断待ち |
| Codex | 2026-09-25 | 全変更の公開準備 | 既存実装・JSON・GUI検証基盤・ドキュメントをまとめてコミット。調査資料と生成物は除外し、研究専用の作業ログはローカル保存。 |
| Claude Code | 2026-09-25 | plugs/plug.py, nodes/reference.py, files/scene.py, files/references.py, namespaces/namespace.py, maths/quaternion.py, maths/eulerRotation.py, decorators/undo.py・__init__.py, utils/optionvar.py(新規), __tests__/test_*(新規・追加多数), docs/development.rst | 共通APIの8項目を実装。Plugの配列setAttr(scalar/length-prefixed型判定)、force接続時の一時アンロック、Reference Edits照会(edit_strings/edit_nodes/edit_attrs)・ネスト参照階層(children/root/is_root)・シーンimport(Scene.import_file)・新規reference作成(create_reference、ネスト参照混入を除外して特定)、カレントネームスペース(current/set_as_current/as_currentコンテキスト)、optionVar永続設定ラッパー(OptionVar、NUL文字はMEL文字列で切れるため専用トークンで回避)、例外時自動ロールバックのundo_transaction(空チャンクのままcmds.undo()すると無関係な直前操作を巻き戻すMaya既定挙動をダミーノード作成/削除のガードで回避)、Quaternion.to_euler()の全6回転順序対応(行列経由・ジンバルロック分岐込み、sympyで機械的に導出しom2と往復検証)、Quaternion.to_swing_twist()によるボーン曲げ/捻り分解。副産物として、EulerRotation.to_quaternion()の汎用フォールバック(xyz以外の5順序)が軸合成方向を逆に実装していた既存バグを発見・修正(xyzだけ別の閉形式式で元々正しかったため顕在化していなかった)。全項目Maya実機(om2比較含む)でテスト済み、run_all_tests.py 41ファイル中40成功(test_json.pyはCodex側未完成コードで対象外)、Sphinx `-W --keep-going`で警告ゼロ |
| Codex | 2026-09-25 | mlib/json・__init__.py・test_json.py・docs/json.rst | 型付きJSON/一時・置換保存/参照解決/事前計画/選択・属性・ポーズ・カーブ・スキン・AnimCurve・既存SDK・Editor Snapshotを追加。既存対象更新、Undo必須、単位・接続・トポロジー不一致拒否。Maya2022/24/25/26/27でJSON各14件成功+GUI1skip、2027全41ファイル成功、Sphinx警告なし。GUI送信は300秒timeoutで未確認・自動再送なし（Maya側は未キャンセル）。外部調査ログ非公開、未プッシュ |
| Codex | 2026-09-25 | tools/run_mlib_gui_tests.py・test_mlib_gui.py・docs/mlib-gui-testing.md・test_channel_box.py | GUI対象一覧と遅延実行・最終結果待機・画像保存を整備。Channel BoxのGUIテストを専用ランナーへ移管。Maya2027で13件成功、別途属性解決2件成功。色/Undo/Redo/カーブ表示/CV選択は画像確認。Channel Box画像・階層展開・通知・マウス操作・他バージョンGUIは未確認として手順化。結果 .maya-output/gui-tests/20260925_044055_827776、削除処理成功。未プッシュ |
| Codex | 2026-09-25 | Maya2027 GUI・.maya-output/gui_colors | 専用Outliner/ビューポートで赤インデックス13・RGBシアン/オレンジと文字色を描画画像で確認。解除→Undo復元→Redo解除も画像確認。Qtウィンドウ取得ではGPU部が空になるためM3dView描画バッファを別保存。検証ノード/ウィンドウを削除し選択を復元。既存シーン保存・新規化なし、検証操作はUndo履歴に残る。他バージョンGUI未検証 |
| Claude Code | 2026-09-25 | components/component.py, point_component.py, maths/matrix.py, nodes/constraint.py, nodes/node.py, nodes/skinCluster.py, namespaces/namespace.py, cmds/setKeyframe.py, cmds/select.py, cmds/outliner.py, cmds/viewport.py, editors/_editor.py, selection.py | mlib全体(nodes/plugs/components/maths/files/namespaces/plugins/editors/decorators/cmds/utils/_core)のdocstringを5並列agentで実装と突き合わせ監査、実際に食い違っていた14箇所を修正(主にRaises記載漏れ、move_attributeの説明範囲誤り、「scene.namespace」という旧パッケージ名を指す誤ったコメント3箇所、Selectionの重複排除の未記載)。run_all_tests.py 40ファイル中39成功(既知の無関係な失敗のみ)、Sphinx `-W --keep-going`で警告ゼロ |
| Claude Code | 2026-09-25 | nodes/animCurve.py（読み取りのみ、Maya実機検証） | 前タスクで疑ったAnimCurve.infinity()/set_infinity()の数値マッピング(値2欠番)を調査した結果、誤検知と判明。Mayaのpre/postInfinity属性自体が`attributeQuery(listEnum=True)`で`Cycle=3`と明示的に2を欠番にしたenumであることを実機のsetAttr/getAttr往復で確認。mlibの既存実装は実際のMaya enumと完全一致しており修正不要。コード変更なし |
| Codex | 2026-09-24 | nodes/skinCluster.py・node.py・test_influences_colors.py・docs | add_influencesをウェイト0・重複除外・全対象事前検査で追加。Outliner RGB、overrideインデックス/RGB/無効化・取得をNodeに追加、Undo対応。正規化3モード×最大influence制限有無で非正規化を含む既存rawウェイト保持を検証。2022/2024/2025/2026/2027各39ファイル成功（.maya-output/version-tests/20260924_234032_392735）、Sphinx警告なし。2023未導入、GUIの色表示は未検証・未プッシュ |
| Codex | 2026-09-24 | editors/timeSlider.py・_core/_playback_range_command.py・nodes/transform.py・test_version_compatibility.py・docs/mlib-testing.md | 2022のplaybackOptions非Undoをcmds実行専用MPxCommandで補完。同一親/既にworldの非インスタンス親変更をno-op化、無効ノードの例外維持。2024以降も再生範囲の自動拡張を明示編集してUndo復元。reload後Undo・Redo・親変更回帰テスト追加。2022/2024/2025/2026/2027各38ファイル成功、2023未導入。結果.maya-output/version-tests/20260924_233304_782360。Sphinx警告なし、GUI除外・未プッシュ |
| Codex | 2026-09-24 | tools/run_mlib_tests.py/.bat・test_run_mlib_tests.py・docs/mlib-testing.md・README.md | Maya2022～2027を個別/一括mayapy実行する環境を追加。ユーザー設定分離・英語固定・実バージョン照合・タイムアウト・結果JSON/ログ保存。ランナー4テスト成功。実行結果:2025/2026/2027各37ファイル成功、2022はedit_undo/shapes_constraints失敗、2024はshapes_constraints失敗、2023未インストール。詳細.maya-output/version-tests/20260924_232219_690401。GUI/外部投稿等の除外は明記。mlib互換性修正は未実施・未プッシュ |
| Codex | 2026-09-24 | nodes/blendColors.py・test_blend_colors.py・docs/blend_colors.rst・usage.rst | BlendColorsを自動登録。入力色/補間係数の設定・Plug接続・出力取得を追加。Maya2027 standalone37ファイル失敗なし（新規3件で補間・Undo/Redo・接続置換・不正値検証、GUI専用1ファイル除外・1件スキップ）、Sphinx警告なし。GUI未検証・未プッシュ |
| Codex | 2026-09-24 | animation/・cmds/drivenKey.py・test_driven_key.py・docs/driven_keys.rst・usage.rst | DrivenKey/DrivenKeysとmlib.drivenKeyを追加。関係取得・カーブ照会・キー設定・駆動先からの検索・一括編集に対応。単位変換とblendWeightedの入力を走査、未知の接続編集は拒否。キー更新後の評価キャッシュをdgdirtyで更新。Maya2027 standalone36ファイル失敗なし（新規5件、GUI専用1ファイル除外・1件スキップ）、Sphinx警告なし。GUI未検証・未プッシュ |
| Codex | 2026-09-24 | nodes/skinCluster.py・test_dag_pose.py・docs/dag_pose.rst | ユーザー指示でbind_pose/restore_bind_pose/reset_bind_poseを追加。復元は全メンバー、更新は当該influenceのみ、bindPreMatrix不変。SkinClusters自動転送・Undo/Redo・未接続例外・更新範囲を検証。Maya2027 standalone35ファイル失敗なし（GUI専用1ファイル除外・1件スキップ）、Sphinx警告なし。GUI未検証・未プッシュ |
| Codex | 2026-09-24 | nodes/dagPose.py・test_dag_pose.py・docs/dag_pose.rst・usage.rst | DagPoseの保存/復元/更新・メンバー編集・行列照会・skinCluster接続照会を追加。既存skinCluster.pyは競合回避で編集せず、取得はDagPose.from_skin_clusterで提供。Maya標準のRedo時名前空間脱落をrename分離で回避。Maya2027 standalone35ファイル失敗なし（DagPose7件成功、GUI専用1ファイル除外・1件スキップ）、Sphinx警告なし。GUI未検証・未プッシュ |
| Codex | 2026-09-24 | .github/workflows/mlib-docs.yml, tools/check_mlib_docs.py, tools/docs-browser-requirements.txt, mlib/docs/_static/custom.css | 公開前後のChromiumテスト(PC/モバイル各4ケース)、コミット・HTML/JS/CSSハッシュ確認、失敗注記・画面・trace保存を追加。実検証で見つかったモバイル固定幅によるクリックずれを修正。187c1a4のActions run 36007110999でbuild/deploy/verify-publication全成功。認証情報の取得は承認審査拒否で未実行、公開APIの注記で診断完了 |
| Codex | 2026-09-24 | mlib/docs/_mermaid_classes.py・class.rst | 各クラス継承図と全体図へ相対リンク追加。85クラス・332リンクのHTMLとアンカー検証、Sphinx警告なし。外部クラスにはリンクを生成しない。実ブラウザでのクリック未検証 |
| Codex | 2026-09-24 | mlib/docs/getting_started.rst, guide_*.rst, usage.rst, index.rst | 入門を92行に縮小、詳細を11ページへ分割。36節・Python39例を保持して機能別ガイドへ整理。Sphinx警告なし・差分検査済み。コード変更なし、Maya再実行なし |
| Codex | 2026-09-24 | mlib/docs/installation.rst | 指定された閲覧・自動公開・手動再公開の3節を削除。Sphinx警告なし、生成HTMLから削除を確認。公開ワークフロー自体は変更なし |
| Codex | 2026-09-24 | mlib/docs/common_methods.rst, index.rst, matrices.rst | 共通処理ページ自体を削除、目次・関連リンクも除去。クリーンビルド警告なし、旧HTML・検索項目が残らないことを確認 |
| Codex | 2026-09-24 | .gitignore・公開ドキュメント・作業ガイド | 調査資料をローカル保持しGit追跡・Sphinx公開から除外。使用方法の説明は保持。再登録防止ルール追加、クリーンビルド警告なし・検索とダウンロード非掲載確認。履歴書換えなし |
| Codex | 2026-09-24 | mlib/docs/conf.py | docs補助モジュールの検索パスを明示。GitHub Pagesと同じルート起点のSphinx -E -a -Wビルド成功。行列ガイド・継承図は8df225bでorigin/mainへpush済み、この修正も追送 |
| Codex | 2026-09-24 | mlib/docs, Git | 行列ガイド・各クラス継承図更新をコミット対象に集約。Sphinx警告なし・差分検査済み、origin/mainと同期確認。ユーザー指示により本コミットをpushする |
| Codex | 2026-09-24 | mlib/docs/_mermaid_classes.py, _templates/autoapi/python/class.rst | 既存継承図に見出し・矢印説明と直接派生クラスを追加。全85クラスHTMLとAnimCurve8派生・Joint祖先を検証、Sphinx警告なし。ブラウザのfile URLはポリシー拒否のため描画未検証。未プッシュ |
| Codex | 2026-09-24 | mlib/docs/matrices.rst, index.rst, getting_started.rst | 行列取得・Plug・合成分解・積と逆行列・座標変換・適用・API変換のガイド追加。Maya2027 standaloneで掲載8ブロックと数値結果・Undo確認、Sphinx警告なし。GUI未検証・未プッシュ |
| Codex | 2026-09-24 | mlib/docs, nodes/node.py, cmds/setKeyframe.py | 使用例をplug()に統一、attr()説明はplugへの互換参照に集約。Nodeのdocstring除外AST一致、Sphinx警告なしで再ビルド。処理変更なし・Maya未実行。未コミット |
| Claude Code | 2026-09-24 | maya/inhouse/mlib/docs/conf.py, _mermaid_classes.py(新規), _templates/autoapi/python/class.rst, development.rst, _static/mermaid.min.js・mermaid.css・mermaid-init.js(新規), .claude/launch.json(新規), .gitignore | 各クラスページに継承チェーンのMermaid図を追加(astのみで静的解析、mlib/Mayaはimportしない)。development.rstに全85クラスの全体クラス図を追加(サブパッケージ単位でnamespace分け)。ベースクラスへのリンクは既存のlink_objsをそのまま使用(図自体はクリック不可、視覚的な補助)。mermaid.jsは_staticにバンドルしCDN依存なし。classDiagramのclassDef複数プロパティがパースエラーになる不具合を回避、SVGサイズがコンテナ幅に潰れる問題をJSで実サイズ指定して解決。Sphinx `-W --keep-going`で警告ゼロを確認、ローカルhttpサーバー+ブラウザでMermaid実描画(テキストラベル・寸法)を確認 |
| Claude Code | 2026-09-24 | maya/inhouse/mlib/docs/_templates/autoapi/python/class.rst | 「ベースクラス:」行が常にプレーンテキスト`:py:obj:\`...\`` のまま表示され、実際にはリンクになっていなかった既存バグを修正(自分の直前作業でraw::htmlブロックに適用したのと同じ原因: `.. py:class::` 直後の空白テンプレート行がJinjaのtrim_blocksで消費され、後続の「ベースクラス:」行がシグネチャの続きとして誤認識され、role記法が一切解決されていなかった)。obj.bases if-block内に明示的な空白行を追加して修正。Joint等で実際にクリック可能なリンク(`<a href="../transform/Transform.html#...">`)になることをブラウザで確認、bases無し/外部クラス(logging.Handler)のケースも回帰なし、Sphinx `-W --keep-going`で警告ゼロ |
| Codex | 2026-09-24 | mlib/_core/collection.py, nodes/joint.py, nodes/skinCluster.py, plugins/plugin.py, __tests__/test_bulk_collections.py, docs/bulk_collections.rst, docs/index.rst | Joints/SkinClusters/Pluginsに単体公開APIの同名一括呼び出し、読取プロパティ列、call_each・sliceを追加。固有メソッド維持。dump/load_weightsは要素別パス指定のみ。Maya2027 standalone317成功・GUI1件スキップ、Sphinx警告なし。Pluginロードはmock境界検証。未コミット |
| Codex | 2026-09-24 | mlib/components/component.py, point_component.py, uv.py, __tests__/test_component_collections.py, docs/component_collections.rst, docs/index.rst | Vertices/CVs/UVsの位置取得・同一座標設定・保持順座標設定、XYZ/UV軸の一括編集とfull_names追加。Edges/Facesは既存vertices経由で対応。ノード系コレクションは対象外。Maya2027 standalone313件成功・GUI1件スキップ、Sphinx警告なし。未コミット |
| Claude Code | 2026-09-24 | maya/inhouse/HTools/rigging/advancedOrientJointUI.py | 新設した`preserved_skin_shape`をこのツールに適用。手動の`_preserve_enable/restore_move_joints_mode`/`_preserve_recache_bind_matrices`/`_compute_skin_clusters_from_joints`(自前実装)を削除し、mlib版へ置き換え。実UI経由(joint+skinCluster+mesh)でjointOrient変更後もメッシュ頂点が完全に不動であることを確認、run_all_tests.pyも既知の無関係な失敗以外は全て成功 |
| Claude Code | 2026-09-24 | maya/inhouse/mlib/decorators/skin.py(新規), decorators/__init__.py, __tests__/test_decorators.py | skinCluster変形を保ったままjointの姿勢を編集する`preserved_skin_shape`を追加(moveJointsMode+recacheBindMatrices、HTools/rigging/advancedOrientJointUI.pyと同じMaya標準機構)。頂点位置編集は既存のcmds.xformベースVertex/CV.set_positionで既に安全と確認。16テスト成功、run_all_tests.pyでも既知の無関係な失敗(test_channel_box.py)以外は全て成功 |
| Codex | 2026-09-24 | mlib/nodes/joint.py, nodes/skinCluster.py, __tests__/test_joint_delete.py | 直前の仕様を更新。同じskinClusterの祖先influenceがある場合のみ加算し、それ以外はcmds.deleteの標準処理へ委譲。単一influence・親なし・混在skinで標準削除と比較、Undo/Redo確認。レイヤー検出の不要なPlug生成を除去。Maya2027 standalone32ファイル失敗なし（GUI1件スキップ）、Sphinx警告なし。未コミット |
| Codex | 2026-09-24 | mlib/nodes/joint.py, nodes/skinCluster.py, __tests__/test_joint_delete.py | Joints.deleteが未スキニング・ルートjointも削除し、子Transformを親/worldへ退避。全skinの移送先を事前検査、実行失敗は対象・段階付きRuntimeErrorで伝播（自動ロールバックなし）。Maya2027 standaloneで32テストファイル失敗なし・GUI1件スキップ、Sphinx警告なし。未コミット |
| Codex | 2026-09-24 | joint.py / skinCluster.py（読み取りのみ） | Joints.deleteのウェイト移送・influence解除・子joint再親付け・削除条件を確認。移送先なしのskinClusterが予定数から除外される点も説明。実装変更・Maya実行なし |
| Codex | 2026-09-24 | maya/inhouse/mlib/nodes/animCurve*.py, nodes/blendWeighted.py, __tests__/test_animation_nodes.py, docs/animation_nodes*.rst, docs/index.rst | 連携ルール確認時に直前の完了作業を追記。AnimCurve基底・8具象型とBlendWeighted、Undo対応編集を追加。Maya 2027 standaloneで既存分含む299テスト成功・GUI1件スキップ、Sphinx警告なし。未コミット |
| Codex | 2026-09-24 | maya/inhouse/mlib/editors/channelBox.py, editors/__init__.py, selection.py, cmds/channelBox.py, cmds/captureSelection.py, __tests__/test_channel_box.py, __tests__/test_selection.py, docs/selection_and_channelbox.rst | 連携ルール確認時に完了作業を追記。ChannelBoxとSelectionを追加。選択復元・Undo・属性解決をstandaloneで検証。ChannelBoxの実UI選択・解除は未検証。未コミット |
| Claude Code | 2026-09-24 | maya/inhouse/mlib/nodes/node.py, skinCluster.py, maths/matrix.py, maths/easing.py(新規), utils/naming.py(新規), plugs/plug.py | 属性並び替え(move_attribute)・非線形ウェイト再分配(redistribute_weights)・行列ミラー(Matrix.mirrored)・名前サニタイズ(legalize_name)を追加。plug.py の attrType() 呼び出し漏れバグを修正 |
| Claude Code | 2026-09-24 | WORK_LOG.md(新規), CLAUDE.md, AGENTS.md, .github/copilot-instructions.md | Claude Code/Codex/Copilot並行運用のためのハンドオフファイル(WORK_LOG.md)を新設し、3つの指示ファイルに参照ルールを追記 |
