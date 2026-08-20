"""
telemetry_map.py — direcciones de telemetría (Model 803 string + Model 103 PCS)
para las alarmas que OmniOps evalúa por VALOR (no por bit).

Extraído de read_bess_registers.py del repo del simulador:
  Model 803 string 1 -> base 10161 (offset del campo sumado a la base)
  Scale factors del header 803 (base 10133): ModTmp_SF=10156, A_SF=10157,
     CellV_SF=10155, SoC_SF=10159
  Model 103 PCS 1 -> base 17000 (A=+2, A_SF=+6)

valor_real = raw * 10^SF   (SF con signo)

Por cada alarma de telemetría:
  field  : registro del valor
  sf     : registro del scale factor
  tipo   : 'int16' (con signo) o 'uint16'
  op     : comparación contra el umbral
  limite : umbral real
  dir    : 'high' (forzar por encima) o 'low' (forzar por debajo) al inyectar
  aprox  : True si el mapeo es aproximado (alarmas relativas/derivadas)

Todo esto es DATO: si hay que ajustar una dirección o umbral, se toca acá.
"""

# inyectamos en el string 1 (base 10161) / PCS 1 (base 17000)
STRING_1_BASE = 10161
PCS_1_BASE = 17000

TELEMETRY = {
    16: {"nombre": "Rack High Temp",        "field": 10173, "sf": 10156,
         "tipo": "int16",  "op": ">", "limite": 58.0,  "dir": "high"},
    17: {"nombre": "Rack Low Temp",         "field": 10175, "sf": 10156,
         "tipo": "int16",  "op": "<", "limite": -2.0,  "dir": "low"},
    29: {"nombre": "String Overcurrent",    "field": 10167, "sf": 10157,
         "tipo": "int16",  "op": ">", "limite": 650.0, "dir": "high"},
    32: {"nombre": "String Temp Abnormal",  "field": 10173, "sf": 10156,
         "tipo": "int16",  "op": ">", "limite": 64.0,  "dir": "high"},
    42: {"nombre": "PCS AC Overcurrent",    "field": 17002, "sf": 17006,
         "tipo": "int16",  "op": ">", "limite": 90.0,  "dir": "high"},
    43: {"nombre": "PCS AC Undercurrent",   "field": 17002, "sf": 17006,
         "tipo": "int16",  "op": "<", "limite": 2.0,   "dir": "low"},
    # --- aproximadas: son relativas/derivadas (diferencia entre strings) ---
    18: {"nombre": "Rack Temp Gradient High", "field": 10173, "sf": 10156,
         "tipo": "int16",  "op": ">", "limite": 45.0,  "dir": "high", "aprox": True},
    19: {"nombre": "Rack Voltage Diff High", "field": 10168, "sf": 10155,
         "tipo": "uint16", "op": ">", "limite": 3.65,  "dir": "high", "aprox": True},
    33: {"nombre": "String SOC Imbalance",  "field": 10165, "sf": 10159,
         "tipo": "uint16", "op": "<", "limite": 44.0,  "dir": "low",  "aprox": True},
}

# valor crudo extremo a inyectar según dirección y tipo (cruza el umbral con
# cualquier scale factor razonable). Para int16 negativo usamos complemento a 2.
def raw_extremo(dir_, tipo):
    if dir_ == "high":
        return 60000 if tipo == "uint16" else 30000
    # low
    if tipo == "uint16":
        return 0
    return (-30000) & 0xFFFF        # int16 muy negativo, en 16 bits
