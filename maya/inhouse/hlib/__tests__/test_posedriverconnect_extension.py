"""同梱の外部SDKと対応バイナリがある場合にサンプルを実機検証する。"""
from pathlib import Path
import importlib.util
import sys
import unittest
import uuid

import maya.cmds as cmds
import hlib

ROOT = Path(__file__).resolve().parents[4]
EXTERNAL = ROOT / 'maya/external/PoseDriverConnect'


class PoseDriverConnectTest(unittest.TestCase):
    def test_external_api_and_nodes(self):
        source = EXTERNAL / 'python'
        if not source.is_dir():
            self.skipTest('PoseDriverConnect source is not installed')
        sys.path.insert(0, str(source))
        extension_source = ROOT / 'maya/inhouse/hlib_posedriverconnect/scripts'
        sys.path.insert(0, str(extension_source))
        created = []
        try:
            before_plugins = set(cmds.pluginInfo(query=True, listPlugins=True) or [])
            hlib.reload()
            self.assertEqual(set(cmds.pluginInfo(query=True, listPlugins=True) or []), before_plugins)
            state = hlib.extensions.status()['hlib_posedriverconnect']
            if importlib.util.find_spec('six') is None:
                self.assertEqual(state['state'], 'error')
                self.assertIn('six', state['reason'])
                self.assertIsNone(hlib.nodes.Node._registry.lookup('UERBFSolverNode'))
                self.assertIsNotNone(hlib.nodes.Node._registry.lookup('transform'))
                self.skipTest('Dependency-error isolation passed; PoseDriverConnect requires six')
            self.assertEqual(state['state'], 'loaded', state['reason'])
            self.assertIsNotNone(hlib.nodes.Node._registry.lookup('UERBFSolverNode'))
            binary = EXTERNAL / 'plug-ins/windows' / str(cmds.about(version=True)).split('.')[0] / 'MayaUERBFPlugin.mll'
            if not binary.exists():
                self.skipTest('Wrapper registration passed; matching Maya plugin binary not installed')
            # 本テストだけが外部標準製品のプラグインを明示的にロードする。
            cmds.loadPlugin(str(binary), quiet=True)
            solver = hlib.createNode('UERBFSolverNode', name='hlibTestRBF_' + uuid.uuid4().hex)
            created.append(solver.full_name())
            blender = hlib.createNode('UEPoseBlenderNode', name='hlibTestPose_' + uuid.uuid4().hex)
            created.append(blender.full_name())
            self.assertEqual(type(solver).__module__, 'hlib_posedriverconnect.nodes.UERBFSolverNode')
            self.assertIs(type(hlib.ls(solver.full_name())[0]), type(solver))
            self.assertEqual(solver.drivers(), [])
            self.assertIsInstance(solver.num_poses(), int)
            before = solver.radius()
            solver.set_radius(before + 10)
            self.assertAlmostEqual(solver.radius(), before + 10)
            cmds.undo()
            self.assertAlmostEqual(solver.radius(), before)
            cmds.redo()
            self.assertAlmostEqual(solver.radius(), before + 10)
            self.assertIsNone(blender.driven_transform())
            self.assertIsInstance(blender.envelope(), float)
            name = solver.full_name()
            hlib.reload()
            solver = hlib.node(name)
            self.assertTrue(isinstance(solver, hlib.nodes.Node))
            self.assertAlmostEqual(solver.radius(), before + 10)
        finally:
            for name in created:
                if cmds.objExists(name):
                    cmds.delete(name)
            sys.path.remove(str(source))
            sys.path.remove(str(extension_source))
            # テストで追加したSDKのimport状態を次のテストへ残さない。
            for name in list(sys.modules):
                if name == 'epic_pose_wrangler' or name.startswith('epic_pose_wrangler.'):
                    del sys.modules[name]
            hlib.reload()


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
