# Maya検証動画の記録とGoogle Drive保存

動画は`.maya-output/verification/<実行ID>/`へ生成し、Google Driveへ保存します。MP4と画像連番はGitやGitHub Pagesへ登録しません。Sphinxには選んだ動画の説明・サムネイル・Driveの閲覧リンクを掲載します。

## 標準ワークフロー

Codex・Claude Code・GitHub Copilotは、リグ検証成果物を「専用シーンで検証リグ作成 → Maya内で計算式と数値を表示 → 実動画を録画・確認 → Google Driveへ保存・リンク共有」の順序で作成します。各エージェントの指示Markdownにも同じ方針を記載しています。

計算表示には、式だけでなく変数の意味・単位・角度の基準・固定値・毎フレームの入力値と実際のDG出力を含めます。固定の値が変わるような演出はせず、変化する値のみ更新します。MayaのHUD等を対象modelPanelへ表示し、完成MP4で可読性・表示の更新・境界での停止と復帰を確認します。`tools/demo_top_view_tangent_limit.py`が実装例です。

ユーザーがローカルのみ等を指定した場合はその指示を優先します。Drive機能が使えなくてもローカル録画まで進め、未完了の工程を明記します。録画・アップロードと、Sphinxへの掲載・コミット・プッシュは別工程です。

## 保存先

