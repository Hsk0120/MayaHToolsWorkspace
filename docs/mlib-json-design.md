# mlib.json 設計書

2026-11-11 にユーザーと質問形式で決めた内容をまとめた設計書(mlib 11.1.0 で実装。実装で決めたことは11章)。実装後は要点を
`docs/mlib-api-design.md` とSphinx(`_docs`)へ移し、この文書は実装と合わせて更新するか削除する。

## 1. 目的と経緯

- 2026-10-23(28e18875)の縮小で、`mlib/json`(codec・storage・references・snapshots・editors)と
  `JsonDocument`・`JsonText`・`Snapshot` 系7クラスを削除した。3.0.0(2026-10-28)では `BlendShape` の
  ターゲット操作と `dumpTargets` / `loadTargets` も削除した。
- これらを、旧形式との互換を持たない新しい設計で戻す。旧 `mlib.blendShape` v1 等のファイルは読まない。

## 2. 全体構成

```
mlib/json/
├ __init__.py              公開名(__all__)
├ codec.py                 encode / decode(数学型 ⇔ JSON の値)
├ file.py                  dump / load と Header(ヘッダー付き JSON、形式・版の検査、fps の換算)
├ nodeRef.py               NodeRef(名前・パス・型で記録し、シーンのノードへ対応付ける)
├ plugRef.py               PlugRef(NodeRef + アトリビュート名)
├ componentRef.py          ComponentRef(NodeRef + コンポーネントの種類と番号)
├ nameMapping.py           NameMapping(nameMap・replace・namespaceMap をまとめ、名前を変換する)
├ snapshot.py              Snapshot 基底と ValidationReport
├ poseSnapshot.py          PoseSnapshot
├ animationSnapshot.py     AnimationSnapshot
├ attributesSnapshot.py    AttributesSnapshot
├ drivenKeysSnapshot.py    DrivenKeysSnapshot
└ selectionSnapshot.py     SelectionSnapshot
```

`ValidationReport` は `Snapshot` 専用の小さな結果クラスなので、例外的に snapshot.py へ同居させる(要確認)。

- 下の層(codec・file・参照・NameMapping)は、どの種類からも使う部品。
- 中の層 `Snapshot` 基底は、`save` / `load` / `validate` / `apply` の共通の流れを持つ。各種類は `capture`・`toData`・`fromData`・
  `_validate`・`_apply` だけを書く。
- 複数ノードにまたがるデータ(ポーズ・アニメーション・アトリビュート・ドリブンキー・選択)は、Snapshot クラスを直接使う。
- 1つのノードが持つデータ(スキンウェイト・カーブ形状・BlendShape)は、処理をそのノードのクラスに直接書く。
  json 側に内部クラスは置かず、ノードのクラスが codec・file・参照・NameMapping を直接使う。

保存の流れ: シーン → 取得(Snapshot の capture、またはノードのメソッド)→ codec・参照(値と名前の変換)→ file(ヘッダー付き JSON)。
読み込みはその逆で、検査してから適用する。

## 3. file 層

```json
{
  "header": {
    "format": "mlib.blendShape",
    "version": 1,
    "mlib": "11.1.0",
    "maya": "2027",
    "units": {"linear": "cm", "angle": "deg", "time": "frame", "fps": 30.0}
  },
  "data": {}
}
```

- 単位は mlib の既定に合わせる。長さは cm、角度は度、時間は保存時の UI 時間単位のフレームとし、fps をヘッダーへ書く。
- 書き出しは UTF-8・整形(indent)・小数は丸めない。一時ファイルへ書いてから置き換え、失敗しても元のファイルを壊さない。
- 読み込み時は、形式名・版が期待と違えば `ValueError` を送出する(メッセージに期待した形式・版と実際の値を書く)。
  専用の例外クラスは作らない。版の変換関数は持たない(版が違えば拒否)。
