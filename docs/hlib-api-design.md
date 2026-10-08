# hlib APIの設計基準

今後のAPI追加・変更では、**Mayaへ問い合わせる操作はメソッド、保持する値はプロパティ**を基本とする。
実装・docstring・使用例を同じ基準に揃える。

## 確定したコーディングルール

- 作成・更新APIは既定で作成したオブジェクトや操作対象を返す。他ライブラリとの引数統一だけを理由に既定戻り値をNoneへ変更しない。`Node.addAttr()` は既定でPlugを返す。

公開APIの表記は**camelCaseに統一**する。common・JSON・logger・decoratorも同じ規則とする。

| 対象 | 規則 | 例 |
| --- | --- | --- |
| クラス | PascalCase | `SkinCluster`、`EulerRotation` |
| 公開関数・メソッド | lowerCamelCase | `getMatrix()`、`getSettings()`、`undoChunk()` |
| プロパティ | lowerCamelCase | `orderName`、`minimumVersion`、`paletteSource` |
| Mayaコマンド・アトリビュート・nodeType | Maya標準の原名 | `createNode`、`offsetParentMatrix`、`skinCluster` |
| 一般Pythonファイル | lowerCamelCase | `channelBox.py`、`eulerRotation.py` |
| 内部関数・引数・ローカル変数 | snake_case可 | `_resolve_input`、`namespace_map` |
| 定数 | UPPER_SNAKE_CASE | `LOAD_FAILED` |

- `get`/`set`は値の取得・設定、`is`/`has`は判定、`create`/`add`/`remove`は作成・追加・除外に使う。
  独自の取得メソッドは `getName()`、`getSource()`、`getChildren()` のようにgetを付ける。
  数学演算・判定・保持値のプロパティ・OpenMaya標準名は一律get化しない。
- 2026-10-08のユーザー指定により、独自の `getX` に `x()` の省略入口を一律追加する。
  本体と内部利用の基準はget付きに残し、通常defから呼出時のget付きメソッドへ委譲する。
  引数・別名・戻り値・単位・例外・Undoは正式getterと同じ。実行時にメソッドを生成しない。
  省略名は同名のMayaアトリビュートや継承propertyより優先する。Plug取得は
  `getPlug("radius")` 等、複合Plugの同名子は `["node"]` 等で明示する。
  静的getterの省略入口はclassmethodとしてクラス/インスタンス両方から利用できる。
  公開コマンドも同名ファイルの省略入口を併用し、動詞+対象の正式名は維持する。
- メソッド内のアトリビュート表記は `Attr/Attrs`、追加分は `Extra` に統一する。
  `getT/setT`・`getQ/setQ`・`getX/setX`等の短縮アクセサーは設けず、正式な長名を使う。
- 型変換は `as` 接頭辞。コピーを返す数学操作は `inverse/normal/mirror`、自身の更新は
  `invertIt/mirrorIt` の形式とする。OpenMaya標準の `Vector.normalize()` は例外として維持する。
- 数学値の戻り型は継承メソッドも対応するhlib型へ統一する。数値・真偽値・生API取得入口、
  対応型のないMPoint/単位値/クラス定数は維持する。ゼロ値などの演算条件は変更しない。
- 引数の追加別名は `idx/index`・`src/source`・`dst/destination`・`attr/attribute`・
  `attrs/attributes`・`f/force`。対応APIの使用例はショート優先。既存シグネチャと位置引数は維持し、
  新規別名の二重指定は同値でも拒否する。既存の接続方向フラグやOR/AND規則は維持する。
- メソッド名の表記と、処理の意味は別に確認する。同名のMaya APIと意味が異なる複合操作は説明を明記し、必要なら専用名に分ける。
- Mayaのコマンドフラグは標準表記を使う。今回の表記統一で既存の独自キーワード引数を一律変更しない。
- om2から継承・オーバーライドする名前、`__init__`等のPython特殊メソッド、`dump`/`loads`等の標準APIは維持する。
  ログの`get_logger`・`raise_with_notify`は既存の通知契約として例外にする。
- JSONの保存キー・データクラスの保存フィールド・外部形式・パッケージ名・テスト探索名は、公開メソッドの改名に巻き込まない。
- 旧名の互換別名は残さない。内製使用側・テスト・ドキュメントを同時に更新し、`hlib.reload()`後も廃止名を公開しない。
- Maya照会はメソッド、保持値はプロパティ。シーン編集は明示的なメソッドにする。
- オブジェクト・数学層はcm/rad/秒とOpenMayaの概念、コマンド層はmaya.cmdsの単位・フラグを基準にする。
- 通常更新はcmdsによるUndo対応、対応する`fast=True`はom2によるUndoなし更新。同じ入力の意味・検証を維持する。
- 日本語Google形式docstringで引数・戻り値・副作用を説明する。Mayaのattributeは「アトリビュート」と表記する。
- hlibにQt依存・独自Mayaプラグインを追加せず、ノード・Plug・Componentの共通処理は各基底へ集約する。

### ファイル・クラスのレイアウト規則

hlib・`hlib_*` のPythonファイルはPEP8の並びを基準にする。並びは挙動に影響しないため、
名前・本文・デコレータの積み順・docstringを変えずに整える。
`python tools/check_hlib_layout.py --check` が規則を検査し、`--fix` が並び替えと空行の正規化を行い、
`--snapshot`/`--compare` で整理前後の関数本体・import束縛・モジュール文が同一であることを確認できる(Maya不要。
実行方法は `docs/hlib-testing.md`)。

