# backend/app/timeseries.py
# Arma el payload del playback temporal: fechas únicas + series r3q/viq por región.
# Formato compacto para mantener ~200 KB gzip.

from __future__ import annotations

import math

import pandas as pd


def build_timeseries(data) -> dict:
    """
    Devuelve:
      {
        "dates": ["2002-07-01", ...],           # N fechas dekadales únicas (global)
        "regions": {
          "BO1401": {
            "name": "Cercado",
            "adm1_name": "Tarija",
            "r3q": [null, -12.3, ...],          # N valores alineados a `dates`
            "viq": [null, -8.1, ...],
          },
          ...
        }
      }

    Alineación: cada serie tiene exactamente len(dates) entradas;
    null donde la región no tiene dato para ese dekad.
    """
    # 1) Fechas globales únicas (unión de todas las regiones).
    all_dates: set[pd.Timestamp] = set()
    for df in data.by_pcode.values():
        all_dates.update(df["date"].tolist())
    dates_sorted = sorted(all_dates)
    dates_iso = [d.strftime("%Y-%m-%d") for d in dates_sorted]
    date_to_idx = {d: i for i, d in enumerate(dates_sorted)}
    N = len(dates_sorted)

    # 2) Por región: alinear r3q y viq a `dates`.
    regions: dict[str, dict] = {}
    for pcode, df in data.by_pcode.items():
        nm = data.names.get(pcode, {"name": pcode, "adm1_name": ""})
        r3q_arr: list[float | None] = [None] * N
        viq_arr: list[float | None] = [None] * N

        for row in df.itertuples(index=False):
            i = date_to_idx.get(row.date)
            if i is None:
                continue
            r = getattr(row, "r3q", None)
            v = getattr(row, "viq", None)
            if r is not None and not math.isnan(r):
                r3q_arr[i] = round(float(r) - 100.0, 1)  # ← ratio → diferencia %
            if v is not None and not math.isnan(v):
                viq_arr[i] = round(float(v) - 100.0, 1)

        regions[pcode] = {
            "name": nm["name"],
            "adm1_name": nm["adm1_name"],
            "r3q": r3q_arr,
            "viq": viq_arr,
        }

    return {"dates": dates_iso, "regions": regions}