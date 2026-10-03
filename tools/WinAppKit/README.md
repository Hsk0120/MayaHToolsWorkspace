# WinAppKit

Windowsアプリ(FramePlayerなど)を配布するための、汎用の道具をまとめる場所。
しばらくはこのワークスペースの中で育て、形が固まったら別リポジトリとして独立させる予定。
Windows標準の機能だけを使い、外部のライブラリやツールには依存しない。

| 道具 | 内容 |
| --- | --- |
| IconBuilder | SVGで描いたアイコンから、Windowsのアイコン(.ico)を作る |
| WinAppSetup | 汎用のインストーラー。アプリの設定ファイル(INI)から、そのアプリのセットアップ(Setup.exe)を作る |

## ビルド

Visual Studio 2022(C++ によるデスクトップ開発)と CMake を使う。

```bat
cmake -S . -B build -G "Visual Studio 17 2022" -A x64
cmake --build build --config Release
```

`build/` はGit管理対象外。

## IconBuilder

```bat
IconBuilder.exe --svg <既定.svg> [--svg-for 16,20=<16px用.svg>] [--svg-for 24=<24px用.svg>]
                [--sizes 16,20,24,32,40,48,64,256] --ico <出力.ico> [--png-dir <フォルダ>]
```

- `--svg`: 既定で使うSVG。`--svg-for` で指定の無いサイズはこれで作る。
- `--svg-for <サイズ,...>=<SVG>`: そのサイズだけ別のSVGで作る(何度でも指定できる)。小さいサイズは細部を省き、
  画素の升目で描いたSVGを使うと、潰れずにくっきり出る(例: `viewBox="0 0 16 16"` で座標1つが1画素)。
- `--sizes`: 作るサイズ。既定は 16,20,24,32,40,48,64,256(Windowsの拡大率100〜250%で使われる大きさ)。
- `--png-dir`: サイズごとのPNGも書き出す(見た目の確認用)。

SVGはWindows標準のDirect2Dで描く。対応するのはSVGの一部(図形・パス・塗り・線・変形など)で、文字(text要素)や
CSSの細かな指定は使えない。アイコンは図形とパスだけで描くこと(描画ソフトで作るときは、文字をアウトライン化する)。
.ico にはサイズごとにPNGを入れる(Windows Vista以降の形式)。

## WinAppSetup(汎用インストーラー)

1つのexeが、セットアップを作る・インストール・アンインストールの3つを受け持つ。

```bat
rem セットアップを作る(このexeを写し、写した方にアプリの中身とアイコンを埋め込む)
WinAppSetup.exe --build <アプリ.wak.ini> --out <AppSetup.exe>

rem インストール(画面あり)。/S で画面を出さない。--dir でインストール先、--no-file-types で関連付けをしない
AppSetup.exe [/S] [--dir <フォルダ>] [--no-file-types]

rem アンインストール(設定の「アプリ」から呼ばれる)。/S で画面を出さない。--remove-data で設定などのデータも消す
<インストール先>\Uninstall.exe --uninstall [/S] [--remove-data]
```

終了コードは 0=成功、1=取り消し、2=失敗。記録は `%TEMP%\<Id>-setup.log` / `<Id>-uninstall.log` に書く。

### インストールすること

すべてこのユーザーだけ(`HKEY_CURRENT_USER` と `%LOCALAPPDATA%`)に入れるので、管理者権限は要らない。

| 内容 | 場所 |
| --- | --- |
| ファイル | 既定は `%LOCALAPPDATA%\Programs\<Id>`(設定の `InstallDir`)。自分自身を `Uninstall.exe` として写す |
| 設定の「アプリ」一覧 | `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\<Id>`(名前・バージョン・発行元・アイコン・サイズ・アンインストールのコマンド) |
| exeの場所の登録(App Paths) | `HKCU\...\CurrentVersion\App Paths\<exe名>`(「ファイル名を指定して実行」や、ほかのプログラムから見つけられる) |
| スタートメニュー | `%APPDATA%\Microsoft\Windows\Start Menu\Programs\<Name>.lnk` |
| 関連付け(選んだときだけ) | 開き方の定義 `Classes\<ProgId>`、「別のアプリを選択」の表示 `Classes\Applications\<exe名>`、拡張子の `OpenWithProgids` に値を1つ、右クリック `Classes\SystemFileAssociations\<拡張子>\shell\<ProgId>`、既定のアプリの候補 `Software\<Id>\Capabilities` と `Software\RegisteredApplications` |

既定のアプリそのものは設定しない(Windowsの決まりで、既定のアプリは本人が設定画面で選ぶ)。
インストールの完了画面から、設定の「既定のアプリ」を開ける。

### 記録とアンインストール

インストールで作ったファイル・フォルダ・レジストリは、すべてインストール先の `uninstall.wak`(UTF-8のテキスト)に
記録する。アンインストールは、この記録を逆順にたどって、記録したものだけを消す。

- 自分のキー(`key`)は中身ごと消す。ほかのアプリと共有するキーは、自分が足した値(`value`)だけを消す。
- 途中に新しく作ったフォルダ(`dir`)・キー(`emptykey`)は、空になったときだけ消す(ほかの人が置いたものを消さない)。
- インストール先のUninstall.exeは動いている間は自分を消せないので、一時フォルダへ自分を写し、写した方が続きを行う。
  写した方は、終わった後に自分を消す。
