"""Timber materials with real physical properties.

A grade name like "C24" is a key, not a material. RFEM happens to resolve
names against its own library, but SAF wants the numbers in the sheet, and
OpenSees/Abaqus have no library at all - without real properties in the
neutral model, those backends are impossible. So the neutral model carries the
numbers, and name-resolution stays a Dlubal-adapter convenience.

Units: moduli and strengths in MPa (N/mm2), densities in kg/m3 - the domain's
working units, stated per field. Strengths matter for design checks only, not
for the FEA itself; stiffness and density drive the analysis.

Preset values: glulam per EN 14080:2013. Solid timber per the widely published
EN 338 table (2009 edition); the 2016 revision adjusted some tension strengths
(e.g. C24 f_t0k 14 -> 14.5) - review the strength rows against the current
edition before wiring up design checks. Stiffness and density are stable
across editions.
"""

from dataclasses import dataclass
from dataclasses import replace


@dataclass
class Material:
    name: str
    standard: str = ""
    density_mean: float = 0.0   # kg/m3
    density_k: float = 0.0      # kg/m3, characteristic
    E0_mean: float = 0.0        # MPa, parallel to grain
    E0_k: float = 0.0           # MPa, 5th percentile
    E90_mean: float = 0.0       # MPa, perpendicular to grain
    G_mean: float = 0.0         # MPa
    f_mk: float = 0.0           # MPa, bending strength (characteristic)
    f_t0k: float = 0.0          # MPa, tension parallel
    f_c0k: float = 0.0          # MPa, compression parallel
    f_vk: float = 0.0           # MPa, shear
    # Timber grillage convention: Poisson effects are neglected in member
    # models; plate models get their coupling from the layup, not from here.
    poisson: float = 0.0

    @classmethod
    def from_preset(cls, name, **overrides):
        """Return a copy of a preset, optionally with single properties overridden.

        >>> Material.from_preset("C24", E0_mean=10500)
        """
        preset = PRESETS.get(name)
        if preset is None:
            available = ", ".join(sorted(PRESETS))
            raise KeyError(f"No material preset {name!r}. Available presets: {available}")
        return replace(preset, **overrides)

    @classmethod
    def resolve(cls, value, fallback="C24"):
        """Turn whatever the model carries into a Material.

        Accepts a Material (passed through), a known grade name (preset), or an
        unknown name - which keeps its name but borrows the fallback's physical
        properties, honestly labelled in ``standard`` so the assumption is
        visible in every export instead of silently wrong.
        """
        if isinstance(value, cls):
            return value
        name = str(value)
        if name in PRESETS:
            return replace(PRESETS[name])
        borrowed = PRESETS[fallback]
        return replace(borrowed, name=name, standard=f"unknown grade - properties assumed as {fallback} ({borrowed.standard})")

    @property
    def is_assumed(self):
        return "assumed" in self.standard


def _solid(name, density_mean, density_k, E0_mean, E0_k, E90_mean, G_mean, f_mk, f_t0k, f_c0k, f_vk):
    return Material(
        name=name, standard="EN 338",
        density_mean=density_mean, density_k=density_k,
        E0_mean=E0_mean, E0_k=E0_k, E90_mean=E90_mean, G_mean=G_mean,
        f_mk=f_mk, f_t0k=f_t0k, f_c0k=f_c0k, f_vk=f_vk,
    )


def _glulam(name, density_mean, density_k, E0_mean, E0_k, E90_mean, G_mean, f_mk, f_t0k, f_c0k, f_vk):
    return Material(
        name=name, standard="EN 14080:2013",
        density_mean=density_mean, density_k=density_k,
        E0_mean=E0_mean, E0_k=E0_k, E90_mean=E90_mean, G_mean=G_mean,
        f_mk=f_mk, f_t0k=f_t0k, f_c0k=f_c0k, f_vk=f_vk,
    )


#: Grade name -> preset. Values: see module docstring for edition caveats.
PRESETS = {
    # Solid softwood, EN 338:      rho_m rho_k E0     E0k   E90  G    fm  ft0   fc0   fv
    "C14": _solid("C14", 350, 290, 7000, 4700, 230, 440, 14, 8.0, 16.0, 3.0),
    "C16": _solid("C16", 370, 310, 8000, 5400, 270, 500, 16, 10.0, 17.0, 3.2),
    "C18": _solid("C18", 380, 320, 9000, 6000, 300, 560, 18, 11.0, 18.0, 3.4),
    "C24": _solid("C24", 420, 350, 11000, 7400, 370, 690, 24, 14.0, 21.0, 4.0),
    "C30": _solid("C30", 460, 380, 12000, 8000, 400, 750, 30, 18.0, 23.0, 4.0),
    # Glulam, EN 14080:2013:         rho_m rho_k E0     E0k    E90  G    fm  ft0   fc0   fv
    "GL24h": _glulam("GL24h", 420, 385, 11500, 9600, 300, 650, 24, 19.2, 24.0, 3.5),
    "GL24c": _glulam("GL24c", 400, 365, 11000, 9100, 300, 650, 24, 17.0, 21.5, 3.5),
    "GL28h": _glulam("GL28h", 460, 425, 12600, 10500, 300, 650, 28, 22.3, 28.0, 3.5),
    "GL28c": _glulam("GL28c", 420, 390, 12500, 10400, 300, 650, 28, 19.5, 24.0, 3.5),
    "GL30c": _glulam("GL30c", 430, 390, 13000, 10800, 300, 650, 30, 19.5, 24.5, 3.5),
    "GL32h": _glulam("GL32h", 490, 440, 14200, 11800, 300, 650, 32, 25.6, 32.0, 3.5),
}
