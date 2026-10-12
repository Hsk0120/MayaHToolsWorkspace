"""専用mayapyプロセスで読込設定と実際のノード名を検証する。"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maya/inhouse/QuickPathExplorer/python'))


def main(output_dir=None, finished=None):
    """一時シーンでネームスペース、衝突、遅延読込を検証する。"""
    import maya.standalone
    if finished is None:
        maya.standalone.initialize(name='python')
    from maya import cmds
    from qpeQt import QtWidgets
    from qpeReadOptions import ReadOptions
    from qpeHost import readFile
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    panel = ReadOptions()
    checks = []
    with tempfile.TemporaryDirectory(prefix='qpe-options-') as folder:
        path = str(Path(folder) / 'asset.ma')
        cmds.createNode('transform', name='hero')
        cmds.file(rename=path)
        cmds.file(save=True, type='mayaAscii')
        for action in ('import', 'reference'):
            cmds.file(new=True, force=True)
            fields = panel.controls[action]
            fields['mode'].setCurrentIndex(1)
            fields['name'].setText('shot:characterA')
            options = panel.fileArguments(action, path)
            readFile(path, action, options)
            assert cmds.objExists('shot:characterA:hero'), (action, options, cmds.ls(type='transform'))
            readFile(path, action, options)
            assert cmds.objExists('shot:characterA1:hero')
            fields['mergeNamespacesOnClash'].setChecked(True)
            options.update(panel.fileArguments(action, path))
            readFile(path, action, options)
            assert cmds.objExists('shot:characterA:hero1')
            checks.append(action + ': custom nested namespace / unique clash / reuse')
            cmds.file(new=True, force=True)
            fields['mode'].setCurrentIndex(2)
            options.update(panel.fileArguments(action, path))
            readFile(path, action, options)
            assert cmds.objExists('hero')
            checks.append(action + ': root namespace')
            fields['mode'].setCurrentIndex(1)
            fields['name'].setText('invalid name!')
            try:
                panel.fileArguments(action, path)
                raise AssertionError('Invalid namespace accepted')
            except ValueError:
                checks.append(action + ': invalid namespace rejected before mutation')
        cmds.file(new=True, force=True)
        fields = panel.controls['reference']
        fields['mode'].setCurrentIndex(0)
        fields['deferReference'].setChecked(True)
        cmds.file(path, reference=True, **panel.fileArguments('reference', path))
        assert not cmds.objExists('asset:hero')
        refs = [node for node in cmds.ls(type='reference') if node != 'sharedReferenceNode']
        assert refs and not cmds.referenceQuery(refs[0], isLoaded=True)
        checks.append('deferred reference creates reference without loading nodes')
        cmds.file(new=True, force=True)
    result = {'status': 'passed', 'maya': cmds.about(version=True), 'checks': checks}
    print(json.dumps(result), flush=True)
    if output_dir:
        (Path(output_dir) / 'result.json').write_text(json.dumps(result), encoding='utf-8')
    panel.close()
    if finished:
        finished(result)
    else:
        maya.standalone.uninitialize()


if __name__ == '__main__':
    main()
