# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 基本方針

- 2026-10-25のユーザー指定により、公開APIの入力検証はassertでなく型付きraiseを使う（テスト・内部整合性のassertは可）。単純な番号/要素の列挙はenumerate、ファイルパスはpathlib、テキストI/Oは明示encodingを基本とする。既存layoutのL040/L043で入力assert候補/文字コード未指定、L041/L042で列挙/pathlibの確認候補を表示する。assertの修正は`--fix-asserts TypeError/ValueError`と対象ファイル・`--line`を明示し、例外型や文字コードを自動推測しない。MayaのDAG名・添字更新・テスト/内部assertを一律変換しない。検出範囲と修正条件は`docs/mlib-api-design.md`の「入力検証・列挙・ファイル操作」を参照する。

- 2026-10-25のユーザー指定により、代入・複合代入・比較演算子の前後は空白1つ、同じ行で次の項目が続くカンマの後は空白1つ、括弧内側は不要な空白なしとする。型注釈なしの既定値・キーワード指定は`fast=False`、型注釈付きの既定値は`fast: bool = False`。行末コメントの前は空白2つ以上、`#`の後は空白1つ（Sphinxの`#:`記法は維持）。名前へ直接代入するlambdaは通常のdefにし、コールバック引数等のlambdaは許可する。既存layoutの`--check`（L030〜L034）で検査し、この5項目は`--fix`で自動修正しない。詳細と対象外は`docs/mlib-api-design.md`を参照する。

- 2026-10-25のユーザー指定により、mlib・`mlib_*`のimportは原則モジュールdocstringの後、定数・関数・クラス定義の前にまとめる。`from __future__`は通常importより先。標準ライブラリ → Maya等の外部 → mlib内部（相対import・`mlib.*`、拡張では自パッケージも含む）の順に分類し、グループ間に空行1行を置く。関数内importは循環参照・任意依存・Maya非依存の維持など必要な理由がある場合だけ使い、直前に短い理由コメントを付ける（同じ理由の連続したimport群は1つでよい）。`import os, sys`は分離し、`from x import A, B`は許可、`from x import *`は禁止。インデントはスペース4、末尾空白なし、長い式は原則括弧内で改行する。reload・型登録等の初期化順、`TYPE_CHECKING`、対応Python構文と文字列データは保持し、一律にimportを移動しない。詳細は`docs/mlib-api-design.md`の「ファイル・クラスのレイアウト規則」を正とする。

- mlibの公開関数・メソッド・プロパティはlowerCamelCase、クラスはPascalCase。例外・引数・保存形式の扱いは `docs/mlib-api-design.md` の「確定したコーディングルール」を正とする。

- mlibの実行フォルダは `cmds`・`nodes`・`plugs`・`components`・`maths`・`common`・`core` とする。選択・名前空間・参照関係、単位、プラグイン導入状態、イベント・遅延実行と既存の汎用計算の型は `common` 直下へ置き、領域別のサブフォルダは増やさない。汎用UI・設定ストア・保存フレームワークは本体へ追加しない。横断的に使う通知は直下の `logger.py`、デコレーター・コンテキストマネージャーとfast/safe・フラグ正規化の内部補助は直下の `decorator.py`、クラスに属さない小さな汎用関数と中立な値処理の補助は直下の `util.py`、共通基底・型判定/登録・編集基盤は `core`、文書は `_docs` に置く。`util.__all__`は`legalizeName`・`measure`・`mirrorArguments`の3件。`mlib_*` もこの責務の分類に合わせる。

- 2026-10-23のユーザー指示により、`_core`は`core`へ改名し、実行フォルダ名で公開/非公開を区分しない。正式なAPIは通常の明示import・`__all__`・文書で示し、集約した内部補助は先頭`_`で示し、既存の内部連携・登録プロトコル名は維持する。`core`内の全関数を正式APIへ拡大せず、既存の`NodeRegistry`・`reload_package`と登録用プロトコルの名前・意味を維持する。旧`mlib._core`や移動前のcommon小モジュールの互換ファイル・別名は残さない。`_docs`・`__tests__`は実行APIと別の文書・検証素材なので配置名を維持する。

- `Object` (`core/object.py`) は単数の `Node`・`Plug`・`Component` の共通基底と種類判別の入口。取得は `from mlib.core.object import Object` とし、ルートへの再公開は行わない。各型の入力解決は各基底クラス、複数入力の検証は `Nodes` に集約する。数学値・コレクション・UI・保存データを無理に継承させない。旧 `general`・`_core/coerce.py` の互換入口は置かない。拡張管理の正式入口は `from mlib.core import extensions` とし、ルート属性や旧モジュールパスは残さない。

- mlibではQt関連ライブラリ（PySide/PyQt/shiboken/qtpy等）をimportしない。Maya標準UIはcmds/melとMayaの通知APIで扱い、Qtウィジェット取得・変換は利用側のUIパッケージに置く。

- HToolsの画面に出る文字(窓の題名・ボタン・ラベル・ダイアログ)と、warning・print・error・ログ・例外のメッセージは英語で書く(Mayaを英語で使うため。2026-10-05 ユーザー指示)。コメント・docstringは日本語のままとし、mlib・mlrigのメッセージは対象外。

- mlibの日本語表記では、Mayaのattributeを「アトリビュート」と呼ぶ。説明・docstring・コメント・メッセージで統一し、API識別子は変更しない。
- 2026-10-25のユーザー指定により、mlibの説明はCGWORLDのMaya記事の用語を参考にし、行列/変換行列は「マトリクス」、constraintは「コンストレイント」、四元数は「クォータニオン」とする。逆/回転/ワールド等の意味は保持し、行列式はdeterminantを指す専門語として区別する。入門の対象検索は`mlib.ls`を中心に説明し、Objectの直接呼出しを推奨例にしない。OpenMayaへの文書リンクはMaya 2027公式リファレンスを使う。API識別子・実行時の文字列・公開契約はこの文言整理で変更しない。

- mlibのクラス実装は原則1クラス1ファイルとする。ただし単数クラスと対応する複数クラスは、単数形の同じファイルにまとめる（例: joint.pyのJoint/Joints、vertex.pyのVertex/Vertices）。既存の分離済みクラスをこの規則だけで移動する必要はない。

- Aiderへの実装委譲は行わない。2026-10-06のユーザー許可により、トークン消費を削減できる翻訳・要約などの補助作業にはローカルOllamaを使用してよい。必要に応じた起動・既存モデルのロードも許可する。MayaとのGPU・メモリ競合を確認し、競合する場合は使用を控える。不要な再翻訳やモデルロードは行わず、作業のためにロードしたモデルは終了後に解放する。生成結果の採否・実装・レビュー・検証は担当エージェントが直接行う。