- [Maya検証動画](https://drive.google.com/drive/folders/1SRERyPNRTIx8Sx_Gv8nK6_XnkcVHhgRy)
- [RootDirectionLimit](https://drive.google.com/drive/folders/1ffExDawPilEDRgWSm3kIvTz8nzDH1J1k)

新しい動画の共有設定は「リンクを知っている全員」「閲覧者」、検索による発見は無効にします。既存の別ファイルの権限は変更しません。フォルダ作成だけではこの共有設定にはなりません。

## 録画

`tools/verification_video.py`の`recordVideo()`は、表示中のmodelPanelから各フレームをMayaの`M3dView.readColorBuffer`で記録します。検証用コールバックが姿勢更新と数値判定を担当します。画面全体や操作UIの録画は対象外です。

```python
from verification_video import recordVideo

def evaluate(frame):
    # 検証シーンを更新し、実際の数値判定を返す。
    return {"frame": frame, "ok": True}

folder = recordVideo(
    "検証名", 120, 24, "対象modelPanel名", evaluate,
    ffmpeg=r"C:/path/to/ffmpeg.exe",
)
```

`evaluate`によるシーン変更の復元は呼び出し側で行います。共通処理は元のcurrentTimeを復元し、失敗時にも結果JSON・HTMLと取得済みフレームを保存します。全フレームの`ok`が明示的にTrueの場合のみ数値検証成功とします。

FFmpegは`libx264`を含むものを指定してください。出力はH.264/yuv420p/faststartの1280×720 MP4です。再生fpsは検証内容に合わせます。実行日時・Maya版・Gitコミット・未コミット変更の有無・映像SHA-256・各フレームの診断も残します。

### 尻尾根元補正

専用の検証用Maya GUIで`demo_root_direction_limit.py`を先に実行します。このデモは新規シーンを作るので、作業中のMayaには送らないでください。

そのGUI内で以下を実行します。

```python
import os
import sys
sys.path.insert(0, r"C:/MayaHToolsWorkspace/tools")
os.environ["MAYA_VERIFICATION_FFMPEG"] = r"C:/path/to/ffmpeg.exe"
import record_root_direction_limit
record_root_direction_limit.main()
```

193フレーム・24fpsで、中立→腕捻り→前屈→側屈→中立を連続記録します。cone角度・根元位置・末端ローカル値を全フレームで検証します。この録画の判定は実メッシュ全頂点の非貫通を保証しません。

`record_root_direction_limit.main(armMotion=True)` は、胴体を固定して腕の持上げ・前後スイング・捻りを337フレーム、24fpsで記録します。検査内容は同じです。

`record_root_direction_limit.main(armMotion=True, elbowBend=90)` は、肘を90度曲げた状態で同じ動作を記録します。赤は未補正、緑は補正後、青は腕です。録画後に肘の角度も復元します。

`record_root_direction_limit.main(armMotion=True, elbowBend=90, tailLength=18)` は、尻尾方向の表示を18cmへ伸ばし、体を横断する未補正方向と補正方向を比較します。カメラの表示範囲を広げ、比較姿勢で停止する時間を設けます。表示用メッシュだけを伸ばし、末端のローカル値は変えません。中心線と胴体メッシュの交差を各フレームで記録し、HUDにBODY HIT/CLEARを表示します。この交差計算は検証時のみで、リグへのコリジョン計算追加ではありません。表示長とカメラ幅も録画後に復元します。

## Drive保存と共有

### 上面だけの簡易検証

ユーザーの接線停止の意図に合わせた最新検証は`tools/demo_top_view_tangent_limit.py`です。専用GUIで新規シーンを作り、円に当たらない方向は維持し、円へ入る回転だけを接線角で止めます。左右の停止と復帰を469フレーム、24fpsで示します。円半径3cm・肘の距離4.5cmは固定し、薄い線の表示余裕として半径へ0.03cmを加え、限界角を`180 - asin((3 + 0.03) / 4.5)`度で計算します。標準clampと2つのunitConversionで回転を制限し、実行時のPythonやメッシュ接触検索は補正へ使用しません。円と根元距離が変化する一般リグ向けAPIはまだ実装していません。入力は外向き0度を基準に-180〜180度の範囲で検証しています。保存シーンは`top-tangent-stop.ma`です。

以下の`demo_top_view_root_limit.py`は、外向きcone補正との比較用の旧検証です。

専用Maya GUIで`tools/demo_top_view_root_limit.py`を実行すると、新規シーンを作成します。既存シーンを破棄するため、作業中のMayaへは送らないでください。胴体はXZ平面上の半径3cmの円、肘は円中心から4.5cmの点、尻尾は12cmの方向線です。カメラは上面の固定正投影で、腕位置と尻尾方向のY軸回転だけを動かします。

赤が未補正、緑が補正後、青が曲げた腕です。円への線分交差は録画時の検証にのみ使用します。補正は既存のRootDirectionLimitの標準DGを使用し、交差検査の結果は接続しません。325フレーム、24fpsの正方形動画と`top-view.ma`を実行フォルダへ保存します。

接続済みGoogle Driveプラグインを使うエージェントは以下の順序で保存します。アップロードは録画実行とは別の処理であり、このPythonスクリプト単独ではクラウドへ送信しません。

1. 生成結果が成功しているか確認する。失敗した動画を共有する場合は失敗と明記する。
2. `google_drive_upload_file`でその実行の`verification.mp4`だけを指定フォルダへアップロードする。日時を含む名前にし、既存動画を上書きしない。
3. Driveでその動画を「リンクを知っている全員・閲覧者」に設定する。一般公開共有を扱えないコネクターの場合はDriveの共有UIを使用する。メールによる招待は不要。
4. `google_drive_get_file_metadata`で`id,name,mimeType,size,md5Checksum,webViewLink,permissions`を読み戻す。
5. そのメタデータをローカルJSONへ保存し、`attachDrive`で検証結果へ登録する。

```powershell
python tools/verification_video.py .maya-output/verification/<実行ID> .maya-output/verification/drive-metadata.json
```

`attachDrive()`は形式・サイズ・ローカルSHA-256を確認し、Driveが返したURLを`result.json`、`index.html`、`drive-link.rst`へ保存します。md5Checksumを取得できた場合はDrive側との一致も検査します。公開権限の読み戻し結果は`drive.link_viewer_verified`へ記録します。Falseの場合はリンク共有の完了を報告しないでください。

コネクターの接続認証をローカルスクリプトへ流用したり、トークンをGitへ保存したりしません。通常のPythonのみで自動アップロードする運用は、別途Drive OAuthの初期設定が必要です。

## iPadとSphinx

Claude Codeの完了報告にはDriveが返した閲覧URLを載せます。iPadではSafariまたはDriveアプリで開きます。アップロード直後はDriveの動画処理が終わるまで再生できない場合があります。

Sphinxへ掲載する場合は`drive-link.rst`のリンクを該当機能の説明へ追加します。公開Sphinxに載せたURLは誰でも見つけられます。毎回の検証URLを自動で公開Sphinxへ追記する処理はありません。

iPad実機での再生確認と、Claudeアプリ内の直接再生確認は別途必要です。
