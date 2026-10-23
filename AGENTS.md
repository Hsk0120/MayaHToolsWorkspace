# Codex 作業ガイド

## 基本方針

- 2026-10-23のユーザー指定により、追加縮小案の上2つを適用する。AddDL/AddDoubleLinear/MultDL/MultDoubleLinear/BlendColors/BlendWeighted/Clamp/Condition/MultiplyDivide/PlusMinusAverage/RemapValue/Reverse/SetRange/UnitConversionは既存基底・公開クラス・型登録を維持し、専用の取得/設定/接続/検証/enum/複合操作APIを提供しない。操作はMaya標準アトリビュート名の`getPlug`とPlugの公開APIを使う。判定のis省略入口は廃止し、`isValid`等の正式is名へ統一する（module関数`undo.enabled`も廃止し`undo.isEnabled`を使う）。旧互換入口と省略名へのSphinx投影は残さない。Maya/OM2標準名、他クラスの同名API、対象外の演算ノードと行列/TRS、専門編集/保存/小便利機能は維持する。ノード/メソッド追加・型登録・複数形/reload/拡張自動探索と保持APIの引数・単位・所有権・返却・通常Undo/fastは維持する。

- 2026-10-23のユーザー指定により、機能縮小案A・Bを適用する。mlibはNode/Plug/Component/数学型と隣接基盤へ絞り、汎用UI、OptionVar/Preferences、型付きJSON・Snapshot、Colorと専用色操作、Scene/Workspace/FBX、mlib版OBBを提供しない。`mlib.json`と旧保存形式の読込保証は終了し、旧import・互換別名・readerを残さない。mlrigの通常JSON文字列は標準`json`、GUI名と標準Editor起動は利用側のcmds/mel、表示色はPlugで扱う。`viewportOff`の表示停止/復帰はdecoratorで維持する。`mlib.cmds`とルート再公開は`getNode/getPlug/createNode/ls/delete/duplicate/select`の7入口に限定し、他のMayaコマンドは利用側で直接使用して必要な戻り値をmlib参照へ変換する。CのMesh.reorderVertices/DagPose.mergeは維持する。数学所有権・単位・保持APIの引数/返却・複数形/reload/拡張自動探索・通常Undo/fastは維持する。

- 2026-10-23の保守性整理により、`AimConstraint.getSettingPlugs`は廃止し保存対象の選定を`mlrig.setups.AimAxisConversion`へ移す。`DecomposeMatrix.getOutputPlugs`、`AngleBetween/DistanceBetween.getOutputPlug`、`VectorProduct.getNormalizeOutputPlug/getOutputPlug`、`AnimCurve.getDriverPlug/getOutputPlug/getDrivenPlugs`は廃止し、Maya標準名の`getPlug`と既存の接続照会へ寄せる。旧別名は残さない。ArrayPlugの`getIndices()`は`getElements()`と同じ既存要素の論理番号を未評価で返す。追加縮小の14型を除く演算ノードの検証/複合処理とBlendShapeのalias投影は維持し、列挙・範囲照会・頂点集約は既存基盤へ委譲する。

- 2026-10-23のユーザー指示により、10/22の複雑性調査の整理案を実施する。対象仕様への明示的な変更として、`mlib.getAttr`は廃止し、参照は`getPlug`・値は`Plug.get`・状態は専用照会へ分ける。`ArrayPlug.getElement`は既存要素の取得のみとし`create`引数と`addElement`を廃止、未作成参照は`[]`・作成は`set/connect`で扱う。generic/kAnyは参照取得時に値評価せず基底Plugとし、実値の型解釈は`get`時に行う。`disconnect`は接続元参照の切断に限定しbool方向指定と`dst`を廃止、方向解除は`disconnectAll`へ寄せる。Joint/Jointsの`delete`はMaya標準削除とし、旧ウェイト移送・子階層保持は`mlrig.setups.JointHierarchy.delete`へ移す。これら以外の確定引数・単位・返却、Transformの`get/safe/at/ra/r/jo`、数学値の所有権、fast継承、複数形/reload/拡張自動探索は維持する。`moveAttrOrder`は定義と接続を保全し、Undo無効/fast文脈では破壊的処理前に拒否する。

