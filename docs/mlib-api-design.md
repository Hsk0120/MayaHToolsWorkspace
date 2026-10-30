# mlib APIの設計基準

今後のAPI追加・変更では、**Mayaへ問い合わせる操作はメソッド、保持する値はプロパティ**を基本とする。
実装・docstring・使用例を同じ基準に揃える。

## 呼び名の対応表

2026-10-28のユーザー指定(4.0.0)により、アトリビュートの構造はMayaのコマンドの呼び方へ揃える。
説明・docstring・コメントでは「マルチアトリビュート」「要素」「論理番号」「コンパウンドアトリビュート」「子」と書き、
「配列」「multi」「マルチ」「複合」等の略称は使わない。英語の例外メッセージは「multi attribute」「multi element」
「compound attribute」とする。Pythonのlist・`doubleArray`等の配列データ型・OpenMayaのAPI名はそのまま書く。

| mlib の名前 | Maya コマンド | OpenMaya |
| --- | --- | --- |
| マルチアトリビュート: `MultiPlug`・`Plug.isMulti()` | `addAttr -multi` | `MPlug.isArray` |
| マルチアトリビュートの要素: `Plug.isMultiElement()`・`Plug.getMulti()`(要素が属するマルチアトリビュート) | `attr[番号]` | `MPlug.isElement`・`MPlug.array()` |
| 要素の番号(論理番号): `Plug.getIndex()`・`MultiPlug.getIndices()` | `[番号]` | `MPlug.logicalIndex()` |
| コンパウンドアトリビュート: `CompoundPlug`・`Plug.isCompound()` | `addAttr -at compound` | `MPlug.isCompound` |
| コンパウンドアトリビュートの子: `Plug.isChild()`・`Plug.getParent()` | `-parent` | `MPlug.isChild`・`MPlug.parent()` |

## 提供する機能の範囲

2026-10-23の指定により、mlibはNode/Plug/Component/数学型と隣接基盤へ絞る。
汎用UI、OptionVar/Preferences、型付きJSON・Snapshot、専用Color、Scene/Workspace/FBX、
mlib版OBBは提供しない。旧import・互換別名・旧保存形式readerは残さない。
通常JSON文字列は標準`json`、標準UIは利用側のcmds/mel、表示色はPlugで扱う。
`mlib.cmds`とルート関数は`getNode/getPlug/createNode/ls/delete/duplicate/select`に限定する。
複数形・reload・拡張自動探索・数学所有権・単位・通常Undo/fastと、保持APIの引数/返却は維持する。
Mesh.reorderVerticesと小さな便利メソッドは残す。

追加縮小では、AddDL/AddDoubleLinear/MultDL/MultDoubleLinear/BlendColors/BlendWeighted/
Clamp/Condition/MultiplyDivide/PlusMinusAverage/RemapValue/Reverse/SetRange/UnitConversionの
型クラスと登録を残し、専用APIを終了する。操作はMaya標準名の`getPlug`とPlugのAPIを使う。
専用の検証・enum名・コンパウンドアトリビュートの編集・戻り型変換は提供しない。
判定は正式is名へ統一し、is省略入口と省略名へのSphinx投影は提供しない。
`undo.enabled`も廃止し`undo.isEnabled`を使用する。保持APIの仕様と拡張機構は維持する。

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
  createNode以上の処理をする特化ビルダーだけを残す: `Container.create(name="container", members=())`(作成+addMembers。
  位置引数の name と互換)、`Container.createNode(type, name=None)`、`DagPose.create(...)`、`SkinCluster.bind(...)`、
  `BlendShape.create(base, targets, name=None, frontOfChain=True)`、`IkHandle.create(startJoint, endJoint, solver="ikRPsolver", name=None, curve=None, **kwargs)`(5.0.0)、
  拡張の `Graph.create(name)`(mlib_bifrost)。単なるcreateNodeの言い換えは追加しない。
  `fast=True` はOpenMayaで直接作成しUndoを記録しない。入力検証・例外・戻り値の意味は通常経路と同じで、
  `shared=True` と `name` 指定で同名ノードが既にある場合は同じnodeTypeのときだけそれを返し、型が違えばRuntimeErrorとする。
  未知の型名はどちらの経路でもRuntimeErrorとし、unknownノードを残さない。`query/edit` フラグは `cmds.createNode` に無いので受け付けない。
