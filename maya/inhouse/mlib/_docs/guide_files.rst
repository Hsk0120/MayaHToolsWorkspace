名前空間と参照ファイル
======================

Mayaの名前空間とReferenceノードを扱います。シーンファイルの開閉・保存は利用側のmaya.cmds.fileを使います。

名前空間を作成して続けて使う
----------------------------

``Namespace.create(name, parent=":")`` は作成先の完全名を返します。
既存の場合の判定も同じ完全名なので、ルートの同名を子名前空間と取り違えません。

.. code-block:: python

    from mlib.common import Namespace

    character = Namespace.create(":character")
    rig = Namespace.create("rig", parent=character)
    assert rig.name == ":character:rig"
    with rig.asCurrent():
        control = mlib.createNode("transform", name="control")

文字列の相対nameはparent配下に作成します。多段名 ``"rig:controls"`` も同じ規則です。
先頭が ``:`` の絶対nameはparentを無視してルートから解決します。
Namespaceオブジェクトも保持済みの絶対名として扱います。
parentが相対文字列の場合は現在の名前空間から解決し、既定の ``":"`` は常にルートです。
作成だけでは現在の名前空間を変更しません。存在しない親は同じUndo内で再帰作成します。
``asCurrent`` はブロック終了時に元へ戻します。

以前は単一nameの返却へparentが反映されず、相対多段name・相対parentも
ルートから解決していました。作成先と返却の一致、およびMaya標準の絶対/相対名の
解決へ変更しています。完全名を明示していた呼び出しはそのまま利用できます。

参照(reference)の列挙と操作
-------------------------------

.. code-block:: python

   from mlib.common.references import listReferences

   for reference in listReferences():
       print(reference.getFilename(), reference.getAssociatedNamespace(), reference.isLoaded())

   top_level = listReferences(top_level_only=True)  # ネストした参照を除外

   reference = listReferences()[0]
   reference.unload()
   reference.load()
   print(reference.getNodes())  # 参照内のノードをラッパーで取得(アンロード中はRuntimeError)

参照ノード自体は ``mlib.nodes.Reference`` として自動解決されます
(``mlib.getNode("参照ノード名")`` でも取得可能)。``filename``/``namespace``/
``isLoaded``/``getNodes``/``getParentReference`` は ``MFnReference`` 経由の
読み取り専用照会、``load``/``unload``/``remove`` は Undo 対応の編集操作です。
