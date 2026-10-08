# Maya HTools Workspace

- バッチ経由でMayaを起動することで、HToolsを含む独自のMaya作業環境を立ち上げられるようにしています。
- 標準環境へ影響を与えない構成にすることで、環境起因の問題切り分けを行いやすくしています。
- https://github.com/Hsk0120/MayaHToolsWorkspace

## ▼ドキュメント

[hlib Sphinxドキュメント（GitHub Pages）](https://hsk0120.github.io/MayaHToolsWorkspace/)

hlibの導入方法・使用例・APIリファレンスを閲覧できます。スマートフォンからもアクセスできます。

[hedit Sphinxドキュメント（GitHub Pages）](https://hsk0120.github.io/MayaHToolsWorkspace/hedit/)

heditの使い方と Preferences 各項目の説明を閲覧できます。

[hrig Sphinxドキュメント（GitHub Pages）](https://hsk0120.github.io/MayaHToolsWorkspace/hrig/)

hrigの機能仕様・テスト方法・テストシーン・計測結果を掲載します（本変更の公開後に利用可能）。
[ソースと目次](maya/inhouse/hrig/docs/index.rst)／[ビルド手順](maya/inhouse/hrig/docs/testing.rst)

[FramePlayer Sphinxドキュメント（GitHub Pages）](https://hsk0120.github.io/MayaHToolsWorkspace/frameplayer/)

コマ送り・2本の比較・連番画像に対応した動画プレイヤー FramePlayer の使い方と、Mayaとの連携の手順を画像付きで説明します。
[ビルド手順](maya/inhouse/FramePlayer/docs/README.md)

## ▼カスタム内容

- `maya_core.bat`で各種ツールパスを設定し、起動バッチで環境を切り替えています。
- mGearやcymelなどの外部パッケージはGit submoduleで管理しています。
- 内製ツールは`maya/inhouse/HTools`配下に集約しています。
- HToolsはMaya起動時にメニューバーへ自動追加される構成です。

### サイクル原因の調査

`HTools > rigging > inspectCycles` から調査画面を開きます。全体・選択ノード・名前指定
（例: `rig:joint1.translateX`、複数は空白区切り）を対象に **Inspect** を押します。
起動済みのMayaでメニューへ未反映の場合は、Script EditorのPythonで実行できます。

```python
from HTools.rigging import inspectCycles
inspectCycles.run()
```

一覧の経路を選ぶと、Mayaの検出順、ノード型、検出アトリビュートの直接接続
（接続元 → 接続先）、親子関係を表示します。**Select Nodes in Selected Path** で
Node Editor等の調査につなげられます。全結果はUTF-8テキストへ保存できます。
調査は接続・値・評価時のサイクルチェック設定を変更しません。

検出にはMayaの`cycleCheck`、対象解決・接続照会・ノード選択にはhlibを使用します。
DAGを含む検索は既定で有効、検索上限は10秒です。大きいシーンは対象を絞るか
**First complete cycle only** を使ってください。検出順は内部依存や部分経路も含み、
表示した直接接続には経路外の接続も含まれます。結果は原因候補であり、自動修復はしません。
検索上限で打ち切られたかを確実に判別できないため、0件でも問題なしとは断定できません。
expressionの実行時依存やIK付きインスタンスには未検出・誤検出の制約があります。
シーン編集後は再調査してください。

### Aimの1〜2軸変換

既存のaimConstraintノードを1つ選択し、`HTools > rigging > convertAimAxes`を開きます。
Equivalent Euler solution・Hinge / 2-axis direction・Per-axis twist の3方式を、X/Y/Z/XY/XZ/YZで比較できます。
**Convert / Switch Method** で適用し、**Restore Original Aim and Settings** で復元します。Undo/Redoにも対応します。
復元時は変換・補正ノードを全て削除し、元Aimの設定値と直接接続へ戻します。
未選択軸のAim接続は変換時の値へ固定します。元の接続サイクルを解消する機能ではありません。
方式2の狙う方向は回転軸以外を指定してください（例：XY回転ならZ方向）。
詳しい挙動・制約・起動コードは[利用説明](maya/inhouse/hrig/docs/aim_axis_conversion.rst)を参照してください。

## ▼起動方法

想定している起動バッチは以下です。

```bat
cd maya
maya_2022_en.bat
maya_2023_en.bat
maya_2024_en.bat
maya_2025_en.bat
maya_2026_en.bat
maya_2027_en.bat
rem 日本語: *_ja.bat
```

- `maya_2022_en.bat`: Maya 2022 (en_US)
- `maya_2023_en.bat`: Maya 2023 (en_US)
- `maya_2024_en.bat`: Maya 2024 (en_US)
- `maya_2025_en.bat`: Maya 2025 (en_US)
- `maya_2026_en.bat`: Maya 2026 (en_US)
- `maya_2027_en.bat`: Maya 2027 (en_US)
- `maya_<version>_ja.bat`: 日本語UI (`ja_JP`)

起動バッチはファイル名の `maya_<version>_<language>.bat` を解析して、
Mayaのバージョンと言語を共通処理へ渡します。ファイル名と起動設定を別々に変更する必要はありません。

### macOS

macOSでは`.command`ランチャーを使用します。ファイル名からバージョンと言語を判定します。

```bash
cd maya
chmod +x maya_core.command maya_*_en.command maya_*_ja.command
./maya_2027_en.command
./maya_2027_ja.command
```

標準のMaya配置は`/Applications/Autodesk/maya<version>/Maya.app`です。
別の場所にインストールしている場合は、起動前に`MAYA_EXE`へMaya実行ファイルのパスを指定してください。

## ▼構造イメージ

```text
maya/
├ external              <- 外部ツール
├ inhouse               <- 内製ツール
├ modules               <- Maya用 .mod ファイル
├ maya_2022_en.bat      <- Maya起動バッチ
├ maya_2024_en.bat      <- Maya起動バッチ
├ maya_2025_en.bat      <- Maya起動バッチ
├ maya_2026_en.bat      <- Maya起動バッチ
├ maya_2027_en.bat      <- Maya起動バッチ
└ maya_core.bat         <- 共通設定バッチ
```

macOS用の起動ファイルは`maya_<version>_<language>.command`と
`maya_core.command`です。

## ▼ディレクトリ補足

- `maya/external`: 外部サブモジュール群(mGear, cymel, AnimationAid ほか)
- `maya/inhouse/hlib`: Mayaノード・アトリビュートラッパー、形状操作、数学型などの共通ライブラリ
- `maya/inhouse/HTools`: Mayaメニューから起動する社内ツール
- `maya/modules`: 各ツールをMayaへ認識させる`.mod`定義
  - `metahuman_for_maya.mod`・`pose_driver_connect.mod`はこのワークスペースで記述した定義で、
    Windows版だけを登録します(MetaHumanForMaya: Maya 2024〜2027、PoseDriverConnect: Maya 2022・2024・2026・2027)。
    macOS・Linuxでは両製品を読み込みません。

## ▼セットアップ

```bash
git clone <this-repo-url>
cd MayaHToolsWorkspace
git submodule update --init --recursive
```

## ▼メモ

- `maya_core.bat`は、上記バージョン別バッチから呼ばれる共通処理です。
- `%USERPROFILE%\Documents\maya\<version>\Maya.env`が存在する場合、起動時に読み込まれます。
## VS CodeからMayaへ実行

`MayaHToolsWorkspace.code-workspace`をVS Codeで開き、Pythonファイルを保存して **Ctrl+Shift+B** でMayaへ送信します。
送信はMaya 2027のmayapyを使用し、追加拡張機能は不要です。
設定・バージョン変更は[VS Codeの使い方](docs/vscode.md)を参照してください。

## hedit ドキュメント

エディター hedit の使い方と Preferences 各項目の説明を Sphinx で `maya/inhouse/hedit/docs` に用意しています(スクリーンショット付き)。
ビルド手順は[hedit ドキュメントのビルド](maya/inhouse/hedit/docs/README.md)を参照してください。

## hlib ドキュメント

Maya 2022～2027の個別・一括テストは [hlibのバージョン別テスト](docs/hlib-testing.md) を参照してください。

Sphinx による日本語ガイドと API リファレンスを `maya/inhouse/hlib/_docs` に用意しています。
Maya を起動せず、ソースから HTML を生成できます。
手順は[hlib ドキュメントのビルド](maya/inhouse/hlib/_docs/README.md)を参照してください。

hlibの公開配置は `nodes`・`plugs`・`components`・`maths`・`cmds`・`common`・`json` です。
シーン状態・標準UI・環境設定・イベント・汎用処理は `common` にまとめ、
ログは `hlib.logger`、Undo等のデコレーターは `hlib.decorator` から利用します。
Objectと拡張登録・管理の入口は `_core` に置き、`from hlib._core.object import Object`、
`from hlib._core import extensions` から取得します。ルートへは再公開しません。
クラス・コマンドの公開名は各パッケージの `__init__.py`、Node/Plugの型対応は同ファイルの
`_WRAPPER_CLASSES` で明示します。追加・削除時はリポジトリルートで
`python tools/check_hlib_exports.py` を実行すると、Mayaを起動せず公開漏れを検査できます。
複数形APIも通常のメソッドとして定義し、共通処理へ委譲します。
旧importの対応は[APIの命名と移行](maya/inhouse/hlib/_docs/api_naming.rst)を参照してください。
