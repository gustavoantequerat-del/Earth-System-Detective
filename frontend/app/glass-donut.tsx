'use client';

import { useEffect, useRef } from 'react';
import * as THREE from 'three';

export interface DonutSlice {
  label: string;
  color: string;
  value: number;
}

interface Props {
  slices: DonutSlice[];
  active: number | null;
  onActive: (index: number | null) => void;
  onUnavailable: () => void;
}

export default function GlassDonut({ slices, active, onActive, onUnavailable }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const selection = useRef(active);

  useEffect(() => { selection.current = active; }, [active]);
  useEffect(() => {
    const mount = host.current;
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('webgl2', { alpha: true, antialias: true });
    if (!mount || !context) {
      onUnavailable();
      return;
    }

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ canvas, context, alpha: true, antialias: true });
    } catch {
      onUnavailable();
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.12;
    canvas.setAttribute('aria-hidden', 'true');
    mount.append(canvas);

    const scene = new THREE.Scene();
    const root = new THREE.Group();
    root.rotation.y = -0.38;
    scene.add(root, new THREE.AmbientLight(0xd6e5ff, 1.5));
    const camera = new THREE.PerspectiveCamera(36, 1, .1, 50);
    camera.position.set(0, 5.1, 5.2);
    camera.lookAt(0, 0.05, 0);
    const lights = [
      { color: 0xffffff, intensity: 3.1, position: [2, 5, 4] },
      { color: 0x559cff, intensity: 2.4, position: [-4, 1, 2] },
      { color: 0xe7ebff, intensity: 2.2, position: [0, 4, -5] },
    ];
    lights.forEach(({ color, intensity, position }) => {
      const light = new THREE.DirectionalLight(color, intensity);
      light.position.set(position[0], position[1], position[2]);
      scene.add(light);
    });
    const halo = new THREE.Mesh(new THREE.RingGeometry(2.34, 2.36, 96),
      new THREE.MeshBasicMaterial({ color: '#73a7ff', transparent: true, opacity: .44, side: THREE.DoubleSide }));
    halo.rotation.x = -Math.PI / 2;
    halo.position.y = -.38;
    root.add(halo);

    const total = slices.reduce((sum, slice) => sum + slice.value, 0);
    let angle = Math.PI / 2;
    const pieces = slices.map((slice, index) => {
      const sweep = slice.value / total * 2 * Math.PI;
      const gap = Math.min(sweep * .13, .022);
      const start = angle + gap;
      const end = angle + sweep - gap;
      angle += sweep;
      const outer = 2.04;
      const inner = 1.11;
      const shape = new THREE.Shape();
      shape.absarc(0, 0, outer, start, end, false);
      shape.lineTo(Math.cos(end) * inner, Math.sin(end) * inner);
      shape.absarc(0, 0, inner, end, start, true);
      shape.closePath();
      const geometry = new THREE.ExtrudeGeometry(shape, {
        depth: .45, curveSegments: Math.max(9, Math.ceil(sweep * 13)), bevelEnabled: true,
        bevelThickness: .035, bevelSize: Math.min(.035, gap), bevelSegments: 3,
      });
      geometry.rotateX(-Math.PI / 2);
      geometry.translate(0, -.22, 0);
      const tint = new THREE.Color(slice.color);
      const material = new THREE.MeshPhysicalMaterial({
        color: tint.clone().lerp(new THREE.Color('white'), .2), attenuationColor: tint,
        attenuationDistance: .65, roughness: .12, transmission: .64, ior: 1.48, thickness: 1.25,
        clearcoat: 1, clearcoatRoughness: .035, specularIntensity: 1.25,
        emissive: tint, emissiveIntensity: .25,
      });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.userData.index = index;
      root.add(mesh);
      return mesh;
    });

    const raycaster = new THREE.Raycaster();
    const point = new THREE.Vector2();
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    let frame = 0;
    let visible = true;
    let needsRender = true;
    let drag: { id: number; x: number; y: number } | null = null;
    let velocity = 0;
    const resize = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (!width || !height) return;
      camera.aspect = width / height;
      camera.position.multiplyScalar((camera.aspect < 1.05 ? 8.5 : 7.5) / camera.position.length());
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
      needsRender = true;
    });
    const intersection = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; });
    resize.observe(mount);
    intersection.observe(mount);

    function display() {
      frame = requestAnimationFrame(display);
      if (!visible || document.hidden) return;
      if (!drag && !reduced.matches && Math.abs(velocity) > .001) {
        root.rotation.y += velocity;
        velocity *= .9;
        needsRender = true;
      }
      for (const piece of pieces) {
        const highlighted = selection.current === piece.userData.index;
        const height = highlighted ? .15 : 0;
        if (Math.abs(piece.position.y - height) > .001) {
          piece.position.y = reduced.matches ? height : THREE.MathUtils.lerp(piece.position.y, height, .2);
          piece.material.emissiveIntensity = highlighted ? .5 : .25;
          needsRender = true;
        }
      }
      if (needsRender) {
        renderer.render(scene, camera);
        needsRender = false;
      }
    }
    function down(event: PointerEvent) {
      if (!event.isPrimary || event.button !== 0) return;
      drag = { id: event.pointerId, x: event.clientX, y: event.clientY };
      canvas.setPointerCapture(event.pointerId);
      canvas.classList.add('dragging');
      velocity = 0;
      onActive(null);
    }
    function move(event: PointerEvent) {
      if (drag?.id === event.pointerId) {
        velocity = (event.clientX - drag.x) * .009;
        root.rotation.y += velocity;
        root.rotation.x = THREE.MathUtils.clamp(root.rotation.x + (event.clientY - drag.y) * .006, -.3, .3);
        needsRender = true;
        drag = { id: event.pointerId, x: event.clientX, y: event.clientY };
        return;
      }
      if (event.pointerType === 'touch') return;
      const rect = canvas.getBoundingClientRect();
      point.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
      raycaster.setFromCamera(point, camera);
      onActive(raycaster.intersectObjects(pieces)[0]?.object.userData.index ?? null);
    }
    function end(event: PointerEvent) {
      if (drag?.id !== event.pointerId) return;
      drag = null;
      canvas.classList.remove('dragging');
    }
    function leave() { if (!drag) onActive(null); }
    function lost(event: Event) { event.preventDefault(); onUnavailable(); }
    canvas.addEventListener('pointerdown', down);
    canvas.addEventListener('pointermove', move);
    canvas.addEventListener('pointerleave', leave);
    canvas.addEventListener('lostpointercapture', end);
    canvas.addEventListener('webglcontextlost', lost);
    display();

    return () => {
      cancelAnimationFrame(frame);
      resize.disconnect();
      intersection.disconnect();
      canvas.removeEventListener('pointerdown', down);
      canvas.removeEventListener('pointermove', move);
      canvas.removeEventListener('pointerleave', leave);
      canvas.removeEventListener('lostpointercapture', end);
      canvas.removeEventListener('webglcontextlost', lost);
      for (const mesh of [halo, ...pieces]) {
        mesh.geometry.dispose();
        mesh.material.dispose();
      }
      renderer.dispose();
      canvas.remove();
    };
  }, [slices, onActive, onUnavailable]);

  return <div className="glass-canvas" ref={host} />;
}
