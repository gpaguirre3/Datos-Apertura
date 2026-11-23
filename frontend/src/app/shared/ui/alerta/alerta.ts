import { Component, input } from '@angular/core';

/** Aviso de una línea: error, acierto o información. */
@Component({
  selector: 'app-alerta',
  standalone: true,
  templateUrl: './alerta.html',
  styleUrl: './alerta.scss',
})
export class Alerta {
  readonly texto = input<string | null>(null);
  readonly tipo = input<'error' | 'ok' | 'info'>('error');
}
