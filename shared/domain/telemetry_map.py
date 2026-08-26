"""
telemetry_map.py — telemetry addresses (Model 803 string + Model 103 PCS)
for the alarms that OmniOps evaluates by VALUE (not by bit).

Extracted from read_bess_registers.py in the simulator repo:
  Model 803 string 1 -> base 10161 (field offset added to the base)
  Scale factors from the 803 header (base 10133): ModTmp_SF=10156, A_SF=10157,
     CellV_SF=10155, SoC_SF=10159
  Model 103 PCS 1 -> base 17000 (A=+2, A_SF=+6)

real_value = raw * 10^SF   (SF is signed)

For each telemetry alarm:
  field  : value register
  sf     : scale factor register
  type   : 'int16' (signed) or 'uint16'
  op     : comparison against the threshold
  limit  : real threshold
  dir    : 'high' (force above) or 'low' (force below) when injecting
  approx : True if the mapping is approximate (relative/derived alarms)

All of this is DATA: if an address or threshold needs adjusting, it's done here.
"""

# we inject on string 1 (base 10161) / PCS 1 (base 17000)
STRING_1_BASE = 10161
PCS_1_BASE = 17000

TELEMETRY = {
    16: {"name": "Rack High Temp",        "field": 10173, "sf": 10156,
         "type": "int16",  "op": ">", "limit": 58.0,  "dir": "high"},
    17: {"name": "Rack Low Temp",         "field": 10175, "sf": 10156,
         "type": "int16",  "op": "<", "limit": -2.0,  "dir": "low"},
    29: {"name": "String Overcurrent",    "field": 10167, "sf": 10157,
         "type": "int16",  "op": ">", "limit": 650.0, "dir": "high"},
    32: {"name": "String Temp Abnormal",  "field": 10173, "sf": 10156,
         "type": "int16",  "op": ">", "limit": 64.0,  "dir": "high"},
    42: {"name": "PCS AC Overcurrent",    "field": 17002, "sf": 17006,
         "type": "int16",  "op": ">", "limit": 90.0,  "dir": "high"},
    43: {"name": "PCS AC Undercurrent",   "field": 17002, "sf": 17006,
         "type": "int16",  "op": "<", "limit": 2.0,   "dir": "low"},
    # --- approximate: relative/derived (difference between strings) ---
    18: {"name": "Rack Temp Gradient High", "field": 10173, "sf": 10156,
         "type": "int16",  "op": ">", "limit": 45.0,  "dir": "high", "approx": True},
    19: {"name": "Rack Voltage Diff High", "field": 10168, "sf": 10155,
         "type": "uint16", "op": ">", "limit": 3.65,  "dir": "high", "approx": True},
    33: {"name": "String SOC Imbalance",  "field": 10165, "sf": 10159,
         "type": "uint16", "op": "<", "limit": 44.0,  "dir": "low",  "approx": True},
}
