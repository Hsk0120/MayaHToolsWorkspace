# GitHub Copilot 作業ガイド

## 基本方針

- hlibの公開フォルダは `cmds`・`nodes`・`plugs`・`components`・`maths`・`common`・`json` とする。シーン状態・関係、Maya標準UI・表示色、作業環境・導入状態、イベント・遅延実行、汎用処理は `common` 直下へ置き、領域別のサブフォルダは増やさない。通知は直下の `logger.py`、デコレーター・コンテキストマネージャーは直下の `decorator.py` に置く。内部基盤は `_core`、文書は `_docs` とし、`hlib_*` もこの責務の分類に合わせる。

- `Object` (`_core/object.py`) は単数の `Node`・`Plug`・`Component` の共通基底と種類判別の入口。取得は `from hlib._core.object import Object` とし、ルートへの再公開は行わない。各型の入力解決は各基底クラス、複数入力の検証は `Nodes` に集約する。数学値・コレクション・UI・保存データを無理に継承させない。旧 `general`・`_core/coerce.py` の互換入口は置かない。拡張管理の正式入口は `from hlib._core import extensions` とし、ルート属性や旧モジュールパスは残さない。

- hlibではQt関連ライブラリ（PySide/PyQt/shiboken/qtpy等）をimportしない。Maya標準UIはcmds/melとMayaの通知APIで扱い、Qtウィジェット取得・変換は利用側のUIパッケージに置く。

- hlibの日本語表記では、Mayaのattributeを「アトリビュート」と呼ぶ。説明・docstring・コメント・メッセージで統一し、API識別子は変更しない。

- hlibのクラス実装は原則1クラス1ファイルとする。ただし単数クラスと対応する複数クラスは、単数形の同じファイルにまとめる（例: joint.pyのJoint/Joints、vertex.pyのVertex/Vertices）。既存の分離済みクラスをこの規則だけで移動する必要はない。

- Aiderへの実装委譲は行わない。Maya開発時のGPU・メモリ競合を避けるため、ローカルOllamaも作業のために自動起動・モデルロードしない。実装・レビュー・検証は担当エージェントが直接行う。ユーザーが明示的に再開を指示するまで、この方針を維持する。

- C++の内製コードは日本語のDoxygen形式（`@brief`・`@param`・`@return`、必要時`@note`）でファイル・クラス・全ての名前付き関数を説明する。初心者が追えるよう、所有権・Qtシグナル/スロット・非同期処理・Maya呼出の理由もコメントする。引数や戻り値がないタグは省略し、自明な各行の逐語説明は避ける。PythonはGoogle形式docstringを使用する。詳細は `docs/cpp-documentation.md` を参照する。外部submoduleへ一括適用しない。

- hlibのAPIは「Mayaへ問い合わせる操作はメソッド」「保持する値はプロパティ」を基本とする。シーン更新は明示的なメソッドで行う。具体例と判断基準は `docs/hlib-api-design.md` を参照する。

- 外部ツールの調査メモ・比較表・候補一覧・調査インベントリは `docs/research/` にローカル保存し、Gitへ登録・プッシュしたりSphinxへ掲載したりしない。公開ドキュメントには実装済み機能の仕様・使い方を記載する。

- このリポジトリでの説明・作業報告は日本語で行う。途中経過の報告・質問・確認・最終報告を含め、ユーザーへの返答はすべて日本語にする。英語の資料やツール出力を読んだ後、長い作業の途中、文脈が要約された後でも英語に切り替えない。コード・コマンド・識別子・ログの引用はそのままでよい。
- Claude Code / Codex / GitHub Copilot を並行運用する前提のリポジトリ。作業開始前に
  `WORK_LOG.md` を確認し、他ツールが進行中の範囲と重ならないか確認する。作業開始時に
  「進行中」へ自分の行を追加し、完了時に「完了履歴」へ移す(運用ルールは同ファイル参照)。
- 変更前に対象ファイルと近傍の実装・テストを確認し、依頼に必要な範囲だけ変更する。
- 既存の変更、未追跡ファイル、submodule の状態を保持する。無関係な修正や一括整形を行わない。
- 仕様や実行方法は `README.md` と `docs/vscode.md`、既存の実装を確認して判断する。
- Mayaで未実行の処理を動作確認済みと報告しない。

## プロジェクト構成

