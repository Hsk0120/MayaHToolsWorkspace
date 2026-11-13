"""Open this file in VS Code and press Ctrl+Shift+B. No scene changes."""
from pathlib import Path
import sys

import maya.cmds as cmds


def main():
    if cmds.about(batch=True):
        raise RuntimeError('Run this test in Maya GUI using Ctrl+Shift+B.')

    print('\n' + '=' * 60)
    print('[VS Code -> Maya] Connection test: SUCCESS')
    print('Maya version :', cmds.about(version=True))
    print('Python       :', sys.version.split()[0])
    print('Executable   :', sys.executable)
    print('Script       :', Path(__file__).resolve())
    print('Scene        :', cmds.file(query=True, sceneName=True) or '(untitled)')
    selection = cmds.ls(selection=True, long=True) or []
    print('Selection    :', selection or '(none)')
    print('Scene was not modified.')
    print('=' * 60 + '\n')


if __name__ == '__main__':
    main()
