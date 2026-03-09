from ct_dlubal.exporter.formats.saf import SAFExporter

FORMATS = {
    "SAF": SAFExporter,
}

def export_file(model, filepath, format="SAF"):
    """Main entry point for file-based exports.
    
    Parameters
    ----------
    model : StructuralModel
        The structural model to be exported.
    filepath : str
        The absolute path where the file will be saved.
    format : str, optional
        The format of the file to be exported. Default is "SAF".
        Available formats: "SAF".
    
    Raises
    ------
    ValueError
        If the specified format is not supported.
    """
    fmt = format.upper()
    if fmt not in FORMATS:
        raise ValueError(f"Unsupported export format: {fmt}. Available formats: {list(FORMATS.keys())}")
        
    exporter_class = FORMATS[fmt]
    exporter = exporter_class(model)
    return exporter.export(filepath)
    
__all__ = ["export_file", "SAFExporter"]