- C++の内製コードは日本語のDoxygen形式（`@brief`・`@param`・`@return`、必要時`@note`）でファイル・クラス・全ての名前付き関数を説明する。初心者が追えるよう、所有権・Qtシグナル/スロット・非同期処理・Maya呼出の理由もコメントする。引数や戻り値がないタグは省略し、自明な各行の逐語説明は避ける。PythonはGoogle形式docstringを使用する。詳細は `docs/cpp-documentation.md` を参照する。外部submoduleへ一括適用しない。

- mlibのAPIは「Mayaへ問い合わせる操作はメソッド」「保持する値はプロパティ」を基本とする。シーン更新は明示的なメソッドで行う。具体例と判断基準は `docs/mlib-api-design.md` を参照する。

- 外部ツールの調査メモ・比較表・候補一覧・調査インベントリは `docs/research/` にローカル保存し、Gitへ登録・プッシュしたりSphinxへ掲載したりしない。公開ドキュメントには実装済み機能の仕様・使い方を記載する。
- 動画・音声を処理するツール(`tools/video_summary.py` 等)について、Gitへ登録するもの(コード・docstring・コメント・ドキュメント・コミットメッセージ・PR・`WORK_LOG.md`)には、処理した動画の題名・イベントやカンファレンスの名前・講演者名・社名・内容を書かない。「参考事例」「試験に使った動画」「〇〇の講演で確認」のように、どの動画かを間接的に示す書き方も禁止する。使用例のファイル名は `movie.mp4` のような汎用の名前にし、動作確認は「手元の動画で確認」程度に留める。処理結果(`.maya-output/video-summary/`)はGitへ登録しない(2026-10-20 ユーザー指示)。

- このリポジトリでの説明・作業報告は日本語で行う。途中経過の報告・質問・確認・最終報告を含め、ユーザーへの返答はすべて日本語にする。英語の資料やツール出力を読んだ後、長い作業の途中、文脈が要約された後でも英語に切り替えない。コード・コマンド・識別子・ログの引用はそのままでよい。
- Claude Code / Codex / GitHub Copilot を並行運用する前提のリポジトリ。作業開始前に
  `WORK_LOG.md` を確認し、他ツールが進行中の範囲と重ならないか確認する。作業開始時に
  「進行中」へ自分の行を追加し、完了時に「完了履歴」へ移す(運用ルールは同ファイル参照)。

## プロジェクト概要

Maya用のカスタム作業環境リポジトリ。バッチファイル経由でMayaを起動し、内製ツール(HTools/mlib)と外部ツール(mGear, cymel等、Git submodule)を標準環境に影響を与えずロードする。ビルドやパッケージングの工程は無く、`PYTHONPATH` / `MAYA_MODULE_PATH` を介してMaya起動時にそのままロードされるPythonコード群である。

## 起動・実行コマンド

### Mayaの起動

`maya/` ディレクトリから対応バッチを実行する(2022/2023/2024/2025/2026/2027用バッチが用意されている。README記載の代表例):

```bat
cd maya
maya_2026_en.bat
```

各バッチは共通処理 `maya_core.bat` を呼び、`PYTHONPATH`(`inhouse`, `inhouse/HTools`)、`MAYA_SCRIPT_PATH`、`MAYA_PLUG_IN_PATH`、`MAYA_MODULE_PATH`(`modules/`)を設定してからMayaを起動する。`%USERPROFILE%\Documents\maya\<version>\Maya.env` が存在すればあわせて読み込まれる。

### pipのパッケージ

外部ツールはGit submoduleが基本で、submoduleにしていないPyPIパッケージだけを `maya/requirements/<名前>.txt`(1ファイル=1グループ)に書く。`maya/install_packages.bat [年...] [グループ...]`(macOSは `.command`)が各バージョンの `mayapy` で `tools/install_maya_packages.py` を実行し、`maya/site-packages/<年>/<名前>`(Git対象外。取得物はライセンスの都合でコミットしない)へ `pip install --target` する。グループは依存も含めて自己完結し、同じバージョン内の同一ファイルは取得後にハードリンクでまとめる。`PYTHONPATH` へ通すのは `pip_<名前>.mod` だけで、submoduleと同じく `maya/modules/` に置いたものが有効、`maya/modules_disabled/` は無効(初期の有効は `slack_sdk` のみ)。`.mod` が無いグループには取得時に無効の `.mod` を作る。Maya本体・ユーザー領域には書き込まず、`PYTHONNOUSERSITE` も設定しない(ユーザー領域と共存)。Maya同梱パッケージは `pip list --path` で調べた版に固定して解決し、取得後に取得先から外す。新しいフォルダーへ取得してから入れ替えるので、起動中のMayaが使うファイルがあると失敗する。起動バッチは有効な `pip_*.mod` のグループについて、`.txt` と取得時の写し(`<名前>/.installed-requirements.txt`)が違えば自動取得してからMayaを起動する。取得に失敗したグループは `<名前>.failed` に写しを残し、同じ内容では起動のたびに再試行せず `[WARN]` だけ出す。

### VS CodeからMayaへコードを送信・実行する

1. リポジトリ直下の `MayaHToolsWorkspace.code-workspace` をVS Codeで開く(フォルダ単体で開くとタスク定義が読み込まれないので不可)。
2. 上記バッチでMayaを起動しておく(GUI必須。commandPortが `:7002` に開くのはGUI起動時のみ)。
3. 実行したい `.py` ファイルを開き、**Ctrl+S → Ctrl+Shift+B** で送信する(保存は自動設定済み)。
4. 標準出力・例外はVS Codeターミナルと実行元のMaya双方に表示される。正常終了は `[Maya] Completed`、未処理例外は `[Maya] FAILED`。終了コードは 成功=0 / スクリプト内例外=1 / 接続やファイル不備=2。

実体は `tools/send_to_maya.py`(mayapy経由でタスク実行)が `localhost:7002` へ実行コマンドを送り、対象ツール自体は**起動中のMaya GUIプロセス内**で実行される仕組み(`MayaCommandPorts` が開くPythonポートを利用)。対象は保存済みファイル全体(`__name__ == "__main__"`)で、選択範囲送信・ブレークポイントは非対応。import済み依存モジュールは自動リロードされない。結果受け渡しは `.maya-output/` 配下の実行ごとのJSONファイル(取得後は削除、gitignore対象)。別バージョン/インストール先を使う場合は `MayaHToolsWorkspace.code-workspace` の `maya.pythonExecutable` と `python.defaultInterpreterPath` を対象の `mayapy.exe` に変更する。

