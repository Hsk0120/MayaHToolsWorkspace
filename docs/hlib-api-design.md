# hlib APIの設計基準

今後のAPI追加・変更では、**Mayaへ問い合わせる操作はメソッド、保持する値はプロパティ**を基本とする。
実装・docstring・使用例を同じ基準に揃える。

## メソッドとプロパティ

| 対象 | 公開形式 | 例 |
| --- | --- | --- |
| Mayaの現在の状態・名前・アトリビュート情報を問い合わせる | メソッド | `node.full_name()`、`node.is_locked()`、`plug.name()` |
| Maya上の座標など、評価済みの値を取得する | メソッド | `vertex.get_position()`、`vertex.get_x()`、`mesh.vertex_count()` |
| Mayaの状態を変更する | 明示的なメソッド | `plug.set(value)`、`vertex.set_x(value)`、`node.rename(name)` |
| オブジェクトが保持している参照・番号を返す | プロパティ | `plug.node`、`component.shape`、`component.index`、`components.indices` |
| 数学値(`hlib.maths`)・保存済みデータを参照する | プロパティまたはデータフィールド | `vector.x`、`matrix.translate`、`node_ref.uuid` |

```python
import hlib

node = hlib.createNode("transform")
plug = node.plug("translateX")

print(node.full_name())    # 現在のMayaノード名を取得
print(plug.is_locked())   # 現在のロック状態を照会
print(plug.node)          # 保持している所有Nodeへの参照
plug.set(10)             # Mayaの値を変更

from hlib.maths import Vector

value = Vector(1, 2, 3)
print(value.x)            # Pythonオブジェクトが保持する値
```

## 判断に迷う場合

- 引数がない、処理が軽い、戻り値が単純な数値という理由だけではプロパティにしない。Mayaの現在値を取得するならメソッドにする。
- `cmds` とOpenMayaのどちらを使うかでは区別しない。MayaのAPIハンドルから現在の名前や状態を読む場合もメソッドにする。
- 内部でキャッシュしていても、「現在のシーン状態を取得する」という契約ならメソッドにする。キャッシュ方式の変更で公開形式を変えない。
- 保存時点のデータは現在のシーン状態と区別する。例えば `Node.uuid()` は現在のノードを照会し、`NodeRef.uuid` はJSON用に保持したUUIDを参照する。
- 保持値を返すプロパティのgetterで、Mayaへの問い合わせ・ノード作成・シーン更新を暗黙に行わない。
- 保持値だけから得られる軽い派生値はプロパティにできる。ただし行列の逆行列計算や形式変換など、明示的な計算・変換は従来どおり `inverse()` / `to_data()` 等のメソッドにする。シーンへ問い合わせない処理をすべてプロパティへ変える規則ではない。
- シーン編集用のproperty setterは追加しない。`hlib.maths` の数学型はom2の型を継承した可変の値型なので、ローカル値を更新するsetter(`vector.x = 1.0`、`matrix.translate = (...)` など)を使用できる。これは値の更新で、シーンは変更しない。
- データクラスの保存フィールドは、そのまま公開してよい。保存フィールドを無意味なgetterで包む必要はない。

`node.tx` はアトリビュート名を解決して `Plug` を取得する既存の省略アクセスであり、Pythonの値プロパティではない。
正式な取得入口は `node.plug("tx")` とし、値は `.get()` / `.set()` で扱う。
`node.tx = 10` をMayaへの書き込みとして実装・案内しない。

## maya.cmds との受け渡し

hlib のオブジェクトは `maya.cmds` へそのまま渡せることを仕様とする。詳細は
[maya.cmds との受け渡し](../maya/inhouse/hlib/docs/cmds_interop.rst) を参照する。

