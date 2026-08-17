"""
timeanchor.py — ANCLAJE POR TIEMPO, en un solo lugar.

OmniOps va un "tick" atrasado respecto al simulador. En vez de comparar contra
el simulador de ahora, guardamos un historial y comparamos contra el valor del
MISMO instante (por timestamp). Esta lógica estaba copiada en los dos watchers.

  historial = lista de (epoch, kw)
  match_buffer(historial, instante) -> ((epoch, kw), gap_en_segundos)

Correr la prueba:  python timeanchor.py --self-check
"""

from __future__ import annotations

import sys

from config import BUFFER_S


def match_buffer(buffer, target_epoch):
    """Del historial, el valor cuya hora esté MÁS CERCA del instante buscado.
    Devuelve ((epoch, kw), gap) o (None, None) si el historial está vacío."""
    best, best_gap = None, None
    for ep, kw in buffer:
        gap = abs(ep - target_epoch)
        if best_gap is None or gap < best_gap:
            best, best_gap = (ep, kw), gap
    return best, best_gap


def podar(buffer, now, ventana_s=BUFFER_S):
    """Deja en el historial solo lo más nuevo que `ventana_s` segundos."""
    buffer[:] = [(e, v) for e, v in buffer if now - e <= ventana_s]
    return buffer


def _self_check():
    print("(prueba de anclaje — sin red)\n")
    # el simulador pasó por 100,200,300,400,500; OmniOps muestra el instante 1002
    buffer = [(1000.0, 100), (1001.0, 200), (1002.0, 300),
              (1003.0, 400), (1004.0, 500)]
    (ep, kw), gap = match_buffer(buffer, 1002.0)
    ok = kw == 300 and gap == 0.0
    print(f"  match 1002 -> kw={kw} gap={gap}  {'OK' if ok else 'MAL'}")
    # poda: con now=1004 y ventana 2s deben quedar los de 1002,1003,1004
    b = list(buffer)
    podar(b, now=1004.0, ventana_s=2.0)
    ok2 = [v for _, v in b] == [300, 400, 500]
    print(f"  poda (ventana 2s) -> {[v for _, v in b]}  {'OK' if ok2 else 'MAL'}")
    print("\n=> " + ("OK ✓" if ok and ok2 else "MAL ✗"))
    return ok and ok2


if __name__ == "__main__":
    sys.exit(0 if _self_check() else 1)
