import re
import unicodedata
from difflib import get_close_matches
import pandas as pd

_TURKISH_CHAR_MAP = str.maketrans({
    "ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
    "ö": "o", "Ö": "o", "ü": "u", "Ü": "u", "ç": "c", "Ç": "c",
})

def normalize(s: str) -> str:
    if s is None:
        return ""
    s = str(s).strip()
    s = s.translate(_TURKISH_CHAR_MAP)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def coerce_numeric_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return series
    s = series.astype(str).replace({"<NA>": "", "nan": "", "None": ""})
    s = s.str.replace(r"[^\d,.\-]", "", regex=True)
    def _fix(x: str) -> str:
        if not x: return ""
        if "," in x and "." in x:
            if x.rfind(",") > x.rfind("."):
                x = x.replace(".", "").replace(",", ".")
            else:
                x = x.replace(",", "")
        elif "," in x and "." not in x:
            x = x.replace(",", ".")
        return x
    return pd.to_numeric(s, errors="coerce")


DEFAULT_SCHEMA = {
    "is_yeri_kodu": {
        "label": "İş Yeri Kodu",
        "synonyms": ["is yeri", "iş yeri", "plant", "site", "plant code", "işyeri", "isyeri"],
    },
    "masraf_yeri_kodu": {
        "label": "Masraf Yeri Kodu",
        "synonyms": ["masraf yeri", "cost center", "cost centre", "cc", "masraf kodu"],
    },
    "makine_kodu": {
        "label": "Makine Kodu",
        "synonyms": ["makina kodu", "ekipman kodu", "equipment code", "asset code"],
    },
    "makine_adi": {
        "label": "Makine Adı",
        "synonyms": ["makina adi", "ekipman adı", "equipment name", "asset name"],
    },
    # "malzeme_kodu" çıkarıldı
    "malzeme_adi": {
        "label": "Malzeme Adı",
        "synonyms": ["malzeme adi", "stok adı", "material name", "item name"],
    },
}

REQUIRED_FIELDS = list(DEFAULT_SCHEMA.keys())

class Mapper:
    def __init__(self, schema: dict):
        self.schema = schema

    def suggest_mapping(self, headers: list[str]) -> dict[str, str | None]:
        norm_headers_map = {normalize(h): h for h in headers}
        mapping: dict[str, str | None] = {}
        for canonical, meta in self.schema.items():
            candidates = [canonical] + meta.get("synonyms", [])
            cand_norm = [normalize(x) for x in candidates]
            hit = None
            for c in cand_norm:
                if c in norm_headers_map:
                    hit = norm_headers_map[c]
                    break
            if hit is None:
                for nh in norm_headers_map.keys():
                    m = get_close_matches(nh, cand_norm, n=1, cutoff=0.88)
                    if m:
                        hit = norm_headers_map[nh]
                        break
            mapping[canonical] = hit
        return mapping

    def apply_mapping(self, df: pd.DataFrame, mapping: dict[str, str | None]) -> pd.DataFrame:
        out = pd.DataFrame()
        for canonical, meta in self.schema.items():
            src = mapping.get(canonical)
            label = meta.get("label", canonical)
            out[label] = df[src] if src and src in df.columns else pd.NA
        if "__kaynak_dosya__" in df.columns:
            out["__kaynak_dosya__"] = df["__kaynak_dosya__"]
        return out
