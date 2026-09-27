# hrig

Maya 2025以降向けのレイヤードリグ検証パッケージです。
現在のビルダーは、正X軸の3関節FK/IK、Soft IK、補助骨1本を対象とします。
本番向けの汎用オートリガーではありません。

## 読み込み

このワークスペースの起動バッチでは `maya/inhouse` が `PYTHONPATH` に
追加されるため、MayaのPythonから次のように読み込めます。

```python
import hrig
rig = hrig.build_limb()  # Bifrost 3.0.0.0以上を必要時にロード
rig.set_mode('ik')
rig.set_lod(1)           # 0: 通常IK・補助骨停止、1: Soft IK・補助骨有効
```

既存シーンをクリアせずに生成します。同名ルートがある場合は拒否します。
同じMayaでもBifrostのバージョンは別に確認します。Bifrost 2.xでは構築できません。
依存はhlib、hlib_bifrost、Maya同梱API、Python標準ライブラリです。

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
│     └─ limb_module_reverse_foot_layer
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
│        ├─ ik_ctrl_ofs → ik_ctrl → reverse_foot_grp → heel_pivot_grp → toe_pivot_grp → ball_pivot_grp
│        └─ pole_ctrl_ofs → pole_ctrl
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
rig.set_backend('cpp')      # Soft IK部分のみ交換。骨やスキンは保持
rig.set_backend('bifrost')
# 初めからC++版を利用する場合（この経路ではBifrostをロードしない）
# rig = hrig.build_limb(hrig.limb_definition('otherLimb'), backend='cpp')
```

C++版のビルドはリポジトリルートで実行します。

```powershell
& 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' tools/build_maya_plugin.py maya/inhouse/hrig/cpp --versions 2025 2027
```

専用ノードは `hrigSoftIK`、バイナリは `release/plug-ins/windows/<年>/hrigNodes.mll`
です。Git対象外で、使用するMaya版ごとにビルドします。
ノードID `0x0007F101` は開発用です。組織外配布・本番アセット化の前に登録済みIDへ
置換する必要があります。MayaのSecurityが拒否した場合、設定を自動変更しません。
このプラグインはhrigが所有し、hlibには実装・同梱しません。

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
GUI監視は `hlib.events.ScriptJobs`、変更があるときだけ行う状態表示の更新は
`Plug.set_if_changed()` を使用します。FK/IKやLODの判断、リグの再探索はhrig側の責務です。
IKハンドル構築、スキン作成・ウェイト転送、プリミティブ作成などにはMaya専用コマンドを使用します。
