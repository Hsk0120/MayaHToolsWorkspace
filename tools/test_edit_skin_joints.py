"""専用mayapyでジョイント編集・形状維持・Undo/Redoを検証する。GUIへ送信しない。"""

import sys
from pathlib import Path


def main():
    """隔離シーンで3種類のスキニングと複数メッシュを検証する。"""
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        import maya.cmds as cmds
        import maya.api.OpenMaya as om
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "maya/inhouse"))
        from HTools.rigging import editSkinJoints as tool

        def points(mesh):
            """比較用のワールド頂点位置を取得する。"""
            return cmds.xform(mesh + ".vtx[*]", query=True, worldSpace=True, translation=True)

        for method in (0, 1, 2):
            cmds.file(new=True, force=True)
            cmds.undoInfo(state=True)
            root = cmds.joint(position=(0, 0, 0))
            child = cmds.joint(position=(0, 3, 0))
            meshes = [cmds.polyCube(height=6, subdivisionsHeight=6)[0] for _ in range(2)]
            skins = [cmds.skinCluster([root, child], mesh, toSelectedBones=True,
                                      skinMethod=method)[0] for mesh in meshes]
            reference = [points(mesh) for mesh in meshes]
            weights = [cmds.getAttr(skin + ".weightList[*].weights[*]")
                       for skin, mesh in zip(skins, meshes)]
            cmds.setAttr(root + ".rotateZ", 35)
            cmds.select(root)
            tool.beginEdit()
            assert all(cmds.getAttr(s + ".envelope") == 0 for s in skins)
            cmds.undo()
            assert not cmds.objExists(tool._SESSION)
            assert all(cmds.getAttr(s + ".envelope") == 1 for s in skins)
            cmds.redo()
            cmds.setAttr(root + ".translateX", 2)
            cmds.setAttr(root + ".jointOrientY", 25)
            cmds.setAttr(child + ".rotateX", 40)
            before = [cmds.getAttr(s + ".bindPreMatrix[0]") for s in skins]
            tool.finishEdit()
            for mesh, ref in zip(meshes, reference):
                error = max(abs(a - b) for a, b in zip(points(mesh), ref))
                assert error < 1e-5, (method, error)
            for skin, mesh, saved in zip(skins, meshes, weights):
                assert cmds.getAttr(skin + ".weightList[*].weights[*]") == saved
            cmds.undo()
            assert cmds.objExists(tool._SESSION)
            for skin, matrix in zip(skins, before):
                assert cmds.getAttr(skin + ".envelope") == 0
                assert cmds.getAttr(skin + ".bindPreMatrix[0]") == matrix
            cmds.redo()
            assert not cmds.objExists(tool._SESSION)
            for mesh, ref in zip(meshes, reference):
                assert max(abs(a - b) for a, b in zip(points(mesh), ref)) < 1e-5
            cmds.setAttr(child + ".rotateX", 65)
            assert max(abs(a - b) for a, b in zip(points(meshes[0]), reference[0])) > 0.01
            print("PASS skinMethod", method, "shape / weights / Undo / Redo / subsequent deformation")
        cmds.select(root)
        cmds.setAttr(skins[0] + ".envelope", 0.5)
        tool.beginEdit()
        cmds.currentTime(2)
        try:
            tool.finishEdit()
        except RuntimeError:
            pass
        else:
            raise AssertionError("Frame change was not rejected")
        cmds.currentTime(1)
        cmds.setAttr(root + ".scaleX", 0)
        try:
            tool.finishEdit()
        except RuntimeError:
            pass
        else:
            raise AssertionError("Singular matrix was not rejected")
        assert cmds.objExists(tool._SESSION)
        assert all(cmds.getAttr(s + ".envelope") == 0 for s in skins)
        cmds.setAttr(root + ".scaleX", 1)
        tool.finishEdit()
        assert cmds.getAttr(skins[0] + ".envelope") == 0.5
        print("PASS invalid frame / singular matrix / envelope restoration")
        # 独立したジョイント階層のスキンを同じbindPoseへ接続し、選択外の共有先を再現する。
        cmds.file(new=True, force=True)
        roots, meshes, skins = [], [], []
        for i in range(3):
            cmds.select(clear=True)
            joint = cmds.joint(position=(i * 3, 0, 0))
            mesh = cmds.polyCube()[0]
            skin = cmds.skinCluster(joint, mesh, toSelectedBones=True)[0]
            roots.append(joint)
            meshes.append(mesh)
            skins.append(skin)
        pose = cmds.listConnections(skins[0] + ".bindPose", source=True)[0]
        cmds.dagPose(roots[1], addToPose=True, name=pose)
        cmds.connectAttr(pose + ".message", skins[1] + ".bindPose", force=True)
        reference = [points(mesh) for mesh in meshes]
        cmds.setAttr(skins[1] + ".envelope", 0.5)
        cmds.setAttr(skins[1] + ".envelope", lock=True)
        cmds.select(roots[0])
        try:
            tool.beginEdit()
        except RuntimeError as exc:
            assert str(exc).isascii(), str(exc)
        else:
            raise AssertionError("Locked shared skin was not rejected")
        assert not cmds.objExists(tool._SESSION)
        assert cmds.getAttr(skins[0] + ".envelope") == 1
        cmds.setAttr(skins[1] + ".envelope", lock=False)
        assert tool.beginEdit() == sorted(skins[:2])
        assert cmds.getAttr(skins[2] + ".envelope") == 1
        cmds.undo()
        assert cmds.getAttr(skins[1] + ".envelope") == 0.5
        cmds.redo()
        cmds.setAttr(roots[0] + ".translateY", 2)
        cmds.setAttr(roots[1] + ".jointOrientZ", 30)
        tool.finishEdit()
        assert cmds.getAttr(skins[1] + ".envelope") == 0.5
        for mesh, ref in zip(meshes, reference):
            assert max(abs(a - b) for a, b in zip(points(mesh), ref)) < 1e-5
        cmds.undo()
        assert all(cmds.getAttr(skin + ".envelope") == 0 for skin in skins[:2])
        cmds.redo()
        assert not cmds.objExists(tool._SESSION)
        cmds.select(roots[0], roots[2])
        assert tool.beginEdit() == sorted(skins)
        assert len(tool._readSession()["poses"]) == 2
        tool.finishEdit()
        print("PASS shared bindPose / multiple roots and poses / unrelated skin exclusion / Undo / Redo")
        for order in range(6):
            cmds.file(new=True, force=True)
            cmds.select(clear=True)
            parent = cmds.joint(position=(0, 0, 0))
            child = cmds.joint(position=(0, 3, 0))
            cmds.setAttr(parent + ".rotateOrder", order)
            cmds.setAttr(parent + ".jointOrient", 15, -23, 42)
            cmds.setAttr(parent + ".rotateAxis", 12, 8, -17)
            cmds.setAttr(parent + ".rotate", 32, -28, 51)
            cmds.setAttr(child + ".rotate", 10, 20, 30)
            mesh = cmds.polyCube()[0]
            skin = cmds.skinCluster([parent, child], mesh, toSelectedBones=True)[0]
            pose = cmds.listConnections(skin + ".bindPose", source=True)[0]
            cmds.select(parent)
            tool.beginEdit()
            cmds.setAttr(parent + ".rotateY", 17)
            before_world = [cmds.getAttr(j + ".worldMatrix[0]") for j in (parent, child)]
            before_rotate = cmds.getAttr(parent + ".rotate")
            before_orient = cmds.getAttr(parent + ".jointOrient")
            before_bind = cmds.getAttr(skin + ".bindPreMatrix[0]")
            before_child_bind = cmds.getAttr(skin + ".bindPreMatrix[1]")
            pose_indices = cmds.getAttr(pose + ".worldMatrix", multiIndices=True)
            old_pose = [cmds.getAttr("{}.worldMatrix[{}]".format(pose, i)) for i in pose_indices]
            child_rotate = cmds.getAttr(child + ".rotate")
            tool.freezeSelectedJoints()
            new_pose = [cmds.getAttr("{}.worldMatrix[{}]".format(pose, i)) for i in pose_indices]
            assert new_pose != old_pose
            assert cmds.getAttr(parent + ".rotate") == [(0.0, 0.0, 0.0)]
            assert cmds.getAttr(child + ".rotate") == child_rotate
            assert cmds.getAttr(skin + ".bindPreMatrix[1]") == before_child_bind
            assert cmds.getAttr(skin + ".envelope") == 0
            for joint, old in zip((parent, child), before_world):
                assert max(abs(a-b) for a,b in zip(cmds.getAttr(joint + ".worldMatrix[0]"), old)) < 1e-8
            expected = list(om.MMatrix(before_world[0]).inverse())
            assert max(abs(a-b) for a,b in zip(cmds.getAttr(skin + ".bindPreMatrix[0]"), expected)) < 1e-8
            cmds.undo()
            assert cmds.getAttr(parent + ".rotate") == before_rotate
            assert cmds.getAttr(parent + ".jointOrient") == before_orient
            assert cmds.getAttr(skin + ".bindPreMatrix[0]") == before_bind
            assert [cmds.getAttr("{}.worldMatrix[{}]".format(pose, i)) for i in pose_indices] == old_pose
            cmds.redo()
            assert [cmds.getAttr("{}.worldMatrix[{}]".format(pose, i)) for i in pose_indices] == new_pose
            assert cmds.getAttr(parent + ".rotate") == [(0.0, 0.0, 0.0)]
            tool.finishEdit()
        print("PASS freeze selected only / six rotation orders / child world and channels / bind matrix / Undo / Redo")
        print("ALL PASSED")
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    main()
