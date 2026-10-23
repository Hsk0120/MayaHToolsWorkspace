APIの命名と責務
==============================

mlibはノード・アトリビュート・コンポーネントと数学値を扱う基礎ライブラリです。
公開関数・メソッド・プロパティはlowerCamelCase、クラスはPascalCaseです。
内部関数・内部メソッド・ローカル変数はsnake_caseを基本とします。
Maya/OpenMaya標準名、Python特殊メソッド、標準APIに合わせる名前は維持します。

公開配置
--------

``nodes``・``plugs``・``components``・``maths``・``cmds``・``common``・``core`` を公開します。
横断的な通知は ``mlib.logger``、コンテキストとデコレーターは ``mlib.decorator``、
クラスに属さない小さな汎用関数は ``mlib.util``、共通基底・型判定/登録・編集基盤は
``mlib.core`` に置きます。文書と検証素材は ``_docs`` と ``__tests__`` です。

.. code-block:: python

   import mlib
   from mlib import logger, util
   from mlib.nodes import Node, Joint
   from mlib.maths import Matrix
   from mlib.common import Selection, ScriptJobs
   from mlib.core import extensions
   from mlib.core.object import Object

``Object`` はNode・Plug・Componentの共通基底です。ルートへは再公開しません。
拡張管理は ``from mlib.core import extensions`` を使います。
旧import・旧名の互換別名はありません。

``util`` の公開関数は ``legalizeName``・``measure``・``mirrorArguments`` です。
フォルダ名で公開/非公開を区分せず、正式なAPIは明示import・``__all__``・文書で示します。
集約した内部補助は先頭 ``_`` で示し、既存の内部連携・登録プロトコル名は維持します。
``core`` の既存の型登録・拡張プロトコルは名前と意味を維持し、全helperを正式APIへ広げません。
旧 ``mlib._core`` や移動前のcommon小モジュールをimportする互換入口はありません。

参照・値・状態
--------------

* ノード参照は ``mlib.getNode(value)``、アトリビュート参照は ``getPlug``。
* 値は ``Plug.get()``、型名・状態は ``getDataType()``・``isLocked()`` 等の専用照会。
* 独自getterは ``getMatrix`` のようにgetを付けます。省略入口は再追加しません。
* 判定は ``isX`` / ``hasX`` の正式名を使い、独自のis省略入口は提供しません。
* Mayaへ問い合わせる操作はメソッド、保持する値はプロパティです。
* 独自の型変換はas、自身更新の数学操作はIt、追加アトリビュートはExtraで表します。

オブジェクト・数学層の距離はcm、角度はrad、時間は秒です。
UI単位への変換は ``get/set(uiUnits=...)`` 等の確定した引数で指定します。
Transformの姿勢とPlugのチャンネル値を混同しません。
詳細は :doc:`api_arguments` と :doc:`cmds_interop` を参照してください。

コマンドの範囲
--------------

``mlib.cmds`` とルートには ``getNode/getPlug/createNode/ls/delete/duplicate/select`` の
7入口だけを公開します。その他のMaya標準コマンドは利用側で直接使い、
必要な戻り値をNode/Plugへ変換します。具体例は :doc:`guide_commands` を参照してください。

既存対象の編集は ``Node.addAttr``、``Transform.addConstraint``、``ObjectSet.addMembers``
等のメソッドを使います。独自の汎用UI・設定ストア・型付き保存フレームワークは提供しません。
通常JSON文字列にはPython標準の ``json`` を使います。
表示色はMaya標準アトリビュートのPlugで扱います。

更新と拡張
----------

通常のシーン更新はcmdsでUndoに対応し、対応する ``fast=True`` はOM2直接更新です。
fastはUndoの有効設定を変更せず、未対応条件は更新前に拒否します。
数学値の所有権、返却型、単位、保持する公開引数は変更しません。

Nodes系の複数形、reload、拡張の自動探索は維持します。
ノード型と公開名は各 ``__init__.py`` へ明示し、複数形メソッドも通常のdefで定義します。
詳細は :doc:`bulk_collections` と :doc:`extensions` を参照してください。
