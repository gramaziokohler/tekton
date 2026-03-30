import pandas as pd
import json
import sys

f_dlubal = "tests/export-tests/test-model-finished-calculation-2-export-dlubal.saf"
f_ct = "tests/export-tests/test-model-finished-calculation-2-export-ctdlubal-tool.saf"

xl_dlubal = pd.ExcelFile(f_dlubal)
xl_ct = pd.ExcelFile(f_ct)

sheets_dlubal = set(xl_dlubal.sheet_names)
sheets_ct = set(xl_ct.sheet_names)

print("Dlubal sheets:", len(sheets_dlubal), sorted(list(sheets_dlubal)))
print("CT sheets:", len(sheets_ct), sorted(list(sheets_ct)))

missing_it = sheets_dlubal - sheets_ct
extra_it = sheets_ct - sheets_dlubal
print("Missing in CT:", missing_it)
print("Extra in CT:", extra_it)

common_sheets = sheets_dlubal.intersection(sheets_ct)

for sheet in sorted(list(common_sheets)):
    df_dlubal = xl_dlubal.parse(sheet)
    df_ct = xl_ct.parse(sheet)
    
    # compare columns
    cols_d = list(df_dlubal.columns)
    cols_c = list(df_ct.columns)
    
    if cols_d != cols_c:
        print(f"\n[{sheet}] Columns Differ:")
        missing_cols = set(cols_d) - set(cols_c)
        extra_cols = set(cols_c) - set(cols_d)
        if missing_cols: print(f"  Missing in CT: {missing_cols}")
        if extra_cols:   print(f"  Extra in CT: {extra_cols}")
        
    # compare shapes
    if df_dlubal.shape != df_ct.shape:
        print(f"[{sheet}] Data shapes differ. Dlubal: {df_dlubal.shape}, CT: {df_ct.shape}")
    else:
        # compare somewhat the content
        pass
