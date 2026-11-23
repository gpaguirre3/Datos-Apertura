/** Forma de los errores que devuelve la API. */
export interface ErrorApi {
  error: string;
  codigo?: 'SIN_SESION' | 'SIN_PERMISO' | 'SESION_REEMPLAZADA';
}
