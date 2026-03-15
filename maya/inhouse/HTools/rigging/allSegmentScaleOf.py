import maya.cmds as cmds

def main():
    joints = cmds.ls(type='joint') or []

    for j in joints:
        if cmds.attributeQuery('segmentScaleCompensate', node=j, exists=True):
            cmds.setAttr(j + '.segmentScaleCompensate', 0)

    print(u'{} 個のjointの segmentScaleCompensate をOFFにしました。'.format(len(joints)))

if __name__ == '__main__':
    main()