### 静的解析(Pylance/pyright)

`python tools/setup_maya_typings.py` で型スタブ(`types-maya`)を `typings/maya/` へ配置する(Git対象外)。設定はリポジトリ直下の `pyrightconfig.json`(解析対象・`extraPaths`・重大度)。スタブの不完全さに起因する指摘は警告にしてあり、エラーは実際の誤りだけ。コマンドラインでは `pyright --pythonpath "C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe"`。詳細は `docs/vscode.md`。

### テストの実行

pytestやCIランナーは無く、Maya(mayapy)経由での手動実行が前提。mlibのテストは `maya/inhouse/mlib/__tests__/`(`unit/`・`integration/`・`checks/`・`support/`・`manual/`)にあり、実行手順・結果の見方・追加方法は同フォルダの `README.md` を正とする。要点だけを挙げる。

- **Maya不要の検査**: `__tests__` フォルダで `python runStatic.py`。`unit/test_static_*.py`(通常のPythonで動く単体テスト。`test_static_version.py` は `__version__`・`mlib.mod`・`changelog.rst` の版の一致を検査)と、`checks/check_mlib_exports.py`(公開名と明示宣言の一致)・`checks/check_mlib_layout.py --check`(import順・空白・入力assert等のレイアウト)の2本を実行する。公開名の追加・削除後はこの2本を必ず通す。
- **Mayaでの実行**: `__tests__` フォルダで `.\run.bat --versions 2027 --suite all`(`python runMaya.py ...` でも同じ)。`--suite unit|integration|all` と `--tests test_datatypes.py ...` で対象を絞り、`--versions 2022 2027` で複数版を同じテストで回す。ランナーが各版の mayapy を隔離した設定で起動して `run_all_tests.py` に同一セッションで連続実行させ、結果は `_output/maya/<日時>/summary.txt`・`result.json`、詳細ログは `_output/logs/<日時>.log`(いずれもGit対象外)。GUI限定の確認(イベント・表示)は `python runGui.py --versions 2027 --suite unit|integration|visual` が使い捨ての専用Maya GUIを起動する。
- `run_all_tests.py` は `unit/`・`integration/` の `test_*.py`(`test_static_*` を除く)を探索し、各ファイルの `if __name__ == "__main__":` を `runpy` で実行して成功/失敗をファイル単位で集計し、1件でも失敗すれば `AssertionError` を送出する。`run_all(notify=...)` は集計後のサマリ文字列を受け取るコールバックを渡せる(`mlib/common/progress.py` の `notify` と同じ設計で、将来 Slack 通知等を差し込む接続点)。テストにはシーンを初期化するものがあるため、**作業中の Maya GUI へ一式を Ctrl+Shift+B で送信しない**。個別ファイルを送る場合も、そのファイルがシーンを初期化しないことを確認する。
- 各テストは専用の一時名前空間やユニーク名でノードを作成し、tearDown で削除する(共通基底は `support/specCase.py`)。2.0.0 で足した仕様テストは `test_spec_*.py` で、変えたAPIごとにフラグ行列・cmds/om2 突き合わせ・Undo 1回/fast=Undoなし・不正入力の例外型・一括(Nodes等)を `subTest` で確かめる。Python 3.7(Maya 2022)で動く書き方にする。
- **cmds突き合わせ(回帰防止の体系的な仕組み)**: `__tests__/integration/test_cmds_parity.py` は、`docs/mlib-api-design.md` のMayaコマンドとOpenMayaの使い分けの方針でcmds→om2に置き換えた読み取り専用メソッドについて、mlib側の戻り値とcmds側の生の値を**同一テスト内で突き合わせる**専任ファイル。他のtest_*.pyにある「固定の期待値になるか」だけのテストと異なり、Mayaバージョン変更やAPIの挙動変化・リファクタによる回帰を継続的に検知する目的を持つ。新しくcmds→om2の置き換えを行った場合はこのファイルに対応する突き合わせを追加するのが規約(既存の突き合わせ一覧はファイル冒頭のdocstringを参照)。一致しないものはcmdsに戻す。
- **利用側の回帰**: mlrig・mlib_bifrost・標準プラグイン連携は、ワークスペースのルートで `"C:\Program Files\Autodesk\Maya2027\bin\mayapy.exe" tools\test_rig_packages.py --suite all` を実行する(2027)。`--suite setups` 等の個別指定もあるが、mlibの変更後の回帰確認は `all` を使う(`setups` だけでは `standard`・`native`・`bifrost`・`mlib` が走らない)。各テストは新規シーンへ切り替えるため Maya GUI 内では実行しない。
- `__tests__/manual/` は自動実行しない個別確認・API調査用。`manual/test_command_discovery.py` は `subprocess` で mayapy を別プロセス起動する疎通確認用スクリプトで、Maya GUI の commandPort 経由で実行すると新しい Maya.exe が起動してしまうため Maya GUI 経由では実行しないこと。
- mlibのSphinx文書は `maya/inhouse/mlib/_docs/rebuild.bat --no-pause` でビルドし、`checks/check_mlib_docs.py --check-directory` と `checks/check_mlib_doc_getter_names.py` で検査する(手順は `__tests__/README.md`)。

## アーキテクチャ

### ディレクトリ構成

```
maya/
├ external/     外部ツール(Git submodule。38個に加え、リグ手法の参考49個・研究論文の公開実装19個・3DCG数学論文の公開実装31個。一覧は下記「external ― 外部ツール一覧」参照)。
│               直接編集せず、変更は各submodule側で行う。
├ inhouse/      内製ツール本体
│  ├ HTools/         Mayaメニューから起動する社内ツール群
│  ├ mlib/           共通ライブラリ(Node/Plugラッパー、数学型、デコレータ等)
│  ├ MayaCommandPorts/  HTools/mlibから独立したcommandPort初期化モジュール
│  ├ integrations/   外部サービス連携(Slack, mGearガイド操作)
│  ├ FramePlayer/    コマ送り確認用の動画プレイヤー(C++のexeをパッケージ直下に置く)と、Mayaのタイムスライダーと双方向に連携するPythonパッケージ(`python/frameplayer`)。mlibに依存しない単体パッケージで、将来は別リポジトリでの公開も検討中。詳細は同フォルダのREADME
│  └ MayaCinematicCameraHUD/  C++プラグイン(別リポジトリのsubmodule。このワークスペースで編集・ビルドする)
├ modules/      各ツールをMayaに認識させる .mod ファイル(2022/2023/2024/2025/2026/2027対応、MAYA_MODULE_PATHの対象)
├ modules_disabled/  上記と同形式だが未登録の .mod ファイル(無効化されたツール/汎用ライブラリ)。有効化するには modules/ へ移動する
└ maya_*.bat, maya_core.bat  起動バッチ
tools/
├ send_to_maya.py  VS Code タスクが実行するMaya送信スクリプト
└ plugin_load_probe/  .mllのロードがWindowsのセキュリティ機能に止められる原因を切り分ける、デバッグ用の最小C++プラグイン(自動ロードしない。詳細は同フォルダのREADME)
```