- `maya/inhouse/HTools/`: Mayaメニューから起動する内製ツール。
- `maya/inhouse/hlib/`: Maya API 2.0 のノード・アトリビュートラッパー、数学型、共通ユーティリティ。
- `maya/inhouse/MayaCommandPorts/`: GUI起動時のcommandPort初期化。HTools/hlibとは独立。
- `maya/inhouse/MayaCinematicCameraHUD/`: C++プラグイン(別リポジトリのsubmodule)。ビルドは `tools/build_maya_plugin.py`、ロードは `maya/modules/*.mod`。
- `maya/inhouse/integrations/`: Slack、mGearなどとの連携。
- `maya/external/`: 外部ツールのGit submodule。原則として直接編集しない。
- `maya/modules/`: Maya用 `.mod` 定義。
- `maya/maya_core.bat` と `maya/maya_*_en.bat`: Mayaの起動環境設定。
- `tools/send_to_maya.py`: 保存済みPythonファイルを起動中のMayaへ送信。

## 実装ルール

- Maya依存コードでは既存の `maya.api.OpenMaya`、ラッパー、共通ヘルパーを優先して再利用する。
- `hlib` の公開名は各パッケージの `__init__.py` で明示する。`nodes`・`plugs`・`components`・`maths`・`json`・`cmds` とルート関数は通常のimportと `__all__`、`common` は遅延公開用の `_exports` と `if TYPE_CHECKING:` を更新する。追加・削除後はMaya不要の `python tools/check_hlib_exports.py` で公開漏れを検査する。
- Node/Plugの型対応は `nodes/__init__.py`・`plugs/__init__.py` の `_WRAPPER_CLASSES` 辞書へ明示する。公開名の宣言と型対応を分け、登録済み型からのラッパー選択は既存の `_core/registry.py` の規則を維持する。デコレーターやモジュール走査で公開・型対応を追加しない。
- 複数形クラスの公開メソッドは通常の `def` で明示し、共通の引数検証・保持順実行・Undo処理へ委譲する。単数APIの自動全公開は行わず、既存の引数・戻り値・専用集約処理を維持する。
- `hlib/maths/` の値型は OpenMaya API 2.0 の型を継承する(Vector/Translation/Scale/Shear は `om2.MVector`、Quaternion は `MQuaternion`、EulerRotation は `MEulerRotation`、Matrix は `MMatrix`)。演算の意味は om2 に合わせ、値は可変・ハッシュ不可。Maya に依存しない純粋な値型へ戻さない(`easing` だけは標準 `math` のみ)。詳細は `hlib/_docs/guide_maths.rst` と `api_naming.rst` の意味の変更の一覧。
- シーンを変更する処理は既存のUndo対応に従い、必要なら `hlib.decorator` を使う。
- HToolsの新規ツールはカテゴリ内の既存パターンと動的メニュー登録の条件に合わせる。
- UIはPySide6優先、PySide2フォールバックを維持し、対象MayaのQtで利用できるAPIだけを使う。
- 相対リソースパスは `__file__` を基準にする。ユーザー環境の `Maya.env`、認証情報、トークンを無断で変更・記録しない。
- Slackなど外部サービスへ実際に送信する処理は、明示的な依頼なしに実行しない。
- hlib内では独自のMayaプラグインを実装・同梱・自動ロードしない。`MPxCommand` / `MPxNode` / `MFnPlugin` による登録は、Undo対応やバージョン差の回避目的でも追加しない。既存の内部プラグインもこの方針の解消対象とし、残存している場合は未対応箇所を明記する。Maya標準コマンドと既存のUndo可能な処理を優先し、実現できない機能は制限・未対応として明示する。`hlib.common`による既存プラグインの状態照会・明示的なロード管理は、この禁止の対象に含めない。

## MayaとVS Codeの実行

- Mayaは `maya/maya_<version>_en.bat` から起動する。対象バージョンのインストールを確認する。
- VS Codeでは `MayaHToolsWorkspace.code-workspace` を開き、Maya GUIを起動してから保存済みPythonファイルを `Ctrl+Shift+B` で送信する。
- `mayapy.exe` は送信スクリプトを実行するだけで、対象コードは `localhost:7002` 経由で起動中のMaya GUI内に実行される。
- import済みモジュールは自動リロードされない。必要な場合は `hlib.reload()` を使用する。
- 送信の終了コードは、正常終了0、対象コードの例外1、接続・ファイル等の失敗2。タイムアウトしてもMaya側の処理がキャンセルされたとは限らない。

