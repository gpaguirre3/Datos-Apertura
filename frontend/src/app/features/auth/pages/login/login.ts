import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';

import { AuthService } from '../../../../core/services/auth.service';
import { Alerta } from '../../../../shared/ui/alerta/alerta';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [FormsModule, Alerta],
  templateUrl: './login.html',
  styleUrl: './login.scss',
})
export class Login {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  usuario = '';
  clave = '';
  readonly enviando = signal(false);
  readonly error = signal<string | null>(null);

  constructor() {
    // Se le dice por qué está aquí otra vez.
    const motivos: Record<string, string> = {
      sesion: 'Tu sesión terminó por inactividad. Vuelve a entrar.',
      'otro-equipo': 'Tu sesión se cerró porque se entró con tu usuario desde otro equipo.',
    };
    const motivo = inject(ActivatedRoute).snapshot.queryParamMap.get('motivo') ?? '';
    if (motivos[motivo]) {
      this.error.set(motivos[motivo]);
    }
  }

  entrar(): void {
    if (this.enviando() || !this.usuario.trim() || !this.clave) {
      return;
    }
    this.enviando.set(true);
    this.error.set(null);
    this.auth.login(this.usuario.trim(), this.clave).subscribe({
      next: () => {
        this.enviando.set(false);
        this.router.navigate(['/procesos']);
      },
      error: (e) => {
        this.enviando.set(false);
        this.clave = '';
        this.error.set(e.mensaje ?? 'No se pudo entrar.');
      },
    });
  }
}
