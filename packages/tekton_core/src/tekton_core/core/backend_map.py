"""What a neutral object is called inside one particular backend.

The neutral id is the project's own identity: derived from the source GUID,
stable when the model around it is edited, and never set by a backend. It is
deliberately a hash over 2^31, which makes it stable but makes it unsuitable
as a backend object number.

A backend number is the opposite: small, dense, and the backend's property. For
RFEM, Dlubal document a capacity of **999,999 objects per category** (RFEM 6
and RSTAB 9 both; RFEM 5 was 99,999), and the proto field is a signed int32.
Measured on the sticks model, every one of our 748 stable ids exceeds 99,999
and all but one exceed 999,999 - so writing them into `no` is outside the
documented capacity.

Keeping the two apart is also what makes an incremental push possible. The
engineer's model has object 17; the next push has to recognise it as the same
member and update it rather than create a twin. Dlubal confirm that re-using a
number overwrites the former object, so the mapping has to be remembered rather
than recomputed - hence a file next to the model JSON.

One map per backend. RFEM's numbers are not SAF's names and not OpenSees' tags,
and mixing them would bind results to the wrong objects without any error.
"""

import json
import os


#: Objects per category in RFEM 6 and RSTAB 9, from Dlubal's "Program Capacity"
#: page. Dlubal add that the practical limit for effective work is
#: "significantly lower", so this is a ceiling, not a target.
MAX_RFEM_NUMBER = 999_999

#: Backends whose numbering this class allocates, with their ceiling. A backend
#: that is not listed gets the RFEM limit, which is the most restrictive one we
#: know of.
BACKEND_LIMITS = {
    "rfem": MAX_RFEM_NUMBER,
    "rstab": MAX_RFEM_NUMBER,
}


class BackendMap:
    """``{neutral id -> backend number}`` for one backend, per object category.

    Parameters
    ----------
    backend : str
        ``"rfem"``, ``"rstab"``, ``"saf"``, ``"opensees"``.
    _limit : int, optional
        Ceiling on allocated numbers. Defaults to the backend's documented
        capacity; present so the exhaustion path can be tested.
    """

    def __init__(self, backend, _limit=None):
        self.backend = backend
        self.limit = _limit or BACKEND_LIMITS.get(backend, MAX_RFEM_NUMBER)
        #: category -> {neutral id: backend number}
        self.assigned = {}
        #: category -> highest number handed out so far. Kept separately from
        #: len(assigned) because a forgotten object must not free its number.
        self.high_water = {}

    # -- allocation --------------------------------------------------------

    def number_for(self, category, neutral_id):
        """The backend number for a neutral id, allocating one if needed.

        Numbers start at 1 - Dlubal does not do zero-based numbering - and
        count up per category, because RFEM keeps nodes, members and surfaces
        in separate namespaces.
        """
        known = self.assigned.setdefault(category, {})
        key = str(neutral_id)
        if key in known:
            return known[key]

        nxt = self.high_water.get(category, 0) + 1
        if nxt > self.limit:
            raise ValueError(
                "{}: ran out of {} numbers for '{}' (limit {}). The model has more "
                "objects than the backend can hold.".format(
                    self.backend, category, category, self.limit)
            )
        known[key] = nxt
        self.high_water[category] = nxt
        return nxt

    def neutral_for(self, category, number):
        """The neutral id behind a backend number, or None.

        None means the backend holds an object we did not create - which is
        information rather than a failure: it is what the engineer added by
        hand, and what the read-back step has to look at.
        """
        for neutral, assigned in (self.assigned.get(category) or {}).items():
            if assigned == number:
                return int(neutral)
        return None

    def forget(self, category, neutral_id):
        """Drop a neutral id, without freeing its backend number.

        The gap is deliberate. Re-using the number would silently overwrite
        whatever the engineer did with the old object, and a gap in the
        numbering costs nothing.
        """
        (self.assigned.get(category) or {}).pop(str(neutral_id), None)

    def obsolete(self, category, live_neutral_ids):
        """Backend numbers whose neutral objects are gone - what to delete.

        The other half of an incremental push: everything still present gets
        updated, everything here gets removed.
        """
        live = {str(i) for i in live_neutral_ids}
        return sorted(
            number for neutral, number in (self.assigned.get(category) or {}).items()
            if neutral not in live
        )

    # -- persistence -------------------------------------------------------

    def save(self, path):
        """Write the map beside the model, as readable JSON.

        Readable on purpose: when a push does the wrong thing, this file is
        the first place to look, and it should not need a tool to open.
        """
        payload = {
            "backend": self.backend,
            "limit": self.limit,
            "assigned": self.assigned,
            "high_water": self.high_water,
        }
        with open(path, "w") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)

    @classmethod
    def load(cls, path, backend=None):
        """Read a map back, or start an empty one if the file is not there.

        A missing file is the normal first push, not an error.

        Raises
        ------
        ValueError
            If the file belongs to a different backend. RFEM's numbers are
            not SAF's, and using one for the other would attach results to
            the wrong objects without anything failing.
        """
        if not os.path.isfile(path):
            return cls(backend=backend or "rfem")

        with open(path) as handle:
            payload = json.load(handle)

        stored = payload.get("backend")
        if backend is not None and stored != backend:
            raise ValueError(
                "backend mismatch: {} holds a map for '{}', not '{}'".format(
                    path, stored, backend)
            )

        backend_map = cls(backend=stored, _limit=payload.get("limit"))
        backend_map.assigned = payload.get("assigned") or {}
        backend_map.high_water = payload.get("high_water") or {}
        return backend_map

    def __repr__(self):
        counts = ", ".join(
            "{} {}".format(len(ids), category)
            for category, ids in sorted(self.assigned.items())
        )
        return "<BackendMap {}: {}>".format(self.backend, counts or "empty")
