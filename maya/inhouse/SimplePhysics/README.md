# Simple Physics

Mayaでボーンの揺れを調整するPython API 2.0プラグインです。Kawaii Physicsの主要な設定名とカテゴリを参考にし、入力アニメーションから別の出力ジョイント階層を生成します。実装は`mlib`から独立しています。現在のバージョンは0.1.0です。

## 起動

このワークスペースのMaya起動バッチで起動し、HToolsの`phsycs > simplePhysics`を実行します。Script EditorのPythonからも開けます。

```python
import simplePhysics
simplePhysics.show()
```

`maya/modules/SimplePhysics.mod`がスクリプトとプラグインのパスを追加します。画面を開いただけでは計算プラグインをロードせず、セットアップ作成時に`simplePhysicsNode.py`をロードします。SafeModeで拒否される環境では、利用者がMayaのPreferences > Securityでこのプラグインの場所を確認してください。セキュリティ設定はスクリプトから変更しません。

別環境に導入する場合は`SimplePhysics`フォルダを配置し、その場所を指す`.mod`をMayaが検索するmodulesフォルダへ置きます。外部KawaiiPhysics・UnrealEngineサブモジュール、UE本体、C++ビルドは実行時に不要です。

## 設定手順

1. 揺らすチェーンの根元ジョイントを選択し、**Root Bones > 選択から**で登録します。複数の独立した根元を同時に登録できます。
2. 対象外の枝があれば**Exclude Bones**へ登録します。そのジョイント以下の子孫を除外します。
3. 末端にも回転を付けたい場合は**Dummy Bone Length**を設定します。末端ローカル軸は**Bone Forward Axis**で指定します。
4. **Create Simple Physics**でSolverと緑の出力ジョイントを作成します。根元位置は入力に固定され、その先の位置が揺れます。出力の回転は揺れた子の方向を向きます。
5. 再生しながら**Physics Settings**と**Physics Settings Curves**で調整します。
6. **Collision Limits**から球・カプセル・平面を追加し、ガイドを移動・回転します。Channel Boxの`physicsRadius`と`physicsHeight`で寸法を調整します。追従先に入力ジョイントを選択しておくと、その子にガイドを作成します。
7. 必要なら出力ジョイント2本を選び、**Bone Constraints**で距離拘束を追加します。複数チェーンを結ぶ用途にも使えます。
8. シーンを保存すると設定・カーブ・接続・コライダーが保存されます。納品用には**Bake to New Joints**で別のキー付き階層へベイクします。

元のジョイント、キー、スキンウェイトは変更しません。メッシュを揺らすには出力階層にバインドするか、既存パイプラインで出力／ベイク階層へウェイトを移してください。既存スキンの自動付け替えは行いません。出力のTRSは計算結果を保つためロックしています。

## 設定

| 項目 | 意味 |
| --- | --- |
| Alpha / Blend | 入力とシミュレーションのブレンド。0で入力、1で全適用 |
| Damping | 速度の減衰。0で減衰なし、1で前ステップの速度を除去 |
| Stiffness | 入力ポーズ方向へ戻す強さ。0で復元なし、1で入力方向へ強く復元 |
| World Damping Location / Rotation | 根元移動・回転に対する遅れ。0で追従、1でワールド位置を保とうとする |
| Radius | ボーン位置の球半径。cm |
| Limit Angle | 各親子の入力方向からの最大角度。度。0は無制限 |
| Physics Settings Curves | 横軸は各根元からの累積骨長を0〜1に正規化、縦軸は上記6係数への倍率 |
| Gravity | ワールド空間の重力。cm/s²。Y-upの既定は(0, -980, 0) |
| Wind Velocity | ワールド空間の一定の風速度。cm/s。乱流なし |
| Planar Constraint | 親の入力ポーズのX/Y/Z軸を法線とする平面制限 |
| Start Frame | シミュレーション開始時刻。開始前は入力姿勢（Warmup設定時はその適用後） |
| Target Framerate | 内部積分の固定刻み。既定60 Hz。Mayaの表示fpsとは別 |
| Warmup Steps | 開始ポーズを固定した事前計算回数 |
| Teleport Distance | 1ステップの根元移動が超えると状態をリセット。cm。0で無効 |
| Max Steps | 開始から許可する内部ステップ数。超過時はエラー |
| Collision Iterations | 衝突押し出しと親子長復元の反復回数 |
| Residual Penetration | ブレンド前の動く計算点の最大残留貫通。cm。固定根元は除外 |
| Compliance | 距離拘束の柔らかさ。0で硬い拘束。逆質量は根元0、その他1 |
| Iterations Before / After Collision | 衝突計算前後に行う距離拘束の反復回数 |

各ランプの初期値は全域1です。Damping・Stiffness・World Dampingは倍率適用後も0〜1へ制限します。Limit Angleが正の場合に倍率0を指定すると、ほぼ0度へ制限します。

