import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../../environments/environment';
import { EstadoTrabajo, Proceso, TrabajoLanzado, VistaPrevia } from '../models/proceso.model';

@Injectable({ providedIn: 'root' })
export class ProcesosService {
  private readonly http = inject(HttpClient);
  private readonly url = environment.apiUrl;

  catalogo(): Observable<{ procesos: Proceso[] }> {
    return this.http.get<{ procesos: Proceso[] }>(`${this.url}/catalogo`);
  }

  lanzar(datos: {
    sitio: string;
    archivo: File;
    segundo?: File | null;
    orden?: string;
  }): Observable<TrabajoLanzado> {
    const cuerpo = new FormData();
    cuerpo.append('sitio', datos.sitio);
    cuerpo.append('excel', datos.archivo);
    if (datos.segundo) {
      cuerpo.append('zip2', datos.segundo);
    }
    if (datos.orden) {
      cuerpo.append('orden', datos.orden);
    }
    return this.http.post<TrabajoLanzado>(`${this.url}/procesos`, cuerpo);
  }

  vistaPrevia(datos: { sitio: string; archivo: File; segundo?: File | null }): Observable<VistaPrevia> {
    const cuerpo = new FormData();
    cuerpo.append('sitio', datos.sitio);
    cuerpo.append('excel', datos.archivo);
    if (datos.segundo) {
      cuerpo.append('zip2', datos.segundo);
    }
    return this.http.post<VistaPrevia>(`${this.url}/procesos/vista-previa`, cuerpo);
  }

  estado(id: string): Observable<EstadoTrabajo> {
    return this.http.get<EstadoTrabajo>(`${this.url}/procesos/${id}/estado`);
  }

  cancelar(id: string): Observable<{ ok: boolean }> {
    return this.http.post<{ ok: boolean }>(`${this.url}/procesos/${id}/cancelar`, {});
  }

  descargar(id: string): Observable<HttpResponseZip> {
    return this.http.get(`${this.url}/procesos/${id}/zip`, {
      responseType: 'blob',
      observe: 'response',
    }) as Observable<HttpResponseZip>;
  }
}

export interface HttpResponseZip {
  body: Blob | null;
  headers: { get(nombre: string): string | null };
}
