import { DestroyRef, Injectable, effect, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { EMPTY, catchError, exhaustMap, filter, interval } from 'rxjs';

import { AuthService } from './auth.service';

/** Cada cuánto se comprueba que la sesión siga siendo la válida. */
const LATIDO_MS = 1000;

/**
 * Cuenta atrás de la sesión y vigilancia de que siga abierta.
 */
@Injectable({ providedIn: 'root' })
export class SesionService {
  private readonly auth = inject(AuthService);
  private readonly segundos = signal(0);

  readonly restante = this.segundos.asReadonly();

  constructor() {
    effect(() => {
      const usuario = this.auth.usuario();
      this.segundos.set(usuario ? Math.max(0, Math.floor(usuario.restante)) : 0);
    });

    interval(1000)
      .pipe(takeUntilDestroyed(inject(DestroyRef)))
      .subscribe(() => {
        if (!this.auth.autenticado() || this.segundos() <= 0) {
          return;
        }
        const quedan = this.segundos() - 1;
        this.segundos.set(quedan);
        if (quedan <= 0) {
          this.auth.salir('sesion');
        }
      });

    // exhaustMap: si una comprobación tarda, los latidos de mientras se ignoran
    // en vez de apilarse.
    interval(LATIDO_MS)
      .pipe(
        filter(() => this.auth.autenticado()),
        exhaustMap(() => this.auth.recuperarSesion().pipe(catchError(() => EMPTY))),
        takeUntilDestroyed(inject(DestroyRef)),
      )
      .subscribe();
  }
}
