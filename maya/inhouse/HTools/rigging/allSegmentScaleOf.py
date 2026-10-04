"""全ジョイントの segmentScaleCompensate を無効化するツール。"""

import maya.cmds as cmds
from hlib.nodes import Node


def main():
    """シーン内ジョイントの segmentScaleCompensate を一括で OFF にします。"""
    joints = cmds.ls(type='joint') or []

    for j in joints:
        if Node(j).hasAttribute('segmentScaleCompensate'):
            Node(j).plug('segmentScaleCompensate').set(0)

    print(u'{} 個のjointの segmentScaleCompensate をOFFにしました。'.format(len(joints)))

if __name__ == '__main__':
    main()