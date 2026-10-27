"""Maya のカメラシェイプを扱う。"""

import maya.api.OpenMaya as om2

from .shape import Shape


class Camera(Shape):
    """Maya camera shape ノードのラッパー。"""

    def mfn(self):
        """この camera で最も具体的な om2 function set を取得する。

        呼び出すたびに新しい ``om2.MFnCamera`` を保持する DAG パスから作る。

        Returns:
            om2.MFnCamera: この camera の function set。
        """
        return om2.MFnCamera(self.mpath())

    def cameraFn(self):
        """MFnCamera を取得する。

        Returns:
            om2.MFnCamera: この camera の function set。
        """
        return om2.MFnCamera(self.mpath())

    def getFocalLength(self):
        """焦点距離を取得する。

        Returns:
            float: Maya の焦点距離。
        """
        return self.cameraFn().focalLength
