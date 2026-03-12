import maya.cmds as cmds
from mgear.shifter import guide_template

def get_guide(isReference=False):
    """
    シーン内のガイドを取得する関数

    args:
        isReference(bool) : リファレンスしているノードも取得するかどうか

    return:
        guide_list(list[str, str]) : ガイドをリストで取得する
    """
    node_list = cmds.ls(exactType="transform")
    
    guide_list = []
    for node in node_list:
        if not isReference and cmds.referenceQuery(node, isNodeReferenced=True):
            continue
        for attr in cmds.listAttr(node):
            if not "isGearGuide" in attr:
                continue
            guide_list.append(node)
    return guide_list
    
if __name__ == "__main__":
    guide_list = get_guide()
    cmds.select(guide_list)
    guide_template.updateGuide()