- 2026-10-11のユーザー指示により、ライブラリの正式名は `mlib`、拡張は `mlib_*` とする。旧パッケージ名のimport互換・別名は設けない。拡張宣言は `MLIB_EXTENSION_API` とし、旧宣言の互換入口は提供しない。その他の公開APIの引数・戻り値・意味は維持する。

- 2026-10-06にユーザーが指定した命名規則: mlib独自の取得/設定メソッドはget/set、メソッド内のアトリビュート名はAttr/Attrs、追加アトリビュートはExtra、型変換はasに統一する。getT/setT等の短縮アクセサーは使用しない。数学型はコピー操作と自身更新を併存し、独自APIの自身更新にはItを付ける。OpenMaya標準名と演算条件は維持し、対応する数学値の戻り型はmlib型へ統一する。引数の長短別名と適用例外の詳細は `docs/mlib-api-design.md` を参照し、今回確定した仕様も下記の変更禁止対象とする。

- 2026-10-22のユーザー指示により、独自の取得はget付きの正式名へ集約し、get省略入口・短名取得コマンドを再追加しない。数学演算・保持プロパティ・OpenMaya/外部SDKの標準名と正式is判定は維持する。接続は `getSource/getDestinations(skipConversionNodes=...)` と方向指定の `getConnections`、単位は `get/set(uiUnits=...)`、子孫探索は `getChildren` のフラグに集約する。`getShapes` は独立して維持する。演算ノードの単純なPlug転送は削減し、Transform/Joint・行列/TRSと追加縮小14型以外の検証や複合処理は残す。リグ用途のオフセット生成・チャンネル初期化は `mlrig.setups.ControlHierarchy` に置く。通常変更はUndo可能なcmds、対応するfastはUndo設定を変更しないOM2実装とし、未対応条件は更新前に拒否する。具体的な範囲と制限は `maya/inhouse/mlib/_docs/consolidated_api.rst` を参照する。

- mlibの確定済み公開APIの引数仕様は、ユーザーから対象仕様への明示的な変更指示がない限り変更禁止とする。引数名・順序・位置引数/キーワード専用の区分・短縮名/長名・既定値・単位・フラグの意味・戻り値を維持する。リファクタリング、他ライブラリへの追従、命名統一、最適化を理由に変更しない。対象には `ws/worldSpace`、`at`、`ra/r/jo`、`safe/get/fast`、接続方向と `f/l/na`、`Node.addAttr` の型指定・`getPlug` を含む。具体的な仕様は `maya/inhouse/mlib/_docs/api_arguments.rst`・`maya/inhouse/mlib/_docs/api_methods.rst`・`docs/mlib-api-design.md` を参照する。特に `Node.addAttr()` は既定で追加したPlugを返し、明示的な `getPlug=False` の場合のみNoneを返す。通常のsetterが自身を返す仕様も維持し、既定戻り値をNoneへ変更しない。ドキュメントやテストを先に書き換えて仕様変更を正当化することも禁止する。既存の呼び出し仕様を保つ内部修正・不具合修正は可能とする。

- mlibの公開関数・メソッド・プロパティは全パッケージ共通でlowerCamelCase（`getSettings`・`undoChunk`・`minimumVersion`）とする。クラスはPascalCase。Maya標準名・om2継承/オーバーライド・Python特殊メソッド・標準ライブラリに合わせたAPIは元の名前を維持し、通知APIの`get_logger`/`raise_with_notify`も例外として維持する。2026-10-23のユーザー指示により、内部関数・内部メソッド・ローカル変数はsnake_caseを基本とする。既存の公開引数・拡張用プロトコル・Mayaフラグ・保存キーは変更しない。インデントはスペース4、文字列は原則ダブル引用符、単純な文字列埋込みはf-stringとし、エスケープを減らす引用符・raw正規表現・外部書式・数値書式・引数の評価順や参照回数を保つformat・loggingの遅延書式は例外とする。詳細は`docs/mlib-api-design.md`の「確定したコーディングルール」を参照する。

