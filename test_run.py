import sys
import os

# Paths setup
sys.path.insert(0, os.path.abspath('packages/compas_timber_fea/src'))
sys.path.insert(0, os.path.abspath('../compas_timber/src'))

from compas.geometry import Point, Frame
from compas_timber.elements import Plate
from compas_timber.model import TimberModel
from compas_timber_fea.translator import TimberToStructural

print("Modules imported successfully!")

frame1 = Frame(Point(0, 0, 0), [1, 0, 0], [0, 1, 0])
plate1 = Plate(frame=frame1, length=2000, width=2000, thickness=100)

frame2 = Frame(Point(1000, 0, 1000), [0, 0, 1], [0, 1, 0])
plate2 = Plate(frame=frame2, length=2000, width=2000, thickness=100)

model = TimberModel()
model.add_element(plate1)
model.add_element(plate2)

try:
    translator = TimberToStructural()
    fea_model = translator.translate(model)
    print("Translation complete!")
    print("Nodes:", len(fea_model.nodes))
    print("Surfaces:", len(fea_model.surfaces))
    print("Surface Connections:", len(fea_model.surface_connections))
except Exception:
    import traceback
    traceback.print_exc()

