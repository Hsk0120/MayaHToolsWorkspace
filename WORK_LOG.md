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

## 完了履歴

| ツール | 完了日時 | 対象範囲 | 内容 |
| --- | --- | --- | --- |
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
