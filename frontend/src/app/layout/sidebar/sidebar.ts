import { Component, inject, input, output } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

import { AuthService } from '../../core/services/auth.service';

interface Enlace {
  ruta: string;
  texto: string;
  icono: string;
  exacta?: boolean;
  soloAdmin?: boolean;
}

/** Barra lateral oscura con la navegación principal. */
@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [RouterLink, RouterLinkActive],
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.scss',
})
export class Sidebar {
  readonly abierta = input(false);
  readonly cerrar = output<void>();

  readonly auth = inject(AuthService);

  private readonly enlaces: Enlace[] = [
    { ruta: '/procesos', texto: 'Consultas', icono: '▣', exacta: true },
    { ruta: '/procesos/obtener-datos', texto: 'Obtener datos', icono: '⤓' },
    { ruta: '/administrar', texto: 'Administrar', icono: '⚙', soloAdmin: true },
  ];

  visibles(): Enlace[] {
    return this.enlaces.filter((e) => !e.soloAdmin || this.auth.esAdmin());
  }
}
