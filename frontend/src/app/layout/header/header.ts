import { Component, inject, output } from '@angular/core';

import { AuthService } from '../../core/services/auth.service';

/** Cabecera clara: quién está dentro y por dónde salir. */
@Component({
  selector: 'app-header',
  standalone: true,
  templateUrl: './header.html',
  styleUrl: './header.scss',
})
export class Header {
  readonly alternarMenu = output<void>();

  readonly auth = inject(AuthService);

  get inicial(): string {
    return (this.auth.usuario()?.usuario ?? '?').charAt(0).toUpperCase();
  }

  salir(): void {
    this.auth.salir();
  }
}