- fps が保存時と違う場合は読み込み側で選ぶ。既定はフレーム番号を保つ。秒を保つ指定(例: `timing="second"`)で、
  実際の時間を保つように換算する。

## 4. codec 層

- 数学型は型名付きで書く。

```json
{"type": "Translate", "value": [0.0, 12.5, 0.0]}
{"type": "EulerRotate", "value": [0.0, 45.0, 0.0], "order": "xyz"}
{"type": "Matrix", "value": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 12.5, 0, 1]}
```

- 対象: `Vector`・`Translate`・`Scale`・`Shear`・`Quaternion`・`EulerRotate`・`Matrix`。
- `EulerRotate` は度で保存し、回転順の名前を付ける。`Quaternion`・`Matrix` は単位を持たないのでそのまま。
- デルタ・ウェイトのような大量の数の並びは、型名を付けずに数の配列で書く(各種類の形式で決める)。

## 5. reference 層

```json
{"name": "chrA:arm_L_jnt", "path": "|chrA:root|chrA:spine|chrA:arm_L_jnt", "type": "joint"}
```

- ノードは短い名前・フルパス・型で記録する。短い名前で探し、同名が複数あればパスで絞り、型で取り違えを検査する。UUID は持たない。
- Plug は `{"node": {...}, "attr": "translateX"}`(ロング名、マルチアトリビュートの要素は `weight[3]` のように番号付き)。
- コンポーネントは `{"node": {...}, "type": "vtx", "indices": [0, 1, 5]}`。
- 読み込み時の対応付けは次の3つで、同時に指定した場合はこの順に適用する。
  1. `nameMap={"arm_L_jnt": "leftArm_jnt"}`: 名前空間を除いた名前で引く。該当すれば最優先で使う。
  2. `replace=[("_L_", "_R_")]`: 文字列の置き換えを順に適用する。
  3. `namespaceMap={"chrA": "chrB"}`: 名前空間を入れ替える。
- 対応するノードが見つからない場合は、飛ばして警告する(常に見つかったものだけ適用)。

## 6. snapshot 層

- `Snapshot` 基底: `capture(...)`(取得)、`validate(...)`(検査。報告を返す)、`apply(...)`(適用)、
  `toData()` / `fromData(data)`、`save(path)` / `load(path)`。
- `apply` は内部でも検査する。適用できない問題(頂点数の違い等)は例外、見つからないノードは警告とする。
- `apply` は通常1回の Undo にまとめ、途中で失敗したら巻き戻す。OpenMaya で速くなる種類だけ `fast=True`(Undo なし)を持つ。

## 7. 種類ごとの仕様

7.1〜7.5 は `mlib.json` の Snapshot クラス、7.6〜7.8 はノードのクラスに直接書くメソッド。

### 7.1 ポーズ `PoseSnapshot`(Snapshot)

- 対象: キー可能なアトリビュートと、キー不可でチャンネルボックスに表示されるアトリビュート。
- ロック・接続中のアトリビュートも保存する。適用時に書けないものは飛ばして警告する。適用でキーは打たない。
- ローカルの値だけを保存する(ワールド空間は扱わない)。

### 7.2 アニメーション `AnimationSnapshot`(Snapshot)

- 時間入力のアニメカーブと、アニメレイヤー(ウェイト・モード・親レイヤーの設定を含む)。
- カーブを完全に再現する: キーの時刻・値、接線の型・角度・ウェイト、ロック、ブレークダウン、ウェイト付き接線、前後のインフィニティ。
- `capture(nodes, time=(start, end))` で範囲を絞り、`apply(timeOffset=...)` で時間をずらす。
- 既存キーの扱いは `mode="replace"`(既定。カーブごと入れ替え)/ `"insert"`(保存した範囲だけ置き換え)/ `"merge"`(同じ時刻だけ上書き)。
- 読み込み先に同名のレイヤーが無い場合は `createLayers`(既定 True)で作成するかを選ぶ。同名があればそれを使う。

### 7.3 アトリビュート `AttributesSnapshot`(Snapshot)

