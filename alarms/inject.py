"""
inject.py — el CEREBRO de la inyección: "quiero la alarma X" -> "qué registro/bit forzar".

No aplica nada por sí solo: calcula el conjunto de overrides (a nivel registro
Modbus) que representan la causa de una o varias alarmas, y una PROGRAMACIÓN en
el tiempo ("a los 10s alarma 1, a los 50s alarma 3"). Después ese mapa de
overrides lo aplica el proxy Modbus (o el hook del simulador) sobre el cable que
OmniOps lee, y el oráculo confirma que quedó puesto.

Traducción por tipo de causa (campo `inject` del catálogo):
  evt1_802_bits  -> PRENDER bit en Evt1_802  (HR 10095, u32)
  evt1_e001_bits -> PRENDER bit en Evt1_E001 (HR 9815,  u32)
  fire_containers-> PRENDER bit (contenedor-1) en FireAlarm (HR 9818)
  pcs_offline    -> APAGAR  bit (pcs-1)        en PcsOnline (HR 9822)
  strings_or_pcs -> telemetría Model 803: FALTA el mapa de registros -> no soportado aún
  ems / trend    -> la causa no está en el Modbus -> no soportado (sería del lado OmniOps)

Los u32 son big-endian (palabra alta primero), igual que el oráculo:
  bit < 16 -> registro base+1 (palabra baja), bit
  bit >=16 -> registro base   (palabra alta), bit-16

Correr la prueba:  python inject.py --self-check
"""

from __future__ import annotations

import json
import os
import sys
import time

from alarms import catalog as cat

# bases u32 por tipo
_BASE = {
    "evt1_802_bits": cat.ADDR["evt1_802"],   # 10095
    "evt1_e001_bits": cat.ADDR["evt1_e001"],  # 9815
    "fire_containers": cat.ADDR["fire_alarm"],  # 9818
    "pcs_offline": cat.ADDR["pcs_online"],    # 9822
}


def _bit_a_reg(base_hr, bit):
    """(registro de 16 bits, máscara) para un bit dentro del u32 big-endian."""
    if bit < 16:
        return base_hr + 1, (1 << bit)        # palabra baja
    return base_hr, (1 << (bit - 16))         # palabra alta


class Overrides:
    """Qué hacerle a cada registro: OR (prender) y CLEAR (apagar)."""

    def __init__(self):
        self.set = {}      # {reg16: máscara a prender}
        self.clear = {}    # {reg16: máscara a apagar}
        self.no_soportado = []  # [(rule_id, motivo)]

    def _or(self, reg, mask):
        self.set[reg] = self.set.get(reg, 0) | mask

    def _and_clear(self, reg, mask):
        self.clear[reg] = self.clear.get(reg, 0) | mask

    def aplicar_a(self, reg, valor):
        """Cómo quedaría el valor de `reg` tras los overrides (lo usa el proxy)."""
        valor = (valor | self.set.get(reg, 0)) & ~self.clear.get(reg, 0)
        return valor & 0xFFFF

    def registros_tocados(self):
        return sorted(set(self.set) | set(self.clear))


def overrides_para(rule_ids):
    """Combina los overrides de varias alarmas en un solo mapa de registros."""
    ov = Overrides()
    for rid in rule_ids:
        a = cat.BY_RULE_ID.get(rid)
        if a is None:
            ov.no_soportado.append((rid, "no está en el catálogo"))
            continue
        inj = a.get("inject") or {}
        if "evt1_802_bits" in inj:
            for b in inj["evt1_802_bits"]:
                reg, mask = _bit_a_reg(_BASE["evt1_802_bits"], b)
                ov._or(reg, mask)
        elif "evt1_e001_bits" in inj:
            for b in inj["evt1_e001_bits"]:
                reg, mask = _bit_a_reg(_BASE["evt1_e001_bits"], b)
                ov._or(reg, mask)
        elif "fire_containers" in inj:
            for c in inj["fire_containers"]:
                reg, mask = _bit_a_reg(_BASE["fire_containers"], c - 1)
                ov._or(reg, mask)
        elif "pcs_offline" in inj:
            for p in inj["pcs_offline"]:
                reg, mask = _bit_a_reg(_BASE["pcs_offline"], p - 1)
                ov._and_clear(reg, mask)      # apagar = PCS caído
        elif "strings_or_pcs" in inj:
            ov.no_soportado.append((rid, "telemetría Model 803: falta el mapa de registros"))
        else:
            ov.no_soportado.append((rid, "ems/trend: la causa no está en el Modbus"))
    return ov


