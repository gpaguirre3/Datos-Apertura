import { Routes } from '@angular/router';

export const PROCESOS_ROUTES: Routes = [
  {
    path: '',
    title: 'Consultas · Apertura de Datos',
    data: { pagina: 'aperturas' },
    loadComponent: () => import('./pages/procesos/procesos').then((m) => m.Procesos),
  },
  {
    path: 'obtener-datos',
    title: 'Obtener datos · Apertura de Datos',
    data: { pagina: 'obtener-datos' },
    loadComponent: () => import('./pages/procesos/procesos').then((m) => m.Procesos),
  },
];