### external ― 外部ツール一覧

`maya/external/` 配下の Git submodule 38個と、末尾「リグ手法の参考」の49個・「研究論文の公開実装」の19個・「3DCG数学論文の公開実装」の31個。いずれも直接編集せず、変更は各submoduleのリポジトリ側で行う。

**Python基盤/ラッパーライブラリ**
- `cymel`: Maya APIとコマンドの軽量ラッパーモジュール。
- `pymel`: `maya.cmds` の直訳的で非pythonicな部分を解消する、Mayaコマンドのpythonicなラッパー(nodetypes.pyを自動生成)。
- `paya`: `cmds`/OpenMaya自体を再ラップせず、その上に機能を足すリガー向けオブジェクト指向ツールキット(PyMELライクなAPI)。
- `AL_omx`: Animal Logic製、Maya APIとコマンドの薄いラッパーライブラリ(PyPi配布)。

**リギング/オートリグフレームワーク**
- `mgear4`, `mgear5`: mGear(既存記載の通り、モジュラーリギングフレームワーク)。
- `crab`: コンポーネント(腕・脊椎・脚など)単位でスケルトンとコントロールリグを構築するモジュラーリギングツール。
- `fossil`: リギング・アニメーションツール群。
- `maya-pulse`: リギングフレームワーク/ツールキット(開発中)。
- `mikan`: Maya/Tangerine向けのブループリント式モジュラーオートリギングフレームワーク。
- `trigger`: モジュラーなリギング・自動化ツール。
- `nl_rigging_tools`(nlRT): リギングツール集。
- `AdvancedSkeleton`, `AnimationAid`, `AriTools`(既存記載): オートリグ/リギング支援ツール。

**アニメーション**
- `aTools`: Alan Camilo氏制作のアニメーションツールキット。
- `animation-retargeting-tool`: リグ間、またはモーキャプ→カスタムリグへのアニメーション転送ツール。
- `guppy_animation_tools`: Arc Tracerなどアニメーション制作支援ツール集。
- `ml_tools`: Morgan Loomis氏のアニメーションツールをまとめたリポジトリ。
- `Red9_StudioPack`: テクニカルアニメーション向けの総合Mayaツールパック。
- `studiolibrary`: ポーズ/アニメーションを保存・管理するQtベースのライブラリツール。
- `PoseDriverConnect`(既存記載): ポーズドリブン関連ツール。

**スキン/ウェイト編集**
- `SkinPowerTool`: SkinMagicプラグインの代替となるスキンウェイト編集ツール。
- `defWeightTransfer`: デフォーマウェイト(bend/cluster/FFD等)の転送・ミラー・変換ツール。
- `maya-skinning-tools`: スキニング支援ツール集(スムーズウェイト等)。
- `skinner`: スキンウェイトのエクスポート/インポート/転送ツール。
- `SIWeightEditor`(既存記載): Softimage風のスキンウェイト編集ツール。

**メッシュ/リターゲット**
- `MayaMeshRetarget`: RBF補間とスキンウェイトベースのクラスタリングでメッシュ変形をソース→ターゲットへ転送するツール。
- `MetaHumanForMaya`(既存記載): MetaHuman関連ツール。

**その他**
- `gt-tools`: 汎用のアニメーション/リギング補助ツール集(GT Tools)。
- `jlr_sort_attributes`(既存記載): チャンネルボックスのユーザー定義アトリビュートを並び替えるツール。
- `CharcoalEditor2`(既存記載): エディタ系ツール。
- `openrv`: ASWF製の画像・動画レビューツール(OpenRV、Apache 2.0)。FramePlayerの色再現(色の情報の読み取り・YUV→RGB・色管理)の参考として取り込み。Mayaへはロードしない。

**汎用Pythonライブラリ(Maya専用ツールではない)**
- `rich`: ターミナル出力の表・プログレスバー・シンタックスハイライト等を行うライブラリ。
- `pyyaml`: YAML パーサ/エミッタ(実体は `lib/yaml` 配下。トップレベルの `yaml/` は未使用のCython版ソース)。
- `tqdm`: プログレスバー。
- `tabulate`: テキストでの表整形。
- `natsort`: 自然順ソート。
- 上記5つは対応する `.mod` を `maya/modules_disabled/` に用意済みだが、`maya/modules/` へは未登録(MAYA_MODULE_PATH対象外)のため起動時に自動ロードされない。有効化するにはそのバージョン用の `.mod` を `maya/modules/` へコピー/移動する。個別スクリプトで使うだけなら `.mod` を経由せず `sys.path` へ直接追加してもよい。

