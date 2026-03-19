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
maya_2026_en.bat
```

- `maya_2022_en.bat`: Maya 2022 (en_US)
- `maya_2024_en.bat`: Maya 2024 (en_US)
- `maya_2026_en.bat`: Maya 2026 (en_US)

## ▼構造イメージ

```text
maya/
├ external              <- 外部ツール
├ inhouse               <- 内製ツール
├ modules               <- Maya用 .mod ファイル
├ maya_2022_en.bat      <- Maya起動バッチ
├ maya_2024_en.bat      <- Maya起動バッチ
├ maya_2026_en.bat      <- Maya起動バッチ
└ maya_core.bat         <- 共通設定バッチ
```

## ▼ディレクトリ補足

- `maya/external`: 外部サブモジュール群(mGear, cymel, AnimationAid ほか)
- `maya/inhouse/Hlib`: 共通ライブラリ(検索付きメニュー部品など)
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