export interface UsuarioAdmin {
  usuario: string;
  rol: 'admin' | 'usuario';
  creado: string | null;
  actualizado: string | null;
  ultimo_acceso: string | null;
}

export interface RespuestaUsuarios {
  usuarios: UsuarioAdmin[];
  /** Quién pide la lista: no puede eliminarse ni desactivarse a sí mismo. */
  yo: string;
}

export type AccionUsuario = 'nombre' | 'clave' | 'rol' | 'eliminar';