- mlibではQt関連ライブラリ（PySide/PyQt/shiboken/qtpy等）をimportしない。汎用UIラッパーは提供せず、Maya標準UIの操作とQtウィジェット取得・変換は利用側へ置く。横断的な通知は既存のmlib.loggerで扱う。

- mlibの日本語表記では、Mayaのattributeを「アトリビュート」と呼ぶ。説明・docstring・コメント・メッセージで統一し、API識別子は変更しない。

- Aiderへの実装委譲は行わない。2026-10-06のユーザー許可により、トークン消費を削減できる翻訳・要約などの補助作業にはローカルOllamaを使用してよい。必要に応じた起動・既存モデルのロードも許可する。MayaとのGPU・メモリ競合を確認し、競合する場合は使用を控える。不要な再翻訳やモデルロードは行わず、作業のためにロードしたモデルは終了後に解放する。生成結果の採否・実装・レビュー・検証は担当エージェントが直接行う。

- C++の内製コードは日本語のDoxygen形式（`@brief`・`@param`・`@return`、必要時`@note`）でファイル・クラス・全ての名前付き関数を説明する。初心者が追えるよう、所有権・Qtシグナル/スロット・非同期処理・Maya呼出の理由もコメントする。引数や戻り値がないタグは省略し、自明な各行の逐語説明は避ける。PythonはGoogle形式docstringを使用する。詳細は `docs/cpp-documentation.md` を参照する。外部submoduleへ一括適用しない。

- mlib・mlib_*・mlrigの診断ログと通知は `mlib.logger` の `debug`・`info`・`warning`・`error`・`print` に集約する。2026-10-23のユーザー指示により、通常の入力検証・下位処理の失敗は型付きの`raise`とし、利用者へ通知して中断する入口だけ`raise_with_notify`を使う。捕捉して戻り値・検証結果へ変換する失敗に通知を追加しない。`error`は通知のみ。復旧の二次失敗は必要時にwarningとし、元例外を優先する。ログの書式引数は標準loggingの遅延形式を使う。進捗表示の指定streamへの描画や保存データの出力は診断ログと区別し、既存の出力契約を維持する。`mlib.cmds.warning`やルートの`mlib.warning`は追加しない。

- mlibのAPIは「Mayaへ問い合わせる操作はメソッド」「保持する値はプロパティ」を基本とする。シーン更新は明示的なメソッドで行う。具体例と判断基準は `docs/mlib-api-design.md` を参照する。

- mlib/mlib_*の実装移動では旧import用の互換ファイル・別名を残さず、使用側（内製ツール・テスト・ドキュメント）を正式な新配置へ更新する。mlib.cmdsの7入口は既存の入力解決・短縮フラグ・Undo・戻り型を維持する。他のコマンドラッパーや生のcmds転送クラスは追加しない。

- mlibの実行フォルダは `cmds`・`nodes`・`plugs`・`components`・`maths`・`common`・`core` とする。選択・名前空間・参照関係、単位、プラグイン導入状態、イベント・遅延実行と既存の汎用計算の型は `common` 直下へ置き、領域別のサブフォルダは増やさない。汎用UI・設定ストア・保存フレームワークは本体へ追加しない。横断的に使う通知は直下の `logger.py`、デコレーター・コンテキストマネージャーとfast/safe・フラグ正規化の内部補助は直下の `decorator.py`、クラスに属さない小さな汎用関数と中立な値処理の補助は直下の `util.py`、共通基底・型判定/登録・編集基盤は `core`、文書は `_docs` に置く。`util.__all__`は`legalizeName`・`measure`・`mirrorArguments`の3件。`mlib_*` もこの責務の分類に合わせる。

- 2026-10-23のユーザー指示により、`_core`は`core`へ改名し、実行フォルダ名で公開/非公開を区分しない。正式なAPIは通常の明示import・`__all__`・文書で示し、集約した内部補助は先頭`_`で示し、既存の内部連携・登録プロトコル名は維持する。`core`内の全関数を正式APIへ拡大せず、既存の`NodeRegistry`・`reload_package`と登録用プロトコルの名前・意味を維持する。旧`mlib._core`や移動前のcommon小モジュールの互換ファイル・別名は残さない。`_docs`・`__tests__`は実行APIと別の文書・検証素材なので配置名を維持する。

