.. raw:: html

   <pre class="mermaid">
      classDiagram
          direction TB
          class Node
          class DagNode
          class Transform
          class Joint
          class Shape
          class Mesh
          class NurbsCurve
          Node <|-- DagNode
          DagNode <|-- Transform
          Transform <|-- Joint
          DagNode <|-- Shape
          Shape <|-- Mesh
          Shape <|-- NurbsCurve
          click DagNode href "autoapi/mlib/nodes/dagNode/DagNode.html#mlib.nodes.dagNode.DagNode" "mlib.nodes.dagNode.DagNode" _self
          click Joint href "autoapi/mlib/nodes/joint/Joint.html#mlib.nodes.joint.Joint" "mlib.nodes.joint.Joint" _self
          click Mesh href "autoapi/mlib/nodes/mesh/Mesh.html#mlib.nodes.mesh.Mesh" "mlib.nodes.mesh.Mesh" _self
          click Node href "autoapi/mlib/nodes/node/Node.html#mlib.nodes.node.Node" "mlib.nodes.node.Node" _self
          click NurbsCurve href "autoapi/mlib/nodes/nurbsCurve/NurbsCurve.html#mlib.nodes.nurbsCurve.NurbsCurve" "mlib.nodes.nurbsCurve.NurbsCurve" _self
          click Shape href "autoapi/mlib/nodes/shape/Shape.html#mlib.nodes.shape.Shape" "mlib.nodes.shape.Shape" _self
          click Transform href "autoapi/mlib/nodes/transform/Transform.html#mlib.nodes.transform.Transform" "mlib.nodes.transform.Transform" _self
   </pre>
