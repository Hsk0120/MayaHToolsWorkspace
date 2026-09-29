"""旧ワークスペースのuiScript用互換入口。新規コードではheditを使う。"""

def restore():
    """保存済みの旧ドックを新しい実装で復元する。旧名のドックの引き継ぎはC++(src/plugin/dock.cpp)が行う。"""
    import hedit
    hedit.restore()
