/** Un proceso del catálogo, tal como lo describe el servidor. */
export interface Proceso {
  clave: string;
  nombre: string;
  detalle: string;
  pagina: 'aperturas' | 'obtener-datos';
  extension: '.xlsx' | '.zip';
  segundo_archivo?: boolean;
  requiere_mina?: boolean;
  disponible: boolean;
  motivo?: string;
  ordenes?: { valor: string; texto: string }[];
}

export type FilaAvance = [string, string, string];

export interface EstadoTrabajo {
  total: number;
  fin: boolean;
  filas: FilaAvance[];
  ok: number;
  errores: number;
  reintentando: number;
  cancelando: boolean;
  hechos: number;
  nombre: string;
}

export interface TrabajoLanzado {
  id: string;
  nombre: string;
  total: number;
}

export interface VistaPrevia {
  proceso: string;
  columnas: string[];
  filas: string[][];
  veces: number[];
  total: number;
  distintos: number;
  agrupada: boolean;
  recortada: boolean;
}
