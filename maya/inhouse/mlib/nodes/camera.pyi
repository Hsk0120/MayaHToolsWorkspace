# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""Maya のカメラシェイプを扱う。"""

import maya.api.OpenMaya as om2
from .shape import Shape



class Camera(Shape):
    """Maya camera shape ノードのラッパー。"""
    def mfn(self) -> om2.MFnCamera:
        """この camera で最も具体的な om2 function set を取得する。

        呼び出すたびに新しい ``om2.MFnCamera`` を保持する DAG パスから作る。

        Returns:
            om2.MFnCamera: この camera の function set。
        """
        ...
    def getFocalLength(self) -> float:
        """焦点距離を取得する。

        Returns:
            float: Maya の焦点距離。
        """
        ...
