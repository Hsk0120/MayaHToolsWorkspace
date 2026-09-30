"""参照の比較・固定hash・具象型・入力形式をMaya内で検証する。"""
import unittest
import maya.cmds as cmds
import hlib
from hlib.nodes import Node, Joint, Nodes
from hlib._core.coerce import to_names

class IdentityContractTest(unittest.TestCase):
    """名前に依存しない参照の契約。"""
    def setUp(self):
        """テスト専用シーンを作る。"""
        cmds.file(new=True, force=True)

    def test_node_hash_lifetime(self):
        """改名と削除/Undoで辞書キーを維持する。"""
        name=cmds.createNode('joint')
        a,b=Node(name),Joint(name)
        self.assertEqual(a,b)
        self.assertEqual(hash(a),hash(b))
        value=hash(a); lookup={a:42}
        a.rename('renamed')
        self.assertEqual(lookup[Node('renamed')],42)
        cmds.delete('renamed')
        self.assertEqual(hash(a),value)
        cmds.undo()
        self.assertEqual(lookup[Node('renamed')],42)

    def test_concrete_type(self):
        """具体型が違う対象を拒否する。"""
        name=cmds.createNode('transform')
        with self.assertRaises(TypeError):
            Joint(name)

    def test_plug_hash(self):
        """同じアトリビュートは短名/長名によらず同じhashを持つ。"""
        n=Node(cmds.createNode('transform'))
        a,b=n.plug('tx'),n.plug('translateX')
        self.assertEqual(a,b)
        self.assertEqual(hash(a),hash(b))
        table={a:1};n.rename('newName')
        self.assertEqual(table[n.plug('tx')],1)
        self.assertNotEqual(a,n.plug('ty'))

    def test_deleted_attribute_and_node(self):
        """削除/Undo/完全破棄でもハッシュは一定で別対象を同一視しない。"""
        n=Node(cmds.createNode('transform'))
        cmds.addAttr(n.name(),longName='sample',attributeType='double')
        a,b=n.plug('sample'),n.plug('sample')
        value=hash(a)
        cmds.deleteAttr(n.name()+'.sample')
        self.assertEqual(hash(a),value)
        self.assertEqual(a,b)
        cmds.undo()
        self.assertEqual(a,n.plug('sample'))
        cmds.delete(n.name());cmds.flushUndo()
        self.assertEqual(hash(a),value)
        self.assertFalse(a == b)
        self.assertFalse(n == Node(cmds.createNode('transform')))

    def test_mixed_edit_is_rejected_before_changes(self):
        """混在した対象の削除で最初の対象も削除されない。"""
        a=Node(cmds.createNode('transform'));b=Node(cmds.createNode('transform'))
        with self.assertRaises(TypeError):
            hlib.delete([a,b.name()])
        self.assertTrue(a.is_valid());self.assertTrue(b.is_valid())

    def test_mixed_rejected(self):
        """列全体の形式を変換前に検証する。"""
        n=Node(cmds.createNode('joint'))
        for values in ([n.name(),n],[n,n.name()]):
            with self.assertRaises(TypeError):
                to_names(iter(values))
            with self.assertRaises(TypeError):
                Nodes(values)
        self.assertEqual(len(Nodes([n,Node(n)])),1)
        self.assertEqual(to_names([n]),[n.full_name()])

    def test_instance_identity(self):
        """同じノードの別インスタンスを比較で区別する。"""
        t=cmds.polyCube()[0]; other=cmds.instance(t)[0]
        a=Node(cmds.listRelatives(t,shapes=True,fullPath=True)[0])
        b=Node(cmds.listRelatives(other,shapes=True,fullPath=True)[0])
        self.assertTrue(a.same_node(b))
        self.assertFalse(a.same_instance(b))
        self.assertNotEqual(a,b)
        self.assertEqual(hash(a),hash(b))
        cmds.delete(t)
        with self.assertRaises(RuntimeError):
            a.full_name()
        self.assertTrue(b.is_valid())

if __name__=='__main__':
    unittest.main(argv=[__file__])
