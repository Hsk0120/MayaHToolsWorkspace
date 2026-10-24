長名・短名の使い分け
==============================

ドキュメントの例では読みやすい長名を基本とします。
Mayaの短名も使えますが、短名はコマンドごとに異なります。

コマンドのフラグ
------------------------------

``ls``、``createNode``、``duplicate``、``select`` は、対応するMayaフラグの
長名・短名を通常の引数として列挙します。mlib直下と ``mlib.cmds`` で同じ動作です。
Mayaのhelpを実行時に解析せず、各本文で指定された値をMayaへ渡します。
各コマンドが扱える対象・モード・戻り値の制限は変わりません。
公開コマンドは、この4つと ``getNode``・``getPlug``・``delete`` の計7入口です。
``getNode/getPlug`` は参照を取得し、Mayaのコマンドフラグは受け取りません。
``delete`` は対象と独自の ``fast`` 指定だけを受け取ります。
時刻・キー等の操作は ``maya.cmds`` を直接使います。

.. list-table:: よく使う対応
   :header-rows: 1

   * - コマンド
     - 長名
     - 短名
   * - ls
     - selection / type / long
     - sl / typ / l
   * - createNode
     - name / parent
     - n / p
   * - select
     - replace / clear
     - r / cl
   * - duplicate
     - name
     - n

.. code-block:: python

   import mlib
   from maya import cmds

   selected = mlib.ls(selection=True, type="joint")
   selected_short = mlib.ls(sl=True, typ="joint")  # どちらもJoints
   node = mlib.createNode("transform", n="example")
   cmds.setKeyframe(node.getFullName(), t=1, at="tx", v=0)

``ls`` の ``type`` の短名は **typ** です。``t`` へ一律に省略はしません。
mlibのコマンドで同じフラグの長名と短名を同時に渡すと、
値が同じでも処理前に ``TypeError`` になります。直接呼ぶ ``maya.cmds`` の引数規則はMayaに従います。

.. code-block:: python

   # TypeError: 長名と短名はどちらか一方にする
   mlib.ls(selection=True, sl=True)

独自メソッドの引数
------------------------------

``Transform.addConstraint`` （Jointにも継承）は
``type`` / ``typ`` と ``maintainOffset`` / ``mo`` を受け付けます。
これはmlibが明示した別名です。``Joints.addConstraint`` や
``callEach`` にも同じ指定を渡せます。位置引数と短名による二重指定もエラーです。

.. code-block:: python

   source = mlib.createNode("transform", name="source")
   target = mlib.createNode("transform", name="target")
   target.addConstraint(source, typ="point", mo=True)

他の独自引数に短名を自動生成することはありません。
座標メソッドは ``ws`` / ``worldSpace`` に対応します。高速編集の ``fast`` は、
それぞれのAPIに記載された名前を使います。

省略と明示指定
------------------------------

長名・短名の両方を通常の引数へ列挙し、追加した別名はキーワード専用です。
引数一覧の ``_UNSET`` や ``Ellipsis`` は省略判定用の内部値です。呼出し側から値として渡しません。
省略時の実際の動作は各引数の説明に従います。FalseやNoneの明示指定と省略を区別し、
長短を両方渡した場合は値が同じでもTypeErrorにします。

Python予約語の短名 ``as`` （lsのassemblies）と ``is`` （addAttrのinternalSet）だけは、
辞書展開で指定します。長名は通常のキーワードで指定できます。

.. code-block:: python

   roots = mlib.ls(assemblies=True)
   roots_short = mlib.ls(**{"as": True})

``callEach`` は全件のPython呼出形式を先に検査します。
長短の競合や省略された必須値は各単数メソッドの本文で保持順に検査するため、
後続要素で失敗した場合、先行要素の変更は残ります。通常Undoとfastの扱いは
:doc:`bulk_collections` を参照してください。

アトリビュートの長名・短名
------------------------------

アトリビュートはMayaが持つ長名・短名のどちらでも同じ ``Plug`` を取得できます。
ユーザー定義アトリビュートの ``longName`` / ``shortName`` にも対応します。

.. code-block:: python

   node = mlib.createNode("transform")
   node.getPlug("translateX").set(10)
   print(node.getPlug("tx").get())  # 10
   print(node.translateX.get())  # 10
   print(node.tx.get())          # 10

``node.tx`` は数値ではなく ``Plug`` です。値の編集は ``node.tx.set(10)`` とします。
``node.tx = 10`` はMayaアトリビュートを編集しないため使用しません。
Python側の既存メソッドやプロパティと名前が重なるアトリビュートは ``node.getPlug("アトリビュート名")``
で明示して取得してください。
