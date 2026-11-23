import { Component, inject, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { SesionService } from '../../core/services/sesion.service';
import { Header } from '../header/header';
import { Sidebar } from '../sidebar/sidebar';

/** Marco de las pantallas con sesión: barra lateral, cabecera y contenido. */
@Component({
  selector: 'app-main-layout',
  standalone: true,
  imports: [RouterOutlet, Header, Sidebar],
  templateUrl: './main-layout.html',
  styleUrl: './main-layout.scss',
})
export class MainLayout {
  readonly lateralAbierta = signal(false);

  private readonly sesion = inject(SesionService);
}
