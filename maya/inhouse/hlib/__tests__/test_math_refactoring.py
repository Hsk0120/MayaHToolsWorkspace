"""数学値共有基盤の移動で保存済みpickleとreload参照を維持する。"""

import base64
import copy
import importlib
import pickle
import sys
import unittest

from hlib import maths
from hlib._core import mathValue

# 2026-10-09、共有基盤移動前のMaya2027で生成したprotocol 2のpickle。
# 別プロセスで保存した関数パスと型の値を固定し、現在のpickle往復だけで代用しない。
_LEGACY_PICKLES = [('Vector',
  'gAJjaGxpYi5tYXRocy52ZWN0b3IKX3JlYnVpbGQKcQBjaGxpYi5tYXRocy52ZWN0b3IKVmVjdG9yCnEBRz/wAAAAAAAAR0AAAAAAAAAAR0AIAAAAAAAAh3EChnEDUnEELg=='),
 ('Translate',
  'gAJjaGxpYi5tYXRocy52ZWN0b3IKX3JlYnVpbGQKcQBjaGxpYi5tYXRocy50cmFuc2xhdGUKVHJhbnNsYXRlCnEBRz/wAAAAAAAAR0AAAAAAAAAAR0AIAAAAAAAAh3EChnEDUnEELg=='),
 ('Scale',
  'gAJjaGxpYi5tYXRocy52ZWN0b3IKX3JlYnVpbGQKcQBjaGxpYi5tYXRocy5zY2FsZQpTY2FsZQpxAUc/8AAAAAAAAEdAAAAAAAAAAEdACAAAAAAAAIdxAoZxA1JxBC4='),
 ('Shear',
  'gAJjaGxpYi5tYXRocy52ZWN0b3IKX3JlYnVpbGQKcQBjaGxpYi5tYXRocy5zaGVhcgpTaGVhcgpxAUc/8AAAAAAAAEdAAAAAAAAAAEdACAAAAAAAAIdxAoZxA1JxBC4='),
 ('Quaternion',
  'gAJjaGxpYi5tYXRocy52ZWN0b3IKX3JlYnVpbGQKcQBjaGxpYi5tYXRocy5xdWF0ZXJuaW9uClF1YXRlcm5pb24KcQEoRz+5mZmZmZmaRz/JmZmZmZmaRz/TMzMzMzMzRz/szMzMzMzNdHEChnEDUnEELg=='),
 ('EulerRotate',
  'gAJjaGxpYi5tYXRocy52ZWN0b3IKX3JlYnVpbGQKcQBjaGxpYi5tYXRocy5ldWxlclJvdGF0ZQpFdWxlclJvdGF0ZQpxAShHP7mZmZmZmZpHP8mZmZmZmZpHP9MzMzMzMzNLBXRxAoZxA1JxBC4='),
 ('Matrix',
  'gAJjaGxpYi5tYXRocy52ZWN0b3IKX3JlYnVpbGQKcQBjaGxpYi5tYXRocy5tYXRyaXgKTWF0cml4CnEBKEcAAAAAAAAAAEc/8AAAAAAAAEdAAAAAAAAAAEdACAAAAAAAAEdAEAAAAAAAAEdAFAAAAAAAAEdAGAAAAAAAAEdAHAAAAAAAAEdAIAAAAAAAAEdAIgAAAAAAAEdAJAAAAAAAAEdAJgAAAAAAAEdAKAAAAAAAAEdAKgAAAAAAAEdALAAAAAAAAEdALgAAAAAAAHRxAoZxA1JxBC4=')]


class MathRefactoringTest(unittest.TestCase):
    """保存済みデータと依存順の再読み込みを検証する。"""

    def test_pre_refactoring_pickle_rebuild_paths(self):
        """移動前の7数学型のpickleを正式な再構築関数で読む。"""
        for name, payload in _LEGACY_PICKLES:
            value = pickle.loads(base64.b64decode(payload))
            self.assertIs(type(value), getattr(maths, name))
            self.assertEqual(value.__reduce_ex__(2)[0].__module__, "hlib.maths.vector")
            if name in ("Vector", "Translate", "Scale", "Shear"):
                self.assertEqual(tuple(value), (1.0, 2.0, 3.0))
            elif name == "Quaternion":
                self.assertEqual(tuple(value), (0.1, 0.2, 0.3, 0.9))
            elif name == "EulerRotate":
                self.assertEqual(tuple(value), (0.1, 0.2, 0.3))
                self.assertEqual(value.orderName, "zyx")
            else:
                self.assertEqual(value.values, tuple(float(index) for index in range(16)))

    def test_shared_helpers_reloaded_before_math_types(self):
        """依存順のreloadで新helperを全数学型へ渡し、判定cacheを再作成する。"""
        import hlib
        state_cache = mathValue._STATEFUL_TYPES
        copy.copy(maths.Vector(1, 2, 3))
        self.assertTrue(state_cache)
        hlib.reload()
        current = importlib.import_module("hlib._core.mathValue")
        self.assertIsNot(current._STATEFUL_TYPES, state_cache)
        for name in ("vector", "quaternion", "eulerRotate", "matrix"):
            module = importlib.import_module("hlib.maths." + name)
            self.assertIs(module._copy_state, current._copy_state)
            self.assertIs(module._checked_index, current._checked_index)
            self.assertIs(module._foreign_comparison, current._foreign_comparison)
        value = hlib.maths.Vector(1, 2, 3)
        self.assertEqual(tuple(copy.deepcopy(value)), (1.0, 2.0, 3.0))
        self.assertEqual(tuple(pickle.loads(pickle.dumps(value))), (1.0, 2.0, 3.0))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
