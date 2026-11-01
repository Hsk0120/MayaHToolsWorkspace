# QuickPathExplorerの開発・再ビルド

この文書のコマンドはQuickPathExplorer直下で実行します。親リポジトリやmlibは不要です。Windows版は静的Qtの単一exe、Maya版はMaya付属Qtへリンクした年別の単一mllです。アプリ本体はPythonを使用しません。開発・検証と、Maya同梱Pythonでプラグインを自動ロードする最小の`scripts/userSetup.py`にのみ使用します。

## 開発環境

- Python 3.12（64bit、Python Launcher付き）。
- Visual StudioのC++ツールセット、Windows SDK、CMake/Ninja。Visual Studio Installerで同梱の`.vsconfig`をインポートします。
- Qt/メディアのビルドにはv143 14.44とGit for Windowsが必要です。
- Maya版には対象年のMaya、SDK・Qtヘッダーと次のツールセットが必要です。

| Maya | ツールセット |
|---|---|
| 2022 / 2023 | v142 |
| 2024 / 2025 | v143 |
| 2026 / 2027 | v145 |

`check_environment.cmd`は環境を表示するだけで、ソフトウェアをインストールしません。Autodesk SDKやVisual Studio本体は同梱しません。Mayaから開発用ファイルを準備する場合もProgram Filesを変更せず、`.maya-output/devkit`を使います。公式devkitを別途用意した場合は指定できます。

```powershell
$env:MAYA_DEVKIT_2027 = 'D:/SDK/Maya2027/devkitBase'
```

## Windows版をビルドする

初回は同梱ソースからQtBase/QtSvgとメディア用FFmpegを準備します。Qtは静的CRT・静的ライブラリ、FFmpegはGPL/nonfree部品を無効にした構成です。make開発ツールがない場合、メディアのビルドスクリプトはMSYS2公式配布から取得します。

```powershell
py -3.12 tools/build_static_qt.py --source-archives third_party/sources --jobs 4
py -3.12 tools/build_native_media.py --source-archives third_party/sources --jobs 4
.\build_windows.cmd
```

`build_windows.cmd`はC++をコンパイルし、専用一時データで回帰テストを実行してから、直下の`QuickPathExplorer.exe`を更新します。旧exeは`.maya-output/product-backups`へ残します。起動中のexeは置換できないため、Windows版QPEを終了してから実行してください。Mayaを終了する必要はありません。

出力は`.maya-output/cpp-windows/`です。直下のexeを変更しないビルドは次のとおりです。

```powershell
py -3.12 tools/build_cpp_windows.py --product --test
```

ビルド素材にPythonを使用しますが、exeへPython/PySideを内蔵しません。Qtとアイコンをexeへリンクします。FFmpegはexeリソースへ格納し、サムネイル取得時にユーザーキャッシュへ展開して子プロセスで使用します。隣に`_internal`を置く必要はありません。

深いフォルダーに展開した場合は、MSVC/Qtの生成パスがWindowsの制限を超えることがあります。その場合は短い専用作業先を指定します。ソースの配置やシステム設定を変更する必要はありません。

```powershell
py -3.12 tools/build_static_qt.py --source-archives third_party/sources --work-root C:/QPE-build/qt --jobs 4
py -3.12 tools/build_native_media.py --source-archives third_party/sources --qt-root C:/QPE-build/qt --work-root C:/QPE-build/media --jobs 4
py -3.12 tools/build_cpp_windows.py --product --qt-prefix C:/QPE-build/qt/install --qt-source C:/QPE-build/qt/sources/qtbase-everywhere-src-6.8.3 --media-executable C:/QPE-build/media/qpe-media.exe --build-dir C:/QPE-build/app --test
```

## Maya版をビルドする

メディア用FFmpegは上記と同じ専用ビルドを準備しておきます。Windows用静的QtはMayaへリンクしません。

```powershell
.\generate_projects.cmd --versions 2027
.\build_maya.cmd --versions 2022 2023 2024 2025 2026 2027
```

Visual Studioプロジェクトは`.maya-output/plugin-build/QuickPathExplorer/<年>/`、mllは`release/plug-ins/windows/<年>/quickPathExplorer.mll`です。Mayaで使用中のmllは、処理完了後にPlug-in ManagerでアンロードするかMayaを終了してから更新します。

任意のステージング出力を使う場合:

```powershell
py -3.12 tools/build_maya_plugin.py --versions 2022 2027 --output-root .maya-output/product-validation
```

Mayaではその年のmllをロードし、Window → QuickPathExplorerまたはMELの`quickPathExplorer;`で開きます。`QuickPathExplorer.mod`は年別パスの任意の登録用です。自動ロードはMayaのPlug-in Managerで設定します。QPEは信頼設定を変更しません。起動・復元には外部Pythonファイルを使用しません。

Maya全体のQtパレットや入力フィルターを変更せず、自分のUI・タイマー・コールバックだけを管理します。実行中のファイル操作・ワーカーが残る場合はアンロードを拒否します。完了を待って再実行してください。

## LGPL資料と再リンク

QPE独自コードは同梱`LICENSE`のMITライセンスです。Qt、FFmpeg、miniz等の条件は`third_party/NOTICES.txt`と`third_party/licenses`を参照してください。対応するQtBase/QtSvg/FFmpegソース、構成記録、ハッシュとSBOMを`third_party`に含めます。独自コードの利用許諾は、これらの依存物の条件を置き換えません。

配布する際はexeだけでなく、対応するソース・ライセンス・再リンク手順も同じ配布先から利用できるようにしてください。ソース付きフォルダーを作るコマンドは次のとおりです。ZIPは作りません。

```powershell
py -3.12 tools/prepare_cpp_relink.py --name product-source
```

`.maya-output/product-source/`にexe・QPEソース・対応依存ソース・`RELINK.txt`・`SHA256.json`を収集します。同名フォルダーは上書きしません。改変したQt SDKへリンクする例:

```powershell
py -3.12 tools/build_cpp_windows.py --product --qt-prefix D:/QtModified/install --qt-source D:/QtModified/qtbase --build-dir .maya-output/relinked --test
```

改変版の実行にQPEの署名・秘密鍵・アクティベーションは不要です。Qt変更のデバッグと再リンクを妨げません。FFmpeg変更版は`QPE_FFMPEG`環境変数またはQPE設定から指定できます。埋め込む場合はCMakeの`QPE_MEDIA_EXECUTABLE`に変更版を指定して再リンクします。

`tests/verify_static_relink.py`は専用Qtソースのバージョン文字列を変更して再リンク・起動し、最後に元のQtを復元する開発用検証です。同じQt SDKを使う別ビルドと同時実行しないでください。

## 検証と独立リポジトリ

C++回帰は`build_windows.cmd`または`build_cpp_windows.py --product --test`で実行します。`tests/native_maya_smoke.py`と`tests/native_maya_restart.py`は専用prefs・専用データのMayaだけで使用します。シーンを変更するため、利用者の作業中Mayaへ送信しないでください。Qtプログラム操作、OS入力、実プロセス再起動は証拠を区別します。

保持するものはソース、CMake、cmd、icons、tests、tools、third_party、文書、年別mllです。`.maya-output`、build、dist、`.vs`、キャッシュ、PDB/オブジェクトはGit対象外です。Windows exeも現在はローカル生成物としてGit対象外です。別リポジトリの作成や公開はこのビルドでは行いません。
