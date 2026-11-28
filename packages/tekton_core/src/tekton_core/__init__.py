__author__ = ["Lorin Wiedemeier"]
__copyright__ = "Gramazio Kohler Research"
__license__ = "MIT License"
__email__ = "wiedemeier@arch.ethz.ch"
__version__ = "0.1.0"

from .translator import TimberToStructural
from .core.model import StructuralMemberResult
from .core.model import StructuralNodeResult
from .core.model import StructuralResultSet
from .core.model import StructuralSurfaceResult

__all__ = ["StructuralMemberResult", "StructuralNodeResult", "StructuralResultSet", "StructuralSurfaceResult", "TimberToStructural"]
