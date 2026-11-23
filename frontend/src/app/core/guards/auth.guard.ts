import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';

import { AuthService } from '../services/auth.service';

export const authGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (auth.autenticado()) {
    return true;
  }
  // La cookie no se puede leer desde aquí: se le pregunta al servidor si vale.
  return auth.recuperarSesion().pipe(
    map(() => true),
    catchError(() => of(router.createUrlTree(['/login']))),
  );
};
