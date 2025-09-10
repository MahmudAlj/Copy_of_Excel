# cost_components.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

# normalize() fonksiyonunu senin core_schema.py'dan alıyoruz
from core_schema import normalize  # → aynı klasörde olmalı

# --------------------------------------------------------
# Kullanıcıdan beklenen girişler: İş Yeri Kodu, Masraf Yeri Kodu
# Çıkış: AMOR, DIS, EDIS, ENER, GUG ve bunlardan türetilen formül sonuçları
# --------------------------------------------------------

# Bileşen isimleri (sabit)
COMPONENTS = ["AMOR", "DIS", "EDIS", "ENER", "GUG"]

# Her bileşen için sütun bulurken kullanılacak aday adlar
# Dilersen burada yeni eş adlar ekleyebilirsin.
COMP_COL_CANDIDATES: Dict[str, List[str]] = {
    "AMOR": ["amor", "amortisman", "depreciation"],
    "DIS":  ["dis", "di̇s", "direkt iscilik", "direkt işçilik", "direct labor", "dl"],
    "EDIS": ["edis", "endirekt iscilik", "endirekt işçilik", "indirect labor", "il"],
    "ENER": ["ener", "enerji", "electricity", "kwh", "energy cost", "elektrik"],
    "GUG":  ["gug", "güg", "genel uretim gider", "genel üretim gider", "overhead", "oh"],
}

# İş yeri / Masraf yeri sütunlarını bulurken kullanılacak adaylar
PLANT_COL_CANDIDATES = ["is yeri kodu", "iş yeri kodu", "is yeri", "işyeri", "plant", "site", "plant code"]
CCTR_COL_CANDIDATES  = ["masraf yeri kodu", "masraf yeri", "cost center", "cost centre", "cc", "masraf kodu"]