## 検証

- リポジトリに通常のpytest/CI工程があるとは仮定しない。対象ファイルの既存テストと実行方法を確認する。
- 数学型の変更は `maya/inhouse/hlib/__tests__/test_datatypes.py` をMaya経由で実行する。
- Maya依存コードは通常のPython環境でimportできると仮定せず、必要なら構文チェックとMaya内実行を分けて報告する。
- UI・起動処理の変更では、対象Mayaでの起動、メニュー表示、操作結果を確認する。
- 静的解析(Pylance/pyright)の設定はリポジトリ直下の `pyrightconfig.json`。`maya.cmds` 等の補完は `python tools/setup_maya_typings.py` で `typings/maya/`(Git対象外)へ型スタブを配置して有効にする。スタブ起因の指摘は警告扱いで、エラーは実際の誤り。詳細は `docs/vscode.md`。
- 静的解析には通常の明示importを公開と補完の共通入口として使う。`common` だけ遅延公開用の `_exports` と `if TYPE_CHECKING:` を両方更新する。`test_typing_exports.py` と `tools/check_hlib_exports.py` で不一致を検査する。
- 変更後は可能な限り対象を絞った検証を先に行い、実行できなかった検証項目と理由を明記する。

## Gitと外部依存

- 作業開始時に `git status --short` で既存の変更を確認する。
- `maya/external/` はsubmoduleであるため、変更が必要な場合は対象submoduleのガイドと状態を確認し、親リポジトリの参照更新と区別する。
- `git reset --hard`、`git checkout --`、コミット、ブランチ作成は明示的に依頼された場合だけ行う。
- `.maya-output/` の実行結果は生成物であり、コミット対象にしない。

## リグ検証の共通ワークフロー

リグの動作・計算を検証してユーザーへ見せる場合は、Codex・Claude Code・GitHub Copilot共通で、次の順序を標準とする。詳細と既存ツールの使い方は `docs/verification-videos.md` を参照する。

1. **検証リグを作成する**: 専用のMaya GUIと検証シーンを使い、期待する挙動が伝わる最小構成を作る。入力と補正後を色分けし、カメラを固定する。境界に達する動き・境界を超える入力・安全範囲への復帰を含める。作業中のユーザーシーンを破棄しない。
2. **計算式と数値を文字で表示する**: MayaのHUD等、録画対象のmodelPanelに映る表示を使う。式、変数の意味、単位、角度の基準、固定値、各フレームの入力値と実際のDG出力を表示する。度とラジアンを区別し、見やすい順序・文字サイズ・配置にする。固定の値は固定と明記し、実際に変化する値を毎フレーム更新する。
3. **動画を撮影して検証する**: `tools/verification_video.py` の `recordVideo()` を基本に、実際のMaya表示を録画する。動画と診断JSONを `.maya-output/verification/<実行ID>/` に保存する。数値判定と、完成MP4の実フレームで文字の可読性・数値の変化・動作を確認する。判定用の計算はリグ本体への追加と区別する。失敗は失敗として報告する。
4. **Google Driveへアップロードする**: 接続済みのDrive機能で、確認したMP4を `Maya検証動画` 内の対象フォルダへ保存する。新規動画を「リンクを知っている全員・閲覧者」に設定し、既存の別ファイルの権限は変えない。メタデータでサイズ・閲覧URL・共有権限を読み戻し、`attachDrive()` でローカル結果に登録する。
5. **閲覧リンクを報告する**: Driveが返したURL、動画内の色・数値の意味、検証結果と制限を簡潔に伝える。再生処理中ならその状態を伝え、iPad実機で未確認なら確認済みとしない。

このワークフローはユーザーが希望する通常のリグ検証成果物の流れとして扱い、毎回録画・Drive保存を提案だけで終えない。ユーザーがローカルのみ等を指定した場合はその指示を優先する。Drive接続や共有操作が使えない場合もローカル録画・検証まで進め、未完了の工程と理由を報告する。認証トークンをコード・ログへ保存せず、コネクター認証をスクリプトへ流用しない。動画・画像連番はGitやGitHub Pagesへ登録せず、Sphinx掲載やコミット・プッシュは別の依頼として扱う。
