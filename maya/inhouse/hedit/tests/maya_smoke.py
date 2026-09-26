"""専用mayapyで実行。ユーザーのMayaセッション/シーンは触らない。"""
import json
from pathlib import Path
import sys
import time

import maya.standalone
maya.standalone.initialize(name='python')
try:
    from maya import cmds
    import hedit
    from hedit import bridge
    from hedit.completion import Index
    root = Path(__file__).resolve().parents[1]
    version = str(cmds.about(version=True)).split('.')[0]
    plugin = hedit._plugin_path(version)
    plugin_name = cmds.loadPlugin(str(plugin))[0]
    assert cmds.pluginInfo(plugin_name, query=True, loaded=True)
    assert 'hedit' in cmds.pluginInfo(plugin_name, query=True, command=True)
    assert Path(cmds.moduleInfo(moduleName='hedit', path=True)).resolve() == root
    # 実際のMayaで動的に公開された名前も補完対象になる。
    import hlib
    config = json.loads(bridge.configuration())
    assert config['ready']
    assert 'createNode' in bridge.runtime_module('maya.cmds')[0]
    index = bridge._index
    for source, expected in [('import maya.cmds as cmds\ncmds.cre', 'createNode'), ('import hlib\nhlib.l', 'ls')]:
        assert expected in [row['name'] for row in json.loads(bridge.complete(source))['items']]
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
