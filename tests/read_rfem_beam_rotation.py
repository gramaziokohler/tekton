import sys
from dlubal.api.rfem import Application
from dlubal.api.rfem import structure_core

# Use the API key from your test script
api_key = 'ak-REDACTED-ROTATED-2026-09'

try:
    print('Verbinde mit RFEM zur Analyse der Balken-Rotation...')
    with Application(api_key_value=api_key) as app:
        print('Verbindung erfolgreich!')
        print('Lese Member ID 11 aus...')
        mem_req = structure_core.Member(no=11)
        member = app.get_object(mem_req)
        print('\n>>> MEMBER (ID 11) GEFUNDEN:')
        print(f'rotation_angle: {getattr(member, "rotation_angle", "Nicht vorhanden")}')
        print(f'rotation_specification_type: {getattr(member, "rotation_specification_type", "Nicht vorhanden")}')
        print(f'has_rotation: {getattr(member, "has_rotation", "Nicht vorhanden")}')
        print(f'is_rotated: {getattr(member, "is_rotated", "Nicht vorhanden")}')
        print('\nKomplettes Member-Objekt:')
        print(member)
except Exception as e:
    print(f'Fehler: {e}')
