import { Component, DestroyRef, computed, effect, inject, signal } from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { Subscription, interval, map, switchMap } from 'rxjs';

import { environment } from '../../../../../environments/environment';
import { Alerta } from '../../../../shared/ui/alerta/alerta';
import { Cargando } from '../../../../shared/ui/cargando/cargando';
import { SelectorProceso } from '../../components/selector-proceso/selector-proceso';
import { TablaAvance } from '../../components/tabla-avance/tabla-avance';
import { VistaPreviaTabla } from '../../components/vista-previa/vista-previa';
import { ZonaArchivo } from '../../components/zona-archivo/zona-archivo';
import { EstadoTrabajo, Proceso, VistaPrevia } from '../../models/proceso.model';
import { ProcesosService } from '../../services/procesos.service';

@Component({
  selector: 'app-procesos',
  standalone: true,
  imports: [FormsModule, Alerta, Cargando, SelectorProceso, ZonaArchivo, TablaAvance, VistaPreviaTabla],
  templateUrl: './procesos.html',
  styleUrl: './procesos.scss',
})
export class Procesos {
  private readonly api = inject(ProcesosService);
  private readonly destroyRef = inject(DestroyRef);

  private readonly pagina = toSignal(
    inject(ActivatedRoute).data.pipe(map((d) => (d['pagina'] ?? 'aperturas') as Proceso['pagina'])),
    { initialValue: 'aperturas' as Proceso['pagina'] },
  );

  private readonly todos = signal<Proceso[]>([]);
  readonly cargandoCatalogo = signal(true);
  readonly procesos = computed(() => this.todos().filter((p) => p.pagina === this.pagina()));

  readonly elegido = signal<Proceso | null>(null);
  readonly archivo = signal<File | null>(null);
  readonly segundo = signal<File | null>(null);
  orden = 'consolidado';

  readonly previa = signal<VistaPrevia | null>(null);
  readonly leyendo = signal(false);

  readonly error = signal<string | null>(null);
  readonly lanzando = signal(false);
  readonly trabajo = signal<string | null>(null);
  readonly estado = signal<EstadoTrabajo | null>(null);
  readonly descargando = signal(false);
  private seguimiento?: Subscription;

  readonly titulo = computed(() =>
    this.pagina() === 'aperturas' ? 'Consultas' : 'Obtener datos',
  );
  readonly listo = computed(
    () =>
      !!this.elegido() &&
      !!this.archivo() &&
      !!this.previa() &&
      (!this.elegido()?.segundo_archivo || !!this.segundo()),
  );
  readonly porcentaje = computed(() => {
    const e = this.estado();
    return e && e.total ? Math.min(100, Math.round((e.hechos / e.total) * 100)) : 0;
  });

  constructor() {
    this.api
      .catalogo()
      .pipe(takeUntilDestroyed())
      .subscribe({
        next: (r) => {
          this.todos.set(r.procesos);
          this.cargandoCatalogo.set(false);
        },
        error: (e) => {
          this.cargandoCatalogo.set(false);
          this.error.set(e.mensaje ?? 'No se pudo cargar la lista de procesos.');
        },
      });

    effect(() => {
      this.pagina();
      this.elegido.set(null);
      this.limpiarArchivos();
    });
  }

  elegir(p: Proceso): void {
    this.elegido.set(p);
    this.error.set(null);
    this.limpiarArchivos();
  }

  private limpiarArchivos(): void {
    this.archivo.set(null);
    this.segundo.set(null);
    this.previa.set(null);
  }

  archivoElegido(archivo: File | null, cual: 'principal' | 'segundo' = 'principal'): void {
    if (cual === 'principal') {
      this.archivo.set(archivo);
    } else {
      this.segundo.set(archivo);
    }
    this.previa.set(null);
    this.error.set(null);

    const proceso = this.elegido();
    const principal = this.archivo();
    if (!proceso || !principal || (proceso.segundo_archivo && !this.segundo())) {
      return;
    }
    this.leyendo.set(true);
    this.api
      .vistaPrevia({ sitio: proceso.clave, archivo: principal, segundo: this.segundo() })
      .subscribe({
        next: (v) => {
          this.leyendo.set(false);
          this.previa.set(v);
        },
        error: (e) => {
          this.leyendo.set(false);
          this.error.set(e.mensaje ?? 'No se pudo leer el archivo.');
        },
      });
  }

  lanzar(): void {
    const proceso = this.elegido();
    const archivo = this.archivo();
    if (!proceso || !archivo || this.lanzando()) {
      return;
    }
    this.lanzando.set(true);
    this.error.set(null);
    this.estado.set(null);

    this.api
      .lanzar({
        sitio: proceso.clave,
        archivo,
        segundo: this.segundo(),
        orden: this.orden,
      })
      .subscribe({
        next: (r) => {
          this.lanzando.set(false);
          this.trabajo.set(r.id);
          this.seguir(r.id);
        },
        error: (e) => {
          this.lanzando.set(false);
          this.error.set(e.mensaje ?? 'No se pudo iniciar el proceso.');
        },
      });
  }

  private seguir(id: string): void {
    this.seguimiento?.unsubscribe();
    this.seguimiento = interval(environment.intervaloEstadoMs)
      .pipe(
        switchMap(() => this.api.estado(id)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (e) => {
          this.estado.set(e);
          if (e.fin) {
            this.seguimiento?.unsubscribe();
          }
        },
        error: (e) => {
          this.seguimiento?.unsubscribe();
          this.error.set(e.mensaje ?? 'Se perdió el seguimiento del proceso.');
        },
      });
  }

  cancelar(): void {
    const id = this.trabajo();
    if (id) {
      this.api.cancelar(id).subscribe({ error: () => undefined });
    }
  }

  descargar(): void {
    const id = this.trabajo();
    if (!id || this.descargando()) {
      return;
    }
    this.descargando.set(true);
    this.api.descargar(id).subscribe({
      next: (respuesta) => {
        this.descargando.set(false);
        if (!respuesta.body) {
          return;
        }
        const cabecera = respuesta.headers.get('Content-Disposition') ?? '';
        const nombre = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cabecera)?.[1];
        const url = URL.createObjectURL(respuesta.body);
        const enlace = document.createElement('a');
        enlace.href = url;
        enlace.download = decodeURIComponent(nombre ?? `resultados_${id}.zip`);
        enlace.click();
        URL.revokeObjectURL(url);
      },
      error: (e) => {
        this.descargando.set(false);
        this.error.set(e.mensaje ?? 'No se pudo descargar el ZIP.');
      },
    });
  }

  nuevo(): void {
    this.seguimiento?.unsubscribe();
    this.trabajo.set(null);
    this.estado.set(null);
    this.limpiarArchivos();
    this.error.set(null);
  }
}
