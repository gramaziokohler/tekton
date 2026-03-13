# Decoupled Architecture: Signal Flow & Logic

Dieses Dokument erklärt den Datenfluss vom **TIMBER-Modell** (COMPAS Timber) zum **Dlubal-Modell** (RFEM/RSTAB) über die neue neutrale Zwischenschicht.

---

## 1. Phase: Translation (Agnostisch)
**File:** `src/ct_dlubal/translator.py`

Der Translator hat keine Ahnung von Dlubal-gRPC. Er arbeitet rein geometrisch und konvertiert das Framework-spezifische `TimberModel` in ein neutrales `StructuralModel`.

**Was passiert hier?**
1.  **Segmentierung:** Da Dlubal Balken an Knotenpunkten physikalisch teilen muss, rufen wir `timber_model.create_beam_structural_segments()` auf. (Hier nutzen wir unseren `FixedGenerator`, um Bugs in der Library zu umgehen).
2.  **Neutrales Modell anlegen:** Ein leeres `StructuralModel` Objekt wird erstellt.
3.  **Materials & Sections:**
    *   Erkennt Querschnitte (z.B. 80x100mm).
    *   Generiert Dlubal-kompatible Namen: `R_M1 80/100`.
4.  **Nodes & Members:**
    *   Erzeugt neutrale `StructuralNode` Objekte (Punkte).
    *   Erzeugt neutrale `StructuralMember` Objekte (Stäbe).
    *   **Wichtig:** Das COMPAS-Koordinatensystem (Z-Achse nach OBEN) bleibt hier noch erhalten!

```python
# Pseudo-Logik
model = StructuralModel()
for beam in timber_model.beams:
    for seg in beam.segments:
        model.add_member(
            start=seg.start, 
            end=seg.end, 
            orientation=seg.frame.yaxis # Agnostischer Vektor
        )
```

---

## 2. Phase: Mapping (Backend-Spezifisch)
**Files:** `src/ct_dlubal/dlubal/mappers/`

Wenn der `DlubalImporter` läuft, nutzt er spezialisierte **Mapper**, um neutrale Objekte in Dlubal-Protobuf-Objekte zu verwandeln.

**Was passiert hier?**
1.  **Koordinaten-Transformation:** Dlubal nutzt standardmäßig Z nach UNTEN. Der Mapper spiegelt die Z-Koordinate.
2.  **Beta-Winkel Berechnung:** Dlubal versteht keinen "Orientierungs-Vektor". Der Mapper berechnet aus dem agnostischen Y-Vektor den software-spezifischen **BETA-Winkel** relativ zur Standard-Lage des Stabs.
3.  **Material-Auflösung:** Kurznamen wie `"C24"` werden über das Dictionary in volle Dlubal-Namen übersetzt.

```python
# Pseudo-Logik im Mapper
def map_node(neutral_node):
    return Dlubal.Node(
        no=neutral_node.id, 
        x=neutral_node.x, 
        y=neutral_node.y, 
        z=-neutral_node.z # <--- Transformation!
    )
```

---

## 3. Phase: Live Push (gRPC)
**Files:** `src/ct_dlubal/dlubal/client.py` & `importer.py`

Dies ist der "Transportweg".

1.  **Connection:** `DlubalClient` öffnet die gRPC-Verbindung mit dem API-Key.
2.  **Transaction:** Alle gemappten Protobuf-Objekte werden in einer großen Liste gesammelt.
3.  **Push:** `client.create_object_list(objects)` sendet alles in einem Schwung an RFEM/RSTAB.

---

## Warum dieser Aufwand?
*   **Agnostisch:** Der Translator kann später auch für **IFC**, **SAF** oder **Abaqus** verwendet werden, ohne den Code zu ändern. Nur die Mapper sind backend-spezifisch.
*   **Testbar:** Wir können das `StructuralModel` in einem Unit-Test prüfen, ohne Dlubal installiert haben zu müssen.
