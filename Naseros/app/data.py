# backend/app/data.py
# DataStore extendido: además de r3h/vim, carga r3h_avg, r3q, vim_lta, viq
# necesarias para el diagnóstico temporal (anomalías + climatología).

from pathlib import Path

import numpy as np
import pandas as pd


class DataStore:
    def __init__(self):
        self.by_pcode: dict[str, pd.DataFrame] = {}
        self.names: dict[str, dict] = {}
        self.meta: dict[str, dict] = {}
        self.verdicts: list[dict] = []

    def load(self, data_dir: str, names: dict[str, dict]):
        data_dir = Path(data_dir)
        self.names = names

        rain = pd.read_csv(data_dir / "bol-rainfall-subnat-full.csv", parse_dates=["date"])
        ndvi = pd.read_csv(data_dir / "bol-ndvi-subnat-full.csv", parse_dates=["date"])

        # Filtros: solo ADM2 y versión final
        rain = rain[(rain["adm_level"] == 2) & (rain["version"] == "final")].copy()
        ndvi = ndvi[ndvi["adm_level"] == 2].copy()

        # Limpieza de outliers imposibles
        rain.loc[rain["r3h"] > 2000, "r3h"] = np.nan
        ndvi.loc[ndvi["vim"].abs() > 2, "vim"] = np.nan

        # Columnas base + extensiones (asumiendo que existen; si no, se ponen NaN)
        rain_cols = ["date", "PCODE", "n_pixels", "r3h"]
        for extra in ("r3h_avg", "r3q"):
            if extra in rain.columns:
                rain_cols.append(extra)

        ndvi_cols = ["date", "PCODE", "n_pixels", "vim"]
        for extra in ("vim_lta", "viq"):
            if extra in ndvi.columns:
                ndvi_cols.append(extra)

        rain = rain[rain_cols].rename(columns={"n_pixels": "n_pixels_rain"})
        ndvi = ndvi[ndvi_cols].rename(columns={"n_pixels": "n_pixels_ndvi"})

        rain["PCODE"] = rain["PCODE"].str.upper()
        ndvi["PCODE"] = ndvi["PCODE"].str.upper()

        merged = (
            rain.merge(ndvi, on=["date", "PCODE"], how="inner")
            .sort_values(["PCODE", "date"])
            .reset_index(drop=True)
        )

        # Columnas faltantes → NaN (degradación elegante si no vinieron).
        for col in ("r3h_avg", "r3q", "vim_lta", "viq"):
            if col not in merged.columns:
                merged[col] = np.nan

        self.by_pcode = {p: g.reset_index(drop=True) for p, g in merged.groupby("PCODE")}

        for pcode, grp in self.by_pcode.items():
            np_px = grp["n_pixels_rain"].dropna()
            self.meta[pcode] = {
                "n_obs": int(len(grp)),
                "n_pixels": int(np_px.median()) if len(np_px) else 0,
                "start": grp["date"].min().strftime("%Y-%m-%d"),
                "end":   grp["date"].max().strftime("%Y-%m-%d"),
            }

        have_anom = merged["r3q"].notna().any() and merged["viq"].notna().any()
        print(f"[data] regiones con datos: {len(self.by_pcode)} / {len(names)} "
              f"| anomalías: {'sí' if have_anom else 'NO'}")


DATA = DataStore()