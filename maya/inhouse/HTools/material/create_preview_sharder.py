import maya.cmds as cmds


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
		selection = cmds.ls(selection=True, long=False) or []
		if not selection:
			cmds.error("シェーダーを1つ選択してください。")

		shader = selection[0]
		shader_types = set(cmds.listNodeTypes("shader") or [])
		if cmds.nodeType(shader) not in shader_types:
			cmds.error("選択ノードはシェーダーではありません。")

		return shader

	def create_preview_blinn(shader):
		preview_name = "prv_{0}".format(shader)
		if cmds.objExists(preview_name):
			cmds.error("同名ノードが既に存在します: {0}".format(preview_name))
		preview_shader = cmds.shadingNode("blinn", asShader=True, name=preview_name)
		cmds.setAttr("{0}.eccentricity".format(preview_shader), 0)
		return preview_shader

	def transfer_input_connections(source_shader, target_shader):
		transferred_count = 0

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
			cmds.connectAttr(input_plug, target_plug, force=True)
			transferred_count += 1

			if len(source_inputs) > 1:
				cmds.warning(
					"{0} には複数入力があります。先頭のみ接続しました。".format(
						source_plug
					)
				)

		# transparency は source の color 入力ノードの outTransparency を使う
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
				"{0} に入力がないため transparency は接続しませんでした。".format(
					color_plug
				)
			)
			return transferred_count

		if len(color_inputs) > 1:
			cmds.warning(
				"{0} には複数入力があります。先頭のみ transparency に使用しました。".format(
					color_plug
				)
			)

		color_input_node = color_inputs[0].split(".", 1)[0]
		if not cmds.objExists(color_input_node):
			cmds.warning(
				"{0} が存在しないため transparency は接続しませんでした。".format(
					color_input_node
				)
			)
			return transferred_count

		if not cmds.attributeQuery("outTransparency", node=color_input_node, exists=True):
			cmds.warning(
				"{0}.outTransparency が無いため transparency は接続しませんでした。".format(
					color_input_node
				)
			)
			return transferred_count

		cmds.connectAttr(
			"{0}.outTransparency".format(color_input_node),
			"{0}.transparency".format(target_shader),
			force=True,
		)
		transferred_count += 1

		return transferred_count

	source_shader = get_selected_shader()
	preview_shader = create_preview_blinn(source_shader)

	transferred_count = transfer_input_connections(source_shader, preview_shader)

	print(
		"作成完了: {0} / 接続移植: {1}".format(
			preview_shader,
			transferred_count,
		)
	)


main()