- シーンのノード・アトリビュート・コンポーネントを表すクラスの `__str__` は、`maya.cmds` が一意に解決できる名前を返す。`Node` は最短一意名、`Plug` は `<ノードの最短一意名>.<アトリビュートパス>`、`Component` はシェイプの完全パス付きの名前とし、呼び出すたびに現在のシーンから求める(名前変更・親子付け替えに追従する)。
- 単一の対象を表すクラス(`Node`・`Plug` など)に `__len__`/`__iter__` を追加しない。`maya.cmds` がシーケンスとして展開してしまう。複数の対象を表すコレクションは反復可能にしてよい。
- ノードやアトリビュートを受け取るコマンド・メソッドは、文字列に加えて hlib のオブジェクトと Maya API 2.0 のオブジェクト(`MObject`・`MDagPath`・`MPlug`)を受け付ける。正規化は `hlib._core.coerce` で行い、各APIで独自に判定しない。
- ノードが必要な引数(`parent` など)は、Plug を所有ノード、Component を所有シェイプへ解決する。プラグ名を `maya.cmds` へそのまま渡して黙って無視させない。
- 名前を解決できない場合(存在しない・複数の対象に一致する)は最初の一致を黙って返さず例外にする(`"bulk*"` のようなパターンも同じ。パターンは `hlib.ls` で扱う)。対象を名前へ変換する引数(`to_name`/`to_names`/`to_node_name`)の例外の種類は、対応しない型が `TypeError`、空・削除済みの対象が `ValueError`、解決できない文字列が `RuntimeError` とする。既存の API が削除済みの対象を `RuntimeError` にしている場合(`Node(...)`/`hlib.getNode`、`hlib.addConstraint` の拘束元・拘束先)は、その規則を変えない(`to_node` は削除済みの Node などをそのまま返し、扱いを呼び出し側に任せる)。ただし所有ノードが有効なまま `deleteAttr` でアトリビュートが削除された Plug・MPlug は、所有ノードへ解決すると削除済みの対象を黙って受け付けるため、ノードが必要な引数でも `ValueError` にする(`DeletedAttributeError`。既存の規則を保つため `RuntimeError` の派生でもある)。削除済みの対象の判定メソッド(`is_parent_of` など)は `False` を返す。
- オブジェクトの取得・ラップ(`node.plug()` などによる Plug の生成)はシーンを変更しない。配列要素の作成などシーンの変更は `element(index, create=True)` のように明示的な操作で行う。評価も起こさないことを基本とし、例外は仕様として明記する。現在の例外は値によって型が変わるアトリビュートで、入力接続が無い場合と、接続元も値によって型が変わるアトリビュートの場合(`choice2.input[0]` ← `choice1.output` など)は、`cmds.getAttr(type=True)` と同じく値を読むため上流の評価が起こり、評価でワールド空間の出力の要素が作られる場合もある。
- 番号を受け取る API は、Maya が範囲外の値を黙って別の値へ変換する場合(`MPlug.elementByLogicalIndex()` は 0〜2147483647 の外の論理インデックスを別の番号へ変換し、`4294967296` は `0` になる)でも、別の対象へ読み替えずに例外にする。
- 解決したノードの種類を API が扱えない場合(parent/point などの拘束元に解決されたシェイプなど)は、`maya.cmds` のように黙って壊れた結果を作らず `TypeError` にする。
- 生の `om2.MPlug` などの API オブジェクトは削除を検出できない場合があるため、hlib の内部でも削除操作をまたいで保持せず、ハンドルで有効性を確かめられる hlib のオブジェクトを保持する。

## 命名と継承

- クラス実装は原則1クラス1ファイルとする。ただし単数クラスと対応する複数クラスは同じファイルへまとめる（`joint.py` に `Joint` / `Joints`）。既存の分離済みクラスの移動は必須としない。`__init__.py` は公開用importを基本とする。
- クラスに関係する処理は、そのクラスのインスタンス／クラス／静的メソッドへ配置する。補助関数だけを置くファイルをクラスのパッケージ内に増やさない。
- 特定クラスに依存しない汎用関数は `hlib.utils` 配下に用途単位でまとめる。版番号のように保持値と関連操作があるものは `hlib.utils.version.Version` のような値クラスにまとめる。既存のMaya互換コマンド入口 (`cmds`) は、その公開方式を維持する。

