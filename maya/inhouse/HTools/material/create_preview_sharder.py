"""選択シェーダーからプレビュー用 blinn を生成するツール。"""

import maya.cmds as cmds


def _connect_attr(source_plug, target_plug, force=False):
	"""接続先のロックを解除せずにアトリビュートを接続する。

	cmds.connectAttr は同じ接続が既にあると warning だけで終わるため、
	ロック中・接続済みの場合は RuntimeError にして呼び出し側へ伝える。

	Args:
		source_plug (str): 接続元のプラグ名。
		target_plug (str): 接続先のプラグ名。
		force (bool): 接続先の既存入力を置き換えるか。

	Raises:
		RuntimeError: 接続先がロックされている、または同じ接続が既にある場合。
	"""
	if cmds.getAttr(target_plug, lock=True):
		raise RuntimeError("Attribute is locked: {0}".format(target_plug))
	if cmds.isConnected(source_plug, target_plug):
		raise RuntimeError(
			"Already connected: {0} -> {1}".format(source_plug, target_plug)
		)
	cmds.connectAttr(source_plug, target_plug, force=force)


def main():
	"""選択シェーダーからプレビュー用 blinn を作成する。

	選択されたシェーダーを元に `prv_` プレフィックス付きの blinn を作成し、
	指定された属性の入力接続を移植する。

	Args:
		なし。

	Returns:
		なし。
	"""
	attribute_mapping = {
		"color": "color",
		"emissive": "incandescence",
	}

	def get_selected_shader():
		"""選択ノードからシェーダーを1件取得します。"""
		selection = cmds.ls(selection=True, long=False) or []
		if not selection:
			cmds.error("Select one shader.")

		shader = selection[0]
		shader_types = set(cmds.listNodeTypes("shader") or [])
		if cmds.nodeType(shader) not in shader_types:
			cmds.error("The selected node is not a shader.")

		return shader

	def create_preview_blinn(shader):
		"""`prv_` プレフィックス付き blinn を作成します。"""
		preview_name = "prv_{0}".format(shader)
		if cmds.objExists(preview_name):
			cmds.error("A node with the same name already exists: {0}".format(preview_name))
		preview_shader = cmds.shadingNode("blinn", asShader=True, name=preview_name)
		cmds.setAttr("{0}.eccentricity".format(preview_shader), 0)
		return preview_shader

	def transfer_input_connections(source_shader, target_shader):
		"""指定属性の入力接続を複製し transparency も補完接続します。"""
		transferred_count = 0

		# 基本属性の入力接続を対応表に従って移植する。
		for source_attr, target_attr in attribute_mapping.items():
			source_plug = "{0}.{1}".format(source_shader, source_attr)
			target_plug = "{0}.{1}".format(target_shader, target_attr)

			source_inputs = cmds.listConnections(
				source_plug,
				source=True,
				destination=False,
				plugs=True,
				skipConversionNodes=True,
			) or []

			if not source_inputs:
				continue

			input_plug = source_inputs[0]
			_connect_attr(input_plug, target_plug, force=True)
			transferred_count += 1

			if len(source_inputs) > 1:
				cmds.warning(
					"{0} has multiple inputs. Only the first one was connected.".format(
						source_plug
					)
				)

		# transparency は color 入力ノードの outTransparency を利用して補完する。
		color_plug = "{0}.color".format(source_shader)
		color_inputs = cmds.listConnections(
			color_plug,
			source=True,
			destination=False,
			plugs=True,
			skipConversionNodes=True,
		) or []

		if not color_inputs:
			cmds.warning(
				"transparency was not connected because {0} has no input.".format(
					color_plug
				)
			)
			return transferred_count

		if len(color_inputs) > 1:
			cmds.warning(
				"{0} has multiple inputs. Only the first one was used for transparency.".format(
					color_plug
				)
			)

		color_input_node = color_inputs[0].split(".", 1)[0]
		if not cmds.objExists(color_input_node):
			cmds.warning(
				"transparency was not connected because {0} does not exist.".format(
					color_input_node
				)
			)
			return transferred_count

		if not cmds.attributeQuery("outTransparency", node=color_input_node, exists=True):
			cmds.warning(
				"transparency was not connected because {0}.outTransparency does not exist.".format(
					color_input_node
				)
			)
			return transferred_count

		_connect_attr(
			"{0}.outTransparency".format(color_input_node),
			"{0}.transparency".format(target_shader),
			force=True,
		)
		transferred_count += 1

		return transferred_count

	source_shader = get_selected_shader()

	# blinn の作成と接続の移植を1回の Undo で戻せるようにまとめる。
	cmds.undoInfo(openChunk=True, chunkName="createPreviewShader")
	try:
		preview_shader = create_preview_blinn(source_shader)
		transferred_count = transfer_input_connections(source_shader, preview_shader)
	finally:
		cmds.undoInfo(closeChunk=True)

	print(
		"Created: {0} / connections transferred: {1}".format(
			preview_shader,
			transferred_count,
		)
	)


if __name__ == "__main__":
	main()
