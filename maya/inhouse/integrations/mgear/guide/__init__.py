"""mGear ガイド取得・更新の補助関数。"""

import maya.cmds as cmds


def get_guide(is_reference=False):
    """isGearGuideを名前に含むアトリビュートを持つTransformを取得する。

    Args:
        is_reference (bool): Trueならリファレンス由来のノードも含める。

    Returns:
        list[str]: 該当するガイドのノード名。
    """
    node_list = cmds.ls(exactType="transform")
    
    guide_list = []
    for node in node_list:
        if not is_reference and cmds.referenceQuery(node, isNodeReferenced=True):
            continue
        # isGearGuide 属性を持つ transform をガイドとみなす。
        for attr in cmds.listAttr(node):
            if not "isGearGuide" in attr:
                continue
            guide_list.append(node)
    return guide_list


def update_guide():
    """mGearを呼び出してガイドを更新する。

    Raises:
        RuntimeError: mGearをimportできない場合。
    """
    try:
        from mgear.shifter import guide_template
    except ImportError as error:
        raise RuntimeError("mGear is required to update guides") from error
    guide_template.updateGuide()