import maya.cmds as cmds
import maya.api.OpenMaya as om2

print("MFnReference exists:", hasattr(om2, "MFnReference"))
print(dir(om2.MFnReference))
