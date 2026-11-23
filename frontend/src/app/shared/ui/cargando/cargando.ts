import { Component, input } from '@angular/core';

/** Rueda de espera con un texto al lado. */
@Component({
  selector: 'app-cargando',
  standalone: true,
  templateUrl: './cargando.html',
  styleUrl: './cargando.scss',
})
export class Cargando {
  readonly texto = input('Cargando…');
}
