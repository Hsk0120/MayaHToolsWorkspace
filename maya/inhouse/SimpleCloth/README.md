# Simple Cloth 0.1.0

Mayaのポリゴンメッシュを布として動かす、独立したPython API 2.0プラグインです。
Chaos Clothに近い、入力メッシュ・Max Distanceマップ・伸び/曲げ・コリジョンの設定手順を提供します。
計算は独自のXPBD実装で、Unreal Engineのコード・バイナリを組み込んだ移植ではありません。
Chaos Clothの数値・アセット・Dataflowとの互換性はありません。

## 起動

ワークスペースの起動バッチでMayaを起動し、**HTools → phsycs → simpleCloth**を選びます。
Maya標準UIを使用し、Qtの追加インストールは不要です。

```python
import simpleCloth
simpleCloth.show()
```

すでに起動しているMayaでモジュールが見つからない場合は、再起動するか次を実行します。

```python
import sys
sys.path.insert(0, "C:/MayaHToolsWorkspace/maya/inhouse/SimpleCloth/scripts")
import simpleCloth
simpleCloth.show()
```

計算プラグイン`plug-ins/simpleClothNode.py`はCreate Cloth時にロードします。
Mayaのセキュリティ確認が出たら、表示されたパスと内容を確認してください。
ツールは信頼済みプラグインパスやユーザーのMaya.envを書き換えません。
シーン再読込時には`SimpleCloth.mod`の検索パスが必要です。

## 基本の使い方

1. 静止姿勢のフレームへ移動し、低分割の入力メッシュを1個選択して**Create Cloth**。
   現在のワールド形状を静止長として記録します。入力のスキン、キー、履歴は保持します。
2. **出力を選択**から頂点選択へ切り替え、固定したい頂点を選択します。
   **選択頂点のMap値**を0にして**選択頂点へMap値を設定**。入力側の同じ頂点も使用できます。
3. **Max Distanceをペイント**でMaya標準Paint Attributes Toolを開きます。
   黒(0)は入力姿勢に固定、白(1)はMax Distanceまで移動可能です。
   Tool SettingsのValue・Replace/Add/Smooth・Floodで調整できます。
   ペイント開始時はStart Frameへ戻ります。再生を止めて編集してください。
4. **Stretch / Bend / Animation**で伸び・曲げ・減衰を調整します。
   Complianceは小さいほど硬く、0で理想的な剛性拘束になります。
   実際の硬さ・誤差はIterationsとSolver Rateにも依存します。
5. **Collisions**からsphere / capsule / planeを追加し、ガイドを配置します。
   追従チェックを付けると、選択TransformまたはJointの子として作成します。
6. タイムラインを再生します。必要なら**リセットして開始フレームへ**。
7. **Preset / Bake / Remove**の範囲を指定し、別メッシュへベイクします。
   ベイク後のメッシュは通常のblendShapeとキーで再生できます。

作成直後のMapは全頂点1で、固定頂点はありません。
入力と出力は両方表示されます。見比べた後、入力の表示を必要に応じて切り替えてください。
出力には初期マテリアルを割り当てます。UVは維持するため、必要なマテリアルを割り当て直せます。

## 設定

すべての距離は**cm**、加速度は**cm/s²**です。Mayaの表示単位をmへ変更しても計算単位は変わりません。
Transformの移動チャンネルは通常のMaya表示単位です。

| アトリビュート | 意味 |
| --- | --- |
| Max Distance / maxDistance | 入力の各頂点から移動可能な半径。`半径 = maxDistance × maxDistanceMap[i]` |
| Stretch Compliance | 三角形の辺の伸縮柔らかさ。対角線も対象とし、独立したせん断係数はなし |
| Bend Compliance | 隣接三角形の対向頂点間スプリングの柔らかさ。二面角の拘束ではない |
| Particle Mass | 各頂点の質量(kg)。全頂点一様、面積密度からの自動計算はなし |
| Damping | 速度減衰(1/s)。各ステップで速度へ`exp(-damping × dt)`を掛ける |
| Anim Drive | 入力姿勢への引き戻し(1/s)。0で無効 |
| Simulation Blend | 入力メッシュと計算結果の線形補間。0で入力と一致 |
| Gravity | 全頂点へ加える重力加速度。既定Y=-980 |
| Wind Acceleration | 一様な外力加速度。抗力・揚力・空気密度を使う風モデルではない |
| Backstop Radius | 各入力頂点の背後に置く排除球の半径。0で無効 |
| Backstop Distance | 球表面と入力頂点の距離。中心は`input - normal × (radius + distance)`。負値も可 |
| Collision Thickness | コライダー表面からの粒子の余裕 |
| Friction | 接触した粒子の更新後速度へ掛ける減衰率(0〜1)。Coulomb摩擦ではない |
| Particle Self Collision | 非隣接粒子間の離隔。三角形・辺同士の衝突ではない |
| Self Thickness | セルフコリジョンの粒子半径。静止辺長より十分小さくする |
| Start Frame | シミュレーション開始フレーム。作成時のcurrentTime |
| Solver Rate | 秒あたり固定計算回数。1〜480Hz、既定120Hz |
| Iterations | 各ステップの拘束反復回数。1〜100 |
| Max Steps | 開始からの固定ステップ数の上限。超過時は計算を拒否 |

