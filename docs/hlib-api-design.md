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
| Maya非依存の数学値・保存済みデータを参照する | プロパティまたはデータフィールド | `vector.x`、`matrix.translate`、`node_ref.uuid` |

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
- 保持値だけから得られる軽い派生値はプロパティにできる。ただし行列の逆行列計算や形式変換など、明示的な計算・変換は従来どおり `inverse()` / `to_data()` 等のメソッドにする。Maya非依存の処理をすべてプロパティへ変える規則ではない。
- シーン編集用のproperty setterは追加しない。数学型のローカル値を更新するsetterは、型が可変として設計されている場合に限り使用できる。不変な数学型のフィールドを代入可能に変えるものではない。
- データクラスの保存フィールドは、そのまま公開してよい。保存フィールドを無意味なgetterで包む必要はない。

`node.tx` は属性名を解決して `Plug` を取得する既存の省略アクセスであり、Pythonの値プロパティではない。
正式な取得入口は `node.plug("tx")` とし、値は `.get()` / `.set()` で扱う。
`node.tx = 10` をMayaへの書き込みとして実装・案内しない。

## 命名と継承

| 対象 | 推奨ルール | 例 |
| --- | --- | --- |
| パッケージ | 小文字、必要ならsnake_case | `nodes`、`components`、`editors` |
| Mayaコマンドとそのファイル | Mayaと同じcamelCase | `createNode.py` / `createNode()` |
| Mayaノードのファイル | nodeTypeと同じ表記 | `skinCluster.py`、`animCurveTL.py` |
| その他のファイル | snake_case | `channel_box.py`、`time_slider.py`、`euler_rotation.py` |
| クラス | PascalCase | `SkinCluster`、`ChannelBox` |
| 独自メソッド | snake_case | `get_matrix()`、`set_weights()` |

Mayaコマンド・nodeTypeに対応する名前は、Maya標準の表記を優先する。
例えば `cmds/channelBox.py` はコマンド、`editors/channel_box.py` はエディターの実装なので、それぞれの規則を適用する。

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
