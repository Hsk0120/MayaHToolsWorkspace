"""Maya のカメラシェイプを扱う。"""

import maya.api.OpenMaya as om2

from .._core.registry import node_wrapper
from .shape import Shape


@node_wrapper("camera")
class Camera(Shape):
    """Maya camera shape ノードのラッパー。"""

    def cameraFn(self):
        """MFnCamera を取得する。

        Returns:
            om2.MFnCamera: この camera の function set。
        """
        return om2.MFnCamera(self.dagPath())

    def getFocalLength(self):
        """焦点距離を取得する。

        Returns:
            float: Maya の焦点距離。
        """
        return self.cameraFn().focalLength
