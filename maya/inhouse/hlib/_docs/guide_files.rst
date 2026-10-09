シーンと参照ファイル
============================================================

Sceneオブジェクトと参照ファイルの取得・操作を説明します。

例は Maya の Script Editor で実行します。既存ノード名は使用するシーンに合わせてください。
最初に ``import hlib`` を実行してください。

シーンオブジェクトの取得
------------------------

.. code-block:: python

    import hlib

    current = hlib.scene()
    print(current)  # 現在のパス。未保存の場合は untitled
    other = hlib.scene("C:/project/scenes/character.ma")
    print(other)    # パスを表示するだけで、ファイルは開かない
    # other.open() # 明示的に開く場合

``isNew()`` は保持パスがNoneかを判定し、``repr(scene)`` も保持パスを表示します。
Scene は取得時のパスを保持します。現在のシーンの切替・名前変更に自動追従しません。
``new()``、``open()``、``saveAs()`` を自身で実行した場合は保持パスも更新します。
``save()``、``saveAs()``、``modified()`` は現在のシーンとパスが一致する場合のみ
使用できます。未保存シーン同士はパスで区別できません。
クラスの定義先は ``hlib.common.Scene``、名前空間クラスは ``hlib.common.Namespace`` です。

直接importする場合は ``hlib.common`` を使います。
``hlib.scene()`` など、コマンドから取得する入口は従来どおりです。

.. code-block:: python

    from hlib.common import Scene, Namespace, Plugin, Preferences, Workspace
    from hlib.common import TimeSlider, Viewport, Outliner
    from hlib.common.references import listReferences

名前空間を作成して続けて使う
----------------------------

``Namespace.create(name, parent=":")`` は作成先の完全名を返します。
既存の場合の判定も同じ完全名なので、ルートの同名を子名前空間と取り違えません。

.. code-block:: python

    from hlib.common import Namespace

    character = Namespace.create(":character")
    rig = Namespace.create("rig", parent=character)
    assert rig.name == ":character:rig"
    with rig.asCurrent():
        control = hlib.createNode("transform", name="control")

文字列の相対nameはparent配下に作成します。多段名 ``"rig:controls"`` も同じ規則です。
先頭が ``:`` の絶対nameはparentを無視してルートから解決します。
Namespaceオブジェクトも保持済みの絶対名として扱います。
parentが相対文字列の場合は現在の名前空間から解決し、既定の ``":"`` は常にルートです。
作成だけでは現在の名前空間を変更しません。存在しない親は同じUndo内で再帰作成します。
``asCurrent`` はブロック終了時に元へ戻します。

以前は単一nameの返却へparentが反映されず、相対多段name・相対parentも
ルートから解決していました。作成先と返却の一致、およびMaya標準の絶対/相対名の
解決へ変更しています。完全名を明示していた呼び出しはそのまま利用できます。

シーン情報
----------

.. code-block:: python

   from hlib.common import Scene

   scene = Scene()
   print(scene.path)  # 未保存なら None
   print(scene.modified())

参照(reference)の列挙と操作
-------------------------------

.. code-block:: python

   from hlib.common.references import listReferences

   for reference in listReferences():
       print(reference.filename(), reference.associatedNamespace(), reference.loaded())

   top_level = listReferences(top_level_only=True)  # ネストした参照を除外

   reference = listReferences()[0]
   reference.unload()
   reference.load()
   print(reference.nodes())  # 参照内のノードをラッパーで取得(アンロード中はRuntimeError)

参照ノード自体は ``hlib.nodes.Reference`` として自動解決されます
(``hlib.node("参照ノード名")`` でも取得可能)。``filename``/``namespace``/
``loaded``/``nodes``/``parentReference`` は ``MFnReference`` 経由の
読み取り専用照会、``load``/``unload``/``remove`` は Undo 対応の編集操作です。