- 2026-10-27のmlib 2.0.0で次版へ送ったsnake_case公開引数のlowerCamelCase化は、2.1.0で改名済み
  (`isType(nodeType)`・`getNodeName(removeNamespace)`・`SkinCluster.bind(maxInfluences)`・`removeInfluence(transferToParent)`・
  `getClosestAxisToVector(refVector, includeNegative)` 等)。旧引数名の互換は残さず、
  旧名のキーワード指定はTypeErrorになる。内部関数・内部メソッド・ローカル変数・`*args`/`**kwargs` はsnake_caseのまま、
  既存の登録プロトコル(`NodeRegistry`・`reload_package` 等、名前自体がsnake_caseの入口)は対象外とする。
  5.0.0でログの公開関数もlowerCamelCaseへ改名した(`logger.getLogger`・`logger.raiseWithNotify`。旧名の別名は残さない)。
  公開defの引数名は `__tests__/unit/test_static_public_args.py` が検査する。対応表は `maya/inhouse/mlib/_docs/source/changelog.rst` の2.1.0に置く。
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
  対応表と移行例は `maya/inhouse/mlib/_docs/source/changelog.rst` に置く。
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
  既存の接続方向フラグやOR/AND規則は維持する。
- メソッド名の表記と、処理の意味は別に確認する。同名のMaya APIと意味が異なる複合操作は説明を明記し、必要なら専用名に分ける。
- Mayaのコマンドフラグは標準表記を使う。今回の表記統一で既存の独自キーワード引数を一律変更しない。
- om2から継承・オーバーライドする名前、`__init__`等のPython特殊メソッド、`dump`/`loads`等の標準APIは維持する。
  ログの公開関数も5.0.0からlowerCamelCase(`getLogger`・`raiseWithNotify`)とし、例外にしない。
- JSONの保存キー・データクラスの保存フィールド・外部形式・パッケージ名・テスト探索名は、公開メソッドの改名に巻き込まない。
- 旧名の互換別名は残さない。内製使用側・テスト・ドキュメントを同時に更新し、`mlib.reload()`後も廃止名を公開しない。
- Maya照会はメソッド、保持値はプロパティ。シーン編集は明示的なメソッドにする。
- オブジェクト層はcm/秒・角度の数値は度(5.0.0)、数学層はOpenMayaの概念(角度rad)、コマンド層はmaya.cmdsの単位・フラグを基準にする。
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
例外メッセージはmlib内で英語に統一する(2026-10-27。混在していた日本語文言を英語化し、形式は下記「例外の4分類と文言形式」に従う)。
通常raiseをすべて通知付きへ置き換えたりしない。

### 内部実装の定型(2026-10-27の表記ブレ統一)

2026-10-27の表記ブレ調査で確定した内部実装の書き方。公開APIの意味・戻り値は変えず、内部名・引数・例外文言・docstringを揃える。
既存コードと矛盾する場合はこの節を正とし、旧名は `grep` で0件にする(互換別名は残さない)。

#### fastの定型

- 署名は `*, fast=False` をkeyword-onlyの先頭に置く(型注釈なしの既定値は `fast=False`)。既存の位置が違うものは公開署名の順序変更になるので一度に動かさず、changelogに載せる変更として扱う。
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

- `must be a non-empty string` 系は非strをTypeError、空文字をValueErrorに分ける。公開例外型の変更はchangelogの「破壊的変更」に載せる。
- 文言は英語でf-stringを使い(`"..." + name` の連結は不可)、対象名は末尾に `: <getFullName() または plug.name()>` で付ける。
  - 型違い: `<arg> must be <型>`(`_require_bool` は `fast must be a bool`)
  - 別名競合: `Specify only one of '<long>' and '<short>'`(長→短の順)
  - 必須欠落: `Missing required argument: '<long>'`
  - 値違い: `<arg> must be <条件>` または `Expected <条件>`
  - 状態: `<対象> is locked|connected|referenced: <名前>`、`Cannot <action> an invalid <type>`(`Node._require_valid(action)`)
  - fast非対応: `fast <publicMethodName> does not support <条件>`、`fast <publicMethodName> does not support flags: a, b`(説明語ではなく公開メソッド名を書く)
- テストが文言を `assertRaisesRegex` している箇所は同時に更新する。

#### 別名引数の書き方