- `Object` (`core/object.py`) は単数の `Node`・`Plug`・`Component` の共通基底と種類判別の入口。取得は `from mlib.core.object import Object` とし、ルートへの再公開は行わない。各型の入力解決は各基底クラス、複数入力の検証は `Nodes` に集約する。数学値・コレクション・UI・保存データを無理に継承させない。旧 `general`・`_core/coerce.py` の互換入口は置かない。拡張管理の正式入口は `from mlib.core import extensions` とし、ルート属性や旧モジュールパスは残さない。

- mlib.cmdsの公開関数とファイルは同名のlowerCamelCaseとし、`getNode/getPlug/createNode/ls/delete/duplicate/select`の7入口を維持する。既存対象の編集はオブジェクトのメソッド、他のMaya標準コマンドは利用側のcmdsへ寄せる。旧名の互換入口は残さず使用側を更新する。

- mlibのクラス実装は原則1クラス1ファイルとする。ただし単数クラスと対応する複数クラスは、単数形の同じファイルにまとめる（例: joint.pyのJoint/Joints、vertex.pyのVertex/Vertices）。既存の分離済みクラスをこの規則だけで移動する必要はない。関連する関数はクラスのメソッドへ、クラスに依存しない小さな中立の汎用関数・値処理補助は `mlib.util`、Mayaの状態・環境等の責務固有の処理は `mlib.common` へ置く。nodes/plugs/componentsなど型をまとめるパッケージ内に関数だけのPythonファイルを追加しない。commonでは用途単位の関数モジュールも扱う。公開コマンドは上記の命名・責務ルールに従う。

- mlibおよび `mlib_*` 拡張パッケージの一般Pythonファイル名はlowerCamelCaseに統一する（`eulerRotate.py`、`scriptJob.py`、`arrayPlug.py`）。Mayaコマンド/nodeTypeと同名のファイル、`__init__.py`等の特殊名、テスト探索用 `test_*.py` は既存規則を維持する。先頭の内部用 `_` とパッケージ名 `mlib_bifrost` 等は保持する。クラス名や独自メソッド名はこのファイル名規則とは別に扱う。

- mlibはMaya標準の名前・概念と汎用的な基礎APIを扱う。標準の関係型とリグ非依存の計算・汎用処理は `common`、骨の追従・Soft IK・補正・操作形状などの独自セットアップは `mlrig.setups` に置く。`mlib/animation` は作らない。Bifrostの演算部品は `mlib_bifrost.common`、リグの組み方はmlrigに置く。

- about/currentTime/cutKey/deleteUI/keyframe/listConnections/listHistory/listRelatives/menu/menuItem/objExists/parent/playbackOptions/setKeyframe はmaya.cmdsを直接使用する。mlrigにも適用し、同名mlibラッパーを再追加しない。必要なNode/Plug変換は使用側で明示する。

- mlrigのPythonコードはmlibの命名・書式・日本語Google形式docstringに合わせる。ノード・アトリビュート・接続・Undo・イベント管理はmlibの公開APIを基本にし、リグに依存しない機能はmlibへ還元する。具体的な境界と記述例は `docs/mlrig-development.md` を参照する。

- 外部ツールの調査メモ・比較表・候補一覧・調査インベントリは `docs/research/` にローカル保存し、Gitへ登録・プッシュしたりSphinxへ掲載したりしない。公開ドキュメントには実装済み機能の仕様・使い方を記載する。
- 動画・音声を処理するツール(`tools/video_summary.py` 等)について、Gitへ登録するもの(コード・docstring・コメント・ドキュメント・コミットメッセージ・PR・`WORK_LOG.md`)には、処理した動画の題名・イベントやカンファレンスの名前・講演者名・社名・内容を書かない。「参考事例」「試験に使った動画」「〇〇の講演で確認」のように、どの動画かを間接的に示す書き方も禁止する。使用例のファイル名は `movie.mp4` のような汎用の名前にし、動作確認は「手元の動画で確認」程度に留める。処理結果(`.maya-output/video-summary/`)はGitへ登録しない(2026-10-20 ユーザー指示)。

