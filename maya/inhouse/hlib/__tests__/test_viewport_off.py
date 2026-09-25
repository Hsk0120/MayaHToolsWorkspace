"""画面停止のバッチ動作とベイクのUndoを検証する。"""
import sys
import unittest
from unittest.mock import patch
import maya.cmds as cmds
import hlib
from hlib.decorators import viewport_off


class ViewportOffTest(unittest.TestCase):
    def test_batch_context_and_decorator(self):
        calls = []

        @viewport_off()
        def operation(value):
            calls.append(value)
            return value

        with patch.object(cmds, 'about', return_value=True), patch.object(
                cmds, 'paneLayout', side_effect=AssertionError('Unexpected UI call')):
            with viewport_off():
                self.assertEqual(operation(1), 1)
                self.assertEqual(operation(2), 2)
            with self.assertRaisesRegex(RuntimeError, 'original'):
                with viewport_off():
                    raise RuntimeError('original')
        self.assertEqual(calls, [1, 2])

    def test_bake_results_undo(self):
        node = cmds.createNode('transform')
        try:
            cmds.setKeyframe(node, attribute='tx', time=1, value=0)
            cmds.setKeyframe(node, attribute='tx', time=4, value=3)
            before = cmds.keyframe(node, attribute='tx', query=True, timeChange=True)
            hlib.bakeResults(node, time=(1, 4), attribute='tx', simulation=True)
            self.assertEqual(cmds.keyframe(node, attribute='tx', query=True, timeChange=True), [1, 2, 3, 4])
            cmds.undo()
            self.assertEqual(cmds.keyframe(node, attribute='tx', query=True, timeChange=True), before)
        finally:
            cmds.delete(node)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
