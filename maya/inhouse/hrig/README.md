# hrig

Maya 2025以降向けのレイヤードリグ検証パッケージです。
現在のビルダーは、正X軸の3関節FK/IK、Soft IK、補助骨1本を対象とします。
本番向けの汎用オートリガーではありません。

単一入力の行列追従には `hrig.setups.MatrixFollow` を使用できます。
parentConstraintとの評価時間比較用に専用mayapyベンチマークを用意しています。
`backend="cpp"` は専用ノード、`backend="bifrost"` は比較検証用のグラフを生成します。
Bifrost版は構築のUndo/Redoでクラッシュが見つかったため、Undo無効の専用プロセスに限定します。
計測ツールへ `--plugins` を付けると5構成を比較できます。
適用条件と再計測手順は [拘束評価の計測](docs/constraint_performance.rst) を参照してください。

## 読み込み

このワークスペースの起動バッチでは `maya/inhouse` が `PYTHONPATH` に
追加されるため、MayaのPythonから次のように読み込めます。

```python
import hrig
rig = hrig.build_limb()  # Maya標準ノードのみ（backend="standard"）
rig.set_mode('ik')
rig.set_lod(1)           # 0: 通常IK・補助骨停止、1: Soft IK・補助骨有効
```

既存シーンをクリアせずに生成します。同名ルートがある場合は拒否します。
既定の依存はhlib、Maya同梱API、Python標準ライブラリです。
デモも標準ノードのみで構築し、hrig起動時にBifrostを自動ロードしません。
Bifrost/C++は明示選択時のみ利用する任意バックエンドです。

## 操作と保存

### アウトライナーとチャンネルボックス

新規リグには構成操作用の`modules_grp`を追加します。標準デモでは
`rig > modules_grp > limb_module`を選択すると、標準チャンネルボックスに
`Mode`（FK / IK）、`Lod`（Low / Full）、`Match On Switch`が表示されます。

- `Mode`: FK/IKの計算経路を変更します。`Match On Switch`がONなら現在姿勢を
  合わせてから切り替えます。Soft IKの完全伸展など、合わせられない場合は
  警告して元のモードへ戻します。OFFなら姿勢合わせせず切り替えます。
- `Lod`: LowはSoft IK・補助骨・リバースフットを計算経路から外し、Fullは
  各レイヤーのEnabled設定に従います。スキンLODの切替は別操作です。
- モジュール下の`*_soft_ik_layer`・`*_helper_layer`・`*_reverse_foot_layer`を
  選択し、`Enabled`を変更すると個別に有効/無効を切り替えられます。
- `Active`はモード・LOD・Enabled・実装有無を反映した読み取り専用の状態です。
  FK/IKレイヤーの切替はモジュールのModeを使用します。Outlinerの色は有効が緑、
  無効がグレーです（Outlinerで色表示を無効にしている場合はActiveを確認）。

属性の変更と、それに伴う姿勢合わせ・接続変更は一回のUndo/Redoへまとめます。
これらは再生中の切替やアニメーションブレンド用ではなく、停止中に行う構成操作です。
設定属性はキー対象外で、キー・式・他ノードを接続して駆動する使い方には対応しません。
Pythonからの`set_mode` / `set_lod` / `set_layer_enabled`でも表示を同期します。

監視はGUIのscriptJobを使い、保存したシーンへ実行スクリプトは埋め込みません。
ワークスペースのhrig起動モジュールが読込時に監視を再登録します。別の環境で使う場合は
hrigをPythonパスへ入れ、`from hrig.channel_controls import install; install()`を
GUI起動時に実行してください。バッチではscriptJobが動かないため、LimbRigの
明示メソッドを使います。保存済みリグの計算自体は監視なしでも保存時の接続で動きます。

構成操作階層がない旧リグには、`from hrig.channel_controls import attach`の後、
`attach(rig)`で追加できます。既存ファイルの自動移行は行いません。

### デモの命名・階層

```python
from hrig.examples.limb_demo import build_demo
demo = build_demo()
```

`RigNamingRule.ma`の構成に合わせ、標準デモは次の階層で生成します。

```text
rig
├─ modules_grp
│  └─ limb_module
│     ├─ limb_module_fk_layer
│     ├─ limb_module_ik_layer
│     ├─ limb_module_soft_ik_layer
│     ├─ limb_module_helper_layer
│     ├─ limb_module_reverse_foot_layer
│     ├─ limb_module_space_layer
│     ├─ limb_module_twist_layer
│     ├─ limb_module_bend_layer
│     └─ limb_module_driven_layer
├─ geo_grp
│  └─ limb_geo_grp
│     ├─ body_geo
│     └─ body_proxy_geo
├─ jnt_grp
│  └─ limb_jnt_grp
│     └─ root_jnt → mid_jnt → tip_jnt
│                       └─ mid_helper_jnt
├─ ctrl_grp
│  └─ limb_ctrl_grp
│     ├─ limb_fk_ctrl_grp
│     │  └─ root_ctrl_ofs → root_ctrl → mid_ctrl_ofs → mid_ctrl → tip_ctrl_ofs → tip_ctrl
│     └─ limb_ik_ctrl_grp
│        ├─ ik_space_grp → ik_ctrl_ofs → ik_ctrl → reverse_foot_grp → heel_pivot_grp → toe_pivot_grp → ball_pivot_grp
│        └─ pole_space_grp → pole_ctrl_ofs → pole_ctrl
└─ setup_grp（非表示）
   └─ limb_setup_grp
      ├─ limb_ik_setup_grp
      ├─ limb_soft_ik_setup_grp
      └─ limb_helper_setup_grp
```

各カテゴリ内をモジュール、レイヤーの順で整理します。現在の検証ビルダーは
`limb`モジュール1つです。`limb_module_set`内にFK・IK・Soft IK・補助骨・
リバースフットの`*_layer_set`を登録し、DAG階層へ入れられない計算ノードも
対応レイヤーから一括選択できます。補助骨は変形上必要な親骨の下に保持し、
`limb_helper_layer_set`へ登録します。`limb_helper_setup_grp`は将来のDAGセットアップ用で、
現在の補助骨計算ノードはDGノードのため選択セットでまとめます。

