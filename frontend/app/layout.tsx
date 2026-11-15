import type { Metadata } from 'next';
import '@fontsource-variable/overpass';
import './globals.css';
import './mission.css';

export const metadata: Metadata = {
  title: 'Detector de huella humana | Agua de Bolivia',
  description: 'Explora desde satélite los lagos, los incendios y los cambios de vegetación en las cuencas de Bolivia.',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="es"><body>{children}</body></html>;
}
