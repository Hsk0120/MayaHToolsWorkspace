# WinAppKit

Windowsアプリ(FramePlayerなど)を配布するための、汎用の道具をまとめる場所。
しばらくはこのワークスペースの中で育て、形が固まったら別リポジトリとして独立させる予定。
Windows標準の機能だけを使い、外部のライブラリやツールには依存しない。

| 道具 | 内容 | 状態 |
| --- | --- | --- |
| IconBuilder | SVGで描いたアイコンから、Windowsのアイコン(.ico)を作る | あり |
| インストーラー | ファイルの配置、「アプリ」一覧への登録とアンインストール、関連付けなど | 予定 |

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
CSSの細かな指定は使えない。アイコンは図形とパスだけで描くこと。
.ico にはサイズごとにPNGを入れる(Windows Vista以降の形式)。