球はガイド原点、カプセルはローカルY軸、平面はローカル+Y側が安全側です。カプセルのHeightは両端の球を除く円柱部分の長さで、全高は`Height + 2 * Radius`です。平面ガイドは表示範囲のみで、計算上は無限平面です。コライダーのスケールは正の均等値を使用してください。親から継承する非均等スケール・シアーは非対応です。

プリセットJSONは係数とランプを保存します。Root/Exclude/Dummy、開始時刻、コライダー、距離拘束、接続はプリセットに含まず、Mayaシーンで保持します。作成時の骨構成を変更する場合はセットアップを作り直してください。コライダーは専用画面の削除ボタンで取り除いてください。

## 評価と制限

- 開始時刻から固定刻みで入力をサンプルするため、通常のキー付き入力では再生順に依存しません。過去のキー変更もサンプル照合により再計算します。シーン保存時は入力と設定を保持し、読み込み後にキャッシュを再構成します。
- 係数・ランプ・重力・風は静的設定です。アニメーション化すると「現在の値を開始時刻から全体に適用」します。入力ジョイントとコライダーの移動・回転・寸法のアニメーションをサンプルします。
- 入力には時刻指定で評価できるアニメーションを使用してください。再生履歴に依存する他シミュレーションは、先にベイクする必要があります。出力を入力・コライダーの駆動元へ接続すると循環するため使用できません。
- Python実装です。過去の入力照合コストと位置キャッシュがボーン数・経過ステップ数に応じて増えます。大量のボーン、長尺、複雑な入力リグでのリアルタイム性能は保証しません。短い区間で調整し、ベイクしてください。
- 衝突はボーン位置の球とガイド形状との離散判定です。ボーンの線分、メッシュ表面、自分同士の衝突、連続衝突検出はありません。高速移動ではすり抜ける場合があります。
- 長さ・角度・平面・距離・衝突の拘束が両立しない場合、最後に親子長を復元するため貫通や距離誤差が残ります。Residual Penetrationで点の貫通を確認してください。Alphaの中間値は制限後のブレンドなので、骨長・衝突制限の厳密な保証対象外です。
- 分岐の回転はMayaの子順で最初の子を基準にします。他の枝の長さは個別に維持します。ゼロ長ボーンは除外する必要があります。負／非均等スケール・シアーを含む入力リグは検証対象外です。
- Kawaii Physicsの完全互換移植ではありません。UEと同一数値の結果、UEアセット読込、PhysicsAsset、Blueprint、Sync Bone、Subdivision、Chaos Clothの布シミュレーションは提供しません。
- ノードID `0x0007F7A0`は開発用です。外部配布前にAutodeskの正式IDへ置き換えてください。保存シーンの型ID移行も必要です。

## Python API例

```python
from maya import cmds
from simplePhysics import api

node = api.create(cmds.ls(selection=True, long=True, type="joint"), dummyLength=2)
cmds.setAttr(node + ".damping", 0.15)
cmds.setAttr(node + ".stiffness", 0.05)
api.addCollider(node, "sphere", attachTo="body_joint", radius=5)
api.savePreset(node, "C:/temp/simplePhysics.json")
baked_group = api.bake(node, 1, 120)
```

作成・コライダー・距離拘束・プリセット適用・ベイク・削除は1操作ごとにUndoできます。Undo無効時の変更は拒否します。`api.remove(node)`はこのセットアップの所有物を削除し、元の骨とベイク済み階層は保持します。

## 検証

Maya 2027の専用mayapyで回帰テストを実行します。

```powershell
& 'C:/Program Files/Autodesk/Maya2027/bin/mayapy.exe' maya/inhouse/SimplePhysics/tests/test_simplePhysics.py
```

実DG、逆順評価、過去キー編集、角度と骨長、ランプ、入力回転、各コライダー、床との接触、距離拘束、単位、DG/Serial/Parallel、保存復元、ベイク、Undo/Redo、失敗時のロールバックを検証します。Maya 2022〜2026の動作は未検証です。

`tests/demo_simplePhysics.py`の`main()`は**専用Maya GUI**でのみ実行してください。新規シーンを作成し、実DGの計算点・式・数値をHUDへ表示して145フレームを録画します。録画にはワークスペースの`tools/verification_video.py`とFFmpegが必要です。動画とシーンは`.maya-output/verification/`に保存され、Git対象外です。

## 出典

KawaiiPhysicsのMITライセンスと参照コミットは[NOTICE.md](NOTICE.md)に保持しています。Unreal Engine／Chaosのソースは含みません。Mayaノード実装の仕様は[Autodesk Maya 2027 MPxNode API](https://help.autodesk.com/cloudhelp/2027/ENU/MAYA-API-REF/py_ref/class_open_maya_1_1_m_px_node.html)を参照してください。
