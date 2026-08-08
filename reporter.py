"""
reporter.py — guarda el resultado de cada corrida, con TRES categorías:

  PASA       -> coincidió (comparación confiable)
  FALLA      -> no coincidió y la medición fue confiable (gap chico) -> sospechoso
  DESCARTADA -> el gap fue grande, no confiamos en la comparación -> no cuenta

La tasa de éxito se calcula SOLO sobre comparaciones confiables (PASA + FALLA),
así el ruido de arranque no infla ni ensucia el número.

Archivos en 'reportes/':
  - reporte_YYYYMMDD_HHMMSS.txt   (legible)
  - reporte_YYYYMMDD_HHMMSS.json  (datos)
"""

from __future__ import annotations

import datetime
import json
import os


class Reporter:
    def __init__(self, titulo="Validación potencia PCS (simulador vs OmniOps)",
                 gap_confiable_s=1.0):
        self.titulo = titulo
        self.gap_confiable_s = gap_confiable_s
        self.inicio = datetime.datetime.now()
        self.filas = []

    def registrar(self, hora, esperado, actual, razon, ok, gap):
        # decidir categoría según la confiabilidad de la medición (el gap)
        if gap is not None and gap > self.gap_confiable_s:
            categoria = "DESCARTADA"
        elif ok:
            categoria = "PASA"
        else:
            categoria = "FALLA"
        self.filas.append({
            "hora": hora, "esperado": round(esperado, 1),
            "actual": round(actual, 1), "razon": round(razon, 3),
            "gap": round(gap, 2) if gap is not None else None,
            "categoria": categoria,
        })

    def save(self, carpeta="reportes"):
        if not self.filas:
            print("(sin comparaciones que reportar)")
            return None
        os.makedirs(carpeta, exist_ok=True)
        stamp = self.inicio.strftime("%Y%m%d_%H%M%S")

        total = len(self.filas)
        paso = sum(1 for f in self.filas if f["categoria"] == "PASA")
        fallo = sum(1 for f in self.filas if f["categoria"] == "FALLA")
        descart = sum(1 for f in self.filas if f["categoria"] == "DESCARTADA")
        confiables = paso + fallo
        tasa = (paso / confiables * 100) if confiables else 0.0

        txt = os.path.join(carpeta, f"reporte_{stamp}.txt")
        with open(txt, "w", encoding="utf-8") as fh:
            fh.write(f"{self.titulo}\n")
            fh.write(f"Corrida: {self.inicio:%Y-%m-%d %H:%M:%S}\n")
            fh.write("=" * 56 + "\n\n")
            fh.write(f"Comparaciones totales : {total}\n")
            fh.write(f"  Confiables          : {confiables}\n")
            fh.write(f"    PASARON           : {paso}\n")
            fh.write(f"    FALLARON          : {fallo}\n")
            fh.write(f"  Descartadas (desfase): {descart}\n\n")
            fh.write(f"Tasa de éxito (solo confiables): {tasa:.1f}%\n\n")
            if fallo:
                fh.write("FALLAS confiables (revisar — posible bug):\n")
                for f in self.filas:
                    if f["categoria"] == "FALLA":
                        fh.write(f"  {f['hora']}: esperado={f['esperado']} "
                                 f"actual={f['actual']} razón={f['razon']} "
                                 f"(gap {f['gap']}s)\n")
            else:
                fh.write("Sin fallas confiables. OmniOps coincidió en todas "
                         "las comparaciones medibles.\n")
            if descart:
                fh.write(f"\nNota: {descart} comparación(es) descartada(s) por "
                         "desfase de tiempo (gap alto); no reflejan error de "
                         "cálculo y no cuentan en la tasa.\n")

        js = os.path.join(carpeta, f"reporte_{stamp}.json")
        with open(js, "w", encoding="utf-8") as fh:
            json.dump({
                "titulo": self.titulo,
                "inicio": self.inicio.isoformat(),
                "total": total, "confiables": confiables,
                "pasaron": paso, "fallaron": fallo, "descartadas": descart,
                "tasa_exito": round(tasa, 1),
                "comparaciones": self.filas,
            }, fh, indent=2, ensure_ascii=False)

        print(f"\nReporte guardado:\n  {txt}\n  {js}")
        return txt


if __name__ == "__main__":
    r = Reporter(gap_confiable_s=1.0)
    r.registrar("20:20:24", 2520, 2520, 1.00, True, 0.5)    # PASA
    r.registrar("20:20:34", 4404, 4404, 1.00, True, 0.3)    # PASA
    r.registrar("20:20:19", 2520, 1241, 0.49, False, 1.4)   # DESCARTADA (gap alto)
    r.registrar("20:25:00", 3000, 1500, 0.50, False, 0.3)   # FALLA confiable (ejemplo)
    r.save()
    print("\n(demo con las 3 categorías)")