- 短縮名の別名はMayaコマンドのフラグを受ける入口だけに置く(3.0.0)。対象は `cmds/` の `ls`・`createNode`・`duplicate`・`select`・`delete` のフラグ群と、Mayaコマンドへフラグを渡す `Node.addAttr`・`Transform.addConstraint`・`Transform.makeIdentity`・`Plug.setKey`、Mayaの `listConnections`/`connectAttr` のフラグを受ける `getConnections` の `s/d/c/t/et/scn`、`Plug.connect/disconnect` の `f/l/na`。これらはMayaと同じ長短の名前を受けるのが契約。
- それ以外のmlib独自メソッドは長名だけを持ち、長名に通常の既定値を置く(`worldSpace=False`、`index=0`)。短縮名の別名・`_UNSET` による省略判定を追加しない。
- 上記の入口では、署名は長名・短名ともkeyword-onlyの `_UNSET` を基本とし、選択は `_pick_alias(long, short, longName, shortName, default=_UNSET)`(`decorator.py`)で行う。インラインの `if ... is not _UNSET` 展開は書かない。競合は `_ArgumentError("Specify only one of '<long>' and '<short>'")`、`default` が `_UNSET` で両方未指定なら `_ArgumentError("Missing required argument: '<long>'")`。`_UNSET` は `util` が唯一の定義で、False/Noneの明示指定と省略を区別するためだけに使う。
- Mayaコマンドへ `**kwargs` で渡すフラグ群は `_merge_flags(kwargs, pairs)` で辞書へ詰めてよい。
- 空間指定のbool検査は `util._world_space()`(TypeError)に一本化し、二重検査を書かない。
- 内部関数へ渡すときも `fast`/`worldSpace` 等の同じ名前を使い、`world_space` のような別名を増やさない(core層のsnake_case関数の既存引数 `ws` は維持)。

#### 内部名の規則

- 検証は `_require_<条件>`(例外を送出し、戻り値は無しか検査済み値)。`_validate_*`・`_check_*` で例外を送出する関数は `_require_*` へ改名し、boolを返す判定は `_is_*`/`_has_*` にする。登録プロトコルとしてDESIGN/CLAUDE.mdに名のある `Nodes._validate_inputs`・`skinEdit.validate_removals`・`attributeEdit.validate_extra_attribute` は維持する。`_validated_*`(`_validated_flags` 等)は検査済みの値を返す検証の名前。
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

#### 共通ヘルパーの置き場

| 置き場 | 責務 | 主な内部ヘルパー |
| --- | --- | --- |
| `decorator.py` | fast/safe・フラグ正規化の内部補助、Undo文脈 | `_require_bool`・`_pick_alias`・`_merge_flags`・`_validated_flags`・`_edit_context`・`_undo_recording` |
| `util.py`(標準ライブラリのみ) | クラスに属さない値処理 | `_UNSET`・`_ArgumentError`・`_world_space`・`_finite`・`_finite_vector`・`_checked_tolerance`・`_checked_index`・`_unique_ordered`・`_rethrow_init_error` |
| `core/object.py` | 入力の存在・選択の判定 | `_exists`・`_selection_plug`・`_selection_component` |
| `core/fastWrite.py` | Plugへのom2書込み基盤 | `require_supported_type`・`require_writable`・`require_range`・`writable_compound`・`_ancestor_plugs`・`set_plug`・`set_attr`・`prepare_data` |
| `core/nodeEdit.py` | ノードの編集可否・削除検査 | `require_editable`・`check_deletion`・`_dag_descendants` |
| `core/geometryEdit.py`・`core/skinEdit.py`・`core/attributeEdit.py` | 形状・スキン・アトリビュートの編集基盤 | `set_positions`・`validate_removals`・`validate_extra_attribute` |
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
`python maya/inhouse/mlib/__tests__/checks/check_mlib_layout.py --check` が既存の並び順と空行を検査し、`--fix` がその整形を行う。
`--check` は下記の演算子・カンマ/括弧・引数指定・行末コメント・名前付きlambdaも検査する。
これら5項目は検査のみで、`--fix` による自動修正はしない。
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
  `__all__` と位置を揃えるための意図的な逸脱)。
- 行の長さは規則の対象外。
- 新しい検査コードは `L030`（代入・比較）、`L031`（カンマ・括弧）、`L032`（引数の `=`）、
  `L033`（行末コメント）、`L034`（名前付きlambda）。文字列内部は検査せず、f-stringは埋込み式も含めて対象外にする。

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
  `L042`は既知の`os.path.join/dirname/basename`を置換の確認候補として表示する。
  `normcase/realpath`等のOS固有の意味は維持し、MayaのDAGパス・アトリビュート名をファイルパスへ変換しない。
  `L043`は組込み`open`・`io.open`と、Path生成/型注釈で対象を判定できる
  `Path.open/read_text/write_text`の文字コード未指定・`encoding=None`を検出する。
  バイナリ・動的なmode・`*args`/`**kwargs`・不明なオブジェクトは断定しない。
  Pythonソースの宣言に従う`tokenize.open`も対象外。外部ファイルの文字コードをUTF-8と自動推測しない。

