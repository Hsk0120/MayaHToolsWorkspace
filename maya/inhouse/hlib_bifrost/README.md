# hlib_bifrost

Maya 2025以降・Bifrost 3.0.0.0以上向けのVNN操作ライブラリです。
import時はプラグインをロードしません。`is_available()` はロード済み対応版かを照会し、
`general.Bifrost.ensure_available()` と `Graph.create()` は必要時にロードします。
hlibの拡張検出プロトコルに対応しますが、内部VNNノードをMaya DGノードとして登録しません。

```python
from maya import cmds
from hlib_bifrost.nodes import Graph

graph = Graph.create('exampleShape')
graph.root.add_port('value', 'float')
graph.root.add_port('result', 'float', output=True)
graph.root.io_port('value').connect(graph.root.io_port('result', output=True))
cmds.setAttr(graph.name() + '.value', 4)
assert cmds.getAttr(graph.name() + '.result') == 4
```

`Graph`はhlibのDG参照で名前変更に追従します。`Node`、`Compound`、`Port`は
グラフ内のパス参照です。内部ノードを改名した場合は取得し直してください。
`Compound.add_node()`で公開Compoundを追加し、`Node.add_port()`で可変入力を追加します。
`Port.set_default()`は定数設定、`connect()` / `disconnect()`は接続操作です。
Compoundの外部ポートは`port()`、既定input/outputノードの内部ポートは`io_port()`で参照します。

VNNコマンドのエラーは隠さず呼出側へ返します。MayaのUndoに従います。
グラフは通常のMayaシーンとして保存でき、`Graph('既存shape名')`で再取得します。
型自動推論、全Bifrost APIのラップ、内部ノード改名への自動追従は含みません。


## 共通の演算構築

`Graph`・`Node`・`Compound`・`Port`はそれぞれのPythonファイルに実装しています。
クラスはnodes/plugs/utils/generalの所属パッケージからimportします。
`Graph.parent()`は現在のDAG親、`Graph.delete()`は親を含む削除です。
親に別の子がある場合は削除を拒否するため、必要ならshapeだけ明示削除してください。

```python
from hlib_bifrost.nodes import Graph
from hlib_bifrost.utils import MathBuilder

graph = Graph.create("sampleGraph")
graph.root.add_port("result", "float", output=True)
builder = MathBuilder(graph.root)
value = builder.operation("add", (2.0, 3.0))
builder.clamp(value, 0.0, 4.0).connect(graph.root.io_port("result", output=True))


```

`MathBuilder.feed`は定数または同一グラフのPortを接続先へ割り当てます。
`operation`はCore::Mathのfloat多入力演算用です。min/max等は結果ポート名を
`output="minimum"`／`"maximum"`で指定してください。固定ポートを持つ任意の演算を
自動推定する機能ではありません。
Soft IKのdistance/softnessは同じ距離単位、ratioは単位なしです。
Bifrost版はゼロ除算を避けるためdistance/softnessを1e-6以上へ制限し、
この微小域では標準DG版と厳密には一致しません。作成・演算追加・削除はUndoに対応します。
hrigの標準構成からBifrostをロードすることはありません。

## パッケージ構成

```text
hlib_bifrost/
  nodes/      # Graph・Node・Compound（1クラス1ファイル）
  plugs/      # Port（Bifrost内部ポート）
  utils/      # MathBuilder（汎用演算）
  general/    # Bifrostの対応版確認・明示ロード
  __tests__/
```

hlibと同じ責務の区分を使います。VNN参照をMaya DGのNode/Plugとして登録はしません。
新規コードは `from hlib_bifrost.nodes import Graph` 等を使用できます。
旧ルートモジュールとクラス再公開は廃止しています。
プラグイン判定・ロードは `general.Bifrost`。ルートの `is_available` はhlib拡張検出専用です。

Soft IKの構築は `hrig.setups.bifrostSoftIK.SoftIK` へ移動しました。hlib_bifrostは基本グラフ操作・演算構築を提供し、hrigへ依存しません。
