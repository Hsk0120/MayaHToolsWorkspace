取得時点の選択を保持する
========================

``mlib.common.Selection`` はNode・Plug・Componentを取得時点の順序で保持します。
現在選択へ自動追従せず、同じ完全名の重複は最初の1件にまとめます。
``Selection()`` は空、``Selection.capture()`` は現在選択の取得です。

.. code-block:: python

   import mlib
   from mlib.common import Selection

   saved = Selection.capture()
   explicit = Selection(["pCube1", "pCube1.translateX", "pCube1.vtx[0:2]"])
   nodes = saved.getNodes()
   groups = saved.filter("vertex").getComponents()
   for vertices in groups:
       print(vertices.shape, vertices.indices)
   saved.select(mode="replace", missing="skip")

コンポーネントは単体へ展開して保持し、``getComponents()`` でシェイプごとの集合へ戻します。
``filter`` は型に合わない対象を除外します。未知の型名では空のSelectionになります。
選び直しは ``select(mode="replace"/"add"/"remove", missing="skip"/"raise")`` を使います。
トポロジーやUVセットの変更後も同じ要素であることは保証しません。

Channel Boxの表示・選択アトリビュート照会は、利用側で ``maya.cmds.channelBox`` を使います。
必要なアトリビュートは ``node.getPlug(name)`` へ明示的に変換してください。