物理係数・Map・開始時刻はショット全体で固定です。変更すると過去から再計算します。
これらへのアニメーション/外部接続は誤った履歴計算を避けるため拒否します。
入力のTransform・スキン変形、コライダーのTransform・寸法はアニメーションできます。
静止長は作成時の値です。入力をスケールしても静止長は自動では伸縮しません。

## コライダー

- **sphere**: `clothRadius`で球半径を調整。
- **capsule**: ローカルY軸の線分を球で膨らませた形状。`clothHeight`は両端球の中心間距離、全長は`height + 2 × radius`。
- **plane**: ローカル+Y側へ点を押し出す無限平面。表示の四角形は範囲の制限ではありません。

コライダーは正の均等スケールのみ対応し、シアー・非均等スケールは拒否します。
ガイドの子の表示メッシュを編集しても計算形状は変わりません。ガイドの移動・回転・寸法を編集します。
削除は専用の**選択コライダーを削除**を使ってください。
出力メッシュへの追従は禁止です。間接的な出力依存を作るリグ接続も循環するため使用しないでください。

## 残差と衝突の制限

固定頂点とMax Distanceを優先します。固定位置や移動可能範囲がコライダー内部にあると、すべての条件は同時に満たせません。
**Solver / Diagnostics**で以下を確認します。

- **Max Stretch Error**: 全辺の`abs(現在長 / 静止長 - 1)`の最大値。0.05は最大5%の誤差。
- **Residual Penetration**: 外部コライダーの外へ出すのに必要な最大補正距離(cm)。固定頂点も含む。
- **Max Distance Error**: 最大距離を超えた分(cm)。

出力Blendを下げた場合も表示結果で残差を測ります。入力との補間によって貫通が再発する場合があります。
Backstop球同士・BackstopとMax Distanceの競合、セルフコリジョンの残差はこの診断に含みません。
点ベースの離散衝突のため、面の貫通・薄い障害物のすり抜け・高速動作でのトンネリングを防ぐ保証はありません。

## プリセット・ベイク・Undo

**プリセット**は係数と全頂点MapをUTF-8 JSONへ保存します。
頂点数・面の頂点順が同じメッシュでのみ読込可能です。位置、コライダー、キー、開始時刻は含みません。
読込内容を全件検証してから変更します。保存ファイルには元メッシュの形状データを含みません。

**ベイク**は指定整数フレームごとにblendShapeターゲットを内包し、頂点形状をキー化します。
元の入力やソルバーにはキーを追加しません。ベイク範囲外は両端形状を保持し、フレーム間は線形補間します。
最大1000フレームです。ターゲット数に比例してシーンが大きくなるため、必要な範囲に絞ってください。
元のソルバーを削除してもベイク済みメッシュは保持します。FBX/Alembic書出しは別途Maya標準機能を使用します。

作成・Map変更・コライダー追加/削除・設定読込・ベイク・セットアップ削除はUndoに対応します。
Undo無効の環境ではこれらの編集を拒否します。出力やコライダーの下へ別の大切なオブジェクトを親子付けしないでください。

## Python例

```python
from simpleCloth import api

cloth = api.create("cape_input")
api.setVertexWeights(cloth, [0, 1, 2, 3], 0.0)
api.paintMap(cloth)
collider = api.addCollider(cloth, "capsule", radius=3, height=8, attachTo="chest_JNT")
api.savePreset(cloth, "C:/MayaHToolsWorkspace/.maya-output/cloth-preset.json")
baked = api.bake(cloth, 1, 120)
```

公開入口は`simpleCloth.__all__`を参照してください。

## 動作範囲

- Maya 2027 / Windowsで検証。他バージョンは未検証。
- 3〜1500頂点の固定トポロジー。Python CPU実装のため、まず100〜300頂点で調整してください。
- 履歴のキー変更を検出するため、要求時刻までの過去入力を毎回照合します。長い範囲や重いスキンでは再生が遅くなります。
- キャッシュはノードごとに保持し、シーンには保存しません。逆再生・時刻ジャンプ時も開始からの固定刻み結果を再現します。
- APIノードは直列スケジューリングです。DG / Serial / Parallelの検証済み。GPU計算・高速な並列布計算は未実装。
- レンダーメッシュへの自動ラップ、LOD、衣服パネル縫合、Dataflow、テザー、異方性材料、破断、三角形セルフ衝突、任意メッシュ/SDFコライダー、Chaosアセット読込は未実装。
- インスタンス、面のない頂点、面積0三角形、長さ0辺、3面以上を共有する辺は入力不可。シミュレーション途中のトポロジー変更も不可。
- ノードID `0x0007F7A1`は開発用です。社外配布時にはAutodeskの正式割当てが必要です。

## 検証

専用mayapyプロセスで実行します。テストは新規シーンを作るため、作業中のGUIへ送信しないでください。

```powershell
& 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/SimpleCloth/tests/test_simpleCloth.py
```

`tests/demo_simpleCloth.py`は専用GUI向けの検証シーン/録画スクリプトです。
99頂点・固定辺・球・入力の左右往復・距離上限の維持・球を離した後の復帰を145フレームで確認します。
赤は入力、緑は出力、青はコライダー。HUDは固定値と実出力の数値を区別して表示します。
動画・診断JSON・検証シーンは`.maya-output/`に保存し、Gitへ登録しません。