- 「設定などのデータも削除する」を選んだときだけ、設定ファイルの `[UserData]` を消す。

更新(同じアプリが入っているときのインストール)は、同じ場所へ上書きする。前の版にあって今の版に無いファイル・登録は
消す。途中で失敗したときは、置き換える前のファイル(インストール先の `.wak-backup` に控える)を戻し、新しく作ったものを消す。

### 安全のための決まり

- インストール先: ドライブの直下、Windowsやユーザーの大事なフォルダ(とその親)、ほかのファイルが入っているフォルダ
  (このインストーラーの記録が無いもの)には入れない。
- `[UserData]` で消せるのは、`HKCU\Software\` の下と、`%LOCALAPPDATA%`・`%APPDATA%` の下のうち、
  途中にアプリの `Id` の階層があるものだけ(例: `HKCU\Software\FramePlayer`、`{LocalAppData}\FramePlayer`)。
  `Microsoft`・`Classes`・`Temp`・`Programs` など共有の場所は消さない。フォルダを消すときは、ジャンクションなどの先へは入らない。
- 起動中のアプリは、Windows標準のRestart Managerで見つけ、閉じてよいかを聞いてから閉じる(画面なしのときは閉じる)。

### アプリの設定ファイル(.wak.ini)

パスは、この設定ファイルのフォルダからの相対パス(絶対パスも書ける)。行頭が `;` か `#` の行は注釈
(値の後ろには注釈を書けない。`;` は拡張子の区切りに使うため)。

```ini
[App]
; 識別名(英数字と . _ -)。「アプリ」一覧の登録名・記録の名前
Id=FramePlayer
; 表示名
Name=FramePlayer
; バージョン。省くと本体のexeのバージョン情報(VERSIONINFO)から読む
Version=1.0.0
Publisher=...
Description=...
; ホームページ(省略可)
Url=https://...
; 本体のexe([Files] の行き先のどれか)
Executable=FramePlayer.exe
InstallDir={LocalPrograms}\FramePlayer
StartMenuShortcut=yes
; セットアップのexeと画面に付けるアイコン
SetupIcon=../resources/icon/FramePlayer.ico

[Files]
; 元=行き先(インストール先からの相対パス。.. は使えない)
../FramePlayer.exe=FramePlayer.exe

[FileTypes]
; 関連付け(ProgIdを書いたときだけ)
ProgId=FramePlayer.Video
Description=動画 (FramePlayer)
Extensions=.mp4;.mov
; 右クリックの文字(省くと右クリックには出さない)
ContextMenu=FramePlayerで開く
; インストールの画面で、関連付けをしないことも選べる
Optional=yes

[UserData]
; アンインストールで「データも削除」を選んだときだけ消す
Registry=HKCU\Software\FramePlayer
Folder={LocalAppData}\FramePlayer
```

置き換え文字: `{LocalAppData}`(`%LOCALAPPDATA%`)、`{AppData}`(`%APPDATA%`)、`{LocalPrograms}`(`%LOCALAPPDATA%\Programs`)、
`{InstallDir}`(インストール先)。

### 中身の形式

セットアップのexeは、中身をリソース(RCDATAの `WAKPACKAGE`)として持つ。形式は `src/setup/Package.h` を参照
(アプリの説明 + ファイル。ファイルはWindows標準の圧縮API(LZMS)で、小さくなるときだけ圧縮する)。
アイコンは RT_ICON / RT_GROUP_ICON の1番として入れる(エクスプローラーでのセットアップのexeのアイコンになる)。

### 確かめたこと(FramePlayer、2026-10-03)

- 画面なしのインストール → 上の表のとおり登録され、記録に作ったものだけが並ぶ。
- 1.0.1 への更新 → バージョンが変わり、新しい版に無いファイルが片付き、前の版で作ったフォルダ・キーは記録に引き継がれる。
- 起動中のFramePlayerがある状態で、「アプリ」一覧と同じ画面なしのアンインストール → アプリを閉じ、関係するレジストリと
  ファイルがインストール前と1行も違わない状態に戻る。アプリの設定と連携の鍵は残る。一時フォルダへ写した自分も消える。
- 試験用のアプリで「データも削除」→ `Id` を含むキー・フォルダだけが消え、含まないものは「安全でないので消しません」と
  記録して残す。ユーザーのフォルダそのもの・ほかのファイルが入ったフォルダへのインストールは拒否する。
- 画面(確認・完了・アンインストールの確認・完了)を出して操作できる。
- Windowsのパッケージ一覧(`Get-Package -ProviderName Programs`)に「FramePlayer 1.0.0」として出る。

### 未対応・制限

- PC全体(`Program Files`・全ユーザー)へのインストールは未対応(管理者権限が要る。今はユーザー単位だけ)。
- コード署名は未対応。署名していないセットアップをインターネットから落とすと、SmartScreenの警告が出る
  (社内の共有フォルダから配るなら、通常は出ない)。
- Windows 11の新しい右クリックメニューの最初の段には出ない(「その他のオプションを確認」の中に出る。最初の段に出すには
  パッケージ化(MSIXなど)が必要)。
- `winget list` には出なかった(`Get-Package` や「アプリ」一覧と同じ登録をしているが、wingetが表示しない理由は未調査)。
