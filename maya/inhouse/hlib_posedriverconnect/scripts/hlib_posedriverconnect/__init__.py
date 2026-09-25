"""PoseDriverConnect v2を利用する任意拡張。UI・プラグインを自動起動しない。"""

HLIB_EXTENSION_API = 1


def is_available():
    """bool: PoseDriverConnectのv2モデルAPIをimportできればTrue。"""
    try:
        import epic_pose_wrangler
    except ModuleNotFoundError as exc:
        if exc.name != "epic_pose_wrangler":
            raise
        return False
    # 導入済みSDKの欠損や依存不備は未導入と区別し、hlib側に報告する。
    from epic_pose_wrangler.v2.model.api import RBFNode
    from epic_pose_wrangler.v2.model.pose_blender import UEPoseBlenderNode
    return True
