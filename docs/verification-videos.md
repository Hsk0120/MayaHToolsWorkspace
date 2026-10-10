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

## 肘の位置が動く接線停止サンプル

固定位置の`tools/demo_top_view_tangent_limit.py`と保存済み動画・シーンは残し、別の`tools/demo_top_view_moving_tangent.py`で肘移動を検証します。専用GUIへ送信すると新規検証シーンを作り、入力をキー化して動画と`moving-tangent-stop.ma`を保存します。録画には同じFFmpeg環境変数を使用します。

円の中心を原点として`d=sqrt(x*x+z*z)`、外向きの角度を肘の位置から求め、`limit=180-degrees(asin((r+gap)/d))`を更新します。入力角度から外向き角度を引いて-180〜180度へ折り返し、`output=outward+clamp(relative,-limit,limit)`を計算します。実DGでは平方根・angleBetween・condition・clamp・単位変換等の標準ノードを使用し、保存シーンの補正にPythonやコリジョン検索は不要です。Maya HUDには距離・基準方向・相対入力角度・制限角度・実出力を表示します。

対象はXZ平面、固定円半径3cm、余裕0.03cm、無スケール、根元が半径と余裕の和より外側にある状態です。距離3.4〜7cm、円周上の移動、左右の接線停止と安全方向への復帰を検証します。根元自体が円の内側に入る場合は回転だけでは回避できません。相対入力が±180度を越えると最近接の接線側が切り替わるため、その境界での連続回転を保証する仕様ではありません。短い尻尾でも長い棒としての制限を使用します。

## 腕のローカルX軸だけで回すジョイントサンプル

`tools/demo_joint_twist_tangent.py`は既存の固定位置・移動位置サンプルを残した別検証です。腕軸は`armTwistAxis_JNT`のローカルX、尻尾はその子の`tailRequested_JNT`と`tailCorrected_JNT`からローカルYへ伸ばします。補正は`tailCorrected_JNT.rotateX`だけへ接続し、rotateY/Zは0でロック、根元位置・jointOrientは変更しません。腕自体の移動・傾きは入力です。保存シーンは`joint-twist-tangent.ma`です。

体を半径3cmの球で近似します。球中心を腕ローカル空間へ変換した座標を`c=(cx,cy,cz)`、余裕込み半径を`R=3.03`として、尻尾が回るYZ平面との断面半径は`rho=sqrt(max(0,R*R-cx*cx))`、断面中心までの距離は`dYZ=sqrt(cy*cy+cz*cz)`です。`limit=180-degrees(asin(rho/dYZ))`と、断面中心から離れる方向の角度で、前の接線停止と同様に相対入力を制限します。`R*R-cx*cx<=0`なら回転平面と球内部は交わらないため、入力をそのまま出力します。実DGでは標準angleBetween・pointMatrixMult・演算・condition・clamp・単位変換を使用します。球近似の幾何計算であり、メッシュのコリジョン検索は補正へ接続しません。

前提は根元が球の余裕込み半径より外側、無スケール、尻尾が腕Xに垂直な直線、補正ジョイントのjointOrientが0であることです。腕のjointOrientZ=90度を含む親姿勢に追従し、腕傾斜0・±25・60度を検証します。実体の形状や曲がった尻尾の全頂点を保証する汎用APIではありません。相対角度±180度の接線側切替には連続性の保証がありません。HUDは録画用Pythonで更新するため、保存シーンを単独で開いた際のHUD再作成は別途必要です。保存した補正DGと入力アニメーションはPythonなしで再生できます。

`demo_joint_twist_tangent.main(topView=True)`は同じ入力・補正を上面の固定正投影で録画します。既定の斜め版と別の実行フォルダへ保存し、上面版の最新フォルダは`.maya-output/verification/latest-joint-twist-top.json`に記録します。腕の傾斜を含む3D動作なので、上面で円と重なって見えても高さ方向で離れている場合があります。

## 肘側へ固定する接線

`demo_joint_twist_tangent.main(topView=True, fixedElbowSide=True)`は、黄色の`elbowDirection_JNT`が示す曲がり側を初期姿勢で選び、その接線側を維持します。緑が固定側、橙が従来の最近接側、赤が入力です。既存モードと保存済み動画は保持し、`joint-twist-fixed-elbow.ma`と`latest-joint-fixed-elbow.json`を別の実行フォルダへ保存します。

腕ローカルYZ平面での外向きを`n=(ny,nz)`、肘ガイド方向を`h=(hy,hz)`とすると、正回転側の接線方向は`(-nz,ny)`です。初期の内積`(-nz)*hy+ny*hz`の符号を`side`として記録します。このサンプルではガイドを腕ローカル-Zへ置き、side=+1となります。肘のガイドが側を判定できない方向なら作成を拒否します。球の断面・制限角度は従来と同じです。

相対入力を`relative=wrap(input-outward)`として、断面があり`abs(relative)>limit`なら`output=outward+side*limit`、それ以外は`output=input`です。中心方向±180度をまたいでもsideを変更しないため、最近接側の切替は起きません。過去フレームの状態は使わず、任意の時刻へ移動しても同じ結果です。回避先を毎フレーム肘ガイドから選び直す実装ではありません。

