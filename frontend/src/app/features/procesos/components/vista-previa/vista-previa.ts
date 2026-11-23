import { Component, computed, input } from '@angular/core';

import { VistaPrevia } from '../../models/proceso.model';

interface FilaPrevia {
  numero: number;
  valores: string[];
  veces: number;
}

@Component({
  selector: 'app-vista-previa',
  standalone: true,
  templateUrl: './vista-previa.html',
  styleUrl: './vista-previa.scss',
})
export class VistaPreviaTabla {
  readonly datos = input.required<VistaPrevia>();

  readonly repetidas = computed(() => {
    const d = this.datos();
    return d.agrupada ? d.total - d.distintos : 0;
  });

  readonly filas = computed<FilaPrevia[]>(() =>
    this.datos().filas.map((valores, i) => ({
      numero: i + 1,
      valores,
      veces: (this.datos().veces ?? [])[i] ?? 1,
    })),
  );

  readonly mostradas = computed(() => this.datos().filas.length);
}