骨は`<JointSpec.id>_jnt`、FKは`<JointSpec.id>_ctrl`、その親は
`<JointSpec.id>_ctrl_ofs`、表示カーブは`<control>Shape`です。
`L_` / `R_`や`antenna_01`などの部位名・連番は関節IDに含めて指定します。
参照内の`*_ofs` / `*_ctrl_ofs`表記揺れは、生成側では`*_ctrl_ofs`に統一します。
IK計算骨は`*_ik_jnt`、補助骨は`*_helper_jnt`、リバースフットのピボットは
`*_pivot_grp`とし、計算用DGノードにはノード種類を付けます。
参照シーンのモデル・姿勢・外部プラグインは取り込みません。

初期配置はオフセット親が保持し、FK・IK・poleの移動/回転チャンネルはゼロです。
IK目標の初期位置は部位空間のX=8なので、例えばX=9.5へ動かす場合は
`cmds.setAttr(demo['rig'].controls()['target'] + '.tx', 1.5)`とします。
FK評価には`control.matrix * offset.matrix`を使用します。
`geo_grp` / `jnt_grp` / `ctrl_grp` / `setup_grp`は整理用の同一座標空間であり、
全体の移動・回転・一様スケールは最上位の`rig`で行ってください。
整理専用グループの移動・回転・スケール・シアーは誤操作防止のためロックしています。

2体目は`build_demo('other')`のように明示名を指定します。最上位が`rig`以外なら
子ノードに`other_`等の部位名を付け、名前の衝突を防ぎます。
`build_limb()`にも同じ規則を適用します（既定部位名は従来どおり`limb`）。
既存シーンのリグを自動改名・移行する処理は含みません。新規生成に適用されます。

カーブ付きの操作コントローラーと高低メッシュをまとめて試す場合:

```python
from hrig.examples.limb_demo import build_demo
demo = build_demo()  # 既存シーンをクリアせずrigを追加
rig = demo['rig']
```

```python
from maya import cmds
controls = rig.controls()
cmds.setAttr(controls['target'] + '.translate', 0, 2, 0)
cmds.setAttr(controls['target'] + '.softness', 1)
rig.match_fk()
rig.set_mode('fk')

# シーン再読込後。メッセージ接続なので生成ノードの名前変更に追従します。
from hrig.limb import LimbRig
rig = LimbRig('rig')
```

`build_limb`のコントローラーはtransformで、`build_demo`では表示用カーブを追加します。
モードとLODは構成階層のチャンネル操作またはメソッドで変更します。
内部属性hrigMode/hrigLodを直接編集しても接続は更新されません。
IKへの姿勢合わせは `match_ik()` を使います。Soft IKで完全に伸び切った姿勢は
有限距離へ逆算できないため拒否します。LOD 0にして合わせるか、少し曲げてください。
非一様スケール・シアー・負スケールを含む部位は対応対象外です。

## 定義とバックエンド

`JointSpec`、`LayerSpec`、`RigDefinition` はMayaなしで保存・検証できます。
親空間の位置を保持し、`to_data()` / `from_data()` でJSON化します。
骨やレイヤーの循環・重複・依存欠落を拒否します。汎用定義が受け付ける種類と、
最小ビルダーが実装する種類は別です。未対応の構成は構築時に拒否します。

```python
rig.set_backend('standard') # 標準ノードへ交換（既存Bifrost/C++リグも対象）
rig.set_backend('cpp')      # Soft IK部分のみ交換。骨やスキンは保持
rig.set_backend('bifrost')
# 初めからC++版を利用する場合（この経路ではBifrostをロードしない）
# rig = hrig.build_limb(hrig.limb_definition('otherLimb'), backend='cpp')
```

既定のSoft IKは`condition`・`plusMinusAverage`・`multiplyDivide`（累乗）で計算し、
標準の`container`で演算ノードをまとめます。距離0・softness0ではゼロ除算を避け、
softness0は通常の到達距離制限として扱います。FK/Lowでは出力の利用経路を外します。
既存シーンは自動変換しません。`rig.set_backend("standard")`でSoft IKのみ交換できます。

任意のBifrost版にはhlib_bifrostとBifrost 3.0.0.0以上が必要です。
C++版のビルドはリポジトリルートで実行します。

```powershell
& 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' tools/build_maya_plugin.py maya/inhouse/hrig/cpp --versions 2025 2027
```

専用ノードは `hrigSoftIK`、バイナリは `release/plug-ins/windows/<年>/hrigNodes.mll`
です。Git対象外で、使用するMaya版ごとにビルドします。
Soft IKのノードID `0x0007F101` と行列追従 `hrigMatrixFollow` の `0x0007F102` は開発用です。組織外配布・本番アセット化の前に登録済みIDへ
置換する必要があります。MayaのSecurityが拒否した場合、設定を自動変更しません。
このプラグインはhrigが所有し、hlibには実装・同梱しません。

## ツイスト補助骨レイヤー

デモでは、root→midとmid→tipの2区間にそれぞれ3本のツイスト補助骨を生成します。
本数は両端の既存骨を含まず、N本なら各骨を`i / (N + 1)`の位置へ配置し、
同じ割合で相対ツイストを分配します。3本・終点90度なら、25/50/75%の位置に
22.5/45/67.5度の回転となります。

```python
from hrig.examples.limb_demo import build_demo
demo = build_demo(twist_count=4)  # 各区間4本。0ならツイスト骨を作らない
```

任意の2骨を指定して区間を追加する場合は、バインド前に次のように構築します。

```python
import hrig
rig = hrig.build_limb()
root, mid, tip = rig.joints()[:3]
rig.add_twist("upper", root, mid, count=3, axis="x")
rig.add_twist("lower", mid, tip, count=5, axis="x")
rig.set_twist_count("upper", 4)  # 未使用の骨を再生成。0なら区間を削除
print(rig.twist_joints("upper"))
rig.set_layer_enabled("twist", False)
```

