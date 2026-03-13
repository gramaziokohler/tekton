from abc import ABC, abstractmethod
from ct_dlubal.core.model import StructuralModel

class BaseExporter(ABC):
    """Abstract base class for all file-based exporters."""
    
    def __init__(self, model: StructuralModel):
        self.model = model

    @abstractmethod
    def export(self, filepath: str):
        """Export the structural model to a file.
        
        Parameters
        ----------
        filepath : str
            The absolute path to the output file.
        """
        pass
