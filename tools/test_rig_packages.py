"""隔離したmayapyでhrig・hlib_bifrost・標準プラグイン連携を検証する。"""

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
    parser.add_argument('--suite',choices=('all','hlib','setups','bifrost','native','standard','matrix-plugins'),default='all')
    args = parser.parse_args()
    sys.path.insert(0,str(ROOT/'maya/inhouse'))
    import maya.standalone
    # 初期化済みGUIで呼ばれた場合、この呼出が失敗し、シーン操作に進まない。
    maya.standalone.initialize(name='python')
    try:
        files=[]
        if args.suite in ('all','matrix-plugins'):
            files.append('hrig/__tests__/test_setup_matrix_backends.py')
        if args.suite in ('all','hlib'):
            from maya import cmds
            # 2022のこの環境ではFBX .modがない。テストプロセスだけ絶対パスでロードする。
            plugin=Path(sys.executable).resolve().parents[1]/'plug-ins/fbx/plug-ins/fbxmaya.mll'
            if plugin.is_file() and not cmds.pluginInfo('fbxmaya',q=True,loaded=True):
                cmds.loadPlugin(str(plugin),quiet=True)
            files += ['hlib/__tests__/'+name+'.py' for name in (
                'test_fbx_hik','test_typing_exports','test_node_creation','test_package_layout','test_events')]
        if args.suite in ('all','setups'):
            files.append('hrig/__tests__/test_setup_matrix_follow.py')
            files += ['hrig/__tests__/test_setup_'+name+'.py' for name in ('space_switch', 'twist_distribution', 'bend_correction', 'swing_twist', 'radial_weights', 'rotation_follow', 'root_direction_limit', 'secondary', 'spline_ik', 'length_compensation', 'pose_edit', 'rig_foundations')]
        if args.suite in ('all','bifrost','native','standard'):
            files.append('hrig/__tests__/test_definition.py')
        if args.suite in ('all','bifrost'):
            files += ['hlib_bifrost/__tests__/test_graph.py','hrig/__tests__/test_limb.py']
        if args.suite in ('all','native'):
            files.append('hrig/__tests__/test_native.py')
        if args.suite in ('all','standard'):
            files += ['hrig/__tests__/test_soft_ik_tiny.py', 'hrig/__tests__/test_limb_ik_origin.py']
            files += ['hrig/__tests__/test_standard.py', 'hrig/__tests__/test_spaces.py', 'hrig/__tests__/test_twist.py', 'hrig/__tests__/test_bend.py', 'hrig/__tests__/test_driven.py', 'hrig/__tests__/test_skirt.py', 'hrig/__tests__/test_follow.py', 'hrig/__tests__/test_secondary.py', 'hrig/__tests__/test_spline.py', 'hrig/__tests__/test_stretch.py', 'hrig/__tests__/test_controls.py']
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