**リグ手法の参考(2026-10-09追加、49個)**
- RBF・ポーズ補正・揺れ物・衝突・変形・IK・行列リグ・リグ構築の手法を調べるための参照用。いずれも `shallow = true`(最新1コミットのみ)。`godot`(約355MB)・`spine-runtimes`(約221MB)が大きい。入れ子のsubmodule(`cmt`・`dem-bones-python`・`maya-dem-bones`・`cvwrap`・`bl_rbf_drivers`)は未取得で、`--recursive` 時に取得される。
- Maya用: `SrtRbfNode`, `cmt`, `ypr-expression-driver`, `Simplex`, `EccentricConePSD`, `NWayBlenderMaya`, `perseus`, `TwistSpline`, `maya_bifrost`(gkRig), `boneDynamicsNode`, `bifrost_AkPBD`, `maya_expressionCollision`, `colDetectionNode`, `BlurHarmonics`, `pw_matrix_collision_rig`, `ny_collisionDeformer`, `iDeform`, `ssds`, `dem-bones`, `dem-bones-python`, `maya-dem-bones`, `MyMayaPlugin`, `direct-delta-mush`, `cvwrap`, `blurRelax`, `dm2skin`, `impulse`, `aniseed`, `rigamajig2`, `defQA`, `MayaMLDeformer`, `FDDADeformer`, `stickyTool`, `NurbBuilder_Maya2026_rigging`。
- Maya以外(発想・アルゴリズムの参照): `bl_rbf_drivers`, `blender-jiggle-physics`, `angavrilov-rigs`(Blender)、`STAR`(論文実装)、`Motion-Matching`, `Spring-It-On`, `MathUtilities`, `JigglePhysics`(C++/Unity)、`godot`, `many_bone_ik`(Godot)、`caliko`(Java)、`Everything-Will-Be-IK`、`closed-chain-ik-js`、`spine-runtimes`、`houdini_apex_graph_from_templates`(Houdini)。
- 読み込める27個(ビルド済みプラグイン・Pythonパッケージ・Bifrost compound)の `.mod` は `maya/modules_disabled/` に置き、起動時には読み込まない。有効化するには `maya/modules/` へ移動する。`Simplex`・`TwistSpline`・`BlurHarmonics`・`cvwrap`・`blurRelax`・`dem-bones-python`・`maya-dem-bones`・`ssds` はプラグイン/拡張モジュールのビルドが別途必要、`SrtRbfNode.mll` はMaya 2020向けで2022以降はロード不可、`impulse`・`aniseed` はMaya 2022(Python 3.7)ではimport不可、`dm2skin` はnumpy/scipyが必要、`MayaMLDeformer` はfbxmayaプラグインが必要、`perseus`・`colDetectionNode`・`ny_collisionDeformer`・`iDeform` のビルド済みは2022〜2023/2024/2025まで。`aniseed`・`iDeform`・`MayaMLDeformer`・`ypr-expression-driver` は有効化するとそれぞれのuserSetupが起動時に実行される。
- ライセンス表記なし(コード流用不可、発想のみ): `SrtRbfNode`, `BlurHarmonics`, `FDDADeformer`, `direct-delta-mush`, `pw_matrix_collision_rig`, `angavrilov-rigs`, `rigamajig2`, `NurbBuilder_Maya2026_rigging`。GPL/LGPL/独自/非商用(`bl_rbf_drivers`・`blender-jiggle-physics`・`Simplex`・`spine-runtimes`・`STAR`)も式・考え方の参照に留める。調査内容はローカルの `docs/research/rig-setup-techniques-2026-10-09.md`。

**研究論文の公開実装(2026-10-09追加、19個)**
- mlrig参考の論文調査(ローカルの `docs/research/rig-research-papers-2026-10-09.md`)で見つかった公開実装。いずれも `shallow = true`。`OpenUSD`(execIr)・`MetaHuman-DNA-Calibration`・`fast_cody` が大きい。`hrbf` のみGitLab。
- 変形・二次動作: `OptimisedCentresOfRotationSkinning`, `velocity_skinning_cpp`, `fast_cody`, `complementary-dynamics-cpp`, `complementary-dynamics`(MATLAB), `hrbf`(Rust/C API), `libigl`(BBW等。MPL2主体で一部GPL)。補正: `splocs`, `neural-blend-shapes`(ライセンス種別未確認)。逆リグ写像: `rig-inversion`, `OpenUSD`(execIr)。リグ定義: `openriglogic`, `MetaHuman-DNA-Calibration`(ライセンス独自)。ウェイト・自動リギング: `RobustSkinWeightsTransferCode`, `UniRig`, `Puppeteer`, `Make-It-Animatable`, `RigNet`(GPL-3.0)。ポーズ生成: `protores-boris`(非商用)。
- Mayaで読み込めるのは `MetaHuman-DNA-Calibration` のみ(Maya 2022〜2024のビルド済み `embeddedRL4`・`MayaUERBFPlugin` と `dna`/`dnacalib`/`dna_viewer`)。`.mod` は `maya/modules_disabled/MetaHuman-DNA-Calibration.mod`。有効な `metahuman_for_maya.mod` と同名プラグインを含むため、同時に有効化しない。ほかはC++・MATLAB・PyTorch等の研究コードで `.mod` なし。

**3DCG数学論文の公開実装(2026-10-10追加、31個)**
- 3DCG表現の数学論文調査(ローカルの `docs/research/cg-math-papers-2026-10-10.md`)で見つかった公開実装。いずれも `shallow = true`。入れ子のsubmoduleを持つもの(`zombie`・`geometry-central`・`mfem` など17個)は未取得で、`--recursive` 時に取得される。`ipc-toolkit`・`beta-splatting`・`IPC`・`kaolin` が比較的大きい。DeepPhase公式実装のAI4Animation(約5.5GB・非商用)はユーザー判断で追加していない。
- 形状処理・PDE: `zombie`(Walk on Spheres/Stars), `geometry-central`, `nonmanifold-laplacian`, `robust-laplacians-py`, `vector-heat-demo`, `SWN`, `repulsive-curves`, `repulsive-surfaces`, `lifting_simplices_to_find_injectivity`, `invertible-maps`(AGPL-3.0), `NeuralJacobianFields`(Adobe、商用不可)。
- 曲線・陰関数・新表現: `UnityC2InterpolatingSplines`(Yuksel C2スプラインの非公式実装), `basalt-headers`(Lie群B-spline), `smoothdists`, `1-Lipschitz-Neural-Distance-Fields`, `neural-implicit-queries`, `jaxgptoolbox`, `2d-gaussian-splatting`(非商用), `beta-splatting`, `3D-student-splatting-and-scooping`(GPL-2.0), `SC-GS`, `DevelopableApproximationViaGaussImageThinning`(ライセンス表記なし)。
- シミュレーション: `IPC`, `ipc-toolkit`, `avbd-demo3d`, `Houdini-VBD`, `YarnBall`(Stable Cosserat Rods、GPL-3.0), `mfem`(ライセンス表記なし), `simkit`, `kaolin`(Simplicits), `ppf-contact-solver`(Cubic Barrier)。
- Mayaで直接読み込めるもの(Mayaプラグイン・Maya用Pythonパッケージ)は無いため `.mod` は用意していない。ライセンス表記なし・GPL/AGPL・非商用のものはコードを流用せず、論文の式・考え方の参照に留める。

### HTools ― メニュー登録の仕組み