| 位置 | 規則 |
| --- | --- |
| モジュール先頭 | docstring → `from __future__` → import → `if TYPE_CHECKING:` → `__all__`・定数 → 関数・クラス |
| import群 | 標準ライブラリ → `maya.*` などのサードパーティ → 相対import の3グループ。グループ間は空行1行。グループ内は isort の既定と同じく `import x` 形式を先にまとめ、続けて `from x import y` 形式を置き、それぞれをモジュール名順(大文字小文字を区別しない。`..` は `.` より先)にする。例: `import inspect` → `import re` → `from functools import wraps`。 |
| import形式 | `import maya.cmds as cmds`、`import maya.mel as mel`、`import maya.api.OpenMaya as om2`。`from maya.api.OpenMaya import MSpace` のような個別名のimportは可。 |
| 定数 | import群の直後に置き、関数・クラスの後へ置かない。説明は `#:` の行末コメント。 |
| 空行 | トップレベルの定義間は2行、クラス内のメンバー間は1行、`class` 行とdocstringの間は0行、デコレータと `def` の間は0行、3行以上の空行は使わない。ファイル末尾は改行1つ。クラス内に区切り線のコメント(`# ----- 比較` など)は置かず、下記の並び順で区分する。 |
| クラス内の順 | docstring → クラス属性 → `__new__`/`__init__`/`__post_init__` → その他の特殊メソッド → 公開 classmethod/staticmethod → property → 公開メソッド → 非公開メソッド(`_` 始まり。static/classmethodも含む) |
| 対になる操作 | `getX`/`setX`、`isX`/`setX`、`x()`/`setX()`、`connect`/`disconnect*`、`lock`/`unlock`、`show`/`hide`、`addX`/`removeX`、`__eq__`/`__ne__`/`__hash__`、`__repr__`/`__str__`、`__getitem__`/`__setitem__`、`__copy__`/`__deepcopy__`、各演算子と `__r*__`/`__i*__` は隣接させる。property の setter は getter の直後。 |

- 公開メソッドの全体をアルファベット順には並べ替えない。対の隣接と上記グループ分けだけを行う。
- 関数・メソッド内の遅延import(循環回避、Maya非依存の維持)、`try/except ImportError`、
  `if TYPE_CHECKING:` の中身は移動しない。
- import文の間に実行文があり、その初期化順そのものが仕様の `__init__.py`(現在は `hlib/__init__.py` のみ)は
  並び替えの対象外。空行だけを整える(`--check` は「スキップ」として表示する)。
- それ以外の `__init__.py` も通常の規則で並べる。import群の途中にあった `globals().pop(...)`・
  `__all__ +=` のような、importの結果に依存しない文はimport群の後へまとめる
  (`common`・`json`・`maths`)。`nodes`・`plugs`・`cmds` の登録処理はimport群の後にあり、import群だけが並び替えの対象になる。
- `@dataclass` のフィールド順、`__str__ = __repr__` のような先行定義を参照する代入、
  `item_class = Node` のようなクラス属性は、参照先が先に定義される位置を維持する。
- `__all__` はPEP8の「import前」ではなく、import群の直後に置く(`__init__.py` の動的な
  `__all__` と位置を揃えるための意図的な逸脱)。
- 行の長さは規則の対象外。

## 公開名・型対応・複数形APIの宣言

- 公開名は所属パッケージの `__init__.py` へ明示する。`nodes`・`plugs`・`components`・`maths`・`json`・`cmds` とルート関数は通常のimportと `__all__` を使う。`common` は初期化順とreloadに合わせ、遅延公開の `_exports` と静的解析用の `if TYPE_CHECKING:` を維持する。
- Node/Plugの型対応は `nodes/__init__.py`・`plugs/__init__.py` の `_WRAPPER_CLASSES` 辞書に宣言する。公開するクラス名とは分けて管理し、登録済みのMaya型に基づく最適なラッパー選択と既存のフォールバックは維持する。
- 外部拡張の検出は `extensions` が担当する。拡張側も `nodes`・`plugs` の明示import・`__all__`・`_WRAPPER_CLASSES` を用い、実行時のクラス注入や登録デコレーターは使わない。
- 複数形APIの入口は通常の `def` で明示する。共通の引数検証・保持順実行・Undo処理へ委譲し、実行時に単数メソッドから公開メソッドを生成しない。既存の引数仕様・戻り値・専用集約処理を維持する。
- 追加・削除後はリポジトリルートで `python tools/check_hlib_exports.py` を実行する。Mayaをimportせず、公開対象と明示宣言の不一致を検査する。実行時に漏れを黙って補う処理は追加しない。

## コマンド層とオブジェクト・数学層

`getAttr(target)` はユーザーの指定により `getPlug` へ委譲し、アトリビュート型に対応する
Plugを返す。値は `.get()` で内部単位、`.getu()` でUI単位として取得する。
既存の `getAttr(target, **kwargs)` の照会フラグは維持する。フラグを一つでも明示した
呼出しは従来どおりMayaの値・状態を返し、time指定・Falseのフラグもこの照会に含める。
型判定・入力解決の本体は `getPlug` 側に集約し、公開入口の名前や位置引数は維持する。