`axis`は始点骨のローカル長手軸（x/y/z）。生成時に両端がその軸に沿っていることを
確認します。標準ノードでQuaternionの軸成分を抽出するため、終点の曲げ角をそのまま
ツイストへ混ぜません。補助骨は始点の下の区間グループに兄弟として配置し、
`offsetParentMatrix`で駆動します。直列階層による回転の累積は行いません。

アウトライナーの`limb_module_twist_layer`で`Enabled`を操作できます。
Full LODで有効、Low LODでは出力接続を外して基準位置・ツイスト0で始点に追従し、
補助骨表示を隠します。FK/IKの両方で利用できます。各区間グループの`Count`は
読み取り専用です。構築データと接続はシーンに保存されます。

高詳細メッシュのバインドには登録済みツイスト骨を含め、proxyは基本3骨だけで
バインドします。LOD変更だけで高詳細スキンのinfluenceを取り除くことはしません。
スキン計算を軽くする場合は既存のメッシュLOD切替も併用してください。
バインド後に追加した骨のinfluence追加・ウェイト設定は自動では行いません。
スキンや外部ノードが使用中の骨は本数変更・削除を拒否し、ウェイトを保護します。

回転は最短経路です。180度境界をまたぐ連続回転や複数回転の蓄積には未対応です。
長手軸に直交する180度曲げは分解が不定なのでツイスト0とします。
軸の自動推定、骨の曲げに合わせた再Aim、ボリューム補正は含みません。

## ペアレント・空間切替レイヤー

新規リグには`limb_module_space_layer`と`limb_space_layer_set`を追加します。
標準チャンネルボックスで各コントローラーの`Space`を変更できます。

| コントローラー | 選択肢 | 意味 |
| --- | --- | --- |
| `ik_ctrl` | local / world | 部位の操作グループに追従 / ワールド固定 |
| `pole_ctrl` | local / world / foot | 部位に追従 / ワールド固定 / IKコントローラーに追従 |

`foot`はIKコントローラーの移動・回転に追従し、heel/toe/ballのロール用ピボットには
追従しません。切替直後のワールド姿勢とコントローラーのローカルチャンネルを保持します。
空間レイヤーは基準座標系なのでFK/IK・LODから独立して常時有効です。

```python
rig = demo["rig"]
rig.set_space("ik", "world")
rig.set_space("pole", "foot")

# 任意のtransformも指定可能。参照ノードはリグの所有物にはしません。
rig.add_space("ik", "chest", "chest_ctrl")
rig.set_space("ik", "chest")
print(rig.space_switch("ik").labels())
print(rig.space_switch("ik").current())
```

共通実装は`hrig.setups.SpaceSwitch`で、標準`choice`・`multMatrix`を使います。
IK目標のローカル行列合成に空間レイヤー分を追加し、Soft IK・リバースフットへは
引き続き部位空間で渡します。ワールドとの変換は参照空間をまたぐ部分に限定します。
自己・子孫・通常のDG依存による循環と、自分の部位の変形骨／計算階層への追従は拒否します。

現在の切替は停止中の構成操作です。`Space`へキーや式を接続する使い方、再生中の
空間切替アニメーションは未対応です。新しい空間への切替時にオフセットを更新するため、
アニメーション済みの場合は他フレームにも影響します。保存済みの旧リグは自動拡張せず、
このレイヤーを利用する場合は新しいコードで構築してください。

## リバースフット

```python
from hrig.reverse_foot import add_reverse_foot
add_reverse_foot(rig, heel=(-1, 0, 0), toe=(2, 0, 0), ball=(1, 0, 0))
cmds.setAttr(rig.controls()['target'] + '.ballRoll', 30)
```

位置はIK目標を原点とするローカル座標、回転軸はZです。LOD 1のみ有効で、
足ロールが非ゼロの状態からのIKマッチは拒否します。後付け設定はシーンの
`hrigFootSettings` に保存します。基本RigDefinitionのJSONだけでは足設定を復元しません。

## スキンと軽量モデル

`hrig.skin.bind_mesh` で未スキニングのモデルをバインドできます。
`create_skin_lod` は別に用意した軽量モデルへウェイトを近似転送し、補助骨を
含まないスキンを作ります。基準姿勢で実行してください。
`set_mesh_lod` は表示とskinClusterのenvelope/nodeStateを切り替えます。
skinClusterはBlocking非対応のため、無効側はHas No Effectとenvelope=0を使用します。
メッシュの自動削減や、スキン以外の変形履歴全体の停止は実装していません。

## アニメーション取り込み

```python
from hrig.animation import bake_source
bake_source(rig, ['sourceRoot', 'sourceMid', 'sourceTip'], 1, 24, mode='fk')
```

FBXやHumanIKで用意した外部の受け側骨を、FKコントローラーへベイクできます。
`mode='ik'` はFKキーも保持してIKへ変換します。IKでは根元位置と骨長の一致が必要です。
異なる骨格比率の自動補正、Spline IKへの変換、足接地補正は含みません。
指定範囲の既存キーを置換するため、作業用リグで実行してください。

## 検証

GUIへ送信せず、隔離したmayapyプロセスで実行します。テストはシーンを初期化します。

```powershell
& 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' tools/test_rig_packages.py --suite standard
# 任意バックエンドを含める場合
& 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' tools/test_rig_packages.py --suite all
& 'C:/Program Files/Autodesk/Maya2025/bin/mayapy.exe' tools/test_rig_packages.py --suite native
& 'C:/Program Files/Autodesk/Maya2022/bin/mayapy.exe' tools/test_rig_packages.py --suite hlib
```

バックエンド交換テストにはビルド済みC++プラグインが必要です。
計測用の汎用入口は `hlib.utils.evaluation.measure` です。入力を変更して出力を
評価する操作を渡してください。キャッシュの読み取りだけではリグ評価時間になりません。

## 開発時の共通ルール

Pythonの書式・日本語Google形式docstringはhlibに合わせます。
詳細は [hrig実装ルール](../../../docs/hrig-development.md) を参照してください。

