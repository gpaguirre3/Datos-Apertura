import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, tap } from 'rxjs';

import { environment } from '../../../environments/environment';
import { Usuario } from '../models/usuario.model';

/** Sesión: quién entró, con qué permisos y cuánto le queda. */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private readonly url = `${environment.apiUrl}/auth`;

  readonly usuario = signal<Usuario | null>(null);
  readonly autenticado = computed(() => !!this.usuario());
  readonly esAdmin = computed(() => this.usuario()?.rol === 'admin');

  login(usuario: string, clave: string): Observable<Usuario> {
    return this.http
      .post<Usuario>(`${this.url}/login`, { usuario, clave })
      .pipe(tap((u) => this.usuario.set(u)));
  }

  /** Al abrir la app pregunta quién es: la cookie va sola y el servidor responde. */
  recuperarSesion(): Observable<Usuario> {
    return this.http.get<Usuario>(`${this.url}/me`).pipe(tap((u) => this.usuario.set(u)));
  }

  /** Cierra sesión en el servidor */
  salir(motivo?: string): void {
    if (this.usuario()) {
      this.http.post(`${this.url}/logout`, {}).subscribe({ error: () => undefined });
    }
    this.limpiar();
    this.router.navigate(['/login'], motivo ? { queryParams: { motivo } } : undefined);
  }

  limpiar(): void {
    this.usuario.set(null);
  }
}
