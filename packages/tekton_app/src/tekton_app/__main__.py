import argparse
import sys
from compas.data import json_load

def main():
    parser = argparse.ArgumentParser(description='Tekton: Export COMPAS Timber models to Dlubal or SAF.')
    parser.add_argument('--gui', action='store_true', help='Start graphic user interface (GUI)')
    parser.add_argument('input', nargs='?', help='Path to the timber_model.json file')
    parser.add_argument('--output', help='Path for SAF export (ends in .xlsx)')
    parser.add_argument('--dlubal', action='store_true', help='Push directly to Dlubal live via gRPC')
    parser.add_argument('--app', default='rfem', choices=['rfem', 'rstab'], help='Dlubal application type (default: rfem)')

    args = parser.parse_args()

    # Start GUI if requested or if no arguments are provided
    if args.gui or (not args.input and len(sys.argv) == 1):
        print("Starte GUI...")
        from tekton_app.gui import run_gui

        run_gui()

    if not args.input:
        parser.print_help()
        sys.exit(1)

    print(f"Loading model: {args.input}")
    try:
        timber_model = json_load(args.input)
    except Exception as e:
        print(f"Error loading model: {e}")
        sys.exit(1)

    if args.output:
        print(f"Exporting to SAF: {args.output}")
        from tekton_saf.exporter.saf import SAFExporter
        from tekton_core.translator import TimberToStructural

        translator = TimberToStructural()
        struct_model = translator.translate(timber_model)

        exporter = SAFExporter(struct_model)
        if not exporter.export(args.output):
            sys.exit(1)

    if args.dlubal:
        print(f"Pushing to Dlubal ({args.app})...")
        from tekton_dlubal.dlubal.importer import DlubalImporter
        from tekton_core.translator import TimberToStructural

        translator = TimberToStructural()
        struct_model = translator.translate(timber_model)

        importer = DlubalImporter(app_type=args.app, delete_all=False)
        if not importer.run(struct_model):
            sys.exit(1)


if __name__ == "__main__":
    main()
