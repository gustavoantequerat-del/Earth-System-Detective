"""Regenera el archivo regional que sirve NestJS con el análisis original de Naseros."""

import gzip
import json
import math
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))

from Naseros.app.analysis import analyze_region
from Naseros.app.data import DataStore
from Naseros.app.timeseries import build_timeseries


def json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    return value


def main():
    source = root / "Naseros" / "data"
    names = json.loads((source / "regions_meta.json").read_text(encoding="utf-8"))
    store = DataStore()
    store.load(str(source), names)
    verdicts, analyses = [], {}
    for code, info in names.items():
        analysis = analyze_region(code, store)
        if analysis is not None:
            analyses[code] = analysis
            verdicts.append({key: analysis[key] for key in ("pcode", "name", "adm1_name", "level", "verdict", "n_pixels")})
        else:
            verdicts.append({**info, "pcode": code, "level": "no_data", "verdict": "Sin datos suficientes", "n_pixels": 0})

    atlas = {
        "origin": "vegetacion-agua",
        "verdicts": verdicts,
        "analyses": analyses,
        "timeline": build_timeseries(store),
    }
    payload = json.dumps(json_safe(atlas), ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    output = root / "data" / "real" / "vegetation-regions.json.gz"
    temp = output.with_suffix(".gz.tmp")
    temp.write_bytes(gzip.compress(payload, compresslevel=6, mtime=0))
    temp.replace(output)
    print(f"{len(analyses)} análisis, {len(atlas['timeline']['dates'])} periodos, {output.stat().st_size:,} bytes.")


if __name__ == "__main__":
    main()
