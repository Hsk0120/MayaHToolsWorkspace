import maya.cmds as cmds

if __name__ == "__main__":
    objs = cmds.ls(sl=True)

    for obj in objs:
        cmds.bakePartialHistory(obj, prePostDeformers=True)