| 対象 | 推奨ルール | 例 |
| --- | --- | --- |
| パッケージ | 小文字、必要ならsnake_case | `nodes`、`components`、`general` |
| Mayaコマンドとそのファイル | Mayaと同じcamelCase | `createNode.py` / `createNode()` |
| Mayaノードのファイル | nodeTypeと同じ表記 | `skinCluster.py`、`animCurveTL.py` |
| その他の実装ファイル | lowerCamelCase | `channelBox.py`、`timeSlider.py`、`eulerRotation.py` |
| クラス | PascalCase | `SkinCluster`、`ChannelBox` |
| 独自メソッド | snake_case | `get_matrix()`、`set_weights()` |

Mayaコマンド・nodeTypeに対応する名前は、Maya標準の表記を優先する。
例えば `cmds/getChannelBox.py` はコマンド、`general/channelBox.py` はエディターの実装で、いずれもlowerCamelCaseのファイル名を使う。

このファイル名規則はhlibとすべての `hlib_*` 拡張パッケージに適用する。クラス実装に限らず内部処理のファイルも `attributeType.py` のようにする。内部用の先頭 `_` は保持する。`__init__.py` 等のPython特殊名、探索規約のある `test_*.py` とテスト用スクリプト、パッケージ名は改名対象外。Maya nodeTypeと同名のファイルは大文字を含む場合もMayaの表記を優先する。関数・独自メソッド・変数のsnake_caseは維持する。

- 値の取得・設定を対にするAPIは `get_position()` / `set_position()` のようにする。名前や判定の照会は `name()` / `is_locked()` など、既存の意味の明確な形式を使う。全メソッドへ機械的に `get_` を付けない。
- 子クラスで基底メソッドと同名の別機能を公開しない。`Node.inputs(type=...)` は接続検索を維持し、`AnimCurve.key_inputs()` と `BlendWeighted.input_plugs()` は専用名を使う。
- 複数形クラスは単体の同名メソッドを一括実行できるようにする。集約・重複除外・要素別設定などで意味が異なる場合は、戻り値と適用範囲を明示する。
- 同じ処理の別名を無制限に増やさない。正式な入口を決め、互換性が必要なら目的と移行先を記載する。

## 追加・変更時の確認

- API名から照会・保持値の参照・編集の違いを判断できること。
- プロパティをメソッドへ変更した場合、内部の呼び出し・複数形クラス・テスト・docstring・Sphinxの例を更新すること。
- シーン編集は既存のUndo方針に従う。対応APIの `fast=True` はUndo不要の明示指定として区別する。
- 改名・モジュール移動は `hlib.reload()` でも検証し、廃止した公開名が残らないこと。

既存APIの変更前後の対応表は [APIの命名と移行](../maya/inhouse/hlib/docs/api_naming.rst) を参照する。

## cmdsの動詞と対象

公開関数とファイル名を同一にし、生成はcreate、既存対象への追加はadd、設定はset、
参照・値の取得はgetを使う。`ls` は一覧取得の慣用名として維持する。
`delete`・`duplicate`・`select`など既に操作を表す名前は維持する。

`addConstraint`は追加のみで、照会は`Constraint.targets()`/`weight_plugs()`、
編集は`set_weight()`などへ分ける。`createSet`も生成のみで、取得・追加・除外は
`ObjectSet.members()`/`add_members()`/`remove_members()`を使う。
`getDrivenKey`は関係を取得するだけで、キー生成は`DrivenKey.set_key()`で行う。
アトリビュートの列挙名変更は`Plug.set_enum_names()`を使い、`addAttr`はアトリビュート追加に限定する。
旧名の互換入口は設けず、使用側を更新する。


### メソッドの統一基準

