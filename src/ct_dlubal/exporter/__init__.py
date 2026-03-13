from .formats.saf import SAFExporter
# from .formats.ifc import IFCExporter

class StructuralExporter:
    """Orchestrierungs-Klasse für verschiedene Export-Formate des StructuralModel."""
    
    def __init__(self, structural_model):
        self.model = structural_model

    def to_saf(self, filepath):
        """Exportiert das Modell in das SAF (Structural Analysis Format / Excel)."""
        exporter = SAFExporter(self.model)
        return exporter.export(filepath)

# For backward compatibility or functional usage
FORMATS = {
    "SAF": SAFExporter,
}

def export_file(model, filepath, format="SAF"):
    """Main entry point for file-based exports."""
    fmt = format.upper()
    if fmt not in FORMATS:
        raise ValueError(f"Unsupported export format: {fmt}. Available formats: {list(FORMATS.keys())}")
        
    exporter_class = FORMATS[fmt]
    exporter = exporter_class(model)
    return exporter.export(filepath)
    
__all__ = ["export_file", "SAFExporter", "StructuralExporter"]
