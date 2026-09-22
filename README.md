# Maya HTools Workspace

- バッチ経由でMayaを起動することで、HToolsを含む独自のMaya作業環境を立ち上げられるようにしています。
- 標準環境へ影響を与えない構成にすることで、環境起因の問題切り分けを行いやすくしています。
- https://github.com/Hsk0120/MayaHToolsWorkspace

## ▼カスタム内容

- `maya_core.bat`で各種ツールパスを設定し、起動バッチで環境を切り替えています。
- mGearやcymelなどの外部パッケージはGit submoduleで管理しています。
- 内製ツールは`maya/inhouse/HTools`配下に集約しています。
- HToolsはMaya起動時にメニューバーへ自動追加される構成です。

## ▼起動方法

想定している起動バッチは以下です。

```bat
cd maya
maya_2022_en.bat
maya_2024_en.bat
maya_2025_en.bat
maya_2026_en.bat
maya_2027_en.bat
rem 日本語: *_ja.bat
```

- `maya_2022_en.bat`: Maya 2022 (en_US)
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
- `maya/inhouse/Hlib`: Mayaノード・属性ラッパー、形状操作、数学型などの共通ライブラリ
- `maya/inhouse/HTools`: Mayaメニューから起動する社内ツール
- `maya/modules`: 各ツールをMayaへ認識させる`.mod`定義

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

## Hlib ドキュメント

Sphinx による日本語ガイドと API リファレンスを `maya/inhouse/Hlib/docs` に用意しています。
Maya を起動せず、ソースから HTML を生成できます。
手順は[Hlib ドキュメントのビルド](maya/inhouse/Hlib/docs/README.md)を参照してください。
