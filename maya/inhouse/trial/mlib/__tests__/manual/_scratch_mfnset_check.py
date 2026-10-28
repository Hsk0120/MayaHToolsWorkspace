import maya.cmds as cmds
import maya.api.OpenMaya as om2

for n in ("scratchSetT1", "scratchSetT2", "scratchSetCube", "scratchSetTest"):
    if cmds.objExists(n):
        cmds.delete(n)

t1 = cmds.createNode("transform", name="scratchSetT1")
t2 = cmds.createNode("transform", name="scratchSetT2")
cube = cmds.polyCube(name="scratchSetCube", constructionHistory=False)[0]
set_name = cmds.sets([t1, t2], name="scratchSetTest")
cmds.sets(cube + ".vtx[0:2]", add=set_name)

sel = om2.MSelectionList()
sel.add(set_name)
mobject = sel.getDependNode(0)
fn = om2.MFnSet(mobject)
members = fn.getMembers(False)
print("members count:", members.length())
for i in range(members.length()):
    try:
        dag, comp = members.getComponent(i)
        print(i, "dag:", dag.fullPathName() if dag.isValid() else None, "comp isNull:", comp.isNull())
        if not comp.isNull():
            it = om2.MFnSingleIndexedComponent(comp)
            print("   comp indices:", list(it.getElements()) if hasattr(it, "getElements") else "n/a")
    except Exception as e:
        print(i, "error:", e)
    try:
        plug = members.getPlug(i)
        print(i, "plug:", plug.name())
    except Exception:
        pass

print("cmds result:", cmds.sets(set_name, query=True))

print("isMember t1:", fn.isMember(sel.getDependNode(0)))  # wrong obj on purpose to check signature
try:
    sel_t1 = om2.MSelectionList()
    sel_t1.add(t1)
    print("isMember(t1 mobject):", fn.isMember(sel_t1.getDependNode(0)))
except Exception as e:
    print("isMember error:", e)

cmds.delete(t1, t2, cube, set_name)
