import argparse
import sys
import os
from compas.data import json_load
from ct_dlubal import push_to_dlubal, save_to_saf

def main():
    parser = argparse.ArgumentParser(description='CT_Dlubal: Export COMPAS Timber models to Dlubal or SAF.')
    parser.add_argument('--gui', action='store_true', help='Start graphic user interface (GUI)')
    parser.add_argument('input', nargs='?', help='Path to the timber_model.json file')
    parser.add_argument('--output', help='Path for SAF export (ends in .xlsx)')
    parser.add_argument('--dlubal', action='store_true', help='Push directly to Dlubal live via gRPC')
    parser.add_argument('--app', default='rfem', choices=['rfem', 'rstab'], help='Dlubal application type (default: rfem)')

    args = parser.parse_args()

    # Start GUI if requested or if no arguments are provided
    if args.gui or (not args.input and len(sys.argv) == 1):
        print("Starte GUI...")
        try:
            from tkinterdnd2 import TkinterDnD
            from ct_dlubal.gui import DlubalExportGUI
            root = TkinterDnD.Tk()
            app = DlubalExportGUI(root)
            root.mainloop()
            return
        except ImportError as e:
            # Fallback if tkinterdnd2 is not installed
            print(f"Warning: tkinterdnd2 not found, starting without Drag&Drop support. ({e})")
            from ct_dlubal.gui import DlubalExportGUI
            import tkinter as tk
            root = tk.Tk()
            app = DlubalExportGUI(root)
            root.mainloop()
            return

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
        save_to_saf(timber_model, args.output)

    if args.dlubal:
        print(f"Pushing to Dlubal ({args.app})...")
        push_to_dlubal(timber_model, app_type=args.app)

if __name__ == "__main__":
    main()




"""
# how to use:

$env:PYTHONPATH = "$PWD\src"; .\.venv_parallels\Scripts\python.exe -m ct_dlubal

"""