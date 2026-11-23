import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';

import { TokenService } from '../services/token.service';

const SEGUROS = ['GET', 'HEAD', 'OPTIONS'];

/**
 * La sesión viaja en una cookie que el navegador manda sola, así que aquí solo
 * hay que pedir que la incluya y devolver el valor anti-CSRF en las peticiones
 * que cambian algo: eso es lo que demuestra al servidor que salen de aquí.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const csrf = inject(TokenService).csrf();
  const cabeceras: Record<string, string> =
    !SEGUROS.includes(req.method) && csrf ? { 'X-CSRF-Token': csrf } : {};

  return next(req.clone({ withCredentials: true, setHeaders: cabeceras }));
};
