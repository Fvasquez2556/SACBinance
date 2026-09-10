# Auditorías

Revisiones externas del sistema, una carpeta por fecha.

## 2026-09-10

Auditoría de solo lectura sobre el servidor y una copia consistente de SQLite
tomada a las 21:57 UTC. Código auditado: `fbed25ca`. **14 hallazgos, los 14
verificados y corregidos** entre el 10-sep por la noche y la madrugada del 11
(esquemas v10 y v11).

Lo que hay aquí:

| | |
|---|---|
| `AUDITORIA.md` | el informe completo |
| `findings.json` | los 14 hallazgos en estructurado |
| `*.py` | los scripts que produjeron cada medición |
| `*_results.json`, `*_summary.json`, `deep_checks.json` | las conclusiones |
| `provenance.json`, `queries.json`, `runtime.json` | de dónde salió cada dato |

Lo que **no** está, y por qué: las copias de la base (160 MB entre las dos), la
copia del repo (recuperable por su commit), el visor del informe y los volcados
de filas crudas. Todo eso se regenera con los scripts de esta misma carpeta.

Dos cosas del informe que no estaban en la tabla de hallazgos y conviene no
perder:

- **Medición independiente de la entrada en el hoyo.** 24 símbolos elegidos por
  hash del nombre, sin mirar rendimientos: 134 de 171 oportunidades se llenan,
  y las tres variantes de stop dan −0.382%, −0.393% y −0.165% netos, con los
  intervalos cruzando cero. Entre los ejemplos elegidos *por haber subido*, la
  misma regla promedia +0.545%. Es la misma conclusión a la que llegamos por
  otro camino, con otra muestra.
- **El coste real.** Con 0.10% de comisión por lado, ganar 3.2% neto exige
  **3.41% bruto**. El `coste_operacion_pct = 0.5` del sistema mete además el
  deslizamiento, así que es más conservador.
