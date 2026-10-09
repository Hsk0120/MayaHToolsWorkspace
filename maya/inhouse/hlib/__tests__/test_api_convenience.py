"""便利メソッドと要素参照の統合検証。"""
import unittest
import maya.cmds as cmds
import maya.api.OpenMaya as om2
import hlib
from hlib.maths import Matrix, Transformation


class ConvenienceTests(unittest.TestCase):
    """独立シーンで接続・Undo・DAGパスを確認する。"""

    def setUp(self):
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)

    def test_alias_key_undo(self):
        node = hlib.createNode('transform')
        plug = node.tx
        self.assertIs(plug.setAlias('travel'), plug)
        self.assertEqual(cmds.aliasAttr(str(plug), q=True), 'travel')
        cmds.undo()
        self.assertFalse(cmds.aliasAttr(str(plug), q=True))
        self.assertIs(plug.setAlias(), plug)
        self.assertIs(plug.setKey(t=3, v=12), plug)
        self.assertEqual(cmds.keyframe(str(plug), q=True, vc=True), [12])
        cmds.undo()
        self.assertFalse(cmds.keyframe(str(plug), q=True, kc=True))

    def test_sparse_brackets(self):
        node = hlib.createNode('transform')
        array = node.addAttr('samples', at='double', multi=True)
        element = array[8]
        self.assertEqual(array.get(), {})
        element.set(80)
        array[3].set(30)
        self.assertEqual([p.get() for p in array], [30, 80])
        self.assertEqual(array.get(), {3:30, 8:80})
        self.assertEqual(node.getPlug("translate")[0], node.tx)
        self.assertEqual(cmds.getAttr(str(node.getPlug("translate"))), [(0.0, 0.0, 0.0)])
        message = node.addAttr('links', at='message', multi=True)
        other = hlib.createNode('transform')
        cmds.connectAttr(str(other.message), str(message[4]))
        self.assertEqual(message[4].getSource().getNode(), other)

    def test_matrix_interop(self):
        matrix = Matrix(translate=(2,3,4), scale=(2,3,4))
        value = matrix.asTransformation()
        self.assertIsInstance(value, Transformation)
        self.assertTrue(Matrix(value).isEquivalent(matrix))
        self.assertTrue(Matrix.fromTransformation(value).isEquivalent(matrix))
        self.assertTrue(Matrix.fromTransformation(om2.MTransformationMatrix(matrix)).isEquivalent(matrix))
        node = hlib.createNode('transform')
        node.getPlug('offsetParentMatrix').set(value)
        self.assertTrue(node.getPlug('offsetParentMatrix').get().isEquivalent(matrix))

    def test_compound_brackets_and_cmds_boundary(self):
        node = hlib.createNode('transform')
        compound = node.getPlug("translate")
        self.assertEqual(compound[0], node.tx)
        self.assertEqual(compound['translateX'], node.tx)
        self.assertEqual(compound['tx'], node.tx)
        self.assertEqual(list(compound), [node.tx, node.ty, node.tz])
        for index in (-1, 3):
            with self.assertRaises(IndexError):
                compound[index]
        for index in (True, 1.5, slice(None)):
            with self.assertRaises(TypeError):
                compound[index]
        with self.assertRaises(AttributeError):
            compound['missing']
        compound['ty'].set(4)
        self.assertEqual(cmds.getAttr(str(compound)), [(0,4,0)])
        self.assertIs(hlib.getAttr(compound), compound)
        self.assertEqual(tuple(hlib.getAttr(compound).get()), (0,4,0))
        cmds.undo()
        self.assertEqual(compound[1].get(), 0)
        blend = hlib.createNode('blendMatrix')
        blend.getPlug('target')[3]['weight'].set(0.25)
        self.assertEqual(blend.getPlug('target')[3]['weight'].get(), 0.25)
        node.ty.setLocked(True)
        self.assertEqual(compound.set((1,2,3), safe=True), 1)
        self.assertEqual(tuple(compound.get()), (1,0,3))

    def test_instances_and_traversal(self):
        root = hlib.createNode('transform', name='root')
        a = hlib.createNode('transform', name='a', parent=root)
        b = hlib.createNode('transform', name='b', parent=root)
        c = hlib.createNode('transform', name='c', parent=a)
        shape = hlib.createNode('mesh', parent=b)
        self.assertEqual([str(n) for n in root.iterBreadthFirst()], ['root','a','b','c'])
        self.assertEqual([str(n) for n in root.iterDepthFirst()], ['root','a','c','b'])
        self.assertEqual(len(list(root.iterBreadthFirst(shapes=True))), 5)
        shape.getPlug("intermediateObject").set(True)
        self.assertEqual(len(list(root.iterBreadthFirst(shapes=True))), 4)
        cmds.parent(str(c), str(b), add=True)
        self.assertEqual(len(c.getInstances()), 2)
        self.assertEqual(len(c.getInstances(noSelf=True)), 1)
        self.assertEqual(len(c.getParents()), 2)
        self.assertEqual(len(c.getParents(indirect=True)), 2)
        self.assertEqual(len(list(root.iterBreadthFirst())), 5)
        self.assertNotEqual(c.getInstances()[0].getFullPath(), c.getInstances()[1].getFullPath())

    def test_animation_layers(self):
        node = hlib.createNode('transform')
        self.assertEqual(node.tx.getAnimLayers(), [])
        first = cmds.animLayer('first', attribute=str(node.tx))
        second = cmds.animLayer('second', attribute=str(node.tx))
        base = cmds.animLayer(q=True, root=True)
        self.assertEqual(node.tx.getAnimLayers(), [second, first, base])
        for layer in (first, second, base):
            cmds.animLayer(layer, e=True, selected=False)
        cmds.animLayer(first, e=True, selected=True)
        self.assertEqual(node.tx.getAnimLayers(selected=True), [first, base])
        self.assertEqual(node.tx.getAnimLayers(selected=True, exact=True), [first])
        cmds.animLayer(first, e=True, attribute=str(node.ry))
        self.assertEqual(node.ry.getAnimLayers(), [first, base])

    def test_underworld_traversal(self):
        surface = cmds.nurbsPlane(ch=False)[0]
        shape = cmds.listRelatives(surface, s=True, f=True)[0]
        cmds.curveOnSurface(shape, d=1, uv=[(0.1,0.1),(0.9,0.9)])
        node = hlib.getNode(surface)
        self.assertEqual(len(list(node.iterBreadthFirst())), 1)
        for traversal in (node.iterBreadthFirst, node.iterDepthFirst):
            self.assertEqual(len(list(traversal(underWorld=True))), 2)
            paths = [n.getFullPath() for n in traversal(shapes=True, underWorld=True)]
            self.assertEqual(len(paths), 4)
            self.assertIn('->', paths[-1])

    def test_layer_proxy_mute_pairblend(self):
        node = hlib.createNode('transform')
        layer = cmds.animLayer('layer', attribute=str(node.tx))
        base = cmds.animLayer(q=True, root=True)
        proxy_node = hlib.createNode('transform')
        cmds.addAttr(str(proxy_node), ln='proxyValue', proxy=str(node.tx))
        self.assertEqual(proxy_node.proxyValue.getAnimLayers(), [layer, base])
        cmds.mute(str(node.tx))
        self.assertEqual(node.tx.getAnimLayers(), [layer, base])
        cmds.mute(str(node.tx), disable=True, force=True)
        source = node.tx.getSourceWithConversion()
        blend = hlib.createNode('pairBlend')
        cmds.disconnectAttr(str(source), str(node.tx))
        cmds.connectAttr(str(source), str(blend.inTranslateX1))
        cmds.connectAttr(str(blend.outTranslateX), str(node.tx))
        self.assertEqual(node.tx.getAnimLayers(), [layer, base])
        blend.translateXMode.set(2)
        self.assertEqual(node.tx.getAnimLayers(), [base])


if __name__ == '__main__':
    unittest.main()
