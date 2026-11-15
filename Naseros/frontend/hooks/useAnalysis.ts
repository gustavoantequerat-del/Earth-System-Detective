// hooks/useAnalysis.ts
// Hook que carga /api/analysis/{pcode} con cancelación vía AbortController.
// - Al cambiar de pcode, cancela el fetch anterior.
// - Al desmontar, cancela el fetch en vuelo.
// - Ignora errores de tipo "AbortError" (no son errores reales).
// - Guarda el último pcode pedido para evitar race conditions (respuesta vieja
//   que llega después de una nueva).

"use client";

import { useEffect, useRef, useState } from "react";
import { getAnalysis } from "@/lib/api";
import type { Analysis } from "@/lib/types";

interface UseAnalysisResult {
  data: Analysis | null;
  loading: boolean;
  error: string | null;
}

/**
 * Carga el análisis de una región. Pasar pcode=null cancela y limpia el estado.
 */
export function useAnalysis(pcode: string | null): UseAnalysisResult {
  const [data, setData] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // pcode "vigente" para descartar respuestas obsoletas.
  const requestedRef = useRef<string | null>(null);

  useEffect(() => {
    // Sin selección → limpiar todo.
    if (!pcode) {
      requestedRef.current = null;
      setData(null);
      setLoading(false);
      setError(null);
      return;
    }

    // Nueva petición: marcar como vigente, limpiar error previo.
    requestedRef.current = pcode;
    setLoading(true);
    setError(null);

    const controller = new AbortController();

    getAnalysis(pcode, controller.signal)
      .then((result) => {
        // Descartar si el usuario ya cambió de región mientras cargaba.
        if (requestedRef.current !== pcode) return;
        setData(result);
        setLoading(false);
      })
      .catch((err: unknown) => {
        // AbortError = cancelación intencional; no es un fallo real.
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (requestedRef.current !== pcode) return;

        const message =
          err instanceof Error ? err.message : "Error desconocido";
        setError(message);
        setLoading(false);
      });

    return () => {
      controller.abort();
    };
  }, [pcode]);

  return { data, loading, error };
}