ノード生成・属性・接続・行列の操作にはhlibの公開APIを使用します。
GUI監視は `hlib.general.ScriptJobs`、変更があるときだけ行う状態表示の更新は
`Plug.set_if_changed()` を使用します。FK/IKやLODの判断、リグの再探索はhrig側の責務です。
IKハンドル構築、スキン作成・ウェイト転送、プリミティブ作成などにはMaya専用コマンドを使用します。

## 肘・膝の曲げ補助レイヤー

`build_demo()` は、ツイスト骨に加えて肘の補間骨・内側骨・外側骨を生成します。
`build_demo(bend_helpers=False)` で省略できます。標準ノードのみで評価します。

```text
root_jnt（上腕・大腿）
├─ mid_jnt（肘・膝） → tip_jnt
└─ limb_bend_layer_elbow_grp（設定）
   └─ limb_bend_layer_elbow_half_jnt（回転50%）
      ├─ limb_bend_layer_elbow_inner_jnt
      └─ limb_bend_layer_elbow_outer_jnt
```

補間骨は肘膝の位置に配置し、生成時の回転から現在の回転へ50%補間します。
曲がる関節自身の子には置かず、上腕・大腿側の子にすることで回転の二重加算を防ぎます。
子の内外骨は指定したローカル軸上に配置し、曲げ量に応じて別々に押し引きします。

```python
from hrig import build_limb

rig = build_limb()
half, inner, outer = rig.add_bend("knee", bend_axis="z", push_axis="y")
settings = rig.bend_settings("knee")
settings.plug("rotationRatio").set(0.5)
settings.plug("referenceAngle").set(90)  # 度。ここで補正量100%
settings.plug("innerRest").set(0.5)
settings.plug("outerRest").set(-0.5)
settings.plug("innerPush").set(-0.2)
settings.plug("outerPush").set(-0.3)
rig.set_layer_enabled("bend", False)
```

- `rotationRatio`: 基準からの回転追従割合。0〜1、既定0.5。
- `referenceAngle`: 補正量が100%になる角度。既定90度。
- `bendSign`: 正方向の曲げは1、負方向の曲げは-1。
- `innerRest` / `outerRest`: 内外骨の基準位置。現在のシーン距離単位。
- `innerPush` / `outerPush`: 100%曲げたときの移動量。符号で押し引きを反転。

移動位置は `Rest + Push * clamp(曲げ角度 * bendSign / referenceAngle, 0, 1)` です。
反対方向の曲げでは補正0、基準角度以上では補正100%に留めます。
「内側」「外側」の空間判定は自動ではありません。骨の向きに合わせてRestとPushの符号を指定します。
デモはPoleが+Y・曲げが-Zなので、bendSign=-1、内側-Y・外側+Yに設定しています。

アウトライナーの `limb_module_bend_layer` の **Enabled** で切り替え、**Active** で状態を確認します。
各設定は `limb_bend_layer_elbow_grp` を選択してチャンネルボックスから編集できます。
Full LODで有効、Low LODまたは無効時には3本の評価出力を切断して基準姿勢に戻します。
曲げの追従と押し引きはDGが評価するため、フレームごとのPython実行は不要です。

高詳細スキンは補助3骨も含み、proxyは基本3骨のみです。レイヤー無効化だけでは高詳細スキンの
influence数は減りません。スキン負荷を下げる場合はメッシュLODも切り替えます。
既存の単純helperレイヤーは保持しています。新しい補正だけを使う場合はhelperを無効にできます。
骨の追加はバインド前に行ってください。既存のスキンへの追加やウェイト調整は自動ではありません。

単一軸のヒンジ曲げを対象とし、多軸回転の解剖学的な曲げ抽出や180度を越える連続回転、
負スケール・シアーは対象外です。設定は構築・調整用で、切替アニメーションには対応しません。
既存シーンを自動変更する処理はありません。新しいデモを生成して利用してください。

## モジュール・レイヤーエディター

MayaのPythonから開きます。同じウィンドウを再利用します。

```python
import hrig
hrig.show_layer_editor()
```

HToolsメニューを再構築した場合は、Riggingの`hrigLayerEditor`からも起動できます。
Maya 2025以降の同梱PySideを使用します。

1. モジュール名を入力して「＋ 作成」。基本3関節FK/IK、メッシュ付きデモ、4/8方向スカート、背骨・尻尾Spline、指、首・視線を選べます。
2. モジュールの行を選び、サンプルレイヤーを選択して「＋ 追加」。
3. 左のチェックで使用設定を変更。右の「評価中／停止」はMode・LODも反映した状態です。
4. 子行を選び「シーンで選択」で設定ノードを選択。「SDKカーブ」で標準グラフエディターを開きます。

モジュールをフォルダー、機能をレイヤー行として表示します。ツイスト・肘膝・SDKの各サンプルは
その下に子行で並びます。同種サンプルのEnabledは機能行でまとめて制御します。
FK/IKと空間レイヤーは必須構成のためチェックで削除せず、上部のModeでFK/IKを切り替えます。
Soft IKと基本補助骨は基本モジュールに含まれ、「追加」は有効化です。
リバースフットは1モジュールにつき1つで、重複追加は拒否します。

Undo/Redo・シーン読込・Mode/LOD/Enabled変更を表示へ反映します。外部スクリプトで
モジュールを追加・削除した場合は「更新」で一覧を取得できます。閉じるとUI所有の監視だけを解除します。
ドラッグによる評価順の並べ替え、レイヤー削除、ブレンド不透明度、ドッキングは未対応です。
モジュールは独立した部位で、複数部位を1キャラクターへ接続するUIではありません。
既存シーンの古いモジュール構造を自動移行しません。新しいサンプルを作成して利用してください。

## Swing / Twistドリブンキーレイヤー

ジョイントのローカル回転をSwingとTwistへ分解し、その1成分から単一属性をSDKで駆動します。
分解は`hrig.setups.SwingTwist`、SDK生成は既存の`hlib.general.DrivenKey`を使用します。