def _find_col_by_candidates(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    """Başlıkları normalize edip adaylardan ilki ile eşleşeni döner."""
    if df is None or df.columns is None:
        return None
    norm_map = {normalize(c): c for c in df.columns}
    # tam eşleşme
    for cand in candidates:
        n = normalize(cand)
        if n in norm_map:
            return norm_map[n]
    # gevşek eşleşme (alt string)
    for col in df.columns:
        ncol = normalize(col)
        if any(normalize(c) in ncol for c in candidates):
            return col
    return None


def _to_float(x) -> float:
    """TR/EN sayı dayanıklı dönüştürücü (virgül/nokta)."""
    try:
        s = str(x).strip()
        if s == "" or s.lower() in ("nan", "<na>", "none"):
            return 0.0
        if "," in s and "." in s and s.rfind(",") > s.rfind("."):
            s = s.replace(" ", "").replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", ".")
        return float(s)
    except Exception:
        try:
            return float(x)
        except Exception:
            return 0.0


@dataclass
class FoundColumns:
    plant_col: Optional[str]
    cctr_col: Optional[str]
    comp_cols: Dict[str, Optional[str]]  # bileşen -> kaynak sütun adı


def resolve_columns(df: pd.DataFrame) -> FoundColumns:
    """Kullanılacak kolonları belirle."""
    plant_col = _find_col_by_candidates(df, PLANT_COL_CANDIDATES)
    cctr_col  = _find_col_by_candidates(df, CCTR_COL_CANDIDATES)
    comp_cols = {}
    for comp in COMPONENTS:
        comp_cols[comp] = _find_col_by_candidates(df, COMP_COL_CANDIDATES.get(comp, [comp]))
    return FoundColumns(plant_col=plant_col, cctr_col=cctr_col, comp_cols=comp_cols)


def filter_by_codes(df: pd.DataFrame, plant_code: str, cctr_code: str, found: FoundColumns) -> pd.DataFrame:
    """İş yeri + masraf yeri ile filtrele (b. kücük harf duyarsız; önce tam, yoksa contains)."""
    if df is None or df.empty:
        return pd.DataFrame()

    mask = pd.Series(True, index=df.index)
    if plant_code and found.plant_col:
        s = df[found.plant_col].astype(str).str.strip()
        eq = s.str.casefold() == plant_code.casefold()
        mask &= (eq if eq.any() else s.str.contains(plant_code, case=False, na=False, regex=False))

    if cctr_code and found.cctr_col:
        s = df[found.cctr_col].astype(str).str.strip()
        eq = s.str.casefold() == cctr_code.casefold()
        mask &= (eq if eq.any() else s.str.contains(cctr_code, case=False, na=False, regex=False))

    return df.loc[mask].copy()


def extract_components(df_filtered: pd.DataFrame, found: FoundColumns) -> pd.DataFrame:
    """
    Filtre sonrası satırlardan AMOR/DIS/EDIS/ENER/GUG sütunları çek.
    Kaynakta yoksa 0 kabul edilir. Çıkış: satır bazında numeric tablo.
    """
    out = pd.DataFrame(index=df_filtered.index)
    for comp in COMPONENTS:
        src = found.comp_cols.get(comp)
        if src and src in df_filtered.columns:
            out[comp] = df_filtered[src].map(_to_float)
        else:
            out[comp] = 0.0
    # referans için opsiyonel: kaynak dosya adı ve kod kolonlarını da ekleyelim
    if "__kaynak_dosya__" in df_filtered.columns:
        out["__kaynak_dosya__"] = df_filtered["__kaynak_dosya__"]
    if found.plant_col and found.plant_col in df_filtered.columns:
        out["İş Yeri Kodu"] = df_filtered[found.plant_col]
    if found.cctr_col and found.cctr_col in df_filtered.columns:
        out["Masraf Yeri Kodu"] = df_filtered[found.cctr_col]
    return out.reset_index(drop=True)


# ------------------- Formül tarafı -------------------

DEFAULT_FORMULAS = {
    # Ana süreç maliyeti — istersen Excel’den gelecektir
    "PROCESS_MALIYETI": "AMOR + DIS + EDIS + ENER + GUG",
    # İstersen başka ara formüller ekleyebilirsin:
    # "BIR_SEY": "AMOR*0.1 + ENER"
}

def load_formulas_from_excel(path: str | Path) -> Dict[str, str]:
    """
    IS_PLAN_FORMULLER.xlsx beklenen şekil:
      Sheet: ilk sayfa
      Kolonlar: name, expr
      Örn:  name=PROCESS_MALIYETI, expr=AMOR + DIS + EDIS + ENER + GUG
    Bulunamazsa DEFAULT_FORMULAS döner.
    """
    p = Path(path)
    try:
        df = pd.read_excel(p)
        name_col = _find_col_by_candidates(df, ["name", "formul ad", "formül adı", "kod"])
        expr_col = _find_col_by_candidates(df, ["expr", "formul", "formül", "expression"])
        if not name_col or not expr_col:
            return DEFAULT_FORMULAS.copy()
        formulas = {}
        for _, r in df.iterrows():
            nm = str(r.get(name_col, "")).strip()
            ex = str(r.get(expr_col, "")).strip()
            if nm and ex:
                formulas[nm] = ex
        return formulas or DEFAULT_FORMULAS.copy()
    except Exception:
        return DEFAULT_FORMULAS.copy()


def eval_formulas_on_rows(components_df: pd.DataFrame, formulas: Dict[str, str]) -> pd.DataFrame:
    """
    components_df: satır bazında AMOR/DIS/EDIS/ENER/GUG var.
    formulas: {"AD": "ifade"} (sadece + - * / ve bileşen isimleri)
    """
    out = components_df.copy()
    # güvenlik: sadece izinli karakterler
    for name, expr in formulas.items():
        if not isinstance(expr, str):
            continue
        if not pd.notna(expr):
            continue
        if not pd.Series(list(expr)).map(lambda ch: ch.isalnum() or ch.isspace() or ch in "+-*/_").all():
            # illegal karakter; atla
            continue

        # eval için ortam: bileşen serileri
        local_env = {comp: out[comp] if comp in out.columns else 0.0 for comp in COMPONENTS}
        try:
            out[name] = eval(expr, {"__builtins__": {}}, local_env)
        except Exception:
            # hata olursa kolon oluşturma ama uygulamayı bozma
            pass
    return out


# ------------------- Ana fonksiyon -------------------

def compute_by_plant_costcenter(
    src_df: pd.DataFrame,
    isyeri_kodu: str,
    masraf_yeri_kodu: str,
    formula_excel_path: str | Path | None = None
) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """
    1) Sütunları çöz → 2) Kodlarla filtrele → 3) AMOR/DIS/EDIS/ENER/GUG çıkar
    4) Formülleri uygula → 5) Satır bazlı tablo + özet (toplamlar) döndür.

    Dönüş:
      (rows_df, summary_dict)
        rows_df: her satırda AMOR,DIS,EDIS,ENER,GUG (+ formül sonuçları)
        summary_dict: toplam AMOR..GUG ve formül sonuçlarının toplamı
    """
    if src_df is None or src_df.empty:
        return pd.DataFrame(), {}

    found = resolve_columns(src_df)
    if not found.plant_col or not found.cctr_col:
        pass

    filtered = filter_by_codes(src_df, isyeri_kodu, masraf_yeri_kodu, found)
    if filtered.empty:
        return pd.DataFrame(), {}

    comp_df = extract_components(filtered, found)
    formulas = DEFAULT_FORMULAS.copy()
    if formula_excel_path:
        formulas = load_formulas_from_excel(formula_excel_path)

    out_rows = eval_formulas_on_rows(comp_df, formulas)

    summary: Dict[str, float] = {}
    for col in COMPONENTS:
        if col in out_rows.columns:
            summary[col] = float(out_rows[col].sum(skipna=True))
    for fname in formulas.keys():
        if fname in out_rows.columns:
            summary[fname] = float(out_rows[fname].sum(skipna=True))

    return out_rows, summary