### Plug.disconnectの方向指定（2026-10-08）

ユーザーの指示により、`Plug.disconnect` は既存の入力元Plug指定に加え、
`src/source` のboolで入力、キーワード専用の `dst/destination` のboolで出力を指定する。
既存の `src=None, force=False, f=False, nextAvailable=False, na=False` は維持し、
`dst=False` を追加する。既定の入力切断・未接続エラー・入力元Plug返却・
入力元指定時のna配列検索と接続先リスト返却は変更しない。
`src` がboolまたは `dst=True` なら、切断した入力元と出力接続先をリストで返す。
入力元Plugを指定したna配列検索との併用時は、従来の入力接続先リストに出力接続先を追加する。
bool方向指定は未接続でも空リストを返す。入力元Plugの明示指定は未接続エラーを維持する。
両Falseは何もせず、`dst=True` 単独は両方向。
子・配列要素の独立接続は展開せず、変換ノードを削除しない。
出力のforceは各接続先のロックを一時解除して復元し、複数切断も1回のUndoで戻す。

### 単位・フラグ・戻り値

`SkinCluster.removeInfluence`・`Joint.removeInfluence`・`SkinClusters.removeInfluences` と
`SkinCluster.removeUnusedInfluences` は、キーワード専用の `force=False` と短縮名 `f` を受け付ける。
`force=True` は不正ウェイトを除去してから既存の移送・登録解除を実行する指定で、
ロック解除・レイヤー保護の回避・最後のinfluenceの解除を許可する指定ではない。
新規の `force/f` は同時指定を拒否し、既存の位置引数・戻り値を維持する。
`removeInvalidWeights(*, fast=False)` は、負値・非有限値・未登録influence論理番号の
既存ウェイト要素だけを除去し、単数/複数とも自身を返す。
正規化・合計0の補填・1超の有限値の切捨ては行わない。
通常はcmdsでUndo対応、fastはOpenMayaのMDGModifierによるUndoなし更新とする。
未使用influenceの判定は引き続きMayaのweightedInfluenceを使い、微小値を切り捨てない。
不正ウェイト除去とinfluence登録解除は別の操作とし、jointノード自体は削除しない。

- `hlib.cmds` はMayaコマンドの名前・長短フラグ・単位解釈を基準にする。
  Node/Plug参照や数学型への戻り値のラップは各コマンドに明記する。
- 全パッケージの公開関数・メソッド・プロパティは上記の例外を除きlowerCamelCase。
  シーン照会にはgetを付ける（`getNumVertices`・`getNumCVs`・`getCvPositions`等）。
  hlib独自の複合操作は独自名と仕様を明記し、MFnと同一の処理だと扱わない。
- オブジェクトの数値は距離cm・角度rad・時間秒。`Plug.get/set`と数学型で同じ値を渡せる。
  `getTranslation/setTranslation`等は行列・姿勢の操作、`getPlug("translate").get/set`は
  アトリビュートの操作として区別する。前者をMFnTransform.translationの単なる別名にはしない。
- 空間指定は`worldSpace=True/False`、短縮名は`ws`。使用例は原則`ws=True`とする。
  Trueはワールド、Falseはローカル。bool以外・長短名の同時指定・旧`space=`は拒否する。
  既定値は各メソッドの仕様を維持する（resetPivot/restoreBindPose等はTrue）。
  OpenMaya標準APIのMSpace引数は変更しない。
- 数学型はOpenMaya API 2.0の継承を維持する。独自の正規化・分解補助は`asUnitMatrix`・
  `asCanonicalAxisAngle`・`asDecomposedEulerRotation`で、標準の`asMatrix`等と区別する。
  ゼロ値を拒否する正規化は`unit/unitIt`、標準のコピー正規化は`normal`。行列式は`det4x4`。
- 型付きデータ配列の対応getterは常にlist。空は`[]`、未初期化は`None`。
  点・ベクトルはtupleのlistとし、1要素でも外側のlistを省かない。
- CVはOpenMayaの番号を保持する。周期末尾の重複CVは通常編集・cmdsへ渡す名前で
  先頭の対応CVへ写す。fastの周期CV編集は未対応として拒否する。
- 通常更新では必要な単位変換をcmds境界で行い、Undoを確保する。`fast=True`では
  同じ内部単位の値をom2へ直接渡す。fastで入力単位・番号・戻り値の意味を変えない。
- UI操作の時刻・表示単位や、JSONスナップショットの保存単位はそれぞれの仕様を明記する。
  スナップショットは単位情報付きの保存形式を保ち、オブジェクト値との境界で変換する。
- 旧Python名の互換入口は作らず、内製使用側・テスト・ドキュメントを更新する。

`cmds.addAttr`の角度・距離のdefaultValue/minValue/maxValueは内部単位を使うなど、
Mayaコマンドにも単位解釈の例外がある。全コマンドへUI単位変換を機械的に適用しない。

## メソッドとプロパティ

