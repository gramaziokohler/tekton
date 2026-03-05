import sys
from dlubal.api.rfem import Application
from dlubal.api.rfem import structure_core

# Use the API key from your test script
api_key = "ak-REDACTED-ROTATED-2026-09"

try:
    print("Verbinde mit RFEM...")
    # Using 'with' is important so the connection closes automatically and avoids RESOURCE_EXHAUSTED
    with Application(api_key_value=api_key) as app:
        print("Verbindung erfolgreich!\n")

        print("-" * 50)
        print("Lese MATERIALIEN aus (ID 1 bis 10)...")
        for i in range(1, 11):
            try:
                mat = app.get_object(structure_core.Material, i)
                print(f"\n>>> MATERIAL (ID {i}):")
                print(mat)
            except Exception:
                pass

        print("\n" + "-" * 50)
        print("Lese QUERSCHNITTE aus (ID 1 bis 10)...")
        for i in range(1, 11):
            try:
                cs = app.get_object(structure_core.CrossSection, i)
                print(f"\n>>> QUERSCHNITT (ID {i}):")
                print(cs)
            except Exception:
                pass

except Exception as e:
    print(f"Fehler: {e}")
