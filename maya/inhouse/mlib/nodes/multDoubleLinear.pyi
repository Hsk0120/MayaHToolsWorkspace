# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""距離型の2入力を乗算する(Maya 2026以降の型名は ``multDL``)。"""

from .node import Node



class MultDoubleLinear(Node):
    """距離型の2入力を乗算する。

    Maya 2026で ``multDoubleLinear`` は ``multDL`` へ改名された。mlibはどの版でも両方の型名を
    受け付け(``createNode``・``ls(type=)``・``isType``)、どちらの型のノードもこのクラスで扱う。
    ``getType()`` はその版の実際の型名を返す。``MultDL`` は同じクラスの別名。
    """
MultDL = MultDoubleLinear
