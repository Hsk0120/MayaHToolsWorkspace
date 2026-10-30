# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya の poleVectorConstraint を扱う。"""

from .pointConstraint import PointConstraint



class PoleVectorConstraint(PointConstraint):
    """RP IKハンドルのポールベクトルをコンストレイントするラッパー。

    Maya の poleVectorConstraint は pointConstraint の派生型なので、基底も PointConstraint にする。
    """
