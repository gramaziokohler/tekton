import os
from compas.geometry import Point, Frame
from compas_timber.elements import Plate
from compas_timber.model import TimberModel
from compas_timber_fea.translator import TimberToStructural

frame1 = Frame(Point(0, 0, 0), [1, 0, 0], [0, 1, 0])
plate1 = Plate(frame=frame1, x=2000, y=2000, thickness=100)

frame2 = Frame(Point(1000, 0, 1000), [0, 0, 1], [0, 1, 0])
plate2 = Plate(frame=frame2, x=2000, y=2000, thickness=100)

model = TimberModel()
model.add_element(plate1)
model.add_element(plate2)

# Oh wait, we need joints for the solver to know they connect? 
# Wait, PlateStructuralElementSolver currently doesn't rely strictly on joints, or does it? Wait, let's see model.plates from TimberModel.
try:
    translator = TimberToStructural()
    fea_model = translator.translate(model)
    print('Nodes:', len(fea_model.nodes))
    print('Surfaces:', len(fea_model.surfaces))
except Exception as e:
    import traceback
    traceback.print_exc()