import { Component, input, output } from '@angular/core';

import { Proceso } from '../../models/proceso.model';

@Component({
  selector: 'app-selector-proceso',
  standalone: true,
  templateUrl: './selector-proceso.html',
  styleUrl: './selector-proceso.scss',
})
export class SelectorProceso {
  readonly procesos = input.required<Proceso[]>();
  readonly elegido = input<string | null>(null);
  readonly elegir = output<Proceso>();
}
