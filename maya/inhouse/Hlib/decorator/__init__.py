import maya.standalone
import maya.cmds as cmds

from .undo import undo_chunk, undoable

def maya_standalone(func):
    """
    mayaをスタンドアロンで起動するためのデコレータ
    """
    def wrapper(*args, **kwargs):
        try: 			
            maya.standalone.initialize()
            func(*args, **kwargs) 
        except Exception as e:
            cmds.warning(e)
        finally:
            maya.standalone.uninitialize()
    return wrapper


__all__ = [
    "maya_standalone",
    "undo_chunk",
    "undoable",
]