import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../../environments/environment';
import { AccionUsuario, RespuestaUsuarios } from '../models/admin.model';

/** Usuarios, registros y configuración: lo que el administrador puede tocar. */
@Injectable({ providedIn: 'root' })
export class AdminService {
  private readonly http = inject(HttpClient);
  private readonly url = `${environment.apiUrl}/admin`;

  usuarios(): Observable<RespuestaUsuarios> {
    return this.http.get<RespuestaUsuarios>(`${this.url}/usuarios`);
  }

  crear(datos: { usuario: string; clave: string; rol: string }): Observable<RespuestaUsuarios> {
    return this.http.post<RespuestaUsuarios>(`${this.url}/usuarios`, datos);
  }

  accion(
    usuario: string,
    accion: AccionUsuario,
    datos: Record<string, unknown> = {},
  ): Observable<RespuestaUsuarios> {
    return this.http.post<RespuestaUsuarios>(`${this.url}/usuarios/${encodeURIComponent(usuario)}`, {
      accion,
      ...datos,
    });
  }
}
