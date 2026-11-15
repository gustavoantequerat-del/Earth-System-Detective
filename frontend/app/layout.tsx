import type { Metadata } from 'next';
import '@fontsource-variable/overpass';
import './globals.css';
import './mission.css';
import './insights.css';

export const metadata: Metadata = {
  title: 'Detector de huella humana | Agua de Bolivia',
  description: 'Evidencia satelital para autoridades del agua, ONG y organismos de cooperación: qué lagos y ríos de Bolivia pierden agua, por qué y dónde actuar primero.',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="es"><body>{children}</body></html>;
}