`L041`と`L042`は個別判断が必要な情報表示で、単独では検査を失敗にしない。
`L040`と`L043`は検査失敗となる。既存の`--fix`では上記を書き換えない。
入力assertの修正だけは`--fix-asserts TypeError`または`--fix-asserts ValueError`を使い、
対象ファイル1つと`--line`で確認した行を明示する。例外型の選択と変更の承認は呼出し側で行う。
複数行指定は全件を検証してから書き込み、コメントを含むassertや他の文と行を共有する場合、
選んだ例外名がソース内で再定義されている場合は拒否する。
この修正は例外型と最適化実行時の挙動を意図的に変更するため、既存の公開仕様と呼出し側も確認する。

## 公開名・型対応の宣言

- 公開名は所属パッケージの `__init__.py` へ明示する。`nodes`・`plugs`・`components`・`maths`・`cmds` とルート関数は通常のimportと `__all__` を使う。`common` は初期化順とreloadに合わせ、遅延公開の `_exports` と静的解析用の `if TYPE_CHECKING:` を維持する。
- Node/Plugの型対応は `nodes/__init__.py`・`plugs/__init__.py` の `_WRAPPER_CLASSES` 辞書に宣言する。公開するクラス名とは分けて管理する。手書きクラスの明示登録は維持し、動的クラス(下記「動的ノードクラス」)はその補完に限る。
- 外部拡張の検出は `extensions` が担当する。拡張側も `nodes`・`plugs` の明示import・`__all__`・`_WRAPPER_CLASSES` を用い、実行時のクラス注入や登録デコレーターは使わない。
- 追加・削除後はリポジトリルートで `python maya/inhouse/mlib/__tests__/checks/check_mlib_exports.py` を実行する。Mayaをimportせず、公開対象と明示宣言の不一致を検査する。実行時に漏れを黙って補う処理は追加しない。

### 動的ノードクラス

2026-10-26のユーザー指定により、`_WRAPPER_CLASSES` に無いMayaのnodeTypeは要求時にクラスを自動生成して返し(動的クラス)、
`Node` へのフォールバックはMayaが認識しない型名だけに残す。手書きクラスの明示登録は維持し、生成はその補完に限る。
移行例は `maya/inhouse/mlib/_docs/source/changelog.rst` を参照する。

- 生成の契機は2つ。`NodeRegistry.wrapper_class(node_type)` による型選択(`Node(node)`・`mlib.getNode`・`mlib.ls`・`mlib.createNode` の戻り値)と、`mlib.nodes.<TypeName>` の属性アクセス(`nodes/__init__.py` のモジュール `__getattr__`)。生成するのは `NodeRegistry(generate_classes=True)` の表(ルートが作るNode登録表)だけで、Plug登録表と汎用の `NodeRegistry` は従来どおり「完全一致 → 登録済み祖先(`resolve_inherited_types=True` の表) → フォールバック」で解決する。
- クラス名は型名の先頭を大文字にしたもの(`pointLight` → `PointLight`)。先頭が既に大文字の型(`AISEnvFacade`・`HIK*`)はそのまま。`mlib.nodes.<TypeName>` は先頭が大文字の名前だけを受け付け(`mlib.nodes.pointLight` はAttributeError)、Mayaが認識しない型名(未ロードのプラグイン型を含む)もAttributeErrorとし、AttributeError以外の例外を送出しない(`hasattr` と `mlib.reload()` から呼ばれる)。
- 生成クラスの基底は、Mayaの継承チェーン(`cmds.nodeType(inherited=True)`)を自身の直前から辿って最初に見つかる登録クラス。チェーンに登録が無ければ `Node`。登録クラスと生成対象の間にある抽象型(`geometryFilter`・`containerBase`・`entity`・`geometryShape` 等)のクラスは生成せず、生成クラス同士を親子にしない。例: `wrap` → `Wrap(Node)`、`symmetryConstraint` → `SymmetryConstraint(Constraint)`、`airField` → `AirField(DagNode)`、`unknownDag` → `UnknownDag(DagNode)`。抽象型そのもの(`mlib.nodes.GeometryFilter`)も同じ規則で生成するが、インスタンスを持たないので `isinstance` には使えない。
- 生成クラスは `__slots__ = ()` で `__init__` を定義せず、`_generated_node_type`(型名)と `_generated = True` を持つ。`mlib.nodes.AirField("airField1")` の明示構築もでき、型が合わなければ登録クラスと同じ `Node.__new__` のTypeError(「参照と入力の固定規則」)。
- isinstanceの約束: 生成クラスは「最寄りの登録クラスの派生である」ことだけを保証する。手書きクラスの `isinstance` 階層はPythonの継承で決まり、Mayaの抽象祖先を含まない(`SkinCluster(Node)` なので `isinstance(skin, mlib.nodes.GeometryFilter)` はFalse。`Container(Node)`・`Transform(DagNode)` も同様)。Mayaの継承に基づく型判定は `node.isType("geometryFilter")`、Maya型名の取得は `getType()`(`getType(inherited=True)` で基底→自身の順)を使う。手書きクラスの基底はMayaの親に揃える(`PoleVectorConstraint(PointConstraint)`)。`DagContainer(Transform, Container)` はMayaの全祖先を含んだ上位集合として据え置く(mixin化は次版)。
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
6.0.0で`Node.getConnections`・`Plug.getConnections`の`skipConversionNodes`(短縮名`scn`)の既定をTrueにし、
`getSource/getDestinations`と揃えた。`cmds.listConnections`とは既定が違い、unitConversion系を飛ばしてその先を返す。
`scn`と`skipConversionNodes`はANDで、どちらかをFalseにすると直結を返す。mlib内部で直結を前提にする呼び出しは`skipConversionNodes=False`を明示する。
`isSource/isDestination/disconnectInput/getSourceNodes`に方向boolは追加しない。
`connect(source)`と`connectTo(destination)`は接続相手を受け取る。