安全な入力を維持するため、優先側とは反対の安全方向から危険範囲に入る・抜ける境界では不連続になり得ます。中心方向の切替を解消する方式であり、全360度での連続性を保証しません。実際の肘の曲がり方向に合わせるには、初期ガイドの配置を調整します。腕ローカルXだけの補正・球近似・根元球外等の前提はジョイント版と同じです。

## 固定側のフリップ再現

`demo_joint_twist_tangent.main(topView=True, fixedElbowSide=True, reproduceFlip=True)`は、固定側とは逆の安全境界を横切る条件を別の動画へ保存します。A:入力44〜40度、B:距離4.3〜4.7cmで入力43度固定、C:円周上の肘位置角-2〜+2度で入力43度固定、D:腕傾斜0〜25度で入力40度固定を往復します。最後に中心方向の入力-10〜+10度を往復し、固定側が切り替わらない比較も入れます。保存シーンは`joint-fixed-side-flip-repro.ma`、最新ポインタは`latest-joint-flip-repro.json`です。

side=+1の場合、不連続となる境界は`relative=-limit`です。安全側の出力`outward-limit`から危険側の出力`outward+limit`へ切り替わります。円上で見た最短の跳び角は`360-2*limit=2*asin(rho/dYZ)`度です。距離4.5cm・断面半径3.03cmなら約84.65度で、入力を少しだけ変えても大きく跳びます。入力だけでなく、肘移動や腕傾斜でoutward/limitが変化しても同じ条件を満たします。

HUDにケース名・逆側境界・制限角・出力角と1フレームの回転差を表示します。回転差は360度の表示折り返しを除いた値で、30度を超えるとFLIPを1秒表示します。録画の`ok`は非交差・式との一致・1軸保持を意味し、滑らかさの成功判定ではありません。フリップを意図的に含む再現動画です。

## フリップより貫通を許容する連続制限

`demo_joint_twist_tangent.main(topView=True, fixedElbowSide=True, reproduceFlip=True, continuousElbowSide=True, maximumAngle=60)`は、旧固定側の再現入力を使い、緑の出力を肘側の負回転可動域だけへ制限します。橙は旧固定側の出力です。このジョイント配置では肘側が負回転なので、プラス方向へは切り替えません。最大角は度で0より大きく180未満です。既存の非貫通モードは維持します。

初期尾の+Y方向と選択接線方向の無符号角を`a`として、`bound=-min(maximumAngle,a)`、`output=clamp(input,-maximumAngle,bound)`を標準DGで計算します。無符号角はangleBetweenで0〜180度として求め、±180度の数値折り返しを使いません。安全/危険で接線と入力を切り替える分岐はなく、角度の境界で出力が連続につながります。球の断面がなくなっても可動域制限を維持し、入力への突然のbypass復帰を作りません。

これは片側可動域と連続性を優先する代替方針です。すでに安全な入力も範囲外なら制限し、任意の肘位置で元の接線と同じ方向を保証する方式ではありません。回避に60度を超える回転が必要なら-60度で止め、貫通を許容します。動画末尾に距離3.2cmの上限到達とBODY HITを表示します。`ok`は計算式・1軸保持の検証であり、非貫通の成功を意味しません。球近似・腕軸に垂直な直線尾・無スケール・根元球外等の前提は維持します。保存は`joint-continuous-elbow-cap.ma`、最新フォルダは`latest-joint-continuous-cap.json`です。

## 初期姿勢から大きく動かす説明動画

`demo_joint_twist_tangent.main(topView=True, fixedElbowSide=True, continuousElbowSide=True, maximumAngle=60, largeMotion=True)`は、同じ連続制限の補正を説明用の大きな動作で示します。初期姿勢2秒、安全な肘移動・腕傾斜2〜10秒、入力-100〜+100度の往復10〜18秒、体へ近づいて回転上限に達する18〜28秒、初期姿勢への復帰28〜32秒の順です。肘距離は最大8cmから3.2cmまで動かします。

灰色の初期方向を残し、緑が出力、赤が入力です。橙の旧方式は大回転を比較する段階だけ表示します。Maya HUDとMP4に段階名を表示し、距離・入出力・1フレームの変化・BODY HITを確認できます。`verification_video.encodeVideo()`はフレーム診断の`presentation_stage`がある場合に、段階名を大きくMP4へ表示します。

補正ロジックは連続制限版と同じで、貫通を許容します。保存は`joint-continuous-cap-large-motion.ma`、最新ポインタは`latest-joint-large-motion.json`です。既存の短い再現動画は残します。

## iPadとSphinx

Claude Codeの完了報告にはDriveが返した閲覧URLを載せます。iPadではSafariまたはDriveアプリで開きます。アップロード直後はDriveの動画処理が終わるまで再生できない場合があります。

Sphinxへ掲載する場合は`drive-link.rst`のリンクを該当機能の説明へ追加します。公開Sphinxに載せたURLは誰でも見つけられます。毎回の検証URLを自動で公開Sphinxへ追記する処理はありません。

iPad実機での再生確認と、Claudeアプリ内の直接再生確認は別途必要です。
