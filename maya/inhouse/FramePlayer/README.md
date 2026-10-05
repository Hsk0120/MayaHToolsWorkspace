# FramePlayer

コマ送りと2本並べての比較に特化した、Windows専用の動画プレイヤー。Mayaのタイムスライダーと双方向に連携できる。

利用者向けの説明(画像付き・日本語/英語)は [FramePlayer ドキュメント(GitHub Pages)](https://hsk0120.github.io/MayaHToolsWorkspace/frameplayer/)。
元の文書は `docs/`(Sphinx。ビルドと画像の撮り方は [docs/README.md](docs/README.md))。このREADMEは開発者向けの詳細。

- Windows標準機能(Media Foundation / Win32 / GDI)だけを使い、外部ライブラリには依存しない。
- 開いたときに「コマ番号の目次」(全コマの表示時刻とキーフレーム)を作る。mp4/movはファイル内の目次
  (サンプルテーブル)を直接読むので、映像データを読まずに済む(4K60fps・1時間・36GBで約1秒)。
  それ以外の形式は、デコードせずに圧縮されたままのコマを最後まで読んで作る。
  デコードしたコマは目次と照合して番号を決めるので、途中から読んでも番号がずれない。
  照合できないコマは表示せず、別のコマで代用しない。
  可変フレームレートの動画(Xbox Game Barの録画など)も、コマごとの本来の時刻のまま扱う
  (Windowsの映像処理が色変換・縮小の際に平均フレームレートの等間隔へ時刻を付け直す機能は止めている)。
- デコードと縮小はGPU(Direct3D 11、Windows標準)で行い、結果は動画本来の形式(YUVのNV12・10bitのP010)のまま
  GPUのメモリにキャッシュする。主メモリへ写さないので速く、RGBで主メモリに持つより約2.7倍多くのコマが入る。
  GPUのメモリに置けない環境ではGPUでデコードして主メモリへ、GPUが使えなければCPUでデコードする(自動で切り替える)。
- 色は動画に記録された色の情報(行列・範囲・色域・伝達関数・ビット数)を読み、自前のシェーダーで規格どおりに
  RGBへ戻す。味付けはせず、ニュートラルに出す(下記「色の扱い」を参照)。HDR(PQ・HLG)と10bitにも対応する。
- 映像は描画専用のスレッドがGPU(Direct3D 11 + Direct2D、Windows標準)で描き、画面の書き換え(垂直同期)に
  合わせて表示する。再生中は表示するコマが変わったときだけ描き、変わらない間は次のコマの時刻まで眠る。再生中に表示するコマも描画スレッドが経過時間から決めるので、操作部の描画などで
  UIスレッドが止まっても再生は止まらない。再生中は画面の省電力(消灯)を止める。
- デコードしたコマは上限付きのキャッシュに入れ、裏のスレッドが表示位置の先(進む向き)を先読みする。
  スライダーのドラッグ中は表示位置の前後を同じ幅で先読みし、キャッシュの帯が行ったり来たりしないようにする。
  上限を超えたら表示位置から遠いコマから捨てるので、長い動画も扱える。
- キャッシュに無い位置へ移ったときは、デコードを待つ間、近いキーフレームの縮小画像を「Loading…」と重ねて
  仮に表示する(下記「軽さ」を参照)。

## 現在の状態

| 段階 | 内容 | 状態 |
| --- | --- | --- |
| 1 | 動画1本の読み込み・←→でのコマ送り・コマ番号表示・確認用ツール | 完了 |
| 1.5 | タイムスライダー・再生ボタン(Space)・ループ再生 | 完了 |
| A | 先読みキャッシュ方式(目次・上限付きキャッシュ・裏での先読み)。長い動画に対応 | 完了 |
| A2 | 高速化: GPUでのデコード、mp4/movの目次の直接読み取り(4K60fps・1時間の動画に対応) | 完了 |
| A3 | 映像をGPUの描画専用スレッドで表示(UIスレッドの停止でコマ落ちしない) | 完了(ローカル画面での60fps測定は未) |
| A4 | キャッシュをGPUのメモリへ置き、小さい形式(NV12)で持つ | 完了 |
| E | 音声の再生と音量の操作(スピーカーのボタン・音量スライダー・M/↑↓キー、設定の保存) | 完了 |
| G | タイムスライダーをMayaと同じ構造に(レンジスライダー・全体範囲と再生範囲・動画の開始)、連携の窓口(TimeSync) | 完了 |
| H | Mayaとの双方向連携(現在フレーム・再生範囲・同期しての再生)、単体パッケージ化 | 完了 |
| A5 | 軽量化: キャッシュの上限見直し・再生中の空回り解消・背面/休止時の抑制・キーフレームの仮表示 | 完了 |
| B | J/K/L・逆再生・往復ループ・再生速度・Alt+←→ | 未着手 |
| C | 動画2本を左右に並べて表示、同じコマ番号で同期、片方のオフセット | 完了 |
| D | 連番画像の読み込み(png・jpg・tif・bmp・gif・webp・heif・avif・jxl・jxr・exr。exrは自前で読む) | 完了 |
| D2 | キャッシュ上限の設定画面 | 未着手 |
| F | 色の正確な再現(色の情報の読み取り・自前のシェーダーでの変換・色域の変換・HDR・10bit・手動の指定・数値での確認) | 完了 |

## 対応形式

WindowsのMedia Foundationが読める形式(デコードはWindowsに任せ、外部のライブラリは使わない)。
Windowsに入っている映像のデコーダーのうち、ffmpegで確認用動画を作れるものはすべて、コマ番号(順・逆・ランダム)と
色を確かめた(下記「全コーデックの確認」)。

| コーデック | 確認した入れ物 | 必要なもの |
| --- | --- | --- |
| H.264 | mp4・mov・mkv・ts・m2ts・avi・3gp | Windows標準(「N」エディションはメディア機能パック) |
| HEVC(H.265、8bit・10bit・HDR) | mp4・mkv・ts | 拡張機能「HEVC Video Extensions」 |
| AV1(8bit・10bit) | mp4・mkv・webm | 拡張機能「AV1 Video Extension」 |
| VP9(8bit・10bit・HDR) | mp4・webm・mkv | 拡張機能「VP9 Video Extensions」 |
| VP8 | webm・mkv | 拡張機能「VP9 Video Extensions」(VP8も含む) |
| MPEG-2 | mpg・ts・vob | 拡張機能「MPEG-2 Video Extension」 |
| MPEG-1 | mpg | Windows標準 |
| MPEG-4 Part 2(Simple Profile)・H.263 | mp4・mov・avi・3gp | Windows標準 |
| MS-MPEG4 v2・v3(DivX 3) | avi | Windows標準 |
| WMV7・WMV8 | wmv | Windows標準(WMV9・VC-1も読めるはずだが、確認用動画を作れないので未確認) |
| MJPEG | avi・mov | Windows標準 |
| DV(NTSC) | avi | Windows標準 |
| Theora | mkv | 拡張機能「Web Media Extensions」 |

- 拡張機能はMicrosoft Storeで無料で入る。入っていないと、その形式だけが「出力形式を設定できません
  (HRESULT 0xC00D5212)」(対応するデコーダーが無い)で開けない(プレイヤー自体は使える)。入っているかは
  PowerShell の `Get-AppxPackage *VP9*`(HEVCなら `*HEVC*` など)で確かめられる。
- ProResは読めない(将来、`FrameSource` の派生クラスを追加して対応できる設計)。
- Windows側の制限で読めないもの・正しく読めないもの:
  - MPEG-4 Part 2のBフレーム(Advanced Simple Profile。XviD・DivXの多くの設定)。Windowsのデコーダーは
    Simple Profileだけで、Bフレームは正しい絵にならない。
  - movに入ったDV、ogg・ogv(Theoraはmkvなら読める)。Windowsが開けない。
  - 映像だけの短い(数秒の)mpg・vob。Windowsが開けない(音声があるか、長ければ開ける)。
- 入れ物・コーデックごとの扱い(コマ番号を正しく決めるため):
  - 10bitの動画は、mp4/movの設定ボックス(HEVCのhvcC・VP9のvpcC・AV1のav1C)から分かるビット数で見分け、
    10bitのときだけP010で受け取る(デコーダーによっては8bitの動画でもP010を受け付けてしまい、読むと失敗・停止
    するため。VP9で確認)。デコーダーが途中で形式を変えた場合(10bitのVP9)は、それに合わせる。
  - aviには表示時刻が無く、Bフレームがあるとデコーダーが出すコマの時刻と絵の順番が食い違う。aviでは、
    キーフレームから数えた順番でコマ番号を決める(デコーダーは表示の順に出す)。
  - ts・m2tsは全コマにキーフレームの印が付き、Windowsのシークも大まか(指定より後のキーフレームから出る・終わり
    近くでは失敗する)。シークしたら最初に出たコマを確かめ、目的より後なら手前からやり直す。確かめた位置は覚えておく。
  - MPEG-1/2(mpg・ts・vob)は圧縮されたコマの一部にしか時刻が無いので、全体をデコードして目次を作る(開くのに
    時間がかかる)。シークの直後はデコーダーが付ける時刻が絵と食い違う(古いコマも混じる)ので、時刻が目次と続けて
    2つ合ったところを基準にし、そこからは出た順番で番号を決める。GPUでデコードするとシークが長く止まる・作り直した
    デコーダーでシークできなくなることを確認したので、MPEG-1/2はCPUでデコードする(デコードが軽い形式)。
  - Windowsの読み込みは、まれに1コマを読む処理が返らなくなる(aviのDVなどで確認)。読み込みは非同期で頼み、
    10秒待っても届かなければ、その読み込み本体を見捨てて作り直し、最後に返したコマの続きから読む。
    非同期では、結果を受け取った直後はまだ前の要求が終わっていない扱いになることがあるので、シーク・読み込みが
    `MF_E_INVALIDREQUEST` で断られたら少し待ってやり直す。
  - DVはデコーダーがYUY2(4:2:2)を出すので、Windowsの映像処理を通さずYUY2のまま受け取る(映像処理を通すと、
    大きさが変わり、GPUではコマが1つずれた)。横長・縦長の画素(DVの10:11など)は、表示のときに縦横比を直す。
  - MJPEGは、JPEG(JFIF)の決まりで大きさによらずBT.601・全範囲として色を戻す。

## 操作

画面の文字(ボタン・メニュー・メッセージ・インストーラー・Maya側のパネル)は英語。

| キー | 動作 |
| --- | --- |
| → / ← (Alt + . / Alt + , も同じ) | 1f進む / 戻る。再生範囲の端では反対の端へ回り込む(Mayaと同じ) |
| Shift + → / ← | 10f進む / 戻る |
| Home / End | 再生範囲の最初 / 最後(Alt + Shift + V でも最初へ。Mayaと同じ) |
| I / O | 再生範囲の最初 / 最後を、今のフレームにする |
| Space / Alt + V | 再生 / 停止(Alt + V はMayaと同じ) |
| Esc | 再生を止める(Mayaと同じ)。フルスクリーン中は元のウィンドウに戻す(再生は続く) |
| K を押しながら映像の上を左ドラッグ | フレームを動かす(Mayaの仮想タイムスライダー)。左右に8ピクセルごとに1f。比較中は2本ともオフセットを保って動く。再生中はドラッグの間だけ止まる |
| Ctrl+F / 映像のダブルクリック / 右クリックのメニュー | フルスクリーンの切り替え(モニター全体に広げる。操作部はそのまま出る) |
| 映像の上で右クリック | メニュー: 再生/停止・フルスクリーン・色の情報の表示・色の解釈の手動の指定(下記「色の扱い」) |
| M | 消音の切り替え |
| ↑ / ↓ | 音量を5%上げる / 下げる(消音中なら消音も解除する) |
| Ctrl+O | 動画をファイル選択画面で開く |
| Ctrl+Shift+O | 比較用の2本目をファイル選択画面で開く |
| [ / ] | 比較中、2本目のオフセットを1f減らす / 増やす(Shift併用で10f) |
| 映像の上で中ボタンドラッグ | 左右に8ピクセル動かすごとに1f。比較中は、右の映像の上なら2本目のオフセットを変え、左の映像の上なら1本目だけを動かす(右の表示はそのままで、オフセットが逆に変わる)。1本のときはその動画のコマを動かす。再生中はドラッグの間だけ止まり、離すと再生を続ける |

### タイムスライダー(Mayaと同じ構造)

映像の下は、Mayaと同じく「タイムスライダー」と「レンジスライダー」の2段。今後のMayaとの連携(同じフレームを
表示・同期して再生)に備えて、フレーム番号と再生範囲の考え方もMayaに合わせている。

- **タイムスライダー(上段)**: 再生範囲だけを目盛りで表示する。数字の間隔は幅に合わせて1・2・5・10…から選ぶ。
  現在のフレームは1コマ分の明るい区画と、その右下の番号の箱で示す。下端のオレンジの帯はキャッシュに入っているコマ。
  段のどこをクリック・ドラッグしても、そのフレームへ移動する。右に現在のフレームの欄(押すと番号を入力できる)と、
  範囲の最初へ・1コマ戻る・再生/停止・1コマ進む・範囲の最後へのボタン。
- **レンジスライダー(下段)**: Mayaと同じ並びで、左から「全体範囲の最初」「再生範囲の最初」、バー、
  「再生範囲の最後」「全体範囲の最後」の欄。4つとも押すと番号を入力できる。バーが全体範囲で、明るい部分が再生範囲。
  両端のつまみをドラッグすると範囲の最初・最後を、範囲の中をドラッグすると長さを保ったまま範囲を動かせる。
  ダブルクリックで全体範囲と直前の再生範囲を切り替える(Mayaと同じ)。全体範囲の欄は控えめな色、再生範囲の欄は
  普通の色で見分けられるようにしている。下端のオレンジの帯はキャッシュに入っているコマ。その右に「Clip start」の欄、
  フレームレート、「Maya Sync」(下記)、「File」「Compare」、音量。
- **動画の外の見え方**: タイムスライダーの目盛りとレンジスライダーのバーは、動画の外の部分を暗く塗る。
  動画の外のフレームでは映像の代わりに「Out of range」と、動画がタイムラインのどこにあるか(例: Video: 1001-8200)を出す。
  現在のフレームが再生範囲の外にあるときは、目盛りの外れている側の端に矢印付きで番号を出す(例: 9000 ▶)。
- **説明とホバー**: 操作部の部品にマウスを乗せると、説明(ツールチップ。ショートカットキーも出す)が出る。
  押せるボタンと欄は、マウスが乗ると明るくなる。
- **タイムラインと動画**: Mayaと同じく、タイムラインのフレーム番号は動画の長さに縛られない。全体範囲・再生範囲・
  現在のフレームは、負の番号や動画より後も含めて自由に決められる。動画はタイムラインの「Clip start」の番号から
  置かれ、動画の外のフレームでは「Out of range」と表示する(比較中の表示枠の下の文字も「out of range」)。
- **範囲の欄の入力**: Mayaと同じく、矛盾する側を押して合わせる。再生範囲を全体範囲の外にすると全体範囲が広がり、
  全体範囲を再生範囲より狭くすると再生範囲も縮む。I/Oキーや連携先から受け取った再生範囲も同じ。
- **動画の開始**: 既定は1(動画の1コマ目を1に置く)。番号を入力すると、タイムライン(範囲と現在のフレームの番号)は
  そのままで、動画だけが動く(例: 1001にすると、動画の1コマ目が1001に来る)。
  `HKEY_CURRENT_USER\Software\FramePlayer` の `StartFrame` に保存し、次回も使う。
- **再生範囲**: 再生は範囲の中でループし、先読みも範囲のうち動画のある部分で回り込む。範囲の外や最後のコマで
  再生を始めると、範囲の最初から再生する。動画の外のフレームも、動画のフレームレートで時間どおりに進む
  (再生範囲が動画の外にかかるときは音声を鳴らさない)。動画を開くと、全体範囲と再生範囲は動画のある所になる。
- 数字の欄はEnterで確定、Escで取り消す。他の所を押しても確定する。

色合いはWindows 11標準の「メディア プレーヤー」に合わせている(地とタイトルバーは#141414、バーは#949494、
キャッシュの帯・音量・比較中のボタンはオレンジ#FF8232)。タイトルバーもダークにしている。
再生中にスライダーを操作した場合は、ドラッグ中はそのコマを表示し、離すとその位置から再生を続ける(YouTubeと同じ)。
コマ送りのキーは再生中に押すと停止してから移動する。

再生はファイルに記録されたフレームレート(不明なら24fps)で、再生範囲の最後まで進むと範囲の最初に戻って繰り返す。
再生はリアルタイム優先で、先読みが間に合わないときは今のコマを表示したまま待ち、届いた時点で時刻どおりの
コマへ進む(飛ばしたコマは表示しない)。

キャッシュに無いコマへ移動すると、直前の画像(またはキーフレームの縮小画像)の上に「Loading…」と出し、
届いたら表示する。

- 再生中は速さを優先して画像を簡易的に拡大縮小し、止めると高画質で描き直す。
- 再生のタイミングは高精度タイマーで各コマの開始時刻に合わせている。確認した環境では24fps・29.97fpsはコマ落ち0、
  60fpsは8秒(約480f)でコマ落ち2fだった。

### 2本の比較

- 2本目の動画は次のどれかで開き、右に並べて表示する。
  - 1本目を開いた状態で、映像の右半分へドラッグ&ドロップする(左半分なら1本目の差し替え)
  - 2つのファイルをまとめてドロップする(1つ目が左、2つ目が右)
  - 操作部の「Compare」ボタン、または Ctrl+Shift+O でファイル選択画面から選ぶ
  - 起動時の引数に2つ指定する(`FramePlayer.exe 左.mp4 右.mp4`)
- 2本は同じコマ番号で表示する(フレームレートが違っても番号で合わせる)。[ ] か右の映像の上の中ボタンドラッグで右のオフセットを変えられ、
  左の映像の上の中ボタンドラッグでは左だけを動かせる(右の表示はそのまま)。オフセットを足した結果が右の動画の範囲外なら「Out of range」と表示する。各表示枠の下にファイル名とコマ番号を出す。
- スライダー・再生・コマ送りは左の動画で操作し、右はそれに従う。再生中は左右両方のコマがそろってから進める
  (片方だけ進んでずれて見えないようにするため)。
- 比較中は音声を鳴らさない。キャッシュの上限は2本で半分ずつにする。
- 「Compare ×」ボタン(比較中の「Compare」ボタン)で比較をやめる。

### 音声

- 通常の再生中だけ音声を鳴らし、映像の進みを音声の再生位置に合わせる(測定では差は±0.03ms以内)。
  コマ送り・スライダー操作では鳴らさない。2本比較中は鳴らさない。逆再生・速度変更(段階B)では消音にする予定。
- 操作部の右側のスピーカーのボタンで消音を切り替え、その右の三角形の音量スライダーで音量を変える。
- 音量と消音は `HKEY_CURRENT_USER\Software\FramePlayer` に保存し、次回の起動でも使う。
- 音声の無い動画では、音量の操作部を薄く表示する(操作した設定は次の動画で使われる)。
- デコードはMedia Foundation、出力はWASAPI(どちらもWindows標準)。音声の出力装置が無い環境では音声なしとして再生する。

動画はウィンドウへのドラッグ&ドロップ、操作部の左端の「ファイル」ボタンのメニュー、または起動時の引数
(`FramePlayer.exe <動画>`)で開く。

「File」ボタンのメニュー:

| 項目 | 内容 |
| --- | --- |
| Open... (Ctrl+O) | ファイル選択画面で動画(または連番の1枚)を選んで開く |
| Open for Comparison... (Ctrl+Shift+O) | 2本目の動画を選び、右に並べて比較する |
| Close Comparison | 比較をやめて1本だけ表示する |
| Recent Files | 最近開いた動画(最大8つ)。選ぶと1本目として開く。「Clear List」で消せる |
| Play Automatically on Open | 動画を開いたら(起動時の引数・ドロップ・メニュー・比較も)そのまま再生する。既定はオン。押すと切り替える |
| Exit | アプリを閉じる |

最近使ったファイルの一覧は `HKEY_CURRENT_USER\Software\FramePlayer` の `RecentFiles` に、自動再生は `AutoPlay`(1/0)に保存する。
Mayaとの連携モードのときは自動再生しない(タイムラインはMaya側が動かすため)。
コマ番号の表示は1始まり(Mayaのタイムラインに合わせる)。

## 性能の目安

測定環境: Core i7-12700KF、GeForce RTX 3090 Ti。H.264(4K 60fps、80Mbps)。

| 項目 | 結果 |
| --- | --- |
| 開く(1時間・21万6千コマ・36GB) | 約1秒(画面に表示されるまで) |
| デコード(順方向) | 約200コマ/秒(60fps再生の約3倍) |
| デコード(逆方向) | 約170コマ/秒 |
| キャッシュに無い位置への移動 | 約0.3秒(キーフレーム間隔2秒の動画。キーフレームから読み直すため)。待つ間は縮小画像を仮表示 |
| 再生中のCPU | 全体の約0.4%(4K 60fps。描画は表示が変わるときだけ) |

操作部(GDI)の描き直しは、変わった段だけにしている(コマが進む・移るときは上段だけ)。目盛りの線と数字は、
通常の地と現在のフレームの区画の地の2枚を作り置きして写すだけにし、タイトルバーの書き換えは再生中・ドラッグ中は
1秒に4回までにしている。60fps再生中の操作部の描画は1回あたり中央値0.3ms(最初は1.3ms)、ドラッグ中は0.34ms(1.1ms)。

動画を開くときは、目次の作成とデコーダーの準備を並行して行い、試しに読んだ先頭のコマをそのまま使う。
4K60fps・600コマで0.24秒→0.15秒、720p60fps・18000コマで0.11秒→0.10秒(確認用ツールでの測定)。

再生中のコマ落ちは、PCの他の処理の影響を受ける。他の処理が重いときは、Keyframe Proでも同程度に落ちることを確認した。

表示は画面の書き換えに合わせるので、画面の書き換え回数より多いコマは表示できない。
画面の合成が遅い環境(リモート接続中や仮想ディスプレイで、1秒に数回しか合成されない場合)でも、表示を待つ間に
CPUを使い続けないようにしている(画面の書き換えを待つ表示命令は、この環境で1回約250msもCPUを使い続けたため使わない)。
リモートデスクトップ接続中は画面が約30Hz(測定時32Hz)になるため、60fpsの動画は約半分のコマが表示されない
(24fpsはリモートデスクトップでもコマ落ち0を確認)。正確な確認はPCに直接つないだ画面で行う。
画面が消えている(省電力・ロック中)と画面の書き換えが止まり、再生の表示も進まない。

## 軽さ(MayaやUnreal Engineとの同時使用)

MayaやUnreal Engineを同時に動かしても邪魔にならないよう、GPUのメモリ・CPU・デコーダーの使用を抑えている。

### キャッシュの上限

キャッシュする画像は幅1280ピクセルに縮小する(`PlayerWindow.cpp` の `kCacheMaxWidth`)。開くと裏で上限まで先読みする。
上限は次のうち最も小さいもの(2本比較中は2本で半分ずつ)。2秒ごとに見直す。

| 上限 | 既定値 | 説明 |
| --- | --- | --- |
| 容量 | 1024MB | 設定 `CacheMB` で変えられる(64〜65536) |
| 長さ | 30秒分 | 設定 `CacheSeconds` で変えられる(秒) |
| GPUのメモリの予算の1/4 | - | ほかのアプリがGPUのメモリを使うほど、Windowsが示す予算が減り、キャッシュも自動で減る |
| 主メモリ不足 | 256MB | Windowsが主メモリの不足を知らせている間 |

設定は `HKEY_CURRENT_USER\Software\FramePlayer` にDWORDで書く(画面からの設定は未対応。次に起動したときから効く)。
1280×720の1コマは、GPUのメモリで約1.4MB、主メモリ(GPUに置けない場合)で約3.7MB。

### 状態ごとの動き

| 状態 | 先読み | 縮小画像の作成 | 裏のスレッドの優先度 |
| --- | --- | --- | --- |
| 再生中 | 再生の先を上限まで | 止める | 通常 |
| 停止中で前面 | 上限まで | 作る | 通常 |
| 停止中で最小化・他のアプリが前面 | 再生位置の前後2秒だけ | 止める | 低い(省電力。12世代以降のIntelでは主にEコア) |
| 休止(最小化して30秒、背面で5分) | 表示中の1コマだけ。デコーダーも閉じる | 止める | 低い |

休止中はキャッシュとデコーダーのGPUのメモリを返し、使っていない主メモリもWindowsへ返す。前面に戻すと読み直す。

### キーフレームの縮小画像(仮表示)

キャッシュに無い位置へ移ったとき、デコードを待つ間(キーフレームの間隔が長い4Kの動画で約0.3〜0.8秒)に、
近いキーフレームの縮小画像(幅320、1画素2バイト)を仮に表示する。直前の画像の方が近ければ(1コマ送りなど)そちらを残す。
縮小画像は専用のデコーダーで裏で作り、1本あたり160MBを超えないよう間隔を空けて選ぶ(間隔は1秒以上)。
粗い間隔から順に作るので、開いてすぐは少し離れたキーフレームの画像になることがある。
全コマがキャッシュに入る短い動画では作らない。

### 測定結果

測定環境: Core i7-12700KF、GeForce RTX 3090 Ti(24GB)、主メモリ64GB。

| 項目 | 以前 | 現在 |
| --- | --- | --- |
| GPUのメモリ(720p 60fps・5分) | 約8.6GB | 約0.9〜1.1GB |
| 主メモリ(同、コミット) | 約8.9GB | 約1.0〜1.3GB |
| 再生中のCPU(画面の合成が遅い環境) | 1コア分(全体の5%) | 全体の約0.4% |
| 休止中(最小化して35秒後) | - | GPUのメモリ約145MB、主メモリ約280MB |
| 縮小画像(720p 24fps・5分、152枚) | - | 16.7MB、作成約4秒 |

GPUのメモリにキャッシュしたコマは、主メモリの予約(コミット)にも同じだけ数えられる(Windowsの仕組み)。

## ビルド

Visual Studio 2022(C++によるデスクトップ開発)と、それに付属するCMakeを使う。映像のシェーダー(HLSL)は、
Windows SDKに入っている `fxc.exe` でビルド時にバイトコードへ変換して埋め込む(実行時のコンパイルはしない)。

```bat
cd maya\inhouse\FramePlayer
cmake -S . -B build -G "Visual Studio 17 2022" -A x64
cmake --build build --config Release
```

成果物は `build\Release\FramePlayer.exe`。`build/` はGit対象外。

### 配布用exeの更新

配布するexeはパッケージ直下の `FramePlayer.exe`(Git管理対象)。ビルド後に次を実行したときだけ更新される
(試しのビルドで管理対象のexeが変わらないようにするため)。

```bat
cmake --install build --config Release
```

ランタイムを静的リンクしているので、依存するのはWindows標準のDLLだけで、exe単体で配布できる。

### アイコン

アイコンの元は `resources/icon/` のSVG(図形とパスだけで描く)。サイズごとに画素の升目に合わせて描き分けている。

| ファイル | 使うサイズ | 座標 |
| --- | --- | --- |
| `FramePlayer.svg` | 32px以上 | 256×256。32pxで1画素=8単位なので、形の端を8の倍数に揃える |
| `FramePlayer-24.svg` | 24px | 24×24(1単位=1画素)。目盛りは省く |
| `FramePlayer-16.svg` | 16px・20px | 16×16(1単位=16pxの1画素)。目盛りは省く |

SVGを直したら、`tools/WinAppKit`(このワークスペースの汎用の道具)の IconBuilder で `.ico` を作り直し、
FramePlayerをビルドし直す(`.ico` はexeに埋め込まれる。`src/app/FramePlayer.rc`)。

```bat
cd resources\icon
..\..\..\..\..\tools\WinAppKit\build\Release\IconBuilder.exe --svg FramePlayer.svg --svg-for 16,20=FramePlayer-16.svg --svg-for 24=FramePlayer-24.svg --ico FramePlayer.ico
```

`FramePlayer.ico` はGit管理対象(このパッケージだけでビルドできるように。IconBuilderが無くてもよい)。

### インストーラー

`tools/WinAppKit` の汎用インストーラー(WinAppSetup)で、FramePlayerのセットアップ(`FramePlayerSetup.exe`)を作れる。
設定は `installer/FramePlayer.wak.ini`。バージョンは `src/app/FramePlayer.rc` の `FP_VERSION_*` から読む
(上げるときは .rc を変えてビルドし、`cmake --install` してからセットアップを作る)。

```bat
cmake --build build --config Release
cmake --install build --config Release
..\..\..\tools\WinAppKit\build\Release\WinAppSetup.exe --build installer\FramePlayer.wak.ini --out FramePlayerSetup.exe
```

セットアップはパッケージ直下の `FramePlayerSetup.exe`(`FramePlayer.exe` と同じくGit管理対象)。配るときはこのexeを渡す。
`FramePlayer.exe` を更新したら、セットアップも作り直す(中に `FramePlayer.exe` を含むため)。

- インストール先は `%LOCALAPPDATA%\Programs\FramePlayer`(このユーザーだけ。管理者権限は不要)。
- 設定の「アプリ」一覧に載り、そこからアンインストールできる。スタートメニューにも追加する。
- 関連付け: インストールの画面の「Change file associations」で、関連付ける拡張子と、右クリックに「Open with FramePlayer」を
  出すかを選べる(既定はすべて)。選んだ拡張子は右クリックの「プログラムから開く」の候補に FramePlayer を追加する。
  更新のときは前回の選択を引き継ぐ。候補は、動画(.mp4 .mov .m4v .avi .wmv .mkv .webm .mts .m2ts .ts .mpg .mpeg .vob .3gp)と
  連番画像(.png .jpg .jpeg .tif .tiff .bmp .gif .webp .heic .heif .hif .avif .jxl .jxr .wdp .exr)。
- 拡張機能が要る形式は、そのPCに入っているときだけ関連付ける(入っていない形式は画面で灰色になり選べず、画面なしの
  インストールでも関連付けない)。入れた後にセットアップを入れ直すと選べる。判定はインストールのときに行う
  (`installer/FramePlayer.wak.ini` の `Require.<拡張子>`)。

  | 拡張子 | 要る拡張機能(判定の方法) |
  | --- | --- |
  | .webm | VP9 Video Extensions または AV1 Video Extension(その形式の動画デコーダーがあるか) |
  | .webp | Webp Image Extensions(その拡張子を読める画像コーデックがあるか) |
  | .heic .heif .hif | HEIF Image Extensions と HEVC Video Extensions(画像コーデックと、HEVCの動画デコーダー) |
  | .avif | AV1 Video Extension(と HEIF Image Extensions。画像コーデックと、AV1の動画デコーダー) |
  | .jxl | JPEG XL Image Extension(画像コーデック) |

  関連付けの前に確かめるだけなら `FramePlayerSetup.exe --check-file-types` で、拡張子ごとの判定(OK・NGと足りないもの)を
  標準出力に書く。
- 既定のアプリ: Windowsの決まりで、アプリが勝手に既定にはできない。動画を右クリックして「プログラムから開く」→
  「別のプログラムを選択」で FramePlayer を選び、「常に使う」を押すと既定になる(拡張子ごと。インストールの完了画面でも案内する)。
- アンインストールで「Also delete settings and other data」を選ぶと、音量・最近使ったファイル(`HKCU\Software\FramePlayer`)と
  連携の鍵(`%LOCALAPPDATA%\FramePlayer`)も消す。選ばなければ残る。
- 画面なしで入れる・消すとき: `FramePlayerSetup.exe /S`、`"%LOCALAPPDATA%\Programs\FramePlayer\Uninstall.exe" --uninstall /S`。
  画面なしのときの関連付けは `--extensions .mp4;.mov`(拡張子を選ぶ)・`--no-file-types`(しない)・`--no-context-menu`
  (右クリックに出さない)で指定する。

仕組み(記録とアンインストール、安全のための決まり、確かめたこと)は `tools/WinAppKit/README.md` を参照。

## 連番画像

1枚の画像(連番の中のどれでもよい)をドラッグ&ドロップするか、開く画面で選ぶと、同じフォルダから同じ名前の並び
(番号の部分だけが違うファイル。例: `shot.1001.exr`〜`shot.1048.exr`)を探し、動画と同じようにコマ送り・再生・比較できる。

- 番号は、拡張子の直前にある最後の数字の並び(9桁まで)。桁の揃え(`0001`)の有無は問わない。番号の無い画像は1枚だけの連番になる。
  大文字・小文字の違いは同じ名前として扱う。
- タイムスライダーの開始は、最初のファイルの番号になる(連番を開いている間だけ。動画の開始の設定は変えない)。
- 番号の抜け(欠け)は詰めずにそのコマを空ける。欠けたコマでは直前の画像を出し、「Missing frame (no image for this frame in the sequence)」と表示する。
- フレームレートは画像に書かれていないので、既定は60fps。操作部のフレームレートの欄(連番を開いているとき)をクリックして
  変えられる(1〜1000。次の連番にも使う)。
- 音声は無い。
- 画像は裏の作業スレッドで先のコマまで並行してデコードする(CPUのコア数の半分まで。最大8枚)。シークの直後は表示するコマを
  先に仕上げ、順に読み進むと先読みを増やす。EXRは1枚の中のチャンクも並行して戻す。

| 形式 | 読み方 | 必要なもの |
| --- | --- | --- |
| PNG・JPEG・TIFF・BMP・GIF・JPEG XR(jxr・wdp) | WindowsのWIC | Windows標準 |
| WebP | WIC | Webp Image Extensions(多くのPCに最初から入っている) |
| HEIF(heic・heif・hif) | WIC | HEIF Image Extensions と HEVC Video Extensions |
| AVIF | WIC | AV1 Video Extension(と HEIF Image Extensions) |
| JPEG XL | WIC | JPEG XL Image Extension |
| OpenEXR | 自前(OpenEXRのファイル形式の仕様から書いた。外部のライブラリは使わない) | なし |

- 8bitの画像は8bitのまま、16bitのPNG・TIFFは16bitのまま、浮動小数点の画像(EXR・浮動小数点のJPEG XR)は半精度のまま持ち、
  描画のときに色を変換する。EXRと浮動小数点のWICの画像はリニア(1.0がSDRの白)、それ以外はsRGBとして扱う。
  1を超える値・負の値は、HDRの画面ではそのまま、SDRの画面では切って表示する。
- EXRの対応:
  - 走査線とタイル(最も細かい段だけ)、複数の部分(multipart。最初の部分だけ)、画素の型 half・float・uint。
  - 圧縮: NONE・RLE・ZIPS・ZIP・PIZ・PXR24・B44・B44A・DWAA・DWAB(zlibの展開も自前)。
  - チャンネル: R・G・B・A。無ければ「層の名前.R」(最初の層)、それも無ければY(灰色)、それも無ければ最初のチャンネル。
  - 色域(`chromaticities`): BT.709・BT.2020・Display P3・DCI-P3・ACES(AP0)・ACEScg(AP1)を見分け、BT.709へ変換して表示する
    (白の違うACESはBradford法で白を合わせる)。書かれていなければBT.709。画素の縦横比(`pixelAspectRatio`)も使う。
  - データの範囲(dataWindow)は表示の範囲(displayWindow)の中の位置に置く(外は黒)。
  - 未対応: 深いデータ(deep)、縦横に間引いたチャンネル(色差を間引いたYC)、2つ目以降の部分・層の切り替え。
- 4K(3840×2160、半精度RGB)のEXRの読み込みの目安(20スレッドのCPU): 1枚あたり NONE 64ms・ZIP 57ms・PIZ 65ms・DWAA 69ms。
  順の再生は ZIP で約28fps・DWAA で約22fps(キャッシュに入ったコマは即座に出る)。

### 確かめ方(連番画像)

```bat
rem 確認用の連番(コマ番号の縦縞、形式・圧縮ごと)と色のパッチの画像を作る
python tests\make_sequence_testdata.py --ffmpeg ffmpeg.exe --oiiotool oiiotool.exe ^
    --convert build\Release\FramePlayerImageConvert.exe --out build\testdata\sequences
rem コマ番号(順・逆・ランダム、欠けの番号)。--cpu でGPUを使わずに
python tests\run_sequence_check.py --verify build\Release\FramePlayerVerify.exe --data build\testdata\sequences
rem 色(SDRとHDRの画面)
build\Release\FramePlayerColorCheck.exe build\testdata\sequences\color
rem EXRの読み込みを、oiiotool(OpenImageIO)の読み込みと画素単位で比べる(圧縮・画素の型・タイルごと)
python tests\run_exr_check.py --oiiotool oiiotool.exe --convert build\Release\FramePlayerImageConvert.exe ^
    --out build\testdata\exr_check
```

`FramePlayerImageConvert`(配布対象外)は、ffmpegやoiiotoolで作れないHEIF・JPEG XL・JPEG XRの確認用画像をWindowsのWICで
書くほか、EXRをFramePlayerの読み込みで読んで圧縮なしのEXRに書き直す(oiiotoolで元と比べるため)・読み込みの速さを測る
(`FramePlayerImageConvert <file.exr> --time`)。

確かめたこと(2026-10-06): 28種類の連番(上の全形式、EXRは圧縮10種・float・タイル、欠けのある連番)でコマ番号がGPU・CPUとも
一致。色のパッチ14枚(ACEScgのEXRを含む)がSDR・HDRの画面とも期待どおり。EXRは40通り(圧縮10種×half/float×走査線/タイル)で、
DWA以外はoiiotoolの読み込みと全画素が一致した。DWAA・DWABは逆DCTを浮動小数点で計算するので、計算の順序の違いで
約0.1%の画素が、圧縮した非線形の値で半精度の1段ずれる(元の画像との差に比べてずっと小さい)。

## 色の扱い

目標は「OpenRVと同じ正確さで色の情報を読み、味付けをせずニュートラルに出す」こと。
ニュートラルとは、**エンコードする前の画像と同じ値が画面に出る**こと(Mayaのプレイブラストなら、Mayaのビューポートと同じ色)。
式は規格(ITU-R BT.601/709/2020/2100・BT.2390・BT.2408、ITU-T H.273、IEC 61966-2-1、SMPTE RP 177)から書いた。
OpenRVなど他のソフトのコードは使っていない(調べるときの参考にしただけ)。

### 読み取る色の情報

| 項目 | 内容 |
| --- | --- |
| YUVの行列 | BT.601・BT.709・BT.2020・SMPTE 240M・FCC |
| 範囲 | 映像用(8bitなら16〜235)・全範囲(0〜255) |
| 色域 | BT.709(sRGB)・BT.601の525本/625本・BT.2020・Display P3・DCI-P3 |
| 伝達関数 | SDR(BT.709・sRGB・ガンマなど)・リニア・HDRのPQ・HLG |
| その他 | ビット数(8・10)、色の画素の位置(H.264・HEVCは左寄せ、JPEGは中央)、HDRの最大の明るさ(MaxCLL・マスタリング) |

情報の出所は、後のものほど優先する。

1. 推定(動画に指定が無いとき): HD以上(幅1024超か高さ576超)はBT.709、それ未満はBT.601(高さ576は625本、他は525本)。
   範囲は映像用、伝達関数はSDR。一般的なプレイヤーと同じ決まり。
2. デコーダーが動画の中(H.264・HEVCのVUI)から読んだ値(行列・色域・伝達関数のどれかが分かったときだけ)。
3. 動画の形式の情報(Media Foundationが報告する値)。
4. mp4/movの `colr` ボックス(自前で読む。Display P3はここでしか分からない)。無ければVP9の `vpcC` ボックス。

### 表示の仕方

- **SDRでBT.709の8bitの動画**: YUVからRGBへ戻した値を、そのまま8bitで画面へ出す(ちょうど8bitの値は1段も変わらない)。
  WindowsのHDRが有効な画面でも、他のSDRのアプリと同じくWindowsが画面に合わせる。
- **色域が違うSDRの動画**(BT.2020・P3・SDのBT.601): 画面(sRGBの曲線)でリニアにし、BT.709の同じ色へ変換する。
  描画先を16bit浮動小数点(scRGB)にして出すので、BT.709の外の色はWindows(広い色域の画面と自動の色管理が
  有効なら、その色域まで)が扱う。
- **10bitの動画**: 10bitのまま変換し、16bit浮動小数点(scRGB)で画面へ出す(8bitに落とさない)。
- **HDRの動画をHDRの画面で**: 明るさ(cd/m²)をそのまま出す(scRGBで1.0 = 80cd/m²)。画面の最大を超える分は画面が収める。
- **HDRの動画をSDRの画面で**: BT.2390の曲線(EETF)で、動画の最大の明るさ(不明なら1000cd/m²)を基準の白(203cd/m²、
  BT.2408)までに収め、基準の白をSDRの白にする。暗い所から約100cd/m²までは比例のまま変えない。HLGは公称の明るさ
  1000cd/m²(γ=1.2)の表示の明るさにしてから同じように扱う。
- 拡大は双三次補間(等倍なら元の値のまま)、縮小はミップマップを使う。範囲外(映像用の範囲の外側)の値は切る。
- 縦横を縮めてキャッシュする場合(幅1280を超える動画)も、自前のシェーダーでYUVのまま縮める(色の画素の位置を保つ)。
- Windowsの映像処理(Video Processor)とGPUのドライバーの映像の補正(コントラストの強調など)は通さない。
  例外はデコーダーがNV12を出せない形式(MJPEGのYUY2など)で、そのときだけWindowsがYUVのまま並べ替える。

### 手動の指定と情報の表示

映像の上の右クリックのメニューで指定する。

- **Show Color Info(色の情報を表示)**: 映像の左上に、使っている色の解釈と出し方を出す。推定した項目には「(guessed)」、
  手動で指定した項目には「(manual)」と付く。設定は保存される。
- **Color Interpretation(色の解釈)**: YUVの行列・範囲・色域・伝達関数を、それぞれ「Auto」(動画の指定・推定)か手動の値に変える。
  動画の色の情報が誤っている(付いていない)ときに直す。比較中は1本目と2本目を別々に指定できる。
  手動の指定は開いている間だけ有効(動画を開き直すと自動に戻る)。

### 制限

- ICCプロファイル(`colr` の `prof`)とOCIO・LUTは使わない。広い色域の画面は、Windowsの自動の色管理に任せる。
- BT.2020の定輝度は非定輝度として、YCgCoはBT.709として扱う(実際の動画はほぼ無い)。
- 主メモリへ写す方式・CPUの方式(GPUのメモリに置けないとき)のコマは縮めずに持つ。
- キーフレームの縮小画像(仮表示)は1画素16bit(RGB565)で持つので、色は近い値になる(正式なコマが届けば置き換わる)。

### 確かめ方

`tests/make_color_testdata.py` で、色の付いた四角(パッチ)を並べた確認用動画と期待値を作り、
`build\Release\FramePlayerColorCheck.exe` で確かめる。プレイヤーと同じ読み込みと変換で最初のコマを等倍で描き、
パッチの中央の値を期待値と比べる。表示は「SDRの画面」と「HDRの画面(SDRの白200cd/m²)」の2通りを、画面を使わずに確かめる。
期待値の式は規格からプレイヤーのコードとは別に(Pythonで)書いた。ffmpegは確認用動画を作るためだけに使う。

```bat
python tests\make_color_testdata.py --ffmpeg C:\path\to\ffmpeg.exe --out build\testdata\color
build\Release\FramePlayerColorCheck.exe build\testdata\color
build\Release\FramePlayerColorCheck.exe build\testdata\color --cpu
build\Release\FramePlayerColorCheck.exe build\testdata\color --max-width 640
```

確認用動画: H.264の8bit(BT.709の映像用・全範囲、mov、BT.601と指定したHD、色の情報なしのHD・SD)、
HEVCの10bit(BT.709、BT.2020のSDR、HDRのPQ・HLG)、VP9(8bitのBT.709、色の情報が `vpcC` にだけあるBT.601、
10bitのHDRのPQ)。各動画で、読み取った色の解釈が期待どおりかも確かめる。
許す差は、SDRの値で8bitの2.5段、HDRの明るさでPQの10bitの4段(圧縮・4:2:0・丸めの分)。

確認結果(GPU・CPU・縮小(幅640)のどれも、13本すべて一致): SDRの値の差は最大2.05段(8bit)、
HDRの明るさの差は最大3.54段(PQの10bit)。色の解釈は13本とも期待どおり。

## 全コーデックの確認

`tests/make_codec_testdata.py` で、Windowsのデコーダーごと・入れ物ごとの確認用動画(コマ番号の縞の動画と、
色のパッチの動画)を作り、`tests/run_codec_check.py` で `FramePlayerVerify.exe`(コマ番号。GPUとCPU、キャッシュを
小さくしてシークも)と `FramePlayerColorCheck.exe`(色。GPUとCPU)をまとめて実行する。1本ごとに時間の上限があり、
止まった場合も失敗として数える。

```bat
python tests\make_codec_testdata.py --ffmpeg C:\path\to\ffmpeg.exe --out build\testdata\codecs
python tests\run_codec_check.py --data build\testdata\codecs --bin build\Release
```

## コマ送りの正確さの確認

`build\Release\FramePlayerVerify.exe` は、プレイヤーと同じ読み込み処理(目次・キャッシュ・先読み)で、
先頭から順・末尾から逆順・ランダムな位置の3通りに全コマを取り出し、各コマに描かれたコマ番号と一致するかを
確かめる(終了コード 0=一致、1=不一致、2=読み込み失敗)。`--cache-mb` でキャッシュを小さくすると、
捨てたコマの読み直しとシークも確かめられる。4096コマ以上の動画は縦縞を13本以上(8192コマまで)で作り、`--bits 13` のように本数を指定して確かめる。

確認用動画は、各コマの中央にコマ番号の2進数を縦縞(左が最下位ビット、白=1)で描いたもの。
上端は白、下端は黒の帯で、上下反転も検出する。手元のffmpegで次のように作れる
(ffmpegは確認用動画を作るためだけに使い、プレイヤーには含めない)。

```bash
ffmpeg -f lavfi -i "nullsrc=s=1920x1080:r=24" -frames:v 300 \
  -vf "geq=lum='if(lt(Y,H/8),235,if(gt(Y,7*H/8),16,if(mod(floor(N/pow(2,floor(X*12/W))),2),235,16)))':cb=128:cr=128,format=yuv420p" \
  -c:v libx264 -bf 3 -g 48 -crf 18 test_1080p.mp4
FramePlayerVerify.exe test_1080p.mp4 300
```

`--max-width` でキャッシュする画像の最大幅を変えられる(0なら縮小しない)。`--cpu` でGPUを使わずに確かめられる。
`--thumbnails` を付けると、キーフレームの縮小画像を作らせ、各画像に描かれた番号がそのキーフレームの番号と一致するかも
確かめる(全コマがキャッシュに入ると作らないので、`--cache-mb` を小さくして使う)。
GPUのメモリにキャッシュしたコマは、主メモリへ読み出してから縞を読む。`--limit N` で長い動画の一部だけを確かめられる。
連番画像では `--missing 1010,1011` で、欠けとして扱われるはずのファイルの番号を指定する(一致しなければ失敗。欠けのコマは
縞の確認から外す)。

## Mayaとの連携

Keyframe Proと同じように、Mayaのタイムスライダーと双方向に連携できる。

- Mayaで時間を動かす(スクラブ・再生・キー操作)と、FramePlayerが同じフレームを表示する。
- FramePlayerでコマ送り・スライダー操作・再生をすると、Mayaの時間が追従する(再生中は最新のフレームだけを反映し、
  重いシーンでも遅れが積み重ならない)。
- 再生範囲も合わせられる(Mayaの再生範囲 ↔ FramePlayerの再生範囲)。
- 番号の対応は「FramePlayerの番号 = Mayaの番号 × 倍率 + オフセット」(Keyframe Proと同じ考え方)。

### 連携モード

FramePlayerは、通常はポートを開かない(ネットワークの待ち受けをしない、シンプルな動画プレイヤー)。
Mayaと連携するときだけ、下段の「Maya Sync」ボタンを押して連携モードにする。

| ボタンの表示 | 状態 |
| --- | --- |
| Maya Sync | 通常モード。ポートを開かない |
| Waiting(強調色) | 連携モード。このPCの中からの接続を待っている |
| Synced(強調色) | 連携モード。Mayaとつながっている(タイトルにも「Synced」と出る) |

もう一度押すと、接続を切ってポートを閉じ、通常モードに戻る。連携モードは記憶せず、毎回の起動は通常モードから始まる
(起動時の引数に `--sync` を付けると連携モードで始まる。Mayaの画面から起動したときはこれを使う)。

### 使い方

1. Mayaで HTools > animation > framePlayerSync を選ぶ(または `import frameplayer; frameplayer.show()`)。
   FramePlayerだけを入れた人は、`maya/FramePlayerMayaSync.py` をMayaのビューへドラッグ&ドロップする(下記)。
2. 「Launch FramePlayer」で、連携モードで起動して自動で接続する。起動済みなら、FramePlayerの「Maya Sync」を
   押してから「Connect」。
3. オフセット・倍率・連携の向き・再生範囲を合わせるかを設定する(Mayaの設定に保存され、次回も使う)。
   「Play in FramePlayer」「Stop」でFramePlayerの再生を操作できる。

スクリプトからは次のように使える。

```python
import frameplayer
frameplayer.launch(r"D:\shots\sh010.mp4")   # 連携モードで起動(2つ渡すと比較。sync=Falseで通常モード)
sync = frameplayer.connect(offset=0, multiplier=1.0, sync_range=True)
if sync is None:
    print(frameplayer.last_error())          # 接続できなかった理由
sync.play()
frameplayer.disconnect()
```

### 仕組み

- 連携モードのFramePlayerは、このPCの中(127.0.0.1)からだけ接続できる待ち受け口を開く(既定は7010番。
  `HKEY_CURRENT_USER\Software\FramePlayer` の `SyncPort` で変更できる)。同じ番号を他のアプリ(別のFramePlayerなど)が
  使っているときは、連携モードにできない旨を表示する。
- Maya側のパッケージ(`python/frameplayer`)がそこへ接続し、互いを確かめてから(下記「安全のための仕組み」)、
  1行1命令の文字をやり取りする。
  - 両方向: `frame <番号>`、`range <最初> <最後>`
  - Maya → FramePlayer: `play`、`stop`、`hello maya`
  - FramePlayer → Maya: `state playing|stopped`、`hello FramePlayer 2`(接続直後は挨拶と再生状態だけを送る)
- 相手から受け取った変化を反映している間は、その変化を送り返さない(両側とも)。行ったり来たりを防ぐため。
- 接続した直後はMaya側の状態(フレーム・再生範囲)をFramePlayerへ合わせる。
- FramePlayer側の窓口は `TimeSync`(`src/app/TimeSync.h`)と、それを使う待ち受け口 `SyncServer`。
  外から動かす関数は `PlayerWindow::goToSceneFrame()`・`setPlaybackRangeScene()`・`setPlaying()`。

### 安全のための仕組み

連携の口から操作できるのは、フレーム・再生範囲・再生/停止だけ(ファイルを開く・プログラムを動かすといった命令は無い)。
そのうえで、次のようにしている。

- **通常はポートを開かない**: 連携モードのときだけ開く。開くのはこのPCの中(127.0.0.1)だけで、他のPCからは接続できない。
  他のプログラムが同じ番号に割り込めないよう、番号を独占して開く。
- **相互認証**: ユーザーごとの秘密鍵 `%LOCALAPPDATA%\FramePlayer\sync.key`(連携モードにしたとき作る)を使い、接続のたびに
  乱数のチャレンジとHMAC-SHA256で、互いが同じ鍵を持つ相手かを確かめる。鍵そのものは通信に流さない。
  - FramePlayer → Maya: `challenge <乱数>` / Maya → FramePlayer: `auth <HMAC(鍵, "maya-to-player:" + 乱数)> <Mayaの乱数>` /
    FramePlayer → Maya: `auth <HMAC(鍵, "player-to-maya:" + Mayaの乱数)>`
  - 正しい応答が無ければ、命令を1つも受け付けずに切る(5秒以内に応答が無い場合も切る)。
  - Maya側も、FramePlayerの応答を確かめる。同じ番号を開いている別のプログラム(偽物)には接続しない。
- **鍵ファイルの権限**: 本人とSYSTEMだけが読み書きできるようにする(親フォルダの権限は引き継がない)。
  同じPCの他のユーザー、サンドボックス化されたアプリ、ブラウザのページからは読めない。
- **乗っ取り防止**: 認証が済んでいない接続は、認証済みの接続を切らない。
- **入力の検査**: 決まった命令と、決まった数の整数(±1億まで)だけを受け付ける。1行の長さと受け取る量に上限があり、
  超えた相手は切る(両側とも)。

確認したこと(`--sync` で起動したFramePlayerに対して): 認証しない接続・間違った応答・HTTPのリクエスト(ブラウザからの
送信を想定)・居座り・範囲外の値・長すぎる行はいずれも拒否され、命令は実行されない。認証しない接続で正規の接続は切れない。
Maya側は偽物のFramePlayer(応答を間違える・チャレンジを送らない)と鍵が無い場合に接続しない。通常モードではポートが
開かず、鍵ファイルも作られない。

### 確認したこと

Maya 2026でcommandPort経由で操作し、FramePlayerの表示と照らし合わせて確認した: Mayaの時間・再生範囲の変更の反映、
FramePlayerのコマ送り・Iキー(範囲の最初)のMayaへの反映、FramePlayerの再生へのMayaの追従、Mayaの再生への
FramePlayerの追従(どちらも範囲内のループを含めて同じフレーム)、オフセット、切断。

### 同期の遅れ(実測)

両側で時刻を記録して突き合わせた(Windowsの高精度タイマーはプロセスをまたいで共通なので、そのまま比べられる)。
測定環境: Core i7-12700KF、RTX 3090 Ti、Maya 2026、720pの動画。重いシーンは約173万面の球30個を毎フレーム曲げで変形させたもの。
「表示」はFramePlayerが画面へ渡した時点、「反映」はMayaの `currentTime` が終わった時点(画面に出るのはそれぞれ次の画面の書き換え)。

| 項目 | 空のシーン・24fps | 重いシーン・24fps | 重いシーン・60fps |
| --- | --- | --- | --- |
| Mayaでコマ送り → FramePlayerの表示(キャッシュ済み) | 中央値1.5ms | 1.4ms | 1.5ms |
| Mayaで遠くへ移動 → 仮表示 / 本物のコマ | 1.1ms / 17ms | 1.0ms / 26ms | 1.0ms / 80ms |
| FramePlayerでコマ送り → Mayaの反映 | 5.9ms(うちMayaの処理4.7ms) | 26ms(処理25ms) | 35ms(処理34ms) |
| FramePlayerの再生 → Mayaの追従 | 100%、遅れ0f | 100%、遅れ0f | 100%、遅れ最大2f |
| Mayaの再生 → FramePlayerの追従 | 100%、中央値1.1ms | 100%、1.0ms | 98%、1.1ms |

- 通信そのもの(送ってから相手が受け取るまで)は、どの条件でも0.1ms前後。遅れのほとんどは、Mayaのシーンの計算と、
  キャッシュに無いコマのデコード。
- Mayaの処理が1コマの時間に収まらないときは、最新のフレームだけを反映するので、遅れは積み重ならない
  (60fpsの重いシーンでも最大2f)。
- この測定のPCは画面の合成が遅い状態(リモート接続と仮想ディスプレイで1秒に約4回)だったため、
  FramePlayerの表示がまれに数十ms待たされた(最大87ms)。通常のモニターでは画面の書き換えは約17ms(60Hz)ごと。

測定用に、環境変数 `FRAMEPLAYER_TRACE_LOG` にファイルのパスを入れて起動すると、FramePlayerが連携の命令の送受信、
コマの表示、操作部の描画、動画を開く各段階の時刻をそのファイルへ書く(入れなければ何もしない。以前の名前
`FRAMEPLAYER_SYNC_LOG` も使える)。

## パッケージの構成

このフォルダだけで動く単体のパッケージ。社内の共通ライブラリ(hlibなど)には依存しない
(Maya側は maya.cmds・maya.api.OpenMaya・Python標準ライブラリだけを使う)。

```
FramePlayer/
├ FramePlayer.exe     プレイヤー本体(配布用。Git管理対象)
├ FramePlayerSetup.exe インストーラー(配布用。Git管理対象。中にFramePlayer.exeを含む)
├ FramePlayer.mod     このフォルダを単体で使うときのMayaモジュール定義
├ maya/               FramePlayerだけを入れた人向けの連携の入口(FramePlayerMayaSync.py)
├ python/frameplayer/ Maya側の連携パッケージ(sync.py=接続、ui.py=画面)
├ docs/               利用者向けのSphinxドキュメント(画像は docs/tools/capture_docs.py で撮る)
├ resources/icon/     アイコンの元のSVGと、exeに埋め込む .ico
├ installer/          インストーラーの設定(tools/WinAppKit の WinAppSetup で読む)
├ src/                プレイヤーのC++ソース
├ tests/              コマ番号の正確さの確認用ツール
└ CMakeLists.txt
```

- このワークスペースでは `maya/modules/FramePlayer.mod` が `python/` をMayaに読み込ませる。
  HToolsのメニュー項目(`HTools/animation/framePlayerSync.py`)は、`frameplayer.show()` を呼ぶだけの入口。
- 単体で使うとき(別のリポジトリとして配布するときなど)は、このフォルダを `MAYA_MODULE_PATH` に加えると
  同梱の `FramePlayer.mod` で読み込まれる。
- FramePlayerだけを入れた人(セットアップ・exeの単体配布)向けに、`maya/FramePlayerMayaSync.py` を置いている。
  Mayaのビューへドラッグ&ドロップすると、同じ並びの `python/frameplayer` を `sys.path` に足して連携パネルを開き、
  今のシェルフにボタンを足す(次からはボタンで開ける)。スクリプトエディターの File > Source Script でも開ける。
  見つからないときは環境変数 `FRAMEPLAYER_HOME`(FramePlayerのフォルダ)とインストール先(App Paths)も探す。
  セットアップはこのスクリプトと `python/frameplayer` もインストール先へ入れる(`<インストール先>\maya`・`\python`)。
- Mayaから起動するexeは、環境変数 `FRAMEPLAYER_EXE` → パッケージ直下の `FramePlayer.exe` → インストーラーで入れた
  FramePlayer(Windowsの App Paths に登録された場所)の順に探す。

## ソース構成

- `src/core/` 画面に依存しない読み込み処理
  - `FrameSource` コマを先頭から順に返す共通の窓口。読み込み方式を増やすときはこの派生クラスを足す
  - `MediaFoundationSource` Media Foundationによる目次の作成とデコード(GPU、使えなければCPU)
  - `Mp4SampleTable` mp4/movのファイル内の目次(サンプルテーブル)の読み取り
  - `AudioPlayer` 音声のデコードと出力、再生位置の取得
  - `GpuDevice` デコード・キャッシュ・描画で共有するGPUデバイス
  - `ColorInfo` 色の解釈(行列・範囲・色域・伝達関数)と、規格から求める変換式(CPUでのYUVからRGBへの変換も)
  - `FrameRenderer` 自前のシェーダーでの縮小・YUVからRGBへの変換・画面に合わせた出力(`shaders/FrameShaders.hlsl`)
  - `Clip` 上限付きキャッシュと裏での先読み、画像の縮小、動作状態(再生中・背面・休止)に応じた先読みの切り替え
  - `KeyframeThumbnails` キーフレームの縮小画像(キャッシュに無い位置の仮表示用)
  - `ImageSequenceSource` 連番画像の読み込み元(連番の検出・欠け・並行したデコード・WICでの読み込み)
  - `ExrReader` OpenEXRの読み込み(圧縮の展開を含む)、`Inflate` zlib(deflate)の展開
  - `ThreadQos` 裏の作業をするスレッドの優先度と省電力の切り替え
  - `Util.h` 高精度タイマーとパスの扱いの小さな関数(複数のファイルで共有)
  - `TraceLog.h` 処理時間や連携の遅れを測るための時刻の記録(環境変数を入れたときだけ)
- `src/app/` 画面
  - `PlayerWindow` メインウィンドウ。`PlayerWindow.cpp` はウィンドウ・動画を開く・比較・連携・資源の管理、
    `PlayerWindowControls.cpp` は下部の操作部(配置・描画・マウスとキー・数字の欄・音量)
  - `VideoView` 映像の表示と再生の時間管理(描画専用のスレッド)、画面の状態(HDR・SDRの白の明るさ)に合わせた描画先の切り替え
  - `Ui` 操作部の色・寸法とGDIの描画部品(書体・裏の画像・作り置きの画像の使い回しを含む)
  - `Settings` 次回の起動でも使う設定(レジストリ)の読み書き
  - `TimeSync`・`SyncServer`・`SyncAuth` Mayaなどとの連携の窓口、待ち受け口、相手を確かめる鍵とHMAC
  - `main.cpp` 起動処理
- `python/frameplayer/` Maya側の連携パッケージ(`sync.py` 接続とMayaの時間の受け渡し、`ui.py` 画面)
- `tests/verify_frame_index.cpp` コマ送りの正確さの確認用ツール
- `tests/verify_color.cpp`・`tests/make_color_testdata.py` 色の正確さの確認用ツールと、確認用動画・期待値の作成
- `tests/make_codec_testdata.py`・`tests/run_codec_check.py` 全コーデック・入れ物の確認用動画の作成と、まとめての確認
- `tests/make_sequence_testdata.py`・`tests/run_sequence_check.py`・`tests/run_exr_check.py`・`tests/image_convert.cpp`
  連番画像の確認用データの作成と確認(上記「確かめ方(連番画像)」)