- `HTools/userSetup.py` がMaya起動時に評価される。GUI起動時のみ・同一セッション内では1回のみ実行される(`MAYA_INHOUSE_USERSETUP_INITIALIZED` 環境変数で二重初期化防止、バッチモードはスキップ)。
- `HTools/` 直下のサブディレクトリ(`animation/`, `material/`, `rigging/` 等、`__` で始まらないもの)をカテゴリとして走査し、各サブディレクトリ内の `.py` ファイル(`__init__.py` を除く)をメニュー項目として動的にQtメニューバーへ追加する。**新規ツールを追加する場合はカテゴリフォルダに `.py` を1本置くだけでHToolsメニューに現れる**(明示的な登録コードは不要)。
- メニュー項目クリック時は `runpy.run_module("HTools.<category>.<tool>", run_name="__main__")` として対象モジュールをその場で実行する。
- `HTools/searchable_menu.py` の `SearchableMenu`(`QtWidgets.QMenu` 拡張)が検索フィールドとフラット/階層表示切り替えを提供する。
- PySide6を優先し、無ければPySide2にフォールバックする実装(Maya 2025以降はPySide6、2022はPySide2)。
- `_` で始まるフォルダー(`__pycache__`・説明ページの `_docs`)はカテゴリにしない。説明ページは `HTools/_docs/<カテゴリ>/<ツール名>.rst`(Sphinx、GitHub Pages の `htools/` に公開、画面のスクリーンショットは `_docs/_static/images/<カテゴリ>/`)。HToolsメニューのツール名の右端の「?」(`searchable_menu.py` の `ToolMenu`/`HelpIconMixin`)でそのツールのページが開き、末尾の Help > HTools Documentation で目次が開く。画面のあるツールは画面の Help から `HTools.toolHelp.openHelp("<カテゴリ>", "<ツール名>")` で自分のページを開く。**ツールを追加・変更したら、そのページとカテゴリの目次も更新する**。

### mlib ― Maya API 2.0 ベースの共通ライブラリ

主に `maya.api.OpenMaya`(API 2.0)を用いたノード/アトリビュート(plug)のラッパーを提供する。通常更新はUndo可能なcmds、対応するfast更新はOpenMayaを使用し、公開名と型対応は明示登録する。読み取りはom2を基本とし、`fast`引数は中核の書き込み(`Plug.get/set`・`createNode`・`delete`・`setMatrix`系等)だけに置く(3.0.0でduplicate・select・Namespace・mute・matchTransform・influence除去のfastを外した。例外と理由、cmds→om2置換時の突き合わせ規約は`docs/mlib-api-design.md`の「判断に迷う場合」)。短縮名の別名引数はMayaコマンドのフラグを受ける入口(`cmds/`・`addAttr`・`addConstraint`・`makeIdentity`等)だけに置く。2.0.0〜4.1.0(2026-10-27〜29)で統合・廃止・改名・削除したAPIの対応表と移行例は`maya/inhouse/mlib/_docs/source/changelog.rst`、規則は`docs/mlib-api-design.md`を正とする。公開の独自引数もlowerCamelCase(Mayaのフラグと同名の引数はMayaの表記、内部関数・ローカル変数はsnake_case)で、`__tests__/unit/test_static_public_args.py`が検査する。アトリビュートの呼び名はMayaのコマンドに合わせ、要素を持つものは「マルチアトリビュート」(`MultiPlug`・`isMulti()`、その要素は`isMultiElement()`)、子を持つものは「コンパウンドアトリビュート」(`CompoundPlug`・`isCompound()`)と呼ぶ(OpenMayaの`MPlug.isArray`・`isElement`との対応表は`docs/mlib-api-design.md`冒頭)。内部名(`_require_`/`_resolve_`/`_<method>_fast|_cmds`)・fastの定型・例外の分類と文言・docstringの固定文は`docs/mlib-api-design.md`の「内部実装の定型」を正とする。