- `capture(nodes, attributes=["visibility", "radius"])` のように名前で指定する(Plug の直接指定も可)。
- キー可能かどうかを問わず、文字列・マトリクス・enum 等の型も扱う。ユーザー定義アトリビュートの定義(addAttr)は保存しない。

### 7.4 ドリブンキー `DrivenKeysSnapshot`(Snapshot)

- ドライバーとドリブンの Plug、カーブ(アニメーションと同じく完全再現)に加え、間の blendWeighted・単位変換ノードも保存・再作成する。

### 7.5 選択 `SelectionSnapshot`(Snapshot)

- 選択順のノードと、コンポーネント(頂点・エッジ・フェース・CV・UV)の選択。

### 7.6 スキンウェイト(`SkinCluster` のメソッド)

- `exportWeights(path)` / `importWeights(path)` / `getWeightsData()` / `setWeightsData(data)`。
- 既定は頂点番号で対応させ、頂点数が違えばエラー。`method="position"` で保存した頂点位置の最近点からウェイトを使う(保存時に位置も記録する)。
- ウェイトのほかに、スキニングの設定(方法・最大インフルエンス数・正規化)、DQ ブレンドウェイト、インフルエンスのロック状態、
  ngSkinTools のレイヤーを保存する。
- メソッドは既存の SkinCluster への適用だけを行う。SkinCluster が無いメッシュには、`mlib.bindSkin` にファイルを渡して
  インフルエンスを揃えて作成する。

### 7.7 カーブ形状(`Transform` のメソッド)

- `exportCurveShapes(path)` / `importCurveShapes(path)` / `getCurveShapesData()` / `setCurveShapesData(data)`。
- Transform 単位で、配下の NurbsCurve Shape をまとめて保存する。適用時は Shape を作り直して置き換えるので、本数が違ってもよい。
- 含めるもの: CV・次数・フォーム、表示色(Shape と Transform)、lineWidth、Shape の名前。

### 7.8 BlendShape(`BlendShape` のメソッド)

- `exportTargets(path)` / `importTargets(path)` / `getTargetsData()` / `setTargetsData(data)`。
- 含めるもの: ターゲットごとのデルタとインビトゥイーン(接続中のターゲットは現在の形をベイク)、ターゲットの頂点マスクと
  baseWeights、各ウェイトの現在値と入力接続(reference の対応付けで再接続)、Shape Editor のフォルダ。
- 既存のターゲットがある場合は、既定で同名を置き換え、無いものを追加する。`mode="empty"` で空の BlendShape にだけ読む。

## 8. BlendShape のターゲット操作(json と別に戻すもの)

3.0.0 で削除したターゲット操作を、今のクラスへ戻す。

- ミラー・フリップ: `mirrorTarget` / `flipTarget`
- インビトゥイーン: `addInBetween` / `removeInBetween` / `getInBetweenWeights`
- 頂点マスクとデルタ: `getTargetWeights` / `setTargetWeights` / `getTargetDeltas` / `setTargetDeltas` /
  `getTargetVertices` / `resetTargetVertices` / `reduceTargetDeltas`
- 複製・差し替え・編集モード: `duplicateTarget` / `replaceTarget` / `targetEdit`

共通の決まり:

- ターゲットは名前・論理番号・weight 要素の Plug で指定できる。既存の `getWeightPlug`・`removeTarget` も同じ受け付け方に揃える。
- 複数のベースを持つ場合に備え、`base=None`(省略時は先頭のベース)を付ける。
- `fast` は OpenMaya で速くなるもの(`setTargetWeights`・`setTargetDeltas` 等)にだけ付け、実測で差が無ければ外す。

## 9. ルール変更(案)

CLAUDE.md の次の2か所を変更する。

