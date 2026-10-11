"""Maya向けモジュラーリギングパッケージ。

リグ構築機能を追加するためのパッケージ入口です。
"""

from .definition import JointSpec, LayerSpec, RigDefinition, limb_definition


def build_spline(name="spine01", joint_count=7, control_count=4, length=10.0, axis="y"):
    """背骨・尻尾用のFK＋Spline IKモジュールを生成する。

    Args:
        name (str): 一意なモジュール名。
        joint_count (int): 末端を含む骨数。
        control_count (int): カーブコントロール数。
        length (float): 現在単位での全長。
        axis (str): 初期配置方向x/y/z。

    Returns:
        SplineRig: 作成したモジュール。
    """
    from .splineRig import SplineRig

    return SplineRig.create(name, joint_count, control_count, length, axis)


def build_skirt(
    name="skirt01", driver_count=4, chain_count=16, joints_per_chain=3, radius=3.0, length=5.0
):
    """標準constraintで円周上の骨列を制御するモジュールを作成する。

    Args:
        name (str): 一意なモジュール名。
        driver_count (int): 4または8方向。
        chain_count (int): 円周の変形骨列数。
        joints_per_chain (int): 末端を含む各列の骨数。
        radius (float): 円周の半径。現在のシーン単位。
        length (float): 骨列の長さ。現在のシーン単位。

    Returns:
        SkirtRig: 作成したモジュール。
    """
    from .skirtRig import SkirtRig

    return SkirtRig.create(name, driver_count, chain_count, joints_per_chain, radius, length)


def show_layer_editor():
    """Maya GUIでサンプルモジュールとレイヤーの編集パネルを開く。

    Returns:
        LayerEditor: 表示中のウィンドウ。
    """
    from .layerEditor import LayerEditor

    return LayerEditor.show_window()


def build_limb(definition=None, backend="standard"):
    """Mayaを必要な時点で読み込み、既定では標準ノードだけでリグを構築する。

    Args:
        definition (RigDefinition | None): 省略時は検証用の3関節定義。
        backend (str): standard（既定の標準ノード）、bifrostまたはcpp。


    Returns:
        LimbRig: 構築した部位の操作用参照。
    """
    from .limb import build_limb as build

    return build(definition, backend=backend)