```python
import hlib
from hrig import build_limb

rig = build_limb()
# 入力骨へ依存を戻さない、独立した補正先を用意する
corrective = hlib.createNode("transform", name="corrective")
graph = rig.add_driven(
    "elbowPush", rig.joints()[1], corrective.plug("translateY"),
    component="swingZ", axis="x",
    keys=[(-90, -1), (0, 0), (90, 1)],
)
rig.set_layer_enabled("driven", False)
```

`axis`はTwistの長手軸、`component`は`twist`または`swingX/Y/Z`です。
Swing成分はTwist除去後のXYZ Euler角です。生成時の姿勢をゼロとし、入力キーは常に度、
出力キーは駆動先の現在のUI単位で指定します。曲線は通常のanimCurveで、接線やキーは
Mayaのグラフエディターから編集できます。デフォルトは線形補間です。

UIのSDKサンプルでは、中間関節の分解角から新しいサンプル骨のtranslateYを駆動します。
入力成分とTwist軸を追加前に選択できます。任意の駆動先への接続は上記Python APIを使います。
現在姿勢がゼロ基準となるため、基準にしたい姿勢で追加してください。

Full LODかつEnabledのときだけ出力を接続し、無効時は駆動先を作成前の値へ戻します。
駆動先が既存接続を持つ場合は上書きせず拒否します。主関節・コントロールや入力側への
循環を作る用途には使用しないでください。独立した補正用ノード向けです。
生成した分解・SDK・単位変換はリグの所有物ですが、APIで指定した外部の駆動先は削除しません。
サンプル骨は既存スキンへ自動追加しません。

最短回転を扱い、180度境界・複数回転・SwingのEuler特異点で連続性を保証しません。
キーを時間に沿って切り替えるレイヤーアニメーションや、既存SDKとの自動合成は未対応です。

## スカートの方向ブレンドモジュール

円周の多数の骨列を、4方向または8方向のドライバー骨列で操作します。
標準parentConstraintの回転のみを使用し、各列の骨長を維持します。
Bifrost・専用C++プラグインは不要です。

```python
from hrig import build_skirt

rig = build_skirt(
    name="skirt01", driver_count=4, chain_count=16,
    joints_per_chain=3, radius=3, length=5,
)
rig.driver_chains()[0][0].plug("rotateX").set(30)
rig.root.plug("blend").set(0.8)
rig.root.plug("falloff").set(1.5)
skin_joints = rig.joints()  # ドライバーを含まない変形骨だけ
```

Y上向き・XZ円周、骨列は下向きです。方向0は+X、番号順に+Zへ回り、各列の
ローカルXは外向き、-Yは長手方向です。寸法は作成時のシーン単位を使います。
ドライバーは黄色い円形状の付いたジョイントで、回転を操作します。
中間の骨も同じ段のドライバー骨から制御されます。

方向ウェイトは作成時の方向を挟む二方向に限定します。正弦則による方向ベクトルの
比率を使い、円周の最後と最初も連続します。姿勢の変化によって担当方向は変わりません。
各ターゲットの初期差分を保持するので、ウェイトを変えても静止姿勢は崩れません。

| ルートの設定 | 動作 |
| --- | --- |
| `blend` | 0=作成時の基準姿勢、1=ドライバーへ全追従。アニメーション可 |
| `falloff` | 1=方向比率。大きいほど近い方向へ集中、小さいほど隣接二方向が均等。0.1〜8 |
| `enabled` | 放射状制御の使用設定。構成変更用 |
| `lod` | Fullで評価、Lowで出力接続を外して基準姿勢へ戻す。構成変更用 |

Layer Editorで「スカート · 4方向／8方向」を選ぶと、列数・各列の骨数・半径・長さを
指定できます。「方向ブレンド」のチェックで使用設定を変更します。その行を選んで
「シーンで選択」を押すと、Channel BoxでBlend/Falloffを調整できます。
ドライバー・変形骨・基準姿勢はそれぞれOutlinerのグループにまとめます。
スカートにはFK/IKや肘膝サンプル追加を適用しないため、それらのUI操作は無効になります。

GUIでは既存のhrig起動処理が属性監視を復元します。バッチでは設定変更時に
`rig.set_layer_enabled("radial", False)` / `rig.set_lod(0)`を使ってください。
Enabled/LODはキーによる切替には使わず、連続した影響量にはBlendを使用します。
無効時はconstraint出力を切断してnodeStateをBlockingにします。
Blend=0だけでは出力接続を切らないため、LODの評価停止と同じではありません。

骨数と方向数は生成時に指定します。既存骨への後付け、非円形の配置、スキンの自動作成、
衝突・布シミュレーションは含みません。骨数変更は未バインド状態で作り直してください。
`rig.delete()`はスキンに使用中なら拒否します。複数回転の蓄積、180度境界の連続性、
負・非一様スケールは保証しません。constraint内部にはワールド空間計算があり、
完全なローカル行列評価ではありません。実制作モデルでの速度・ウェイト品質は別途評価が必要です。

## 回転追従補助骨レイヤー

Twistのみ、Swingのみ、全回転の割合追従を追加できます。計算は
`hrig.setups.RotationFollow`へ共通化し、標準ノードのQuaternion補間を使います。

```python
from hrig import build_limb

rig = build_limb()
rig.add_follow("twistOnly", mode="twist", axis="x", ratio=1.0)
rig.add_follow("swingOnly", mode="swing", axis="x", ratio=1.0)
rig.add_follow("half", mode="full", ratio=0.5)
rig.follow_settings("half").plug("ratio").set(0.25)
rig.set_layer_enabled("follow", False)
```

入力骨を省略すると腕脚は中間骨、スカートは先頭ドライバーの根元を使用します。
`joint=rig.driver_chains()[2][1]`のように、モジュール配下の任意の骨も指定できます。
スカートの長手軸はYなので、Twist/Swingでは`axis="y"`を指定します。

各サンプルは入力骨と同じ親空間に設定グループと補助骨を生成します。
入力の作成時の姿勢を基準とし、位置は全追従、回転だけを割合で追従します。
親から継承する回転には割合を掛けません。補助骨から入力へは接続しません。
このAPIは新しい補助骨を作る機能で、既存骨の接続を差し替えるものではありません。

