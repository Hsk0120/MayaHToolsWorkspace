.. raw:: html

   <pre class="mermaid">
      classDiagram
          direction TB
          class Matrix
          class Quaternion
          class EulerRotate
          class Vector
          class MMatrix["OpenMaya.MMatrix"]
          class MQuaternion["OpenMaya.MQuaternion"]
          class MEulerRotation["OpenMaya.MEulerRotation"]
          class MVector["OpenMaya.MVector"]
          class object
          object <|-- MMatrix
          object <|-- MQuaternion
          object <|-- MEulerRotation
          object <|-- MVector
          MMatrix <|-- Matrix
          MQuaternion <|-- Quaternion
          MEulerRotation <|-- EulerRotate
          MVector <|-- Vector
          click MMatrix href "https://help.autodesk.com/cloudhelp/2026/ENU/MAYA-API-REF/py_ref/class_open_maya_1_1_m_matrix.html" "Autodesk Python API 2.0: MMatrix" _self
          click MQuaternion href "https://help.autodesk.com/cloudhelp/2026/ENU/MAYA-API-REF/py_ref/class_open_maya_1_1_m_quaternion.html" "Autodesk Python API 2.0: MQuaternion" _self
          click MEulerRotation href "https://help.autodesk.com/cloudhelp/2026/ENU/MAYA-API-REF/py_ref/class_open_maya_1_1_m_euler_rotation.html" "Autodesk Python API 2.0: MEulerRotation" _self
          click MVector href "https://help.autodesk.com/cloudhelp/2026/ENU/MAYA-API-REF/py_ref/class_open_maya_1_1_m_vector.html" "Autodesk Python API 2.0: MVector" _self
          click EulerRotate href "autoapi/mlib/maths/eulerRotate/EulerRotate.html#mlib.maths.eulerRotate.EulerRotate" "mlib.maths.eulerRotate.EulerRotate" _self
          click Matrix href "autoapi/mlib/maths/matrix/Matrix.html#mlib.maths.matrix.Matrix" "mlib.maths.matrix.Matrix" _self
          click Quaternion href "autoapi/mlib/maths/quaternion/Quaternion.html#mlib.maths.quaternion.Quaternion" "mlib.maths.quaternion.Quaternion" _self
          click Vector href "autoapi/mlib/maths/vector/Vector.html#mlib.maths.vector.Vector" "mlib.maths.vector.Vector" _self
   </pre>
