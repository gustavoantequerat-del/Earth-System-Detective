// hooks/usePlayback.ts
// Estado y control del playback temporal.
// - currentDekad: índice 0..N-1
// - isPlaying: bool
// - speed: 1 | 2 | 4 (multiplicador)
// - play/pause/toggle/seek/setSpeed
// Detiene al llegar al final (sin loop).

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const BASE_DEKADS_PER_SEC = 6; // velocidad 1×

interface UsePlaybackResult {
  currentDekad: number;
  isPlaying: boolean;
  speed: 1 | 2 | 4;
  play: () => void;
  pause: () => void;
  toggle: () => void;
  seek: (index: number) => void;
  setSpeed: (s: 1 | 2 | 4) => void;
}

export function usePlayback(totalDekads: number): UsePlaybackResult {
  const [currentDekad, setCurrentDekad] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeedState] = useState<1 | 2 | 4>(1);

  // Refs para no re-crear el interval cuando cambia speed o currentDekad.
  const currentRef = useRef(0);
  const speedRef = useRef<1 | 2 | 4>(1);
  const totalRef = useRef(totalDekads);

  useEffect(() => { currentRef.current = currentDekad; }, [currentDekad]);
  useEffect(() => { speedRef.current = speed; }, [speed]);
  useEffect(() => { totalRef.current = totalDekads; }, [totalDekads]);

  // Interval de avance.
  useEffect(() => {
    if (!isPlaying) return;
    if (totalRef.current <= 0) return;

    // Tick cada (1000 / (base * speed)) ms.
    const tickMs = 1000 / (BASE_DEKADS_PER_SEC * speedRef.current);
    const id = setInterval(() => {
      const next = currentRef.current + 1;
      if (next >= totalRef.current - 1) {
        setCurrentDekad(totalRef.current - 1);
        setIsPlaying(false);
      } else {
        setCurrentDekad(next);
      }
    }, tickMs);

    return () => clearInterval(id);
  }, [isPlaying, speed]); // re-crear interval si cambia speed

  const play = useCallback(() => {
    // Si está al final, resetear al inicio.
    if (currentRef.current >= totalRef.current - 1) {
      setCurrentDekad(0);
    }
    setIsPlaying(true);
  }, []);

  const pause = useCallback(() => setIsPlaying(false), []);
  const toggle = useCallback(() => {
    setIsPlaying((p) => {
      if (!p && currentRef.current >= totalRef.current - 1) {
        setCurrentDekad(0);
      }
      return !p;
    });
  }, []);

  const seek = useCallback((index: number) => {
    const clamped = Math.max(0, Math.min(totalRef.current - 1, index));
    setCurrentDekad(clamped);
    setIsPlaying(false); // pausar al hacer seek manual
  }, []);

  const setSpeed = useCallback((s: 1 | 2 | 4) => setSpeedState(s), []);

  return {
    currentDekad,
    isPlaying,
    speed,
    play,
    pause,
    toggle,
    seek,
    setSpeed,
  };
}