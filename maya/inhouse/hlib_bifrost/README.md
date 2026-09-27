# hlib_bifrost

Maya 2025以降・Bifrost 3.0.0.0以上向けのVNN操作ライブラリです。
import時はプラグインをロードしません。`is_available()` はロード済み対応版かを照会し、
`ensure_available()` と `Graph.create()` は必要時にロードします。
hlibの拡張検出プロトコルに対応しますが、内部VNNノードをMaya DGノードとして登録しません。

```python
from maya import cmds
from hlib_bifrost import Graph

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
