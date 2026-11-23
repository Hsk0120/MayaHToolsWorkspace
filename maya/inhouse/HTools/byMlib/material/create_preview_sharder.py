"""選択シェーダーからプレビュー用 blinn を生成するツール。"""

import maya.cmds as cmds

import mlib
from mlib.decorator import undoChunk


def _connect_attr(source_plug, target_plug, force=False):
	"""接続先のロックを解除せずにアトリビュートを接続する。

	cmds.connectAttr は同じ接続が既にあると warning だけで終わるため、
	ロック中・接続済みの場合は RuntimeError にして呼び出し側へ伝える。

	Args:
		source_plug (Plug): 接続元のプラグ。
		target_plug (Plug): 接続先のプラグ。
		force (bool): 接続先の既存入力を置き換えるか。

	Raises:
		RuntimeError: 接続先がロックされている、または同じ接続が既にある場合。
	"""
	if target_plug.isLocked():
		raise RuntimeError("Attribute is locked: {0}".format(target_plug))
	if target_plug.isConnected(source_plug, destination=False):
		raise RuntimeError(
			"Already connected: {0} -> {1}".format(source_plug, target_plug)
		)
	target_plug.connect(source_plug, force=force, unlock=False)


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
		selection = mlib.ls(selection=True, long=False)
		if not selection:
			cmds.error("Select one shader.")

		shader = selection[0]
		# コンポーネント・アトリビュートの選択は、持ち主のノードで型を調べる。
		node = shader if isinstance(shader, mlib.Node) else (shader.shape if isinstance(shader, mlib.Component) else shader.getNode())
		if not node.isClassified("shader"):
			cmds.error("The selected node is not a shader.")

		return shader

	def create_preview_blinn(shader):
		"""`prv_` プレフィックス付き blinn を作成します。"""
		preview_name = "prv_{0}".format(shader.getName())
		if mlib.objExists(preview_name):
			cmds.error("A node with the same name already exists: {0}".format(preview_name))
		preview_shader = mlib.createNode("blinn", name=preview_name, asShader=True)
		preview_shader.getPlug("eccentricity").set(0)
		return preview_shader

	def transfer_input_connections(source_shader, target_shader):
		"""指定属性の入力接続を複製し transparency も補完接続します。"""
		transferred_count = 0

		# 基本属性の入力接続を対応表に従って移植する。
		for source_attr, target_attr in attribute_mapping.items():
			source_plug = source_shader.getPlug(source_attr)
			# cmds.listConnections と同じく、子(colorR など)だけの接続は数えない。
			target_plug = target_shader.getPlug(target_attr)

			source_inputs = source_plug.getConnections(destination=False, skipConversionNodes=True, checkChildren=False)

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
		color_plug = source_shader.getPlug("color")
		color_inputs = color_plug.getConnections(destination=False, skipConversionNodes=True, checkChildren=False)

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

		color_input_node = color_inputs[0].getNode()
		if not mlib.objExists(color_input_node):
			cmds.warning(
				"transparency was not connected because {0} does not exist.".format(
					color_input_node
				)
			)
			return transferred_count

		if not color_input_node.hasAttr("outTransparency"):
			cmds.warning(
				"transparency was not connected because {0}.outTransparency does not exist.".format(
					color_input_node
				)
			)
			return transferred_count

		_connect_attr(
			color_input_node.getPlug("outTransparency"),
			target_shader.getPlug("transparency"),
			force=True,
		)
		transferred_count += 1

		return transferred_count

	source_shader = get_selected_shader()

	# blinn の作成と接続の移植を1回の Undo で戻せるようにまとめる。
	with undoChunk("createPreviewShader"):
		preview_shader = create_preview_blinn(source_shader)
		transferred_count = transfer_input_connections(source_shader, preview_shader)

	print(
		"Created: {0} / connections transferred: {1}".format(
			preview_shader,
			transferred_count,
		)
	)


if __name__ == "__main__":
	main()
