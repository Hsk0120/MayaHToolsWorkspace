"""シーン内のモジュール型を共通のUIから解決する。"""

import mlib


class ModuleRegistry:
    """保存済みの識別属性からモジュールを取得する。"""

    @staticmethod
    def get(root):
        """ルートに対応する操作オブジェクトを取得する。

        Args:
            root (str | Node): モジュールルート。

        Returns:
            LimbRig | SkirtRig | SplineRig: 保存されたモジュール。
        """
        from .limb import LimbRig
        from .skirtRig import SkirtRig
        from .splineRig import SplineRig

        node = mlib.nodes.Node(root)
        if node.hasAttr("mlrigControlDefinition"):
            from .controlRig import ControlRig
            from .fingerRig import FingerRig
            from .aimRig import AimRig

            return FingerRig(node) if ControlRig(node).kind() == "finger" else AimRig(node)
        if node.hasAttr("mlrigSplineDefinition"):
            return SplineRig(node)
        return SkirtRig(node) if node.hasAttr("mlrigSkirtDefinition") else LimbRig(node)

    @staticmethod
    def roots():
        """登録済みモジュールのルートを列挙する。

        Returns:
            list[str]: モジュールルート。
        """
        return [
            attr.rsplit(".", 1)[0]
            for marker in (
                "mlrigDefinition",
                "mlrigSkirtDefinition",
                "mlrigSplineDefinition",
                "mlrigControlDefinition",
            )
            for attr in (
                [item.getFullName() for item in mlib.ls("*." + marker, recursive=True)] or []
            )
        ]
