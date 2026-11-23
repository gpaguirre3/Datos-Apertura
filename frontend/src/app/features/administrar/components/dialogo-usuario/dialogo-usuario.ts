import {
  Component,
  ElementRef,
  effect,
  input,
  output,
  viewChild,
} from '@angular/core';
import { FormsModule } from '@angular/forms';

import { Alerta } from '../../../../shared/ui/alerta/alerta';
import { CampoClave } from '../../../../shared/ui/campo-clave/campo-clave';

export interface UsuarioNuevo {
  usuario: string;
  clave: string;
  rol: string;
}

@Component({
  selector: 'app-dialogo-usuario',
  standalone: true,
  imports: [FormsModule, Alerta, CampoClave],
  templateUrl: './dialogo-usuario.html',
})
export class DialogoUsuario {
  readonly abierto = input(false);
  readonly guardando = input(false);
  readonly error = input<string | null>(null);

  readonly crear = output<UsuarioNuevo>();
  readonly cerrar = output<void>();

  private readonly dialogo = viewChild.required<ElementRef<HTMLDialogElement>>('dialogo');

  datos: UsuarioNuevo = { usuario: '', clave: '', rol: 'usuario' };

  constructor() {
    effect(() => {
      const elemento = this.dialogo().nativeElement;
      if (this.abierto()) {
        this.datos = { usuario: '', clave: '', rol: 'usuario' };
        if (!elemento.open) {
          elemento.showModal();
        }
      } else if (elemento.open) {
        elemento.close();
      }
    });
  }

  enviar(): void {
    if (this.guardando()) {
      return;
    }
    this.crear.emit({ ...this.datos, usuario: this.datos.usuario.trim() });
  }
}
