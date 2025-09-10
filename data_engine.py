from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from core_schema import DEFAULT_SCHEMA, Mapper, normalize

FOUR_KEYS = ["is_yeri_kodu", "masraf_yeri_kodu", "makine_kodu"]
FALLBACK_LABELS = {
    "is_yeri_kodu": "İş Yeri Kodu",
    "masraf_yeri_kodu": "Masraf Yeri Kodu",
    "makine_kodu": "Makine Kodu",
}

class Engine:
    def __init__(self, schema: dict | None = None, state_dir: Optional[Path] = None):
        self.schema = (schema or DEFAULT_SCHEMA).copy()
        self.mapper = Mapper(self.schema)
        self.state_dir = state_dir or Path(__file__).with_name("sampa_state")
        self.state_dir.mkdir(exist_ok=True)

        # ÜST (sistem) ve ALT (geçici) veri kümeleri
        self.src_df: Optional[pd.DataFrame] = None       # üst
        self.staged_df: Optional[pd.DataFrame] = None    # alt
        self.processed_df: Optional[pd.DataFrame] = None # son işlenmiş (export için)
        self.loaded_files_top: List[str] = []
        self.loaded_files_bottom: List[str] = []
        self.manual_values: Dict[str, str] = {}

    def load_state(self) -> None:
        try:
            p_top = self.state_dir / "src_df.pkl"
            p_bot = self.state_dir / "staged_df.pkl"
            p_proc = self.state_dir / "processed_df.pkl"
            if p_top.exists():   self.src_df = pd.read_pickle(p_top)
            if p_bot.exists():   self.staged_df = pd.read_pickle(p_bot)
            if p_proc.exists():  self.processed_df = pd.read_pickle(p_proc)
        except Exception:
            pass

        cfg = self.state_dir / "config.json"
        if cfg.exists():
            try:
                data = json.loads(cfg.read_text(encoding="utf-8"))
                self.loaded_files_top = data.get("loaded_files_top", [])
                self.loaded_files_bottom = data.get("loaded_files_bottom", [])
                self.manual_values = data.get("manual_values", {})
            except Exception:
                pass

    def save_state(self, window: Dict[str, int] | None = None) -> None:
        if self.src_df is not None and not self.src_df.empty:
            self.src_df.to_pickle(self.state_dir / "src_df.pkl")
        if self.staged_df is not None and not self.staged_df.empty:
            self.staged_df.to_pickle(self.state_dir / "staged_df.pkl")
        if self.processed_df is not None and not self.processed_df.empty:
            self.processed_df.to_pickle(self.state_dir / "processed_df.pkl")

        cfg = {
            "loaded_files_top": self.loaded_files_top,
            "loaded_files_bottom": self.loaded_files_bottom,
            "manual_values": self.manual_values,
            "window": window or {},
        }
        (self.state_dir / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    def reset_bottom(self) -> None:
        """Sadece alt (staged) veriyi ve ilgili dosya listesini temizle."""
        self.staged_df = None
        self.loaded_files_bottom = []
        # diskteki alt pickle'ı da sil
        try:
            p = self.state_dir / "staged_df.pkl"
            if p.exists():
                p.unlink()
        except Exception:
            pass

    def reset_state(self) -> None:
        self.src_df = None
        self.staged_df = None
        self.processed_df = None
        self.loaded_files_top = []
        self.loaded_files_bottom = []
        self.manual_values = {}
        for name in ["src_df.pkl", "staged_df.pkl", "processed_df.pkl", "config.json"]:
            p = self.state_dir / name
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass

    def reset_top(self) -> None:
        self.src_df = None
        self.processed_df = None
        self.loaded_files_top = []
        try:
            p = self.state_dir / "src_df.pkl"
            if p.exists():
                p.unlink()
        except Exception:
            pass
        try:
            p = self.state_dir / "processed_df.pkl"
            if p.exists():
                p.unlink()
        except Exception:
            pass

    def _read_any(self, path: str) -> pd.DataFrame:
        if path.lower().endswith(".csv"):
            return pd.read_csv(path)
        return pd.read_excel(path)

    def read_files(self, paths: List[str]) -> pd.DataFrame:
        frames = []
        for path in paths:
            try:
                df = self._read_any(path)
            except Exception:
                continue
            if df.empty:
                continue
            df["__kaynak_dosya__"] = Path(path).name
            frames.append(df)
        return pd.concat(frames, ignore_index=True, join="outer") if frames else pd.DataFrame()

    def append_to_top(self, new_df: pd.DataFrame, source_paths: List[str]) -> None:
        if new_df is None or new_df.empty:
            return
        if self.src_df is None or self.src_df.empty:
            self.src_df = new_df
        else:
            self.src_df = pd.concat([self.src_df, new_df], ignore_index=True, join="outer")
        for p in source_paths:
            if p not in self.loaded_files_top:
                self.loaded_files_top.append(p)

    def append_to_bottom(self, new_df: pd.DataFrame, source_paths: List[str]) -> None:
        if new_df is None or new_df.empty:
            return
        if self.staged_df is None or self.staged_df.empty:
            self.staged_df = new_df
        else:
            self.staged_df = pd.concat([self.staged_df, new_df], ignore_index=True, join="outer")
        for p in source_paths:
            if p not in self.loaded_files_bottom:
                self.loaded_files_bottom.append(p)

    def auto_apply_top(self) -> Optional[pd.DataFrame]:
        if self.src_df is None or self.src_df.empty:
            return None
        mapping = self.mapper.suggest_mapping(list(self.src_df.columns))
        self.processed_df = self.mapper.apply_mapping(self.src_df, mapping)
        return self.processed_df

    def _cands(self, key: str) -> List[str]:
        meta = self.schema.get(key, {})
        return [meta.get("label", FALLBACK_LABELS.get(key, key)), *meta.get("synonyms", []), key]

    def find_col_by_candidates(self, df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
        if df is None or df.columns is None:
            return None
        norm_map = {normalize(c): c for c in df.columns}
        for cand in candidates:
            n = normalize(cand)
            if n in norm_map:
                return norm_map[n]
        for col in df.columns:
            if any(normalize(c) in normalize(col) for c in candidates):
                return col
        return None

    def autofill_manual_from_df(self, df: pd.DataFrame, keys: List[str] = FOUR_KEYS, override: bool = False) -> List[str]:
        if df is None or df.empty:
            return []
        filled = []
        for key in keys:
            if not override and self.manual_values.get(key):
                continue
            col = self.find_col_by_candidates(df, self._cands(key))
            if not col:
                continue
            s = (
                df[col].astype(str).str.strip()
                .replace({"": pd.NA, "nan": pd.NA, "<NA>": pd.NA, "None": pd.NA})
                .dropna()
            )
            if s.empty:
                continue
            uniq = s.unique()
            if len(uniq) == 1:
                val = str(uniq[0])
            else:
                vc = s.value_counts(dropna=True)
                top_val = vc.index[0]
                ratio = float(vc.iloc[0]) / float(len(s))
                if ratio < 0.9:
                    continue
                val = str(top_val)
            self.manual_values[key] = val
            filled.append(key)
        return filled

    def import_staged_into_system(self, replace_on_keys: bool = True) -> Tuple[int, int]:
        if self.staged_df is None or self.staged_df.empty:
            return (0, 0)
        if self.src_df is None or self.src_df.empty:
            self.src_df = self.staged_df.copy()
            return (0, len(self.staged_df))

        top_is = self.find_col_by_candidates(self.src_df, self._cands("is_yeri_kodu"))
        top_ms = self.find_col_by_candidates(self.src_df, self._cands("masraf_yeri_kodu"))
        bot_is = self.find_col_by_candidates(self.staged_df, self._cands("is_yeri_kodu"))
        bot_ms = self.find_col_by_candidates(self.staged_df, self._cands("masraf_yeri_kodu"))

        if replace_on_keys and top_is and top_ms and bot_is and bot_ms:
            key_pairs = set(
                zip(
                    self.staged_df[bot_is].astype(str).str.strip().str.casefold(),
                    self.staged_df[bot_ms].astype(str).str.strip().str.casefold(),
                )
            )
            before = len(self.src_df)
            mask_keep = ~(
                self.src_df[top_is].astype(str).str.strip().str.casefold().combine(
                    self.src_df[top_ms].astype(str).str.strip().str.casefold(),
                    lambda a, b: (a, b)
                ).isin(key_pairs)
            )
            self.src_df = self.src_df.loc[mask_keep].reset_index(drop=True)
            removed = before - len(self.src_df)
        else:
            removed = 0

        self.src_df = pd.concat([self.src_df, self.staged_df], ignore_index=True, join="outer")
        added = len(self.staged_df)
        return (removed, added)

    def filter_df_by_codes(self, df: pd.DataFrame, isyeri: str | None, masraf: str | None) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        col_is = self.find_col_by_candidates(df, self._cands("is_yeri_kodu")) if isyeri else None
        col_ms = self.find_col_by_candidates(df, self._cands("masraf_yeri_kodu")) if masraf else None
        mask = pd.Series(True, index=df.index)
        if isyeri and col_is:
            s = df[col_is].astype(str).str.strip()
            eq = s.str.casefold() == isyeri.casefold()
            mask &= (eq if eq.any() else s.str.contains(isyeri, case=False, na=False, regex=False))
        if masraf and col_ms:
            s = df[col_ms].astype(str).str.strip()
            eq = s.str.casefold() == masraf.casefold()
            mask &= (eq if eq.any() else s.str.contains(masraf, case=False, na=False, regex=False))
        sub = df.loc[mask]
        if sub.empty:
            return pd.DataFrame()
        cols = list(sub.columns)
        if "__kaynak_dosya__" in cols:
            cols = ["__kaynak_dosya__"] + [c for c in cols if c != "__kaynak_dosya__"]
            sub = sub.loc[:, cols]
        return sub.reset_index(drop=True)
