"""RigNamingRule.maに準拠する部位名と用途サフィックス。"""


def limb_names(definition):
    """生成ロールからノード名への辞書を返す。

    Args:
        definition (RigDefinition): 部位名と関節IDを持つ定義。

    Returns:
        dict[str, str]: rigは無接頭辞、他の部位は部位名を接頭辞にする。
    """
    prefix = '' if definition.name == 'rig' else definition.name + '_'
    names = {role: prefix + name for role, name in {
        'geometryGroup': 'geo_grp', 'jointGroup': 'jnt_grp',
        'controlGroup': 'ctrl_grp', 'setupGroup': 'setup_grp',
        'target': 'ik_ctrl', 'pole': 'pole_ctrl',
        'targetRotation': 'ik_rotation_grp', 'handle': 'limb_ikh',
        'effector': 'limb_eff', 'soft': 'soft_ik',
        'distance': 'ik_distance_distanceBetween',
        'softScale': 'soft_ik_multiplyDivide',
        'helperDecompose': 'helper_decomposeMatrix',
        'helperScale': 'helper_multiplyDivide',
        'targetMatrix': 'ik_multMatrix', 'targetDecompose': 'ik_decomposeMatrix',
        'footMatrix': 'foot_multMatrix', 'footDecompose': 'foot_decomposeMatrix',
        'moduleJoints': 'limb_jnt_grp', 'moduleControls': 'limb_ctrl_grp',
        'moduleSetup': 'limb_setup_grp', 'moduleGeometry': 'limb_geo_grp',
        'fkControls': 'limb_fk_ctrl_grp', 'ikControls': 'limb_ik_ctrl_grp',
        'ikSetup': 'limb_ik_setup_grp', 'softSetup': 'limb_soft_ik_setup_grp',
        'helperSetup': 'limb_helper_setup_grp',
        'moduleSet': 'limb_module_set', 'fkSet': 'limb_fk_layer_set',
        'ikSet': 'limb_ik_layer_set', 'softSet': 'limb_soft_ik_layer_set',
        'helperSet': 'limb_helper_layer_set', 'footSet': 'limb_reverse_foot_layer_set',
        'footGroup': 'reverse_foot_grp',
    }.items()}
    for index, joint in enumerate(definition.joint_order()):
        stem = prefix + joint.id
        names['joint' + str(index)] = stem + '_jnt'
        names['ik' + str(index)] = stem + '_ik_jnt'
        names['fk' + str(index)] = stem + '_ctrl'
        names['fkMatrix' + str(index)] = stem + '_fk_multMatrix'
    names['helper'] = prefix + definition.joint_order()[1].id + '_helper_jnt'
    for role in ('fk0', 'fk1', 'fk2', 'target', 'pole'):
        names[role + 'Offset'] = names[role] + '_ofs'
    for role in ('heel', 'toe', 'ball'):
        names[role] = prefix + role + '_pivot_grp'
    return names
