# Dlubal RFEM / RSTAB (API v2) - Cheatsheet für Python

Dieses Dokument fasst die wichtigsten Fallstricke und Herangehensweisen bei der Arbeit mit der (neuen) **Dlubal API v2 (via gRPC/Protobuf)** zusammen, speziell im Kontext des `ct_dlubal` (COMPAS Timber) Importers.

---

## 1. Namensgebung fÃ¼r Querschnitte (String Parsing)

Dlubal RFEM generiert Querschnitte aus einfachen Strings. Die Abmessungen mÃ¼ssen in den meisten FÃ¤llen in **Millimetern** angegeben werden, auch wenn die Quellgeometrie (z.B. in Rhino/COMPAS) in Metern modelliert wurde. Ist der String ungÃ¼ltig formatiert, ist der Querschnitt im Programm meist unsichtbar oder fehlerhaft.

```python
# FALSCH (Meter oder falsches PrÃ¤fix)
# name = "Rect 0.1/0.2"

# RICHTIG (Millimeter mit gÃ¼ltigem Dlubal-PrÃ¤fix "Rectangle" oder "R_M1")
width_mm = 120
height_mm = 240
cs_name = f"Rectangle {width_mm}/{height_mm}" 
# oder auch f"R_M1 {width_mm}/{height_mm}" je nach Sprachpaket

# API-Objekt generieren
from dlubal.api.rfem import structure_core
cross_section = structure_core.CrossSection(
    no=1, 
    name=cs_name, 
    material=1
)
```

## 2. Material-Typen (Achtung: Versteckte Standard-Enums!)

Dies ist eine der hÃ¤ufigsten Fehlerquellen: Wenn man ein neues Material per API erzeugt, stuft Dlubal es **standardmÃ¤ÃŸig immer als Beton (CONCRETE)** ein! Wenn der Name im Katalog aber ein Holz ist (z.B. "GL24h"), schlÃ¤gt die Zuweisung bzw. interne Berechnung fehl. Man muss den Material-Typ `material_type` zwingend mit dem korrekten Flag Ã¼berschreiben!

```python
from dlubal.api.rfem import structure_core

# Enum-ID fÃ¼r Timber aus dem Protobuf-Schema extrahieren
# Meist ist TIMBER = 1, CONCRETE = 0, STEEL = 2 etc.
mat_type_timber = structure_core.Material.Descriptor().fields_by_name['material_type'].enum_type.values_by_name['MATERIAL_TYPE_TIMBER'].number

timber_material = structure_core.Material(
    no=1, 
    name="GL24h | EN 14080:2013-09", # Genauer Name aus dem aktiven Dlubal-Katalog
    material_type=mat_type_timber    # <--- ZWINGEND ERFORDERLICH!
)
```

## 3. Z-Achsen Konvention beachten (Gravity)

Im konstruktiven Ingenieurbau (sowie nativ in Dlubal RFEM) zeigt die globale Z-Achse standardmÃ¤ÃŸig **nach unten** in Richtung der Schwerkraft. Da 3D-CAD-Software (wie Rhino/COMPAS) Z klassischerweise nach oben definiert, mÃ¼ssen die Z-Koordinaten der generierten Nodes invertiert werden, damit Modelle nicht kopfÃ¼ber hÃ¤ngen.

```python
# "coordinate_3" steht fÃ¼r die Z-Achse im Dlubal-Modell
node = structure_core.Node(
    no=node_id, 
    coordinate_1=pt.x, 
    coordinate_2=pt.y, 
    coordinate_3=-pt.z  # invertieren fÃ¼r korrekte Dlubal-Darstellung
)
```

## 4. Objekte in Listen pushen (Mass-Create)

Statt Hunderte API-Aufrufe mit `app.create_object(obj)` einzeln in einer langen Schleife abzufeuern, sollte man ein Array aus allen generierten Objekten bilden und dieses per `create_object_list` senden. 
Dieses Batch-Processing lÃ¶st das Problem von gRPC Timeouts oder Blockaden und ist dramatisch schneller.

```python
objects = []

# Objekte sammeln
objects.append(timber_material)
objects.append(cross_section)
# ... for-Schleife Ã¼ber alle Nodes, Members etc. ...

# Alles in EINEM Netzwerk-Call an RFEM/RSTAB feuern:
app.create_object_list(objects)
```

## 5. Fehlersuche & Reverse Engineering (gRPC Blockaden)

Wenn man herausfinden will, welche Properties Dlubal intern genau erwartet, ist es am einfachsten:
1. Ein Objekt in RFEM hÃ¤ndisch / per GUI anzulegen.
2. Das Objekt Ã¼ber ein Python Script (mit ID/Name) auszulesen.

**Wichtig:** Wenn ein Script abstÃ¼rzt, bleibt die gRPC-Schnittstelle oft "blockiert" (Error: `RESOURCE_EXHAUSTED`). Daher sollte die Verbindung zum Dlubal-Client immer mit einem Context-Manager (z.B. einem `with`-Statement) geÃ¶ffnet werden, damit die Verbindung bei einem Crash sicher und sauber abgebaut (geclosed) wird:

```python
from dlubal.api.rfem import Application

# Safe Connection
with Application(api_key_value="dein_API_key") as app:
    # Get active material (z.B. frisch angelegt von Hand)
    mat = app.get_object(structure_core.Material, 1)
    print(mat)
```
