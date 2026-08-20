"""
verdict.py — el JUEZ de la validación de alarmas.

Toma dos hechos independientes y decide UN veredicto:

  - causa_activa   : ¿el ORÁCULO (crudo del simulador) dice que la condición que
                     debería disparar la alarma está presente? (bit de Evt1 o
                     umbral de telemetría — lo calcula alarms_oracle.py).
  - alarma_abierta : ¿OmniOps tiene esa alarma como Open en la API/UI?

Cruza los dos y da uno de estos veredictos:

  causa | alarma | veredicto            | qué significa
  ------+--------+----------------------+------------------------------------------
   sí   |  sí    | PASA                 | detección correcta (alarma real, detectada)
   no   |  no    | PASA_SANO            | sano y sin alarma: correcto
   no   |  sí    | FALLA_FALSA          | ALARMA FALSA (salta sin causa) <<<
   sí   |  no    | FALLA_NO_DETECTADA   | NO DETECTADA (hay causa y no salta) <<<

Caso aparte: si la alarma es `oracle_independent=False` (ems/trend), no podemos
calcular la causa por nuestra cuenta -> NO_VERIFICABLE (no cuenta como error).

Es lógica pura: no toca red ni Modbus. Se puede probar sola.

Correr la prueba:  python verdict.py --self-check
"""

from __future__ import annotations

# etiquetas (constantes para no escribirlas mal en otros archivos)
PASA = "PASA"
PASA_SANO = "PASA_SANO"
FALLA_FALSA = "FALLA_FALSA"
FALLA_NO_DETECTADA = "FALLA_NO_DETECTADA"
NO_VERIFICABLE = "NO_VERIFICABLE"

# ¿la etiqueta cuenta como confiable para la tasa de éxito?
CONFIABLES = {PASA, PASA_SANO, FALLA_FALSA, FALLA_NO_DETECTADA}
# ¿la etiqueta es un "OK"?
ES_OK = {PASA, PASA_SANO}

DESCRIPCION = {
    PASA: "detección correcta (alarma real y detectada)",
    PASA_SANO: "sano y sin alarma (correcto)",
    FALLA_FALSA: "ALARMA FALSA: salta sin causa en el crudo",
    FALLA_NO_DETECTADA: "NO DETECTADA: hay causa en el crudo y la alarma no salta",
    NO_VERIFICABLE: "no verificable (oracle_independent=False: ems/trend)",
}


def verdict(causa_activa, alarma_abierta, oracle_independent=True):
    """Devuelve una de las etiquetas de arriba.

    causa_activa / alarma_abierta pueden venir None si no se pudieron medir;
    en ese caso también devolvemos NO_VERIFICABLE (no arriesgamos un falso error).
    """
    if not oracle_independent:
        return NO_VERIFICABLE
    if causa_activa is None or alarma_abierta is None:
        return NO_VERIFICABLE

    causa = bool(causa_activa)
    alarma = bool(alarma_abierta)
    if causa and alarma:
        return PASA
    if not causa and not alarma:
        return PASA_SANO
    if not causa and alarma:
        return FALLA_FALSA
    return FALLA_NO_DETECTADA          # causa and not alarma


def es_ok(etiqueta):
    return etiqueta in ES_OK


def es_confiable(etiqueta):
    return etiqueta in CONFIABLES


def clasificar(causa_estado, abierta, fresca):
    """Veredicto para alarmas que NO se cierran (usan first/lastOccurred).
    Una alarma abierta pero NO fresca (vieja pegada, de otro día) se trata como
    no-abierta, así no se marca como falsa. causa None -> NO_VERIFICABLE.
    Lo usan tanto el monitor en vivo como el comando alarms.probar."""
    if causa_estado is None:
        return NO_VERIFICABLE
    return verdict(causa_estado, bool(abierta and fresca), oracle_independent=True)


# ---------------------------------------------------------------------------
def _self_check():
    print("(prueba de verdict — lógica pura, sin red)\n")
    casos = [
        # (causa, alarma, oracle_independent, esperado)
        (True,  True,  True,  PASA),
        (False, False, True,  PASA_SANO),
        (False, True,  True,  FALLA_FALSA),
        (True,  False, True,  FALLA_NO_DETECTADA),
        (True,  True,  False, NO_VERIFICABLE),   # ems/trend: no verificable
        (None,  True,  True,  NO_VERIFICABLE),   # no se pudo medir la causa
        (True,  None,  True,  NO_VERIFICABLE),   # no se pudo leer la API
    ]
    todos_ok = True
    for causa, alarma, oi, esperado in casos:
        got = verdict(causa, alarma, oracle_independent=oi)
        ok = got == esperado
        todos_ok = todos_ok and ok
        print(f"  causa={str(causa):5} alarma={str(alarma):5} oi={str(oi):5} "
              f"-> {got:18} {'OK' if ok else f'MAL (esperaba {esperado})'}")
    print("\n=> " + ("TODOS OK ✓" if todos_ok else "HAY DIFERENCIAS ✗"))
    return todos_ok


if __name__ == "__main__":
    import sys
    ok = _self_check()          # este archivo solo tiene el self-check
    sys.exit(0 if ok else 1)
