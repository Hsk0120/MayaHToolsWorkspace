"""選択したジョイントからコーンの一致度(0〜1)を出すセットアップを作るウィンドウ。

1つ目に選んだジョイントへ矢印(ドライバー)を、2つ目に選んだジョイントへコーンを
コンストレイントする。2つ目を選ばなければ、コーンはどこにも追従しない。
計算は ``mlrig.setups.ConeReader`` が標準ノードで行う。
"""

from maya import cmds

WINDOW = "coneReaderWindow"
AXES = ("x", "y", "z", "-x", "-y", "-z")


def create(*_):
    """ウィンドウの設定と選択から ConeReader を作る。"""
    from mlrig.setups import ConeReader

    selection = cmds.ls(selection=True, type="transform") or []
    if not selection:
        cmds.warning("Select the driver joint first, then optionally the joint the cone follows.")
        return
    name = cmds.textFieldGrp("coneReaderName", query=True, text=True).strip() or "coneReader"
    reader = ConeReader.create(
        driverJoint=selection[0],
        coneJoint=selection[1] if len(selection) > 1 else None,
        name=name,
        coneAngle=cmds.floatSliderGrp("coneReaderAngle", query=True, value=True),
        driverAxis=AXES[cmds.optionMenuGrp("coneReaderAxis", query=True, select=True)-1],
        size=cmds.floatFieldGrp("coneReaderSize", query=True, value1=True),
        falloff=("linear", "smooth")[cmds.optionMenuGrp("coneReaderFalloff", query=True, select=True)-1],
    )
    cmds.select(reader.cone)
    print("Created {}: rotate '{}' to aim the cone. Output: {}.weight (1 at the center, 0 at the edge)."
          .format(reader.container.getName(), reader.cone, reader.container.getName()))


def show():
    """ウィンドウを開く。"""
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW, window=True)
    cmds.window(WINDOW, title="Cone Reader", widthHeight=(420, 10), sizeable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnAttach=("both", 8))
    cmds.text(label="Select the driver joint, then (optional) the joint the cone follows.", align="left")
    cmds.textFieldGrp("coneReaderName", label="Name", text="coneReader", columnWidth2=(110, 280))
    cmds.floatSliderGrp("coneReaderAngle", label="Cone angle", field=True, minValue=1, maxValue=180,
                        value=45, columnWidth3=(110, 60, 220))
    cmds.optionMenuGrp("coneReaderAxis", label="Driver axis", columnWidth2=(110, 80))
    for axis in AXES:
        cmds.menuItem(label=axis)
    cmds.optionMenuGrp("coneReaderFalloff", label="Falloff", columnWidth2=(110, 80))
    for falloff in ("linear", "smooth"):
        cmds.menuItem(label=falloff)
    cmds.floatFieldGrp("coneReaderSize", label="Display size", value1=1.0, columnWidth2=(110, 80))
    cmds.button(label="Create from selection", height=30, command=create)
    cmds.text(label="After creating, rotate <name>_cone to aim the cone. "
                    "Change coneAngle / falloff / size on the <name> container.", align="left", wordWrap=True)
    cmds.separator(style="none", height=6)
    cmds.showWindow(WINDOW)
    cmds.window(WINDOW, edit=True, resizeToFitChildren=True)


if __name__ == "__main__":
    show()
