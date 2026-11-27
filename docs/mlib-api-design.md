# mlib APIの設計基準

> mlibは別リポジトリ(`Hsk0120/mlib`)へ分けた(2026-11-12)。この文書はワークスペース側の設計の検討と経緯の記録で、mlibのリポジトリには入れない。コードを書くときのルールの正本はmlibの `.github/copilot-instructions.md`(`maya/inhouse/mlib/.github/copilot-instructions.md`)。ルールを変えたら両方を更新し、食い違う場合は指示ファイルとコードを確かめて揃える。文中の版番号(12.4.0以前)と `tools/generate_mlib_stubs.py` 等のパスは分割前のもの。

今後のAPI追加・変更では、**Mayaへ問い合わせる操作はメソッド、保持する値はプロパティ**を基本とする。
実装・docstring・使用例を同じ基準に揃える。

## 2026-11-19の未対応候補に限る例外

ユーザーの採否回答A〜Fにより、以下の範囲を検証・実装対象とする。実装済み・動作保証とは扱わず、
既存API全体のUndo・fast・API 2.0方針へ一般化しない。独自MayaプラグインとUndo設定の変更は禁止のまま。

- A: API 2.0に入口がなかった次の機能に限りAPI 1.0併用も許可する。DG計測の全体設定、DAGのactive/dormant/hilite色・hilite色使用状態・描画overrideの色/有効/参照/テンプレート状態、groupIdからの所属、カメラの非正規化near/farクリップ平面、Meshの重複点検査設定の照会、BlendShapeの履歴位置、Lambertの特殊な屈折色の取得/設定。Maya版ごとの同等性・型/値の境界・保持期間を検証する。
- B: カメラの視点コピー/一括姿勢/注視点変更、コンポーネント基準のピボット中央化、スキン強制正規化は、通常Undoの代替経路に加え、Undoなしを明示した限定APIも検討できる。単にUndoチャンクで囲んで復元可能と説明しない。
- C: NURBS曲面のUV割当/一括割当/解除と、共有法線番号を維持したMeshの法線配列更新は、検証できたものをfast=True専用で追加できる。fast省略/Falseは更新前に拒否し、ヒストリ等の未対応条件も更新前に拒否する。
- D: スキンのジョイント移動モード、Referenceのロック/解除/編集履歴削除は、Undo対象外と明示した専用操作として検証・実装する。特に編集履歴削除の保存内容への影響を説明する。cmdsの呼出しをfastと呼び替えない。
- E: BlendShapeのトポロジー/UV基準の対称編集は、既存mirrorTarget/flipTargetの操作時指定として検証する。省略時のobject空間の動作を維持する。通常Undoが成立しない場合もUndoなしの限定版を検討できる。単独のsymmetry設定setterを形だけ追加しない。
- F: カーブのノット削除とカメラのクリップ状態照会は、API 1.0も含む代替経路を再検証する。結果が正しくない入口は公開しない。同じ意味なら既存APIへ集約し、解決できなければ理由付きで未対応とする。

BはカメラのsetView/copyViewFrom/setCenterOfInterestPointをfast=True専用、ピボット中央化と強制正規化を通常Undo対応として実装する。EはmirrorTarget/flipTargetのsymmetrySpace/symmetryEdgeでtopologyに対応し、object既定を維持する。API 1.0併用の明示許可はA/Fに限定する。
通常Undoなしの操作はdocstringとテストで区別する。既存APIの省略時動作や返却を変更しない。

カードの内訳はA=16、B=6、C=4、D=4、E=2、F=2の計34候補。
旧台帳の未対応状態は消さず、再検証の決定と実装結果を分けて管理する。
対象別の対応表はGit対象外の `docs/research/mlib-full-method-survey-20261119/implementation-progress.csv` に記録する。

### 実装した入口と制限