| 対象 | 公開形式 | 例 |
| --- | --- | --- |
| Mayaの現在の状態・名前・アトリビュート情報を問い合わせる | メソッド | `node.getFullName()`、`node.isLocked()`、`plug.getName()` |
| Maya上の座標など、評価済みの値を取得する | メソッド | `vertex.getPosition()`、`vertex.getPositionX()`、`mesh.getNumVertices()` |
| Mayaの状態を変更する | 明示的なメソッド | `plug.set(value)`、`vertex.setPositionX(value)`、`node.rename(name)` |
| オブジェクトが保持している参照・番号を返す | プロパティ | `component.shape`、`component.index`、`components.indices` |
| 数学値(`hlib.maths`)・保存済みデータを参照する | プロパティまたはデータフィールド | `vector.x`、`matrix.translate`、`node_ref.uuid` |

```python
import hlib

node = hlib.createNode("transform")
plug = node.getPlug("translateX")

print(node.getFullName())    # 現在のMayaノード名を取得
print(plug.isLocked())   # 現在のロック状態を照会
print(plug.getNode())        # 所有Node取得メソッド
plug.set(10)             # Mayaの値を変更

from hlib.maths import Vector

value = Vector(1, 2, 3)
print(value.x)            # Pythonオブジェクトが保持する値
```

## 判断に迷う場合

- 内部の照会・数値計算はOpenMaya API 2.0を基本とする。通常のシーン更新はUndo対応の`maya.cmds`を使い、対応APIの`fast=True`ではAPI 2.0で直接更新する。
- 読取りの高速化に`fast`指定を要求しない。単点・一括取得を使い分け、保持するMPlugやMDagPathを名前へ戻して再解決しない。型・単位・順序・削除検出の契約は維持する。
- `fast`は検証を省略する指定ではない。未対応の直接更新は変更前に拒否し、Undoのグローバル設定変更や独自プラグインで補わない。内側の対応処理は外側の`fast=True`を引き継ぐ。
- UI・環境設定、既存のcmds直接利用指定は例外としてcmds/melを使用する。

- 引数がない、処理が軽い、戻り値が単純な数値という理由だけではプロパティにしない。Mayaの現在値を取得するならメソッドにする。
- `cmds` とOpenMayaのどちらを使うかでは区別しない。MayaのAPIハンドルから現在の名前や状態を読む場合もメソッドにする。
- 内部でキャッシュしていても、「現在のシーン状態を取得する」という契約ならメソッドにする。キャッシュ方式の変更で公開形式を変えない。
- 保存時点のデータは現在のシーン状態と区別する。例えば `Node.getUuid()` は現在のノードを照会し、`NodeRef.uuid` はJSON用に保持したUUIDを参照する。
- 保持値を返すプロパティのgetterで、Mayaへの問い合わせ・ノード作成・シーン更新を暗黙に行わない。
- 保持値だけから得られる軽い派生値はプロパティにできる。ただし行列の逆行列計算や形式変換など、明示的な計算・変換は従来どおり `inverse()` / `asData()` 等のメソッドにする。シーンへ問い合わせない処理をすべてプロパティへ変える規則ではない。
- シーン編集用のproperty setterは追加しない。`hlib.maths` の数学型はom2の型を継承した可変の値型なので、ローカル値を更新するsetter(`vector.x = 1.0`、`matrix.translate = (...)` など)を使用できる。これは値の更新で、シーンは変更しない。
- データクラスの保存フィールドは、そのまま公開してよい。保存フィールドを無意味なgetterで包む必要はない。

`node.tx` はアトリビュート名を解決して `Plug` を取得する既存の省略アクセスであり、Pythonの値プロパティではない。
正式な取得入口は `node.getPlug("tx")` とし、値は `.get()` / `.set()` で扱う。
`node.tx = 10` をMayaへの書き込みとして実装・案内しない。

## maya.cmds との受け渡し

hlib のオブジェクトは `maya.cmds` へそのまま渡せることを仕様とする。詳細は
[maya.cmds との受け渡し](../maya/inhouse/hlib/_docs/cmds_interop.rst) を参照する。