Layer Editorの「サンプルレイヤーを追加」に以下を追加しています。

| サンプル | 動作 |
| --- | --- |
| Twistのみ追従 | 指定した長手軸のひねりだけを追従 |
| Swingのみ追従 | 長手軸のひねりを取り除いた傾きだけを追従 |
| 回転の割合追従 | 全回転の差分を追従。50%で半回転追従 |

軸と割合（0〜100%）を指定して追加します。3種類とも初期の割合欄は50%です。
作成後は「回転追従補助骨」の子行を選び、「シーンで選択」でChannel Boxへ移動します。
`ratio`はアニメーション可能、`followMode`はFull/Twist/Swingの成分選択です。
同じモジュール内の追従骨を1つの使用チェックで管理します。サンプルごとの個別Enabledはありません。

Full LODかつEnabledで評価し、無効時はOPM出力を切断して作成時の位置・回転へ戻します。
`rig.joints()`は追従骨も含み、`rig.follow_joints()`は追従骨だけを返します。
既存スキンには自動追加しません。新しい表示レイヤーを持たない旧腕脚シーンでは、
新規モジュールでの利用を推奨します（Python APIの追加・制御は可能）。
180度境界・多回転・負または非一様scale・shearの連続追従は保証しません。

## 揺れ物とポーズ補正レイヤー

スカートの任意のドライバー列に、揺れ物と複数入力RBFポーズ補正を追加できます。
元の手付け骨を入力として保持し、別の出力骨列を方向ブレンドへ渡します。
再生時は標準ノードのみで、Bifrost・独自プラグインには依存しません。

Layer Editorでスカートを選び、「サンプルレイヤーを追加」から
「揺れ物（ベイク）」または「ポーズ補正（RBF）」を追加します。
サンプルの対象は先頭ドライバー列です。まず元の骨に回転キーを設定し、
揺れを追加してください。後から変更した場合は「揺れを再ベイク（再生範囲）」を押します。
ドライバーの子行を選んで再ベイクすると、その列が対象になります。

```python
from hrig import build_skirt

rig = build_skirt()
# rig.driver_chains()[0] の骨に回転アニメーションを設定してから実行する
settings = rig.bake_spring(driver_index=0, start=1, end=120)
settings.plug("intensity").set(0.5)
rig.set_layer_enabled("spring", False)
```

揺れはローカルEuler回転を各軸の減衰ばねで計算し、animCurveへベイクする方式です。
元のアニメーションは書き換えません。フレームを逆順に移動しても同じ結果になります。
設定グループの`frequency`（Hz）、`damping`（減衰比）、`angleLimit`（度）で調整します。
元のキー・これらの設定・FPSを変えた場合は再ベイクが必要です。自動更新はしません。
`intensity`は再ベイク不要でアニメーションできます。
整数フレームをサンプルし、間は線形補間、範囲外は端のベイク値を保持します。
静止入力には揺れは発生しません。親の移動だけによる慣性、ライブ物理、重力、衝突は未対応です。

ポーズ補正はライブ評価です。`rig.add_pose_correction(driver_index, drivers, poses, values, scales)`
で登録します。入力は同じスカート内の元ドライバー骨のrotateX/Y/Z、登録値は度です。
valuesの各行は、対象列の各骨のXYZ回転補正を順に並べた配列（骨数×3要素）です。
ローカル回転に補正を合成し、`poseIntensity`で影響量を調整できます。
戻り値の`PoseRbf.set_values(values)`で登録補正値を編集できます。
`graph.set_data(poses, values, scales)`で登録の追加・削除・編集ができます。
外部入出力とcontainerは維持し、内部計算ノードだけ再構築します。

UIサンプルは根元のX/Z回転が0度／60度の4組を入力とし、根元へ最大25度の補正を加えます。
RBFは登録点で指定値に一致しますが、中間で負値やオーバーシュートが出る場合があります。
離れた入力では補正が0に近づきます。自動的な体積保持やスキン修正ではありません。

揺れとポーズ補正はそれぞれの使用チェックとLODで切り替えられます。
無効な出力は切断し、両方無効なら方向ブレンドを元の骨へ戻します。
強度0だけでは計算接続を切りません。設定切替はアニメーションキーではなく構成変更用です。
初版の統合対象はスカートのみです。出力骨は内部計算用で、スキンの対象骨には追加しません。
実制作モデルでの性能、非一様scale、多回転の連続性は未検証です。

## 背骨・尻尾のSpline IKモジュール

Layer Editorの新規モジュールから「背骨 · Spline IK」「尻尾 · Spline IK」を選び、
骨数（末端を含む3〜64本）、コントロール数（4〜32個）、全長を指定して作成します。
背骨は+Y、尻尾は+Zへ配置します。作成後はモジュールルートで配置・向きを変更できます。

```python
from hrig import build_spline, show_layer_editor

rig = build_spline("tail01", joint_count=12, control_count=5, length=15, axis="z")
rig.controls()[1].plug("translateX").set(2)
# スキンに使用するのは rig.joints() の変形骨
show_layer_editor()
```

OutlinerではFK、IK計算骨、カーブコントロール、変形骨、内部セットアップを
グループ分けします。FK骨とカーブコントロールには円形の操作シェイプがあります。
Layer Editorの子行を選び「シーンで選択」で対象コントロールを選択できます。
カーブ用コントロールは独立配置で、移動がCVへ反映されます。
中間コントロールは移動のみ、両端は回転でもひねりを調整できます。
カーブは内部CVの位置を必ず通るものではありません。

初期状態は骨長固定の標準ikSplineSolverを使用し、Bifrostや外部プラグインは不要です。
曲線が骨列より長くなると先端の骨は最後のコントロールに届きません。
伸縮と体積補正は後述の任意レイヤーで追加します。極端に短い曲線での挙動は保証しません。
CV位置は行列でカーブ空間へ変換しますが、IKソルバーにはワールド空間のカーブを渡します。

