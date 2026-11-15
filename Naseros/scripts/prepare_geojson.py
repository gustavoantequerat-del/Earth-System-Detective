"""
Genera (una sola vez):
  data/bol_admin2_simplified.geojson         (para inspección)
  data/bol_admin2_simplified.geojson.gz      (servido por /api/regions)
  data/regions_meta.json                     (pcode -> {name, adm1_name})
"""
import gzip
import json
from pathlib import Path

from shapely.geometry import shape, mapping

INPUT   = Path("../bol_admin_boundaries.geojson/bol_admin2.geojson")
OUT_DIR = Path("../data")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_GJ  = OUT_DIR / "bol_admin2_simplified.geojson"
OUT_GZ  = OUT_DIR / "bol_admin2_simplified.geojson.gz"
OUT_META = OUT_DIR / "regions_meta.json"

TOLERANCE = 0.01   # ~1.1 km; sube a 0.02 si aún pesa > 1 MB gz
PRECISION = 4      # decimales (~11 m)


def _round(coords, p):
    if isinstance(coords[0], (int, float)):
        return [round(c, p) for c in coords]
    return [_round(c, p) for c in coords]


def main():
    print(f"Leyendo {INPUT} ({INPUT.stat().st_size/1e6:.1f} MB)…")
    gj = json.loads(INPUT.read_text())

    features, meta = [], {}
    for i, feat in enumerate(gj["features"], 1):
        geom = shape(feat["geometry"])
        if not geom.is_valid:
            geom = geom.buffer(0)
        simple = geom.simplify(TOLERANCE, preserve_topology=True)
        geom_dict = mapping(simple)
        if "coordinates" in geom_dict:
            geom_dict["coordinates"] = _round(geom_dict["coordinates"], PRECISION)

        p = feat["properties"]
        pcode = p["adm2_pcode"].upper()
        entry = {
            "pcode":     pcode,
            "name":      p.get("adm2_name") or pcode,
            "adm1_name": p.get("adm1_name") or "",
        }
        features.append({"type": "Feature", "properties": entry, "geometry": geom_dict})
        meta[pcode] = {"name": entry["name"], "adm1_name": entry["adm1_name"]}

        if i % 20 == 0:
            print(f"  {i}/{len(gj['features'])}…")

    payload = json.dumps(
        {"type": "FeatureCollection", "features": features},
        separators=(",", ":"),
    ).encode()

    OUT_GJ.write_bytes(payload)
    with gzip.open(OUT_GZ, "wb", compresslevel=9) as f:
        f.write(payload)
    OUT_META.write_text(json.dumps(meta, ensure_ascii=False))

    print(f"\nOriginal   : {INPUT.stat().st_size/1e6:8.1f} MB")
    print(f"Simplified : {OUT_GJ.stat().st_size/1e6:8.2f} MB")
    print(f"Gzipped    : {OUT_GZ.stat().st_size/1e6:8.2f} MB   ← lo que viaja al frontend")
    print(f"Meta       : {OUT_META.stat().st_size/1e3:8.1f} KB")


if __name__ == "__main__":
    main()