- シーンのノード・アトリビュート・コンポーネントを表すクラスの `__str__` は、`maya.cmds` が一意に解決できる名前を返す。`Node` は最短一意名、`Plug` は `<ノードの最短一意名>.<アトリビュートパス>`、`Component` はシェイプの完全パス付きの名前とし、呼び出すたびに現在のシーンから求める(名前変更・親子付け替えに追従する)。
- 単一の対象を表すクラス(`Node`・`Plug` など)に `__len__`/`__iter__` を追加しない。`maya.cmds` がシーケンスとして展開してしまう。複数の対象を表すコレクションは反復可能にしてよい。
- ノードやアトリビュートを受け取るコマンド・メソッドは、文字列に加えて hlib のオブジェクトと Maya API 2.0 のオブジェクト(`MObject`・`MDagPath`・`MPlug`)を受け付ける。正規化は `Object`・`Node`・`Plug`・`Component` の内部メソッドで行い、各APIで独自に判定しない。
- ノードが必要な引数(`parent` など)は、Plug を所有ノード、Component を所有シェイプへ解決する。プラグ名を `maya.cmds` へそのまま渡して黙って無視させない。
- 名前を解決できない場合(存在しない・複数の対象に一致する)は最初の一致を黙って返さず例外にする(`"bulk*"` のようなパターンも同じ。パターンは `hlib.ls` で扱う)。対象を名前へ変換する引数(`to_name`/`to_names`/`to_node_name`)の例外の種類は、対応しない型が `TypeError`、空・削除済みの対象が `ValueError`、解決できない文字列が `RuntimeError` とする。既存の API が削除済みの対象を `RuntimeError` にしている場合(`Node(...)`/`hlib.getNode`、`hlib.addConstraint` の拘束元・拘束先)は、その規則を変えない(`to_node` は削除済みの Node などをそのまま返し、扱いを呼び出し側に任せる)。ただし所有ノードが有効なまま `deleteAttr` でアトリビュートが削除された Plug・MPlug は、所有ノードへ解決すると削除済みの対象を黙って受け付けるため、ノードが必要な引数でも `ValueError` にする(`DeletedAttributeError`。既存の規則を保つため `RuntimeError` の派生でもある)。削除済みの対象の判定メソッド(`isParentOf` など)は `False` を返す。
- オブジェクトの取得・ラップ(`node.getPlug()` などによる Plug の生成)はシーンを変更しない。配列要素の作成などシーンの変更は `getElement(index, create=True)` のように明示的な操作で行う。評価も起こさないことを基本とし、例外は仕様として明記する。現在の例外は値によって型が変わるアトリビュートで、入力接続が無い場合と、接続元も値によって型が変わるアトリビュートの場合(`choice2.input[0]` ← `choice1.output` など)は、`cmds.getAttr(type=True)` と同じく値を読むため上流の評価が起こり、評価でワールド空間の出力の要素が作られる場合もある。
- 番号を受け取る API は、Maya が範囲外の値を黙って別の値へ変換する場合(`MPlug.elementByLogicalIndex()` は 0〜2147483647 の外の論理インデックスを別の番号へ変換し、`4294967296` は `0` になる)でも、別の対象へ読み替えずに例外にする。
- 解決したノードの種類を API が扱えない場合(parent/point などの拘束元に解決されたシェイプなど)は、`maya.cmds` のように黙って壊れた結果を作らず `TypeError` にする。
- 生の `om2.MPlug` などの API オブジェクトは削除を検出できない場合があるため、hlib の内部でも削除操作をまたいで保持せず、ハンドルで有効性を確かめられる hlib のオブジェクトを保持する。

## 命名と継承

- クラス実装は原則1クラス1ファイルとする。ただし単数クラスと対応する複数クラスは同じファイルへまとめる（`joint.py` に `Joint` / `Joints`）。既存の分離済みクラスの移動は必須としない。`__init__.py` は公開用importを基本とする。
- クラスに関係する処理は、そのクラスのインスタンス／クラス／静的メソッドへ配置する。補助関数だけを置くファイルをnodes/plugs/componentsなど型をまとめるパッケージ内に増やさない。commonでは用途単位の関数モジュールも扱う。
- 特定クラスに依存しない汎用関数は `hlib.common` 配下に用途単位でまとめる。版番号のように保持値と関連操作があるものは `hlib.common.version.Version` のような値クラスにまとめる。既存のMaya互換コマンド入口 (`cmds`) は、その公開方式を維持する。

| 対象 | 推奨ルール | 例 |
| --- | --- | --- |
| パッケージ | 小文字、必要ならsnake_case | `nodes`、`components`、`common` |
| Mayaコマンドとそのファイル | Mayaと同じcamelCase | `createNode.py` / `createNode()` |
| Mayaノードのファイル | nodeTypeと同じ表記 | `skinCluster.py`、`animCurveTL.py` |
| その他の実装ファイル | lowerCamelCase | `channelBox.py`、`timeSlider.py`、`eulerRotation.py` |
| クラス | PascalCase | `SkinCluster`、`ChannelBox` |
| オブジェクト層の公開メソッド | lowerCamelCase | `getMatrix()`、`setWeights()` |

Mayaコマンド・nodeTypeに対応する名前は、Maya標準の表記を優先する。
例えば `cmds/getChannelBox.py` はコマンド、`common/channelBox.py` はエディターの実装で、いずれもlowerCamelCaseのファイル名を使う。

このファイル名規則はhlibとすべての `hlib_*` 拡張パッケージに適用する。クラス実装に限らず内部処理のファイルも `attributeType.py` のようにする。内部用の先頭 `_` は保持する。`__init__.py` 等のPython特殊名、探索規約のある `test_*.py` とテスト用スクリプト、パッケージ名は改名対象外。Maya nodeTypeと同名のファイルは大文字を含む場合もMayaの表記を優先する。内部関数・ローカル変数はsnake_caseを使用できる。nodes/plugs/componentsの公開メソッドはlowerCamelCaseとする。

- 値の取得・設定を対にするAPIは `getPosition()` / `setPosition()` のようにする。名前や判定の照会は `getName()` / `isLocked()` など、既存の意味の明確な形式を使う。全メソッドへ機械的に `get_` を付けない。
- 子クラスで基底メソッドと同名の別機能を公開しない。`Node.getInputs(type=...)` は接続検索を維持し、`AnimCurve.getKeyInputs()` と `BlendWeighted.getInputPlugs()` は専用名を使う。
- 複数形クラスは単体の同名メソッドを一括実行できるようにする。集約・重複除外・要素別設定などで意味が異なる場合は、戻り値と適用範囲を明示する。
- 同じ処理の別名を無制限に増やさない。正式な入口を決め、互換性が必要なら目的と移行先を記載する。

## 追加・変更時の確認