`getConnections`の`pcls`引数(戻り値のPlugクラス指定)は2026-10-26にNode/Plugの両方から削除した。
戻り値は常に実際のアトリビュート型に対応するPlugラッパーとする。
Plugの演算子は`src >> dst`(`src.connectTo(dst)`。解決した接続先dstを返す)、`dst << src`(`dst.connect(src)`。dst自身を返す)、
`src // dst`(`dst.disconnect(src)`。接続先dstを返す)の3つで、`connect`/`connectTo`/`disconnect`と同じ入力解決・例外・
通常Undoを持ち、fast経路は無い。マルチアトリビュート全体への`>>`はMayaと同じRuntimeErrorで、空き要素への接続は
`connectTo(multi, nextAvailable=True)`を使う。cymelの同名演算子はNoneを返すが、mlibでは戻り値を持つ。
`a >> b.x`は`a >> (b.x)`と評価される。`__len__`・`__add__`・無引数の作成・transform→shapeの暗黙のアトリビュート解決は追加しない。

### 再実行向けのsafe(5.0.0)

`safe=True` はAPIにより意味が違う。いずれも既定はFalseで、引数名は同じでも挙動と戻り値の契約が違う。

| 意味 | API | safe=Trueの挙動 | 戻り値 |
| --- | --- | --- | --- |
| 失敗の集計 | `Plug.set`(既存) | ロック・入力接続等の失敗を例外にせず数える。コンパウンドアトリビュートは子ごとに再試行する | 失敗数(成功は0) |
| 書ける成分だけ更新 | `Transform.setMatrix/setTranslation/setRotate/setScale/setShear/setQuaternion`(既存) | 書けないチャンネルを保持し、書けるチャンネルだけを更新する | 通常と同じ(自身) |
| 再実行の許容 | `Node.addAttr`・`Plug.connect`・`Plug.connectTo`・`Plug.setAlias`(5.0.0) | 既に同じ状態(同名のアトリビュート・同じ接続・同じ別名)なら何も変更しない | 成功時と同じ値(Plug・接続先・自身)。件数は返さない |