- このリポジトリでの説明・作業報告は日本語で行う。途中経過の報告・質問・確認・最終報告を含め、ユーザーへの返答はすべて日本語にする。英語の資料やツール出力を読んだ後、長い作業の途中、文脈が要約された後でも英語に切り替えない。コード・コマンド・識別子・ログの引用はそのままでよい。
- Claude Code / Codex / GitHub Copilot を並行運用する前提のリポジトリ。作業開始前に
  `WORK_LOG.md` を確認し、他ツールが進行中の範囲と重ならないか確認する。作業開始時に
  「進行中」へ自分の行を追加し、完了時に「完了履歴」へ移す(運用ルールは同ファイル参照)。
- 作業開始時に `git status --short` を確認し、既存の変更や未追跡ファイルを保持する。
- 依頼に必要な範囲を変更し、周辺コードの命名・書式・設計に合わせる。
- 仕様やコマンドは実装を確認する。概要は `README.md`、VS Code連携は `docs/vscode.md` を参照する。
- 完了時は変更内容、実施した検証、未検証の項目を簡潔に伝える。Mayaで未実行なら動作確認済みとしない。

## プロジェクト概要

Windows上でバッチ経由でMayaを起動し、標準環境への影響を抑えて内製・外部ツールをロードするカスタム作業環境。
Pythonコードは `PYTHONPATH` / `MAYA_MODULE_PATH` などを介してロードされ、通常のビルドやパッケージング工程はない。

| パス | 役割 |
| --- | --- |
| `maya/inhouse/HTools/` | Mayaメニューから実行する内製ツール |
| `maya/inhouse/mlib/` | ノード・アトリビュートラッパー、数学型、共通ユーティリティ |
| `maya/inhouse/MayaCommandPorts/` | GUI起動時のcommandPort初期化 |
| `maya/inhouse/MayaCinematicCameraHUD/` | C++プラグイン(別リポジトリのsubmodule)。ビルドは `tools/build_maya_plugin.py`、ロードは `maya/modules/*.mod` |
| `maya/inhouse/integrations/` | SlackやmGearとの連携 |
| `maya/external/` | 外部ツール。Git submoduleの定義は `.gitmodules` を参照 |
| `maya/modules/` | Maya用の `.mod` 定義 |
| `maya/maya_core.bat` | 共通の起動環境設定 |
| `maya/maya_*_en.bat` | バージョン別起動バッチ |
| `tools/send_to_maya.py` | 保存済みPythonファイルを起動中のMayaへ送信 |
| `tools/plugin_load_probe/` | `.mll`のロードがWindowsのセキュリティ機能に止められる原因を切り分けるデバッグ用の最小C++プラグイン。自動ロードしない |
| `MayaHToolsWorkspace.code-workspace` | VS Code設定・送信タスク |

## 起動と実行

- 起動バッチは2022・2023・2024・2025・2026・2027用がある。対象バージョンのインストールを確認して使用する。
- バッチは環境変数を設定し、存在する場合はユーザーの `Documents/maya/<version>/Maya.env` を読み込む。ユーザー環境を無断で書き換えない。
- VS Codeでは `MayaHToolsWorkspace.code-workspace` を開き、対象ファイルを保存して `Ctrl+Shift+B` で送信する。
- 現在の送信タスクはMaya 2027の `mayapy.exe` を使用する。実際のパスはワークスペースの `maya.pythonExecutable` を確認する。
- Pythonの送信先は `127.0.0.1:7002`。対象コードは送信側のmayapyではなく、起動中のMaya GUI内で `__main__` として実行される。

リポジトリルートからPowerShellで既存テストを送信する例（Maya GUI起動済みが前提）:

```powershell
& 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' tools/send_to_maya.py maya/inhouse/mlib/__tests__/test_datatypes.py
```

