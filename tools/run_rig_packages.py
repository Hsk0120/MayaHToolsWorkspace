"""隔離したmayapyでmlrig・mlib_bifrost・標準プラグイン連携を検証する。"""

import argparse
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def main():
    """テスト用standaloneを初期化し、選択したスイートを実行する。

    Returns:
        int: 成功時0、テスト失敗時1。
    Note:
        各テストは新規シーンへ切り替える。Maya GUI内へ送信しない。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite',choices=('all','mlib','setups','bifrost','native','standard','matrix-plugins'),default='all')
    args = parser.parse_args()
    sys.path.insert(0,str(ROOT/'maya/inhouse'))
    import maya.standalone
    # 初期化済みGUIで呼ばれた場合、この呼出が失敗し、シーン操作に進まない。
    maya.standalone.initialize(name='python')
    try:
        files=[]
        rig='mlrig/__tests__/'
        if args.suite in ('all','matrix-plugins'):
            files.append(rig+'unit/root/test_backends_matrix.py')
        if args.suite in ('all','mlib'):
            from maya import cmds
            # 2022のこの環境ではFBX .modがない。テストプロセスだけ絶対パスでロードする。
            plugin=Path(sys.executable).resolve().parents[1]/'plug-ins/fbx/plug-ins/fbxmaya.mll'
            if plugin.is_file() and not cmds.pluginInfo('fbxmaya',q=True,loaded=True):
                cmds.loadPlugin(str(plugin),quiet=True)
            files += ['mlib/__tests__/unit/'+name+'.py' for name in (
                'root/test_init_typing','cmds/test_init_basics','root/test_init_layout','common/test_scriptJobs_rigUse')]
        if args.suite in ('all','setups'):
            # setups/ の各モジュールのテストと、例・セットアップ全体の確認をフォルダーから集める。
            inhouse=ROOT/'maya/inhouse'
            for folder in ('unit/setups','unit/examples'):
                files += sorted(path.relative_to(inhouse).as_posix() for path in (inhouse/rig/folder).glob('test_*.py')
                                if path.name!='test_softIK_tiny.py')
            files += [rig+'unit/root/test_setupSamples.py', rig+'integration/test_workflow_foundations.py',
                      rig+'integration/test_workflow_setupSecondary.py']
        if args.suite in ('all','bifrost','native','standard'):
            files.append(rig+'unit/root/test_definition.py')
        if args.suite in ('all','bifrost'):
            files += ['mlib_bifrost/__tests__/unit/nodes/test_graph.py','mlib_bifrost/__tests__/unit/plugs/test_port.py',
                      rig+'unit/root/test_limb.py']
        if args.suite in ('all','native'):
            files.append(rig+'unit/root/test_backends_native.py')
        if args.suite in ('all','standard'):
            files += [rig+'unit/setups/test_softIK_tiny.py', rig+'unit/root/test_limb_ikOrigin.py']
            files += [rig+name+'.py' for name in (
                'integration/test_workflow_standard', 'unit/root/test_spaceLayer', 'unit/root/test_twistLayer',
                'unit/root/test_bendLayer', 'unit/root/test_drivenLayer', 'unit/root/test_skirtRig',
                'unit/root/test_followLayer', 'unit/root/test_secondaryLayer', 'unit/root/test_splineRig',
                'integration/test_workflow_stretch', 'integration/test_workflow_controls')]
        suite=unittest.TestSuite()
        for index,file in enumerate(files):
            spec=importlib.util.spec_from_file_location('rig_test_'+str(index),ROOT/'maya/inhouse'/file)
            module=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    finally:
        maya.standalone.uninitialize()


if __name__=='__main__':
    sys.exit(main())
