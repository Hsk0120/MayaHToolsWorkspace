"""シーンに依存しないリグ定義の整合性を検証する。"""

import json
import unittest
from hrig.definition import JointSpec, LayerSpec, RigDefinition, limb_definition


class DefinitionTest(unittest.TestCase):
    """永続化・依存解決・不正入力のテスト。"""

    def test_json_roundtrip(self):
        """JSON往復で型と値を保持する。"""
        definition = limb_definition()
        self.assertEqual(definition, RigDefinition.from_data(json.loads(json.dumps(definition.to_data()))))
        self.assertEqual([l.id for l in definition.active_layers(0)], ['fk', 'ik', 'space'])

    def test_cycles_and_missing_dependencies(self):
        """骨とレイヤーの循環や欠落を拒否する。"""
        with self.assertRaises(ValueError):
            RigDefinition('bad', (JointSpec('a', 'b', (0,0,0)), JointSpec('b','a',(0,0,0))), ())
        with self.assertRaises(ValueError):
            RigDefinition('bad', limb_definition().joints, (LayerSpec('a','fk',('b',)),))
        with self.assertRaises(ValueError):
            RigDefinition('bad', limb_definition().joints,
                          (LayerSpec('a','fk',('b',)), LayerSpec('b','ik',('a',))))

    def test_invalid_lod_dependency(self):
        """LODで依存だけが無効になる定義は利用時に拒否する。"""
        definition = RigDefinition('bad', limb_definition().joints,
                                   (LayerSpec('a','fk',(),1), LayerSpec('b','ik',('a',))))
        with self.assertRaises(ValueError):
            definition.active_layers(0)
        with self.assertRaises(ValueError):
            definition.active_layers(True)

    def test_invalid_values_and_schema(self):
        """非有限値、重複識別子、未知のフィールドを拒否する。"""
        with self.assertRaises(ValueError):
            JointSpec('a',None,(float('nan'),0,0))
        with self.assertRaises(ValueError):
            RigDefinition('bad',(JointSpec('a',None,(0,0,0)),)*2,())
        data=limb_definition().to_data(); data['unexpected']=1
        with self.assertRaises(TypeError):
            RigDefinition.from_data(data)


if __name__ == '__main__':
    unittest.main()