- API名から照会・保持値の参照・編集の違いを判断できること。
- プロパティをメソッドへ変更した場合、内部の呼び出し・複数形クラス・テスト・docstring・Sphinxの例を更新すること。
- シーン編集は既存のUndo方針に従う。対応APIの `fast=True` はUndo不要の明示指定として区別する。
- 改名・モジュール移動は `hlib.reload()` でも検証し、廃止した公開名が残らないこと。

既存APIの変更前後の対応表は [APIの命名と移行](../maya/inhouse/hlib/_docs/api_naming.rst) を参照する。

## cmdsの動詞と対象

公開関数とファイル名を同一にし、生成はcreate、既存対象への追加はadd、設定はset、
参照・値の取得はgetを使う。`ls` は一覧取得の慣用名として維持する。
`delete`・`duplicate`・`select`など既に操作を表す名前は維持する。

`addConstraint`は追加のみで、照会は`Constraint.getTargets()`/`getWeightPlugs()`、
編集は`setWeight()`などへ分ける。`createSet`も生成のみで、取得・追加・除外は
`ObjectSet.getMembers()`/`addMembers()`/`removeMembers()`を使う。
`getDrivenKey`は関係を取得するだけで、キー生成は`DrivenKey.setKey()`で行う。
アトリビュートの列挙名変更は`Plug.setEnumNames()`を使い、`addAttr`はアトリビュート追加に限定する。
旧名の互換入口は設けず、使用側を更新する。


### メソッドの統一基準

- 同じ結果を返す互換別名は追加せず、正式な入口へ集約する。
- 状態の切替は `setVisibility(state)`・`setMuted(state)` のように表す。
- 排他的な選択操作は `Selection.select(mode="replace")` のようなモードで指定する。
- メンバーの操作は `addMembers` / `removeMembers`、個数の照会は `numVertices` などの `対象_count` に揃える。
- `Plug.get/set` は対象アトリビュートを扱い、行列アトリビュートから所有ノードのTRS更新へ暗黙に切り替えない。ノード変換は `Transform.getMatrix/setMatrix` を使用する。
- 単数形と複数形の座標取得はともに `getPosition`。全要素を同じ座標にする `setPosition` と要素別の `setPositions` は区別する。
- 戻り値の型・単位・更新対象・破壊性が違う操作は、名前が似ていても安易にフラグ統合しない。

- Plug系の空間指定は廃止し、アトリビュート値とTransformの姿勢を区別する。Double3Plugのrotateは回転順序・単位変換だけを行い、jointOrientや他のチャンネルを合成しない。
- アトリビュートフラグはキーワード専用の `setFlags(locked=None, keyable=None, channelBox=None, fast=False)` へ集約する。Noneは変更なし、bool以外は更新前に拒否する。
- 一括更新では、対象名・所属・入力値など検証できる項目を更新前に全件検証する。Undoチャンクは失敗時の自動ロールバックを意味しない。

### 複数形ノードの基底クラス

- ノードコレクションは `Nodes` を基底にし、単体に対応して `DagNodes` → `Transforms` → `Joints` のように継承する。`SkinClusters` は `Nodes` の派生。`Nodes` 自体は `Node` を継承しない。
- `item_class` で受け入れるラッパー型を宣言する。入力は各基底クラスの共通処理で解決し、型の不一致を黙って除外せず例外にする。登録済みの外部拡張の派生ラッパーを基底型へ置き換えない。
- 重複は同一ノードかつ同一DAGパスで判定する。異なるインスタンスパスをUUIDだけでまとめない。構築後の参照の削除によってコレクション長を暗黙に変えない。
- 整数アクセスは保持中の参照、スライス/copyは同じ具象コレクションで同じシーン対象を参照する。ノード複製とは別。`Colors` は独立した値コピーである。
- 照会・結果が必要な生成操作の一括転送は結果リストを保つ。通常の更新はコレクション自身を返す。色getterは明示的に `Colors` を返す。関係検索を一律に平坦化したり、結果の内容からコレクション型を推測したりしない。
- 単色用 `setOverrideColor` と対象別 `setOverrideColors` のように、同値の一括指定と一対一の列を分ける。色setterは自身を返し、入力・全対象の書込み可否・共有アトリビュートの矛盾を検証してから反映する。
- 複数形メソッドは各クラスの通常の `def` と継承で公開する。派生型で単数メソッドの引数仕様が変わる場合は複数形側も明示する。要素別の入力が必要な操作は派生にも制限を引き継ぎ、直接の同一引数による一括入口を公開しない。
- `Joints.delete` 等の階層・ウェイトを扱う専用処理は単純な転送へ置き換えない。Undoは自動ロールバックを意味しない。`ls` の返却規則の変更は別途使用側を含む移行として扱う。


### 参照対象と取得契約

- 独自のアトリビュート操作名は `attribute` に統一する（`addAttr` / `setAttributeFlags`）。Mayaコマンド `addAttr` 等は標準名を維持する。
- メソッドのオーバーライドで対象を切り替えない。`Reference.associatedNamespace` は参照内容、継承した `namespace/setNamespace` はreferenceノード自身を扱う。
- 接続用参照は `*_plug`、文字列のみの一覧は `*_names` / `*_aliases` などで返却対象を明示する。
- 未存在の配列入力を取得するgetterは要素を作らずIndexErrorとする。作成はsetter等へ限定する。
- `PluginPackage.tryLoad` は状態文字列を返し、`Plugin.ensureLoaded` は失敗時に例外を送出する。成功保証の違いを隠さない。
- `getVisibility/setVisibility` は自身のvisibilityアトリビュートだけを扱い、階層や表示レイヤーを含む最終可視性と区別する。

