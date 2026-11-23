/** Quién está dentro y qué puede hacer. */
export interface Usuario {
  usuario: string;
  rol: 'admin' | 'usuario';
  restante: number;
}
