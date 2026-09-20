"""Camera shape wrapper."""

import maya.api.OpenMaya as om2

from .shape import Shape


class Camera(Shape):
    """Maya camera shape ノードのラッパー。"""

    def camera_fn(self):
        """MFnCamera を取得する。

        Returns:
            om2.MFnCamera: この camera の function set。
        """
        return om2.MFnCamera(self.dag_path())

    @property
    def focal_length(self):
        """焦点距離を取得する。

        Returns:
            float: Maya の焦点距離。
        """
        return self.camera_fn().focalLength