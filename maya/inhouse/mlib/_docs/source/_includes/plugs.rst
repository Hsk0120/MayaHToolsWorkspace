.. raw:: html

   <pre class="mermaid">
      classDiagram
          direction TB
          class Plug
          class CompoundPlug
          class Double3Plug
          class ArrayPlug
          class MatrixPlug
          Plug <|-- CompoundPlug
          CompoundPlug <|-- Double3Plug
          Plug <|-- ArrayPlug
          Plug <|-- MatrixPlug
          click ArrayPlug href "autoapi/mlib/plugs/arrayPlug/ArrayPlug.html#mlib.plugs.arrayPlug.ArrayPlug" "mlib.plugs.arrayPlug.ArrayPlug" _self
          click CompoundPlug href "autoapi/mlib/plugs/compoundPlug/CompoundPlug.html#mlib.plugs.compoundPlug.CompoundPlug" "mlib.plugs.compoundPlug.CompoundPlug" _self
          click Double3Plug href "autoapi/mlib/plugs/double3Plug/Double3Plug.html#mlib.plugs.double3Plug.Double3Plug" "mlib.plugs.double3Plug.Double3Plug" _self
          click MatrixPlug href "autoapi/mlib/plugs/matrixPlug/MatrixPlug.html#mlib.plugs.matrixPlug.MatrixPlug" "mlib.plugs.matrixPlug.MatrixPlug" _self
          click Plug href "autoapi/mlib/plugs/plug/Plug.html#mlib.plugs.plug.Plug" "mlib.plugs.plug.Plug" _self
   </pre>
