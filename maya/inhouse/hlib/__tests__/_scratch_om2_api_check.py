import maya.api.OpenMaya as om2

try:
    import maya.api.OpenMayaAnim as oma2
except ImportError as e:
    oma2 = None
    print("oma2 import failed:", e)

print("om2.MFnSet exists:", hasattr(om2, "MFnSet"))
print("om2.MNamespace exists:", hasattr(om2, "MNamespace"))
print("om2.MFnMatrixData exists:", hasattr(om2, "MFnMatrixData"))
print("om2.MItDag exists:", hasattr(om2, "MItDag"))
print("om2.MGlobal.getActiveSelectionList exists:", hasattr(om2.MGlobal, "getActiveSelectionList"))
if oma2:
    print("oma2.MFnGeometryFilter exists:", hasattr(oma2, "MFnGeometryFilter"))
    print("oma2.MAnimControl exists:", hasattr(oma2, "MAnimControl"))

# Check MFnMesh.getPoint / getUV
print("MFnMesh.getPoint:", hasattr(om2.MFnMesh, "getPoint"))
print("MFnMesh.getUV:", hasattr(om2.MFnMesh, "getUV"))
print("MFnNurbsCurve.cvPosition:", hasattr(om2.MFnNurbsCurve, "cvPosition"))

# Check MPlug numeric getters
print("MPlug.asDouble:", hasattr(om2.MPlug, "asDouble"))
print("MPlug.asMObject:", hasattr(om2.MPlug, "asMObject"))
