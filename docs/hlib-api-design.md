# hlib APIの設計基準

今後のAPI追加・変更では、**Mayaへ問い合わせる操作はメソッド、保持する値はプロパティ**を基本とする。
実装・docstring・使用例を同じ基準に揃える。

## メソッドとプロパティ

| 対象 | 公開形式 | 例 |
| --- | --- | --- |
| Mayaの現在の状態・名前・属性情報を問い合わせる | メソッド | `node.full_name()`、`node.is_locked()`、`plug.name()` |
| Maya上の座標など、評価済みの値を取得する | メソッド | `vertex.get_position()`、`vertex.get_x()`、`mesh.num_vertices()` |
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

`node.tx` は属性名を解決して `Plug` を取得する既存の省略アクセスであり、Pythonの値プロパティではない。
正式な取得入口は `node.plug("tx")` とし、値は `.get()` / `.set()` で扱う。
`node.tx = 10` をMayaへの書き込みとして実装・案内しない。

## maya.cmds との受け渡し

hlib のオブジェクトは `maya.cmds` へそのまま渡せることを仕様とする。詳細は
[maya.cmds との受け渡し](../maya/inhouse/hlib/docs/cmds_interop.rst) を参照する。

- シーンのノード・属性・コンポーネントを表すクラスの `__str__` は、`maya.cmds` が一意に解決できる名前を返す。`Node` は最短一意名、`Plug` は `<ノードの最短一意名>.<属性パス>`、`Component` はシェイプの完全パス付きの名前とし、呼び出すたびに現在のシーンから求める(名前変更・親子付け替えに追従する)。
- 単一の対象を表すクラス(`Node`・`Plug` など)に `__len__`/`__iter__` を追加しない。`maya.cmds` がシーケンスとして展開してしまう。複数の対象を表すコレクションは反復可能にしてよい。
- ノードや属性を受け取るコマンド・メソッドは、文字列に加えて hlib のオブジェクトと Maya API 2.0 のオブジェクト(`MObject`・`MDagPath`・`MPlug`)を受け付ける。正規化は `hlib._core.coerce` で行い、各APIで独自に判定しない。
- ノードが必要な引数(`parent` など)は、Plug を所有ノード、Component を所有シェイプへ解決する。プラグ名を `maya.cmds` へそのまま渡して黙って無視させない。
- 名前を解決できない場合(存在しない・複数の対象に一致する)は最初の一致を黙って返さず例外にする(`"bulk*"` のようなパターンも同じ。パターンは `hlib.ls` で扱う)。対象を名前へ変換する引数(`to_name`/`to_names`/`to_node_name`)の例外の種類は、対応しない型が `TypeError`、空・削除済みの対象が `ValueError`、解決できない文字列が `RuntimeError` とする。既存の API が削除済みの対象を `RuntimeError` にしている場合(`Node(...)`/`hlib.node`、`hlib.constraint` の拘束元・拘束先)は、その規則を変えない(`to_node` は削除済みの Node などをそのまま返し、扱いを呼び出し側に任せる)。ただし所有ノードが有効なまま `deleteAttr` で属性が削除された Plug・MPlug は、所有ノードへ解決すると削除済みの対象を黙って受け付けるため、ノードが必要な引数でも `ValueError` にする(`DeletedAttributeError`。既存の規則を保つため `RuntimeError` の派生でもある)。削除済みの対象の判定メソッド(`is_parent_of` など)は `False` を返す。
- オブジェクトの取得・ラップ(`node.plug()` などによる Plug の生成)はシーンを変更しない。配列要素の作成などシーンの変更は `element(index, create=True)` のように明示的な操作で行う。評価も起こさないことを基本とし、例外は仕様として明記する。現在の例外は値によって型が変わる属性で、入力接続が無い場合と、接続元も値によって型が変わる属性の場合(`choice2.input[0]` ← `choice1.output` など)は、`cmds.getAttr(type=True)` と同じく値を読むため上流の評価が起こり、評価でワールド空間の出力の要素が作られる場合もある。
- 番号を受け取る API は、Maya が範囲外の値を黙って別の値へ変換する場合(`MPlug.elementByLogicalIndex()` は 0〜2147483647 の外の論理インデックスを別の番号へ変換し、`4294967296` は `0` になる)でも、別の対象へ読み替えずに例外にする。
- 解決したノードの種類を API が扱えない場合(parent/point などの拘束元に解決されたシェイプなど)は、`maya.cmds` のように黙って壊れた結果を作らず `TypeError` にする。
- 生の `om2.MPlug` などの API オブジェクトは削除を検出できない場合があるため、hlib の内部でも削除操作をまたいで保持せず、ハンドルで有効性を確かめられる hlib のオブジェクトを保持する。

## 命名と継承

- クラスの実装は1クラス1ファイルにする。コレクションクラスも単体クラスとは別ファイルに置き、`__init__.py` は公開用importを基本とする。
- クラスに関係する処理は、そのクラスのインスタンス／クラス／静的メソッドへ配置する。補助関数だけを置くファイルをクラスのパッケージ内に増やさない。
- 特定クラスに依存しない汎用関数は `hlib.utils` 配下に用途単位でまとめる。版番号のように保持値と関連操作があるものは `hlib.utils.version.Version` のような値クラスにまとめる。既存のMaya互換コマンド入口 (`cmds`) は、その公開方式を維持する。

| 対象 | 推奨ルール | 例 |
| --- | --- | --- |
| パッケージ | 小文字、必要ならsnake_case | `nodes`、`components`、`editors` |
| Mayaコマンドとそのファイル | Mayaと同じcamelCase | `createNode.py` / `createNode()` |
| Mayaノードのファイル | nodeTypeと同じ表記 | `skinCluster.py`、`animCurveTL.py` |
| その他の実装ファイル | lowerCamelCase | `channelBox.py`、`timeSlider.py`、`eulerRotation.py` |
| クラス | PascalCase | `SkinCluster`、`ChannelBox` |
| 独自メソッド | snake_case | `get_matrix()`、`set_weights()` |

Mayaコマンド・nodeTypeに対応する名前は、Maya標準の表記を優先する。
例えば `cmds/channelBox.py` はコマンド、`editors/channelBox.py` はエディターの実装で、どちらも同じファイル名の表記を使う。

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
