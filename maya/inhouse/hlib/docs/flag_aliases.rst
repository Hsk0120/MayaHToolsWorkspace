長名・短名の使い分け
==============================

ドキュメントの例では読みやすい長名を基本とします。
Mayaの短名も使えますが、短名はコマンドごとに異なります。

コマンドのフラグ
------------------------------

``ls``、``createNode``、``duplicate``、``group``、``select``、
``currentTime``、``setKeyframe``、``bakeResults`` は、実行中のMayaの
フラグ定義に従って短名を長名へ変換します。hlib直下と ``hlib.cmds`` で同じ動作です。
各コマンドが扱える対象・モード・戻り値の制限は変わりません。
たとえば ``currentTime()`` は時間を省略すると照会のみです。

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
   * - setKeyframe
     - time / attribute / value
     - t / at / v
   * - bakeResults
     - time / attribute / simulation
     - t / at / sm

.. code-block:: python

   import hlib

   selected = hlib.ls(selection=True, type="joint")
   selected_short = hlib.ls(sl=True, typ="joint")  # どちらもJoints
   node = hlib.createNode("transform", n="example")
   hlib.setKeyframe(node, t=1, at="tx", v=0)

``ls`` の ``type`` の短名は **typ** です。``t`` へ一律に省略はしません。
同じフラグの長名と短名を同時に渡すと、値が同じでも処理前に ``TypeError`` になります。

.. code-block:: python

   # TypeError: 長名と短名はどちらか一方にする
   hlib.ls(selection=True, sl=True)

独自メソッドの引数
------------------------------

``hlib.constraint`` と ``Transform.add_constraint`` （Jointにも継承）は
``type`` / ``typ`` と ``maintainOffset`` / ``mo`` を受け付けます。
これはhlibが明示した別名です。``Joints.add_constraint`` や
``call_each`` にも同じ指定を渡せます。位置引数と短名による二重指定もエラーです。

.. code-block:: python

   source = hlib.createNode("transform", name="source")
   target = hlib.createNode("transform", name="target")
   target.add_constraint(source, typ="point", mo=True)

他の独自引数に短名を自動生成することはありません。
たとえば既存の座標メソッドの ``ws`` や高速編集の ``fast`` は、
それぞれのAPIに記載された名前を使います。

属性の長名・短名
------------------------------

属性はMayaが持つ長名・短名のどちらでも同じ ``Plug`` を取得できます。
ユーザー定義属性の ``longName`` / ``shortName`` にも対応します。

.. code-block:: python

   node = hlib.createNode("transform")
   node.plug("translateX").set(10)
   print(node.plug("tx").get())  # 10
   print(node.translateX.get())  # 10
   print(node.tx.get())          # 10

``node.tx`` は数値ではなく ``Plug`` です。値の編集は ``node.tx.set(10)`` とします。
``node.tx = 10`` はMaya属性を編集しないため使用しません。
Python側の既存メソッドやプロパティと名前が重なる属性は ``node.plug("属性名")``
で明示して取得してください。
