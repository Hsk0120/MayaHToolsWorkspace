"""専用mayapyで実行。ユーザーのMayaセッション/シーンは触らない。"""
import json
from pathlib import Path
import sys
import time

import maya.standalone
maya.standalone.initialize(name='python')
try:
    from maya import cmds
    import heditor
    from heditor import bridge
    from heditor.worker import Index
    root = Path(__file__).resolve().parents[1]
    version = str(cmds.about(version=True)).split('.')[0]
    plugin = heditor._plugin_path(version)
    plugin_name = cmds.loadPlugin(str(plugin))[0]
    assert cmds.pluginInfo(plugin_name, query=True, loaded=True)
    assert 'heditor' in cmds.pluginInfo(plugin_name, query=True, command=True)
    assert Path(cmds.moduleInfo(moduleName='HEditor', path=True)).resolve() == root
    # 実際のMayaで動的に公開された名前も補完対象になる。
    import hlib
    config = json.loads(bridge.configuration())
    assert 'createNode' in config['modules']['maya.cmds']
    index = Index(config['paths'], config['modules'])
    for source, expected in [('import maya.cmds as cmds\ncmds.cre', 'createNode'), ('import hlib\nhlib.l', 'ls')]:
        assert expected in [row['name'] for row in index.complete(source)]
    duration = []
    for _ in range(100):
        start = time.perf_counter()
        index.complete('import maya.cmds as cmds\ncmds.cre')
        duration.append((time.perf_counter()-start)*1000)
    cmds.unloadPlugin(plugin_name)
    assert plugin_name not in (cmds.pluginInfo(query=True, listPlugins=True) or [])
    Path(sys.argv[1]).write_text(json.dumps(config), encoding='utf-8')
    print('Maya {}: mod, native plugin load/unload and live exports passed; warm p95 {:.3f} ms'.format(version, sorted(duration)[94]), flush=True)
finally:
    maya.standalone.uninitialize()
