import { Component, computed, inject, signal } from '@angular/core';
import { concat, last } from 'rxjs';

import { Alerta } from '../../../../shared/ui/alerta/alerta';
import { Cargando } from '../../../../shared/ui/cargando/cargando';
import { CambiosUsuario, DialogoEditar } from '../../components/dialogo-editar/dialogo-editar';
import { DialogoUsuario, UsuarioNuevo } from '../../components/dialogo-usuario/dialogo-usuario';
import { TablaUsuarios } from '../../components/tabla-usuarios/tabla-usuarios';
import { RespuestaUsuarios, UsuarioAdmin } from '../../models/admin.model';
import { AuthService } from '../../../../core/services/auth.service';
import { AdminService } from '../../services/admin.service';

/** La lista de usuarios. Crear y editar se hacen en ventanas flotantes. */
@Component({
  selector: 'app-usuarios',
  standalone: true,
  imports: [Alerta, Cargando, TablaUsuarios, DialogoUsuario, DialogoEditar],
  templateUrl: './usuarios.html',
  styleUrl: './usuarios.scss',
})
export class Usuarios {
  private readonly admin = inject(AdminService);
  private readonly auth = inject(AuthService);

  readonly usuarios = signal<UsuarioAdmin[]>([]);
  readonly yo = signal('');
  readonly cargando = signal(true);
  readonly error = signal<string | null>(null);
  readonly aviso = signal<string | null>(null);

  readonly nuevoAbierto = signal(false);
  readonly creando = signal(false);
  readonly errorNuevo = signal<string | null>(null);

  readonly editando = signal<UsuarioAdmin | null>(null);
  readonly guardando = signal(false);
  readonly errorEditar = signal<string | null>(null);
  readonly editandoEsYo = computed(() => this.editando()?.usuario === this.yo());

  constructor() {
    this.cargar();
  }

  private aplicar(r: RespuestaUsuarios): void {
    this.usuarios.set(r.usuarios);
    this.yo.set(r.yo);
  }

  private motivo(e: unknown, porDefecto: string): string {
    return (e as { error?: { error?: string } })?.error?.error ?? porDefecto;
  }

  cargar(): void {
    this.cargando.set(true);
    this.admin.usuarios().subscribe({
      next: (r) => {
        this.aplicar(r);
        this.cargando.set(false);
      },
      error: (e) => {
        this.error.set(this.motivo(e, 'No se pudo cargar la lista.'));
        this.cargando.set(false);
      },
    });
  }

  abrirNuevo(): void {
    this.errorNuevo.set(null);
    this.nuevoAbierto.set(true);
  }

  crear(datos: UsuarioNuevo): void {
    if (!datos.usuario || datos.clave.length < 4) {
      this.errorNuevo.set('Escribe el usuario y una contraseña de al menos 4 caracteres.');
      return;
    }
    this.errorNuevo.set(null);
    this.aviso.set(null);
    this.creando.set(true);
    this.admin.crear(datos).subscribe({
      next: (r) => {
        this.aplicar(r);
        this.creando.set(false);
        this.nuevoAbierto.set(false);
        this.aviso.set(`Usuario «${datos.usuario}» creado.`);
      },
      error: (e) => {
        this.creando.set(false);
        // El error se queda dentro de la ventana: ahí está el formulario que hay que corregir.
        this.errorNuevo.set(this.motivo(e, 'No se pudo crear el usuario.'));
      },
    });
  }

  abrirEditar(u: UsuarioAdmin): void {
    this.errorEditar.set(null);
    this.editando.set(u);
  }

  cerrarEditar(): void {
    this.editando.set(null);
  }

  guardar(cambios: CambiosUsuario): void {
    if (cambios.clave !== undefined && cambios.clave.length < 4) {
      this.errorEditar.set('La contraseña debe tener al menos 4 caracteres.');
      return;
    }
    if (cambios.nombre !== undefined && !/^[a-z0-9._-]{3,30}$/.test(cambios.nombre)) {
      this.errorEditar.set(
        'Usuario de 3 a 30 caracteres: letras, números, punto, guion o guion bajo.',
      );
      return;
    }
    const eraYo = cambios.usuario === this.yo();
    const destino = cambios.nombre ?? cambios.usuario;
    const peticiones = [];
    if (cambios.nombre) {
      peticiones.push(this.admin.accion(cambios.usuario, 'nombre', { nombre: cambios.nombre }));
    }
    if (cambios.rol) {
      peticiones.push(this.admin.accion(destino, 'rol', { rol: cambios.rol }));
    }
    if (cambios.clave) {
      peticiones.push(this.admin.accion(destino, 'clave', { clave: cambios.clave }));
    }
    if (!peticiones.length) {
      this.cerrarEditar();
      return;
    }

    this.errorEditar.set(null);
    this.aviso.set(null);
    this.guardando.set(true);
    concat(...peticiones)
      .pipe(last())
      .subscribe({
        next: (r) => {
          this.aplicar(r);
          this.guardando.set(false);
          this.cerrarEditar();
          this.aviso.set(
            cambios.nombre
              ? `«${cambios.usuario}» ahora se llama «${cambios.nombre}».`
              : `«${cambios.usuario}» actualizado.`,
          );
          if (eraYo && cambios.nombre) {
            this.auth.recuperarSesion().subscribe({ error: () => undefined });
          }
        },
        error: (e) => {
          this.guardando.set(false);
          this.errorEditar.set(this.motivo(e, 'No se pudo guardar.'));
          this.cargar();
        },
      });
  }

  eliminar(usuario: string): void {
    this.errorEditar.set(null);
    this.aviso.set(null);
    this.guardando.set(true);
    this.admin.accion(usuario, 'eliminar').subscribe({
      next: (r) => {
        this.aplicar(r);
        this.guardando.set(false);
        this.cerrarEditar();
        this.aviso.set(`Usuario «${usuario}» eliminado.`);
      },
      error: (e) => {
        this.guardando.set(false);
        this.errorEditar.set(this.motivo(e, 'No se pudo eliminar.'));
      },
    });
  }
}
