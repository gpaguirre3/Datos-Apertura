import { Routes } from '@angular/router';

export const ADMINISTRAR_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () => import('./pages/administrar/administrar').then((m) => m.Administrar),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'usuarios' },
      {
        path: 'usuarios',
        title: 'Usuarios · Apertura de Datos',
        loadComponent: () => import('./pages/usuarios/usuarios').then((m) => m.Usuarios),
      },
    ],
  },
];
