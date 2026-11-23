import { Routes } from '@angular/router';

import { adminGuard } from './core/guards/admin.guard';
import { authGuard } from './core/guards/auth.guard';
import { AUTH_ROUTES } from './features/auth/auth.routes';

export const routes: Routes = [
  ...AUTH_ROUTES,
  {
    path: '',
    canActivate: [authGuard],
    loadComponent: () => import('./layout/main-layout/main-layout').then((m) => m.MainLayout),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'procesos' },
      {
        path: 'procesos',
        loadChildren: () =>
          import('./features/procesos/procesos.routes').then((m) => m.PROCESOS_ROUTES),
      },
      {
        path: 'administrar',
        canActivate: [adminGuard],
        loadChildren: () =>
          import('./features/administrar/administrar.routes').then((m) => m.ADMINISTRAR_ROUTES),
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
