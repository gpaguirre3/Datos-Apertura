import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

import { ErrorApi } from '../models/respuesta.model';
import { AuthService } from '../services/auth.service';

/**
 * Traduce los errores de la API a algo que las pantallas puedan mostrar
 */
export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  return next(req).pipe(
    catchError((e: HttpErrorResponse) => {
      const cuerpo = e.error as ErrorApi | undefined;

      if (e.status === 401 && !req.url.endsWith('/auth/login')) {
        auth.limpiar();
        // El servidor distingue la sesión caducada de la cerrada por otro equipo.
        const motivo = cuerpo?.codigo === 'SESION_REEMPLAZADA' ? 'otro-equipo' : 'sesion';
        router.navigate(['/login'], { queryParams: { motivo } });
      }

      const mensaje =
        cuerpo?.error ??
        (e.status === 0 ? 'No se pudo conectar con el servidor.' : 'Ocurrió un error inesperado.');
      return throwError(() => ({ ...e, mensaje }));
    }),
  );
};
