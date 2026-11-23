import { Component, input, model, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-campo-clave',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './campo-clave.html',
  styleUrl: './campo-clave.scss',
})
export class CampoClave {
  readonly valor = model<string>('');
  readonly nombre = input('clave');
  readonly marcador = input('');

  readonly viendo = signal(false);

  ver(mostrar: boolean): void {
    this.viendo.set(mostrar);
  }
}
