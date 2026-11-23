import { Routes } from '@angular/router';

export const AUTH_ROUTES: Routes = [
  {
    path: 'login',
    title: 'Entrar · Apertura de Datos',
    loadComponent: () => import('./pages/login/login').then((m) => m.Login),
  },
];