- **明示的な公開・型登録** (`mlib/core/registry.py`): `nodes/__init__.py`・`plugs/__init__.py`の通常importと`__all__`へ公開名を追加し、`_WRAPPER_CLASSES`辞書へMaya型名とクラスの対応を宣言する。クラスの走査や登録デコレーターは使わない。登録表に無いMayaのnodeTypeは要求時に動的クラス(型名の先頭を大文字にした名前。`mlib.nodes.<TypeName>` でも取得でき、Mayaが認識しない型名はAttributeError)を生成して補完する。生成クラスは`__all__`・モジュール属性・Sphinxに載せず、`mlib.reload()`・登録表の変更(`register/replace/clear`)・`Plugin.load/unload`で廃棄して次の照会で作り直す(保持中の生成クラス参照は`mlib.nodes.<TypeName>`を取り直す)。手書きクラスの明示登録は維持し(`"constraint"`は`Constraint`として登録、`"node"`は登録しない)、拡張の登録は生成より優先する。コマンドは`cmds/__init__.py`とルートの通常import/`__all__`、commonのみ遅延公開の`_exports`と`TYPE_CHECKING`を更新する。追加・削除後は`python maya/inhouse/mlib/__tests__/checks/check_mlib_exports.py`で検査する。クラスは`mlib.nodes.Joint`等の所属パッケージから取得し、ルートへ展開しない。任意拡張は`MLIB_EXTENSION_API`と明示対応表を検証して自動探索・登録する。
- **型の選択**: `Node.__new__`(`mlib/nodes/node.py`)が対象のMaya nodeTypeから登録済みラッパーを選び、未登録の型は動的クラスを生成して返す(`Node`へのフォールバックはMayaが認識しない型名だけ)。動的クラスの基底はMayaの継承チェーン上で最も近い登録クラスで、間にある抽象型(`geometryFilter`・`containerBase`・`entity`等)のクラスは生成しない。`getType()`はNode・PlugともにMayaの型名を返す(NodeはnodeType名で`getType(inherited=True)`は基底→自身の順のlist、Plugはアトリビュートの定義型名でgenericはNone。旧`Plug.getDataType`は無い)。Mayaの継承に基づく判定は`isType()`、Pythonクラスは`type(x)`/`isinstance`で行う(手書きクラスの`isinstance`はMayaの抽象祖先を含まず、生成クラスは最寄りの登録クラスの派生であることだけを保証する)。`Node`を基底とした取得と、`Joint`等の具体型を明示した構築の検証を区別し、不一致の型へ黙って差し替えない。
- **maya.cmds・OpenMaya との受け渡し**: `Node`/`Plug`/`Component` はそのまま `maya.cmds` に渡せる(`__str__` が毎回取り直す一意な名前を返す。Plug は「ノードの一意名 + ロング名のアトリビュートパス」)。コンポーネントの集まりは cmds がシーケンスとして展開する。`MultiPlug`(マルチアトリビュート全体)自体と `om2.MObject` は cmds に渡せない。mlib のコマンドは Node/Plug/Component/集まり/`MObject`/`MDagPath`/`MPlug` を受け付ける(`core/object.py・nodes/node.py・plugs/plug.py・components/component.py`)。Node/Plug を str や `__len__` を持つ型にしない(cmds の解釈が変わる)。`MultiPlug` も `__len__` を持たない(cmds が位置0〜len-1の並びとして展開し、論理番号と違う値を黙って返すため。要素数は `len(getIndices())`)。`in` は論理番号の存在を返す。`repr` は `MultiPlug('pma.input1D')` のようにラッパーの型名を表示する。受付対象と制限は各公開APIのdocstringと `docs/mlib-api-design.md` を参照する。
- **`mlib/cmds/`の明示公開**: `getNode/getPlug/createNode/ls/delete/duplicate/select`の7入口を提供する。ノードの作成は`mlib.createNode(type, name=..., parent=..., fast=...)`(`cmds.createNode`相当。実際のnodeTypeに対応するラッパーを返す)だけで行い、`Node.create`・`Transform.create`等の型付きcreate・`Node(name, create=True)`は無い(constructorは取得専用)。`fast=True`はOpenMayaで作成しUndoに記録しない。未知の型名はどちらの経路でもRuntimeErrorでノードを残さず、`query/edit`フラグは受け付けない。createNode以上の処理をする特化ビルダー(`Container.create(name="container", members=())`・`Container.createNode`・`DagPose.create`・`SkinCluster.bind`)だけを残す。関数名とファイル名を同じlowerCamelCaseにし、通常importと`__all__`を`cmds/__init__.py`とルートへ追加する。ファイルを置くだけでは公開されない。各モジュールのdocstringはSynopsis/Return value/Flags/Examples形式で記載し、Sphinxの専用テンプレートへ渡す。`mlib.reload()`は現在の定義と明示公開を読み直す。
- **依存順リロード** (`mlib/core/reload.py`): `mlib.reload()`が現存モジュールのglobals内参照から依存順を推定し、依存先から再読み込みする。型登録表はルート、各cacheは所有moduleが再生成する。任意拡張は解除後に再検出・登録し、外部SDK/Mayaプラグインは再ロードしない。動的クラスのキャッシュは登録表が持つため、登録表の作り直しで生成クラスも廃棄される。更新後は保持中のNode/Plug・生成クラス等を取得し直す。全体のatomicな巻き戻しは保証しない。
- `mlib/maths/`: `Vector`/`Translate`/`Scale`/`Shear`(`om2.MVector` を継承)、`Quaternion`(`MQuaternion`)、`EulerRotate`(`MEulerRotation`。`Vector` の派生ではない)、`Matrix`(`MMatrix`)。om2 の関数へそのまま渡せ、演算は om2 の実装で高速に行う。意味は om2 に合わせる: `q1*q2` は q1 を先に適用、`v*m` は行ベクトルの方向変換、`m*v` は列ベクトルの積、位置の変換は `Matrix.transformPoint()`、分解は `MTransformationMatrix` の規約。値は可変でハッシュ不可(dict のキー・set の要素にできない)。`EulerRotate` は内部値が radian で order は om2 の番号(int。名前は `orderName`)。mlib独自APIもlowerCamelCaseを使う。戻り値は各メソッドの契約に従い、継承したom2のメソッド名と独自補助の名前を区別する。`easing` だけは標準 `math` のみ。
- `mlib/components/`: Mesh/NurbsCurveの部分要素を、作成時に番号を固定した参照として提供する(`Vertex`/`Vertices`、`CV`/`CVs`、`Edge`/`Edges`、`Face`/`Faces`、`UV`/`UVs`)。座標は都度シーンから取得する読み取り専用の参照で、座標の書込みは3.0.0で外した(書き換えはcmds.xform等を使う)。トポロジー変更後の番号の同一性は保証しない。
- 選択・名前空間・参照関係、単位、プラグイン導入状態、イベント・遅延実行は`mlib.common`へ置く。参照列挙は`mlib.common.references.listReferences()`、参照ノードは`mlib.nodes.Reference`で扱う。汎用UI・シーン/プロジェクト操作は利用側のMaya標準APIを使い、本体へ旧パッケージを再追加しない。
- `mlib/decorator.py`: `undoChunk`、`undoTransaction`、`nativeUnits`、`preservedSelection`、`preservedSkinShape`、`viewportOff`の既存6入口を公開する。fast/safeの状態管理・内部wrapper・フラグ正規化も同ファイルへ集約する。インスタンス固有のcontextは各クラスに残し、既存の装飾順序・Undo/fast/safeの意味を維持する。
- `mlib/util.py`: クラスに属さない`legalizeName`・`measure`・`mirrorArguments`の3関数を公開する。数学値と空間指定の内部helperは先頭`_`で区別し、標準ライブラリだけをimportする。ログは`mlib.logger`、進捗表示は`mlib.common.progressBar`が担当する。
- `mlib/__init__.py`は`core`・`util`等のモジュール、`reload()`、明示した基礎7コマンドを公開し、版番号`__version__`(現行`4.1.0`)を持つ。`__version__`は`__all__`に入れず、`maya/modules/mlib.mod`の6行と`_docs/source/changelog.rst`の先頭見出しと同じ値にする(`__tests__/unit/test_static_version.py`が三者の一致を検査する)。`Object`の正式入口は`mlib.core.object.Object`、拡張管理は`mlib.core.extensions`とし、ルートへクラス/関数を展開しない。旧`mlib._core`や移動前のcommon小モジュールの互換入口は残さない。再読み込みは廃止済みモジュール参照も除去する。

### MayaCommandPorts

HTools/mlibから独立した最小モジュール(依存は `maya.cmds` / `maya.utils` のみ)。GUI起動時のみ遅延実行でcommandPortを `:7001`(MEL)/`:7002`(Python)に開く。既存ポートは開き直さず、失敗はwarning出力に留める。VS Code連携(`tools/send_to_maya.py`)はこの `:7002` を使用する。無効化するには `maya/modules/MayaCommandPorts.mod` をmodules検索対象外へ移動する。

### integrations

- `integrations/slack/`: `post_message(text, channel="random", thread_ts=None)`。環境変数 `SLACK_API_BOT_TOKEN` が未設定または `slack_sdk` が無い場合は `RuntimeError`。
- `integrations/mgear/guide/`: mGearガイド(`isGearGuide` アトリビュートを持つtransform)の取得・更新ヘルパー。`update_guide()` は呼び出し時に初めて `mgear` を import するため、mGear未導入でも本モジュール自体のimportは可能。

### C++プラグイン(別リポジトリ)

C++のMayaプラグインは別リポジトリで管理し、submoduleとして取り込む。現在の対象は `maya/inhouse/MayaCinematicCameraHUD`(`.mll` を `release/plug-ins/windows/<Mayaバージョン>/` にコミットする構成)。