1. 実行フォルダの一覧に `json` を加える。
   - 変更前: 「mlibの実行フォルダは `cmds`・`nodes`・`plugs`・`components`・`maths`・`common`・`core` とする。」
   - 変更後: 「mlibの実行フォルダは `cmds`・`nodes`・`plugs`・`components`・`maths`・`common`・`core`・`json` とする。
     `json` はノード・Plug のデータの JSON 保存・復元(codec・file・reference・snapshot)を置く。」
2. 保存の禁止を緩める。
   - 変更前: 「汎用UI・設定ストア・保存フレームワークは本体へ追加しない。」
   - 変更後: 「汎用UI・設定ストアは本体へ追加しない。シーンのデータの JSON 保存・復元は `mlib/json` に置き、
     ノードが持つデータはノードクラスのメソッド、複数ノードのデータは `mlib.json` の Snapshot で提供する。」

あわせて、`docs/mlib-api-design.md` に「JSON 保存」の節を足す。

## 10. 注意点

- `mlib/json` は標準ライブラリの `json` と同じ名前になる。Python 3 の `import json` は絶対 import なので、
  通常は標準の json が読まれる。ただし mlib のフォルダ自体が `sys.path` に入る(そのフォルダで python を起動する等)と、
  標準の json の代わりに `mlib/json` が読まれる。そうしたスクリプトやテストランナーが無いことを、実装時に確認する。
- 版の変更: 新しい公開パッケージとメソッドの追加なので mlib 11.1.0(マイナー)。既存 API の変更が出れば 12.0.0。

## 11. 実装で決めたこと・設計からの差(11.1.0)

- 形式名: `mlib.pose`・`mlib.animation`・`mlib.attributes`・`mlib.drivenKeys`・`mlib.selection`・`mlib.skinWeights`・
  `mlib.curveShapes`・`mlib.blendShapeTargets`。どれも版1。
- `ValidationReport` は `snapshot.py` に同居させた(Snapshot専用の小さな結果クラスのため)。
- 存在しないノードを `capture` に渡した場合は、`Node()` と同じく RuntimeError。
- `fast` を付けたもの(実測): `SkinCluster.setWeightsData` / `importWeights`(20,100頂点で1.68秒→0.18秒)、
  `AnimationSnapshot.apply`(2万キーで約0.7秒→0.18秒)、`BlendShape.setTargetWeights` / `setTargetDeltas` /
  `resetTargetVertices` / `reduceTargetDeltas`。`duplicateTarget` は Shape Editor への登録に cmds が要るため fast なし。
- アニメーション: レイヤー名には名前の対応付けを当てない(名前空間外のシーン全体の名前のため)。レイヤーのウェイトは現在値だけ。
  キーの無いカーブは保存しない。ドリブンキーの置き換えはドライバーと駆動先の組の単位。
- スキンウェイト: 位置での対応付けは skinCluster に入る前の形状(`input[i].inputGeometry`)で比べる。見つからないインフルエンスの
  ウェイトは除き、残りを頂点ごとの元の合計へ比率を保って拡大する。`mlib.bindSkin(weights=...)` は `maximumInfluences` の既定を
  None(ファイルの値、無ければ4)にした。旧来の `dumpWeights` / `loadWeights` は残している。
- カーブ形状: Shape は保存した短い名前に読み込み先 Transform の名前空間を付けて作る。形状は MEL の
  `setAttr ".cached" -type nurbsCurve` で設定する(Python の cmds.setAttr では渡せず、cmds.curve は closed を作れないため)。
- BlendShape: `mirrorTarget` の向きは `positiveToNegative=True`(`SkinCluster.mirrorWeights` に合わせた)。接続中のターゲットへの
  `resetTargetVertices` / `reduceTargetDeltas` / `setTargetDeltas` は `disconnect=False` なら RuntimeError、True なら切ってベイク。
  `addInBetween` / `replaceTarget` は self を返す。`duplicateTarget(target, name=None)` は `<元の名前>Copy`。
  Shape Editor のフォルダは `targetDirectory` と `parentDirectory` で戻す。envelope・origin・デフォーマーの順序は保存しない。

