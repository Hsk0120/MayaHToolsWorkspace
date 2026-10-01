"""専用mayapyで実行。ユーザーのMayaセッション/シーンは触らない。

引数1のファイルへ、組み込みの名前と予約語(hedit.bridge.environment)を書き出す。
tests/ui_smoke.cpp(hedit_ui_smoke.exe)が、Maya無しの補完エンジンの検証に使う。
"""
import json
from pathlib import Path
import sys
import time

import maya.standalone
maya.standalone.initialize(name='python')
try:
    from maya import cmds
    root = Path(__file__).resolve().parents[1]
    version = str(cmds.about(version=True)).split('.')[0]
    # hedit.mod(MAYA_PLUG_IN_PATH)経由でプラグイン名から解決する。
    # hedit.pyは存在しない(src/python/の同梱ソースをinitializePlugin時にimportフックで配る)。
    plugin_name = cmds.loadPlugin('hedit')[0]
    assert cmds.pluginInfo(plugin_name, query=True, loaded=True)
    assert 'hedit' in cmds.pluginInfo(plugin_name, query=True, command=True)
    assert Path(cmds.moduleInfo(moduleName='hedit', path=True)).resolve() == root
    import hedit
    from hedit import bridge
    assert hedit.__version__ == cmds.pluginInfo(plugin_name, query=True, version=True)
    environment = json.loads(bridge.environment())
    assert 'print' in environment['builtins'] and 'return' in environment['keywords']
    assert 'createNode' in json.loads(bridge.module_info('maya.cmds'))['members']

    def complete(source):
        """C++の補完エンジンの候補名(hedit -complete)。"""
        return [row['name'] for row in json.loads(cmds.heditTest(complete=source))['items']]

    # 実際のMayaで動的に公開された名前も補完対象になる。
    import hlib
    for source, expected in [('import maya.cmds as cmds\ncmds.cre', 'createNode'), ('import hlib\nhlib.l', 'ls')]:
        assert expected in complete(source), (source, complete(source))
    duration = []
    for _ in range(100):
        start = time.perf_counter()
        complete('import maya.cmds as cmds\ncmds.cre')
        duration.append((time.perf_counter()-start)*1000)
    cmds.unloadPlugin(plugin_name)
    assert plugin_name not in (cmds.pluginInfo(query=True, listPlugins=True) or [])
    Path(sys.argv[1]).write_text(json.dumps(environment), encoding='utf-8')
    print('Maya {}: mod, native plugin load/unload and live exports passed; warm p95 {:.3f} ms'.format(version, sorted(duration)[94]), flush=True)
finally:
    maya.standalone.uninitialize()