ルートのChannel Boxには`mode`（FK/SplineIK）、`lod`（Low/Full）、`enabled`があります。
FK選択、Low LOD、Splineレイヤー無効時はSpline IKのinCurveを切断してソルバーを停止し、
変形骨をFK骨列へ接続します。これらはキーでアニメーションする属性ではありません。
バッチでは`rig.set_mode("fk")`、`rig.set_lod(0)`、
`rig.set_layer_enabled("spline", False)`の明示APIを使ってください。

Layer EditorからIK→FKへ切り替える場合は、現在姿勢をFKへコピーしてから切り替えます。
Pythonでは`rig.match_fk()`→`rig.set_mode("fk")`の順で実行できます。
FKへのキー自動作成は行いません。FKが既に入力接続・キーで駆動されている場合は
姿勢コピーを拒否することがあります。Channel Box・Enabled・LOD切替では姿勢コピーしません。
FK→Spline IKはLayer Editorからの切り替え時に近似フィットし、最大位置誤差を表示します。
Pythonでは`error = rig.match_ik(tolerance=None)`→`rig.set_mode("ik")`を使用します。
`match_ik`自身はモードを維持し、実際のIK評価との最大位置差を現在の距離単位で返します。
`tolerance`を指定すると超過時は変更をUndoして拒否します。
カーブの制御点はFK関節の折れ線へ最小二乗で近似し、両端Up方向を合わせます。
少ないCV・鋭い折れ・中間Twist・断面scaleは完全に再現できません。
Full LODとSpline使用設定が必要で、キーの自動作成は行いません。

骨数やコントロール数は作成時指定です。作成後の本数変更、既存骨への後付け、
スキン自動作成は対象外です。伸縮とTweakは独立レイヤーとして追加できます。
`rig.delete()`は所有ノードを削除しますが、変形骨がスキン使用中なら拒否します。
負・非一様scale、shear、接線と上方向が平行になる姿勢、多回転の連続性、
実制作モデルでの性能は保証していません。初版では正の均等scaleを使用してください。

単位をmにした検証では、既存hlibの`plug("scale").set(...)`がtranslateを
再変換する問題を確認しています（今回のSpline機能とは別の未修正箇所）。
ルートのスケールはChannel Box、または`scaleX/Y/Z`を個別に設定してください。

## 伸縮・体積補正レイヤー（腕・脚・Spline）

Layer Editorで腕脚または背骨・尻尾モジュールを選び、
「サンプルレイヤーを追加」→「伸縮・体積補正」を追加します。
設定行を選択して「シーンで選択」を押すとChannel Boxで調整できます。
Pythonでは両モジュールとも次のAPIを使います。

```python
settings = rig.add_stretch()
settings.plug("stretch").set(1.0)
settings.plug("squash").set(0.5)
settings.plug("volume").set(1.0)
settings.plug("maxStretch").set(2.0)
rig.set_layer_enabled("stretch", False)
```

| 設定 | 意味 | 初期値 |
| --- | --- | --- |
| stretch | 伸長の影響量。0〜1 | 1 |
| squash | 圧縮の影響量。0〜1 | 腕脚0、Spline1 |
| volume | 横2軸の体積補正量。0〜1 | 1 |
| minSquash | 最小長さ倍率 | 0.1 |
| maxStretch | 最大長さ倍率 | 2 |

腕脚では部位空間のIK目標距離、Splineではローカルカーブの長さを測ります。
骨同士の基準長比率を保ったまま伸縮します。最大2なら元の全長の2倍までです。
腕脚のsquashは通常の肘膝の曲げを維持するため0から開始します。
1にすると、短い目標距離に骨列全体を合わせるため、肘膝が伸びた姿勢に近づきます。
Splineは弧長による近似なので、強い曲げでは末端位置が最後のcontrolに厳密一致しません。

横倍率は長さ倍率の逆平方根から計算し、volumeで強さを調整します。
親の横倍率を子へ累積させないよう補償します。これは棒状断面の体積近似で、
メッシュ体積・関節の潰れ・ウェイト品質を保証するものではありません。
SplineはFK/変形骨のSSCとinverseScaleを設定するため、スキン前に追加してください。
腕脚はOPM内の行列で断面を補償し、スキンウェイトを変更しません。

腕脚ではSoft IKへ渡す距離を伸縮率で正規化し、Soft IKと重ねて使えます。
Soft IK有効時は柔らかい到達挙動を維持するため、目標位置より手前になります。
腕脚のFK→IK合わせでは伸縮とSoft IKの合成距離を逆算します。
到達上限を超える姿勢は拒否します。任意のFK骨長配分をIKへ完全変換するものではありません。
IK→FKでは伸縮・断面を含む現在姿勢をコピーします。SplineのFK→IKは前述の近似フィットを使用します。

このレイヤーはIKモードかつFull LODで評価します。使用チェックを外すかLow/FKにすると
長さ計算の入力と骨への出力を切断し、IK骨を追加時の長さへ戻します。
FKへ姿勢コピー済みなら、そのFK姿勢は保持します。strength=0は連続調整用で、
レイヤー無効化と同じ計算停止ではありません。設定値にはキーを付けられますが、
使用チェック・Mode・LODは構成切替用です。

共通の比率計算は`hrig.setups.LengthCompensation`へ実装しています。
標準ノードのみで再生し、Bifrost・mGear・外部プラグインへ依存しません。
負・非一様scale、shear、極端な圧縮、実制作メッシュでの性能・変形品質は未検証です。


## 上部hrigメニュー（仮）

ワークスペースのMaya 2025以降の起動時に、メニューバーへ **hrig** が追加されます。
「レイヤーエディタを開く」「サンプル作成」「選択スカートのポーズ補正を編集」
「選択骨へ局所Tweakを追加」を使用できます。再登録しても重複しません。
現在起動中のMayaへ手動で追加する場合:

```python
from hrig.menu import Menu
Menu.install()
```

## 指Curl / Spread、首・視線Aim、局所Tweak

