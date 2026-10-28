import maya.api.OpenMayaAnim as oma2
import maya.api.OpenMaya as om2

print(dir(oma2.MAnimControl))
print()
print("currentTime methods:")
print(hasattr(oma2.MAnimControl, "currentTime"))
print(hasattr(oma2.MAnimControl, "setCurrentTime"))

t = oma2.MAnimControl.currentTime()
print("type:", type(t), t)