- API 1.0は対象を限定した照会とDG計測に使用し、API 2.0のオブジェクトを直接渡さず名前・完全DAGパスから解決する。描画状態はMayaのキャッシュの照会で、描画更新を強制しない。
- カメラの`setView`・`copyViewFrom`・`setCenterOfInterestPoint`、Meshの`setNormals`、NurbsSurfaceの`setUVData`は`fast=True`専用。未対応条件を更新前に拒否し、Undo設定は変えない。
- `Mesh.setNormals`は共有法線番号を維持し、法線をロックする。ワールド空間は明示変換し、特異マトリクスは拒否する。`setUVData`は完全なUV表と割当表を受け取り、既存UV表の縮小には対応しない。
- コンポーネント基準のピボット中央化は既存の`setPivot(preserve=True)`へ、強制正規化は計算した値を`setWeights(normalize=False)`へ渡して通常Undoに対応する。強制正規化はインフルエンスの保持設定を無視するが、ウェイトPlugのロックは解除しない。合計0は0のまま残す。
- Referenceのロック変更は、ロード中ならアンロード・再ロードを伴う。保持済みの参照先オブジェクトは無効になる。編集履歴削除はアンロード済みでロックされていない参照に限定し、いずれもUndo対象外。スキンのジョイント移動モード切替もUndo対象外。
- BlendShapeのtopology基準は既存のミラー/反転のキーワード引数で指定する。基準エッジの設定も同じUndoチャンクへ含める。階層なしで一意なShape名を要求する。Mayaの対称編集キャッシュ`topoSymmetrySet`の作成・破棄はUndoで復元されない。テストでは自分が作ったキャッシュだけを後始末し、後続ケースに持ち越さない。
- Lambertの屈折フラグは既存の`getPlug("refractions")`で取得・変更できるため、同じ意味の専用入口を増やさない。
- カーブの`reduceKnotMultiplicity(parameter)`は内側の重複ノットを1つへ減らす。2026-11-20の追加採用により、`NurbsCurve.removeKnot(parameter)`は標準のEP削除で指定値のノットをすべて除去する。形状維持は保証しない。次数1〜3・両端が最大多重度の開いたカーブに限定し、ヒストリ・参照・インスタンス・タグ・CVのロックや接続は拒否する。いずれも通常Undo対応。OpenMayaのremoveKnotは最後の1つを残したため全削除には使わない。
- カメラの`MFnCamera.isClippingPlanes`の取得値は、`getPlug("bestFitClippingPlanes").get()`と一致する。専用入口は増やさない。`clippingPlanes`は[公式ノード仕様](https://help.autodesk.com/cloudhelp/2027/ENU/Maya-Tech-Docs/Nodes/camera.html)で未使用とされており、これを変えて専用照会が変わらないことだけで照会の不具合とは判断しない。APIのsetterは未使用側を書いたため、getterとsetterを対にしたラッパーも追加しない。
- 2026-11-20の追加採用により、`NurbsSurface.clearUVData()`は同じShapeへ形状データを書き戻し、明示UV表と割当を消す。通常Undo対応で、Shapeの削除・再作成はしない。ヒストリ・参照・トリム・インスタンス・タグ・複数UVセットやCV/UVの編集不可条件は拒否する。消去後は明示UV未設定となり、getUVDataはRuntimeErrorになる。OpenMayaのclearUVsでは表が消えず、別経路を採用した。既存setUVDataのfast専用仕様は維持する。
- BlendShapeのUV基準対称編集は、2026-11-20の回答で再現例が得られるまで保留。UV配置・軸・ターゲット形式に加えライブ/削除済みターゲット・別UVセット・ミラー/反転を試してもデルタや評価頂点位置は変わらなかった。objectの対照は成立。全条件で不可能とは断定せず、独自UV対応付けも追加しない。調査証拠は `.maya-output/mlib-remaining-investigation-20261120/REPORT.md`。

## 2026-11-18の追加APIの境界

採用した52〜67の照会・編集を既存クラスへ追加する。独自の変形・キー削減アルゴリズムやMayaプラグインは作らない。
既存メソッドへ加える引数はキーワード専用とし、省略時の動作を維持する。新規setterはNoneを返す。

- Nodeの外部ファイル情報はMayaが申告した内容だけを返し、連番・UDIMの全ファイルを収集する機能にはしない。
- ReferenceのEdit照会は種類と保存元で絞る。記録中の名前を現在のNodeやPlugへ変換しない。
- Plugのカテゴリは読み取り、Nice Nameは非参照ノードの追加アトリビュートの定義だけを編集する。空文字列で表示名の上書きを解除する。
- Cameraのfilm frustumはOpenMayaの戻り値を保持する。幅・高さは距離面のcm、オフセットはフィルム面のinch値で、同じ空間の四隅座標にはしない。
- Meshの法線番号・穴の内周・NURBSの明示UVとトリム境界はMayaの番号順を保持する。未設定のNURBS UVを推測生成しない。
- 面頂点カラーの解除は未設定へ戻す。通常は検証済みのヒストリだけ、fastは入力ヒストリなしに限定する。
- BlendShapeのbaseWeightsとweightListは別データとして扱い、Maya版による変形への作用の違いを記す。
  ターゲット再生成は全ベースに作用し、通常の1.0本体と0より大きく1未満のin-betweenに限定する。Maya本体の異常終了を確認した項目は実行前に拒否する。
- SkinClusterの転送条件は、転送先を自動バインドする前に検査する。Maya2023ではロックされたweightListへの転送を通常Undoで戻せないため、変更前に拒否する。
  AnimCurveのキー削減はMaya標準フィルターを使い、出力が接続済みのTA/TL/TUに限定する。
- rotateAxisの姿勢維持は操作時点の補正だけを行い、アニメーション全体の維持を保証しない。

## 呼び名の対応表

2026-10-28のユーザー指定(4.0.0)により、アトリビュートの構造はMayaのコマンドの呼び方へ揃える。
説明・docstring・コメントでは「マルチアトリビュート」「要素」「論理番号」「コンパウンドアトリビュート」「子」と書き、
「配列」「multi」「マルチ」「複合」等の略称は使わない。例外メッセージでも「マルチアトリビュート」「マルチアトリビュートの要素」
「コンパウンドアトリビュート」と書く。Pythonのlist・`doubleArray`等の配列データ型・OpenMayaのAPI名はそのまま書く。

| mlib の名前 | Maya コマンド | OpenMaya |
| --- | --- | --- |
| マルチアトリビュート: `MultiPlug`・`Plug.isMulti()` | `addAttr -multi` | `MPlug.isArray` |
| マルチアトリビュートの要素: `Plug.isMulti(element=True)`・`Plug.getMulti()`(要素が属するマルチアトリビュート) | `attr[番号]` | `MPlug.isElement`・`MPlug.array()` |
| 要素の番号(論理番号): `Plug.getIndex()`・`MultiPlug.getIndices()` | `[番号]` | `MPlug.logicalIndex()` |
| コンパウンドアトリビュート: `CompoundPlug`・`Plug.isCompound()` | `addAttr -at compound` | `MPlug.isCompound` |
| コンパウンドアトリビュートの子: `Plug.isChild()`・`Plug.getParent()` | `-parent` | `MPlug.isChild`・`MPlug.parent()` |

## 提供する機能の範囲

2026-10-23の指定により、mlibはNode/Plug/Component/数学型と隣接基盤へ絞る。
汎用UI、OptionVar/Preferences、専用Color、Scene/Workspace/FBX、
mlib版OBBは提供しない。旧import・互換別名・旧保存形式readerは残さない。
通常JSON文字列は標準`json`、標準UIは利用側のcmds/melで扱う(表示色は下記の2026-11-10の指定で専用メソッドへ戻した)。
型付きJSON・Snapshotは2026-11-11の指定で、旧形式と互換の無い新しい`mlib.json`として戻した(下記「JSON保存・復元」)。
`mlib.cmds`とルート関数は`getNode/getPlug/createNode/ls/delete/duplicate/select`に限定する。
複数形・reload・拡張自動探索・数学所有権・単位・通常Undo/fastと、保持APIの引数/返却は維持する。
Mesh.reorderVerticesと小さな便利メソッドは残す。

追加縮小では、AddDL/AddDoubleLinear/MultDL/MultDoubleLinear/BlendColors/BlendWeighted/
Clamp/Condition/MultiplyDivide/PlusMinusAverage/RemapValue/Reverse/SetRange/UnitConversionの
型クラスと登録を残し、専用APIを終了する。操作はMaya標準名の`getPlug`とPlugのAPIを使う。
専用の検証・enum名・コンパウンドアトリビュートの編集・戻り型変換は提供しない。
判定は正式is名へ統一し、is省略入口と省略名へのSphinx投影は提供しない。
`undo.enabled`も廃止し`undo.isEnabled`を使用する。保持APIの仕様と拡張機構は維持する。

## JSON保存・復元

2026-11-11のユーザー指定(11.1.0)。設計の経緯と各形式の中身は`docs/mlib-json-design.md`を参照する。

- 置き場所は`mlib/json`。下の層は`codec`(数学型を`{"type": ..., "value": [...]}`で書く。EulerRotateは度と回転順の名前)、
  `file`(`{"header", "data"}`のファイル。ヘッダーは形式名・版・mlib/Mayaの版・単位(cm・度・保存時UIのフレームとfps))、
  `NodeRef`・`PlugRef`・`ComponentRef`(名前・完全パス・型で記録)、`NameMapping`。中の層は`Snapshot`基底と`ValidationReport`。
- 形式名・版が期待と違うファイルは`ValueError`で読まない。版の変換は持たない。書き出しは一時ファイル経由で、失敗しても既存のファイルを壊さない。
- 名前の対応付けは`nameMap`(名前空間を除いた名前で引き、該当すれば最優先)→`replace`(順に文字列置換)→`namespaceMap`の順に当てる。
  見つからないノードは飛ばし、最後にまとめて警告する(常に部分適用)。型が違うノード・1つに絞れない名前は対応させない。
- 1つのノードが持つデータはノードクラスに直接書く(`SkinCluster.exportWeights`・`Transform.exportCurveShapes`・
  `BlendShape.exportTargets`と、それぞれの`get…Data`・`set…Data`・`import…`)。名前は中身が分かる名前にし、`exportData`のような汎用名にしない。
  json側に中間の内部クラスは置かず、nodesからはメソッド内で`mlib.json`をimportする(循環参照の回避)。
- 複数ノードのデータは`mlib.json`の`PoseSnapshot`・`AnimationSnapshot`・`AttributesSnapshot`・`DrivenKeysSnapshot`・
  `SelectionSnapshot`で、`capture`→`save`/`load`→`validate`/`apply`の流れにする。各種類は`apply`の引数を明示して書き、
  本体は基底の`_run_apply`(検査→errorsがあれば何も変えずにValueError→1回のUndoで適用・失敗時は巻き戻し→警告)に渡す。
- 時間は保存時のフレームで書き、読み込み時に`timing="frame"`(既定。フレーム番号を保つ)か`"second"`(秒を保つ)を選ぶ。
- `fast`は他のAPIと同じく、実測で速くなるものだけに付ける(11.1.0では`SkinCluster.setWeightsData`/`importWeights`と
  `AnimationSnapshot.apply`、BlendShapeの頂点マスク・デルタの書込み)。

## 確定したコーディングルール

- シーンの作成・更新APIは基本として生成物や操作対象を返す。`Node.addAttr()` は既定でPlugを返す。`delete`、設定・標準UI等の既存None返却、`safe/get`によるモード別返却、専用集約結果は各APIの契約を維持し、一般原則へ合わせるために変更しない。

公開APIの表記は**camelCaseに統一**する。common・logger・decoratorも同じ規則とする。

| 対象 | 規則 | 例 |
| --- | --- | --- |
| クラス | PascalCase | `SkinCluster`、`EulerRotate` |
| 公開関数・メソッド | lowerCamelCase | `getMatrix()`、`getSettings()`、`undoChunk()` |
| プロパティ | lowerCamelCase | `orderName`、`minimumVersion` |
| Mayaコマンド・アトリビュート・nodeType | Maya標準の原名 | `createNode`、`offsetParentMatrix`、`skinCluster` |
| 一般Pythonファイル | lowerCamelCase | `scriptJob.py`、`eulerRotate.py` |
| 内部関数・内部メソッド・ローカル変数 | snake_caseを基本とする | `_resolve_input`、`namespace_map` |
| 引数 | 公開の独自引数はlowerCamelCase。Mayaのフラグと同じ名前はMayaの表記 | `worldSpace`、`uiUnits`、`transferToParent` |
| 定数 | UPPER_SNAKE_CASE | `LOAD_FAILED` |

- `get`/`set`は値の取得・設定、`is`/`has`は判定、`create`/`add`/`remove`は作成・追加・除外に使う。
  独自の取得メソッドは `getName()`、`getSource()`、`getChildren()` のようにgetを付ける。
  数学演算・判定・保持値のプロパティ・OpenMaya標準名は一律get化しない。
- 2026-10-26のユーザー指定により、ノードの作成は `mlib.createNode(type, *, name/n, parent/p, shared/s, skipSelect/ss, fast=False, **kwargs)` だけで行う。
  `cmds.createNode` 相当で、戻り値は作成したノードの実際のnodeTypeに対応するラッパー(登録クラスまたは動的クラス)。
  `Node.create` クラスメソッド・`Transform.create` 等の型付きcreate・`Node(name, create=True)` 経路は廃止し、
  単数Nodeクラスのconstructor `Node(node)` は既存ノードの取得専用とする(`create` 引数は持たない)。
  getNode等の取得関数・複数形・Object入口も作成を兼ねない。2026-10-09の `create=False` 規則はこの指定で置き換える。
  2026-10-31のユーザー指定(8.0.0)により、createNode以上の処理をするノード型の作成も、クラスメソッドではなく
  `mlib.cmds` の関数にする(存在しないインスタンスを作ってから create する形をやめる)。
  `createContainer`・`createDagContainer`・`createDagPose`・`createIkHandle`・`createBlendShape`・`createCurve`・
  `createCircle`・`createLocator`・`createPolyCube/Sphere/Cylinder/Plane`・`bindSkin`(Maya の cmds.skinCluster と同じ引数の順)。
  形状の作成関数はShapeを返し、大きさはcm(UI単位に依存しない)。既存ノードへの操作(`Container.createNode`・`Joint.mirror`・
  `Transform.addConstraint`)、common の作成(`Namespace.create` 等)、拡張の `Graph.create(name)`(mlib_bifrost)は残す。
  単なるcreateNodeの言い換えは追加しない。
  `fast=True` はOpenMayaで直接作成しUndoを記録しない。入力検証・例外・戻り値の意味は通常経路と同じで、
  `shared=True` と `name` 指定で同名ノードが既にある場合は同じnodeTypeのときだけそれを返し、型が違えばRuntimeErrorとする。
  未知の型名はどちらの経路でもRuntimeErrorとし、unknownノードを残さない。`query/edit` フラグは `cmds.createNode` に無いので受け付けない。
- 2026-10-27のmlib 2.0.0で次版へ送ったsnake_case公開引数のlowerCamelCase化は、2.1.0で改名済み
  (`isType(nodeType)`・`getNodeName(removeNamespace)`・`SkinCluster.bind(maxInfluences)`・`removeInfluence(transferToParent)`・
  `getClosestAxisToVector(refVector, includeNegative)` 等)。旧引数名の互換は残さず、
  旧名のキーワード指定はTypeErrorになる。内部関数・内部メソッド・ローカル変数・`*args`/`**kwargs` はsnake_caseのまま、
  既存の登録プロトコル(`NodeRegistry`・`reload_package` 等、名前自体がsnake_caseの入口)は対象外とする。
  5.0.0でログの公開関数もlowerCamelCaseへ改名した(`logger.getLogger`・`logger.raiseWithNotify`。旧名の別名は残さない)。
  公開defの引数名は `__tests__/noMaya/test_mlib_publicArgs.py` が検査する。旧名との対応は git の履歴(各版のコミットメッセージ)で追う。
- 2026-11-13のユーザー指定により、互換のために残す引数は置かない。使わなくなった引数は削除し、呼出し側・docstring・型スタブも一緒に直す。
  `ruff check` の `ARG`(未使用引数)で検出し、残すのは「呼ぶ側が引数を決める」ものだけとする:
  基底クラスの契約(`Snapshot._validate`/`_apply` の `options`・`fast`、`DagNode.getShape` の `index`・`intermediates` のように
  派生が使い基底は無視するもの)、Mayaのコールバックが渡す引数、差し替える関数の表が決めた引数。
  残す場合は `# noqa: ARG002` 等と理由を同じ行に書き、docstringにも「使わない」と明記する。
  `*args`・`**kwargs` は呼出しの形を合わせるためのものなので対象外(`ignore-variadic-names`)。テストは
  コールバックと差し替えで受ける引数が多いため `__tests__/**` で除外する。先頭に `_` を付けて残すのは、
  上の「呼ぶ側が決める」場合だけとし、それ以外は削除する。公開APIの引数を削除したら、Maya 2027のテスト一式と
  利用側(`tools/run_rig_packages.py --suite all`)を通してから確定する。
- 2026-10-22のユーザー指示により、独自の取得は `getX()` へ統合する。
  get省略入口と対応する短名コマンドファイルは削除し、利用側・テスト・Sphinxもget付きへ更新する。
  判定・数学演算・保持プロパティ・OpenMaya標準名は取得統合の対象外とする。
  演算ノードはPlugで扱う。追加縮小14型の専用APIは検証・enum変換・コンパウンドアトリビュート処理も含め終了する。
  対象外のノードの検証・コンパウンドアトリビュート処理は維持する。
  Transform/Jointおよびマトリクス・TRS関連の専用アクセサーは維持する。
  接続は `getSource/getDestinations(skipConversionNodes=...)` と方向指定の `getConnections`、
  単位は `get/set(uiUnits=...)`、子孫探索は `getChildren(allDescendents/order/leaves/includeSelf)` に集約する。
  `getShapes` は独立して維持する。オフセットグループ生成とリグ向けチャンネル初期化は
  `mlrig.setups.ControlHierarchy` が担当する。
- 2026-10-26のユーザー指定により、名前の重なる接続・階層・型照会のメソッドは次へ集約する。旧名の互換入口は残さず、
  旧名との対応は git の履歴(各版のコミットメッセージ)で追う。
  名前・パスは `getName()`(最短一意名)/`getFullName()`(完全パス)に集約し、`getPath(full)`・`getFullPath()`・`getPartialPath()` は廃止する。
  親のDAGパスは `getParent().mpath()`(`getParentPath()` 廃止)。
  階層判定は `isParentOf(other)`・`isAncestorOf(other)` で、`isChildOf` は `other.isParentOf(self)` に置き換えて廃止する。
  `sameInstance` は `==`(DAGではインスタンスパスを含む等価比較)と同じなので廃止する。
  function setは `mfn()` がそのノードで最も具体的なOpenMayaのfunction set(Node→MFnDependencyNode、DagNode→MFnDagNode、
  Transform→MFnTransform、Mesh/Camera/NurbsCurve/Referenceは各クラスのoverrideでMFnMesh等)を毎回新規に返す。
  `dagFn()`・`transformFn()` は廃止、`getAttrCount()` は `mfn().attributeCount()`、`hasFn(fn)` は `mnode().hasFn` の公開入口。
  2.1.0で`cameraFn/meshFn/curveFn/referenceFn`と`SkinCluster.fn`は廃止し、`mfn()`(SkinClusterはoma2.MFnSkinCluster)へ統合した。
  形状データの無いmesh/nurbsCurve(作成直後など)の`mfn()`は`MFnDagNode`を返し、形状を要する照会は`RuntimeError`にする。
  アトリビュートの列挙は `getPlugs(userDefined=False, includeChildren=True, **listAttrFlags)` に集約し、
  `getExtraAttrs(include_children, *, asNames)` は廃止する。`userDefined=True` はユーザー定義アトリビュートだけを
  OpenMaya経路で追加順の型付きPlug(マルチアトリビュートはMultiPlug)として返し、`cmds.listAttr` のフラグとの併用はTypeError。
  `userDefined=False` は `cmds.listAttr` 経路。`includeChildren=False` はコンパウンドアトリビュートの子を省く。名前の列は
  `[p.getLongName() for p in node.getPlugs(userDefined=True)]`(`getName()` のアトリビュート部分は `tx`・`wm[0]` 形式のショート名と論理番号のパスなので、ロング名の一覧には使わない)。
  DAG共通の `getRoot()`・`getSiblings()`・`getBoundingBox(worldSpace=False)`・`isIntermediateObject()` は
  `DagNode` に置き、TransformとShapeの両方から使う。`getSiblings()` はShapeでは親直下の他の非中間Shape、
  `getBoundingBox` は `MDagPath.exclusiveMatrix` で空間を切り替える。
  アウトライナーの並び順(親の直接の子の中の順番)も `DagNode` に置く。`getOutlinerOrder()` は保持パスが何番目かを返し、
  `setOutlinerOrder(index)` は番号で移動する(負の値は末尾から、範囲外は IndexError、同じ番号なら何もせず Undo にも積まない)。
  `reorder(front/f, back/b, relative/r)` は `cmds.reorder` のフラグをそのまま受ける入口で、ちょうど1つを指定する
  (`relative` は Maya と同じく端を越えると反対側へ回る。Maya が受ける bool・float の `relative` は TypeError で拒否する)。
  並びは Transform・Shape・中間オブジェクトを区別せず親の直接の子すべてを数え(同じ種類だけを返す `getSiblings()` とは別)、
  ワールド直下は `cmds.ls(assemblies=True)` の並び(`MItDag` の幅優先の深さ1。既定のカメラを含む)で数える。
  インスタンスは保持パスの親の下だけを変える。親の側から子の並びをまとめて決めるメソッドは置かない。
  `getShape(index=0, intermediates=False)` は自身がShapeなら引数を無視して自身、Transformは派生側の実装、無効なindexはNone。
  `collectSkinClusters()`(DagNode)は廃止し `SkinClusters(node.getSkinClusters())`、
  `getAssignedObjects()`・`getMaterials()` は廃止し `getShadingEngines()` の結果に `ShadingEngine.getMembers()/getShader()` を使う。
  二重入口のうち `show()/hide()` と `setVisibility(state)` は両方残す。6.0.0でPlugの `lock()/unlock()`・`mute()/unmute()` は廃止し、
  `setLocked(state)`・`setMuted(state)` に一本化した(`show()/hide()` は残し、`isHidden()` をその判定にした)。
  `isConnected(source=, destination=)` と `isSource()/isDestination()`、切断3本(`disconnect/disconnectInput/disconnectAll`)は
  戻り値・no-op規則が違うので統合しない。
- 2026-10-23のユーザー指定により、独自の判定は正式な `isX` へ一本化する。
  is省略入口は提供せず、説明・使用例・Sphinxも実際の正式名を使う。
  判定本体の引数・戻り値・フラグ、OpenMaya/外部SDKの標準名と他クラスの別APIは維持する。
- 2026-10-09のユーザー指定により、mlibの変換APIはMayaの `translate/rotate/scale` 表記へ統一する。
  クラスは `Translate/EulerRotate/Scale`、取得・設定は `getTranslation/setTranslation`・`getRotate/setRotate`・`getScale/setScale`、
  対応する独自のコンパウンドアトリビュート名・内部メソッド・ファイル・内製利用側も揃える。
  ただし位置の取得・設定は6.0.0から `getTranslation/setTranslation`(旧 `getTranslate/setTranslate`。別名は置かない)とする。
  既定 `at=2` は回転ピボットの位置(MayaのLocal Axis表示やコンストレイントがノードの位置とする基準)で、
  translateチャンネルの値(`node.t.get()`)とは異なるため、チャンネル名と同じ名前にしない。
  `getRotate` は常に `EulerRotate` を返す(6.0.0で `unit` 引数を削除。度は `getRotate().asDegrees()`)。
  移動・回転・スケールのPlugは `getPlug("translate")` 等で明示取得する。旧独自名・旧importの互換入口は残さない。
  OpenMaya標準名、Maya標準のフラグ・アトリビュート名に忠実な `useEulerRotation` 系、既存引数・単位・Undo・戻り値の意味は維持する。
  `Quaternion.asEulerRotate()` は標準の `asEulerRotation()` へ委譲する。
  shearも2026-10-26にMayaのアトリビュート名へ揃え、`getShear/setShear`(旧 `getShearing/setShearing`)とする。
- メソッド内のアトリビュート表記は `Attr/Attrs` に統一する。追加分を表す `Extra`(旧 `getExtraAttrs`)は
  2026-10-26の集約で対象が無くなり、ユーザー定義アトリビュートは `getPlugs(userDefined=True)` で列挙する。
  `getT/setT`・`getQ/setQ`・`getX/setX`等の短縮アクセサーは設けず、正式な長名を使う。
- 型変換は `as` 接頭辞。コピーを返す数学操作は `inverse/normal/mirror`、自身の更新は
  `invertIt/mirrorIt` の形式とする。OpenMaya標準の `Vector.normalize()` は例外として維持する。
- ミラーの `axis`(`Vector/EulerRotate/Quaternion/Matrix.mirror(It)`・`Transform.mirrorTransform`・`Joint.mirror`・
  `SkinCluster.mirrorWeights`・`util.mirrorArguments`)は、反転する軸(`"x"`・`"y"`・`"z"`、0/1/2)とミラー面
  (`"YZ"`・`"XZ"`・`"XY"`)のどちらの書き方も受ける(6.0.0)。対応は x⇔YZ、y⇔XZ、z⇔XY で、面の文字の順序と
  大文字小文字は問わない。解釈は `util._mirror_axis` の1か所にまとめる。2文字は常にミラー面で、
  旧来の複数軸の同時反転(`"xy"` で x・y を反転、`"xyz"`)は受けない。
- 数学値の戻り型は継承メソッドも対応するmlib型へ統一する。数値・真偽値・生API取得入口、
  対応型のないMPoint/単位値/クラス定数は維持する。ゼロ値などの演算条件は変更しない。
- 3.0.0で、mlib独自メソッドの短縮名の別名引数(`ws`・`idx`・`src`・`dst`・`attrs`・`f`・`r`・`scn` 等)を廃止し、
  長名(`worldSpace`・`index`・`source`・`destination`・`attributes`・`force`・`relative`・`skipConversionNodes`)だけにした。
  短縮名の別名はMayaコマンドのフラグを受ける入口だけに置く(「内部実装の定型」の「別名引数の書き方」)。
  2026-11-11のユーザー指定(12.2.0)により、`worldSpace` を受ける公開メソッドはすべて短縮名 `ws` も受ける。
  既存の接続方向フラグやOR/AND規則は維持する。
- メソッド名の表記と、処理の意味は別に確認する。同名のMaya APIと意味が異なる複合操作は説明を明記し、必要なら専用名に分ける。
- Mayaのコマンドフラグは標準表記を使う。今回の表記統一で既存の独自キーワード引数を一律変更しない。
- om2から継承・オーバーライドする名前、`__init__`等のPython特殊メソッド、`dump`/`loads`等の標準APIは維持する。
  ログの公開関数も5.0.0からlowerCamelCase(`getLogger`・`raiseWithNotify`)とし、例外にしない。
- JSONの保存キー・データクラスの保存フィールド・外部形式・パッケージ名・テスト探索名は、公開メソッドの改名に巻き込まない。
- 旧名の互換別名は残さない。内製使用側・テスト・ドキュメントを同時に更新し、`mlib.reload()`後も廃止名を公開しない。
- Maya照会はメソッド、保持値はプロパティ。シーン編集は明示的なメソッドにする。
- オブジェクト層はcm・角度の数値は度(5.0.0)・時間の数値は現在のUI時間単位のフレーム(6.0.0)、数学層はOpenMayaの概念(角度rad)、コマンド層はmaya.cmdsの単位・フラグを基準にする。
- 通常更新はcmdsによるUndo対応、対応する`fast=True`はom2によるUndoなし更新。同じ入力の意味・検証を維持する。
  読み取りはom2を基本とし、書き込み系の公開メソッドは原則 `fast` 引数を持つ。`fast` を持たない書き込みは
  om2に同等機能が無いものに限り、理由付きの一覧を「判断に迷う場合」に置く。
- 日本語Google形式docstringで引数・戻り値・副作用を説明する。Mayaのattributeは「アトリビュート」と表記する。
- mlibにQt依存・独自Mayaプラグインを追加せず、ノード・Plug・Componentの共通処理は各基底へ集約する。

### 内部名・文字列・docstringの書式

2026-10-23のユーザー指示により、内部関数・内部メソッド・ローカル変数はsnake_caseを基本とする。
公開名・既存公開引数・Mayaフラグ・OM2標準名・拡張プロトコル・保存キーは変更しない。
インデントはスペース4とする。文字列は原則ダブル引用符、単純な値の埋込みはf-stringを使う。
エスケープが減る引用符、raw正規表現、外部形式、数値書式や動的な書式には必要な表記を使う。
既存の引数評価順・参照回数を保つ必要がある複数引数のformatも維持する。
ログは `logger.warning("処理に失敗しました: %s", error)` のように標準loggingの遅延書式へ渡す。
改行形式はGitの設定を尊重し、書式整理だけの目的で全ファイルの改行を変更しない。

docstringは概要、必要な詳細、`Args:`、`Returns:`または`Yields:`、`Raises:`、
必要時の`Note:`・`Examples:`の順を基本にし、見出し間に空行を入れる。
引数の説明は署名の順に書き、self/clsを除く公開引数・単位・既定動作・別名を説明する。
値を返さない処理も `Returns: None`、必ず例外を送出する処理は `NoReturn` と明記する。
`fast/safe/get`等で返却・副作用・対応範囲が変わる場合は条件ごとに説明する。
OM2転送は標準APIへの委譲とmlib戻り型の違いを短く説明し、内部の小さなクロージャへ長い定型文を強制しない。
関数の型情報はdocstringを基本とし、型注釈の全面導入を要求しない。
dataclassフィールド・TYPE_CHECKING下の保持値・補完に必要な `Node.__getattr__` のAny注釈は別の用途として維持する。

### 検証・通知・出力の境界

通常の入力検証と下位処理の失敗は、対応する型の `raise` で呼出し側へ渡す。
捕捉して戻り値・検証結果・診断へ変換する失敗に画面通知を追加しない。
利用者へ通知して中断するツール側の入口では `logger.raiseWithNotify` を使う。
mlib本体は例外を送出するだけで、同じ内容を `logger.error` で重ねて表示しない(5.0.0でNode名解決失敗の通知も外した)。
Script Editorのエラー表示は、mlib内部のフレームを省いて利用者がmlibを呼んだ行を示す
(`maya.utils.formatGuiException` を包む。環境変数 `MLIB_FULL_TRACEBACK=1` で省略しない)。例外オブジェクトのトレースバック自体は変更しない。
`logger.error` は通知のみで例外を送出しない。復旧の二次失敗は必要時にwarningとし、元例外を優先する。
広いexceptは拡張単位の隔離・後始末・再送出などの境界に限定し、通常の検証では具体的な例外を扱う。

診断ログと通知は `mlib.logger` に集約する。進捗表示の指定streamへの描画やJSON等の保存出力は
診断ログとは別の機能であり、その出力先・描画・戻り値の契約を保つ。
例外メッセージとログの文言はmlib内で日本語に統一する(2026-11-14のユーザー指定。2026-10-27に英語へ統一していたものを、docstring・文書と同じ日本語へ揃えた。Maya 2022・2025のScript Editor相当の出力で文字化けしないことを確認済み。Maya自身のエラーは英語のまま。形式は下記「例外の4分類と文言形式」に従う)。
通常raiseをすべて通知付きへ置き換えたりしない。

### 2026-11-15の戻り値・引数の統一(ユーザー指定)

公開メソッド1186件の署名と戻り値を機械的に集めて、メソッドごとのブレを直した。決まりの正本はmlibの指示ファイル
(「メソッドとプロパティ」の戻り値の決まり・「引数の規則」・「複数形」)。

- **set系は値を返さない**(PyMEL・cymelと同じ)。約270メソッドの「自身を返す」をやめた。つなげて書いていた利用側は1行ずつに直す。
  `get=True` の計算値・`safe=True` の失敗数・作ったものや相手を返すメソッドはそのまま。
- **`get=True` は数学型**: `setTranslation` はTranslate、`setRotate`・`setQuaternion` はEulerRotate(rad)、`setScale` はScale、`setShear` はShear。
  `setQuaternion` の `unit`(戻り値の単位だけに使っていた)は削除した。
- **一覧は複数形のクラス**: `getChildren`・`getShapes`・`getParents`・`getHistory`・`getPlugs`・`getInfluences`・`getSkinClusters`・
  `getChainFromHere`・`getConnections`・`getDestinations` など約60メソッド。listと比べる `==` はそのまま使える。
- **複数形にlistのメソッド**: `append`・`extend`・`insert`・`remove`・`pop`・`index`・`count`・`clear`・`reverse` など。
- **strでなくオブジェクト**: `ObjectSet.getMembers` と集合演算(アトリビュートはPlug、コンポーネントは範囲ごとのVertices等)、
  `Joint.getTransferTarget`(Joint)、`Plug.getAnimLayers`(Nodes)、`PluginPackage.loadPlugins`(Plugin)。
  `Transform.deleteConstraints` は消したノードの名前のまま(もう存在しないのでオブジェクトにできない)。
- **角度のget**: `AimConstraint.getRestRotate`・`getOffset` はEulerRotate(回転順序はconstraintRotateOrder。Maya 2025で、offsetがこの順序で
  掛かることを確かめた)。`unit` 引数は削除。setはEulerRotateも受ける。`Joint.setPreferredAngle` に `fast`・`check` を足した。
- **キーワード専用**: `safe`・`get`(Transformのset系・`Plug.set`)、`type`(`getSets`・`getHistory`・`Selection.getNodes`)、`getConnections` の全フラグ、
  `force`(`Plug.connect`・`disconnect`・`delete`・`Plugin.unload`・`Joint.connectInverseScale`・`Place2dTexture.connectTexture`)、
  `transferToParent`(`SkinCluster.removeInfluence(s)`)、`geometryIndex`、`index`(`AnimCurve.removeKey`・`moveKey`)、
  `locked`/`keyable`/`channelBox`(`setAttrFlags`)、`leaf`(`Plug.setLocked`・`setKeyable`・`setChannelBox`)。
- **残りの引数もキーワード専用**(同日の追加の指定): `normalize`(`SkinCluster.mirrorWeights`・`pruneWeights`・`setVertexWeights`)、
  `colorSet`(`Vertex.getColor`・`setColor`・`Mesh.getVertexColors`)、`vertices`(`Mesh.setVertexColors`)、`uvSet`(`Mesh.reorderVertices`・
  `getUVShells`・`getUVAtPoint`・`getPointAtUV`)、`relative`・`add`(`setParent`、`BlendShape.addInBetween`)、`children`・`zeroScaleOrient`
  (`Joint.orient`・`assumePreferredAngles`)、`mode`・`missing`(`Selection.select`)、`aimAxis`・`upAxis`(`Quaternion.fromRollBend`・`asRollBend`)、
  `tolerance`(`Face.isZeroArea`・`BlendShape.reduceTargetDeltas`・`Mesh.reorderVertices`・`getMirrorVertexMap`・`NurbsCurve.getLength`・
  `getCollocatedCVGroups`)。`worldSpace` は位置引数のまま残した(`getMirrorVertexMap(axis, worldSpace)` のように前へ詰まる)。
  数学型の `isEquivalent(other, tolerance)`・`isIdentity(tolerance)` などは、OpenMayaと同じ位置引数のままにした。
- **`fast`・`check` の追加**(同日の追加の指定): `Transform.setRotateOrder`(fastは `MFnTransform.setRotationOrder`。2種類のノード×回転順序36通り×
  preserveの有無で通常の経路と一致)、`Joint.setDegreesOfFreedom`・`setInfluenceLocked`、`SkinCluster.setInfluencesLocked`。
  単純なアトリビュートの書き込みで、fastが約2.5倍速い。`setDegreesOfFreedom` の書き込み前の確認は `check=True` のときだけにした。
  足さなかったもの: `Plug.setMin`・`setMax`・`setSoftMin`・`setSoftMax`(定義の編集で、7.0.0で `setEnumNames` から外したのと同じ種類)、
  `Transform.setLimits`(OpenMayaで書いても速くならないと以前に確かめてある)。
- **単独の角度は数値+`unit`**: `Camera.getFieldOfView`・`Transform.getLimits` は、回転ではない単独の角度なので、`Plug.get` と同じく
  数値と `unit` 引数(既定は度)のままにした。EulerRotateで返すのは回転(3成分)だけ。
- **`addAttr` の近道**: めったに使わないフラグが1つも指定されていないときは、46組ある長い名前と短縮名の突き合わせを飛ばして、
  よく使う7組(attributeType・dataType・defaultValue・keyable・maxValue・minValue・shortName)だけを突き合わせる。型名の集合・正規表現・
  単位の対応表はモジュールの定数にした。動きは変えていない。1回あたり38.7→34.6µs(cmdsは17µs。`getPlug=False` は26.8µs)。
- **`mlib.delete` の削除前の確認は外さない**: Maya 2025で確かめたところ、`cmds.delete` はロックされたノード・ロックされた子を持つ親・
  既定のノードを渡しても例外にせず、エラーを表示して黙って残す。`MDagModifier.deleteNode` はロックされたノードを黙って残し、
  ロックされた子を持つ親は親だけを消す。確認を外すと「例外にならずに消えない」になるので、`check` に従わせない。
- **計測の注意**: ベンチマークの絶対値は、計測時のPCの状態で3〜4倍変わる(同じコードで全項目が動いた)。比べるときは、
  変更前の写し(`run.py --mlib-source head --commit <コミット>`)と今のコードを続けて交互に計る。
- **オン・オフの引数名**: `state`(既定True)。`Plug.setLocked`・`setKeyable`・`setChannelBox` の `val`、`setShadingOverride` の `enabled`、
  `Edge.setSmooth` の `value` を改名した。
- **`check` の抜け**: `setVisibility`・`setOutlinerVisibility`・`setOffsetParentMatrix`・`mirrorTransform`・`Plug.reset`・`setIfChanged`・
  `resetAttrs`・`Joint.setRadius`・`setSegmentScaleCompensate`・`AimConstraint`・`Constraint.setWeight`・`Locator.setPosition`・
  `Keyframe(s).setTangent`・`SkinCluster.setVertexWeights`・`File` と、`Nodes` の `setOverrideColor(s)`・`setOutlinerColor(s)`・
  `setVisibility`・`setParent`・`resetAttrs`。`Nodes.setAttrFlags` に `children` を足した。`AimConstraint` の書き込み前の
  ロック・接続の確認は `check=True` のときだけにした。UV・頂点カラーは切り替える事前確認が無いので `check` を持たない。
- **リファレンスの読み込みは `prompt=False`**: `Reference.replaceFile`・`load`・`removeEdits` の再読み込み・`createReference` は、
  GUIでも「Reference file not found」などの確認ダイアログを出さず、読み込めないときは例外にする(GUIテストが止まって見つかった)。
- **速度**: 取得系を複数形で包んだ後も、ベンチマーク65項目は変更前と同等。`Transform.getShape` は複数形を作らず中身のlistを直接使う。

### 2026-11-16の使い方の見直し(ユーザー視点の調査から)

ユーザーが書きそうなスクリプトを約50通りMayaで動かし、戸惑う点を洗い出して決めた(ユーザー指定)。

- **角度の往復は文書で説明する**: EulerRotateは度で表示するが、`list()`・`tuple()`・添字・`.x` の中身はラジアン。3つの数値をset系へ渡すと
  度として扱うので、`setRotate(tuple(getRotate()))` は値がずれる(例外にならない)。動きは変えず、`getting_started` に警告の節を置いた。
  正しい書き方は、オブジェクトをそのまま渡すか `.asDegrees()`。
- **listのメソッドと同じ名前の操作は改名**: `ObjectSet.clear` → `removeAllMembers`、`NurbsCurve.reverse` → `reverseDirection`。
  複数形から呼ぶと、シーンではなく集まりを操作してしまうため(`sets.clear()` が集まりを空にするだけになっていた)。
  単数のクラスには、listのメソッドと同じ名前の公開メソッドを置かない。
- **古い書き方の案内はしない**: 以前の引数名(`safe`・`val` など)を受けて新しい名前を案内する処理は入れない。古い記述は消す。
- **全部ジョイントならJoints**: `Nodes._wrap` と `mlib.ls` は、要素がすべてJointならJoints、すべてSkinClusterならSkinClustersにする
  (`joint.getChildren().sortedByDepth()` が使える)。自動で決まった型の集まりは、型の合わない要素を足すとNodesへ戻る
  (`mlib.ls("joint1") + [cube]` が中身によってTypeErrorにならないようにする)。自分で作った `Joints([...])` は今までどおり拒否する。
- **Plugsも要素へ転送**: `plugs.get()`・`plugs.set(0)` のように、自分に無い公開メソッドの名前を各Plugへ転送する(Nodesと同じ決まり)。
- **名前の一覧**: Nodes・Plugsとも `getNames()`・`getFullNames()` の両方を持つ。コンポーネントは `getNames(*, full=False, compact=False)` の1つ
  (2026-11-23 の共通化で `getFullNames()`・`getCompactNames()` をまとめた。末尾の「メソッドの共通化」)。

### 2026-11-14〜15の速度の見直し(Undoチャンク・接続・Transformation)

cmds・OpenMaya・他のライブラリとの速度比較(ローカルの `docs/research/benchmark-2026-10-25/RESULTS-2026-11-14.md`)から決めた。

- 2026-11-14のユーザー指定により、Mayaのコマンドを1回だけ呼ぶ操作ではチャンクを開かない(1回のコマンドは、チャンクが無くても1回の Undo で戻る。
  `cmds.undoInfo` の3回の呼び出しを省くため)。`_edit_context(name, fast, single=True)` か、複数のコマンドになる場所だけの `undoChunk` で書く。
  対象は `Plug.set`・1件の `disconnect`・要素以外への `connect`・`setFlags`/`setLocked`・`setKey`・親を指定しない `createNode`・
  `Node.rename`・`Transform.setParent`/`setTranslation`/`setRotate`/`setQuaternion`/`setMatrix`(書くチャンネルが1つのとき)。
  Undo の表示名は Maya の既定になる。呼び出したメソッドと対象から表示名を作る処理は置かない(チャンク名は決めた名前をそのまま付ける)。
- 接続前の値を Undo へ記録する書き込み(`Plug.connect`)は、接続先がマルチアトリビュートの要素かその下のときだけ行う。
  それ以外は、接続の Undo で Maya が元の値へ戻す(Maya 2022〜2027で確認。`blendWeighted.input[n]` のような要素は値が0になる)。
- `Transform` の translate・rotate・scale・shear・ピボットは `MFnTransform` でまとめて読み、この4つのチャンネルへの書き込みは
  内部単位の値を直接 `cmds.setAttr`(fast は MPlug)へ渡す。Maya が拒否したときだけ、これまでの `Plug.set` の流れで例外にする。
- fast のスキンウェイト設定は `MFnSkinCluster.setWeights(normalize=False)` の1回で書く。`normalizeWeights` が interactive のときは
  書く間だけ none にして戻す。値が0の要素は Maya が削除する(読み取る値は0のまま)。
- `mlib.delete` は、有効な Node だけの入力(1個・list・tuple)を名前へ直さずそのまま使う。
- `Transformation` は `om2.MTransformationMatrix` を継承し、translate・rotate(回転順序つき)・scale・shear・rotateAxis・ピボット4種に加えて、
  Joint のための jointOrient と inverseScale を持つ(距離 cm・角度 rad)。値はプロパティで読み書きし、取得した値は複製。
  `matrix` プロパティは Maya の transform・joint のローカルのマトリクスと同じ決まりで合成する(jointOrient・inverseScale を含む)。
  継承した `asMatrix()` は om2 の計算のままで、この2つを含まない。om2 と同じ名前の `scale(space)`・`shear(space)`・`rotatePivot(space)`・`scalePivot(space)` は
  om2 のまま残し、値のプロパティは `scaleValue`・`shearValue`・`rotatePivotValue`・`scalePivotValue`(2026-11-26。それまでは同じ名前のプロパティで置き換えていた)。ノード側は `Transform.getTransformation()`・`setTransformation(value, *, fast=False)`(ローカルだけ)。
- `Transformation` は `{"type": "Transformation", "value": {成分名: [x, y, z], "rotateOrder": "xyz"}}` で書く。角度は度。
  既定値のままの rotateAxis・ピボット・jointOrient・inverseScale は書かず、読むときに既定値で補う。

2026-11-15の続き(アトリビュートの取り出し・追加・3成分の書き込み)。

- `Node.getPlug` は、静的アトリビュートの名前(`[` を含まないもの)を一度解決したら、ノードのオブジェクトごとに覚える
  (`Node._plug_cache`)。次からは持ち主・未解決の論理番号・型名を調べ直さず、覚えた情報で新しい Plug を作る
  (`Plug._static_entry`・`_from_static_entry`)。静的アトリビュートは削除も改名もできないので、ノードが有効な間は同じ結果になる。
  動的アトリビュート(削除・改名・同名での作り直しがある)とエイリアスは覚えない。登録した型のクラスは覚えず型名から毎回選ぶので、
  型の登録を後から変えても新しい登録が使われる。`node.tx`・`hasAttr` も同じ記憶を使う。返す Plug は毎回新しいオブジェクト。
- 単位の種類は `MFnUnitAttribute` を作らず、定義の apiType(`kDoubleAngleAttribute`・`kFloatAngleAttribute`・`kDoubleLinearAttribute`・
  `kFloatLinearAttribute`・`kTimeAttribute`)で見分ける。Maya 2025の全ノード型の静的アトリビュート(約6万7千件)と、
  addAttr で作る単位アトリビュートで、これまでの判定と一致することを確かめた。
- 子も要素も持たない Plug の `get()` は、単位の種類を初回だけ調べて、角度と時間の数値だけを換算する。
  `Double3Plug.get()` は、角度の子が無ければ換算を通さない。
- double2・double3 の通常の書き込みは、ロックや接続を前もって調べず、親への1回の `cmds.setAttr` を先に試す
  (`CompoundPlug._set_at_once`。UI 単位へ変換する関数は初回だけ子の定義から選ぶ)。Maya が拒否したときだけ書き込めるかを調べ、
  これまでと同じ例外にする。Maya は親への書き込みを拒否するとき、どの子も変えない(子のロック・子の接続・親のロックで確認)。
  書き込めない定義(`decomposeMatrix.outputTranslate` のような出力専用)は `setAttr` が拒否しないので、まとめた書き込みの対象にしない。
- `Node.addAttr` は、コマンドが1回で済む追加ではチャンクを開かない。子の追加・作った後の既定値・チャンネルボックスへの表示・
  プロキシの接続があるときだけ、1回の Undo にまとめる。
- 有効なノードから今取得した MPlug は `Plug._wrap_owned(node, mplug)` で包む(`Node.getPlug`・名前の文字列からの解決)。
  ノードが有効か・持ち主が合っているかの確認を省き、アトリビュートの有無と決まっていない論理番号は確かめる。
  クラスの選択は `Plug._target_class` の1か所にまとめ、`Plug(node, mplug)` と同じクラスになる。
- `Double3Plug` の値の型(Translate・EulerRotate など)は、静的アトリビュートでは Plug ごとに一度だけ名前から決める
  (動的アトリビュートは改名できるので毎回調べる)。UI の単位が内部単位(cm・rad)と同じときは、単位の変換を通さない。
- `Transform` は `MFnTransform` をノードごとに1つだけ作って持つ(`_transform_fn`。値は覚えない)。rotateAxis は
  `rotateOrientation` の1回で読む。fast の `setParent` は、書き込めるかの確認を translate・rotate・scale・shear の
  4つの親アトリビュートへの `isFreeToChange` にまとめ、書けないものがあるときだけ1つずつ調べてこれまでの例外にする。
  確かめた後の書き込みでは、確かめ直さない。
- 2026-11-15のユーザー指定により、fast の `setParent` は、ピボット(rotatePivot・scalePivot・rotatePivotTranslate・scalePivotTranslate)が
  すべて0のとき、新しいローカルのマトリクスを `MTransformationMatrix` でそのまま分解して `MFnTransform` で書く
  (`Transform._write_local_matrix_fast`)。今の値に近い Euler や、今の値と同じ符号のスケールは選ばないので、rotate・scale の値が
  通常の経路と違うことがある(ワールドの姿勢・回転順序・rotateAxis は同じ)。789 → 約225(Maya 2025、2000回のms。通常は約262)。
  ピボットのどれかが0でないときは、これまでの計算(`_matrix_channel_values`)で書く(約580で、通常より遅い)。
  通常の経路はピボットの値を動かし、fast はピボットを保って translate で合わせる。
- 2026-11-15のユーザー指定により、書き込む前の検査(値が有限か・書き込めるか)は既定では行わず、検査用の引数 `check=True` を
  渡したときだけ行う(cmds をそのまま呼ぶ薄いラッパーと同じ軽さにするため。`safe` は「失敗を例外にせず数える」ままで、検査は足さない)。
  fast でも既定では確かめない。段階を分けて進める。
  - **段階1(実装済み)**: `Plug.set`(単数・`CompoundPlug`・`Double3Plug`・enum・マトリクス)。`check=False` では
    `_require_finite_value` と `_require_writable` を呼ばず、Maya の拒否に任せる。`check=True` では、どの子も書く前に
    値が有限か・すべての子へ書き込めるか(ロック・入力の接続・書き込めない定義)を確かめ、何も書かずに例外にする。
  - 既定のときに Maya 自身がどう動くか(Maya 2025で確認): ロック・入力の接続があるアトリビュートは、cmds も OpenMaya の MPlug も拒否する
    (MPlug の文言は `(kFailure): Unexpected Internal Failure`。`fastWrite.set_plug` は、拒否されたときだけ理由を調べて
    `アトリビュートがロックされているか、接続されています` の例外にする)。NaN・無限大は cmds も MPlug もそのまま受け取る。
    出力専用の定義は cmds が拒否せずに書く。ノードのロック(`lockNode`)は MPlug では拒否されない(`require_editable` は残す)。
  - 範囲(min/max・enum の範囲)は、cmds は拒否するが MPlug は範囲外の値をそのまま書くので、fast の範囲の検査は `check` に関係なく残す。
  - 既定では、途中まで書いた状態が残ることがある: fast のコンパウンドアトリビュート(子を順に書くため、ロックされた子より前の子)、
    float3 などへの通常の書き込み(Maya の `setAttr` 自体が、拒否する前の子を書く)。double2・double3 の通常の書き込みは、
    Maya が拒否するときどの子も変えない。mlib が子ごとに書く経路(まとめた書き込みの対象外の値・uiUnits)は、`check` に関係なく
    子を書く前に全部の子を確かめる(途中まで書くのが mlib 自身の動きになるため)。
  - **段階2(実装済み)**: `Transform` の `setMatrix`・`setTransformation`・`setTranslation`・`setRotate`・`setScale`・`setShear`・
    `setQuaternion`・`setParent`・`setPivot`・`centerPivot`。`check=False` の fast は、translate・rotate・scale・shear へ確かめずに
    MPlug で書き、Maya が拒否したらこれまでの書き込みへ回して理由の分かる例外にする。`check=True` は `Plug` の書き込みを通して確かめる。
    fast の `setParent` は、`check=True` か、先に確かめるためだけの呼び出し(`validate_only`)のときだけ書き込めるかを調べる。
    `setPivot`・`centerPivot` は、通常の経路では常に確かめ(`cmds.xform` はロックされた成分を例外にせず飛ばすため)、fast は `check=True` のときだけ確かめる。
  - **段階3(実装済み)**: `AnimCurve.setKey`・`removeKey`・`setTangent`・`setInfinity`、`Keyframe.setValue`・`Keyframes.setValue`、
    `DrivenKey.setKey`、`BlendShape.setTargetWeights`・`setTargetDeltas`・`resetTargetVertices`・`reduceTargetDeltas`、
    `DagNode.setOverrideColor`・`setOutlinerColor`・`setDisplayType`・`setShadingOverride`、`GeometryFilter.setDeformerWeights`、
    ポイントの書き込み(`PointComponent`/`PointComponents` の `setPosition`(`axis`・`relative`・`each` を含む)・`mirror`、
    `Mesh.setPoints`・`mirror`、`NurbsCurve.setCvPositions`・`mirror`、`NurbsSurface.setCvPositions`、`Shape.scaleGeometry`、
    `Transform.scaleGeometry`・`mirrorGeometry`)、`SkinCluster.setWeights`・`pruneWeights`・`setBlendWeights`。
    どれも fast の中の `require_writable` を `check=True` のときだけ呼ぶ。入力ヒストリの有無・ノードのロック・番号や型の検査は `check` に関係なく行う。
  - **段階4(2026-11-22のユーザー指定)**: 複数のPlug・要素・ノード・形状へ順に書くメソッドは、`check=True` なら通常の経路と fast の両方で、
    書く前に対象を全部確かめて途中まで書かない(テストで、例外にはなるが手前の書き込みが残るものが見つかったため)。
    対象は `Transform.mirrorTransform`・`setMatrix`・`setTransformation`(回転順序も含む)、`Node`/`Joint`/`Nodes` の `resetAttrs`(明示したもの)、
    `Plug.reset`(コンパウンドアトリビュート)、`Constraint.setWeight`、`Joints.setRadius`・`setSegmentScaleCompensate`、
    `Nodes.setVisibility`・`setOverrideColor(s)`・`setOutlinerColor(s)`(`Nodes._forward` の `writes`)、通常の経路の
    `GeometryFilter.setDeformerWeights`・`SkinCluster` のウェイトの書き込み(`_set_weight_values_cmds`)、複数の形状を書く `mirrorGeometry` の fast。
    また、通常の経路で `check=True` でもロックを見ていなかった `AnimCurve.setKey`・`removeKey`・`setTangent`(と `Keyframe(s).setTangent`)と、
    ポイントの書き込みの通常の経路(`cmds.xform` は pnts・controlPoints のロックを見ずに書く)にも、fast と同じ確認を足した
    (`geometryEdit._require_points_writable`・`_require_control_points_writable`)。`check=False` の動きは変えていない。
  - `check` を付けていないもの(これまでどおり、変える前に確かめる): 複数のコマンドで補償値まで書き換える通常の経路
    (`Joint.jointOrientToRotate`・`freezeRotate`・`setDegreesOfFreedom`、`Transform.zeroTransformPivots`・`freezeToOffsetParent`)、
    インフルエンスの除去に伴うウェイトの移し替え、`Mesh.reorderVertices`、JSON からの復元、`require_editable`(リファレンス・ノードのロック)。
  - `check=False` の fast で、OpenMaya がロック・入力の接続をどう扱うか(Maya 2025で確認): MPlug の書き込みは拒否する。
    `MFnTransform` の `setTranslation`・`setRotation`・`setScale` は、ロックや接続のある成分を例外にせず飛ばし、ほかの成分は書く
    (fast の `setParent` は、ロックされたチャンネルがあるとワールドの姿勢が保たれない)。`MFnMesh.setPoints` は pnts のロックを無視して書く。
    `MFnSkinCluster.setWeights` などのまとめて書く関数も、要素ごとのロックを見ない。確かめたいときは `check=True` を使う。
- 将来、fast の書き込みを Undo に載せる拡張(`MPxCommand` を1つ登録し、実行と取り消しの関数を渡して Undo キューに載せる方式)を
  検討できるように、fast の書き込みは `core/fastWrite.py` の `set_plug`・`set_attr(fast=True)` と各クラスの `_<method>_fast` に集め、
  公開メソッドから OpenMaya の書き込みを直接呼ばない形を保つ。プラグインは今は実装・同梱しない(方針は変えていない)。
- 2026-11-15のユーザー指定により、`Transform.setTranslation(worldSpace=True)` を軽くした。
  - 基準点が translate(`at=1`)と回転ピボット(`at=2`)のときは、今の translate を読まない
    (「今の translate + (目標 − 今の基準点の位置)」を整理すると、`at=1` は目標そのもの、`at=2` は「目標 − ピボットのずれ」になる)。
  - 既定の呼び方(`at=2`・通常の経路・`safe`/`get`/`check` なし)で、回転ピボットとその移動がどちらも0のときは、
    `cmds.xform(worldSpace=True, translation=...)` の1回に任せる(`Transform._set_world_translation_at_once`)。
    transform・joint、スケールや鏡映した親、offsetParentMatrix、UI の単位(cm・m)、rotateAxis・scale の192通りで突き合わせ、
    ピボットが0の96通りは値が一致し、ピボットがある96通りは一致しない(`xform` は回転ピボットではなく原点を目標へ合わせる)ことを確かめた。
  - `xform` は、ロックや入力の接続がある成分を例外にせず飛ばす。そのため、translate へ書き込めないとき(`isFreeToChange` の1回で確かめる)は
    `xform` を使わず、これまでの書き込みへ回して例外にする(この確認は `check` に関係なく行う。既定で例外になる動きを保つため)。
- `Node.addAttr`(約106、cmds は46)と Plug 経由の translate 設定(約138、cmds は93)は、残りが引数の受け取り・名前の重なりの確認・
  値の検査・返す Plug の作成に薄く分かれていて、まとめて削れる処理は残っていない(2026-11-15のプロファイル)。

### 内部実装の定型(2026-10-27の表記ブレ統一)

2026-10-27の表記ブレ調査で確定した内部実装の書き方。公開APIの意味・戻り値は変えず、内部名・引数・例外文言・docstringを揃える。
既存コードと矛盾する場合はこの節を正とし、旧名は `grep` で0件にする(互換別名は残さない)。

#### fastの定型

- 署名は `*, fast=False` をkeyword-onlyの先頭に置く(型注釈なしの既定値は `fast=False`)。既存の位置が違うものは公開署名の順序変更になるので一度に動かさず、破壊的変更としてコミットメッセージに明記する。
- 本体の冒頭で `_require_bool(fast, "fast")`(`decorator.py`)を呼ぶ。委譲型(show/hide・ScalarGraph等)も省かない。
- Undo文脈は `with _edit_context("mlib<Class><Method>", fast):`(`decorator.py`。`nullcontext() if fast else undoChunk(name)` の1行化)で包む。`undoTransaction` はUndo無効時に拒否する必要がある構築処理(reorderVertices・container系)だけに使い、`transaction=True` と理由コメントを付ける。
- 対象解決・値検証はwithの内側に1回だけ書く(fast=Trueではnullcontextなので挙動は変わらない)。書込み直前に `if fast:` で `_<method>_fast` / `_<method>_cmds` へ分岐し、内側の更新先へ `fast=fast` を明示的に渡す。未対応は変更前にNotImplementedErrorで拒否する。
- Undoチャンク名はメソッドが `mlib<Class><Method>`(クラス名・メソッド名どおり。短縮やクラス名違いは不可。単数Jointが複数形の名を使わない)、モジュール関数・cmdsが `mlib<Func>`(`mlibCreateNode`・`mlibDelete`・`mlibDuplicate`・`mlibSelect`・`mlibCreateReference`)。ドット区切り(`mlib.<Class>.<method>`)は使わない。計算ノードの共通setterは `"mlib" + type(self).__name__ + "<Method>"` を呼出し側から渡し、Undoキューで区別できるようにする。
- `_Calculation.set_value/connect` のfastも既定 `False`。

#### 例外の4分類と文言形式

| 分類 | 例外型 | 対象 |
| --- | --- | --- |
| 型違い・別名競合・必須欠落 | `TypeError`(別名は `util._ArgumentError`。TypeErrorの派生) | boolでないfast、Mayaフラグの長短名の同時指定、必須引数の不足、受け付けない入力型 |
| 値違い | `ValueError` | 空文字、範囲外、特異マトリクス、空集合、fastと無関係な非対応値(`scaleGeometry`・`addTargetDeltas`・mesh reorderの制限) |
| シーンの状態 | `RuntimeError` | ロック、接続済み、参照、削除済み・無効ノード、不在 |
| 実装上の未対応 | `NotImplementedError` | fast経路で扱えない操作・フラグ(変更前に拒否) |

- 「空でない文字列で指定してください」系は非strをTypeError、空文字をValueErrorに分ける。公開例外型の変更は破壊的変更としてコミットメッセージに明記する。
- 文言は日本語でf-stringを使い(`"..." + name` の連結は不可)、対象名は末尾に `: <getFullName() または plug.name()>` で付ける。引数名・型名・メソッド名・ノード型名などの識別子は英字のまま書き、日本語との間に空白を入れない。括弧は半角。用語はdocstringと同じ。
  - 型違い: `<arg>は<型>で指定してください`(`_require_bool` は `fastはboolで指定してください`)
  - 別名競合: `'<long>'と'<short>'は同時に指定できません`(長→短の順)
  - 必須欠落: `必須の引数がありません: '<long>'`
  - 値違い: `<arg>は<条件>で指定してください` または `<条件>を指定してください`
  - 状態: `<対象>がロックされています|接続されています|リファレンスです: <名前>`、`無効な<type>のため、<動作>はできません`(`Node._require_valid(action)`。`action` は「名前の変更」「アトリビュートの取得」のような名詞句)
  - fast非対応: `fastの<publicMethodName>は<条件>に対応していません`、`fastの<publicMethodName>は次のフラグに対応していません: a, b`(説明語ではなく公開メソッド名を書く)
  - 英語の文は残さない。`_tools/check_mlib_layout.py` のL060が、日本語を含まない英語の文(英単語が2つ以上続くもの)を報告する。ログ(`logger.warning` 等)も日本語で書く。snapshotの報告に入る理由のうち `"locked"`・`"connected"`・`"not settable"` は戻り値として決めた値なので英字のまま。
- テストが文言を `assertRaisesRegex` している箇所は同時に更新する。

#### 別名引数の書き方

- 短縮名の別名はMayaコマンドのフラグを受ける入口だけに置く(3.0.0)。対象は `cmds/` の `ls`・`createNode`・`duplicate`・`select` と作成関数(`createIkHandle`・`createCurve` 等)のフラグ群と、Mayaコマンドへフラグを渡す `Node.addAttr`・`Transform.addConstraint`・`Transform.makeIdentity`・`Plug.setKey`・`DagNode.reorder`(`f/b/r`)、Mayaの `listConnections`/`connectAttr` のフラグを受ける `getConnections` の `s/d/c/t/et/scn`、`Plug.connect/disconnect` の `f/l/na`。これらはMayaと同じ長短の名前を受けるのが契約。`delete` はフラグを受けない。
- cymel 由来の短い引数名だった `Transform.getMatrix` の `p`・`inv` と `getQuaternion`/`setQuaternion` の `ra`・`r`・`jo` は、12.3.0 で長名(`parent`・`inverse`・`rotateAxis`・`rotate`・`jointOrient`、keyword-only)を足し、短い名前は既存のコードのため別名として残す。`getTranslation`/`setTranslation` の `at` は単語として扱い、長名を足さない。
- それ以外のmlib独自メソッドは長名だけを持ち、長名に通常の既定値を置く(`index=0` 等)。短縮名の別名・`_UNSET` による省略判定を追加しない。
- 例外として、`worldSpace` を受ける公開メソッドはすべて短縮名 `ws` も受ける(12.2.0、2026-11-11のユーザー指定)。署名は `worldSpace=_UNSET, ..., *, ws=_UNSET` とし、docstringの後の最初の行で `worldSpace = _pick_alias(worldSpace, ws, "worldSpace", "ws", default=False)` と選ぶ(既定値は従来の値)。`ws` は keyword-only。`__tests__/noMaya/test_mlib_publicArgs.py` の `test_world_space_has_short_alias` が、`worldSpace` を持つ公開defが `ws` も持つことを検査する。
- 上記の入口では、署名は長名・短名ともkeyword-onlyの `_UNSET` を基本とし、選択は `_pick_alias(long, short, longName, shortName, default=_UNSET)`(`decorator.py`)で行う。インラインの `if ... is not _UNSET` 展開は書かない。競合は `_ArgumentError("'<long>'と'<short>'は同時に指定できません")`、`default` が `_UNSET` で両方未指定なら `_ArgumentError("必須の引数がありません: '<long>'")`。`_UNSET` は `util` が唯一の定義で、False/Noneの明示指定と省略を区別するためだけに使う。
- Mayaコマンドへ `**kwargs` で渡すフラグ群は `_merge_flags(kwargs, pairs)` で辞書へ詰めてよい。
- 空間指定のbool検査は `util._world_space()`(TypeError)に一本化し、二重検査を書かない。
- 内部関数へ渡すときも `fast`/`worldSpace` 等の同じ名前を使い、`world_space` のような別名を増やさない(core層のsnake_case関数の既存引数 `ws` は維持)。

#### 内部名の規則

- 検証は `_require_<条件>`(例外を送出し、戻り値は無しか検査済み値)。`_validate_*`・`_check_*` で例外を送出する関数は `_require_*` へ改名し、boolを返す判定は `_is_*`/`_has_*` にする。登録プロトコルとしてDESIGN/CLAUDE.mdに名のある `Nodes._validate_inputs`・`attributeEdit.validate_extra_attribute` は維持する。`_validated_*`(`_validated_flags` 等)は検査済みの値を返す検証の名前。
- 変換・解決は `_resolve_<対象>`(`_resolve_mvector`・`_resolve_mesh`・`_resolve_input_or_none`)。`_as_*`・`_coerce_*` は使わない。
- 書込みの実装分岐は `_<method>_fast` / `_<method>_cmds`(`_direct`・`_fast_xxx` 前置は使わない)。
- function setの取得は `_<kind>_fn`(`_dependency_fn`・`_geometry_fn`。キャッシュ付きでも `_cached_` は付けない)。`om2.MFnDependencyNode(self.mnode())` を直接書かず `_dependency_fn()` を使う。
- 内部専用の引数は先頭 `_`(`_fn=None`・`_writable_checked=False`)。公開defには置かない。
- 略語を使わず完全語にする(`_jnt_index`→`_influence_index`、`_xfer_pair`→`_transfer_pair`、`_all_verts`→`_all_vertices`、`_attr`→`_full_attr_name` 等)。
- 入力の名前解決は `Node._from_name(value)`・`Node._input_name`・`Nodes._resolve_inputs` を使い、`Node(n)` で二重解決しない。`cmds` へ渡す名前はDAGノードでは `getFullName()`。
- core層(`core/*.py`)の関数名はsnake_case(`set_positions`・`require_writable`・`require_range`)。

#### docstringの固定文と項目順

- 項目順は `Args → Returns(Yields) → Raises → Note → Examples`。見出し無しの自由文(Returns/Raisesの後)はNoteへ移し、非標準見出しは置かない。
- 1行目は動詞文「〜する。」。get系は「〜を取得する。」、set系は「〜を設定する。」。概要とReturnsの逐語一致は避け、Returnsは型と値の説明にする。
- 固定文:
  - `fast (bool): TrueはUndoなしのOpenMaya更新。既定False。`(内部関数へ転送するだけの引数は転送先を書いてよい)
  - `worldSpace (bool): Trueはワールド空間、Falseはローカル空間。`(Shape系は「Falseはオブジェクト空間」)
  - Mayaフラグの短名: `e (bool): editの別名。同時指定は不可。`(主引数側に「別名 ``e`` も使用可能」を重ねて書かない)
  - Raises: `TypeError: fastがbool以外の場合。`
  - `Returns:` の `None: 値を返さない。`(`Args:` があって値を返さない処理には必ず書く。「値は返さない」は使わない)
- Raisesの並びは `TypeError → ValueError → IndexError → RuntimeError → NotImplementedError`。
- 型表記は `list[Node]`・`tuple[float, float, float]`・`dict[str, Any]` のように要素型を書き、裸の `list`/`tuple`/`dict` は使わない。
- 用語はCGWORLDのMaya記事に合わせ「アトリビュート」「マトリクス」(determinantは「行列式」のまま)「クォータニオン」「コンストレイント」「ワールド空間/ローカル空間/オブジェクト空間」「番号」(インデックス・添字は使わない)「ウェイト」。括弧は半角、文の区切りは句点のみで半角スペースで区切らない。モジュール定数には `#:` を付ける。
- 2026-11-13のユーザー指定: mlibでPyMELの名前を書くのは文書の紹介文(`_docs/source/whymlib.rst`)だけとする。mlibのコード・コメント・docstring・メッセージ・テスト・ほかの文書・ファイル名・コミットメッセージには書かない(mlibの `noMaya/test_mlib_wording.py` が検査する。mlibの履歴からも削除済み)。他のライブラリで使われる名前への案内は「maya.cmdsやほかのライブラリの名前」のように書く。mlibの指示ファイルではこの名前を書かず「紹介文で比較に挙げる他のライブラリの名前」と表す。このワークスペースの文書(設計文書・`maya/external/pymel` の説明等)は対象外。

#### 共通ヘルパーの置き場

| 置き場 | 責務 | 主な内部ヘルパー |
| --- | --- | --- |
| `decorator.py` | fast/safe・フラグ正規化の内部補助、Undo文脈 | `_require_bool`・`_pick_alias`・`_merge_flags`・`_validated_flags`・`_edit_context`・`_undo_recording` |
| `util.py`(標準ライブラリのみ) | クラスに属さない値処理 | `_UNSET`・`_ArgumentError`・`_world_space`・`_finite`・`_finite_vector`・`_checked_tolerance`・`_checked_index`・`_unique_ordered`・`_rethrow_init_error` |
| `core/object.py` | 入力の存在・選択の判定 | `_exists`・`_selection_plug`・`_selection_component` |
| `core/fastWrite.py` | Plugへのom2書込み基盤 | `require_supported_type`・`require_writable`・`require_range`・`writable_compound`・`_ancestor_plugs`・`set_plug`・`set_attr`・`prepare_data` |
| `core/nodeEdit.py` | ノードの編集可否・削除検査 | `require_editable`・`check_deletion`・`_dag_descendants` |
| `core/geometryEdit.py`・`core/attributeEdit.py` | 形状・アトリビュートの編集基盤(スキンのfastの書き込みは `SkinCluster` の `_<method>_fast`。`core/skinEdit.py` は2026-11-27に削除) | `set_positions`・`validate_extra_attribute` |
| `nodes/node.py` | ノード固有の解決・検証 | `Node._from_name`・`Node._require_valid`・`Node._input_name`・`Nodes._resolve_inputs` |

共通化しないもの: `Node.delete`、`SkinCluster.mesh/mesh_path`・`Component.component_type`(core/common/cmdsが参照する内部契約)、`Version.isAtLeast` への委譲、cmds/ls.pyのフラグ列挙、core→commonのimport方向を作る単位変換の置換。

### 2026-10-09の利用者向け追加仕様

- 利用者視点の全体検討に対する「全て対応」の指示に基づき、既存型を次の操作へ渡す入力を追加する。
  SkinCluster.redistributeWeightsは先頭geometryのmeshに属するVertex/Verticesも受理する。
  SkinCluster.getWeights/setWeightsは同じ頂点指定を`vertices=`で受け付け、influence入力の未登録はValueError・頂点の混入はTypeErrorで検証する。5.0.0から、K個(influenceごとに1個)の値を複数頂点へ適用するには`broadcast=True`を明示する(暗黙の適用はValueError)。
  既存の整数・エイリアス・返却・単位・Undo・fast・途中更新は維持する。
- Selection.filterはcomponent正式名を追加し、既存記号・保持順・未知の型名の空結果を維持する。
  Mesh・NurbsCurveの単数/複数取得は正式getメソッドへ集約し、番号・型・戻り値を維持する。
- Namespace.createのparent指定は、Maya標準に従って作成先を完全名へ解決し、既存確認と返却も同じ名前にする。
  これは今回承認された意味変更であり、従来の「parentを返却へ反映しない」という制限を廃止する。
- ログのFormatter・例外詳細・stack情報はScript Editorへ、ビューポートはメッセージ本文を表示する。
  preservedSkinShapeのRuntimeError抑制は維持し、対象と失敗段階を通知する。
- 有効性・編集可否・保存データの適用能力・拡張の現在状態は専用の照会で区別する。
  既存getterの返却を平坦化したり、状態文字列の真偽評価を変更したりしない。

### ファイル・クラスのレイアウト規則

mlib・`mlib_*` のPythonファイルはPEP 8を基本にし、下記のプロジェクト固有の並び順と例外を使う。
2026-10-25のユーザー指示により、import位置・分類・関数内import・import形式・空白と改行を明文化する。
整理では依存関係と初期化順を維持し、名前・本文・デコレータの積み順・docstringを変えない。
`python maya/inhouse/mlib/_tools/check_mlib_layout.py --check` が、下記のうちruffに無い並び順を検査し、`--fix` がクラス内メンバーの並び替えを行う。
2026-11-13のユーザー指定により、空白(演算子・カンマ/括弧・引数指定・行末コメント)・空行・改行位置・引用符は `ruff format` が自動で直す(設定は `maya/inhouse/mlib/ruff.toml`、入口は `_tools/format_mlib.bat`)。
importの分類・並び替えと未使用名・Mayaのimport形式・未使用引数・pathlib・文字コードは `ruff check --fix` が担当する。
2026-11-14のユーザー指定により、選ぶルールと除いたルールを次のとおり決めた(`ruff.toml` が正本)。

**設定の安定性**: `required-version = "==0.17.5"` で別の版のruffは実行を拒否する(`requirements-dev.txt` の固定と対にし、
VS Code拡張が同梱する版で整形結果が変わるのを防ぐ)。`explicit-preview-rules = true` で、previewのルールはコードを明示したものだけ
有効にする(これが無いと、選んだ族の新しいpreviewルールがruffの更新で黙って増え、検査結果が変わる)。

**選ぶルール**: F・E4/E7/E9・W(誤りと空白)、I(import順)、B(壊れやすい書き方)、ICN(Mayaのimport形式)、ARG(未使用引数)、
PTH(pathlib)、C4(内包表記)、RET(returnの書き方)、UP(f-string等)、TC(型注釈だけのimport)、G・INT・LOG(ログと書式)、
PIE(不要な書き方)、ERA(コメントアウトしたコード)、DTZ(timezoneなしの日時)、PLE(実行時に壊れるもの)、PLW1514(文字コード未指定)、
RUF100(効いていないnoqa)、RUF022(`__all__`の並び)、RUF001〜003(全角と半角の統一)。

**除外**: `E741`(`l`・`f`・`i`はMayaの短縮フラグ)、`PLE0605`(ルートとcommonの`__all__`は実行時に組み立てる)、
テストの`C408`(cmdsへ渡す辞書を`dict()`で組む)。`logger.py`・`decorator.py`の`PTH`とテストの`PTH`・`B023`は前述のとおり。

**入れないルール**(件数は2026-11-14時点のmlib): D 7,525件・DOC 1,128件(docstringは日本語Google形式で、
`check_mlib_docs.py`・`check_mlib_doc_getter_names.py`が担当)、ANN 6,502件(型はdocstringに書いてスタブを生成する方針と衝突)、
EM 2,344件・TRY 1,173件(例外文言の規約と衝突)、N 1,837件(公開APIはlowerCamelCase。`test_mlib_publicArgs.py`が担当)、
TID252 1,616件(相対importは仕様)、FBT 373件(boolのフラグ引数はMayaの流儀)、PLC 314件(大半が`PLC0415`=意図的な関数内import)、
SIM 297件(`SIM108`の三項化は160字近い式になり読みにくい、`SIM105`の`contextlib.suppress`はtry/except/passより遅い、
テストの`SIM117` 254件は入れ子の`with`を1行へ繋げてPython 3.7では折り返せない)、S 404件(`S101`は内部整合性のassertで、
`S105`の6件は`token`という変数名への誤検知)、COM・Q(ruff formatが決める)、`format.docstring-code-format`
(`json/_animCurveData.py`のJSON構造の図解が4行→25行に展開され、`cmds/createJointChain.py`の折り返した例が1行に潰れる)。

**2026-11-22の追加(ユーザーと1項目ずつ、mlibの実際のコードを例に決めた)**: 族ごとではなく、コードを1つずつ選んで足した。
上の「入れないルール」は族ごとの判断で、ここで選んだコードはその例外。件数は2026-11-22時点で、すべて直してから入れた。

- Mayaのimportの別名をICNの表で固定する(`cmds`・`mel`・`maya_utils`・`om2`・`oma2`・`om1`・`oma1`・`omui`。別名なしも報告)。
  割れていたのは`maya.utils`(`utils`と`maya_utils`)・`maya.OpenMaya as om`・`maya.OpenMayaUI as OpenMayaUI`の5か所。
- `T20`(print): 本体は`logger`を使う(本体0件)。テストのランナーと`_tools`は結果を出すので外す。
- `E501`(160桁超え)は入れない(ユーザー指定)。残る長い行は日本語の例外メッセージとdocstringで、折ると検索しにくくなる。
- `BLE001`(`except Exception`): 本体だけ。後始末(コールバック・scriptJob・Undoチャンクの解除、拡張の読み込み、通知の書式)の11件は
  `# noqa: BLE001 <理由>`で残し、黙って別の値を返す2件(`maths/matrix.py`のAPI版の判定、`Transform._channel_equals`)は受ける例外を絞った。
- バグになりやすい書き方: `RUF012`・`RUF017`・`RUF034`・`PLW0642`・`PLW1641`・`PLR0124`・`PLC0206`。テストで`==`・`in`・`__hash__`の動きを
  わざと確かめる`PLR0124`・`PLW1641`・`SIM300`・`FURB171`はテストを外す。
- 書き方の統一: `SIM101`・`SIM102`・`SIM103`・`SIM114`・`SIM300`・`PLR1714`・`PLR5501`・`FURB171`(条件式)、`RUF015`・`RUF046`・`RUF021`・
  `PERF401`・`PERF402`・`FURB167`・`RSE102`(式とループ)、`D202`・`D205`・`D209`・`D301`(docstringの形。中身はL07x)。
- 好みが分かれるものもユーザーが選んだ: `RUF005`(`[a, *b]`。全体。ただし左側がmlibの型だと `+` は Vector の加算・複数形の連結なので、
  ruffの自動修正(unsafe)はテスト7ファイルで意味を変えた。`+` そのものを確かめるテスト5ファイルは対象外にし、Vectorの加算の2か所は
  `# noqa: RUF005 Vector の加算` にした。自動修正をかけたら、左側がlist・tupleかを必ず確かめる)、`PLW2901`(ループ変数の上書き。本体だけ)、`RUF059`(使わない値は`_`付き)、
  `SIM108`(三項演算子)、`SIM105`(`contextlib.suppress`)。2026-11-14の「SIM108は読みにくい・SIM105は遅い」の判断を改めた
  (SIM108は160桁を超える場合は報告しない。SIM105の本体の該当は回数の少ない2か所)。
- `check_mlib_layout.py`に独自検査を3つ足した: L053(公開の関数・メソッド・プロパティはlowerCamelCase、クラスはPascalCase、
  先頭が`_`の関数・メソッドはsnake_case。`core`と先頭が`_`のモジュール・クラスの中、関数の中の関数は公開の形を問わない。足した時点で0件)、
  L054(大文字の定数をlist・setで書かない。関数の中で書き足すか`global`で代入する名前は小文字。キャッシュ5件と`WeakSet`1件を小文字へ改名し、
  変わらない値なのに小文字だった`_package_name`・`_extension_pattern`を大文字にした)、L055(mlibの中のimportに別名を付けない。
  先頭に`_`を付けて隠すだけの別名は可。`geometryEdit as geometry_edit`の7ファイルと`Object as _InputObject`等の本体7ファイル・テスト4ファイルを直した)。
  ローカル変数の名前は検査しない(158件のcamelCaseは、公開の引数名を正規化して入れ直すもの)。
- コミット前のフックは置かない(ユーザー指定)。代わりに、mlibの指示ファイル・`CONTRIBUTING.md`とこのワークスペースの
  `CLAUDE.md`・`AGENTS.md`・`.github/copilot-instructions.md`に「コミットの前に必ず`format_mlib.bat --check --no-pause`を実行し、
  最後の行が`[OK]`であることを確かめる」と書いた。
`check_mlib_layout.py` に残すのは、ruffに無い検査(定数・`__all__`・`if TYPE_CHECKING:`の位置、クラス内メンバー順と対になる操作の隣接、
公開入口の入力assert、enumerate)だけとし、2026-11-14にruffと重なる検査(import順・空白・空行・名前付きlambda・pathlib・文字コード)を削除した。
関数内importの必要性・理由コメント、複数モジュールimport、ワイルドカード、インデント・末尾空白・長い式の改行をすべて検査するものではない。
`--snapshot`/`--compare` で整理前後の関数本体・import束縛・モジュール文が同一であることを確認できる(Maya不要。
実行方法は `maya/inhouse/mlib/__tests__/README.md`)。この比較だけでimport移動後の実行順や挙動の同一性は保証しない。

| 位置 | 規則 |
| --- | --- |
| import位置 | 原則、モジュールdocstringの後、定数・関数・クラス定義の前にまとめる。`from __future__` があれば通常importより先に置く。基本の順は docstring → `from __future__` → import → `if TYPE_CHECKING:` → `__all__`・定数 → 関数・クラス。初期化順に依存する例外は下記を参照。 |
| import群 | 標準ライブラリ → `maya.*` などの外部ライブラリ → mlib内部の3グループ。相対importと絶対名の `mlib.*` はどちらも内部に分類し、拡張では自パッケージも内部とする。グループ間は空行1行。グループ内は既存規則どおり `import x` 形式を先にまとめ、続けて `from x import y` 形式を置き、それぞれをモジュール名順(大文字小文字を区別しない。`..` は `.` より先)にする。例: `import inspect` → `import re` → `from functools import wraps`。 |
| 関数内import | 循環参照の回避・任意依存・Maya非依存の維持など、必要な理由がある場合だけ使う。その理由をimportの直前に短くコメントする。同じ理由の連続したimport群にはコメント1つでよい。 |
| import形式 | `import os, sys` のような複数モジュールのimportは1行ずつ分離する。`from x import A, B` は許可し、`from x import *` は禁止する。Mayaは `import maya.cmds as cmds`、`import maya.mel as mel`、`import maya.api.OpenMaya as om2` を使う。`from maya.api.OpenMaya import MSpace` のような個別名のimportは可。 |
| 定数 | 原則import群の直後。先行する関数・クラスを参照する対応表等は依存先の定義後に置く。説明は `#:` を使う。 |
| 空白・改行 | インデントはスペース4とし、末尾空白を残さない。長い式は原則 `()`・`[]`・`{}` 内で改行する。対象MayaのPythonが対応しない構文へは置き換えない。文字列中の空白や改行はデータとして保持する。 |
| 演算子の空白 | 代入・複合代入・比較演算子の前後は空白1つとする。例: `value = 10`、`value += 1`、`value >= 0`。通常の算術演算子全体には今回の検査を広げない。 |
| カンマ・括弧の空白 | 同じ行で次の項目が続くカンマの後は空白1つ。括弧の内側に不要な空白を置かない。例: `getValue(node, index)`。末尾カンマと括弧内の改行・字下げは許可する。 |
| 引数の既定値・キーワード指定 | 型注釈なしの既定値と呼出しのキーワード指定は `=` の前後に空白を置かない。例: `fast=False`。型注釈付きの既定値は `fast: bool = False` とする。 |
| 行末コメント | コードとの間に空白2つ以上、`#` の後に空白1つを置く。例: `index += 1  # 次の要素へ`。Sphinxの説明コメントは意味を保つため `#:` の記法を維持する。単独行のコメントや文字列中の `#` はこの検査の対象外。 |
| 名前付き関数 | `function = lambda ...` のように名前へ直接代入する場合は通常の `def` を使う。型付き代入・連鎖代入・代入式も対象とする。コールバック引数や既定値・戻り値・コレクション内のlambdaは許可する。 |
| 空行 | トップレベルの定義間は2行、クラス内のメンバー間は1行、`class` 行とdocstringの間は0行、デコレータと `def` の間は0行、3行以上の空行は使わない。ファイル末尾は改行1つ。クラス内に区切り線のコメント(`# ----- 比較` など)は置かず、下記の並び順で区分する。 |
| クラス内の順 | docstring → クラス属性 → `__new__`/`__init__`/`__post_init__` → その他の特殊メソッド → 公開 classmethod/staticmethod → property → 公開メソッド → 非公開メソッド(`_` 始まり。static/classmethodも含む) |
| 対になる操作 | `getX`/`setX`、`isX`/`setX`、`connect`/`disconnect*`、`lock`/`unlock`、`show`/`hide`、`addX`/`removeX`、`__eq__`/`__ne__`/`__hash__`、`__repr__`/`__str__`、`__getitem__`/`__setitem__`、`__copy__`/`__deepcopy__`、各演算子と `__r*__`/`__i*__` は隣接させる。property の setter は getter の直後。 |

- 公開メソッドの全体をアルファベット順には並べ替えない。対の隣接と上記グループ分けだけを行う。
- 関数内importは上記の理由を確認する。理由のある遅延import、`try/except ImportError`、
  `if TYPE_CHECKING:` の中身は機械的に先頭へ移さない。
- import文の間に実行文があり、その初期化順そのものが仕様の `__init__.py`(ルートと `core`・`cmds`・`nodes`・`plugs` の初期化)は
  import群の並び替え対象外。空行だけを整える(`--check` は「スキップ」として表示する)。
- それ以外の `__init__.py` も通常の規則で並べる。import群の途中にあった `globals().pop(...)`・
  `__all__ +=` のような、importの結果に依存しない文はimport群の後へまとめる
  (`common`・`maths`)。`nodes`・`plugs`・`cmds` の登録処理はimport群の後にあり、import群だけが並び替えの対象になる。
- `@dataclass` のフィールド順、`__str__ = __repr__` のような先行定義を参照する代入、
  `item_class = Node` のようなクラス属性は、参照先が先に定義される位置を維持する。
- `__all__` はPEP8の「import前」ではなく、import群の直後に置く(`__init__.py` の動的な
  `__all__` と位置を揃えるための意図的な逸脱)。`L005`は文字列の並び(`__all__ = ["A", "B"]`)だけを検査し、
  ルートの `__init__.py` のように他の名前から組み立てる `__all__` は定義の後ろでもよい。
- 行の長さは`ruff.toml`の`line-length = 160`で揃える(`ruff format`が改行位置を決める)。
- 検査コードは族で分ける。2026-11-14のユーザー指定で `L05x`〜`L08x` を追加した。
  - `L00x` 位置: `L004` 定数、`L005` `__all__`、`L006` `if TYPE_CHECKING:`。
  - `L02x` クラス内: `L020`〜`L022` メンバーの順と対になる操作の隣接、`L023` 並び検査をスキップしたクラス。
  - `L04x` 近代化: `L040` 公開入口の入力assert、`L041` 列挙の確認候補。
  - `L05x` 内部名と命名: `L050` 禁止した接頭辞・末尾、`L051` function setの直書き、`L052` 関数内importの理由コメント。
  - `L06x` 例外とログ: `L060` 文言の言語、`L061` `+` 連結、`L062` `logger.error` と `raise` の同居、
    `L063` Undoチャンク名、`L064` fastの受け取り。
  - `L07x` docstring: `L070` 見出しの順、`L071` Raisesの並び、`L072` 1行目の句点、`L073` fastの固定文、
    `L074` 用語、`L075` 公開定数の説明、`L076` `Args:` の名前と位置引数の順、`L077` 残った `TODO`（情報）。
    `L076` だけは内部の `def`・`__init__` も見る（docstringは型スタブにも出るため）。
    `self`・`cls`・`*args`・`**kwargs` は書いても省いてもよく、キーワード専用引数の順は問わない
    （短縮名を元の名前の直後へ置く書き方が41件あり、署名の並びとは変わるため）。
  - docstring の雛形は `--template-docstrings <ファイル>` が入れる。署名から `Args:` の名前と並び、
    本文から `Returns:`/`Yields:`/`Raises:` を決め、`fast`・`ws`・値を返さない `Returns:` は固定文で完成させる。
    書けない説明の `TODO` は型として読まれない形（引数は型を省き、戻り値はコロンを書かない）にして、
    型スタブの生成と Sphinx のビルドが止まらないようにする。埋め忘れは `L077`（情報）で追う。
  - `L08x` Python版とproperty: `L080` Python 3.7（Maya 2022）で動く書き方、`L081` propertyのgetterでのMaya問い合わせ。
- 入れないと決めた検査: 1クラス1ファイル（現状の3件はすべて規則本文が認める組み合わせで、許可表が要る）、
  単数クラスの `__len__`/`__iter__`（`CompoundPlug`・`MultiPlug` の `__iter__` は意図的）。

### 入力検証・列挙・ファイル操作

- 公開APIの入力検証には`assert`を使わず、`TypeError`・`ValueError`等を明示する。
  テストと内部の整合性確認には`assert`を使用できる。`L040`は公開関数・公開クラスのメソッドと
  constructorの冒頭で、引数を直接参照するassertを入力検証の候補として検出する。
  内部関数・テスト・self/clsの状態確認・処理開始後のassertは対象外。
  全分岐のデータフローを解析する検査ではなく、入力検証か内部整合性かは最終的に本文で判断する。
- 番号と要素を単に列挙する場合は`enumerate`を基本にする。`L041`は
  `range(len(name))`と`name[index]`の読取りから確認候補を表示する。
  要素更新・削除・隣接番号の計算等は一律に変更しない。任意オブジェクトの反復と添字の同等性は推測しない。
- ファイルパスには`pathlib`、テキストの読書きには明示的な`encoding`を基本にする。
  2026-11-14のユーザー指定により、この2つはruffの`PTH`・`PLW1514`で検査する(`L042`・`L043`は削除した)。
  `normcase`等のOS固有の意味は維持し、MayaのDAGパス・アトリビュート名をファイルパスへ変換しない。
  例外として、フレームのファイル名を`os.path.normcase`で大小を無視して比べる`logger.py`・`decorator.py`と、
  パスをMayaのコマンドへ文字列で渡すテストは`PTH`の対象外にする(理由は`ruff.toml`に書く)。
  外部ファイルの文字コードをUTF-8と自動推測しない。

`L041`は個別判断が必要な情報表示で、単独では検査を失敗にしない。`L040`は検査失敗となる。
`--fix`はクラス内メンバーの並び替えだけを行い、上記を書き換えない。
入力assertの修正だけは`--fix-asserts TypeError`または`--fix-asserts ValueError`を使い、
対象ファイル1つと`--line`で確認した行を明示する。例外型の選択と変更の承認は呼出し側で行う。
複数行指定は全件を検証してから書き込み、コメントを含むassertや他の文と行を共有する場合、
選んだ例外名がソース内で再定義されている場合は拒否する。
この修正は例外型と最適化実行時の挙動を意図的に変更するため、既存の公開仕様と呼出し側も確認する。

## 公開名・型対応の宣言

- 公開名は所属パッケージの `__init__.py` へ明示する。`nodes`・`plugs`・`components`・`maths`・`cmds` とルート関数は通常のimportと `__all__` を使う。`common` は初期化順とreloadに合わせ、遅延公開の `_exports` と静的解析用の `if TYPE_CHECKING:` を維持する。
- ルートからのクラス取得(10.4.0): `nodes`・`plugs`・`components`・`maths`・`common` の `__all__` にあるクラス(別名・例外クラスを含む)は、ルートのモジュール `__getattr__` で `mlib.Joint` のように取得でき、文書・例ではこの書き方を推奨する。値はルートへimportして保持せず、毎回所属パッケージから取得する(reload後も現在のクラスを返す)。対象はルートの `_CLASS_PACKAGES`・`_EXCLUDED_CLASSES`(`Object`)と各パッケージの `__all__` から `_class_sources()` が求め、ルートの `__all__` は `_names + sorted(_classes)` とする。名前が重なる場合はルートの名前→`nodes`→`plugs`→`components`→`maths`→`common`→生成クラスの順に優先する。`common` は遅延公開のためimportせず、大文字だけの名前(定数)を除く(`check_mlib_exports.py` がクラス名と定数名の規則を検査する)。定数・関数・`Object` は対象にしない。補完用の再公開(`from .nodes import Joint as Joint`)は `tools/generate_mlib_stubs.py` が `mlib/__init__.pyi` へ書き出す。
- Node/Plugの型対応は `nodes/__init__.py`・`plugs/__init__.py` の `_WRAPPER_CLASSES` 辞書に宣言する。公開するクラス名とは分けて管理する。手書きクラスの明示登録は維持し、動的クラス(下記「動的ノードクラス」)はその補完に限る。
- 外部拡張の検出は `extensions` が担当する。拡張側も `nodes`・`plugs` の明示import・`__all__`・`_WRAPPER_CLASSES` を用い、実行時のクラス注入や登録デコレーターは使わない。
- 追加・削除後はリポジトリルートで `python maya/inhouse/mlib/_tools/check_mlib_exports.py` を実行する。Mayaをimportせず、公開対象と明示宣言の不一致を検査する。実行時に漏れを黙って補う処理は追加しない。

### 動的ノードクラス

2026-10-26のユーザー指定により、`_WRAPPER_CLASSES` に無いMayaのnodeTypeは要求時にクラスを自動生成して返し(動的クラス)、
`Node` へのフォールバックはMayaが認識しない型名だけに残す。手書きクラスの明示登録は維持し、生成はその補完に限る。
移行の経緯は git の履歴(各版のコミットメッセージ)を参照する。

- 生成の契機は2つ。`NodeRegistry.wrapper_class(node_type)` による型選択(`Node(node)`・`mlib.getNode`・`mlib.ls`・`mlib.createNode` の戻り値)と、`mlib.nodes.<TypeName>`・`mlib.<TypeName>` の属性アクセス(`nodes/__init__.py` のモジュール `__getattr__`。ルートの `__getattr__` は公開クラスに無い名前をこれへ渡す)。生成するのは `NodeRegistry(generate_classes=True)` の表(ルートが作るNode登録表)だけで、Plug登録表と汎用の `NodeRegistry` は従来どおり「完全一致 → 登録済み祖先(`resolve_inherited_types=True` の表) → フォールバック」で解決する。
- クラス名は型名の先頭を大文字にしたもの(`pointLight` → `PointLight`)。先頭が既に大文字の型(`AISEnvFacade`・`HIK*`)はそのまま。`mlib.nodes.<TypeName>` は先頭が大文字の名前だけを受け付け(`mlib.nodes.pointLight` はAttributeError)、Mayaが認識しない型名(未ロードのプラグイン型を含む)もAttributeErrorとし、AttributeError以外の例外を送出しない(`hasattr` と `mlib.reload()` から呼ばれる)。
- 生成クラスの基底は、Mayaの継承チェーン(`cmds.nodeType(inherited=True)`)を自身の直前から辿って最初に見つかる登録クラス。チェーンに登録が無ければ `Node`。登録クラスと生成対象の間にある抽象型(`weightGeometryFilter`・`containerBase`・`entity`・`geometryShape` 等)のクラスは生成せず、生成クラス同士を親子にしない。例: `wrap` → `Wrap(GeometryFilter)`(10.1.0でデフォーマー共通の `geometryFilter` を手書きの `GeometryFilter` として登録)、`symmetryConstraint` → `SymmetryConstraint(Constraint)`、`airField` → `AirField(DagNode)`、`unknownDag` → `UnknownDag(DagNode)`。抽象型そのもの(`mlib.ContainerBase`)も同じ規則で生成するが、インスタンスを持たないので `isinstance` には使えない。
- 生成クラスは `__slots__ = ()` で `__init__` を定義せず、`_generated_node_type`(型名)と `_generated = True` を持つ。`mlib.AirField("airField1")` の明示構築もでき、型が合わなければ登録クラスと同じ `Node.__new__` のTypeError(「参照と入力の固定規則」)。
- isinstanceの約束: 生成クラスは「最寄りの登録クラスの派生である」ことだけを保証する。手書きクラスの `isinstance` 階層はPythonの継承で決まり、Mayaの抽象祖先を含まない(`Container(Node)` なので `isinstance(container, mlib.ContainerBase)` はFalse。`Transform(DagNode)` も同様。10.1.0から `SkinCluster`・`Cluster`・`BlendShape` は手書きの `GeometryFilter` の派生)。
Mayaの継承に基づく型判定は `node.isType("geometryFilter")`、Maya型名の取得は `getType()`(`getType(inherited=True)` で基底→自身の順)を使う。手書きクラスの基底はMayaの親に揃える(`PoleVectorConstraint(PointConstraint)`)。`DagContainer(Transform, Container)` はMayaの全祖先を含んだ上位集合として据え置く(mixin化は次版)。
- 登録表には `"constraint"` を `Constraint` として明示登録し、未登録のコンストレイント型の生成クラスを `Constraint` 派生にする。`"node"` は登録しない(`cmds.nodeType("node", isTypeName=True, inherited=True)` は継承チェーンに現れないため、チェーンが尽きたときのフォールバック `Node` で足りる)。拡張(mlib_*)の明示登録は生成より常に優先する。
- 生成クラスは `__all__` やモジュール属性に追加せず(Sphinxにも載せない)、登録表(`NodeRegistry`)の登録辞書とは別のキャッシュに置く。無効化の契機は3つ: (a) 登録表の作り直し(`replace`・`clear`・`mlib.reload()`)、(b) `register`(基底の候補が変わる)、(c) `Plugin.load/unload` 後の型継承キャッシュの消去。いずれも生成済みクラスを廃棄し、次の照会で作り直す。無効化前に保持していた生成クラスの参照は新しいラッパーに対して `isinstance` が偽になるので、reload後のNode/Plugと同じく `mlib.nodes.<TypeName>` を取り直す。テストの期待値は `type(node).__name__`・`issubclass` で書き、クラスの同一性に依存しない。`cmds.loadPlugin` 直接呼び出し・Plug-in Managerからのロードには追従しない。

## コマンド層とオブジェクト・数学層

参照は`mlib.getPlug(target)`または`node.getPlug(name)`、値は`Plug.get()`、
Mayaの型名・状態は`getType()`・`isLocked()`・`isSettable()`等の専用メソッドで取得する。
2026-10-26のユーザー指定により、型の照会はNodeとPlugで同じ名前・同じ意味にする。
`getType()`はどちらもMayaの型名を返す(Nodeは`cmds.nodeType`のnodeType名、Plugはアトリビュートの定義型名で
generic/kAnyはNone。値は評価しない)。Nodeの`getType(inherited=True)`は`cmds.nodeType(inherited=True)`と
同順(基底→自身)の`list[str]`、Mayaの継承に基づく判定は`isType(nodeType)`、Pythonのラッパークラスは
`type(x)`・`isinstance`で調べる。旧`Plug.getType()`(Pythonクラスを返す)と`Plug.getDataType()`は廃止し、
`nodeType()`等の別名は追加しない。`getTypeId()/getPluginName()/getClassification()`は名前・戻り値を維持する。
現在値の型名が必要な場合は、
`maya.cmds.getAttr(plug.getFullName(), type=True)`で明示的に評価する。
`mlib.getAttr` / `mlib.cmds.getAttr`は公開しない。値の単位は既定で内部単位、
`get(uiUnits=True)`でUI単位とする。`getMin/getMax/getSoftMin/getSoftMax/getDefault(*, uiUnits=False)`も
同じ流儀で、省略時は内部単位、`uiUnits=True`でUI単位の値を返す。`time`等のMaya固有の照会は
`maya.cmds.getAttr`を直接呼び出し、Maya標準の戻り値と単位を扱う。

### Plugの接続と切断

`Plug.disconnect(source=None, force=False, f=False, nextAvailable=False, na=False, *, fast=False)`は
入力だけを解除する。`source`はPlug/MPlug/アトリビュート名またはNoneで、
bool方向と`destination`は受け付けない。入力省略時は現在の入力を解除する。
単一切断は入力元Plugを返し、入力がない・指定接続がない場合はRuntimeErrorとする。
入力元を指定した`nextAvailable/na`はマルチアトリビュート内の直結を検索し、切断した接続先要素のリストを返す。
`force/f`と`nextAvailable/na`のOR評価、通常Undo/fast OM2の方針は維持する。

`isConnected(*, source=True, destination=True)`、`isConnectedTo(other, *, source=True, destination=True)`、
`disconnectAll(*, source=True, destination=True)`はboolの方向指定を受け付ける。
bool以外はTypeErrorとする。両Falseでは判定はFalse、
`disconnectAll`は何もせず自身を返す。`getConnections`の既存の位置引数、
入力`s and source`、出力`d and destination`、型・ペア・ノード・番号・
子・マルチアトリビュートの要素の列挙フラグと戻り値は維持する。
`isConnected`は既存のMPlug接続状態判定を維持し、子・マルチアトリビュートの要素を列挙しない。
`isConnectedTo`・`disconnectAll`は対象Plugの直結だけを扱う。
`disconnectAll`は既定で両方向、未接続時no-op、自身返却で、force指定は持たない。
入力だけの未接続時no-opは`disconnectInput()`とし、自身を返す。
通常の複数切断は1回のUndo/Redoへまとめ、fastはUndoなしのOM2更新とする。

接続元・接続先は`getSource/getDestinations(skipConversionNodes=...)`、
方向付き照会は`getConnections`へ集約する。
2026-10-31のユーザー指定(8.0.0)により、`getSource`・`getDestinations`・`Node/Plug.getConnections`の`skipConversionNodes`(短縮名`scn`)の既定を
Falseにした(`cmds.listConnections`と同じく直結を返す。リグ構築では変換ノードを飛ばさない呼び出しが多かったため)。
`scn`と`skipConversionNodes`はORで、どちらかをTrueにするとunitConversion系を飛ばしてその先を返す。変換を飛ばす前提の呼び出しは`skipConversionNodes=True`を明示する。
`isSource/isDestination/disconnectInput/getSourceNodes`に方向boolは追加しない。
`connect(source)`と`connectTo(destination)`は接続相手を受け取る。

`getConnections`の`pcls`引数(戻り値のPlugクラス指定)は2026-10-26にNode/Plugの両方から削除した。
戻り値は常に実際のアトリビュート型に対応するPlugラッパーとする。
Plugの演算子は`src >> dst`(`src.connectTo(dst)`。解決した接続先dstを返す)、`dst << src`(`dst.connect(src)`。dst自身を返す)、
`src // dst`(`dst.disconnect(src)`。接続先dstを返す)の3つで、`connect`/`connectTo`/`disconnect`と同じ入力解決・例外・
通常Undoを持ち、fast経路は無い。マルチアトリビュート全体への`>>`はMayaと同じRuntimeErrorで、空き要素への接続は
`connectTo(multi, nextAvailable=True)`を使う。演算子は接続結果のPlugを返す。
`a >> b.x`は`a >> (b.x)`と評価される。`__len__`・`__add__`・無引数の作成・transform→shapeの暗黙のアトリビュート解決は追加しない。

### 再実行向けの指定(5.0.0。2026-11-16に引数名を分けた)

5.0.0では3つの意味を同じ `safe=True` で受けていたが、2026-11-16のユーザー指定で引数名を分けた。`safe` は「失敗しても例外にしない」だけに使い、
「すでに目的の状態なら何もしない」は `skipExisting`、「接続があるノードは消さない」(`Node.delete`・`Joint.delete`・`Joints.delete`)は `skipConnected`。
いずれも既定はFalse。下の表の「再実行の許容」の行が `skipExisting`、ほかの2行が `safe`。

| 意味 | API | Trueのときの挙動 | 戻り値 |
| --- | --- | --- | --- |
| 失敗の集計 | `Plug.set`(既存) | ロック・入力接続等の失敗を例外にせず数える。コンパウンドアトリビュートは子ごとに再試行する | 失敗数(成功は0) |
| 書ける成分だけ更新 | `Transform.setMatrix/setTranslation/setRotate/setScale/setShear/setQuaternion`(既存) | 書けないチャンネルを保持し、書けるチャンネルだけを更新する | 通常と同じ(値を返さない) |
| 再実行の許容 | `Node.addAttr`・`Plug.connect`・`Plug.connectTo`・`Plug.setAlias`(5.0.0) | 既に同じ状態(同名のアトリビュート・同じ接続・同じ別名)なら何も変更しない | 成功時と同じ値(Plug・接続先・自身)。件数は返さない |

再実行の許容は「既に目的の状態」だけを成功とみなす。状態が違う(既存のアトリビュートの型やマルチアトリビュートかどうかが違う、
別の入力がある、ロックされている、別名を別のアトリビュートが使っている)場合はskipExistingでも既定と同じ例外にする
(`addAttr` の型違いはTypeError)。既存の状態は更新しない(`addAttr` の既定値・範囲・表示、`connect` のlockは変えない)。
`connect/connectTo(nextAvailable=True, skipExisting=True)` は、接続元が既にいずれかの要素へ接続されていればその要素を返す。
同じ接続の判定はunitConversion等の変換ノードを経由した接続も含む(Mayaも同じ接続として拒否する)。演算子 `>>`・`<<` はskipExistingを持たない。
再実行で失敗しない操作には追加しない: `Transform.addConstraint` は同じ種類の既存コンストレイントを再利用し、
`Container.addMembers` は既存のメンバーを受け付け、`DrivenKey.setKey`・`AnimCurve.setKey` は同じ入力のキーを置き換える。

### 単位・フラグ・戻り値

`SkinCluster.removeInfluence`・`Joint.removeInfluence` と
`SkinCluster.removeUnusedInfluences` は、キーワード専用の `force=False` を受け付ける。
`force=True` は不正ウェイトを除去してから既存の移送・登録解除を実行する指定で、
ロック解除・レイヤー保護の回避・最後のinfluenceの解除を許可する指定ではない。
既存の位置引数・戻り値を維持する。
`removeInvalidWeights(*, fast=False)` は、負値・非有限値・未登録influence論理番号の
既存ウェイト要素だけを除去し、単数/複数とも自身を返す。
正規化・合計0の補填・1超の有限値の切捨ては行わない。
通常はcmdsでUndo対応、fastはOpenMayaのMDGModifierによるUndoなし更新とする。
未使用influenceの判定は引き続きMayaのweightedInfluenceを使い、微小値を切り捨てない。
不正ウェイト除去とinfluence登録解除は別の操作とし、jointノード自体は削除しない。

- `mlib.cmds` はMayaコマンドの名前・長短フラグ・単位解釈を基準にする。
  Node/Plug参照や数学型への戻り値のラップは各コマンドに明記する。
- 全パッケージの公開関数・メソッド・プロパティは上記の例外を除きlowerCamelCase。
  シーン照会にはgetを付ける（`getNumVertices`・`getNumCVs`・`getCvPositions`等）。
  mlib独自の複合操作は独自名と仕様を明記し、MFnと同一の処理だと扱わない。
- オブジェクトの数値は距離cm・時間は現在のUI時間単位のフレーム(6.0.0で既定を秒からフレームへ変更)・
  角度は度(5.0.0で既定をradから度へ変更)。角度の数値を受け渡す公開API
  (`Plug.get/set`、`Transform.setRotate/getRotate/setQuaternion(get=True)`、`DrivenKey.setKey`、
  `Node.addAttr`の角度の既定値・範囲、角度出力のAnimCurve・接線の角度、`AimConstraint`のoffset/restRotate、
  `units.angleToUi/angleFromUi`)は`unit="deg"|"rad"`(別名`degree(s)`・`radian(s)`)を受け、既定は度とする。
  `uiUnits=True`は現在のUI単位で、`unit`とは同時に指定できない(ValueError)。
  `EulerRotate`・`Quaternion`は内部rad(om2互換)で値自身が単位を持つため、`unit`に関係なく換算しない。
  `rotate`の`get()`は従来どおり`EulerRotate`を返し、`unit`を明示した場合だけ数値tupleを返す
  (`tuple(rotate.get())`はradの数値になるので、度の数値列が必要なら`get(unit="deg")`を使う)。
  `Plug.getMin/getMax/getSoftMin/getSoftMax`は既定で`MAngle`等の単位付きの値を返し、`unit`指定時に数値を返す。`getDefault`は9.0.0から`get()`と同じ規則の数値(度・cm・フレーム)を返す。`Plug.setKey`・`Node.setKey`の`value`も9.0.0から度・cm(`uiUnits=True`でUI単位)。
- 時間の数値を受け渡す公開API(`Plug.get/set`の時間アトリビュートと、時間の子を持つコンパウンド・マルチアトリビュート、
  `Plug.setKey`の`time`、`AnimCurve`のT型入力・時間出力(`setKey`・`getKeyInputs`・`getKeyValues`・`evaluate`・
  `moveKey`・`scaleKey`/`mirror`のpivot)、`DrivenKey.setKey`、`Node.addAttr`の時間の既定値・範囲、
  `Plug.setMin`等)は`timeUnit="frame"|"sec"`(別名`frames`・`second(s)`)を受け、既定は現在のUI時間単位のフレームとする。
  角度の`unit`と別の引数にする(animCurveTAのように角度と時間を同時に持つ値でも、それぞれを指定できるため)。
  単位名を逆の引数へ渡した場合(`unit="sec"`等)は、正しい引数名を示すValueErrorにする。
  `uiUnits=True`はフレームと同じ値になるが、`timeUnit`とは同時に指定できない(ValueError)。
  `MTime`は値自身が単位を持つため換算しない。`getMin`等は`timeUnit`指定時だけ`MTime`を数値で返す。
  U型(ドリブンキー等の無次元入力)のカーブ入力・`scaleKey`の倍率は無次元のまま。接線のウェイトは`keyTangent`と同じ値で、
  `timeUnit`を持たない。
  数学型の生成は既定rad(`EulerRotate(..., unit="deg")`・`Quaternion.fromAxisAngle(..., unit="deg")`で度)。
  内部処理はradで計算し、公開境界で一度だけ換算する(通常・fast・safeで同じ換算)。
  `getTranslation/setTranslation`等はマトリクス・姿勢の操作、`getPlug("translate").get/set`は
  アトリビュートの操作として区別する。前者をMFnTransform.translationの単なる別名にはしない。
- 空間指定は`worldSpace=True/False`(短縮名`ws`は3.0.0で廃止し、12.2.0で全メソッドに戻した)。使用例は`worldSpace=True`とする。
  Trueはワールド、Falseはローカル。bool以外・旧`space=`は拒否する。
  既定値は各メソッドの仕様を維持する（`SkinCluster.restoreBindPose`・`Joint.getBoneSegments` はTrue、`Transform.getPivot/setPivot/mirrorTransform`・
  `DagNode.getBoundingBox` はFalse）。
  OpenMaya標準APIのMSpace引数は変更しない。
- 数学型はOpenMaya API 2.0の継承を維持する。独自の正規化・分解補助は`asUnitMatrix`・
  `asCanonicalAxisAngle`・`asDecomposedEulerRotate`で、標準の`asMatrix`等と区別する。
  ゼロ値を拒否する正規化は`unit/unitIt`、標準のコピー正規化は`normal`。行列式は`det4x4`。
- 型付きデータ配列の対応getterは常にlist。空は`[]`、未初期化は`None`。
  点・ベクトルはtupleのlistとし、1要素でも外側のlistを省かない。
- CVはOpenMayaの番号を保持する。周期末尾の重複CVは通常編集・cmdsへ渡す名前で
  先頭の対応CVへ写す。fastの周期CV編集は未対応として拒否する。
- 通常更新では必要な単位変換をcmds境界で行い、Undoを確保する。`fast=True`では
  同じ内部単位の値をom2へ直接渡す。fastで入力単位・番号・戻り値の意味を変えない。
- 旧Python名の互換入口は作らず、内製使用側・テスト・ドキュメントを更新する。

`cmds.addAttr`の角度・距離のdefaultValue/minValue/maxValueは内部単位を使う(`Node.addAttr`は角度を既定の度から換算して渡す)など、
Mayaコマンドにも単位解釈の例外がある。全コマンドへUI単位変換を機械的に適用しない。

### 2026-10-26の統合で確定したメソッド契約

名前の重なるメソッドの統合・改名で確定した契約。旧名の互換入口は残さず、旧名との対応は
git の履歴(各版のコミットメッセージ)で追う。

- `Node.resetAttrs(attributes=None, *, fast=False)` はリセットしたPlugの `list[Plug]` を返す(3.0.0で別名 `attrs` は廃止)。
  `Transform.resetAttrs` は省略時の既定だけをoverrideし、translate/rotate/scale/shearを対象にする。
  2026-11-15のユーザー指定により、`Joint.resetAttrs` は省略時にjointOrientも0へ戻す(キーを設定できないので通常の対象に入らないため、Jointで足す。
  ロック・入力の接続がある成分は飛ばし、戻り値の末尾に `jointOrientX/Y/Z` を並べる。アトリビュートを明示したときは足さない)。
  jointOrientの読み書きは `Joint.getJointOrient`(EulerRotate・XYZ・rad)と `Joint.setJointOrient(value, *, unit="deg", fast=False, check=False)`
  (3つの数値は度が既定、EulerRotateはXYZへ直して書く。値だけを書くので向きが変わる)、preferredAngleは `getPreferredAngle`・`setPreferredAngle` で行う。
  角度の3成分を返すgetは `getRotate` に合わせてEulerRotate(rad)で返し、unit引数は置かない(度は `.asDegrees()`)。`getPreferredAngle` の回転順序はノードのrotateOrder
  (以前は度のlistと `unit` 引数だった)。setは3つの数値(度が既定)かEulerRotateを受け、回転順序が違えば同じ回転になる値へ直して書く。
  旧 `Transform.reset`(戻りself)・`resetPivot`(`setPivot((0, 0, 0), worldSpace=True, kind=...)` で代替)・`freeze`(`makeIdentity(apply=True, ...)`)は廃止。
- `Transform.getRotate(worldSpace=False, *, order=None)` は二段の規則で等価解を選ぶ。`order` を省略、またはノードのrotateOrderと同じ順序なら、
  Transformは現在のrotateチャンネル、Jointはゼロ回転に最も近い等価解を返す(`setRotate` との往復でチャンネル値が保たれる)。
  それ以外の順序なら `quaternion.asEulerRotation().reorder(order)` の素の分解値(等価解の選択なし)を返し、`order=0`(xyz)は旧 `getEuler` と同値。
  `order` はom2の番号(int)または名前。ゼロスケール軸のValueErrorは両方で共通。
  旧 `getEuler`・`getJointOrientQuaternion`(`getQuaternion(worldSpace, r=False)` と同値)・
  `getOffsetParentMatrix/setOffsetParentMatrix`(`getPlug("offsetParentMatrix").get()/set(value, fast=)`)は廃止。
- `Transform.getShear(worldSpace=False)` / `setShear(value, worldSpace=False, safe=False, get=False, *, fast=False)`(旧 `getShearing/setShearing`)。
- `Transform.setParent(parent=None, relative=False, add=False, *, fast=False)`(3.0.0で短縮名 `r` は廃止。fast は、ワールドの位置を保つ既定の動きでは通常の約1.5倍かかる(2026-11-15の計測)。利用側が「Undoに残さない親の変更」として使っているため、削除せずに残している)。
  JointのinverseScaleは `cmds.parent` と同じく `relative=False` のときだけ接続される(Mayaの仕様)。fastはJoint未対応で、変更前にNotImplementedErrorとする。
- `Joint.isJoint()` は廃止し、`isinstance(x, mlib.Joint)` または `x.isType("joint")` を使う。
- `Node.setLocked(state=True, *, fast=False)` はノード自体のロックで自身を返す(通常は `cmds.lockNode` でUndo1回、fastは `MFnDependencyNode.isLocked` のsetter)。
  アトリビュートのロックは `Plug.setLocked()`。`Node.mfn()` は毎回新規のfunction setを返す(Mesh/Camera/NurbsCurve/ReferenceはMFnMesh等を返すoverride)。
- 6.0.0で `Plug.lock()`・`unlock(below=)`・`mute()`・`unmute()` を廃止した。ロックは `setLocked(state, leaf=False, *, fast=False)`・
  `setFlags(locked=)`、ミュートは `setMuted(state)` を使う。`unlock()` が行っていた上位のコンパウンドアトリビュート・マルチアトリビュートの
  継承ロックの解除と `below=True` の下位の解除は `setLocked(False)` に無い(利用が無かったため引数は足していない)。
  上位が必要なら `plug.getParent()`・`plug.getMulti()` の `setLocked(False)`、コンパウンドアトリビュートの子は `setFlags(locked=False, children=True)`。
  接続時の一時解除は `connect(force=True)` が内部で行う。
  `Plug.hide(*, fast=False)` は keyable・Channel Box表示をFalse、`Plug.show(keyable=True, *, fast=False)` はその逆で、
  どちらもコンパウンドアトリビュートの子へ広げる(ロックは変えない)。`Plug.isHidden()` はその判定で、
  keyableでもChannel Box表示でもない(コンパウンドアトリビュートは子孫の末端がすべてそう)ときTrue(6.0.0。5.0.0までは
  `addAttr(hidden=True)` の定義フラグ `cmds.attributeQuery(hidden=True)` を返していた。定義フラグの照会入口は置かない)。
- コンパウンドアトリビュートの状態: Mayaの `setAttr(keyable=/channelBox=)` は親(`t`)にだけ効き、子(`tx`)は変わらない
  (ロックは親から継承される)。`Plug.setFlags(..., children=False)`・`Node.setAttrFlags(..., children=False)` は既定でこの挙動を保ち、
  `children=True` は自身に続けて子孫へ同じ状態を明示的に設定する(マルチアトリビュートの要素へは広げない)。
  `setKeyable/setChannelBox/setLocked(leaf=True)` は末端の子だけを変え、自身(親)は変えない点が `children=True` と異なる。
- `MultiPlug.getNextAvailable(start=-1, checkLocked=True, checkChildren=True, *, vacant=False)` はマルチアトリビュートのPlugだけが持つ
  (基底Plugからは `AttributeError`)。6.0.0から常に要素のPlugを返し、番号は `getIndex()` で取る(`asPlug` 引数は廃止)。要素の作成・予約はしない。5.0.0で「次に使える要素」はMayaの規則
  (`cmds.connectAttr(nextAvailable=True)`)に統一し、`connect/connectTo(nextAvailable=True)` は `getNextAvailable()` の既定の結果へ接続する
  (4.x の `connect(nextAvailable=True)` は0から探したため、途中の空きへ接続していた)。要素は入力接続が無ければ使え、値を持つだけの要素も候補になる。
  `vacant=True` はMayaの規則と別の「未使用の番号」の探索で、値を設定する空き要素を探す用途に残す。`appendMessage(node, *, fast=False)` は探索規則が違うので統合しない。

  | 呼び方 | 開始位置 | 返す要素の番号 | checkLocked/checkChildren |
  | --- | --- | --- | --- |
  | `getNextAvailable()`(既定。`connectTo(nextAvailable=True)` と `cmds.connectAttr(nextAvailable=True)` も同じ) | `start`。負数なら接続(子の接続を含む)のある最後の要素の次(途中の空きは飛ばす) | 入力接続・ロック・子の入力接続の無い最初の論理番号(値を持つだけの既存要素も可) | 有効 |
  | `getNextAvailable(vacant=True)`(旧 `getNextAvailableIndex`) | `start`。負数なら0 | 既存番号(値・接続のある要素)に無い最初の番号 | 無視する |
  | `appendMessage(node)` | 最大の既存番号+1 | その番号へmessage接続して返す(途中の穴は再利用しない) | — |

- `Plug.getEnumName(value=None)`: 省略時は現在値の名前、指定時はその値の名前(旧 `getEnumFieldName(val)` を吸収)。
  `getEnumNames()` は `list[tuple[str, int]]` を値順で返す。`setEnumNames(names, *, fast)`・`getEnumValue(name)` は維持。
  5.0.0で `EnumPlug.set()` はフィールド名(`set("head")`)も受け付ける(整数も可)。大文字・小文字を区別する完全一致で、
  一致しなければ有効な名前を並べたValueError(safe=Trueでは失敗数1)。通常・fast・safeで同じ。
  `Node.addAttr(..., type="enum", enumName=..., defaultValue="head")` も `enumName` からフィールドの値を求める。
- 範囲の編集: `Plug.setMin/setMax/setSoftMin/setSoftMax(value, *, unit=None, timeUnit=None)` は動的アトリビュートの定義を
  `cmds.addAttr(edit=True, minValue=...)` で編集し(Undo1回、fastなし)、`setMin/setMax(None)` で制限を外す(ソフト値の削除はMayaが編集できないため `setSoftMin/setSoftMax(None)` はNotImplementedError)。値の単位は `addAttr` の
  `minValue` と同じ(角度は度が既定で `unit="rad"` も可、距離cm、時間はフレームが既定で `timeUnit="sec"` も可)。静的アトリビュートと数値・単位型以外はTypeError。
  `Transform.setLimits(*, unit="deg", **limits)` は `cmds.transformLimits` の入口で、`translateX=(min, max)` のように
  チャンネルのロング名へ組を渡す。片側の `None` はその側の制限を無効、値全体の `None` は両側を無効にする(距離cm・角度は度で、MayaのUI単位へ換算して渡す。`cmds.transformLimits` の照会は移動だけcm、回転はUI単位で返る)。
- Plugの名前: `getName()` は `<ノードの最短名>.<ショート名と論理番号のパス>`(`tt.wm[0]`・`bs.it[0].itg[3].tw[2]`)、
  `getFullName()`/`str(plug)` は `<ノードの一意名>.<ロング名のパス>`(エイリアスがあれば使う。Mayaコマンドへ渡す名前)、
  `getShortName()`/`getLongName()` はアトリビュート自身の名前(ノード名・親・論理番号を含まない)、`getNiceName()` はUI表示名。
  5.0.0でworldSpaceの要素の番号も省かなくなった(4.x は `tt.wm`・`.wm`)。6.0.0で `getAttrName()` は廃止した
  (ノード名を除いたパスは `plug.getName().partition(".")[2]` で、`node.getPlug()` へ渡せば同じPlugへ戻せる)。
- 「アトリビュートが無い」例外は `mlib.getPlug("node.nope")` と `node.getPlug("nope")` で同じ
  `mlib.plugs.plug.MissingAttributeError`(`AttributeError` と `RuntimeError` の両方を継承。文言は `Attribute not found: node.nope`)。
  `DeletedAttributeError(ValueError, RuntimeError)` と同じ作りで、既存の `except AttributeError`/`except RuntimeError` のどちらも効く。
- `MultiPlug.getElement(index)` は `multi[index]` と同じく、未作成の要素も参照を返す(5.0.0。4.x は欠番をIndexError)。
  既存要素だけが必要なら `getElements()`、存在の判定は `index in multi`。
- generic/kAnyのアトリビュートへの定数のマトリクス(`plug.set(Matrix())`)は、Mayaの `setAttr` がマトリクスのデータを
  受け付ける場合(`addAttr(dataType=["matrix", ...])` の動的アトリビュート等)だけ通常・fastとも書き込む。
  `choice.input` のような組み込みのgenericはMayaがマトリクスの定数を受け付けず、OpenMayaで書き込めても保存したシーンを
  読み込めない(値が失われる)ため、通常・fastともTypeErrorにする。マトリクスの出力(`holdMatrix.outMatrix` 等)を接続する。
- `Plug.getAlias()`(`MFnDependencyNode.plugsAlias`)、`getMulti()`(要素が属するマルチアトリビュートのPlug)、`getIndex()`(要素の論理番号。非要素はTypeError)を追加。
  `getPlugName(short, fullAttrPath)` は廃止し `getName()/getFullName()`。
- `DagNode.show(*, fast=False)` / `hide(*, fast=False)` は `setVisibility(state, fast=)` へ通す。

## メソッドとプロパティ

| 対象 | 公開形式 | 例 |
| --- | --- | --- |
| Mayaの現在の状態・名前・アトリビュート情報を問い合わせる | メソッド | `node.getFullName()`、`node.isLocked()`、`plug.getName()` |
| Maya上の座標など、評価済みの値を取得する | メソッド | `vertex.getPosition()`、`mesh.getNumVertices()` |
| Mayaの状態を変更する | 明示的なメソッド | `plug.set(value)`、`transform.setTranslation(value)`、`node.rename(name)` |
| オブジェクトが保持している参照・番号を返す | プロパティ | `component.shape`、`component.index`、`components.indices` |
| 数学値(`mlib.maths`)を参照する | プロパティまたはデータフィールド | `vector.x`、`matrix.translate` |

```python
import mlib

node = mlib.createNode("transform")
plug = node.getPlug("translateX")

print(node.getFullName())    # 現在のMayaノード名を取得
print(plug.isLocked())   # 現在のロック状態を照会
print(plug.getNode())        # 所有Node取得メソッド
plug.set(10)             # Mayaの値を変更

from mlib.maths import Vector

value = Vector(1, 2, 3)
print(value.x)            # Pythonオブジェクトが保持する値
```

## 判断に迷う場合

- 内部の照会・数値計算はOpenMaya API 2.0を基本とする。通常のシーン更新はUndo対応の`maya.cmds`を使い、対応APIの`fast=True`ではAPI 2.0で直接更新する。
- 読取りの高速化に`fast`指定を要求しない。単点・一括取得を使い分け、保持するMPlugやMDagPathを名前へ戻して再解決しない。型・単位・順序・削除検出の契約は維持する。
- `fast`は検証を省略する指定ではない。未対応の直接更新は変更前に拒否し、Undoのグローバル設定変更や独自プラグインで補わない。内側の対応処理へも`fast=fast`を明示的に渡す。
- 2026-10-26の指定により、書き込み系の公開メソッドは原則 `fast=False` 引数を持ち、定型(`_require_bool(fast, "fast")` → `with _edit_context("mlib<Class><Method>", fast):`(`nullcontext() if fast else undoChunk(...)`) → 検証・対象解決はwith内に通常/fast共通で1回 → 書込み直前の `if fast:` 分岐 → 内側へ `fast=fast` を明示 → 未対応は変更前にNotImplementedError)で実装する。fastでも入力検証・例外型・単位・戻り値は同じ。複数のom2操作は1つのmodifierに積んで `doIt` を1回にし、DAG削除とDG操作を同じmodifierに混在させない。
- `fast` を持たない書き込みはom2に同等機能が無いものに限り、docstringに「fast引数は持たない」と理由を書く: `Transform.addConstraint`(コンストレイント作成APIなし)、`makeIdentity`(形状へのベイク)、`SkinCluster.bind/copyWeightsTo/addInfluences/restoreBindPose/mirrorWeights`(バインド・コピー・ミラーAPIなし)、`BlendShape.create/addTarget/removeTarget`・`IkHandle.create`・`Joint.orient/mirror`(cmds.blendShape・ikHandle・joint・mirrorJointの同等機能なし)、`DagPose.create/restore`(Mayaの階層補完・復元規則)、`Container/DagContainer` の作成・所属・publish系(MFnContainerNodeは照会専用)、`Reference.load/unload/remove`・`createReference`(ファイル操作)、`Plugin.load/unload`(環境操作)、`moveAttrOrder`、`DagNode.reorder`・`setOutlinerOrder`(子の順番を変えるOpenMaya APIなし。`MFnDagNode.addChild` は既存の子の位置を変えられない)。`setEnumNames` は引数を持つが `fast=True` をNotImplementedErrorで拒否する。
- 2026-10-30のユーザー指定により、fast は通常経路より速くなるものに付ける(デコレーター・コンテキストでは切り替えず、引数だけで指定し、内部の処理へ `fast=fast` で渡す)。6.1.0 で `Mesh.setPoints`・`NurbsCurve.setCvPositions`(全点を `MFnMesh.setPoints`・`MFnNurbsCurve.setCVPositions` で1回に書く)、`DagNode.setColor`・`Nodes.setColor`、`BoolPlug.toggle`、`SkinCluster.pruneWeights`(`setWeights` と同じPlug直接書込み)、`DrivenKey.setKey`(この組のカーブが無ければ setDrivenKeyframe と同じ型・名前のカーブを作って接続する。別ドライバーが既にある駆動先は blendWeighted の挿入が必要なので NotImplementedError)に fast を足した。周期カーブの fast 座標編集(`setCvPositions`・`scaleGeometry`)は末尾の重複CVを先頭の独立CVに揃えて書く。mayapy 2027 で cmds と om2 の1回あたりの時間を測り、差がほぼ無いものは fast を付けない: `Transform.setLimits`(transformLimits 1回とPlug 8本の書込みが同程度)、`matchTransform`(同程度)、`Joint.orient`(joint -e 1回が約30µs)、`NurbsCurve.create`(約1.4倍)、`Plug.setMin/setMax/setSoftMin/setSoftMax`(addAttr -e 1回が約10µs)。1回の cmds で全体を処理するもの(`copyWeightsTo`・`mirrorWeights`・`bind`・`makeIdentity` 等)も om2 にしても速くならない。
- 2026-10-31のユーザー指定により、fast にしても速くならないもの・効果がほぼ無いもの(実際の使い方に近い量で約1.1倍以下)は、fast 引数と OpenMaya の経路を削除する。7.0.0 で削除: `ShadingEngine.assign`・`ObjectSet.addMembers/removeMembers`(MFnSet が cmds.sets より遅い)、`DisplayLayer.addMembers/removeMembers/setCurrent`(同じく遅い)、`Joint.reparentChildren`(ワールド位置を保つ付け替えは cmds.parent が速い)、`AnimCurve.shiftKeys/scaleKeys/mirror`(全キーを1回で処理する cmds が速い。9.0.0で`moveKey`・`scaleKey`へ改名)、`Plug.setKey`(検証と照会が大半。`AnimCurve.setKey` の fast は残す)、`Joint.jointOrientToRotate/freezeRotate`・`SkinCluster.redistributeWeights`(検証・計算が大半で約1.0倍)、`Plug.setEnumNames`(fast=True が常に未対応だった)。`Transform.setParent` の fast は `relative=True` で約2.5倍速いため残す(ワールド位置を保つ既定では fast の方が遅い)。削除した fast は docstring に「fast引数は持たない(理由)」と書く。
- 3.0.0 で次の書き込みから `fast` を外した。利用がほぼ無く、cmds と同じ結果を保つ補正が保守の負担になるため 3.0.0 で外した: `mlib.duplicate`(`MFnDagNode.duplicate` の名前・ロック・セット所属・inverseScale の補正)、`mlib.select`・`Selection.select`(`MGlobal.setActiveSelectionList` でのコンポーネントのまとめ方の再現)、`Namespace.create/setCurrent/rename/move/remove`(`om2.MNamespace` の作成名の特定・ASCII以外の拒否)、`Plug.setMuted/mute/unmute`(`MDGModifier` での mute ノードの命名・接続の再現)、`Transform.matchTransform`(position・pivots だけの再現)、`SkinCluster.removeInfluence/removeUnusedInfluences`・`Joint.removeInfluence`(`cmds.skinCluster -removeInfluence` の再配分・距離配分の再現)。いずれも通常経路(cmds、Undo 1 回)だけを持つ。
- cmds→om2の読み取り置換は `__tests__/inMaya/integration/test_parity_cmds.py` にcmdsの生値との突き合わせを同時に追加し、一致しないものはcmdsに戻す。om2に対応APIが無い読み取り(`Plug.getNiceName` の `attributeName -nice`、`cmds.nodeType` による型継承照会、`ls -undeletable`、`referenceQuery` のedit系、`keyTangent -g`、`mlib.ls` の検索・並び順、module/plugin/scriptJob/undoの環境系)はcmdsのままとする。
- UI・環境設定、既存のcmds直接利用指定は例外としてcmds/melを使用する。

- 引数がない、処理が軽い、戻り値が単純な数値という理由だけではプロパティにしない。Mayaの現在値を取得するならメソッドにする。
- `cmds` とOpenMayaのどちらを使うかでは区別しない。MayaのAPIハンドルから現在の名前や状態を読む場合もメソッドにする。
- 内部でキャッシュしていても、「現在のシーン状態を取得する」という契約ならメソッドにする。キャッシュ方式の変更で公開形式を変えない。
- 取得した値は現在のシーン状態と区別する。例えば `Node.getUuid()` は現在のノードを照会し、その戻り値は取得時点のUUIDを表す。
- 保持値を返すプロパティのgetterで、Mayaへの問い合わせ・ノード作成・シーン更新を暗黙に行わない。
- 保持値だけから得られる軽い派生値はプロパティにできる。ただしマトリクスの逆マトリクス計算や形式変換など、明示的な計算・変換は従来どおり `inverse()` / `asMatrix()` 等のメソッドにする。シーンへ問い合わせない処理をすべてプロパティへ変える規則ではない。
- シーン編集用のproperty setterは追加しない。`mlib.maths` の数学型はom2の型を継承した可変の値型なので、ローカル値を更新するsetter(`vector.x = 1.0`、`matrix.translate = (...)` など)を使用できる。これは値の更新で、シーンは変更しない。
- データクラスの保存フィールドは、そのまま公開してよい。保存フィールドを無意味なgetterで包む必要はない。

`node.tx` はアトリビュート名を解決して `Plug` を取得する省略アクセスである。正式な取得入口は `node.getPlug("tx")`。
5.0.0から `node.tx = 10` は `node.getPlug("tx").set(10)` と同じ書込みになる(Undoに記録し、角度は度)。
`_` で始まる名前とクラスに定義された名前(メソッド・プロパティ・クラス属性)は通常のPythonの代入のままで、
Mayaアトリビュートの無い名前はAttributeErrorにする(Nodeのインスタンスへ任意のPython属性を追加しない。
保持したい値はクラスで宣言する)。これは「シーン編集用のproperty setterは追加しない」の例外として扱う。

## maya.cmds との受け渡し

mlib のオブジェクトは `maya.cmds` へそのまま渡せることを仕様とする。詳細は
各公開APIのdocstringを参照する。基本例は[はじめに](../maya/inhouse/mlib/_docs/source/getting_started.rst)に記載する。

- シーンのノード・アトリビュート・コンポーネントを表すクラスの `__str__` は、`maya.cmds` が一意に解決できる名前を返す。`Node` は最短一意名、`Plug` は `<ノードの最短一意名>.<アトリビュートパス>`、`Component` はシェイプの完全パス付きの名前とし、呼び出すたびに現在のシーンから求める(名前変更・親子付け替えに追従する)。
- 単一の対象を表すクラス(`Node`・`Plug` など)に `__len__`/`__iter__` を追加しない。`maya.cmds` がシーケンスとして展開してしまう。複数の対象を表すコレクションは反復可能にしてよい。
  `MultiPlug`(マルチアトリビュート全体)も `__len__` を持たない。`__getitem__` が論理番号を取るため、`__len__` があると cmds が位置0〜len-1の並びとして展開し、`cmds.getAttr(multi)` が論理番号[0, 2]でなく[0, 1]の値を黙って返す(2026-10-29に確認)。現状は cmds がエラーにするので、`str(multi)` で渡す。要素数は `len(multi.getIndices())`。`in` は論理番号または要素Plugの存在を返す(`__contains__` は cmds の展開に影響しない)。
- Plug の `repr` は実際のラッパーの型名を表示する(`Plug('t.translateX')`・`CompoundPlug('t.translate')`・`MultiPlug('pma.input1D')`、無効なら `<MultiPlug invalid>` など)。
- ノードやアトリビュートを受け取るコマンド・メソッドは、文字列に加えて mlib のオブジェクトと Maya API 2.0 のオブジェクト(`MObject`・`MDagPath`・`MPlug`)を受け付ける。正規化は `Object`・`Node`・`Plug`・`Component` の内部メソッドで行い、各APIで独自に判定しない。
- ノードが必要な引数(`parent` など)は、Plug を所有ノード、Component を所有シェイプへ解決する。プラグ名を `maya.cmds` へそのまま渡して黙って無視させない。
- 名前を解決できない場合(存在しない・複数の対象に一致する)は最初の一致を黙って返さず例外にする(`"bulk*"` のようなパターンも同じ。パターンは `mlib.ls` で扱う)。対象を名前へ変換する内部処理(`Object._input_name/_input_names`・`Node._input_name`)の例外の種類は、対応しない型が `TypeError`、空・削除済みの対象が `ValueError`、解決できない文字列が `RuntimeError` とする。既存の API が削除済みの対象を `RuntimeError` にしている場合(`Node(...)`/`mlib.getNode`、`Transform.addConstraint` のターゲット・コンストレイント先)は、その規則を変えない(`Node._resolve_input` は既存Nodeの保持参照を返し、後続操作が有効性を検証する)。ただし所有ノードが有効なまま `deleteAttr` でアトリビュートが削除された Plug・MPlug は、所有ノードへ解決すると削除済みの対象を黙って受け付けるため、ノードが必要な引数でも `ValueError` にする(`DeletedAttributeError`。既存の規則を保つため `RuntimeError` の派生でもある)。削除済みの対象の判定メソッド(`isParentOf` など)は `False` を返す。
- オブジェクトの取得・ラップ(`node.getPlug()` などによるPlug生成)と接続列挙は値を評価せず、マルチアトリビュートの要素を作成しない。generic/kAnyは保持値によらず基底Plugのままとし、`get()`の時点で現在値を判定する。マトリクスならMatrix、数値の組ならtuple等の既存表現を返す。値の取得では上流の評価や出力マルチアトリビュートの実体化が起こる場合がある。要素作成は`array[index].set(value)`または参照への接続で明示する。
- 番号を受け取る API は、Maya が範囲外の値を黙って別の値へ変換する場合(`MPlug.elementByLogicalIndex()` は 0〜2147483647 の外の論理番号を別の番号へ変換し、`4294967296` は `0` になる)でも、別の対象へ読み替えずに例外にする。
- 解決したノードの種類を API が扱えない場合(parent/point などのターゲットに解決されたシェイプなど)は、`maya.cmds` のように黙って壊れた結果を作らず `TypeError` にする。
- 生の `om2.MPlug` などの API オブジェクトは削除を検出できない場合があるため、mlib の内部でも削除操作をまたいで保持せず、ハンドルで有効性を確かめられる mlib のオブジェクトを保持する。

## 命名と継承

- クラス実装は原則1クラス1ファイルとする。ただし単数クラスと対応する複数クラスは同じファイルへまとめる（`joint.py` に `Joint` / `Joints`）。既存の分離済みクラスの移動は必須としない。`__init__.py` は公開用importを基本とする。
- クラスに関係する処理は、そのクラスのインスタンス／クラス／静的メソッドへ配置する。補助関数だけを置くファイルをnodes/plugs/componentsなど型をまとめるパッケージ内に増やさない。commonでは用途単位の関数モジュールも扱う。
- 特定クラスに依存しない小さな中立の汎用関数・値処理補助は `mlib.util` へ集約し、Mayaの状態・環境等の責務固有の処理は `mlib.common` 配下へ用途単位でまとめる。版番号のように保持値と関連操作があるものは `mlib.common.version.Version` のような値クラスにまとめる。既存のMaya互換コマンド入口 (`cmds`) は、その公開方式を維持する。

| 対象 | 推奨ルール | 例 |
| --- | --- | --- |
| パッケージ | 小文字、必要ならsnake_case | `nodes`、`components`、`common` |
| Mayaコマンドとそのファイル | Mayaと同じcamelCase | `createNode.py` / `createNode()` |
| Mayaノードのファイル | nodeTypeと同じ表記 | `skinCluster.py`、`animCurveTL.py` |
| その他の実装ファイル | lowerCamelCase | `scriptJobs.py`、`eulerRotate.py`、`multiPlug.py` |
| クラス | PascalCase | `SkinCluster`、`ScriptJobs` |
| オブジェクト層の公開メソッド | lowerCamelCase | `getMatrix()`、`setWeights()` |

Mayaコマンド・nodeTypeに対応する名前は、Maya標準の表記を優先する。
例えば `cmds/createNode.py` はコマンド、`common/scriptJobs.py` はイベント所有の実装で、いずれもlowerCamelCaseのファイル名を使う。

このファイル名規則はmlibとすべての `mlib_*` 拡張パッケージに適用する。クラス実装に限らず内部処理のファイルも `attributeType.py` のようにする。内部用の先頭 `_` は保持する。`__init__.py` 等のPython特殊名、探索規約のある `test_*.py` とテスト用スクリプト、パッケージ名は改名対象外。Maya nodeTypeと同名のファイルは大文字を含む場合もMayaの表記を優先する。内部関数・内部メソッド・ローカル変数はsnake_caseを基本とする。nodes/plugs/componentsの公開メソッドはlowerCamelCaseとする。

- 値の取得・設定を対にするAPIは `getTranslation()` / `setTranslation()` のようにする。名前や判定の照会は `getName()` / `isLocked()` など、既存の意味の明確な形式を使う。全メソッドへ機械的に `get_` を付けない。
- 子クラスで基底メソッドと同名の別機能を公開しない。`Node.getConnections(source=True, destination=False, type=...)` は接続検索とし、`AnimCurve.getKeyInputs()` と `BlendWeighted.getInputPlugs()` は専用名を使う。
- 同じ処理の別名を増やさない。正式な入口へ使用側も更新し、旧名の互換入口は残さない。判定も正式is名へ一本化する。

## 追加・変更時の確認

- API名から照会・保持値の参照・編集の違いを判断できること。
- プロパティをメソッドへ変更した場合、内部の呼び出し・複数形クラス・テスト・docstring・Sphinxの例を更新すること。
- シーン編集は既存のUndo方針に従う。対応APIの `fast=True` はUndo不要の明示指定として区別する。
- 改名・モジュール移動は `mlib.reload()` でも検証し、廃止した公開名が残らないこと。

現行APIの名前・引数・返却は各公開APIのdocstringを参照する。

### テストの置き場所と名前(2026-11-13のユーザー指定)

- フォルダーはMayaが要るかどうか、ファイル名は確かめる対象で決める(2026-11-14にMaya有無の軸へ再編成)。`__tests__/noMaya/` はMaya不要(`runNoMaya.py`)、`__tests__/inMaya/unit/<パッケージ>/` は1つのモジュール(パッケージはソースと同じ `cmds`・`nodes`・`plugs`・`components`・`maths`・`common`・`core`・`json`、mlib直下のモジュールは `root`)、`__tests__/inMaya/integration/` は複数のパッケージにまたがる確認でフォルダーを作らない。
- 名前は `test_<対象>[_<話題>].py`。`_` は区切りだけに使い、各部分は lowerCamelCase。対象はソースのファイル名のまま(`__init__.py` は `init`、先頭の `_` は付けない、スネークケースのツールは lowerCamelCase に直す)。`inMaya/integration/` の対象は観点 `naming`・`units`・`fast`・`parity`・`undo`・`errors`・`interop`・`performance`・`workflow`・`reload`・`compat`。GUIが要るものは話題を `gui` にする。
- 何を確かめるかが分からない語・作業の経緯を表す語(`spec`・`refactoring`・`consolidated`・`changes`・`additions`・`backlog`・`misc`・`api`・`contracts`)や番号・記号は名前に使わない。
- 検査ツールは mlib の `_tools/` に置く(`__tests__/checks/` は作らない)。調査用の使い捨てスクリプトはリポジトリに入れず、残す価値がある確認はテストにする(`manual/` は作らない)。
- `noMaya/test_runAll.py` がこの規則を検査する。同名のファイルが別フォルダーにあるので、`--tests` はフォルダー付きの相対パスも受ける。
- 利用側も同じ軸へ揃える(2026-11-14): mlrig `__tests__/inMaya/{unit,integration}/`、mlib_bifrost `__tests__/inMaya/unit/`、`tests/mlib_integration/inMaya/`(旧 `cases/`。GUIは `inMaya/gui/`)、`tools/tests/{noMaya,inMaya}/`。全体がMaya前提のものは `noMaya/` を作らず、Maya不要のテストを足すときに作る。

## cmdsの範囲

`getNode/getPlug/createNode/ls/delete/duplicate/select/objExists`の基礎8入口と、8.0.0で足した作成関数(上の「確定したコーディングルール」)、10.1.0で足した `bakeDeformer`(デフォーマーの変形をスキンへ焼き込み skinCluster を返す)、10.2.0で足した `bakeResults`(cmds.bakeResults 相当)・`createJointChain`(点からジョイントの連鎖を作る)だけを公開する。

関数とファイルは同名。Mayaの長短フラグ・入力解決・Undo・戻り型の既存契約を維持する。
ノードの作成は `createNode` だけが担い、クラス側の `Node.create`・`X(name, create=True)` は無い(「確定したコーディングルール」の2026-10-26指定)。
その他のMayaコマンドは利用側で直接使い、必要な結果をgetNode/getPlugで包む。
既存対象の編集はNode.addAttr/Transform.addConstraint/ObjectSet.addMembers等のメソッドへ寄せる。
同じ用途の別ラッパーや汎用cmds転送クラスを再追加しない。

### メソッドの統一基準

- 同じ結果を返す互換別名は追加せず、正式な入口へ集約する。
- 状態の切替は `setVisibility(state)`・`setMuted(state)` のように表す。
- 排他的な選択操作は `Selection.select(mode="replace")` のようなモードで指定する。
- メンバーの操作は `addMembers` / `removeMembers`、個数の照会は `getNumVertices` / `getNumCVs` 等のget付き正式名にする。
- `Plug.get/set` は対象アトリビュートを扱い、マトリクスアトリビュートから所有ノードのTRS更新へ暗黙に切り替えない。ノード変換は `Transform.getMatrix/setMatrix` を使用する。
- 単数形と複数形の座標取得はともに `getPosition`。書込みは 12.1.0 で戻した `setPosition`(1成分は `axis`、移動は `relative=True`、複数形の要素ごとの値は `each=True`)と `mirror` で、`worldSpace=False`・cm・通常は `cmds.xform`/`polyEditUV`、`fast=True` は OpenMaya。
- 点の位置(XYZ)は、単体なら `mlib.Vector`、複数なら `list[Vector]` で返す(6.0.0。`Vertex`/`CV`・`Vertices`/`CVs` の `getPosition`、`Mesh.getPoints`、`NurbsCurve.getCvPositions`)。om2の `MPointArray`・tupleは返さず、wでは割らない。成分だけの `getPositionX/Y/Z` は float。UVの位置は2成分のため `(U, V)` のtupleのまま。全点の一括書込みは `Mesh.setPoints`・`NurbsCurve.setCvPositions` で、どちらも `get` の結果・tupleの列・MPointArrayを受け、点数の違いはValueError、1回のUndoにまとめる。
- 戻り値の型・単位・更新対象・破壊性が違う操作は、名前が似ていても安易にフラグ統合しない。

- Plug系の空間指定は廃止し、アトリビュート値とTransformの姿勢を区別する。Double3Plugのrotateは回転順序・単位変換だけを行い、jointOrientや他のチャンネルを合成しない。
- アトリビュートフラグはキーワード専用の `setFlags(locked=None, keyable=None, channelBox=None, fast=False)` へ集約する。Noneは変更なし、bool以外は更新前に拒否する。
- 一括更新では、対象名・所属・入力値など検証できる項目を更新前に全件検証する。Undoチャンクは失敗時の自動ロールバックを意味しない。

### 複数形ノードの基底クラス

- ノードコレクションは `Nodes` を基底にし、`Joints`・`SkinClusters` は `Nodes` の派生とする。`Nodes` 自体は `Node` を継承しない。3.0.0で `DagNodes`・`Transforms`、単数メソッドへの一括転送(`_bulk_entries`・`callEach`)は利用が無いため廃止した。
- 12.2.0(2026-11-11のユーザー指定)で、単数のメソッドを複数形から呼べるようにした。`Nodes.__getattr__`・`Components.__getattr__` が、コレクションに無い公開メソッド名を「各要素の同名メソッドを同じ引数で保持順に呼び、戻り値を保持順のリストで返す関数」として返す(書込みも常にリスト。コレクション自身の明示メソッドが優先)。通常は1回のUndoにまとめ、`fast=True` はそのまま各メソッドへ渡す。`Nodes` は呼ぶ前に全要素がメソッドを持ち有効か確かめ(無い要素はTypeError)、どの要素も持たない名前はAttributeError。名前で呼ぶ `Nodes.callEach(method, *args, **kwargs)` も同じ動き。要素ごとに違う引数は単数を `for` で呼ぶ。`Plugs` は転送しない。
- 型スタブでは、転送するメソッドを各コレクションへ書き出す(`tools/generate_mlib_stubs.py` の `_forwards`。`Nodes` は `Node`・`DagNode`・`Transform` のメソッド)。`Nodes` は要素の型を引数に取る(`Nodes[Transform]`。既定は `Node`、共変)ため、`mlib.ls(type="transform")[0]` は `Transform`、`for n in mlib.ls(type="joint")` の `n` は `Joint` として補完される。型を指定しない `ls` の戻り値は従来どおりの組み合わせ型。実行時も `Nodes[Transform]` と書けるよう `Nodes.__class_getitem__` はクラス自身を返す。
- 複数形が持つのは、listとしての振る舞い(`__iter__`・`__len__`・`__getitem__`・`copy`、6.0.0で `+`・`==`・`sort`)と入力検証(`_resolve_inputs`・`_validate_inputs`)、一括の書込み(5.0.0)に加え、`Joints.sortedByDepth()`・`Joints.removeInfluence()`・`Joints.delete()`(10.6.0)だけとする。`+` は左辺の型で構築と同じ重複除外・型検証を行い、`==` は同じ並びのコレクション・list・tupleと比べる(このためハッシュ不可)。`sort(*, key=None, reverse=False)`(2026-11-26から list.sort と同じくキーワード専用)はその場で並べ替えてNoneを返し、keyの省略時は完全名(コンポーネントは実番号)の順にする。
- `mlib.ls` は常に集まりで返す(6.0.0): ノードだけなら `Nodes`(`type="joint"` は `Joints`、`type="skinCluster"` は `SkinClusters`)、アトリビュートだけなら `Plugs`(`plugs/plug.py`)、同じシェイプの同じ種類のコンポーネントだけなら `Vertices`/`Edges`/`Faces`/`UVs`/`CVs`。種類が混在する場合だけlist、それ以外の0件は空の `Nodes`(コンポーネント型指定の0件はシェイプが決まらないため空の `Nodes`)。集まりは構築と同じく重複を除く。
- `Plugs` は `Nodes` と同じ入力順・重複除外の規則で `len`・添字(sliceはPlugs)・`for`・`bool`・`+`・`==`・`sort`・`repr` だけを持つ。`maya.cmds` へ渡すとcmdsが各Plugの名前へ展開する。Componentsの `+` は同じシェイプ・同じ種類どうしだけで、それ以外はTypeError。
- `item_class` で受け入れるラッパー型を宣言する。入力は各基底クラスの共通処理で解決し、型の不一致を黙って除外せず例外にする。登録済みの外部拡張の派生ラッパーを基底型へ置き換えない。
- 重複は同一ノードかつ同一DAGパスで判定する。異なるインスタンスパスをUUIDだけでまとめない。構築後の参照の削除によってコレクション長を暗黙に変えない。
- 整数アクセスは保持中の参照、スライス/copyは同じ具象コレクションで同じシーン対象を参照する。ノード複製とは別。
- 2026-11-10のユーザー指定(10.6.0)により、`Joint.delete`・`Joints.delete` は自身と子孫のinfluenceを解除し、ウェイトを残る祖先influenceへ移してから削除する(`removeInfluence=False`でMaya標準の削除。fastはウェイトの書込みと削除をOpenMayaで行い、OpenMayaに無い登録解除だけをUndoへ記録しないcmdsで行う)。この解除と`SkinCluster.removeInfluence(s)`・`Joint(s).removeInfluence`は、ウェイトのロックを一時的に外して元へ戻す。ngSkinTools2のレイヤーはレイヤーごとに移送し(`core/ngSkinLayers.py`。ngSkinTools2は任意依存で、自動ロードしない)、使えない場合のレイヤーは拒否せずskinClusterのウェイトだけを書き換える。複数の解除は親子の連鎖を最終の移送先へ1回で書き、0にした列の登録をまとめて解除する(値が残る列を一括で外すとMayaの再配分の結果が変わるため、移送先の無いものは1本ずつ外す)。`mlib.delete(joints)` はMaya標準削除のまま。子を残す階層整理は`mlrig.setups.JointHierarchy.delete(joints, *, safe=False, fast=False)`へ分ける。一般にUndo対応は失敗時の自動ロールバックを意味しない。`ls`の返却規則は維持する。


### 参照対象と取得契約

- 独自のアトリビュート操作名は `Attr/Attrs`。ユーザー定義アトリビュートの列挙は `getPlugs(userDefined=True)` で、専用の `Extra` 名は置かない。フラグ設定は `setFlags` を使う。
- メソッドのオーバーライドで対象を切り替えない。`Reference.getAssociatedNamespace` は参照内容、継承した `getNamespace/setNamespace` はreferenceノード自身を扱う。
- 内部の接続用参照は `*_plug`、文字列のみの一覧は `*_names` / `*_aliases` などで対象を明示する。公開名はlowerCamelCaseとする。
- マルチアトリビュートの `getElement` は既存要素のみ。`multi[index]` は未作成の非実体化参照も返し、作成はset/connectで行う。
- `PluginPackage.tryLoad` は状態文字列を返し、`Plugin.ensureLoaded` は失敗時に例外を送出する。成功保証の違いを隠さない。
- `getVisibility/setVisibility` は自身のvisibilityアトリビュートだけを扱い、階層や表示レイヤーを含む最終可視性と区別する。
- 2026-10-31のユーザー指定(9.0.0)により、キーは `mlib.Keyframe`/`Keyframes`(Mayaの setKeyframe・keyframe に合わせた名前)で「カーブ + キーの番号」を作成時に固定した参照として扱う。頂点と同じくキーの追加・削除の後の同一性は保証しない。ドリブンキーのカーブも同じクラスで、時刻はカーブの入力値を指す。編集は AnimCurve の処理を呼び、`Keyframes` の編集は全体で1回のUndo。選択キーは `Selection.getKeyframes()` と `mlib.ls(selectedKeyframes=True)`(他の引数と併用しない)。キーの範囲操作は AnimCurve(`moveKey`・`scaleKey`・`removeKey`・`replaceKeys`)、Plug・Node(`setKey`・`removeKey`・`moveKey`)の両方に置き、`index`(番号・番号の並び)・`time`(時刻・範囲)で絞る。`AnimCurve.removeKey` は既定でカーブを残し(`keepCurve=True`、Mayaの cutKey はロック中のノードを消さないためその間だけロックする)、Plug・Node の removeKey は Maya と同じく空のカーブを消す。`AnimCurve.setKey` の接線型の省略は `cmds.setKeyframe` と同じ(既存は保ち、新規は Default tangent)。

## 参照と入力の固定規則

- Nodeの等価比較(`==`)は生存中のMaya対象、DAGではインスタンスパスも含む。JointだけのUUID比較は廃止。`sameNode` はパスに関係なく同じMayaノードかを比較する。旧 `sameInstance` は `==` と同じなので廃止した。
- Nodeのhashは生成時のMObjectHandle.hashCodeを保持。Plugは所有ノードのhashと生成時のアトリビュートパスを保持する。改名・削除でhashを変えず、永続IDとして保存しない。完全破棄後は他参照と等価にしない。可変数学型はhash不可を維持。
- getNode/Nodeは動的に型解決するが、具体クラスの構築はその型または派生に適合しなければTypeError。Nodeと同一のノードを別の具体型へ無理にラップしない。動的クラスが選ばれる型でも同じ(`mlib.Joint("pointLight1")` はTypeError、`mlib.PointLight("pointLight1")` は可)。
- 保持DAGパスの消失を別インスタンスへの自動切替で補わない。ノードの有効性とパスの有効性を区別する。
- ノード対象列では文字列とNodeの混在を変更前にTypeErrorにする。名前列/Node列は両方許可し、派生型はNode形式として扱う。空入力や操作対象型の制限は各操作の仕様を維持する。
- reload後の旧インスタンスは取得し直す。動的に生成したクラスの参照も同じで、reload・登録表の変更・`Plugin.load/unload` の後は `mlib.nodes.<TypeName>` を取り直す。新旧クラスの相互比較/自動移行を保証しない。
- lsの専用コレクション返却、copy/sliceの参照共有、bulk失敗時の停止・自動ロールバックなしを維持する。
- Maya依存の有無は責務分離の基準にしない。対象に固有の取得・計算・更新は同じクラスに置く。

## 利用側が担当する操作

- 標準UIの作成・参照・エディター起動は利用側のcmds/mel、Qt変換は利用側のUIパッケージへ置く。
- ユーザー設定は利用側でMaya標準APIを明示使用する。
- 2026-11-23のユーザー指定により、シーン/プロジェクト/FBX操作をmlibに入れない決まりを無くした。シーンのファイルは`mlib.common.Scene`(`pathlib.Path`の派生。Maya 2022のPython 3.7では`Path`を直接継承できないため`type(Path())`を継承する)で扱う。`Scene(path)`は値を持つだけでシーンを変えず、今のシーンは`Scene.getCurrent()`(名前の無いシーンはNone)。Pathの`open()`を上書きしないため、開くのは`openFile`。保存・書き出しの形式は拡張子(.ma/.mb)で決め、別のファイルの上書きと保存していない変更の破棄は`force=True`のときだけ行う。`export(nodes=None)`は全体と選択の書き出しを1つにまとめた。`reference`は既存の`references.createReference`を呼ぶ(両方残す)。プロジェクト・FBXは必要になったら足す。
- 通常JSON文字列は標準jsonで扱う。型codec・汎用Snapshot・参照保存の本体機能は持たない。
- 2026-11-10のユーザー指定により、表示色は何の色かが名前で分かる`getOverrideColor`/`setOverrideColor`と`getOutlinerColor`/`setOutlinerColor`を`DagNode`・`Nodes`に置き、`Nodes`には一色ずつの`setOverrideColors`/`setOutlinerColors`も置く。色は番号・(r, g, b)・無効のNoneで指定し、色値型は追加しない。どちらも既定はTransform・Jointでも呼び出したノード自身へ設定し、`shape=True`で直下の中間でないShape全てへ設定する(Shapeが無ければ自身)。
- ConstraintはTransform派生。Nodesは全DGノード共通の参照・アトリビュート・接続処理を扱う。
- mlibはQtをimportしない。横断的な通知はlogger、表示停止と復帰はdecorator.viewportOffを使う。

## 入力解決とパッケージ境界

- `core/object.py` の `Object` は単数の `Node`・`Plug`・`Component` の共通基底。取得は `from mlib.core.object import Object` とし、ルートへ再公開しない。`Object(value)` は具体的な参照型を返し、既存ラッパーはそのまま返す。比較・ハッシュ・寿命は各参照型が担当する。
- `Node._resolve_input()` はノードを必要とする内部処理、`Plug._resolve_input()` はアトリビュート入力、`Component._resolve_input()` は単一要素入力を解決する。各公開APIで判定処理を複製しない。
- `Object._input_name()` / `_input_names()` はcmds向けの名前変換。文字列をそのまま渡す既存の規則を維持し、対象解決を必要とする `Object()` と区別する。
- `Nodes._resolve_inputs()` は複数入力を検証する。名前だけ／Nodeだけを受け付け、同じ対象列の文字列とNodeの混在は拒否する。空集合など各APIの規則は維持する。
- 実行フォルダは `nodes`・`plugs`・`components`・`maths`・`cmds`・`common`・`core` とする。選択・名前空間・参照関係、単位、プラグイン導入状態、イベント・遅延実行、既存の共通計算の型は `common` 直下へ統合する。領域別のサブフォルダは作らず、具体的な機能名のファイルから提供する。
- ログ・通知・出力は `mlib.logger`、デコレーター・コンテキストマネージャーは `mlib.decorator` を正式入口とする。文書と生成設定は `_docs` に置く。汎用UI・設定・保存フレームワークは本体へ追加しない。
- クラスに属さない小さな汎用関数は直下の `mlib.util` に置く。公開は `legalizeName`・`measure`・`mirrorArguments` の3件。数学値の添字・比較・派生状態の補助と空間指定の検証は先頭`_`の内部関数とし、utilからNode/Plug/core/decoratorをimportしない。
- `core`は通常の実行パッケージであり、フォルダ名だけで公開/非公開を決めない。正式なAPIは明示import・`__all__`・文書で示す。集約した内部補助は先頭`_`で示し、既存の内部連携・登録プロトコル名は維持する。既存の `core.NodeRegistry`・`core.reload_package` と登録プロトコルの名前・意味を維持し、全helperの公開や一括改名はしない。旧 `mlib._core` の互換入口は残さない。`_docs`・`__tests__` は実行APIと別の素材なので配置名を維持する。
- 拡張管理の正式入口は `core/extensions.py` とし、拡張作者は `from mlib.core import extensions` を使う。ルートへ再公開せず、旧モジュールパスの互換入口も残さない。
- 数学値・複数形コレクション・UI・保存データは `Object` の派生にしない。既存の便利メソッド・Undo・fastの意味は維持する。
- 旧 `general` / `_core/coerce.py` の互換ファイルは残さず、内製利用側も正式な配置へ更新する。

### 内部の参照方向

- 入力の汎用展開は `Object._flatten_inputs()`、展開済み列の名前/Node混在検査は `Nodes._validate_inputs()`。検査からObjectの展開へ戻らない。`Nodes._resolve_inputs()` は両者を順に呼ぶノード側入口。
- 公開コマンドはクラス側の共通処理に委譲する。`createNode` はフラグ正規化とUndoチャンクを一本で行い、内部ヘルパー `Node._create_node(node_type, flags, *, fast=False)` へ委譲する(`Container.createNode` も同じヘルパーを呼ぶ)。クラス側から公開コマンドへ戻らない。Undoと短縮フラグは各公開入口の契約を維持する。
- Undo等のコンテキストは `decorator.py`、定義に基づく単位境界は `core.attributeType._convert_units`、型継承照会とその単一キャッシュは `core.registry` に集約する。fast/safeは各メソッド本文で判定し、更新先へ明示的に渡す。長短の引数も通常defへ列挙して本文で検証し、Maya helpの実行時解析・別名メタデータ・汎用resolverは使わない。省略判定専用の`util._UNSET`でFalse/Noneの明示指定と省略を区別する。長短競合・必須値欠落は各単数の更新前に拒否する。通常Undo・安全検証と単位の既存規則を維持する。

### 任意拡張の参照方向と再読み込み

- 拡張はmlibの公開APIへ依存し、他のmlib_*をimport・継承しない。組合せ処理はmlrig等の利用側に置く。
- 拡張の__init__.pyは宣言を先に完了し、mlibやラッパーを先行importしない。公開サブパッケージは必要時に読み込む。
- mlib.reload()は宣言済み拡張の一括解除、本体の再読み込み、拡張の再検出・登録の順で処理する。外部SDKとMayaプラグインは再ロードしない。
- 定義モジュールの再読み込みはreload処理が一度だけ行う。ルートの初期化でNode/Plug両方の明示対応表を検証し、構築できた登録表を両基底へ代入する。任意拡張の登録はその後に行う。動的クラスのキャッシュは登録表が持つため、reloadで登録表を作り直すと生成クラスも廃棄される。
- リロード後は利用側の拡張パッケージ・クラス・インスタンス参照(動的に生成したクラスを含む)を取得し直す。初期化中のリロードは拒否する。


## 対象を所有するクラスへの委譲

- 具象Nodeは対象Plug・値の意味・更新順を決め、値設定はPlugへ委譲する。通常/fastの型付き書込みと単位境界をノードごとに再実装しない。
- 複数Plugの更新可否を先に調べる処理は、Plugの内部検証を使う。事前検証と自動ロールバックは別の契約であり、fastの実行途中の失敗を自動で戻す保証はしない。
- MultiPlugは論理番号と要素の参照・存在を管理する。`multi[index]`は未作成でも参照を返し、`getElement(index)`は既存要素のみを返す。`create`引数と`addElement`は公開しない。要素は値設定・接続で作成し、参照取得や検証で事前に実体化しない。空き番号の探索は `getNextAvailable(vacant=)`、messageのマルチアトリビュートへの追加は `appendMessage`(対比は「2026-10-26の統合で確定したメソッド契約」)。
- MultiPlugの`getIndices()`は既存の論理番号を昇順で返し、`getElements()`と同じくワールド空間アトリビュートのDAGインスタンス番号も含む。型固有の番号選択はノード側、列挙・既存性の管理はMultiPlug側へ寄せる。
- Mesh/Curveの単数・複数コンポーネントとShapeの座標書込みは、非公開のgeometryEditを共有する。通常cmds/fast om2、CVの番号変換・重み・単位変換をこの境界へ集約する。Shapeは変形する座標列を決める。
- Transform姿勢とJoint固有の変換、SkinClusterの一括ウェイト処理は、それぞれの意味と効率を持つため単純なPlugの反復へ置き換えない。

### 公開メソッド名と生API取得

所有Plugの`getNode()`は保持参照でもメソッドとする。独自の取得は`getParent/getLongName/getFullName`等の正式名へ集約し、取得短名の互換入口は残さない。判定の正式is名と`hasAttr`、操作の`delete`、生API取得の`mnode/mpath/mplug`はそれぞれの確定契約を維持する。固定Plugの参照だけを返す専用入口は増やさず、`getPlug()`を使う。用途ごとの固定一覧は利用側で選定する。複数フラグを扱う`setFlags()`等の独自操作は維持する。詳細・制限は`maya/inhouse/mlib/nodes/node.py`と`maya/inhouse/mlib/plugs/plug.py`の公開APIのdocstringを参照する。

マルチアトリビュートの要素参照の標準表記は`multi[index]`とし、未作成の論理番号も非実体化のPlugとして参照できる。マルチアトリビュート反復は既存要素の論理番号順、`get()`は番号を保持する辞書。既存要素だけの取得には`getElement(index)`を使い、未作成ならIndexErrorとする。コンパウンドアトリビュートの子もユーザーの統一指示により`compound[index]`・`compound[name]`とし、旧childメソッドは残さない。コンパウンドアトリビュートの整数番号は0以上の定義順、反復は子の定義順。マルチアトリビュート・コンパウンドアトリビュートのPlugをmaya.cmdsへ渡す時はstrまたはgetFullNameで文字列化する。mlibコマンドでは直接受け取る。Plugの`setAlias`・`setKey`は自身を返す。`setKey`内部はmaya.cmds.setKeyframeを直接使用し、mlib.cmdsの同名ラッパーは作らない。


### 参照・計算・書込みの責務

- Transformの設定予定値の計算とチャンネル書込みは内部で分ける。`safe/get/at/ra/r/jo/worldSpace`の既存の意味、返却型、単位は変更しない。通常cmdsのUndoとfastのOM2直接更新を維持し、内部のチャンネル更新へfast/safeを明示的に渡す。呼出元の状態で`fast=False`や省略値を上書きしない。
- Transformationは入力をコピーして保持するが、成分プロパティは保持する可変値の参照を返す。合成マトリクス・quaternionとMatrixの成分取得は独立した値である。Transformationのmatrix代入・マトリクスによる自身更新では成分が置き換わり、以前取得した成分参照は更新先へ追従しない。ノードから取得した値はシーンと独立し、反映には明示的なsetterを使う。
- `moveAttrOrder`は対応する定義・値・フラグ・別名を復元し、全定義が揃ってから接続を復元する。変更途中の失敗はこの処理のUndoで復元するため、実際に並びを変更する場合はUndo無効を削除前に拒否する。fast引数は持たず、通常Undoを使う。

## 追加アトリビュートの既定値変更(2026-11-18)

ユーザーの明示指定により、`Plug.setDefault(value, *, fast=False, unit=None, uiUnits=False)`は通常経路も提供する。通常の`cmds.addAttr`には、Undoで変更前の既定値でなく0へ戻る制限がある(Maya 2022〜2027)。Redoは指定値へ戻る。一般のsetterのUndo保証の例外とし、補償用のプラグイン・再作成・コールバックは追加しない。fastはOpenMayaの定義更新でUndo設定を変えない。

対象は非参照ノードの単一の追加数値・bool・enum・角度・距離。時間型・マルチアトリビュート・コンパウンドと子・プロキシ・組込み定義は拒否する。現在値と接続を保持するため、更新前にget()で現在値を評価する。角度は度(明示rad可)、距離はcm、uiUnitsはUI単位を使う。戻り値はNone。

## mlibの使用事例を増やすための追加(2026-11-23)

ユーザー指定により、inhouseのツールをmlibで書いた版(mlrig・AnimBar・SkinWeightKitは書き換え、ほかは各ツールの`byMlib/`)で足りなかった機能を足した(不足の一覧はローカルの`docs/research/byMlib/gaps-*.md`)。メソッドを増やしすぎないよう、既存のメソッドへの引数を優先した。

- シェーディングの分類(`asShader`・`asTexture`・`asUtility`・`asLight`・`asPostProcess`・`asRendering`)は新しい関数でなく`createNode`の引数にする(`cmds.shadingNode`で作る。2つ以上はTypeError、fastとの併用はNotImplementedError。短縮名`s`はsharedと重なるので持たない)。
- 作成関数を足した: `createShadingEngine`・`createMotionTrail`・`createExpression`。`createPoly*`は`constructionHistory`/`ch`・`createUVs`/`cuv`(Cylinderは`roundCap`/`rcp`も)、`createBlendShape`は`origin`/`o`を受ける。
- `indirect`は「setKeyframeが打つ先のカーブ(アニメーションレイヤー・pairBlendの先)」を意味する名前で、`Plug.getAnimCurve`と`Transform.eulerFilter`で同じ意味に使う。
- `ScriptJob.stop`は常にforceで消す。`ScriptJob`は`uiDeleted`・`parent`・`allChildren`・`runOnce`・`protected`を受ける。
- `SkinCluster.smoothWeights(vertices=None)`は対象の頂点を実行中だけ選び、作業中の選択に左右されない(省くとメッシュ全体)。2つ目以降の形状は、後述の`geometryIndex`で指定する。
- `AnimCurve.replaceKeys`は同じ型のAnimCurveも受け、接線・ウェイト・ロック・ブレイクダウンまで写す(キーのクリップボードは使わない。前後のinfinityは写さない)。
- `Components.getNames()`は`cmds.ls(flatten=True)`と同じ1要素ずつの名前を返す。
- `Matrix.asRotateMatrix()`は回転だけ(正規直交)を返す。`om2.MTransformationMatrix(m).asRotateMatrix()`はスケール・シアーを含む3x3を返すので、元の計算に合わせるときはそちらを使う。
- 最初は足さなかったが、同日のユーザー指定で足したもの(byMlibの残り7件):
  - `SkinCluster.getWeights`・`setWeights`・`getVertexWeights`・`setVertexWeights`・`smoothWeights`にキーワード専用の`geometryIndex=None`(`input`・`outputGeometry`の論理番号。`getGeometryIndex`で求める。Noneは先頭の形状)を足した。内部は`mesh_path`だけを差し替えた写し(`_geometry_view`)で処理する。Mayaのskinクラスタは変形するすべての形状で`weightList`を共有するため(同じ番号の頂点は形状が違っても同じウェイト。Maya 2027で確認)、差し替えるのは頂点の数・番号の確かめとOpenMayaへ渡す形状だけでよい。既定をGeometryFilterの`geometryIndex=0`と違うNoneにしたのは、先頭の形状の論理番号が0でない場合に今の動きを変えないため。ほかのウェイトのメソッド(`limitInfluences`等)は先頭の形状のまま。
  - `Node.getAttrNames(**listAttrFlags)`は`cmds.listAttr`と同じ名前・順の`list[str]`を返す(`getPlugs`はPlugにできない、番号を決めていないマルチアトリビュートの子を省く)。名前を返すので「mlibのオブジェクトを返す」の例外(名前)に入る。
  - `Faces.extrude(*, curve=None, divisions=1, keepFacesTogether=True)`は`cmds.polyExtrudeFacet`を1回実行し、作ったpolyExtrudeFaceを返す(作成履歴を残す。Mayaのコマンドと同じく押し出したフェースが選ばれる)。モデリングのコマンドはこれが最初。
  - `mlib.findCycles(nodes=None, *, dag=False, timeLimit=None, firstOnly=False)`(`cmds/`)は`cycleCheck(list=True, secondary=True)`の経路ごとに`Plugs`を返す(Noneはシーン全体)。`Node.findCycles()`は1つのノードを通る単純な循環を接続からたどって並べるもので、DAGの依存・部分経路を返す`cycleCheck`の指定とは意味が合わないため、引数は足していない。
  - `mlib.isNodeType(name)`(`cmds/`)は`cmds.allNodeTypes(includeAbstract=True)`にある型名か(抽象型も含む)を返す。
- SkinWeightKitの見直し(同日のユーザー回答): `SkinCluster.limitInfluences(count, *, vertices, fast, check)`・`roundWeights(decimals=3, *, vertices, fast, check)`を足し、`transferWeights`に`vertices`・`add`を足した(ロックしたインフルエンスは値を保ち、残りの比率で合計1にする規則。`vertices`か`add`を指定したときは行を読んで変わった値だけを書き、移す元・先がロックされていればRuntimeError)。ロックの照会・変更は`getLockedInfluences`・`setInfluencesLocked`がジョイント以外も扱えるので変えていない。

## クラスの親は1つ(2026-11-23)

ユーザー指定により、mlibのクラスの親は1つにする。ミックスイン・多重継承は使わず、責務は1本の継承の中に収める(例外クラスも同じ)。
`_tools/check_mlib_layout.py` の L056 が、親が2つ以上あるクラスを報告する。

- 別の系統のクラスで同じ処理が要るときは、共通の親へ上げるか、モジュールの関数に置いて各クラスから呼ぶ。
  種類ごとの違いは、クラス属性と、派生クラスが上書きする先頭 `_` のメソッドで持つ。
- 既にあった多重継承を無くした。
  - コンポーネント: 番号を複数持つ要素(`SurfaceCV`・`LatticePoint`・`VertexFace` と複数形)のミックスイン `_MultiIndexComponent`・`_MultiIndexComponents` をやめ、
    基底の `Component`・`Components` に取り込んだ。具体的なクラスは `index_size` を2以上にし、`_element_count`・`_multi_indices`・`_flat_indices` を上書きする。
    `getMultiIndex()` は基底のメソッドになり、番号が1つの要素では `(index,)` を返す。
  - コンテナー: `_ContainerMixin` をやめ、メンバー・公開の操作13個は `Container(Node)` に置いた。`DagContainer` は `Transform` だけを親にし、
    同じ名前の13個のメソッドが `Container` のメソッドを呼ぶ(ユーザーの選択。`isinstance(dag, Container)` はFalseになるので、コンテナかは `isType("containerBase")` で調べる)。
  - 例外: `MissingAttributeError` は `AttributeError` だけ、`DeletedAttributeError` は `ValueError` だけの派生にした(以前はどちらも `RuntimeError` の派生でもあった)。
    名前のアトリビュートが見つからないとき(`mlib.getPlug("node.nope")`・文字列を渡す `connect`・`isConnectedTo`・`DrivenKey` など)は、`except RuntimeError` では捕まえられず、
    `except AttributeError` で捕まえる。アトリビュートが削除されたPlugをノードの引数に渡したときは `ValueError`。

## メソッドの共通化(2026-11-23〜)

ユーザー指定により、公開メソッドの数を減らす。機能は減らさず、(1) 汎用の入口(Plug・`mfn()`)で書けて利用側が使っていない専用メソッドを削る、
(2) 似たメソッドを、違いを引数で選ぶ1つにまとめる、(3) 同じ中身を基底へ上げる、の3つで進める。
検討の経緯と数はローカルの `docs/research/mlib-method-consolidation/`(proposal3〜12.md、進み具合は implementation-plan.md)。段ごとに実装し、ここへ結果を書く。

- 段1(計算ノード): `multiplyDivide`・`plusMinusAverage`・`condition`・`composeMatrix`/`decomposeMatrix`・`blendMatrix`・`remapValue` など27型のクラスから、
  専用メソッド112個(`setInput`・`getResult`・`getOutputPlug`・`get/setOperation`・`get/setRotateOrder`・`addInput`/`removeInput`/`getInputIndices`・
  `addTarget`/`removeTarget`/`getTargetIndices`・ランプの点の操作など)と補助の `nodes/_calculation.py` を削った。クラスは型の選択と `isinstance` のために残す。
  代わりの書き方: 値は `node.getPlug("input1").set(...)`、接続は `plug.connect(...)`、結果は `node.getPlug("output").get()`、
  演算の種類は `node.getPlug("operation").set("Divide")`(Maya のフィールド名。番号でもよい)と `getEnumName()`、
  マルチアトリビュートの入力は `MultiPlug.getNextAvailable()`・`removeElement()`・`getIndices()`、ランプは `RampPlug.getEntries()`・`setEntries()`。
  専用メソッドが受けていた小文字の演算名(`"divide"`)は無くなり、Maya の表記(`"Divide"`)になる。利用側での使用は無かった。
- 段2(使われていない専用の get/set・照会): アトリビュート1つを読み書きするだけ、または om2 の値を1つ返すだけの公開メソッドのうち、
  利用側で使われていない63個を削った。主なもの: `Plug` の `isDynamic`・`isReadable`・`isWritable`・`isStorable`・`isConnectable`・`isCaching`・`isNetworked`・`getAffected`・`getAffecting` など14個、
  `Node` の `getTypeId`・`getPluginName`・`isDefaultNode`・`isRoot`・`isShared`・`getNumAttrs`・`getAbsoluteName` など10個、
  `NurbsSurface` の `getDegree`・`getNumSpans`・`getNumPatches`・`isTrimmed` など8個、`NurbsCurve` の `getDegree`・`getNumSpans`・`getForm`・`isPlanar`、
  `DagNode` の `isDrawOverrideEnabled`・`getOutlinerVisibility`/`setOutlinerVisibility` など7個、`File` の `get/setFilePath`・`get/setColorSpace`、
  `Camera` の `getFocalLength` など4個、`AimConstraint` の `get/setOffset`・`getOutputRotate`、`BlendShape` の `getWeightPlug`・`getHistoryLocation`・`duplicateTarget`。
  代わりは `node.getPlug("x").get()`/`set()` と `node.mfn().<名前>`・`plug.mplug().<名前>`。
  残したもの: mlib の内部が使うもの(`Plug.getShortName`・`isChannelBox`・`isProxy`、`AnimCurve.isWeighted`、`IkHandle.getSolver` など16個)、
  対になる設定側が残るもの(`Camera.getAspectRatio`・`Plug.getAlias`・`Edge.isSmooth` など6個)、
  コンポーネントのクラスが名前の文字列(`count_attribute`)で呼ぶ要素数の取得(`Mesh.getNumPolygons`・`getNumEdges`・`getNumUVs`、`NurbsCurve`・`NurbsSurface` の `getNumCVs`)。
- 段3(転送と同じ複数形・数学型の自身を変える版・別名): 13個を削った。
  - 数学型の「自身を変える版」11個: `EulerRotate.mirrorIt`・`roundIt`・`reverseDirectionIt`、`Matrix.transposeIt`・`mirrorIt`、`Quaternion.unitIt`・`mirrorIt`、
    `Vector.mirrorIt`・`roundIt`・`unitIt`・`orthogonalIt`。代わりは、コピーを返す版を受け取る(`v = v.unit()`・`m = m.mirror("x")`)。
    om2 から継承した名前(`invertIt`・`reorderIt`・`normalize()` など)は残る。独自の「…It」は置かない決まりにした。
  - 別名3個: `Selection.items` → `getItems()`、`Matrix.euler` → `rotate`、`Quaternion.asEulerRotate()` → `asEulerRotation()`(om2 の名前)。
    `Shape.getTransform` は利用側で広く使われているので残した。
  - 複数形の明示メソッド2個: `Nodes.setAttrFlags`・`setLocked`。自動の転送(`__getattr__` → `_forward`)と同じ動きなので、呼び方は変わらない
    (Undo チャンク名も同じ `mlibNodesSetAttrFlags`・`mlibNodesSetLocked`)。戻り値だけが `None` から要素ごとの `[None, ...]` になる。
  - 削らなかったもの: `Nodes.show`・`hide`・`getOverrideColor`・`getOutlinerColor`。この4つは `DagNode` のメソッドなので、転送にすると
    要素が無い `Nodes`(`item_class` が `Node`)で AttributeError になる(明示メソッドは何もせず `None`・`[]` を返す。`mlib.ls(...)` の結果が空のときに違いが出る)。
    `Nodes.setOverrideColor`・`setOutlinerColor`・`setVisibility`・`resetAttrs`・`setParent`、`Joints.setRadius`・`setSegmentScaleCompensate`・`getSkinClusters`、
    `Edges.getVertices`、`Faces.getVertices`・`getEdges`、`UVs.getPosition` も、書く前に全要素を確かめる・結果を1つにまとめる・まとめて読むので残した。
- 段5(json の内部の部品・兄弟クラスの同じ本体): 公開の名前を30個減らした(非公開へ21、削除2、基底へ上げて7)。
  - json の部品21個を非公開にした: `NodeRef`・`PlugRef`・`ComponentRef` の `fromData`/`toData`/`mappedName` → `_from_data`/`_to_data`/`_mapped_name`、
    `ValidationReport.addMissing`/`addSkipped`/`addError` → `_add_missing`/`_add_skipped`/`_add_error`、
    `Header.fromData`/`toData`/`convertTime` → `_from_data`/`_to_data`/`_convert_time`、`codec.encode`/`decode` → `_encode`/`_decode`、
    `file.currentFps`/`dump`/`load` → `_current_fps`/`_dump`/`_load`、`NameMapping.applyPath` → `_apply_path`。
    `mlib.json.encode`・`decode`・`dump`・`load`(パッケージ直下の再公開)も無くした。利用側での使用は無かった。
  - 削った2個: `NameMapping.isIdentity`(どこからも使われていない)、`Snapshot.fromData`(コンストラクターと同じ。`PoseSnapshot(data)`)。
  - 候補のうち公開のまま残した6個: `ValidationReport.missing`・`skipped`・`valid`(`apply`・`validate` が返す結果を利用者が読む)、
    `Header.mlib`・`fps`(`Snapshot.header` で読み込んだファイルの情報を読む。`format`・`version`・`maya` と同じ扱い)、
    `Snapshot.toData`(データを辞書で取り出す唯一の入口)。
  - Snapshot の4種類(`AttributesSnapshot`・`DrivenKeysSnapshot`・`PoseSnapshot`・`SelectionSnapshot`)の `apply` は本体が同じなので、基底の `Snapshot.apply` へ上げた
    (引数と動きは同じ。種類ごとの説明は各クラスの docstring へ移した。追加の引数を持つ `AnimationSnapshot.apply` は上書きのまま)。
  - `Module` と `Plugin` の同じ本体(`name`・`getVersion`・`isVersionAtLeast` と `__init__`・`__str__`)を、新しい共通の親 `common/versionedItem.py` の
    `_VersionedItem` へ上げた。Maya のコマンドが違う `isRegistered`・`getPath`・`getVersionText` と、型を比べる `__eq__`・`__hash__`・`__repr__` は各クラスに残した。
  - 対象外: `Component` と `Components` の `shape`・`index`、`isOnBoundary`(Vertex・Edge・Face)は、共通の親が無い
    (親に置くと関係ないクラスにも付く)ので上げていない。
- 領域1a(コンポーネント): `components/` の公開メソッドを、機能を残して引数でまとめた(公開の名前は44個減)。あわせて決まりを
  「種類を選ぶ引数で戻り値の型が変わってよい(型スタブはオーバーロード)」「更新する対象が違う操作も、同じ種類の値ならフラグでまとめてよい(壊し方が違うものは別)」に改めた。
  - 頂点・CV の位置(`PointComponent`・`PointComponents`。−15): `getPositionX/Y/Z` → `getPosition().x`(複数形は `[p.x for p in pts.getPosition()]`)、
    `setPositionX/Y/Z(v)` → `setPosition(v, axis="x")`、`moveBy(offset)` → `setPosition(offset, relative=True)`、
    `PointComponents.setPositions(values)` → `setPosition(values, each=True)`。署名は
    `setPosition(value, worldSpace, *, axis=None, relative=False, [each=False,] fast=False, check=False, ws)`。`axis`・`relative`・`each` はどの組み合わせも意味が通るので全部受ける
    (`axis`+`relative` はその成分だけ足す、`each`+`relative` は要素ごとの移動量)。複数形の旧 `setPositionX` は数値1つと並びの両方を受けていたが、
    数値1つは `each=False`、並びは `each=True` と明示する。値の形が `each`・`axis` と合わないときは TypeError(座標の並びを `each=False` で渡しても全点が1か所に集まらない)。
    Undo チャンク名は `mlibPointComponentSetPosition`・`mlibPointComponentsSetPosition` の1つずつ。fast・check・worldSpace の動きは同じ。
  - UV(`UV`・`UVs`。−9): `getU()`・`getV()` → `getPosition()[0]`・`[1]`、`setU(v)`・`setV(v)` → `setPosition(v, axis="u")`、
    `UVs.setPositions(values)` → `setPosition(values, each=True)`。UV に `relative` は足していない(元から移動のメソッドが無い)。
    fast で入力ヒストリがあるときの文言のメソッド名は `setPosition` になった。
  - 名前(−4): `Components.getNames()`・`getFullNames()`・`getCompactNames()` → `getNames(*, full=False, compact=False)`。
    `getFullNames()` は `getNames(full=True)`、`getCompactNames()` は `getNames(full=True, compact=True)`(元から完全パスだった)。
    `getNames(compact=True)`(最短の名前でまとめる)は新しい組み合わせ。`CVs` の上書き2つは内部の `_full_names` になった。
    `Nodes`・`Plugs` の `getNames`/`getFullNames` と単数の `getFullName` は、ノード・Plug の領域でそろえる。
  - フェースの判定(−8): `isPlanar`・`isConvex`・`isStarlike`・`isLamina`・`isHoled`・`hasValidTriangulation`・`isZeroArea`・`isZeroUVArea`・`isUVReversed` →
    `Face.isKind(kind, *, uvSet=None, tolerance=None)`(`"planar"`・`"convex"`・`"starlike"`・`"lamina"`・`"holed"`・`"validTriangulation"`・`"zeroArea"`・`"zeroUVArea"`・`"uvReversed"`)。
    名前は、書き込み前の検査の引数 `check=` と重ならず、判定は `is` で始める決まりに合わせた。その種類で使わない `uvSet`・`tolerance` は TypeError。
    `isOnBoundary` は Vertex・Edge・Face にあるので残した。
  - 隣(−2): `Face.getConnectedFaces/Edges/Vertices()` → `Face.getConnected(*, type="face")`(`"face"`・`"edge"`・`"vertex"`。戻り値は Faces・Edges・Vertices)。
    名前をそろえるため `Edge.getConnectedEdges()` → `Edge.getConnected()`、`Vertex.getConnectedVertices()` → `Vertex.getConnected()`(数は変わらない。
    エッジ・頂点のほかの種類は `getFaces`・`getEdges`・`getVertices` が既にあるので、`type` は付けていない)。
  - 面積(−1): `Face.getUVArea(uvSet=...)` → `getArea(uv=True, uvSet=...)`。`uv=True` と `worldSpace`、`uv=True` でない `uvSet` は TypeError。
  - ループとリング(−2): `Edge`・`Edges` の `getRing()` → `getLoop(ring=True)`。
  - 頂点フェース(−3): `getBinormal()` → `getTangent(binormal=True)`、`setNormalLocked(state)` → `setNormal(locked=state)`
    (`normal` を渡すと今までどおり設定してロック。`normal` と `locked=False`、どちらも無しは TypeError)、`isNormalLocked()` → `getNormal(locked=True)`
    (bool を返す get になる。検証では勧めないとしたが、書けるものは全部採る決定に合わせた)。Mesh 側の `getFaceVertexNormalLocks` などは形状の領域で扱う。
  - まとめなかったもの: `Face.getPointAtUV`/`getUVAtPoint`(向きが逆の変換)、`Edge.getVertices`・`Face.getVertices`・`UV.getPosition` などの種類ごとの変換、
    `Vertices.grow`/`shrink`、`Face.getShadingEngine`/`getMaterial`。
  - 内部: 軸の名前と1成分の値の検査は `components/component.py` の `_axis_index`・`_axis_numbers`・`_edited_row`・`_require_single_row` に置いた(頂点・CV と UV で共有)。
- 領域1b(Plug): `plugs/` の公開メソッドを、機能を残して引数でまとめた(公開の名前は38個減)。これより前の節に残る古い名前(`getSource`・`getElements`・`isMultiElement` など)は、下の書き方に読み替える。
  - 範囲(−14): `getMin`・`getMax`・`getSoftMin`・`getSoftMax`・`getSoftRange`・`hasMin`・`hasMax`・`hasSoftMin`・`hasSoftMax` → `getRange(*, soft=False)`((最小, 最大)。無い側は None)。
    `setMin`・`setMax`・`setSoftMin`・`setSoftMax`・`setSoftRange` → `setRange(minimum, maximum, *, soft=False)`。**省略した側は変えず、None は制限を外す**(`setMin(a)` は `setRange(a)`、`setMax(b)` は `setRange(maximum=b)`)。
    両方省略は TypeError。片側だけのときは設定済みの反対側との矛盾を、両方のときは min > max を ValueError にする(今までの2つの検査を使い分ける)。片側だけでも Undo チャンクを開かない(1回の addAttr)。
    None で外した制限は、Maya の Undo では戻らない(以前の `setMin(None)` と同じ)。
  - 接続の判定(−3): `isSource()` → `isConnected(source=False)`、`isDestination()` → `isConnected(destination=False)`(引数は調べる相手の側なので、名前と逆に見える)、
    `isConnectedTo(other, ...)` → `isConnected(other, ...)`。
  - 状態(−4、−3、+1): `setKeyable`・`setChannelBox`・`show`・`hide` → `setFlags(...)`。`setFlags` に `leaf=`(末端の子だけ。`children` と同時は TypeError)を足した。
    keyable と Channel Box 表示は Maya が排他にする(`keyable=True` は Channel Box 表示を外し、`channelBox=True` は keyable を外す。fast でも同じ)が、Maya の Undo は外した側を戻さないので、
    `setFlags` が `keyable=True` のときは先に Channel Box 表示を外す書き込みを分け、`channelBox=True` だけのときは `keyable=False` も一緒に書く(旧 `setKeyable`/`setChannelBox` の動き。Undo 1回で元の2つの状態へ戻る)。
    `show()` → `setFlags(keyable=True, children=True)`、`show(keyable=False)` → `setFlags(channelBox=True, children=True)`、`hide()` → `setFlags(keyable=False, channelBox=False, children=True)`。
    `isKeyable`・`isChannelBox`・`isHidden` → 新しい `getFlags()`(`locked`・`keyable`・`channelBox`・`hidden` の辞書)。`isLocked`・`setLocked`・`isFromReferencedFile` は残した。
  - 入力の切断(−1): `disconnectInput()` → `disconnectAll(destination=False)`(入力だけなら Undo チャンクを開かない)。
  - MultiPlug(−3): `getConnectedIndices()` → `getIndices(connected=True)`、`getElementByPhysicalIndex(i)` → `getElement(i, physical=True)`、`getElements()` → `getElement()`
    (index を省くと、すでにある要素の Plugs。番号を渡すと、まだ無い要素も返す。`multi[i]`・反復は変わらない)。
  - 構造の判定(−2): `isMultiElement()` → `isMulti(element=True)`、`isChild()` → `isCompound(child=True)`。`getMulti` は残した。
  - 親(−1): `getAllParents(includeMulti)` → `getParent(all=True, includeMulti=...)`(`all=True` はマルチアトリビュートの要素も通るので、`all=False` の繰り返しとは同じにならない)。
  - アニメーションカーブ(−1): `getAnimCurveType(timeInput=)` → `getAnimCurve(suitableType=True, timeInput=)`。「つながっているカーブの型」ではなく「この Plug に合うカーブの型」なので、引数名を `type` にしなかった。
  - enum(−2): `getEnumName()` → `getEnumNames(current=True)`、`getEnumName(v)` → `getEnumNames(value=v)`、`getEnumValue(name)` → `getEnumNames(name=name)`。
    引数なしは今までどおり全部の `(名前, 値)`。「今の値の名前」を `current=True` に分けて、引数なしの意味がぶつからないようにした。
  - 存在(−1): `isExisting()` → `isValid(elements=True)`(既定の `isValid()` は変えていない)。
  - 接続の相手(−2): `getSource(...)` → `getConnections(input=True, ...)`(Plug か None)、`getDestinations(...)` → `getConnections(outputs=True, ...)`(Plugs)。
    どちらも「この Plug 自身」だけを見る(子・要素をたどらない)短い指定で、`source=False`・`checkChildren=False`・`index=0`(input のとき)などと同時に指定すると TypeError。絞り込みが無いときは今までと同じく MPlug へ直接問い合わせる。
    `getConnections(destination=False)` は子・要素もたどる Plugs を返すので、`getSource()` の置き換えには使わない(`is None` が常に False になる)。型スタブのオーバーロードは `getConnections` にまとめた。
  - 名前(−2): `getLongName()`・`getShortName()`・`getNiceName()` → `getAttributeName(kind="long"|"short"|"nice")`(`long` という引数名は「完全パス」の意味と紛れるので使わない)。
    `getFullName` → `getName(full=True)` と `Plugs.getNames`/`getFullNames` は、Node と合わせて後の段で行う。
  - まとめなかったもの: `isLocked`/`setLocked`(広く使われている)、Node と共通の基底へ上げる案(実装が別で、基底に置けるのは名前だけ)、`RampPlug`(似た名前の対が無い)、
    `set`/`setIfChanged`・`connect`/`connectTo`・`getDefault`/`isDefaultValue`・`setKey`/`setKeyTangent`。
- 領域2(基本のノード。2026-11-24): `nodes/` の node・dagNode・transform・joint・skinCluster・geometryFilter・コンストレイント・ikHandle・objectSet・dagPose・shadingEngine と `Plugs` で、公開メソッドをまとめた。
  - Transform の相対の変更(−4): `translateBy(v)`・`rotateBy(v)`・`scaleBy(v)`・`shearBy(v)` → `setTranslation`・`setRotate`・`setScale`・`setShear` の `relative=True`。
    translate・rotate は足す・回す、scale・shear は掛ける。相対でも `fast`・`safe`・`get`・`check` が使える。Maya のコマンドは1回なので Undo チャンクは開かない
    (`mlibTransformTranslateBy` などのチャンク名は無くなった)。`setTranslation(relative=True)` は `at` と、`setScale`・`setShear` の `relative=True` は `worldSpace=True` と同時に指定できない(TypeError)。
    相対の値の型・数・有限かの確認(TypeError・ValueError)は、今までどおり check に関係なく行う。
  - 描画の色(−3): `getActiveColor`・`getDormantColor`・`getHiliteColor`・`getDrawOverrideColor` → `getDrawColor(mode="dormant"|"active"|"hilite"|"override")`。
  - 表示色(DagNode −2、Nodes −3): `getOverrideColor`・`getOutlinerColor` → `getColor(outliner=)`、`setOverrideColor`・`setOutlinerColor` → `setColor(color, outliner=)`。
    `Nodes` は明示メソッドの `getColor`・`setColor`・`setColors(colors, outliner=)` の3つ(要素が無ければ何もしない・書く前に全要素を確かめる・Undo 1回は今までどおり。
    Undo チャンク名は `mlibNodesSetColor`・`mlibNodesSetColors`)。単数の Undo チャンク名(`mlibDagNodeSetOverrideColor`・`…SetOutlinerColor`)は変えていない。
  - バウンディングボックスと並び順(−2): `getBoundingBoxCorners()` → `getBoundingBox(corners=True)`(`includeInvisible` も使えるようになった)、`setOutlinerOrder(i)` → `reorder(index=i)`
    (`index` は端を越えない。範囲外は IndexError)。
  - ピボット(−3): `centerPivotsOnComponents(c)` → `centerPivot(c)`(`fast`・`check` も使える)、`getPivotTranslation`・`setPivotTranslation` → `getPivot(translation=True)`・`setPivot(v, translation=True)`
    (`translation=True` は `preserve`・`fast` と同時に指定できない。`getPivot(translation=True)` は Vector)。
  - 表示と非表示(DagNode −2、Nodes −2): `show()`・`hide()` → `setVisibility(True)`・`setVisibility(False)`。2026-10-26 の「両方残す」を改めた。
  - 親とシェイプ(−2): `getParents(indirect)` → `getParent(instances=True, indirect=)`(Plug の `getParent(all=True)` は祖先、こちらはインスタンスの親なので、引数名を分けた)。2026-11-25に DagNode にも `getParent(all=True)`(祖先を近い順にすべて。Plug と同じ考え方)を足した(`getAllParents` の案内が `instances=True` を指していて、祖先を取れないように見えたため)、
    `Transform.getShapes(intermediates)` → `getShape(intermediates=, all=True)`(`DagNode.getShape(all=True)` は、Shape なら自身1つ、ほかは空の集まり)。
  - 名前(Node −1、Nodes −1、Plugs −1): `getNodeName(removeNamespace)` → `getName(node=True, removeNamespace=)`、`Nodes`・`Plugs` の `getFullNames()` → `getNames(full=True)`。
    単数の `getFullName` → `getName(full=True)` は、最後の段で一括して行う。
  - 判定とアトリビュートの一覧(−2): `isParentOf(o)` → `isAncestorOf(o, direct=True)`(自身が無効なときは、`direct=True` でも RuntimeError になる)、`getAnimatablePlugs()` → `getPlugs(animatable=True)`。
  - DG の計測(−3): `setDgTimerEnabled(s)`・`resetDgTimer()` → `setDgTimer(state=None, *, reset=False)`、`getDgCallbacks()`・`getDgTimerState()` → `getDgTimer(callbacks=True)`・`getDgTimer(state=True)`。
    Maya 全体の設定の `setDgTimingEnabled`(staticmethod)は、ノードが要らない操作なので残した。
  - Joint(−2): `jointOrientToRotate()` → `freezeRotate(toRotate=True)`、`getIkHandles()` → `getConnections(type="ikHandle", asNode=True)`。
  - スキン(−11): `forceNormalizeWeights()` → `normalizeWeights(force=True)`、`getLockedInfluences()`・`getUnusedInfluences()` → `getInfluences(locked=True)`・`getInfluences(unused=True)`、
    `removeInfluence(j)`・`removeUnusedInfluences()` → `removeInfluences(joints=None, *, unused=False, transferToParent=True, requireAncestor=True, force=False)`(外したノードの Nodes を返す)、
    `isMaintainingMaxInfluences()` → `getMaxInfluences(maintain=True)`、`getSkinningMethod`・`setSkinningMethod`・`getNormalizeMode`・`setNormalizeMode` → `getMode(kind)`・`setMode(value, kind)`(`"skinning"`・`"normalize"`)、
    `getVertexWeights(v)`・`setVertexWeights(v, w)` → `getWeights(vertex=v)`・`setWeights(w, vertex=v, normalize=...)`。
    - 単数の `removeInfluence` は、ウェイトを受け取る祖先のインフルエンスが無いとき Maya 標準の配り直しに任せ、複数の `removeInfluences` は ValueError にしていた。
      まとめた後の既定(`requireAncestor=True`)は複数の動き(ValueError)で、単数の動きは `requireAncestor=False`。以前の `removeInfluence(j)` は `removeInfluences(j, requireAncestor=False)` と書く。
    - `setVertexWeights` は `normalize` の既定が True で `setWeights`(False)と逆だったので、`vertex=` の形では `normalize` を省けない(TypeError)。
  - デフォーマーの形状(−3): `getInputGeometry()` → `getGeometry(input=True)`、`getGeometryAtIndex(geometryIndex=i)`・`getInputGeometryAtIndex(geometryIndex=i)` → `getGeometry(geometryIndex=i)`・`getGeometry(input=True, geometryIndex=i)`、
    `getGeometryIndex(g)` → `getGeometryIndices(g)`(引数なしは全部の list)。
  - セット(−5、+1): `addExclusiveMembers(*m)` → `addMembers(*m, exclusive=True)`、`removeAllMembers()` → `removeMembers(all=True)`、`getMemberDagNodes(shadingOnly=)` → `getMembers(dagOnly=True, shadingOnly=)`、
    `getUnion`・`getIntersection`・`getDifference` → 新しい `combine(other, mode="union"|"intersection"|"difference")`。`ShadingEngine.getMembers` も `dagOnly`・`shadingOnly` を受ける。
  - コンストレイント(−4): `getWeight(t)` → `getWeights(t)[0]`(`getWeights(*targets)` は渡した順の list)、`getWeightAliases()` → `getWeightPlugs(aliases=True)`、
    `OrientConstraint`・`ParentConstraint` の `createCache`・`deleteCache` は、間に置いた非公開の基底 `_InterpCacheConstraint`(`nodes/interpCacheConstraint.py`)の1つの定義にした(使い方は同じ。ほかのコンストレイントには付かない)。
  - 名前が似ているもの(−4): `DagPose.getMemberIndex(m)` → `getMemberIndices(m)`、`DagPose.isAtPose()` → `not pose.getNotAtPose()`、`IkHandle.getEndJoint()` → `getJoints(end=True)`、`ShadingEngine.getShaderPlug(kind)` → `getShader(kind, plug=True)`。
  - まとめなかったもの: `getQuaternion`・`setQuaternion`(既定で返す回転も書き込む先も `getRotate`・`setRotate` と違う)、`getBlendWeights`・`setBlendWeights`(別の種類の値)、
    `SkinCluster.hasInfluence`(`getInfluenceIndex(...) is not None` は長く、番号 0 の取り違えも起きやすい)、`Joint.getSkinClusters`・`Joints.getSkinClusters`
    (`DagNode.getSkinClusters` を別の意味で上書きしているので、消すと「このジョイントの下の形状を変形しているスキン」が黙って返る)、`Node.getConnections` の `input=`・`outputs=`
    (Plug では「この Plug 自身の入力元1つ」だが、ノードには入力が多数あり同じ意味にならない)、`setDgTimingEnabled`(Maya 全体の設定)、
    メンバーを持つノードの共通の基底(`DagPose`・`DisplayLayer`・`ObjectSet` の `addMembers`・`removeMembers`・`getMembers` は、コマンドも入力の確認も戻り値の型も引数も違い、基底に置けるのは名前だけ)、
    `isLocked`・`setLocked`・`isFromReferencedFile` を `Object` へ上げる案(実装が別)。
  - 「名前を残す」とした照会・get/set(`Joint.getRadius`・`setRadius`・`getSegmentScaleCompensate`・`getJointOrient`・`getInverseScale`、`Transform.getRotateOrder`、`IkHandle.getEffector`、
    `Node.isFromReferencedFile`・`hasUniqueName`、`DagNode.isInstanced`・`isIntermediateObject` など)は、利用側の本体で使われているか、対になる片方が使われているので残した。
- 領域3(形状・デフォーマー・カメラなど。2026-11-24): `nodes/` の mesh・nurbsCurve・nurbsSurface・blendShape・camera・reference・animCurve・locator と `common/keyframe.py` で、公開メソッドをまとめた(公開の名前は63個減)。
  - 点を持つシェイプの共通の親(−5): `Mesh`・`NurbsCurve`・`NurbsSurface` の間に非公開の基底 `_ControlPointShape`(`nodes/controlPointShape.py`。Maya の `controlPoint` 型に当たる)を置き、
    `getPoints`・`setPoints`・`mirror` を1つずつにした。`NurbsCurve`・`NurbsSurface` の `getCvPositions()`・`setCvPositions(p)` → `getPoints()`・`setPoints(p)`(Mesh と同じ名前)。
    種類ごとの違い(読む関数・書き込みの手順・周期カーブの重なった CV・コレクションの型)は `_raw_points`・`_set_points`・`_point_components`、Undo チャンク名は今までの名前のまま
    (`mlibMeshSetPoints`・`mlibNurbsCurveSetCvPositions`・`mlibNurbsSurfaceSetCvPositions`・`mlibMeshMirror`・`mlibNurbsCurveMirror`)。親が持つので `NurbsSurface.mirror` が新しく使える
    (`surface.getCVs(indices).mirror(...)` と同じ。`mlibNurbsSurfaceMirror`)。`Transform.mirrorGeometry` は今までどおり mesh と nurbsCurve だけ。型の登録(`_WRAPPER_CLASSES`)と動的クラスの基底は変わらない(基底は登録しない)。
    proposal12 の S1(NURBS だけの親 `NurbsShape`)は置いていない: `getArea`・`getClosestPoint`・`getParamRange`・`setKnots`・`removeKnot`・`getAtParam` はカーブとサーフェスで引数・戻り値・本体が違い、親に置けるのは名前だけになる。
    同じ理由で `getClosestPoint`(Mesh・カーブ・サーフェス)と `getUVData`・`setUVData`(Mesh・サーフェス)も上げていない。
  - 単数と複数のコンポーネントの取得(−7): `mesh.getVertex(i)`・`getEdge(i)`・`getFace(i)`・`getUV(i)`、`curve.getCV(i)`、`animCurve.getKeyframe(i)` → 複数形に番号1つを渡す(`mesh.getVertices(i)` は Vertex。
    `MultiPlug.getElement` と同じ「番号を渡すと1つ、並び・省略はコレクション」)。`surface.getCV(u, v)` → `surface.getCVs([(u, v)])[0]`(`getCVs(n)` は通し番号の SurfaceCV。`getCVs((u, v))` は今までどおり通し番号2つ)。
    以前は複数形に番号1つを渡すと TypeError だったので、黙って結果が変わる呼び方は無い。型スタブは番号1つと並びのオーバーロード。
  - Mesh の頂点ごと・面頂点ごと(−6): `getFaceVertexNormals(...)` → `getVertexNormals(perFace=True, ...)`、`getFaceVertexNormalLocks(...)` → `getVertexNormals(perFace=True, locked=True, ...)`、
    `setFaceVertexNormalsLocked(state, ...)` → `setFaceVertexNormals(locked=state, ...)`(`normals` を渡すと今までどおり設定してロック。`VertexFace.getNormal`・`setNormal` と同じ形)、
    `getFaceVertexColors(...)` → `getVertexColors(perFace=True, ...)`、`setFaceVertexColors(c, ...)` → `setVertexColors(c, perFace=True, ...)`、`getFaceShadingEngines()` → `getShadingEngines(perFace=True)`。
    `vertices` は頂点ごと、`faceVertices` は面頂点ごとだけ(逆は TypeError)。`removeFaceVertexColors` は壊し方が違うので残した。set の `setNormals`(共有法線の一覧。fast 専用)と `setFaceVertexNormals` は書く対象が違うのでまとめていない。
  - Mesh のそのほか(−6): `getFaceVertexBinormals(...)` → `getFaceVertexTangents(binormal=True, ...)`、`getUVShells(uvSet=)` → `getShells(uv=True, uvSet=)`(UV 側は番号の list のまま)、
    `getBorderEdges()`・`getBorderVertices()` → `getBorder(type="edge"|"vertex")`、`getClosestNormal(p)`・`getUVAtPoint(p, uvSet=)` → `getClosestPoint(p, what="normal"|"uv")`(既定の `"point"` は今までどおり (点, フェース番号))、
    `getClosestVertex(p)` → `mesh.getVertices(mesh.getClosestVertices([p])[0])`、`getPointAtUV(u, v)` → `(mesh.getPointsAtUV(u, v) or [(None, None)])[0][1]`。
    `getClosestVertices` は番号の list のまま(別の点が同じ頂点に当たることがあり、重なりを除く Vertices では点ごとの対応が崩れる)。
  - UV セットとカラーセット(−7): `getUVSetNames`・`getCurrentUVSet`・`setCurrentUVSet`・`createUVSet`・`copyUVSet`・`renameUVSet`・`deleteUVSet` と `…ColorSet` の7つ →
    `getSetNames`・`getCurrentSet`・`setCurrentSet`・`createSet`・`copySet`・`renameSet`・`deleteSet` の `color=`(既定は UV セット。`copySet(color=True, replace=True)` は TypeError)。Undo チャンク名12個と例外の文言は今までどおり。
  - NurbsCurve(−5): `getLengthAtParam(p)` → `getLength(p)`(`tolerance` は全長だけ)、`getParamAtPoint(pt)`・`getParamAtLength(l)` → `getParam(point=pt)`・`getParam(length=l)`(全部キーワード専用。`worldSpace` もキーワードで渡す)、
    `getPointAtParam`・`getTangentAtParam`・`getNormalAtParam`・`getDerivativesAtParam` → `getAtParam(param, what="point"|"tangent"|"normal"|"derivatives")`。`removeKnot` と `reduceKnotMultiplicity` はまとめない。
  - NurbsSurface(−4): `getPointAtParam`・`getNormalAtParam`・`getTangentsAtParam`・`getMatrixAtParam`・`getDerivativesAtParam` → `getAtParam(u, v, what="point"|"normal"|"tangents"|"matrix"|"derivatives")`。
  - BlendShape(−6): `flipTarget(t, ...)` → `mirrorTarget(t, flip=True, ...)`、`addInBetween(t, geometry, w)` → `addTarget(geometry, inBetween=t, fullWeight=w)`(戻り値がウェイトの Plug になった)、
    `removeInBetween(t, w)` → `removeTarget(t, inBetween=w)`、`getBaseWeights(base)` → `getTargetWeights(base=base)`、`setBaseWeights(w, base)` → `setTargetWeights(None, w, base)`、
    `reduceTargetDeltas(t, tolerance=x)` → `resetTargetVertices(t, tolerance=x)`(`vertices` か `tolerance` のどちらか1つ)。
  - Camera(−6、+1): `getRenderingFrustum(a)`・`getViewingFrustum(a, ...)` → `getFrustum(a, kind="rendering"|"viewing")`(`getFilmFrustum` は入れない)、`setNearFocusDistance(d)`・`setFarFocusDistance(d)` → `setFocusDistance(near=d)`・`setFocusDistance(far=d)`
    (片方を書くと反対側も変わるので、同時には指定できない)、`getPostProjectionMatrix()` → `getProjectionMatrix(post=True)`、`getPortFieldOfView(w, h)` → `getFieldOfView(port=(w, h))`、
    `getEyePoint()`・`getCenterOfInterestPoint()` → `getPoint(kind="eye"|"centerOfInterest")`、`getViewDirection()`・`getUpDirection()` → `getDirection(kind="view"|"up")`。
    対の set も同じ形にした: `setCenterOfInterestPoint(p, fast=True)` → `setPoint(p, kind="centerOfInterest", fast=True)`、`setUpDirection(d)` → `setDirection(d, kind="up")`。
    `setPoint` の既定の `kind="eye"` は新しい機能(`MFnCamera.setEyePoint`。注視点を保って視点を動かすので、カメラの向きは変わる。fast 専用)。視線だけを変える操作は無いので `setDirection` の `kind` は省けず、`"view"` は NotImplementedError。
  - Reference(−4): `getEditStrings`・`getEditNodeNames`・`getEditAttrNames` → `getEdits(kind="string"|"node"|"attr")`、`load()`・`unload()` → `setLoaded(state=True)`(`isLoaded` と対)、`getRoot()` → `getParentReference(root=True)`
    (`root=True` はトップレベルで自身を返し、None にならない)。`getCopyNumber` と `getCopyNumbers` は別の情報なので両方残した。
  - AnimCurve・Keyframe(−5): `AnimCurve.mirror(input, value, ...)` → `scaleKey(-1 if input else 1, -1 if value else 1, ...)`、`insertKey(input)` → `setKey(input)`(`value` を省くと形を変えない挿入)、
    `Keyframe.getTime()` → `getValue(time=True)`、`Keyframes.getTimes()` → `getValues(time=True)`(入力の単位は `timeUnit`。`unit` と同時は TypeError)。`addKeys` と `replaceKeys` はまとめない。
    `AnimCurve` の番号を渡す形と `Keyframe`・`Keyframes` の同じ操作は両方残した。
  - 「名前を残す」とした照会・get/set の数え直し(−2): `Locator.getPosition`・`setPosition`(localPosition の1アトリビュート)は利用側・内部のどちらからも使われていなかったので削った(`getPlug("localPosition")`)。
    残したもの: `Mesh.getNumVertices`・`AnimCurve.getKeyCount`・`isTimeInput`・`getDrivenPlugs`・`getInfinity`・`Camera.isOrtho`・`Reference.getFilename`(利用側で使われている)、`Reference.isLoaded`(`setLoaded` と対で、内部でも使う)、
    `Mesh.getNumPolygons`・`getNumEdges`・`getNumUVs`・`getNumCVs`(コンポーネントが名前で呼ぶ)、`NurbsSurface.getForm`・`AnimCurve.isWeighted`・`Cluster.getWeightedNode`(内部・文書の例で使う)、
    `Camera.getAspectRatio`/`setAspectRatio`・`isVerticalLocked`/`setVerticalLocked`、`Reference.isReferenceLocked`/`setReferenceLocked`・`isUsingNamespaces`・`isDeferred`・`isTopLevel`、`BlendShape.getWeightCount`・`getNormalizationGroups`
    (Maya のコマンドでの照会・設定で、アトリビュート1つの読み書きと同じとは言い切れない)。
  - 内部: 種類の名前の検査は `util._require_choice`、番号1つとコレクションの振り分けは `components/component.py` の `_component_of`、UV セット・カラーセットの名前の検査は `Mesh._require_set`。
- 領域4(common・cmds・数学型。2026-11-24): `common/`・`cmds/`・`maths/` で、公開の名前を31個減らした(作成関数 −6、そのほか −25)。
  - 版(−5、+1): `Plugin`・`Module` の `getVersionText()` → `getVersion(text=True)`(Maya の文字列そのまま。数字で始まらない版を読む手段として残す。実装は派生クラスの非公開 `_version_text`)、
    `isVersionAtLeast(m)` → `v = p.getVersion(); v is not None and v.isAtLeast(m)`(`v >= "1.2"` は str との比較が TypeError のままで、広げるとハッシュと食い違うので使わない)、
    `PluginPackage.getInstalledVersion()`・`getLoadedVersion()` → `getVersion()`・`getVersion(loaded=True)`、`Plugin.ensureLoaded()` → `load(skipExisting=True)`(ロード済みなら型のキャッシュも消さない)。
  - マトリクス(−5、+1): `asTranslateMatrix`・`asRotateMatrix`・`asScaleMatrix`・`as3x3` → `Matrix.extract(part)`(`"translate"`・`"rotate"`・`"scale"`・`"3x3"`。位置引数で必須。
    `asMatrix(part=)` にしなかったのは、`Quaternion.asMatrix`・om2 の `MTransformationMatrix.asMatrix`/`asRotateMatrix` と同じ名前で意味が違うため)。`getAxes()` → `tuple(m.getAxis(i) for i in range(3))`
    (符号つきの軸の名前を受ける `getAxis` を残した)。
  - コンストラクターで書ける生成(−6): `Matrix.identity()` → `Matrix()`、`Matrix.fromMMatrix(m)` → `Matrix(m)`、`Matrix.fromTransformation(t)` → `Matrix(t.asMatrix())`、
    `Vector.fromIterable(v)` → `Vector(v)`(要素2つも受ける om2 の動き)、`EulerRotate.fromIterable(v, o)` → `EulerRotate(v, o)`、`EulerRotate.fromDegrees(x, y, z, o)` → `EulerRotate(x, y, z, o, unit="deg")`。
    mlib の内部の `fromMMatrix` は非公開の `Matrix._wrap` にした(速さを保つ)。`Matrix.compose` は利用側で多く使われ読みやすいので残した。
  - そのほかの数学型・環境(−2): `Vector.distanceSqTo(o)` → `distanceTo(o, squared=True)`、`Environment.isInteractive()` → `not Environment.isBatch()`。
  - 単位(−5): `distanceToUi(cm)` → `convertDistance(cm, "cm")`、`distanceFromUi(v)` → `convertDistance(v, toUnit="cm")`、`angleToUi(v, unit=u)` → `convertAngle(v, u, None)`、
    `angleFromUi(v, unit=u)` → `convertAngle(v, None, u)`、`secondsPerFrame()` → `convertTime(1.0, toUnit="sec")`(fps は `convertTime(1.0, "sec")`)。`convertAngle` の既定(度→ラジアン)は変えていない。
  - 時間(−5、+2): `Time.getPlaybackRange`・`getAnimationRange`・`getSelectedRange` → `getRange(*, animation=False, selected=False, timeUnit=)`(両方 True は TypeError。`selected=True` は None になることがある)、
    `setPlaybackRange`・`setAnimationRange` → `setRange(start, end, *, animation=False, timeUnit=)`。`setRange` と `Time.setCurrent` は、書き換えるメソッドの決まりどおり値を返さなくした(以前は設定後の値)。
  - コールバック(−1): `Callbacks.addSceneCheckCallback(e, f)` → `addSceneCallback(e, f)`(イベント名が重ならないのでフラグなし。`…Check` のイベントでは偽(None を含む)を返すと操作を止める。以前は ValueError だったので、黙って変わる呼び方は無い)。
  - 作成関数(−8、+2): `createDagContainer(...)` → `createContainer(..., dag=True)`(既定の名前と Undo チャンク名は今までどおり)、
    `createPolyCube`・`createPolySphere`・`createPolyCylinder`・`createPolyPlane` → `createPoly(kind, *, ...)`(`kind` 以外はキーワード専用。形ごとに使えない引数は TypeError。既定値・Undo チャンク名は形ごとに今までどおり)、
    `createCluster`・`createLattice`・`createWire` → `createDeformer(kind, targets, *, curves=, ...)`(`"cluster"`・`"lattice"`・`"wire"`。wire は `curves=` が必須で、省くと TypeError。
    名前が `cmds.deformer` と重なるが、扱うのは専用コマンドの3種類だけで、ほかの型名は ValueError。`kind` はノードの型名ではなく作るもの(lattice は ffd を返す)なので `type` にしなかった)。
    `createBlendShape`・`bindSkin` は引数と戻り値が大きく違うので入れていない。型スタブは `kind`・`dag`・`text`・`selected` のオーバーロード(`createPoly` は形ごとに使える引数だけを並べる)。
  - まとめなかったもの: `EulerRotate` の解の選び直し8つ(om2 の名前の上書き。消すと戻り値が om2 の型になるだけ)、`Quaternion` の `asCanonicalAxisAngle`・`asDecomposedEulerRotate`・`safeLog`・`asUnitMatrix`、
    `Vector`・`Quaternion` の `unit`(数学型の独自名はまとめないユーザーの決定)、`Version.minor`・`patch`・`build`(別の情報)、`json.file._current_fps`(非公開のまま)。
- 最後の段(名前の取得。2026-11-24): 書き換えが多くても(約3,100か所)まとめるユーザーの決定により、`getFullName` を `getName(full=True)` にした(公開の名前は3個減り、コンポーネントの単数に `getName` が1個増えた)。
  - `Node.getFullName()` → `Node.getName(full=True)`(`full=True` と `node`・`removeNamespace` の同時指定は TypeError。無効なノードで空文字列を返すのは今までどおりで、既定の `getName()` の RuntimeError とは違う)。
  - `Plug.getFullName()` → `Plug.getName(full=True)`(`str(plug)` と同じ。`full` は bool 以外を TypeError)。
  - `Component.getFullName()`(`CV` の上書きを含む) → `Component.getName(full=True)`。単数のコンポーネントに `getName(*, full=False)` を足し、既定は `Components.getNames()` の1要素と同じ最短の名前(シェイプの部分だけ `cmds.ls` で最短にする)。
  - mlib の中で cmds へ名前を渡す所(約480か所)・`__str__`・並べ替えの `methodcaller` は、引数の検査を省くため非公開の `_full_name()`(Node・Plug・Component)を直接呼ぶ。複数形の `getNames(full=True)` は領域1a・2で済んでいる。
  - 案内の表(`core/object.py`)の `longName`・`fullPath`・`fullPathName` は `getName(full=True)` を案内する。

## 引数の統一と上書きの整理(2026-11-26)

ユーザー指定(2026-11-26)により、引数の名前・働きと、基底のメソッドの上書きを揃えた。検討の資料と決めたことはローカルの
`docs/research/mlib-test-coverage/arg-study/`(`decisions.md`・`argConsistency.md`・`overridesAndSiblings.md`)、
**古い呼び方から新しい呼び方への対応表**は同じフォルダーの `renames/impl-dag.md`・`renames/impl-geometry.md`・`renames/impl-rest.md`
(1行1件。意味を保つために呼び方を変えるものは書き換えを添えてある)。この節より前の節に出てくる古い名前(`getName(node=True)`・
`getMatrix(parent=True)`・`IkHandle.getJoints(end=True)`・`getShader(plug=True)`・`Keyframe.getValue(time=True)`・`AnimCurve.setKey`・
`Joint.getSkinClusters`・Mesh のセット操作の `color=True` など)は、その時点の記録として残し、今の名前はこの節と対応表を正とする。

- **同じ名前の引数は同じ働き**: 引数名が同じなら、どのメソッドでも同じ働き・同じ種類の型・同じ受け方(位置かキーワード専用か)・同じ既定値と None の意味にする。
  同じ働きは mlib の中で1つの名前にする(Maya のフラグ名が割れていても1つ)。Maya のフラグをそのまま受ける入口(`cmds/` の作成関数・`addAttr`・
  `getConnections` の短縮名など)だけは Maya の名前。
  - `force` は「障害があっても実行」だけ。ロックを外すのは `unlock`(`Plug.connect`・`disconnect`・`delete`)、不正なウェイトを直すのは `repair`。
  - bool の引数に名詞を使わない: `getName(short=True)`・`getShader(asPlug=True)`・`Keyframe.getValue(input=True)`・`getMatrix(exclusive=True)`・
    `IkHandle.getJoints(tipOnly=True)`・Mesh のセット操作の `kind="color"`・`getColor`/`setColor(toShape=True)`・`getNormal(lockedOnly=True)`。
  - 末端は `leaves`、自身は `includeSelf`(`noSelf` は向きを変えて置き換え)、組は `asPair`(`connections`・`c` は置かない)、接続は `input`/`output` の対、
    並べる順は `sortBy`、距離の単位は `distanceUnit`、ミラーの面は `plane`。
  - `remove`・`clear` は list の意味だけ。自身を消すのは `delete`(`Namespace.delete`・`Keyframe(s).delete`)、親の変更は `setParent`(`Namespace.setParent`)。
  - mlib 独自のメソッドの短縮名(`getMatrix` の `p`・`inv`、`getQuaternion` の `ra`・`r`・`jo`)は消した。短縮名は Maya のフラグを受ける入口と `ws` だけ。
- **上書きで引数・意味を変えない**: 基底の引数をすべて同じ形で持ち、種類に特有の引数をキーワード専用・既定値つきで後ろに足すだけは許す
  (`AnimationSnapshot.apply`・`Mesh.getShadingEngines(perFace=)`)。`Joint.delete` の引数は `Node.delete` へ上げ(Joint 以外では型の確認だけ)、
  `Joint.getSkinClusters` は `DagNode.getSkinClusters(*, influence=False)` にまとめた(インフルエンス側は `influence=True`)。
  `AnimCurve` の `setKey`・`removeKey`・`moveKey` の上書きは消し、カーブへのキーの追加は `addKey`、番号・時刻で選んだキーの編集は
  `getKeyframes(indices | time=)` が返す `Keyframe`・`Keyframes` の `delete`・`move`・`setTangent`・`setBreakdown` にした。
  `Transformation` は om2 の `scale(space)` などを om2 のまま残し、値のプロパティを `scaleValue`・`shearValue`・`rotatePivotValue`・`scalePivotValue` にした。
- **許可表**: 意図して違うものは、mlib の `_tools/check_mlib_layout.py` の表に理由を書く。上書きは `OVERRIDE_ALLOWED`(L090)、親子でないクラスの
  同じ名前の公開メソッドは `SIBLING_ALLOWED`(L094。取る対象が違って意味の無い引数は置かず、差を理由として書く)、同じ名前の引数の型は
  `ARGUMENT_ALLOWED`(L095。情報)。もう違いの無い許可は L096 が報告する。これらはクラスの親をまたぐので、mlib 全体を対象にした
  `check_mlib_layout.py --check`(`format_mlib.bat` の流れ)だけで行う。初めに入れた許可は、上書き5(Snapshot の `capture`)・同じ名前のメソッド63(クラスごとの81件)・引数の型2。
  未実装: 上書きの戻り値・例外の比較(案の L091)、複数形の明示メソッドと単数の比較(L092)、om2 の名前の上書き(L093)。
- **名前を変えたとき**: 互換の別名は残さない。`core/object.py` の `_MEMBER_HINTS`(消した名前の案内。AnimCurve の `getTangent` などと SkinCluster の `mesh`)と、
  `_tools/generate_mlib_stubs.py` の `OVERLOADS`(`getVertexNormals(lockedOnly=)`・`getShader(asPlug=)`・`getJoints(tipOnly=)`・`getDgTimer(kind=)`・
  `getConnections(output=)`)も合わせる。

## 引数の表・検査・フォーマッター(2026-11-27)

2026-11-27のユーザー指定(引数の扱いのフォーマッターが欲しい、引数のテストと文書を厚くしたい、引数の差による問題が気になる)で入れた。
2026-11-26 に決めた「同じ名前の引数は同じ働き・型・受け方・既定値」のうち、受け方と既定値は誰も検査していなかった。
実測(公開def 約980個・引数名 約750種)では、同じ名前で位置とキーワード専用が混ざる名前が69種、既定値が違う名前が77種、
bool を位置で受ける引数が `worldSpace`・`state` のほかに約40個、既定値つきの引数の説明に既定値の記述が無いものが約4割あった。

- **引数の表**: `_tools/check_mlib_arguments.py` の `ARGUMENTS`。2か所以上で使う引数名ごとに、働き・受け方(`kind`)・既定値(`default`)・docstring の型(`type`)・
  説明の決まり文句(`text`)と、違ってよい def と理由(`kindAllowed`・`defaultAllowed`)を書く。種類ごとに既定が違うものは `default=VARIES` と理由。
  `check_mlib_layout.py` の L090・L094〜L096 が「同じ名前のメソッドどうし」を比べるのに対して、この表は「同じ名前の引数どうし」を比べる。
- **検査(A001〜A015)**: A001 キーワード専用の名前を既定値つきの位置引数で受けない、A002 既定値は表と同じ、A003 bool の位置引数は `worldSpace`・`state` だけ、
  A004 表に無い名前を食い違う形で使わない、A005 使わなくなった許可、A006 引数の一覧のページが古い、A010 docstring の型が既定値を含む、
  A011 説明に既定値を書く、A012 決まり文句、A013 型の書き方、A014 キーワード専用の引数の並び、A015 `Args:` の並び。
  `format_mlib.bat` の4番目の手順(5手順になった)で、`[OK]` の条件に入る。
- **フォーマッター**: `--check` を付けない `format_mlib.bat` が、動きを変えずに直せるものを書き込む: 型へ `| None` を足す、説明の末尾へ「既定は…。」を足す、
  決まり文句へ書き換える(`ws` は全体、`check` などは古い文の対応表にあるものだけ)、型の書き方を表の形にする、キーワード専用の引数を
  「その他 → fast → check → safe → 位置引数の短縮名」の順にする、`Args:` を署名の順にする。位置引数をキーワード専用へ変える・既定値を変える・名前を変えるのは、
  呼び出し側が壊れるので自動では直さない(報告だけ)。省略を番兵(`_UNSET`)で見分ける Maya のフラグの入口は、既定値を Maya に任せるので A011 の対象外。
  バックスラッシュを含む既定値(`end="\n"`)は docstring を raw にする必要があるので自動では足さない。
- **キーワード専用へ変えたもの(2026-11-27。互換の別名なし)**: `ShadingEngine.getShader(*, kind=)`・`setShader(shader, *, kind=, output=)`、`SkinCluster.getMode(*, kind=)`・`setMode(value, *, kind=)`、
  `Plug.getAttributeName(*, kind=)`、`Transform.addConstraint(target, *, type=, maintainOffset=)`、`DagNode`/`Transform.getShape(*, index=)`、
  `Vector.getClosestAxis(*, includeNegative=)`・`Transform.getClosestAxisToVector(refVector, *, includeNegative=)`、`Reference.getEdits`/`removeEdits(*, successful=, failed=)`、
  `createCurve(points, degree, *, closed=, knots=)`、`PluginPackage.tryLoad(*, dialog=, warn=)`、`listReferences(*, topLevelOnly=)`、`ScalarGraph.sum(role, left, right, *, subtract=)`、
  `DagNode.deleteHistory(*, keepDeformers=)`、`Joint.mirror(plane, *, behavior=, searchReplace=)`、`Node.getType(*, inherited=)`、`Node.rename(name, *, ignoreShape=)`、
  `Node.addAttr(longName, type, subType, *, channelBox=, …)`、`Reference.getFilename(*, resolved=, withCopyNumber=)`・`importContents(*, removeNamespace=)`、
  `SkinCluster.mirrorWeights(plane, *, positiveToNegative=)`・`unbind(*, keepHistory=)`、`BlendShape.mirrorTarget(target, axis, *, positiveToNegative=, base=)`、
  `Transform.matchTransform(target, *, position=, rotation=, scale=, pivots=)`、`MultiPlug.removeElement(index, *, shift=)`。
  位置のまま残したもの(表に理由): 数学型の `tolerance`(om2 と同じ)、`Node.addAttr` の `type`(名前と型を続けて書く)、`NodeRef(name, dagPath, type)`、
  `Components.pop(index)`(list と同じ)、`MultiPlug.getElement(index)`(主な値)、`BlendShape.resetTargetVertices(target, vertices)`、`bakeResults(nodes, attributes, time)`、`NameMapping(nameMap, replace, namespaceMap)`。
- **決まり文句**: `fast` は「TrueはUndoなしのOpenMaya更新。既定False。」、`check` は「Trueなら書き込む前に確かめ、問題があれば何も書かずに例外にする。既定はFalseで、
  確かめずに書く(Mayaが拒否したときだけ例外になる)。」のあとへ「確かめるのは、…。」を続ける、`safe` は「Trueなら、失敗しても例外にしない。既定はFalse。」、
  `skipExisting` は「Trueなら、すでに目的の状態のときは何もしない。既定はFalse。」、`skipConnected` は「Trueなら、接続があるノードは削除しない。既定はFalse。」、
  `ws` は「worldSpaceの短縮名。worldSpaceと同時には指定できない(TypeError)。」だけ。
- **既定値の食い違い**: 動きが変わるので、1件ずつ決めるまで変えていない。表の理由に「未決(2026-11-27)」と書いてある(`worldSpace` が True の5つ、
  `Plug.connect(unlock=True)`、`children`、`tolerance` の値、`preserve`、`Node.setDgTimer(state=None)` など16件)。案はローカルの
  `docs/research/mlib-test-coverage/arg-study/formatter/defaults-proposal.md`。`timeOffset` の 0.0 だけは動きが変わらないので 0 へ揃えた。
- **文書**: Sphinx の「引数の一覧」(`_docs/source/arguments.rst`)は表から自動で作る(早見表と、引数ごとの受け方・既定値・例外と理由・使うメソッドへのリンク)。
  入門(`getting_started.rst`)に「引数の渡し方」の節を足した。
- **テスト**: 引数の網羅(`support/argumentSweep.py`)に段4 `test_<メソッド>_calling` を足した。表の「正しい呼び方」を、渡し方だけ変えて呼ぶ:
  `defaults`=省いた引数へ既定値を明示しても同じ結果、`positional`=位置で渡しても名前で渡したときと同じ、`keywordOnly`=キーワード専用を位置で渡すと TypeError で
  シーンが変わらない。ツール自身は `noMaya/test_checkMlibArguments.py`。
- **試して入れなかったもの**: 呼び出し側(利用側のツール)が古い引数名・位置引数を渡していないかを、名前だけで調べる検査。ツール自身の同じ名前の関数と
  区別できず誤検出が多い(mlib で約2500件)。型スタブと pyright の役目とした。
