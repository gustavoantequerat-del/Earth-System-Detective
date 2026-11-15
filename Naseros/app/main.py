import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import Response
from .timeseries import build_timeseries
from .analysis import analyze_region
from .data import DATA

DATA_DIR    = Path(__file__).parent.parent / "data"
GEOJSON_GZ  = DATA_DIR / "bol_admin2_simplified.geojson.gz"
REGIONS_MET = DATA_DIR / "regions_meta.json"

app = FastAPI(title="Earth System Trend Detective · Bolivia")

app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:5173", "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

_geojson_gz: bytes = b""


@app.on_event("startup")
def _startup():
    global _geojson_gz
    if not GEOJSON_GZ.exists() or not REGIONS_MET.exists():
        raise RuntimeError(
            "Faltan archivos generados. Corre: cd scripts && python prepare_geojson.py"
        )

    _geojson_gz = GEOJSON_GZ.read_bytes()
    names = json.loads(REGIONS_MET.read_text())
    DATA.load(str(DATA_DIR), names)

    # Pre-computa veredictos (una sola vez, al startup)
    verdicts = []
    for pcode, nm in names.items():
        res = analyze_region(pcode, DATA)
        if res is None:
            verdicts.append({
                "pcode": pcode, "name": nm["name"], "adm1_name": nm["adm1_name"],
                "level": "no_data", "verdict": "Sin datos suficientes", "n_pixels": 0,
            })
        else:
            verdicts.append({
                "pcode": res["pcode"], "name": res["name"], "adm1_name": res["adm1_name"],
                "level": res["level"], "verdict": res["verdict"], "n_pixels": res["n_pixels"],
            })
    DATA.verdicts = verdicts

    print(f"[startup] geojson={len(_geojson_gz)//1024} KB (gz), "
          f"regiones={len(names)}, con datos={len(DATA.by_pcode)}")


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "regions_total": len(DATA.names),
        "regions_with_data": len(DATA.by_pcode),
        "geojson_kb": len(_geojson_gz) // 1024,
    }


@app.get("/api/regions")
def get_regions():
    """GeoJSON simplificado; ya viene gzipeado, se sirve sin re-comprimir."""
    return Response(
        content=_geojson_gz,
        media_type="application/geo+json",
        headers={"Content-Encoding": "gzip", "Cache-Control": "public, max-age=3600"},
    )


@app.get("/api/regions/verdicts")
def get_verdicts():
    return DATA.verdicts


@app.get("/api/analysis/{pcode}")
def get_analysis(pcode: str):
    res = analyze_region(pcode, DATA)
    if res is None:
        raise HTTPException(404, f"PCODE desconocido o sin datos: {pcode}")
    return res


_timeseries_cache: dict | None = None

@app.get("/api/timeseries")
def get_timeseries():
    """Series dekadales de r3q/viq alineadas para playback temporal."""
    global _timeseries_cache
    if _timeseries_cache is None:
        print("[timeseries] calculando por primera vez…")
        _timeseries_cache = build_timeseries(DATA)
        print(
            f"[timeseries] {len(_timeseries_cache['dates'])} dekads × "
            f"{len(_timeseries_cache['regions'])} regiones"
        )
    return _timeseries_cache