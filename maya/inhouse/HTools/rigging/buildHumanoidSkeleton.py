"""一般的な人間の全身骨格(簡易プロキシメッシュ付き)をシーンに作る。

関節名は UE のマネキン / MetaHuman 風、身長約170cm の Tポーズ。実体は
``mlrig.examples.humanoid.build``。同じ名前があるときは "human2_" のような接頭辞を付けて作る。
"""

from maya import cmds


def main():
    """骨格を作り、ルート関節を選んだ状態にする。"""
    from mlrig.examples import humanoid

    prefix = ""
    index = 2
    while any(cmds.objExists(prefix+name) for name in humanoid.jointNames()):
        prefix = "human{}_".format(index)
        index += 1
    result = humanoid.build(prefix=prefix)
    print("Built a humanoid skeleton: {} joints, {} proxy meshes, root '{}'.".format(
        len(result["joints"]), len(result["meshes"]), result["root"]))


if __name__ == "__main__":
    main()
