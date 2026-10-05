"""選択シェーダーからプレビュー用 blinn を生成するツール。"""

import maya.cmds as cmds
import hlib
from hlib.nodes import Node


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
		if Node(shader).type() not in shader_types:
			cmds.error("The selected node is not a shader.")

		return shader

	def create_preview_blinn(shader):
		"""`prv_` プレフィックス付き blinn を作成します。"""
		preview_name = "prv_{0}".format(shader)
		if cmds.objExists(preview_name):
			cmds.error("A node with the same name already exists: {0}".format(preview_name))
		preview_shader = hlib.createShader("blinn", name=preview_name).name()
		Node(preview_shader).plug("eccentricity").set(0)
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
			hlib.getPlug(input_plug).connectTo(target_plug, force=True, unlock=False)
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

		if not Node(color_input_node).hasAttr("outTransparency"):
			cmds.warning(
				"transparency was not connected because {0}.outTransparency does not exist.".format(
					color_input_node
				)
			)
			return transferred_count

		Node(color_input_node).plug("outTransparency").connectTo(
			"{0}.transparency".format(target_shader),
			force=True, unlock=False,
		)
		transferred_count += 1

		return transferred_count

	source_shader = get_selected_shader()
	preview_shader = create_preview_blinn(source_shader)

	transferred_count = transfer_input_connections(source_shader, preview_shader)

	print(
		"Created: {0} / connections transferred: {1}".format(
			preview_shader,
			transferred_count,
		)
	)


main()