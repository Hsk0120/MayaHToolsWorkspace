"""距離型の2入力を加算する(Maya 2026以降の型名は ``addDL``)。"""

from .node import Node


class AddDoubleLinear(Node):
    """距離型の2入力を加算する。

    Maya 2026で ``addDoubleLinear`` は ``addDL`` へ改名された。mlibはどの版でも両方の型名を
    受け付け(``createNode``・``ls(type=)``・``isType``)、どちらの型のノードもこのクラスで扱う。
    ``getType()`` はその版の実際の型名を返す。``AddDL`` は同じクラスの別名。
    """


AddDL = AddDoubleLinear  #: Maya 2026以降の型名に合わせた別名(同じクラス)。
