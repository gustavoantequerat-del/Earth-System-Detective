// components/BoliviaMap.tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { LEVEL_COLORS } from "@/lib/colors";
import { scoreToColor } from "@/lib/animation";
import type { Level, RegionsFeatureCollection, Verdict } from "@/lib/types";

interface BoliviaMapProps {
  regions: RegionsFeatureCollection | null;
  verdicts: Verdict[];
  selectedPcode: string | null;
  onSelect: (pcode: string) => void;
  /** Si != null, colorea por score compuesto del playback. */
  scoreByPcode?: Map<string, number | null> | null;
}

export default function BoliviaMap({
  regions,
  verdicts,
  selectedPcode,
  onSelect,
  scoreByPcode = null,
}: BoliviaMapProps) {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const geoLayerRef = useRef<L.GeoJSON | null>(null);
  const [containerReady, setContainerReady] = useState(false);

  // Refs sincronizadas con props (para leer valor vigente en callbacks).
  const levelByPcodeRef = useRef<Map<string, Level>>(new Map());
  const selectedPcodeRef = useRef<string | null>(selectedPcode);
  const scoreByPcodeRef = useRef<Map<string, number | null> | null>(null);
  const onSelectRef = useRef(onSelect);

  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  useEffect(() => {
    selectedPcodeRef.current = selectedPcode;
  }, [selectedPcode]);

  useEffect(() => {
    scoreByPcodeRef.current = scoreByPcode;
  }, [scoreByPcode]);

  // 0) Contenedor listo.
  useEffect(() => {
    if (mapContainerRef.current) setContainerReady(true);
  }, []);

  // ─────────────────────────────────────────────────────────────
  // styleForDynamic: elige color según playback o level.
  // ─────────────────────────────────────────────────────────────
  const styleForDynamic = useCallback(
    (pcode: string | undefined, isSelected: boolean): L.PathOptions => {
      let fillColor: string;

      if (scoreByPcodeRef.current) {
        const score = pcode
          ? scoreByPcodeRef.current.get(pcode) ?? null
          : null;
        fillColor = scoreToColor(score);
      } else {
        const level = pcode
          ? levelByPcodeRef.current.get(pcode) ?? "no_data"
          : "no_data";
        fillColor = LEVEL_COLORS[level];
      }

      return {
        color: isSelected ? "#000000" : "#ffffff",
        weight: isSelected ? 2.5 : 0.8,
        opacity: 1,
        fillColor,
        fillOpacity: isSelected ? 0.95 : 0.7,
      };
    },
    []
  );

  // ─────────────────────────────────────────────────────────────
  // 1) Init mapa (una vez).
  // ─────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!containerReady) return;
    if (!mapContainerRef.current || mapRef.current) return;

    const map = L.map(mapContainerRef.current, {
      zoomControl: true,
      attributionControl: true,
    }).setView([-16.5, -64.5], 6);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 12,
      minZoom: 4,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(map);

    mapRef.current = map;

    const raf = requestAnimationFrame(() => {
      try {
        map.invalidateSize();
      } catch {
        /* noop */
      }
    });

    return () => {
      cancelAnimationFrame(raf);
      try {
        map.remove();
      } catch {
        /* noop */
      }
      mapRef.current = null;
      geoLayerRef.current = null;
    };
  }, [containerReady]);

  // ─────────────────────────────────────────────────────────────
  // 2) levelByPcode desde verdicts.
  // ─────────────────────────────────────────────────────────────
  useEffect(() => {
    const m = new Map<string, Level>();
    for (const v of verdicts) m.set(v.pcode, v.level);
    levelByPcodeRef.current = m;
  }, [verdicts]);

  // ─────────────────────────────────────────────────────────────
  // 3) Crear layer GeoJSON.
  // ─────────────────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !regions) return;

    if (geoLayerRef.current) {
      map.removeLayer(geoLayerRef.current);
      geoLayerRef.current = null;
    }

    const layer = L.geoJSON(regions as GeoJSON.GeoJsonObject, {
      style: (feature) => {
        const pcode = (feature?.properties as { pcode?: string } | undefined)
          ?.pcode;
        return styleForDynamic(pcode, selectedPcodeRef.current === pcode);
      },
      onEachFeature: (feature, lyr) => {
        const props = feature.properties as
          | { pcode?: string; name?: string; adm1_name?: string }
          | undefined;
        const pcode = props?.pcode;
        const name = props?.name ?? "";
        const adm1 = props?.adm1_name ?? "";
        if (!pcode) return;

        const verdict = verdicts.find((v) => v.pcode === pcode);
        const shortVerdict = verdict?.verdict ?? "Sin datos";

        lyr.bindTooltip(
          `<div class="text-xs"><strong>${name}</strong><br/><span class="text-slate-500">${adm1}</span><br/><span>${shortVerdict}</span></div>`,
          { sticky: true, direction: "top", opacity: 1 }
        );

        lyr.on("click", () => onSelectRef.current(pcode));
        lyr.on("mouseover", () => {
          (lyr as L.Path).setStyle({ weight: 1.5, color: "#334155" });
        });
        lyr.on("mouseout", () => {
          (lyr as L.Path).setStyle(
            styleForDynamic(pcode, selectedPcodeRef.current === pcode)
          );
        });
      },
    }).addTo(map);

    geoLayerRef.current = layer;

    try {
      const bounds = layer.getBounds();
      if (bounds.isValid()) map.fitBounds(bounds, { padding: [10, 10] });
    } catch {
      /* noop */
    }

    const raf2 = requestAnimationFrame(() => {
      try {
        map.invalidateSize();
      } catch {
        /* noop */
      }
    });
    return () => cancelAnimationFrame(raf2);
  }, [regions, styleForDynamic, containerReady]);

  // ─────────────────────────────────────────────────────────────
  // 4) Recolorear cuando cambian verdicts.
  // ─────────────────────────────────────────────────────────────
  useEffect(() => {
    const layer = geoLayerRef.current;
    if (!layer) return;
    layer.eachLayer((lyr) => {
      const feature = (lyr as L.GeoJSON & { feature?: GeoJSON.Feature }).feature;
      const pcode = (feature?.properties as { pcode?: string } | undefined)?.pcode;
      if (!pcode) return;
      (lyr as L.Path).setStyle(
        styleForDynamic(pcode, selectedPcodeRef.current === pcode)
      );
    });
  }, [verdicts, styleForDynamic]);

  // ─────────────────────────────────────────────────────────────
  // 5) Resaltar selección.
  // ─────────────────────────────────────────────────────────────
  useEffect(() => {
    const layer = geoLayerRef.current;
    if (!layer) return;
    layer.eachLayer((lyr) => {
      const feature = (lyr as L.GeoJSON & { feature?: GeoJSON.Feature }).feature;
      const pcode = (feature?.properties as { pcode?: string } | undefined)?.pcode;
      if (!pcode) return;
      (lyr as L.Path).setStyle(styleForDynamic(pcode, selectedPcode === pcode));
    });
  }, [selectedPcode, styleForDynamic]);

  // ─────────────────────────────────────────────────────────────
  // 6) Recolorear cuando cambia el score del playback.
  //    Este es el que hace que el mapa "se mueva" con el slider.
  // ─────────────────────────────────────────────────────────────
  useEffect(() => {
    const layer = geoLayerRef.current;
    if (!layer) return;
    layer.eachLayer((lyr) => {
      const feature = (lyr as L.GeoJSON & { feature?: GeoJSON.Feature }).feature;
      const pcode = (feature?.properties as { pcode?: string } | undefined)?.pcode;
      if (!pcode) return;
      (lyr as L.Path).setStyle(
        styleForDynamic(pcode, selectedPcodeRef.current === pcode)
      );
    });
  }, [scoreByPcode, styleForDynamic]);

  return (
    <div
      ref={mapContainerRef}
      className="h-[500px] min-h-[500px] w-full md:h-[600px] md:min-h-[600px]"
      aria-label="Mapa coroplético de provincias de Bolivia"
    />
  );
}