再実行の許容は「既に目的の状態」だけを成功とみなす。状態が違う(既存のアトリビュートの型やマルチアトリビュートかどうかが違う、
別の入力がある、ロックされている、別名を別のアトリビュートが使っている)場合はsafeでも既定と同じ例外にする
(`addAttr` の型違いはTypeError)。既存の状態は更新しない(`addAttr` の既定値・範囲・表示、`connect` のlockは変えない)。
`connect/connectTo(nextAvailable=True, safe=True)` は、接続元が既にいずれかの要素へ接続されていればその要素を返す。
同じ接続の判定はunitConversion等の変換ノードを経由した接続も含む(Mayaも同じ接続として拒否する)。演算子 `>>`・`<<` はsafeを持たない。
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
- オブジェクトの数値は距離cm・時間秒・角度は度(5.0.0で既定をradから度へ変更)。角度の数値を受け渡す公開API
  (`Plug.get/set`、`Transform.setRotate/getRotate/setQuaternion(get=True)`、`DrivenKey.setKey`、
  `Node.addAttr`の角度の既定値・範囲、角度出力のAnimCurve・接線の角度、`AimConstraint`のoffset/restRotate、
  `units.angleToUi/angleFromUi`)は`unit="deg"|"rad"`(別名`degree(s)`・`radian(s)`)を受け、既定は度とする。
  `uiUnits=True`は現在のUI単位で、`unit`とは同時に指定できない(ValueError)。
  `EulerRotate`・`Quaternion`は内部rad(om2互換)で値自身が単位を持つため、`unit`に関係なく換算しない。
  `rotate`の`get()`は従来どおり`EulerRotate`を返し、`unit`を明示した場合だけ数値tupleを返す
  (`tuple(rotate.get())`はradの数値になるので、度の数値列が必要なら`get(unit="deg")`を使う)。
  `Plug.getMin/getMax/getSoftMin/getSoftMax/getDefault`は既定で`MAngle`等の単位付きの値を返し、`unit`指定時に数値を返す。
  数学型の生成は既定rad(`EulerRotate(..., unit="deg")`・`Quaternion.fromAxisAngle(..., unit="deg")`で度)。
  内部処理はradで計算し、公開境界で一度だけ換算する(通常・fast・safeで同じ換算)。
  `getTranslation/setTranslation`等はマトリクス・姿勢の操作、`getPlug("translate").get/set`は
  アトリビュートの操作として区別する。前者をMFnTransform.translationの単なる別名にはしない。
- 空間指定は`worldSpace=True/False`(3.0.0で短縮名`ws`は廃止)。使用例は`worldSpace=True`とする。
  Trueはワールド、Falseはローカル。bool以外・旧`space=`は拒否する。
  既定値は各メソッドの仕様を維持する（`SkinCluster.restoreBindPose` はTrue、`Transform.getPivot/setPivot/mirrorTransform`・
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

名前の重なるメソッドの統合・改名で確定した契約。旧名の互換入口は残さず、対応表と移行例は
`maya/inhouse/mlib/_docs/source/changelog.rst` に置く。

- `Node.resetAttrs(attributes=None, *, fast=False)` はリセットしたPlugの `list[Plug]` を返す(3.0.0で別名 `attrs` は廃止)。
  `Transform.resetAttrs` は省略時の既定だけをoverrideし、translate/rotate/scale/shearを対象にする。
  旧 `Transform.reset`(戻りself)・`resetPivot`(`setPivot((0, 0, 0), worldSpace=True, kind=...)` で代替)・`freeze`(`makeIdentity(apply=True, ...)`)は廃止。
- `Transform.getRotate(worldSpace=False, *, order=None)` は二段の規則で等価解を選ぶ。`order` を省略、またはノードのrotateOrderと同じ順序なら、
  Transformは現在のrotateチャンネル、Jointはゼロ回転に最も近い等価解を返す(`setRotate` との往復でチャンネル値が保たれる)。
  それ以外の順序なら `quaternion.asEulerRotation().reorder(order)` の素の分解値(等価解の選択なし)を返し、`order=0`(xyz)は旧 `getEuler` と同値。
  `order` はom2の番号(int)または名前。ゼロスケール軸のValueErrorは両方で共通。
  旧 `getEuler`・`getJointOrientQuaternion`(`getQuaternion(worldSpace, r=False)` と同値)・
  `getOffsetParentMatrix/setOffsetParentMatrix`(`getPlug("offsetParentMatrix").get()/set(value, fast=)`)は廃止。
- `Transform.getShear(worldSpace=False)` / `setShear(value, worldSpace=False, safe=False, get=False, *, fast=False)`(旧 `getShearing/setShearing`)。
- `Transform.setParent(parent=None, relative=False, add=False, *, fast=False)`(3.0.0で短縮名 `r` は廃止)。
  JointのinverseScaleは `cmds.parent` と同じく `relative=False` のときだけ接続される(Mayaの仕様)。fastはJoint未対応で、変更前にNotImplementedErrorとする。
