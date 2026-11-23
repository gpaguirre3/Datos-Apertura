import { Component, ElementRef, effect, input, output, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { Alerta } from '../../../../shared/ui/alerta/alerta';
import { CampoClave } from '../../../../shared/ui/campo-clave/campo-clave';
import { UsuarioAdmin } from '../../models/admin.model';

export interface CambiosUsuario {
  usuario: string;
  nombre?: string;
  clave?: string;
  rol?: string;
}

@Component({
  selector: 'app-dialogo-editar',
  standalone: true,
  imports: [FormsModule, Alerta, CampoClave],
  templateUrl: './dialogo-editar.html',
})
export class DialogoEditar {
  readonly usuario = input<UsuarioAdmin | null>(null);
  readonly esYo = input(false);
  readonly guardando = input(false);
  readonly error = input<string | null>(null);

  readonly guardar = output<CambiosUsuario>();
  readonly eliminar = output<string>();
  readonly cerrar = output<void>();

  private readonly dialogo = viewChild.required<ElementRef<HTMLDialogElement>>('dialogo');
  private readonly confirmacion = viewChild.required<ElementRef<HTMLDialogElement>>('confirmacion');

  readonly confirmando = signal(false);

  nombre = '';
  rol = 'usuario';
  clave = '';

  constructor() {
    effect(() => {
      const elemento = this.dialogo().nativeElement;
      const u = this.usuario();
      if (u) {
        this.confirmando.set(false);
        this.nombre = u.usuario;
        this.rol = u.rol;
        this.clave = '';
        if (!elemento.open) {
          elemento.showModal();
        }
      } else if (elemento.open) {
        elemento.close();
      }
    });

    effect(() => {
      const aviso = this.confirmacion().nativeElement;
      if (this.confirmando() && !aviso.open) {
        aviso.showModal();
      } else if (!this.confirmando() && aviso.open) {
        aviso.close();
      }
    });
  }

  /** Sin cambios no hay nada que guardar: el botón se queda apagado. */
  hayCambios(): boolean {
    const u = this.usuario();
    return !!u && (this.nombreLimpio() !== u.usuario || this.rol !== u.rol || this.clave.length > 0);
  }

  private nombreLimpio(): string {
    return this.nombre.trim().toLowerCase();
  }

  enviar(): void {
    const u = this.usuario();
    if (!u || this.guardando() || !this.hayCambios()) {
      return;
    }
    const nombre = this.nombreLimpio();
    this.guardar.emit({
      usuario: u.usuario,
      nombre: nombre !== u.usuario ? nombre : undefined,
      clave: this.clave || undefined,
      rol: this.rol !== u.rol ? this.rol : undefined,
    });
  }

  pedirEliminar(): void {
    this.confirmando.set(true);
  }

  confirmarEliminar(): void {
    const u = this.usuario();
    this.confirmando.set(false);
    if (u) {
      this.eliminar.emit(u.usuario);
    }
  }
}
