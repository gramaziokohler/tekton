import argparse
import sys
import logging
from compas.data import json_load
from ct_dlubal.importer import DlubalImporter

def main():
    parser = argparse.ArgumentParser(description="Import COMPAS Timber model to Dlubal RSTAB/RFEM.")
    parser.add_argument("input", help="Path to COMPAS Timber JSON file.")
    parser.add_argument("--app", choices=["rstab", "rfem"], default="rstab", help="Target Dlubal application.")
    parser.add_argument("--name", default="COMPAS Timber Import", help="Model name in Dlubal.")
    parser.add_argument("--key", help="Dlubal API key (optional if configured in Dlubal).")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging.")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    try:
        model = json_load(args.input)
    except Exception as e:
        print(f"Error loading COMPAS model: {e}")
        sys.exit(1)
        
    importer = DlubalImporter(app_type=args.app, api_key=args.key)
    
    try:
        importer.run(model, model_name=args.name)
    except Exception as e:
        print(f"Error during import: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

