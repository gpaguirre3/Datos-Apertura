import { Component, computed, input, signal } from '@angular/core';

import { FilaAvance } from '../../models/proceso.model';

type Filtro = 'todos' | 'ok' | 'error';

@Component({
  selector: 'app-tabla-avance',
  standalone: true,
  templateUrl: './tabla-avance.html',
  styleUrl: './tabla-avance.scss',
})
export class TablaAvance {
  readonly filas = input.required<FilaAvance[]>();
  readonly filtro = signal<Filtro>('todos');

  readonly hayCaptcha = computed(() => this.filas().some((fila) => fila[1] === 'CAPTCHA'));

  readonly visibles = computed(() => {
    const f = this.filtro();
    if (f === 'todos') return this.filas();
    return this.filas().filter((fila) => (f === 'ok' ? this.esOk(fila[1]) : !this.esOk(fila[1])));
  });

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
