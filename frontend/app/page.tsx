import { Suspense } from 'react';
import { Dashboard } from './dashboard';

export default function Home() {
  return <Suspense fallback={<p className="loading" role="status">Cargando observatorio…</p>}>
    <Dashboard />
  </Suspense>;
}