- 対象はこのワークスペース内の保存済み `.py` ファイル全体。選択範囲送信やブレークポイントには対応しない。
- import済み依存モジュールは自動リロードされない。必要な場合は既存のリロード手段を確認する。
- 終了コードは正常終了0、対象コードの例外1、接続・ファイル等の失敗2。出力と最終結果の両方を確認する。
- 応答待ちは300秒で終了するがMaya側の処理はキャンセルされない。タイムアウト時は実行状況を確認し、自動再送しない。
- `.maya-output/` は実行結果の受け渡し用。生成物をコミット対象にしない。

## 実装時の指針

### HTools

- `HTools/userSetup.py` がGUI起動時にメニューを作成する。バッチモードのスキップと同一セッションでの二重初期化防止を維持する。
- カテゴリフォルダ内のツール用 `.py` は動的にメニューへ登録され、`runpy.run_module(..., run_name="__main__")` で実行される。追加前に既存カテゴリと走査条件を確認する。
- UIのPySide6優先・PySide2フォールバックを維持する。対象MayaのPython・Qtで使用できるAPIを選ぶ。
- シーンを変更する処理は既存のUndo対応に合わせ、必要に応じて `mlib/decorator.py` を利用する。

### mlib

- ノード・アトリビュートラッパーは主に `maya.api.OpenMaya`（API 2.0）を使用する。既存のラッパーと共通処理を確認して再利用する。
- 公開名は各パッケージの `__init__.py` で明示する。`nodes`・`plugs`・`components`・`maths`・`cmds` とルート関数は通常のimportと `__all__`、`common` は遅延公開用の `_exports` と `if TYPE_CHECKING:` を更新する。追加・削除後はMaya不要の `python tools/check_mlib_exports.py` で公開漏れを検査する。
- Node/Plugの型対応は `nodes/__init__.py`・`plugs/__init__.py` の `_WRAPPER_CLASSES` 辞書へ明示する。公開名の宣言と型対応は別の責務で、登録済み型からのラッパー選択は `core/registry.py` の既存規則を維持する。デコレーターやモジュール走査で公開・型対応を追加しない。
- 複数形クラスの公開メソッドは通常の `def` として明示し、共通の引数検証・保持順実行・Undo処理へ委譲する。単数メソッドの追加だけで複数形APIを増やさず、既存の引数・戻り値・専用集約処理を維持する。
- 静的解析(Pylance/pyright)は、リポジトリ直下の `pyrightconfig.json` に設定を集約している。`maya.cmds` 等の補完は `python tools/setup_maya_typings.py` で `typings/maya/`(Git対象外)へ型スタブを配置して有効にする。スタブ起因の指摘は警告扱いで、エラーは実際の誤り。詳細は `docs/vscode.md`。
- 静的解析向けに公開名だけの別名一覧を増やさず、通常の明示importを公開と補完の共通入口にする。`common` だけ遅延公開用の `_exports` と `if TYPE_CHECKING:` を両方更新する。`test_typing_exports.py` と `tools/check_mlib_exports.py` で不一致を検査する。
- `mlib.reload()` は既存のリロード入口。変更を反映する際はシーンや保持中のインスタンスへの影響を確認する。
- `mlib/maths/` の値型は OpenMaya API 2.0 の型を継承する(Vector/Translate/Scale/Shear は `om2.MVector`、Quaternion は `MQuaternion`、EulerRotate は `MEulerRotation`、Matrix は `MMatrix`)。演算の意味は om2 に合わせ、値は可変・ハッシュ不可。Maya に依存しない純粋な値型へ戻さない(`easing` だけは標準 `math` のみ)。詳細は `mlib/_docs/guide_maths.rst` と `api_naming.rst` の意味の変更の一覧。
- Mayaの信頼済みプラグインの場所(`optionVar SafeModeAllowedlistPaths`)をスクリプトから変更しない。MayaのSafeModeが拒否する設定で、迂回せずユーザーがPreferences > Securityで登録する。
- mlib内では独自のMayaプラグインを実装・同梱・自動ロードしない。`MPxCommand` / `MPxNode` / `MFnPlugin` による登録は、Undo対応やバージョン差の回避目的でも追加しない。既存の内部プラグインもこの方針の解消対象とし、残存している場合は未対応箇所を明記する。Maya標準コマンドと既存のUndo可能な処理を優先し、実現できない機能は制限・未対応として明示する。`mlib.common`による既存プラグインの状態照会・明示的なロード管理は、この禁止の対象に含めない。

