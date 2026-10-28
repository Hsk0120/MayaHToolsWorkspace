.. raw:: html

   <pre class="mermaid">
      classDiagram
          direction TB
          class Component
          class PointComponent
          class Vertex
          class CV
          class Edge
          class Face
          class UV
          Component <|-- PointComponent
          PointComponent <|-- Vertex
          PointComponent <|-- CV
          Component <|-- Edge
          Component <|-- Face
          Component <|-- UV
          click CV href "autoapi/mlib/components/cv/CV.html#mlib.components.cv.CV" "mlib.components.cv.CV" _self
          click Component href "autoapi/mlib/components/component/Component.html#mlib.components.component.Component" "mlib.components.component.Component" _self
          click Edge href "autoapi/mlib/components/edge/Edge.html#mlib.components.edge.Edge" "mlib.components.edge.Edge" _self
          click Face href "autoapi/mlib/components/face/Face.html#mlib.components.face.Face" "mlib.components.face.Face" _self
          click PointComponent href "autoapi/mlib/components/pointComponent/PointComponent.html#mlib.components.pointComponent.PointComponent" "mlib.components.pointComponent.PointComponent" _self
          click UV href "autoapi/mlib/components/uv/UV.html#mlib.components.uv.UV" "mlib.components.uv.UV" _self
          click Vertex href "autoapi/mlib/components/vertex/Vertex.html#mlib.components.vertex.Vertex" "mlib.components.vertex.Vertex" _self
   </pre>