## 参照と入力の固定規則

- Nodeの等価比較は生存中のMaya対象、DAGではインスタンスパスも含む。JointだけのUUID比較は廃止。sameNodeは同じMayaノード、sameInstanceは同じDAGインスタンスを明示的に比較する。
- Nodeのhashは生成時のMObjectHandle.hashCodeを保持。Plugは所有ノードのhashと生成時のアトリビュートパスを保持する。改名・削除でhashを変えず、永続IDとして保存しない。完全破棄後は他参照と等価にしない。可変数学型/Colorはhash不可を維持。
- getNode/Nodeは動的に型解決するが、具体クラスの構築はその型または派生に適合しなければTypeError。Nodeと同一のノードを別の具体型へ無理にラップしない。
- 保持DAGパスの消失を別インスタンスへの自動切替で補わない。ノードの有効性とパスの有効性を区別する。
- ノード対象列では文字列とNodeの混在を変更前にTypeErrorにする。名前列/Node列は両方許可し、派生型はNode形式として扱う。空入力や操作対象型の制限は各操作の仕様を維持する。
- reload後の旧インスタンスは取得し直す。新旧クラスの相互比較/自動移行を保証しない。
- lsの専用コレクション返却、copy/sliceの参照共有、bulk失敗時の停止・自動ロールバックなしを維持する。
- Maya依存の有無は責務分離の基準にしない。対象に固有の取得・計算・更新は同じクラスに置く。

## 設定操作と保存先

- Scene・Preferences・Workspaceなど操作対象の概念でクラスを構成し、保存ファイルごとに操作クラスを分割しない。
- 設定操作クラスはMayaの現在値を問い合わせる。保持する値のコピーと混同しない。
- 設定メソッドには作用範囲・保存区分・保存の有無を記載する。現在値の変更、保存用optionVarの同期、ディスク保存を区別する。
- 保存先と保存・復元時期はSphinxのsettings_storage.rstに集約する。
- 比較・復元・JSON出力が必要になった場合にスナップショット用データを設計する。未実装のcapture/apply等を使用例として掲載しない。

### 基底責務・一括公開・UI退避の契約

- ConstraintはMayaの継承に合わせTransform派生とする。表示・Outliner色・Drawing OverridesはDagNode、複数形はDagNodesに置く。Nodesは全DGノード共通の参照・アトリビュート・接続処理を扱う。
- 複数形APIは通常のメソッドとして明示し、単数APIの自動全公開はしない。照会・生成結果が必要な操作は保持順の結果リスト、通常の更新は自身を返す。callEachも同じ規則。既存の専用集約結果やdeleteのNoneはdocstringへ明示する。
- Preferencesの単位setterはsaveを受け付けない。シーン保存で保持する。その他のsave=Trueは一般ユーザー設定全体の保存を意味し、batchでは更新前に拒否する。
- Window/WorkspaceControlはMaya標準MUiMessageの削除通知で寿命を追跡し、同名再生成へ乗り換えない。UiSnapshotは同一セッション限定の変更不可値で、復元前に対象の寿命を検証する。
- WorkspaceLayoutは配置の切り替え・保存と全体のドッキングロックを扱い、ドッキング配置のメモリ退避・復元は提供しない。cmds/melからはworkspaceControlのドッキング先を照会できず、`window -dockingLayout`/`-state`にも含まれないため(Qtが必要になるが、hlibはQtをimportしない)。配置全体を戻す場合は保存済み配置をactivate/resetで読み直す。

- hlibはQt関連ライブラリ（PySide/PyQt/shiboken/qtpy等）をimportしない。Maya標準UIはcmds/mel/OpenMayaUIの通知APIで扱い、MQtUtilによるポインター取得やQtへの変換は利用側のUIパッケージへ置く。MainWindowはUI名だけを返す。

## 入力解決とパッケージ境界

- `_core/object.py` の `Object` は単数の `Node`・`Plug`・`Component` の共通基底。取得は `from hlib._core.object import Object` とし、ルートへ再公開しない。`Object(value)` は具体的な参照型を返し、既存ラッパーはそのまま返す。比較・ハッシュ・寿命は各参照型が担当する。
- `Node._resolve_input()` はノードを必要とする内部処理、`Plug._resolve_input()` はアトリビュート入力、`Component._resolve_input()` は単一要素入力を解決する。各公開APIで判定処理を複製しない。
- `Object._input_name()` / `_input_names()` はcmds向けの名前変換。文字列をそのまま渡す既存の規則を維持し、対象解決を必要とする `Object()` と区別する。
- `Nodes._resolve_inputs()` は複数入力を検証する。名前だけ／Nodeだけを受け付け、同じ対象列の文字列とNodeの混在は拒否する。空集合など各APIの規則は維持する。
- 公開フォルダは `nodes`・`plugs`・`components`・`maths`・`cmds`・`common`・`json` とする。シーン状態・関係、標準UI参照・表示色、環境・プラグイン導入状態、イベント・遅延実行、汎用関数は `common` 直下へ統合する。領域別のサブフォルダは作らず、具体的な機能名のファイルから提供する。
- ログ・通知・出力は `hlib.logger`、デコレーター・コンテキストマネージャーは `hlib.decorator` を正式入口とする。保存基盤は直下の `json`、文書と生成設定は `_docs` に置く。
- 拡張管理の正式入口は `_core/extensions.py` とし、拡張作者は `from hlib._core import extensions` を使う。ルートへ再公開せず、旧モジュールパスの互換入口も残さない。
- 数学値・複数形コレクション・UI・保存データは `Object` の派生にしない。既存の便利メソッド・Undo・fastの意味は維持する。
- 旧 `general` / `_core/coerce.py` の互換ファイルは残さず、内製利用側も正式な配置へ更新する。

