コマンドによるシーン編集
============================================================

選択・複製・グループ化・キー設定など、hlib直下のコマンドを使います。
引数の短縮表記は :doc:`flag_aliases` を参照してください。

例は Maya の Script Editor で実行します。既存ノード名は使用するシーンに合わせてください。
最初に ``import hlib`` を実行してください。

シーン編集コマンド
------------------

.. code-block:: python

   import hlib

   a = hlib.createNode("transform", name="a")
   b = hlib.createNode("transform", name="b")

   print(hlib.objExists(a))          # True
   copy = hlib.duplicate(a, name="aCopy")
   parent = hlib.group([a, b], name="grp")
   empty = hlib.group(name="emptyGrp", empty=True)

   hlib.delete(copy)

``duplicate``/``group`` はいずれも作成したノードのラッパーを返します。
``group`` は ``nodes`` を省略すると ``maya.cmds.group`` と同じく現在の選択を
グループ化します。空のグループを作る場合は ``empty=True`` を指定してください
（選択も無く ``empty`` も指定しない場合は Maya がエラーを送出します）。
``delete`` は複数ノードもまとめて受け付けます。

選択とアニメーション
--------------------

.. code-block:: python

   import hlib

   a = hlib.createNode("transform", name="animationA")
   b = hlib.createNode("transform", name="animationB")

   hlib.select([a, b])
   print(hlib.ls(selection=True))
   hlib.select(clear=True)

   hlib.currentTime(1)
   hlib.setKeyframe(a.plug("translateX"), value=0.0)
   hlib.currentTime(24)
   hlib.setKeyframe(a.plug("translateX"), value=10.0)

   hlib.bakeResults(a, time=(1, 24), attribute=["translateX"], simulation=True)

``select`` は ``maya.cmds.select`` と同じ引数を受け付けます。``nodes`` を省略すると
``clear=True`` のような選択操作専用のフラグだけで呼び出せます。
``setKeyframe`` はノードまたは ``Plug`` を対象にでき、``target`` を省略すると
現在の選択が対象になります。``currentTime`` は引数を省略すると現在時間を照会します。
``bakeResults`` は時間範囲を補いません。``time=(start, end)`` を明示してください。
``simulation`` の既定値はFalseです。シーン全体の評価が必要ならTrueを指定します。
GUIではベイク中のメインペインを非表示にし、終了時に元の状態へ戻します。

アトリビュートの取得・設定・接続（``getAttr``/``setAttr``/``connectAttr``/``addAttr``）は
コマンドとしては用意していません。``node.plug("attrName")`` が返す ``Plug`` の
``get()``/``set()``/``connect()``、および ``node.add_attr()`` を使ってください。

ノードのアトリビュートは、:meth:`~hlib.nodes.node.Node.plug` で取得した
:class:`~hlib.plugs.plug.Plug` オブジェクトを通して操作します。
本ドキュメントの使用例は ``plug()`` に統一しています。
``attr()`` は既存コードとの互換性のために残している ``plug()`` の別名です。
