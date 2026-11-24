import { Component, DestroyRef, computed, effect, inject, input, signal } from '@angular/core';

import { FilaAvance } from '../../models/proceso.model';

type Filtro = 'todos' | 'ok' | 'error';

const PANTALLA_REMOTA = '/Apertura/pantalla/vnc.html?autoconnect=1&resize=scale&reconnect=1';

@Component({
  selector: 'app-tabla-avance',
  standalone: true,
  templateUrl: './tabla-avance.html',
  styleUrl: './tabla-avance.scss',
})
export class TablaAvance {
  readonly filas = input.required<FilaAvance[]>();
  readonly terminado = input(false);
  readonly filtro = signal<Filtro>('todos');

  private pantalla: Window | null = null;

  readonly hayCaptcha = computed(() => this.filas().some((fila) => fila[1] === 'CAPTCHA'));

  readonly visibles = computed(() => {
    const f = this.filtro();
    if (f === 'todos') return this.filas();
    return this.filas().filter((fila) => (f === 'ok' ? this.esOk(fila[1]) : !this.esOk(fila[1])));
  });

  constructor() {
    effect(() => {
      if (this.terminado()) this.cerrarPantalla();
    });
    inject(DestroyRef).onDestroy(() => this.cerrarPantalla());
  }

  abrirPantalla(): void {
    this.pantalla = window.open(PANTALLA_REMOTA, 'pantalla-remota');
    this.pantalla?.focus();
  }

  private cerrarPantalla(): void {
    if (this.pantalla && !this.pantalla.closed) this.pantalla.close();
    this.pantalla = null;
  }

  esOk(estado: string): boolean {
    return estado === 'OK' || estado === 'OMITIDO';
  }

  clase(estado: string): string {
    if (this.esOk(estado)) return 'fila--ok';
    if (estado === 'REINTENTANDO' || estado === 'CAPTCHA') return 'fila--espera';
    if (estado === 'CANCELADO') return 'fila--cancelado';
    return 'fila--error';
  }
}
