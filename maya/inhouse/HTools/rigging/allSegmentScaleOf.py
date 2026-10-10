"""全ジョイントの segmentScaleCompensate を無効化するツール。"""

import maya.cmds as cmds


def main():
    """シーン内ジョイントの segmentScaleCompensate を一括で OFF にします。"""
    joints = cmds.ls(type='joint') or []

    for j in joints:
        if cmds.attributeQuery('segmentScaleCompensate', node=j, exists=True):
            cmds.setAttr('{}.segmentScaleCompensate'.format(j), 0)

    print(u'Turned off segmentScaleCompensate on {} joints.'.format(len(joints)))

if __name__ == '__main__':
    main()