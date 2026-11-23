import { Component, input, output } from '@angular/core';

import { UsuarioAdmin } from '../../models/admin.model';

/** La lista de usuarios */
@Component({
  selector: 'app-tabla-usuarios',
  standalone: true,
  templateUrl: './tabla-usuarios.html',
  styleUrl: './tabla-usuarios.scss',
})
export class TablaUsuarios {
  readonly usuarios = input.required<UsuarioAdmin[]>();
  readonly yo = input<string>('');
  readonly editar = output<UsuarioAdmin>();
}
