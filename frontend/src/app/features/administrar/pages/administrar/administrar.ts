import { Component } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';

/** Marco de la administración: título y migas sobre la pantalla de turno. */
@Component({
  selector: 'app-administrar',
  standalone: true,
  imports: [RouterOutlet, RouterLink],
  templateUrl: './administrar.html',
  styleUrl: './administrar.scss',
})
export class Administrar {}
