import { Component, ElementRef, input, output, signal, viewChild } from '@angular/core';

import { tamanoLegible } from '../../../../shared/utils/formato';

@Component({
  selector: 'app-zona-archivo',
  standalone: true,
  templateUrl: './zona-archivo.html',
  styleUrl: './zona-archivo.scss',
})
export class ZonaArchivo {
  readonly extension = input.required<string>();
  readonly texto = input('Arrastra el archivo aquí o haz clic para elegirlo');
  readonly ayuda = input<string>('');
  readonly archivo = input<File | null>(null);
  readonly elegido = output<File | null>();

  private readonly entrada = viewChild.required<ElementRef<HTMLInputElement>>('entrada');
  readonly encima = signal(false);

  get descripcion(): string {
    const f = this.archivo();
    return f ? `${f.name} · ${tamanoLegible(f.size)}` : this.texto();
  }

  abrir(): void {
    this.entrada().nativeElement.click();
  }

  seleccionar(evento: Event): void {
    const lista = (evento.target as HTMLInputElement).files;
    this.elegido.emit(lista?.length ? lista[0] : null);
  }

  soltar(evento: DragEvent): void {
    evento.preventDefault();
    this.encima.set(false);
    const archivo = evento.dataTransfer?.files?.[0];
    if (archivo && archivo.name.toLowerCase().endsWith(this.extension())) {
      this.elegido.emit(archivo);
    }
  }
}
