"""旧ワークスペースのuiScript用互換入口。新規コードではheditを使う。"""

def restore():
    """保存済みの旧ドックを新しい実装で復元する。"""
    from maya import cmds
    import hedit
    from hedit import docking
    if cmds.workspaceControl('HEditorDockWorkspaceControl', exists=True):
        docking.CONTROL = 'HEditorDockWorkspaceControl'
    return hedit.restore()