- `Joint.isJoint()` は廃止し、`isinstance(x, mlib.nodes.Joint)` または `x.isType("joint")` を使う。
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
- 範囲の編集: `Plug.setMin/setMax/setSoftMin/setSoftMax(value, *, unit=None)` は動的アトリビュートの定義を
  `cmds.addAttr(edit=True, minValue=...)` で編集し(Undo1回、fastなし)、`setMin/setMax(None)` で制限を外す(ソフト値の削除はMayaが編集できないため `setSoftMin/setSoftMax(None)` はNotImplementedError)。値の単位は `addAttr` の
  `minValue` と同じ(角度は度が既定で `unit="rad"` も可、距離cm、時間は秒)。静的アトリビュートと数値・単位型以外はTypeError。
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
| Maya上の座標など、評価済みの値を取得する | メソッド | `vertex.getPosition()`、`vertex.getPositionX()`、`mesh.getNumVertices()` |
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
- `fast` を持たない書き込みはom2に同等機能が無いものに限り、docstringに「fast引数は持たない」と理由を書く: `Transform.addConstraint`(コンストレイント作成APIなし)、`makeIdentity`(形状へのベイク)、`SkinCluster.bind/copyWeightsTo/addInfluences/restoreBindPose/mirrorWeights/pruneWeights`(バインド・コピー・ミラーAPIなし、刈り込みはMaya標準の規則に合わせたcmds編集)、`BlendShape.create/addTarget/removeTarget`・`IkHandle.create`・`Joint.orient/mirror`(cmds.blendShape・ikHandle・joint・mirrorJointの同等機能なし)、`DagPose.create/restore`(Mayaの階層補完・復元規則)、`Container/DagContainer` の作成・所属・publish系(MFnContainerNodeは照会専用)、`Reference.load/unload/remove`・`createReference`(ファイル操作)、`DrivenKey.setKey`、`Plugin.load/unload`(環境操作)、`moveAttrOrder`。`setEnumNames` は引数を持つが `fast=True` をNotImplementedErrorで拒否する。
- 3.0.0 で次の書き込みから `fast` を外した。利用がほぼ無く、cmds と同じ結果を保つ補正が保守の負担になるため 3.0.0 で外した: `mlib.duplicate`(`MFnDagNode.duplicate` の名前・ロック・セット所属・inverseScale の補正)、`mlib.select`・`Selection.select`(`MGlobal.setActiveSelectionList` でのコンポーネントのまとめ方の再現)、`Namespace.create/setCurrent/rename/move/remove`(`om2.MNamespace` の作成名の特定・ASCII以外の拒否)、`Plug.setMuted/mute/unmute`(`MDGModifier` での mute ノードの命名・接続の再現)、`Transform.matchTransform`(position・pivots だけの再現)、`SkinCluster.removeInfluence/removeUnusedInfluences`・`Joint.removeInfluence`(`cmds.skinCluster -removeInfluence` の再配分・距離配分の再現)。いずれも通常経路(cmds、Undo 1 回)だけを持つ。
- cmds→om2の読み取り置換は `__tests__/integration/test_cmds_parity.py` にcmdsの生値との突き合わせを同時に追加し、一致しないものはcmdsに戻す。om2に対応APIが無い読み取り(`Plug.getNiceName` の `attributeName -nice`、`cmds.nodeType` による型継承照会、`ls -undeletable`、`referenceQuery` のedit系、`keyTangent -g`、`mlib.ls` の検索・並び順、module/plugin/scriptJob/undoの環境系)はcmdsのままとする。
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
5.0.0から `node.tx = 10` は `node.getPlug("tx").set(10)` と同じ書込みになる(PyMELと同じ。Undoに記録し、角度は度)。
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

## cmdsの範囲

`getNode/getPlug/createNode/ls/delete/duplicate/select`の7入口だけを公開する。
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
- 単数形と複数形の座標取得はともに `getPosition`。コンポーネントは座標の照会だけを提供し、書込みは `cmds.xform` 等を使う。
- 戻り値の型・単位・更新対象・破壊性が違う操作は、名前が似ていても安易にフラグ統合しない。

- Plug系の空間指定は廃止し、アトリビュート値とTransformの姿勢を区別する。Double3Plugのrotateは回転順序・単位変換だけを行い、jointOrientや他のチャンネルを合成しない。
- アトリビュートフラグはキーワード専用の `setFlags(locked=None, keyable=None, channelBox=None, fast=False)` へ集約する。Noneは変更なし、bool以外は更新前に拒否する。
- 一括更新では、対象名・所属・入力値など検証できる項目を更新前に全件検証する。Undoチャンクは失敗時の自動ロールバックを意味しない。

### 複数形ノードの基底クラス