- **置き場所の規則**: このワークスペースで**編集する**リポジトリは `maya/inhouse/` 、編集せず成果物を使うだけのものは `maya/external/` にsubmoduleとして置く。編集後はまずプラグイン側リポジトリでコミットし、その後に親リポジトリでsubmoduleの参照を更新する。
- **ビルド**: `tools/build_maya_plugin.py <プラグインのフォルダ> --versions <年...>`(2022/2023/2024/2025/2026/2027 で実ビルドとロードを確認済み)(または VS Code のタスク「Maya plugin: Build MayaCinematicCameraHUD」)。Visual Studio・CMake・ツールセットを自動検出し、ビルドフォルダは `.maya-output/plugin-build/` 配下(Git対象外)に作る。`--list` で検出結果を確認できる。
- **devkit**: 別配布のdevkitは不要。Maya 2025/2027 のようにインストール先に `cmake/pluginEntry.cmake` が無い版や、Qt用zipが未展開の版は、`tools/maya_devkit.py` がインストール先(ヘッダ・lib・moc・Qt用zip)から `.maya-output/devkit/<年>/` にローカルdevkitを自動生成する(Program Files配下は書き換えず、管理者権限も不要)。別途入手したdevkitを使う場合は環境変数 `MAYA_DEVKIT_<年>` に `devkitBase` を指定する。ツールセットの対応は 2022=v142、2023=v142、2024=v143、2025=v143、2026=v145、2027=v145(`tools/build_maya_plugin.py` の `TOOLSETS`)。
- **ロード**: `maya/modules/<名前>.mod` の `MAYA_PLUG_IN_PATH` で検索パスに通すだけで、自動ロードはしない(Plug-in Manager または `cmds.loadPlugin` で読み込む)。初回ロード時にMayaの「信頼されていない場所からのロード」警告ダイアログが出てGUI(とcommandPort経由の送信実行)が止まるため、ロード前に信頼済みの場所へ登録しておく。登録は Preferences > Security > Plug-ins の「My trusted plugin locations」で「Add」するか、警告ダイアログで「Apply to all plugins in this location」にチェックして Allow する(各フォルダ1回のみ。プラグインのフォルダはバージョン別なので使う版の分だけ)。**スクリプトからの登録はできない**: `optionVar SafeModeAllowedlistPaths` への追記はMayaのSafeModeが拒否する(戻り値1・値は変化せずセキュリティログに reject/Deny)ため、迂回せず手動で行う。HToolsの「system > checkWorkspacePluginTrust」は、`maya/inhouse/` 配下で未登録の場所を確認して一覧表示し、Preferences画面を開く読み取り専用ツール。自動テストやCIでは、警告が出ないmayapy(`maya/inhouse/mlib/__tests__/runMaya.py` 等)を使う。
- **注意**: 上記の「mlib内では独自プラグインを用意しない」方針は mlib のコードに対するもので、別リポジトリのC++プラグインは対象外。ビルドすると追跡対象の `release/**/*.mll` が書き換わるため、リリースとしてコミットする意図が無い場合は `git checkout -- release/` で戻す。

## 開発上の注意

- Pythonの単体実行環境(venv)は用意されていない(pipはMaya起動用の `maya/site-packages/<年>/<グループ>` への取得だけ)。全てMaya本体(GUIまたはmayapy)を介して動作する前提で、純粋ロジックのテストであってもMaya経由で実行するのがこのリポジトリの標準的な方法。
- `maya/external/*` はGit submodule。変更が必要な場合は各submoduleのリポジトリ側で行う(親リポジトリからの直接コミット対象ではない)。
- 新規clone後は `git submodule update --init --recursive` が必要。
- mlib内では独自のMayaプラグインを実装・同梱・自動ロードしない。`MPxCommand` / `MPxNode` / `MFnPlugin` による登録は、Undo対応やバージョン差の回避目的でも追加しない。既存の内部プラグインもこの方針の解消対象とし、残存している場合は未対応箇所を明記する。Maya標準コマンドと既存のUndo可能な処理を優先し、実現できない機能は制限・未対応として明示する。`mlib.environment`による既存プラグインの状態照会・明示的なロード管理は、この禁止の対象に含めない。

## リグ検証の共通ワークフロー

リグの動作・計算を検証してユーザーへ見せる場合は、Codex・Claude Code・GitHub Copilot共通で、次の順序を標準とする。詳細と既存ツールの使い方は `docs/verification-videos.md` を参照する。

1. **検証リグを作成する**: 専用のMaya GUIと検証シーンを使い、期待する挙動が伝わる最小構成を作る。入力と補正後を色分けし、カメラを固定する。境界に達する動き・境界を超える入力・安全範囲への復帰を含める。作業中のユーザーシーンを破棄しない。
2. **計算式と数値を文字で表示する**: MayaのHUD等、録画対象のmodelPanelに映る表示を使う。式、変数の意味、単位、角度の基準、固定値、各フレームの入力値と実際のDG出力を表示する。度とラジアンを区別し、見やすい順序・文字サイズ・配置にする。固定の値は固定と明記し、実際に変化する値を毎フレーム更新する。
3. **動画を撮影して検証する**: `tools/verification_video.py` の `recordVideo()` を基本に、実際のMaya表示を録画する。動画と診断JSONを `.maya-output/verification/<実行ID>/` に保存する。数値判定と、完成MP4の実フレームで文字の可読性・数値の変化・動作を確認する。判定用の計算はリグ本体への追加と区別する。失敗は失敗として報告する。
4. **Google Driveへアップロードする**: 接続済みのDrive機能で、確認したMP4を `Maya検証動画` 内の対象フォルダへ保存する。新規動画を「リンクを知っている全員・閲覧者」に設定し、既存の別ファイルの権限は変えない。メタデータでサイズ・閲覧URL・共有権限を読み戻し、`attachDrive()` でローカル結果に登録する。
5. **閲覧リンクを報告する**: Driveが返したURL、動画内の色・数値の意味、検証結果と制限を簡潔に伝える。再生処理中ならその状態を伝え、iPad実機で未確認なら確認済みとしない。

このワークフローはユーザーが希望する通常のリグ検証成果物の流れとして扱い、毎回録画・Drive保存を提案だけで終えない。ユーザーがローカルのみ等を指定した場合はその指示を優先する。Drive接続や共有操作が使えない場合もローカル録画・検証まで進め、未完了の工程と理由を報告する。認証トークンをコード・ログへ保存せず、コネクター認証をスクリプトへ流用しない。動画・画像連番はGitやGitHub Pagesへ登録せず、Sphinx掲載やコミット・プッシュは別の依頼として扱う。
