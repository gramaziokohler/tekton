__author__ = ["Lorin Wiedemeier"]
__copyright__ = "Gramazio Kohler Research"
__license__ = "MIT License"
__email__ = "wiedemeier@arch.ethz.ch"
__version__ = "0.1.0"

from .importer import TimberImporter
from .exporter import export_file
from .translator import TimberToStructural

# High-level convenience functions
def push_to_dlubal(timber_model, app_type="rfem", delete_all=False):
    """Translate and push a timber model to Dlubal live."""
    importer = TimberImporter(app_type=app_type, delete_all=delete_all)
    return importer.run(timber_model)

def save_to_saf(timber_model, filepath):
    """Translate and save a timber model to a SAF file."""
    translator = TimberToStructural()
    struct_model = translator.translate(timber_model)
    
    return export_file(struct_model, filepath, format="SAF")

__all__ = ["push_to_dlubal", "save_to_saf", "TimberImporter", "TimberToStructural"]