### 外部ツールと連携

- 外部submoduleを内製コードと混同しない。変更が依頼に必要な場合は対象submoduleの状態と独自のガイドを確認し、親リポジトリの参照更新も区別して扱う。
- 無関係なsubmodule更新や外部ライブラリの一括整形を行わない。
- `MayaCommandPorts` はHTools/mlibから独立した構成を維持する。
- Slackへの実投稿など外部への送信を伴うスクリプトは、ユーザーから送信の指示がある場合にのみ実行する。認証トークンをコードやログへ出さない。

## 検証

- 共通のpytest/CIコマンドを前提にせず、変更対象の既存テストと実行方法を確認する。
- 数学型の変更は `maya/inhouse/mlib/__tests__/test_datatypes.py` で検証する。標準の実行経路は上記のMaya送信タスク。
- `test_maya_standalone.py` や `test_slack_postMessage.py` は手動スクリプト。名前だけで安全な一括テストと判断せず、実行前に副作用を確認する。
- Maya依存コードは通常のPythonでimportできると仮定しない。構文チェックとMaya内の動作確認を区別する。
- UI・起動処理の変更では、対象Mayaでの起動、メニュー表示、操作結果を必要な範囲で確認する。実行環境が使えない場合は、その制約と確認手順を報告する。
- ドキュメントのみの変更では内容・参照先・差分を確認し、Mayaの起動は不要。

## リグ検証の共通ワークフロー

リグの動作・計算を検証してユーザーへ見せる場合は、Codex・Claude Code・GitHub Copilot共通で、次の順序を標準とする。詳細と既存ツールの使い方は `docs/verification-videos.md` を参照する。

1. **検証リグを作成する**: 専用のMaya GUIと検証シーンを使い、期待する挙動が伝わる最小構成を作る。入力と補正後を色分けし、カメラを固定する。境界に達する動き・境界を超える入力・安全範囲への復帰を含める。作業中のユーザーシーンを破棄しない。
2. **計算式と数値を文字で表示する**: MayaのHUD等、録画対象のmodelPanelに映る表示を使う。式、変数の意味、単位、角度の基準、固定値、各フレームの入力値と実際のDG出力を表示する。度とラジアンを区別し、見やすい順序・文字サイズ・配置にする。固定の値は固定と明記し、実際に変化する値を毎フレーム更新する。
3. **動画を撮影して検証する**: `tools/verification_video.py` の `recordVideo()` を基本に、実際のMaya表示を録画する。動画と診断JSONを `.maya-output/verification/<実行ID>/` に保存する。数値判定と、完成MP4の実フレームで文字の可読性・数値の変化・動作を確認する。判定用の計算はリグ本体への追加と区別する。失敗は失敗として報告する。
4. **Google Driveへアップロードする**: 接続済みのDrive機能で、確認したMP4を `Maya検証動画` 内の対象フォルダへ保存する。新規動画を「リンクを知っている全員・閲覧者」に設定し、既存の別ファイルの権限は変えない。メタデータでサイズ・閲覧URL・共有権限を読み戻し、`attachDrive()` でローカル結果に登録する。
5. **閲覧リンクを報告する**: Driveが返したURL、動画内の色・数値の意味、検証結果と制限を簡潔に伝える。再生処理中ならその状態を伝え、iPad実機で未確認なら確認済みとしない。

このワークフローはユーザーが希望する通常のリグ検証成果物の流れとして扱い、毎回録画・Drive保存を提案だけで終えない。ユーザーがローカルのみ等を指定した場合はその指示を優先する。Drive接続や共有操作が使えない場合もローカル録画・検証まで進め、未完了の工程と理由を報告する。認証トークンをコード・ログへ保存せず、コネクター認証をスクリプトへ流用しない。動画・画像連番はGitやGitHub Pagesへ登録せず、Sphinx掲載やコミット・プッシュは別の依頼として扱う。
