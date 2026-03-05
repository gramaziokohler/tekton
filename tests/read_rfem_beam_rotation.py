import sys
from dlubal.api.rfem import Application
from dlubal.api.rfem import structure_core

# Use the API key from your test script
api_key = "ak-REDACTED-ROTATED-2026-09"

try:
    print("Verbinde mit RFEM zur Analyse der Balken-Rotation...")
    with Application(api_key_value=api_key) as app:
        print("Verbindung erfolgreich!\n")

        print("-" * 50)
        print("Lese Member ID 11 aus...")
        try:
            # Note: For app.get_object, pass an instance of the protobuf message, not the class reference!
            mem_req = structure_core.Member(no=11)
            member = app.get_object(mem_req)
            print("\n>>> MEMBER (ID 11) GEFUNDEN:")
            
            # Print attributes that might relate to rotation
            print(f"rotation_angle: {getattr(member, 'rotation_angle', 'Nicht vorhanden')}")
            print(f"rotation_specification_type: {getattr(member, 'rotation_specification_type', 'Nicht vorhanden')}")
            print(f"is_rotated: {getattr(member, 'is_rotated', 'Nicht vorhanden')}")
            print(f"rotation_help_node: {getattr(member, 'rotation_help_node', 'Nicht vorhanden')}")
            
            print("\nKomplettes Member-Objekt:")
            print(member)
        except Exception as e:
            print(f"Member 11 konnte nicht gelesen werden: {e}")

except Exception as e:
    print(f"Fehler: {e}")
