import { Injectable } from '@angular/core';

const COOKIE_CSRF = 'sacardatos_csrf';
/** Resto de cuando el token se guardaba en el navegador; se limpia al arrancar. */
const CLAVE_ANTIGUA = 'sacardatos.token';

/**
 * El token de sesión ya no se guarda aquí: viaja en una cookie que JavaScript
 * no puede leer. Lo único que esta clase necesita es el valor anti-CSRF, que sí
 * es legible y hay que devolver en cada petición que cambia algo.
 */
@Injectable({ providedIn: 'root' })
export class TokenService {
  constructor() {
    try {
      localStorage.removeItem(CLAVE_ANTIGUA);
    } catch {
      /* sin almacenamiento no hay nada que limpiar */
    }
  }

  csrf(): string | null {
    const marca = `${COOKIE_CSRF}=`;
    const cookie = document.cookie.split('; ').find((c) => c.startsWith(marca));
    return cookie ? decodeURIComponent(cookie.slice(marca.length)) : null;
  }
}
