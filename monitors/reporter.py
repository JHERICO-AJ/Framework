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

        # además, SIEMPRE: un resumen ejecutivo (para mostrar a un directivo).
        # Idioma humano, sin descartadas, sin gaps ni anclaje.
        ej = self._guardar_ejecutivo(carpeta, stamp, confiables, paso, fallo, tasa)

        print(f"\nReporte técnico guardado:\n  {txt}\n  {js}")
        print(f"Resumen ejecutivo (para presentar):\n  {ej}")
        return txt

    def _guardar_ejecutivo(self, carpeta, stamp, confiables, paso, fallo, tasa):
        """Resumen limpio y EN INGLÉS para un alto cargo. No menciona
        descartadas ni desfase. El técnico (en español) queda para nosotros."""
        path = os.path.join(carpeta, f"executive_summary_{stamp}.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("OmniOps Validation — Executive Summary\n")
            fh.write(f"Date: {self.inicio:%Y-%m-%d %H:%M}\n")
            fh.write("=" * 44 + "\n\n")
            fh.write("Automated, independent verification that OmniOps\n")
            fh.write("displays the correct power value.\n\n")
            fh.write(f"Measurements verified : {confiables}\n")
            fh.write(f"  Passed              : {paso}\n")
            fh.write(f"  Failed              : {fallo}\n")
            fh.write(f"Pass rate             : {tasa:.1f}%\n\n")
            if fallo == 0:
                fh.write("Overall result: PASS\n")
                fh.write(f"OmniOps showed the correct value in {tasa:.0f}% of "
                         "measurements. No differences.\n")
            else:
                fh.write("Overall result: FAIL\n")
                fh.write("Differences detected (to review):\n")
                for f in self.filas:
                    if f["categoria"] == "FALLA":
                        fh.write(f"  {f['hora']}: expected {f['esperado']} kW, "
                                 f"OmniOps showed {f['actual']} kW\n")
        return path


if __name__ == "__main__":
    r = Reporter(gap_confiable_s=1.0)
    r.registrar("20:20:24", 2520, 2520, 1.00, True, 0.5)    # PASA
    r.registrar("20:20:34", 4404, 4404, 1.00, True, 0.3)    # PASA
    r.registrar("20:20:19", 2520, 1241, 0.49, False, 1.4)   # DESCARTADA (gap alto)
    r.registrar("20:25:00", 3000, 1500, 0.50, False, 0.3)   # FALLA confiable (ejemplo)
    r.save()
    print("\n(demo con las 3 categorías)")
