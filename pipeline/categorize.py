"""Assign HPD violations and complaints to categories from pipeline/hpd_categories.yml.

    from categorize import Categorizer
    cat = Categorizer()
    cat.violation(ordernumber="689", text="PROPERLY REPAIR ... EXPOSED WIRING ...")  # {'electrical_wiring'}
    cat.complaint("APPLIANCE", "ELECTRIC/GAS RANGE", "GAS SHUT-OFF VALVE LEAKING")  # {'appliance_gas_leak', ...}

Also usable on DataFrames: cat.violation_frame(df) / cat.complaint_frame(df) add one boolean
column per category (named cat_<name>).
"""
import pathlib, re
import yaml

RULES = pathlib.Path(__file__).resolve().parent / "hpd_categories.yml"

def _code(x):
    s = str(x).strip() if x is not None else ""
    return s.split(".", 1)[0] if s else ""

class Categorizer:
    def __init__(self, path=RULES):
        spec = yaml.safe_load(pathlib.Path(path).read_text())
        self.meta, self._v, self._c = {}, {}, {}
        for name, c in spec["categories"].items():
            self.meta[name] = {"hypothesis": c.get("hypothesis"), "description": c.get("description", "")}
            v = c.get("violations") or {}
            self._v[name] = (
                {str(x) for x in v.get("order_codes", [])},
                [re.compile(p, re.I) for p in v.get("text", [])],
                [re.compile(p, re.I) for p in v.get("text_exclude", [])],
            )
            self._c[name] = [
                (r["major"].upper(), (r.get("minor") or "").upper() or None,
                 re.compile(r["problem"], re.I) if r.get("problem") else None)
                for r in (c.get("complaints") or [])
            ]
        self.names = list(self.meta)

    def violation(self, ordernumber, text):
        code, text = _code(ordernumber), text or ""
        out = set()
        for name, (codes, pats, excl) in self._v.items():
            if (code in codes or any(p.search(text) for p in pats)) and not any(x.search(text) for x in excl):
                out.add(name)
        return out

    def complaint(self, major, minor, problem):
        major, minor, problem = (major or "").upper(), (minor or "").upper(), problem or ""
        out = set()
        for name, rules in self._c.items():
            for maj, mn, prob in rules:
                if maj == major and (mn is None or mn == minor) and (prob is None or prob.search(problem)):
                    out.add(name); break
        return out

    def violation_frame(self, df, code_col="ordernumber", text_col="novdescription"):
        sets = [self.violation(c, t) for c, t in zip(df[code_col], df[text_col])]
        return df.assign(**{f"cat_{n}": [n in s for s in sets] for n in self.names})

    def complaint_frame(self, df, major="major_category", minor="minor_category", problem="problem_code"):
        sets = [self.complaint(a, b, c) for a, b, c in zip(df[major], df[minor], df[problem])]
        return df.assign(**{f"cat_{n}": [n in s for s in sets] for n in self.names})