- 同じ結果を返す互換別名は追加せず、正式な入口へ集約する。
- 状態の切替は `set_visibility(state)`・`set_muted(state)` のように表す。
- 排他的な選択操作は `Selection.select(mode="replace")` のようなモードで指定する。
- メンバーの操作は `add_members` / `remove_members`、個数の照会は `vertex_count` などの `対象_count` に揃える。
- `Plug.get/set` は対象アトリビュートを扱い、行列アトリビュートから所有ノードのTRS更新へ暗黙に切り替えない。ノード変換は `Transform.get_matrix/set_matrix` を使用する。
- 単数形と複数形の座標取得はともに `get_position`。全要素を同じ座標にする `set_position` と要素別の `set_positions` は区別する。
- 戻り値の型・単位・更新対象・破壊性が違う操作は、名前が似ていても安易にフラグ統合しない。

- Plug系の空間指定は廃止し、アトリビュート値とTransformの姿勢を区別する。Double3Plugのrotateは回転順序・単位変換だけを行い、jointOrientや他のチャンネルを合成しない。
- アトリビュートフラグはキーワード専用の `set_flags(locked=None, keyable=None, channel_box=None, fast=False)` へ集約する。Noneは変更なし、bool以外は更新前に拒否する。
- 一括更新では、対象名・所属・入力値など検証できる項目を更新前に全件検証する。Undoチャンクは失敗時の自動ロールバックを意味しない。

### 複数形ノードの基底クラス

- ノードコレクションは `Nodes` を基底にし、単体に対応して `Transforms` → `Joints` のように継承する。`SkinClusters` は `Nodes` の派生。`Nodes` 自体は `Node` を継承しない。
- `item_class` で受け入れるラッパー型を宣言する。入力は既存coerceで解決し、型の不一致を黙って除外せず例外にする。登録済みの外部拡張の派生ラッパーを基底型へ置き換えない。
- 重複は同一ノードかつ同一DAGパスで判定する。異なるインスタンスパスをUUIDだけでまとめない。構築後の参照の削除によってコレクション長を暗黙に変えない。
- 整数アクセスは保持中の参照、スライス/copyは同じ具象コレクションで同じシーン対象を参照する。ノード複製とは別。`Colors` は独立した値コピーである。
- 通常の一括転送は結果リストを保つ。色getterは明示的に `Colors` を返す。関係検索を一律に平坦化したり、結果の内容からコレクション型を推測したりしない。
- 単色用 `set_override_color` と対象別 `set_override_colors` のように、同値の一括指定と一対一の列を分ける。色setterは自身を返し、入力・全対象の書込み可否・共有アトリビュートの矛盾を検証してから反映する。
- `bulk_api` は明示実装を優先し、自動生成された継承メソッドのみ派生型のsignatureへ更新する。`per_item_only` は派生にも継承し、直接の一括入口を公開しない。
- `Joints.delete` 等の階層・ウェイトを扱う専用処理は単純な転送へ置き換えない。Undoは自動ロールバックを意味しない。`ls` の返却規則の変更は別途使用側を含む移行として扱う。


### 参照対象と取得契約

- 独自のアトリビュート操作名は `attribute` に統一する（`add_attribute` / `set_attribute_flags`）。Mayaコマンド `addAttr` 等は標準名を維持する。
- メソッドのオーバーライドで対象を切り替えない。`Reference.associated_namespace` は参照内容、継承した `namespace/set_namespace` はreferenceノード自身を扱う。
- 接続用参照は `*_plug`、文字列のみの一覧は `*_names` / `*_aliases` などで返却対象を明示する。
- 未存在の配列入力を取得するgetterは要素を作らずIndexErrorとする。作成はsetter等へ限定する。
- `PluginPackage.try_load` は状態文字列を返し、`Plugin.ensure_loaded` は失敗時に例外を送出する。成功保証の違いを隠さない。
- `get_visibility/set_visibility` は自身のvisibilityアトリビュートだけを扱い、階層や表示レイヤーを含む最終可視性と区別する。

## 参照と入力の固定規則

- Nodeの等価比較は生存中のMaya対象、DAGではインスタンスパスも含む。JointだけのUUID比較は廃止。same_nodeは同じMayaノード、same_instanceは同じDAGインスタンスを明示的に比較する。
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