Layer Editorの新規モジュールに「指 · Curl / Spread」「首・視線 · Aim」があります。
いずれもMaya標準ノードだけを使用し、rootの`enabled`と`lod`、UIの使用チェックで
追加回転の接続を停止できます。手付けFKの値は維持します。
これらは構成切り替えであり、キー付きの連続ブレンドではありません。

```python
from hrig.fingerRig import FingerRig
from hrig.aimRig import AimRig
from hrig.tweakLayer import TweakLayer

hand = FingerRig.create("hand01", finger_count=5, joint_count=3, length=3, spacing=1)
look = AimRig.create("look01", size=2)
control = TweakLayer(hand).add("tip", hand.joints()[-1])
```

- **指**: 正Xへ伸びる平行な指列。各列は操作関節＋末端骨で構成します。
  レイヤー設定グループの`curl`（全体）、`curl1..`（個別加算）、
  `curlWeight1_1..`（関節別割合）でZ曲げ、`spread`と`spreadWeight1..`で根元Y開きを制御します。
  別階層の各FKコントロールで追加回転できます。角度はMayaの表示単位です。
  親指の向き・手のひら・解剖学的配置の自動生成は含みません。
- **首・視線**: 首と左右眼を作り、正Zを視線、正YをUpとします。
  各`target_ctrl`で注視点、`up_ctrl`で上方向、FK controlで追加回転を操作します。
  首の子に左右眼があり、ターゲットは共通のレイヤーグループに分離しています。
  AimとUpが平行になる姿勢、目標と原点が一致する姿勢は避けてください。
  Aim constraintはworld空間を使用します。回転のみを追従し、首の伸縮は行いません。
- **Tweak**: 全モジュールの配下jointへ後付けできる局所TRS操作です。
  Layer Editorで「局所Tweak」を追加すると、選択骨（未選択なら先頭変形骨）を使用します。
  各Tweakグループの`enabled`とモジュールLODでOPM入力を切断し、ゼロ姿勢へ戻します。
  元のコントロール値は保持し、再有効化で復帰します。`TweakLayer(rig).joints()`と
  `rig.joints()`に補助骨を含みますが、既存skinClusterへは自動追加しません。
  無効化によってskinClusterのinfluence数が減るわけではありません。
  バッチでグループの`enabled`を直接変更した後は`TweakLayer(rig).update()`を呼びます。

正の一様scaleで使用してください。負・非一様scale、shear、実制作モデルでの性能は未検証です。

## ポーズ補正の登録・編集UI

スカートを選び「ポーズ補正を登録・編集」を開き、補正するドライバー列を選択します。
未登録列はその列の先頭骨のRX/RZを入力として開始します。

1. 基準姿勢で「現在入力で登録」を押し、補正値を0のまま残します。
2. ドライバーを曲げて再度登録し、各骨のXYZ補正角を表へ入力します（度単位）。
3. 「適用」で登録します。2〜64ポーズが必要で、重複・数値不正は拒否します。
4. 選択行の再取得、数値編集、行追加・削除をして再度「適用」できます。

登録済みグラフはAPIで作った入力も読み込めます。入力・出力の次元数は固定です。
入力スケールで補間の広がりを調整します。表の変更は適用するまでシーンに反映せず、
適用は1回のUndoで戻せます。Undo後は「シーンから再読込」で表も更新してください。
列変更・再読込は未適用の表編集を破棄します。
これはスカートの骨回転補正用UIで、Maya標準Pose Editorやメッシュのsculpt編集ではありません。


## 共通ライブラリへの依存

hrigは構成・命名・レイヤー有効状態・LOD・リグの姿勢合わせを担当し、
以下の基礎処理はhlib/hlib_bifrostの公開APIを利用します。

| 処理 | 実装先 |
| --- | --- |
| 計算ノードの所有・追加・列挙 | `hlib.nodes.Container` |
| 保存用message配列 | `hlib.plugs.ArrayPlug.source_nodes / append_message` |
| 操作カーブ | `hrig.setups.ControlShape` |
| 表示単位変換 | `hlib.general.Units` |
| スキンのバインド・最近傍ウェイト転送 | `hlib.nodes.SkinCluster` |
| 標準演算とSoft IK | `hlib.utils.scalarGraph.ScalarGraph / SoftIK` |
| Bifrost基本演算とSoft IK | `hlib_bifrost.utils.MathBuilder` / `hrig.setups.bifrostSoftIK.SoftIK` |

Soft IKは`hrig.setups.SoftIK`、Bifrost版は`hrig.setups.bifrostSoftIK.SoftIK`を使用します。旧互換モジュールは廃止しています。
標準バックエンドの既定値と生成リグの入出力・レイヤー設定は変更していません。
Bifrostは明示指定時だけ使用し、hlib側からhrigに依存しません。

## セットアップの配置

`setups/` はSoft IK、空間切替、Twist分配、曲げ補正、回転追従、円周ウェイト、RBF補正、Spline IK構築、伸縮補正、操作形状を持ちます。標準Maya機能のラッパーはhlib、リグとしての組み方はhrigへ分離しています。

```python
from hrig.setups import SoftIK, SpaceSwitch, SplineIK
from hlib.general import DrivenKey, DrivenKeys
from hlib.utils.scalarGraph import ScalarGraph
```

セットアップの詳しい仕様:

- [space_switch](docs/space_switch.rst)
- [twist_distribution](docs/twist_distribution.rst)
- [bend_correction](docs/bend_correction.rst)
- [swing_twist](docs/swing_twist.rst)
- [radial_weights](docs/radial_weights.rst)
- [rotation_follow](docs/rotation_follow.rst)
- [secondary_motion](docs/secondary_motion.rst)
- [spline_ik](docs/spline_ik.rst)
- [length_compensation](docs/length_compensation.rst)

## Sphinxドキュメント

[ドキュメント目次](docs/index.rst)に機能仕様、[テスト方法](docs/testing.rst)、[テストシーン](docs/test_scenes.rst)、[テスト結果](docs/test_results.rst)をまとめています。hlibと同じテーマ・CSSを使用します。ビルド手順はテスト方法ページを参照してください。
