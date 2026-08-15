"""選択ノードのみで回転オーバーラップを KawaiiPhysics 風にベイクするツール。"""

import maya.cmds as cmds


def _selected_chain_nodes():
	"""選択順を保った transform/joint 一覧を返す。"""
	selection = cmds.ls(orderedSelection=True, l=True) or []
	if not selection:
		selection = cmds.ls(sl=True, l=True) or []
	chain = []
	for node in selection:
		node_type = cmds.nodeType(node)
		if node_type not in ("transform", "joint"):
			continue
		if node in chain:
			continue
		chain.append(node)
	return chain


def _as_world_translate_vector(node):
	"""ノードの world translate を [x, y, z] で返す。"""
	return list(cmds.xform(node, q=True, ws=True, t=True))


def _as_world_rotate_vector(node):
	"""ノードの world rotate を [x, y, z] で返す。"""
	return list(cmds.xform(node, q=True, ws=True, rotation=True))


def _as_local_rotate_vector(node):
	"""ノードの local rotate を [x, y, z] で返す。"""
	return [
		cmds.getAttr("{0}.rotateX".format(node)),
		cmds.getAttr("{0}.rotateY".format(node)),
		cmds.getAttr("{0}.rotateZ".format(node)),
	]


def _set_world_rotation_with_delta(node, base_world_rotate, delta_world_euler):
	"""base の world 回転へ world 相対の回転差を合成して適用する。"""
	cmds.xform(node, ws=True, rotation=base_world_rotate)
	cmds.rotate(
		delta_world_euler[0],
		delta_world_euler[1],
		delta_world_euler[2],
		node,
		r=True,
		ws=True,
	)


def _scene_fps():
	"""Maya の time unit から現在シーンの FPS を返す。"""
	unit = cmds.currentUnit(q=True, time=True)
	if isinstance(unit, str):
		unit = unit.lower()

	# Maya の代表的な time unit を優先的に明示マップ。
	known = {
		"game": 15.0,
		"film": 24.0,
		"pal": 25.0,
		"ntsc": 30.0,
		"show": 48.0,
		"palf": 50.0,
		"ntscf": 60.0,
	}
	if unit in known:
		return known[unit]

	# 23.976fps -> "23.976fps", 120fps -> "120fps" のような任意指定に対応。
	if isinstance(unit, str) and unit.endswith("fps"):
		try:
			fps = float(unit[:-3])
			if fps > 0.0:
				return fps
		except Exception:
			pass

	return 24.0


def _v_add(a, b):
	return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def _v_sub(a, b):
	return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _v_mul(a, s):
	return [a[0] * s, a[1] * s, a[2] * s]


def _v_len(a):
	return (a[0] * a[0] + a[1] * a[1] + a[2] * a[2]) ** 0.5


def _v_safe_normalize(a):
	length = _v_len(a)
	if length <= 1e-8:
		return [0.0, 0.0, 0.0]
	return [a[0] / length, a[1] / length, a[2] / length]