- ノードコレクションは `Nodes` を基底にし、`Joints`・`SkinClusters` は `Nodes` の派生とする。`Nodes` 自体は `Node` を継承しない。3.0.0で `DagNodes`・`Transforms`、単数メソッドへの一括転送(`_bulk_entries`・`callEach`)は利用が無いため廃止した。各要素の操作は単数のメソッドを `for` で呼ぶ。
- 複数形が持つのは、listとしての振る舞い(`__iter__`・`__len__`・`__getitem__`・`copy`)と入力検証(`_resolve_inputs`・`_validate_inputs`)に加え、`Joints.sortedByDepth()`・`Joints.getSkinClusters()`(重複を除いた `SkinClusters`)だけとする。`mlib.ls(type="joint")` は `Joints`、`type="skinCluster"` は `SkinClusters` を返す。
- `item_class` で受け入れるラッパー型を宣言する。入力は各基底クラスの共通処理で解決し、型の不一致を黙って除外せず例外にする。登録済みの外部拡張の派生ラッパーを基底型へ置き換えない。
- 重複は同一ノードかつ同一DAGパスで判定する。異なるインスタンスパスをUUIDだけでまとめない。構築後の参照の削除によってコレクション長を暗黙に変えない。
- 整数アクセスは保持中の参照、スライス/copyは同じ具象コレクションで同じシーン対象を参照する。ノード複製とは別。
- `Joint.delete`・`mlib.delete(joints)` はMaya標準削除とし、ウェイト移送と子保持を行わない。これらを伴う階層整理は`mlrig.setups.JointHierarchy.delete(joints, *, safe=False, fast=False)`へ分ける。一般にUndo対応は失敗時の自動ロールバックを意味しない。`ls`の返却規則は維持する。


### 参照対象と取得契約

- 独自のアトリビュート操作名は `Attr/Attrs`。ユーザー定義アトリビュートの列挙は `getPlugs(userDefined=True)` で、専用の `Extra` 名は置かない。フラグ設定は `setFlags` を使う。
- メソッドのオーバーライドで対象を切り替えない。`Reference.getAssociatedNamespace` は参照内容、継承した `getNamespace/setNamespace` はreferenceノード自身を扱う。
- 内部の接続用参照は `*_plug`、文字列のみの一覧は `*_names` / `*_aliases` などで対象を明示する。公開名はlowerCamelCaseとする。
- マルチアトリビュートの `getElement` は既存要素のみ。`multi[index]` は未作成の非実体化参照も返し、作成はset/connectで行う。
- `PluginPackage.tryLoad` は状態文字列を返し、`Plugin.ensureLoaded` は失敗時に例外を送出する。成功保証の違いを隠さない。
- `getVisibility/setVisibility` は自身のvisibilityアトリビュートだけを扱い、階層や表示レイヤーを含む最終可視性と区別する。

## 参照と入力の固定規則

- Nodeの等価比較(`==`)は生存中のMaya対象、DAGではインスタンスパスも含む。JointだけのUUID比較は廃止。`sameNode` はパスに関係なく同じMayaノードかを比較する。旧 `sameInstance` は `==` と同じなので廃止した。
- Nodeのhashは生成時のMObjectHandle.hashCodeを保持。Plugは所有ノードのhashと生成時のアトリビュートパスを保持する。改名・削除でhashを変えず、永続IDとして保存しない。完全破棄後は他参照と等価にしない。可変数学型はhash不可を維持。
- getNode/Nodeは動的に型解決するが、具体クラスの構築はその型または派生に適合しなければTypeError。Nodeと同一のノードを別の具体型へ無理にラップしない。動的クラスが選ばれる型でも同じ(`mlib.nodes.Joint("pointLight1")` はTypeError、`mlib.nodes.PointLight("pointLight1")` は可)。
- 保持DAGパスの消失を別インスタンスへの自動切替で補わない。ノードの有効性とパスの有効性を区別する。
- ノード対象列では文字列とNodeの混在を変更前にTypeErrorにする。名前列/Node列は両方許可し、派生型はNode形式として扱う。空入力や操作対象型の制限は各操作の仕様を維持する。
- reload後の旧インスタンスは取得し直す。動的に生成したクラスの参照も同じで、reload・登録表の変更・`Plugin.load/unload` の後は `mlib.nodes.<TypeName>` を取り直す。新旧クラスの相互比較/自動移行を保証しない。
- lsの専用コレクション返却、copy/sliceの参照共有、bulk失敗時の停止・自動ロールバックなしを維持する。
- Maya依存の有無は責務分離の基準にしない。対象に固有の取得・計算・更新は同じクラスに置く。

## 利用側が担当する操作

- 標準UIの作成・参照・エディター起動は利用側のcmds/mel、Qt変換は利用側のUIパッケージへ置く。
- シーン/プロジェクト/FBX操作とユーザー設定は利用側でMaya標準APIを明示使用する。
- 通常JSON文字列は標準jsonで扱う。型codec・汎用Snapshot・参照保存の本体機能は持たない。
- 表示色はMaya標準アトリビュートのPlugで扱い、色値型や専用一括操作を追加しない。
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
