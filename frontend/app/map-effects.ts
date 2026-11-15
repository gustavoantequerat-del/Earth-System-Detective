import { AmbientLight, DirectionalLight, LightingEffect } from '@deck.gl/core';

/** Iluminación compartida por los mapas 3D: luz cálida principal, relleno frío y ambiente suave. Da volumen a columnas, relieve y provincias. */
export const sceneLighting = new LightingEffect({
  ambient: new AmbientLight({ color: [255, 255, 255], intensity: 1.05 }),
  key: new DirectionalLight({ color: [255, 243, 224], intensity: 1.55, direction: [-3, -7, -5] }),
  fill: new DirectionalLight({ color: [150, 215, 235], intensity: 0.65, direction: [5, 3, -2] }),
});

/** Material para elementos extruidos: algo de brillo para que se lean las caras. */
export const extrudedMaterial = { ambient: 0.42, diffuse: 0.72, shininess: 40, specularColor: [60, 80, 86] as [number, number, number] };

export const accentRgb: [number, number, number] = [95, 224, 200];