### 内部の参照方向

- 入力の汎用展開は `Object._flatten_inputs()`、展開済み列の名前/Node混在検査は `Nodes._validate_inputs()`。検査からObjectの展開へ戻らない。`Nodes._resolve_inputs()` は両者を順に呼ぶノード側入口。
- 公開コマンドはクラス側の共通処理に委譲する。`addAttr` は `Node._add_attribute()`、`executeDeferred` は `Deferred.call()` を呼ぶ。クラス側から公開コマンドへ戻らない。Undoと短縮フラグは各公開入口の契約を維持する。
- `_core.collection` は転送メソッドを生成し、実行は `Nodes._dispatch_shared()` に任せる。独自 `callEach()` のoverride判定と共通引数の実行方針はNodesが所有する。

### 任意拡張の参照方向と再読み込み

- 拡張はhlibの公開APIへ依存し、他のhlib_*をimport・継承しない。組合せ処理はhrig等の利用側に置く。
- 拡張の__init__.pyは宣言を先に完了し、hlibやラッパーを先行importしない。公開サブパッケージは必要時に読み込む。
- hlib.reload()は宣言済み拡張の一括解除、本体の再読み込み、拡張の再検出・登録の順で処理する。外部SDKとMayaプラグインは再ロードしない。
- リロード後は利用側の拡張パッケージ・クラス・インスタンス参照を取得し直す。初期化中のリロードは拒否する。


## 対象を所有するクラスへの委譲

- 具象Nodeは対象Plug・値の意味・更新順を決め、値設定はPlugへ委譲する。通常/fastの型付き書込みと単位境界をノードごとに再実装しない。
- 複数Plugの更新可否を先に調べる処理は、Plugの内部検証を使う。事前検証と自動ロールバックは別の契約であり、fastの実行途中の失敗を自動で戻す保証はしない。
- ArrayPlugは論理番号と要素の参照・存在を管理する。内部の書込み・接続経路は参照だけを取得し、更新前のgetAttrによる要素作成を避ける。公開element(create=True)の明示作成は従来の契約を維持する。
- Mesh/Curveの単数・複数コンポーネントとShapeの座標書込みは、非公開のgeometryEditを共有する。通常cmds/fast om2、CVの番号変換・重み・単位変換をこの境界へ集約する。Shapeは変形する座標列を決める。
- JSONの保存形式は公開Plug値とは別の契約。型の低水準読取・単位変換は共有し、保存時の単位・配列形・未初期化値はJSON側で維持する。
- Transform姿勢とJoint固有の変換、SkinClusterの一括ウェイト処理は、それぞれの意味と効率を持つため単純なPlugの反復へ置き換えない。

### 公開メソッド名の確定仕様（2026-10-05）

ユーザーの明示指示により、所有Plugの`getNode()`は保持参照でもメソッドとする。`hasAttr`・`parent`・`longName`・`delete`・`mnode`・`mpath`等への移行と、短縮メソッドを正式APIとする。旧hlib名の互換別名は残さない。ノードとPlug共通の`getFullName()`、複数フラグを扱う`setFlags()`等の独自操作は維持する。詳細・制限は`maya/inhouse/hlib/_docs/api_methods.rst`を参照する。

### Transformationの追加仕様

`hlib.maths.Transformation` は既存数学値をまとめるシーン非依存の可変値で、om2型の派生ではない。値の保持・成分編集はプロパティ、シーン照会/適用は`Transform.getTransformation`/`setTransformation`に分ける。距離cm・角度radianを使い、通常setterは自身、`get=True`は適合後のTransformationを返す。ユーザーの連携統一指示により`Matrix.asTransformation()`はhlibのTransformationを返す。OpenMaya型は`om2.MTransformationMatrix(matrix)`で明示変換する。`Matrix(value)`・`Matrix.fromTransformation(value)`・MatrixPlug.setはTransformationの合成行列を受け取る。`setMatrix(get=True)`の辞書返却は維持する。成分・空間・制限は`maya/inhouse/hlib/_docs/transformation.rst`を参照する。

配列要素参照の標準表記は`array[index]`とし、未作成の論理番号も非実体化のPlugとして参照できる。配列反復は既存要素の論理番号順、`get()`は番号を保持する辞書。既存の明示的な`getElement(index, create=False)`の仕様は維持する。複合の子もユーザーの統一指示により`compound[index]`・`compound[name]`とし、旧childメソッドは残さない。複合の整数番号は0以上の定義順、反復は子の定義順。配列・複合Plugをmaya.cmdsへ渡す時はstrまたはfullNameで文字列化する。hlibコマンドでは直接受け取る。Plugの`setAlias`・`setKey`は自身を返す。`setKey`内部はmaya.cmds.setKeyframeを直接使用し、hlib.cmdsの同名ラッパーは作らない。