class Programacion:
    """Línea de tiempo: en el segundo t, prender/apagar ciertas alarmas.
    Las alarmas quedan activas hasta que un evento posterior las apague
    (coherente con que OmniOps no cierra las alarmas)."""

    def __init__(self):
        self.eventos = []      # [(t, 'on'|'off', rule_id)]

    def encender(self, t, *rule_ids):
        for r in rule_ids:
            self.eventos.append((t, "on", r))
        return self

    def apagar(self, t, *rule_ids):
        for r in rule_ids:
            self.eventos.append((t, "off", r))
        return self

    def activas_en(self, segundo):
        """Set de alarmas activas en ese instante, según los eventos hasta ahí."""
        activas = set()
        for t, accion, rid in sorted(self.eventos, key=lambda e: e[0]):
            if t > segundo:
                break
            activas.add(rid) if accion == "on" else activas.discard(rid)
        return activas

    def overrides_en(self, segundo):
        return overrides_para(self.activas_en(segundo))


# ---------------------------------------------------------------------------
# Persistencia: el CLI escribe el estado; el proxy (tools/sim_proxy.py) lo lee.
# ---------------------------------------------------------------------------
def guardar_estado(rule_ids):
    """Calcula los overrides de esas alarmas y los deja en INJECT_STATE_FILE."""
    ov = overrides_para(rule_ids)
    data = {
        "alarmas": sorted(rule_ids),
        "set": {str(r): m for r, m in ov.set.items()},
        "clear": {str(r): m for r, m in ov.clear.items()},
        "no_soportado": ov.no_soportado,
    }
    with open(cat_state_file(), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    return ov


def leer_estado():
    """Lo que el proxy aplica: (dict set {reg:mask}, dict clear {reg:mask}).
    Si no hay archivo, no hay inyección (todo vacío)."""
    path = cat_state_file()
    if not os.path.exists(path):
        return {}, {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        pon = {int(r): int(m) for r, m in data.get("set", {}).items()}
        qui = {int(r): int(m) for r, m in data.get("clear", {}).items()}
        return pon, qui
    except Exception:
        return {}, {}


def limpiar_estado():
    """Apaga toda inyección (borra el archivo de estado)."""
    path = cat_state_file()
    if os.path.exists(path):
        os.remove(path)


def cat_state_file():
    # ruta del archivo de estado (a la raíz del proyecto, no al cwd)
    try:
        from config import INJECT_STATE_FILE
        return INJECT_STATE_FILE
    except Exception:
        return "inject_state.json"


# ---------------------------------------------------------------------------
def _self_check():
    print("(prueba del cerebro de inyección — pura lógica, sin red)\n")
    ok = True

    def chequeo(desc, got, exp):
        nonlocal ok
        bien = got == exp
        ok = ok and bien
        print(f"  {desc:46} {'OK' if bien else f'MAL got={got} exp={exp}'}")

    # bit 9 (Cell Overvoltage) -> palabra baja de 10095 = reg 10096, 0x200
    o1 = overrides_para([1])
    chequeo("ID 1 bit 9  -> set{10096:0x200}", o1.set, {10096: 0x200})
    # bit 17 (Cell Voltage diff) -> palabra alta = reg 10095, 0x2
    o6 = overrides_para([6])
    chequeo("ID 6 bit 17 -> set{10095:0x2}", o6.set, {10095: 0x2})
    # e001 bit 0 (PCS Ground Fault) -> reg 9816, 0x1
    o46 = overrides_para([46])
    chequeo("ID 46 e001 bit 0 -> set{9816:0x1}", o46.set, {9816: 0x1})
    # fire contenedor 1 -> bit 0 -> reg 9819, 0x1
    o24 = overrides_para([24])
    chequeo("ID 24 fire cont 1 -> set{9819:0x1}", o24.set, {9819: 0x1})
    # pcs_offline [1] -> apagar bit 0 -> clear{9823:0x1}
    o50 = overrides_para([50])
    chequeo("ID 50 pcs_offline 1 -> clear{9823:0x1}", o50.clear, {9823: 0x1})
    # telemetría / ems -> no soportado
    chequeo("ID 16 telemetría -> no soportado", len(overrides_para([16]).no_soportado), 1)
    chequeo("ID 44 ems -> no soportado", len(overrides_para([44]).no_soportado), 1)
    # combinar 1 y 2 (bits 9 y 11) en el mismo registro
    o12 = overrides_para([1, 2])
    chequeo("ID 1+2 -> set{10096:0xA00}", o12.set, {10096: 0x200 | 0x800})
    # aplicar sobre un registro limpio
    chequeo("aplicar_a(10096, 0) con bit9", o1.aplicar_a(10096, 0x0000), 0x200)
    # clear real: PcsOnline 0b111 -> apagar bit0 -> 0b110
    chequeo("aplicar_a(9823, 0b111) apaga PCS1", o50.aplicar_a(9823, 0b111), 0b110)

    # programación en el tiempo
    prog = Programacion().encender(10, 1).encender(50, 3).apagar(60, 1)
    chequeo("t=5  -> {}", prog.activas_en(5), set())
    chequeo("t=10 -> {1}", prog.activas_en(10), {1})
    chequeo("t=55 -> {1,3}", prog.activas_en(55), {1, 3})
    chequeo("t=65 -> {3}", prog.activas_en(65), {3})

    print("\n=> " + ("TODOS OK ✓" if ok else "HAY DIFERENCIAS ✗"))
    return ok


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        sys.exit(0 if _self_check() else 1)

    args = sys.argv[1:]

    if "--status" in args:
        pon, qui = leer_estado()
        if not pon and not qui:
            print("No hay inyección activa (el proxy devuelve el simulador tal cual).")
        else:
            print("Inyección ACTIVA:")
            for r, m in sorted(pon.items()):
                print(f"  PRENDER HR {r}: {m:#06x}")
            for r, m in sorted(qui.items()):
                print(f"  APAGAR  HR {r}: {m:#06x}")
        sys.exit(0)

    if "--clear" in args or "--off" in args:
        limpiar_estado()
        print("Inyección apagada. El proxy vuelve a devolver el simulador tal cual.")
        sys.exit(0)

    # ids de alarmas a encender (ej: python -m alarms.inject 1 3)
    ids = [int(x) for x in args if x.isdigit()]
    if not ids:
        print("Uso:\n"
              "  python -m alarms.inject 1 3        # encender alarmas 1 y 3 YA\n"
              "  python -m alarms.inject 1 --at 10  # encender la alarma 1 a los 10s\n"
              "  python -m alarms.inject --status   # ver qué hay inyectado\n"
              "  python -m alarms.inject --clear    # apagar toda inyección")
        sys.exit(1)

    # --at N : esperar N segundos antes de encender ("disparo en tal segundo")
    espera = 0
    if "--at" in args:
        try:
            espera = int(args[args.index("--at") + 1])
        except (IndexError, ValueError):
            print("--at necesita un número de segundos (ej: --at 10)")
            sys.exit(1)

    if espera:
        print(f"Voy a encender {ids} en {espera}s… (Ctrl+C para cancelar)")
        time.sleep(espera)

    ov = guardar_estado(ids)
    nombres = ", ".join(f"{i}:{cat.BY_RULE_ID[i]['name']}" for i in ids
                        if i in cat.BY_RULE_ID)
    print(f"Inyección ACTIVA para [{nombres}].")
    for reg, mask in sorted(ov.set.items()):
        print(f"  PRENDER HR {reg}: {mask:#06x}")
    for reg, mask in sorted(ov.clear.items()):
        print(f"  APAGAR  HR {reg}: {mask:#06x}")
    for rid, motivo in ov.no_soportado:
        print(f"  (no soportado) ID {rid}: {motivo}")
    print("\nEl proxy ya lo está aplicando. Para apagar: python -m alarms.inject --clear")