def _bake_pbd_overlap_for_chain(
	chain,
	start_frame,
	end_frame,
	stiffness,
	damping,
	follow,
	substeps,
):
	"""単一チェーンへ KawaiiPhysics コア相当の回転オーバーラップをベイクする。"""
	if len(chain) < 2:
		cmds.warning("{0}: 子が無いためスキップします。".format(chain[0]))
		return 0

	# root は入力アニメを維持し、子のみオーバーラップを焼き込む。
	children = chain[1:]
	frame_list = list(range(int(start_frame), int(end_frame) + 1))

	# 先に元アニメの pose 情報を全フレーム分キャッシュする。
	base_world_pos = {}
	base_world_rot = {}
	base_local_rot = {}
	for frame in frame_list:
		cmds.currentTime(frame, e=True)
		base_world_pos[frame] = {}
		base_world_rot[frame] = {}
		base_local_rot[frame] = {}
		for node in chain:
			base_world_pos[frame][node] = _as_world_translate_vector(node)
			base_world_rot[frame][node] = _as_world_rotate_vector(node)
			base_local_rot[frame][node] = _as_local_rotate_vector(node)

	# 子ノードの既存回転キーはベイク前に削除して置換する。
	try:
		cmds.cutKey(
			children,
			at=["rotateX", "rotateY", "rotateZ"],
			time=(start_frame, end_frame),
		)
	except Exception:
		pass

	state = {}
	for node in children:
		state[node] = {
			"location": list(base_world_pos[frame_list[0]][node]),
			"prev_location": list(base_world_pos[frame_list[0]][node]),
		}

	fps = _scene_fps()
	delta_time = 1.0 / max(fps, 1e-8)
	delta_time_old = delta_time
	exponent = 1.0
	dt = delta_time / float(max(1, int(substeps)))

	for frame_index, frame in enumerate(frame_list):
		cmds.currentTime(frame, e=True)
		sim_pos = {}
		sim_pos[chain[0]] = list(base_world_pos[frame][chain[0]])
		prev_frame = frame_list[frame_index - 1] if frame_index > 0 else frame

		for i, node in enumerate(children, 1):
			parent = chain[i - 1]
			parent_sim = sim_pos[parent]
			parent_pose = base_world_pos[frame][parent]
			pose = base_world_pos[frame][node]

			loc = state[node]["location"]
			prev_loc = state[node]["prev_location"]

			vel = _v_mul(_v_sub(loc, prev_loc), 1.0 / max(delta_time_old, 1e-8))
			state[node]["prev_location"] = list(loc)

			delayed_pose = base_world_pos[prev_frame][node]
			delayed_parent_pose = base_world_pos[prev_frame][parent]
			base_location = _v_add(parent_sim, _v_sub(delayed_pose, delayed_parent_pose))

			# Kawaii コア簡略: target へのばね追従 + 減衰。
			for _ in range(max(1, int(substeps))):
				acc = _v_mul(_v_sub(base_location, loc), follow)
				vel = _v_add(vel, _v_mul(acc, dt))
				vel = _v_mul(vel, damping)
				loc = _v_add(loc, _v_mul(vel, dt))

			pull_alpha = 1.0 - ((1.0 - stiffness) ** exponent)
			loc = _v_add(loc, _v_mul(_v_sub(base_location, loc), pull_alpha))

			bone_length = _v_len(_v_sub(pose, parent_pose))
			dir_vec = _v_safe_normalize(_v_sub(loc, parent_sim))
			if bone_length > 1e-8 and _v_len(dir_vec) > 0.0:
				loc = _v_add(parent_sim, _v_mul(dir_vec, bone_length))

			state[node]["location"] = list(loc)
			sim_pos[node] = list(loc)

		for i, node in enumerate(children, 1):
			# tip は parent->self ベクトル、その他は self->child ベクトルで回転差を作る。
			if i < len(chain) - 1:
				next_node = chain[i + 1]
				pose_vec = _v_sub(base_world_pos[frame][next_node], base_world_pos[frame][node])
				sim_vec = _v_sub(sim_pos[next_node], sim_pos[node])
			else:
				parent = chain[i - 1]
				pose_vec = _v_sub(base_world_pos[frame][node], base_world_pos[frame][parent])
				sim_vec = _v_sub(sim_pos[node], sim_pos[parent])
			if _v_len(pose_vec) <= 1e-8 or _v_len(sim_vec) <= 1e-8:
				rx, ry, rz = base_local_rot[frame][node]
				cmds.setAttr("{0}.rotateX".format(node), rx)
				cmds.setAttr("{0}.rotateY".format(node), ry)
				cmds.setAttr("{0}.rotateZ".format(node), rz)
				cmds.setKeyframe(node, at=["rotateX", "rotateY", "rotateZ"], t=(frame,))
				continue

			delta_world_euler = cmds.angleBetween(euler=True, v1=pose_vec, v2=sim_vec)
			base_wr = base_world_rot[frame][node]
			_set_world_rotation_with_delta(node, base_wr, list(delta_world_euler))
			cmds.setKeyframe(node, at=["rotateX", "rotateY", "rotateZ"], t=(frame,))

		delta_time_old = delta_time

	try:
		cmds.keyTangent(
			children,
			at=["rotateX", "rotateY", "rotateZ"],
			itt="auto",
			ott="auto",
			time=(start_frame, end_frame),
		)
	except Exception:
		pass

	return len(children)


def create_pbd_overlap_rotation_bake(
	start_frame=None,
	end_frame=None,
	stiffness=0.08,
	damping=0.92,
	follow=0.35,
	substeps=2,
):
	"""選択ノードのみを対象に KawaiiPhysics コア風の回転揺れ遅れをベイクする。

	子ノードは既存回転キーを範囲削除したうえで、速度積分 + 減衰 +
	pose への復帰(stiffness) + 骨長復元を使って遅延を計算し、rotate に焼き込む。
	root は入力アニメを維持する。コリジョン/外力/制約は対象外。

	Args:
		start_frame (int | None): 開始フレーム。None の場合は再生レンジ最小値。
		end_frame (int | None): 終了フレーム。None の場合は再生レンジ最大値。
		stiffness (float): pose への復帰強度。大きいほど形状維持が強い。
		damping (float): 速度保持率。0 に近いほど減衰強、1 に近いほど残る。
		follow (float): target 位置へ引くばね強度。大きいほど追従が速い。
		substeps (int): 内部積分回数。シーン FPS から算出した秒 dt を分割して積分する。

	Returns:
		dict: 実行サマリ。
	"""
	chain = _selected_chain_nodes()
	if len(chain) < 2:
		cmds.warning("transform/joint を2つ以上、根本→先端の順で選択してください。")
		return {"processed_roots": 0, "baked_nodes": 0}

	if start_frame is None:
		start_frame = int(cmds.playbackOptions(q=True, minTime=True))
	if end_frame is None:
		end_frame = int(cmds.playbackOptions(q=True, maxTime=True))

	if end_frame < start_frame:
		cmds.warning("終了フレームが開始フレームより前です。")
		return {"processed_roots": 0, "baked_nodes": 0}

	substeps = max(1, int(substeps))
	damping = max(0.0, min(float(damping), 0.9999))
	stiffness = max(0.0, min(float(stiffness), 0.9999))

	total_baked = _bake_pbd_overlap_for_chain(
		chain=chain,
		start_frame=start_frame,
		end_frame=end_frame,
		stiffness=float(stiffness),
		damping=damping,
		follow=float(follow),
		substeps=substeps,
	)
	processed = 1

	print(
		"Kawaii-core overlap rotation bake 完了: roots={0}, bakedNodes={1}, range={2}-{3}, substeps={4}".format(
			processed,
			total_baked,
			start_frame,
			end_frame,
			substeps,
		)
	)

	return {
		"processed_roots": processed,
		"baked_nodes": total_baked,
		"start_frame": start_frame,
		"end_frame": end_frame,
		"substeps": substeps,
	}


if __name__ == "__main__":
	# 既定は「揺れ遅れを強める」寄りに設定（Kawaii コア簡略）。
	create_pbd_overlap_rotation_bake(
		stiffness=0.08,
		damping=0.92,
		follow=0.35,
		substeps=8,
	)
