"""
alarms_catalog.py — Alarmas SPEC90 para el framework de validación de OmniOps. VERSION 5.

OBJETIVO (oráculo): corroborar que cada alarma se activó POR LA CAUSA CORRECTA y no
falsamente. El oráculo lee el Modbus CRUDO y confirma la causa (p.ej. Cell Overvoltage
<-> Evt1_802 HR 10095 bit 9 = 0x200). verdict(): 4 casos (ver abajo).

V5: direcciones y bits REALES del Catalogo_Bits_BESS. Correcciones vs v4:
  - ID 21 (Rack Contactor Failure): ahora es BIT (Evt1_802 bit 20), no telemetria.
  - ID 22 (Rack Cooling Fan Failure): ahora es BIT (Evt1_802 bit 21), no EMS.

Capas: bit_802 (HR 10095) · bit_e001 (HR 9815) · bit_fire (FireAlarm HR 9818) ·
       bit_pcsonline (PcsOnline HR 9822) · telemetry (Model 803) · ems/trend (fuera de Modbus).
"""

ALARMS_API_PATH = "/api/events/alarms/filtered"

# Direcciones absolutas (Holding Registers) confirmadas en el Catalogo de Bits
ADDR = dict(evt1_802=10095, evt1_e001=9815, fire_alarm=9818, pcs_online=9822)
MODEL802_BASE = 10069   # el Evt1 esta en base+26 = 10095

SUBSYSTEM_API_TO_UI = {
    'BATTERY_BMS': 'Battery / BMS',
    'TRANSFORMER_PCS': 'PCS / Inverter',
    'EMS_GATEWAY': 'EMS IPC & Gateway',
    'THERMAL_HVAC': 'HVAC / Thermal',
    'FIRE_SAFETY': 'Fire & Safety',
    'UPS_AUX': 'UPS / Auxiliary Power',
}

SITE_GUID = {
    "S01": "10000000-0000-0000-0000-000000000001",
    "S02": "10000000-0000-0000-0000-000000000002",
    "S03": "10000000-0000-0000-0000-000000000003",
    "S04": "10000000-0000-0000-0000-000000000004",
    "S05": "10000000-0000-0000-0000-000000000005",
    "S06": "10000000-0000-0000-0000-000000000006",
    "S07": "10000000-0000-0000-0000-000000000007",
    "S08": "10000000-0000-0000-0000-000000000008",
    "S09": "10000000-0000-0000-0000-000000000009",
    "S10": "10000000-0000-0000-0000-000000000010",
}
SITE_GUID_TO_KEY = {v: k for k, v in SITE_GUID.items()}

ALARMS = [
    dict(alarm_rule_id=1, name='Cell Overvoltage', severity='Major',
         subsystem_api='BATTERY_BMS', subsystem_ui='Battery / BMS',
         signal_trigger='Cell_V_Max > 3.65-4.20 V', layer='bit_802',
         oracle={'hr': 10095, 'bit': 9, 'mask': '0x200', 'sig': 'Evt1_802 (HR 10095) bit 9'}, oracle_independent=True,
         inject={'evt1_802_bits': [9]}),
    dict(alarm_rule_id=2, name='Cell Undervoltage', severity='Major',
         subsystem_api='BATTERY_BMS', subsystem_ui='Battery / BMS',
         signal_trigger='Cell_V_Min < 2.7-3.0 V', layer='bit_802',
         oracle={'hr': 10095, 'bit': 11, 'mask': '0x800', 'sig': 'Evt1_802 (HR 10095) bit 11'}, oracle_independent=True,
         inject={'evt1_802_bits': [11]}),
    dict(alarm_rule_id=3, name='Cell High Temp', severity='Critical',
         subsystem_api='BATTERY_BMS', subsystem_ui='Battery / BMS',
         signal_trigger='Cell_T_Max > 55-60 C', layer='bit_802',
         oracle={'hr': 10095, 'bit': 1, 'mask': '0x2', 'sig': 'Evt1_802 (HR 10095) bit 1'}, oracle_independent=True,
         inject={'evt1_802_bits': [1]}),
    dict(alarm_rule_id=4, name='Cell Low Temp', severity='Major',
         subsystem_api='BATTERY_BMS', subsystem_ui='Battery / BMS',
         signal_trigger='Cell_T_Min < 0-5 C', layer='bit_802',
         oracle={'hr': 10095, 'bit': 3, 'mask': '0x8', 'sig': 'Evt1_802 (HR 10095) bit 3'}, oracle_independent=True,
         inject={'evt1_802_bits': [3]}),
    dict(alarm_rule_id=5, name='Cell Temp Difference High', severity='Major',
         subsystem_api='BATTERY_BMS', subsystem_ui='Battery / BMS',
         signal_trigger='Cell Delta T > 8-10 C', layer='bit_802',
         oracle={'hr': 10095, 'bit': 18, 'mask': '0x40000', 'sig': 'Evt1_802 (HR 10095) bit 18'}, oracle_independent=True,
         inject={'evt1_802_bits': [18]}),
    dict(alarm_rule_id=6, name='Cell Voltage difference High', severity='Major',
         subsystem_api='BATTERY_BMS', subsystem_ui='Battery / BMS',
         signal_trigger='Cell Delta V > 80-120 mV', layer='bit_802',
         oracle={'hr': 10095, 'bit': 17, 'mask': '0x20000', 'sig': 'Evt1_802 (HR 10095) bit 17'}, oracle_independent=True,
         inject={'evt1_802_bits': [17]}),
    dict(alarm_rule_id=10, name='Module High Temp', severity='Critical',
         subsystem_api='BATTERY_BMS', subsystem_ui='Battery / BMS',
         signal_trigger='Module_T > 55 C', layer='bit_802',
         oracle={'hr': 10095, 'bit': 1, 'mask': '0x2', 'sig': 'Evt1_802 (HR 10095) bit 1'}, oracle_independent=True,
         inject={'evt1_802_bits': [1]}),
    dict(alarm_rule_id=11, name='Module Low Temp', severity='Major',
         subsystem_api='BATTERY_BMS', subsystem_ui='Battery / BMS',
         signal_trigger='Module_T < 0-5 C', layer='bit_802',
         oracle={'hr': 10095, 'bit': 3, 'mask': '0x8', 'sig': 'Evt1_802 (HR 10095) bit 3'}, oracle_independent=True,
         inject={'evt1_802_bits': [3]}),
    dict(alarm_rule_id=13, name='Module Temp Difference High', severity='Major',
         subsystem_api='BATTERY_BMS', subsystem_ui='Battery / BMS',
         signal_trigger='Module Delta T > 10 C', layer='bit_802',
         oracle={'hr': 10095, 'bit': 18, 'mask': '0x40000', 'sig': 'Evt1_802 (HR 10095) bit 18'}, oracle_independent=True,
         inject={'evt1_802_bits': [18]}),
    dict(alarm_rule_id=16, name='Rack High Temp', severity='Critical',
         subsystem_api='BATTERY_BMS', subsystem_ui='Battery / BMS',
         signal_trigger='Rack_T > 50-55 C', layer='telemetry',
         oracle={'hr': None, 'bit': None, 'mask': None, 'sig': 'telemetria Model 803 (string/PCS) vs umbral'}, oracle_independent=True,
         inject={'strings_or_pcs': {'t_max': 58.0}}),
    dict(alarm_rule_id=17, name='Rack Low Temp', severity='Major',
         subsystem_api='BATTERY_BMS', subsystem_ui='Battery / BMS',
         signal_trigger='Rack_T < 0-5 C', layer='telemetry',
         oracle={'hr': None, 'bit': None, 'mask': None, 'sig': 'telemetria Model 803 (string/PCS) vs umbral'}, oracle_independent=True,
         inject={'strings_or_pcs': {'t_min': -2.0}}),
    dict(alarm_rule_id=18, name='Rack Temp Gradient High', severity='Major',
         subsystem_api='BATTERY_BMS', subsystem_ui='Battery / BMS',
         signal_trigger='Rack Delta T > 10 C', layer='telemetry',
         oracle={'hr': None, 'bit': None, 'mask': None, 'sig': 'telemetria Model 803 (string/PCS) vs umbral'}, oracle_independent=True,
         inject={'strings_or_pcs': {'t_avg': 45.0}}),
    dict(alarm_rule_id=19, name='Rack Voltage Difference High', severity='Major',
         subsystem_api='BATTERY_BMS', subsystem_ui='Battery / BMS',
         signal_trigger='Module Delta V > 80-120 mV', layer='telemetry',
         oracle={'hr': None, 'bit': None, 'mask': None, 'sig': 'telemetria Model 803 (string/PCS) vs umbral'}, oracle_independent=True,
         inject={'strings_or_pcs': {'cv_max': 3.65}}),
    dict(alarm_rule_id=21, name='Rack Contactor Failure', severity='Critical',
         subsystem_api='BATTERY_BMS', subsystem_ui='Battery / BMS',
         signal_trigger='Contactor_Status abnormalities', layer='bit_802',
         oracle={'hr': 10095, 'bit': 20, 'mask': '0x100000', 'sig': 'Evt1_802 (HR 10095) bit 20'}, oracle_independent=True,
         inject={'evt1_802_bits': [20]}),
    dict(alarm_rule_id=22, name='Rack Cooling Fan Failure', severity='Critical',
         subsystem_api='THERMAL_HVAC', subsystem_ui='HVAC / Thermal',
         signal_trigger='Fan RPM or Status abnormalities', layer='bit_802',
         oracle={'hr': 10095, 'bit': 21, 'mask': '0x200000', 'sig': 'Evt1_802 (HR 10095) bit 21'}, oracle_independent=True,
         inject={'evt1_802_bits': [21]}),
    dict(alarm_rule_id=23, name='Rack Door Open', severity='Minor',
         subsystem_api='BATTERY_BMS', subsystem_ui='Battery / BMS',
         signal_trigger='Door sensor = Open', layer='bit_802',
         oracle={'hr': 10095, 'bit': 23, 'mask': '0x800000', 'sig': 'Evt1_802 (HR 10095) bit 23'}, oracle_independent=True,
         inject={'evt1_802_bits': [23]}),
    dict(alarm_rule_id=24, name='Rack Smoke Detected', severity='Critical',
         subsystem_api='FIRE_SAFETY', subsystem_ui='Fire & Safety',
         signal_trigger='Smoke Sensor = ALARM', layer='bit_fire',
         oracle={'hr': 9818, 'bit': None, 'mask': None, 'sig': 'FireAlarm (HR 9818) mask contenedor'}, oracle_independent=True,
         inject={'fire_containers': [1]}),
    dict(alarm_rule_id=27, name='Rack Ground Fault', severity='Critical',
         subsystem_api='BATTERY_BMS', subsystem_ui='Battery / BMS',
         signal_trigger='Ground Impedance too low', layer='bit_802',
         oracle={'hr': 10095, 'bit': 22, 'mask': '0x400000', 'sig': 'Evt1_802 (HR 10095) bit 22'}, oracle_independent=True,
         inject={'evt1_802_bits': [22]}),
    dict(alarm_rule_id=29, name='String Overcurrent', severity='Critical',
         subsystem_api='BATTERY_BMS', subsystem_ui='Battery / BMS',
         signal_trigger='overcurrent (MAJOR inst / CRITICAL sostenida)', layer='telemetry',
         oracle={'hr': None, 'bit': None, 'mask': None, 'sig': 'telemetria Model 803 (string/PCS) vs umbral'}, oracle_independent=True,
         inject={'strings_or_pcs': {'current_a': 650.0}}),
    dict(alarm_rule_id=32, name='String Temp Abnormal', severity='Critical',
         subsystem_api='BATTERY_BMS', subsystem_ui='Battery / BMS',
         signal_trigger='Rack Delta T > 50 C', layer='telemetry',
         oracle={'hr': None, 'bit': None, 'mask': None, 'sig': 'telemetria Model 803 (string/PCS) vs umbral'}, oracle_independent=True,
         inject={'strings_or_pcs': {'t_max': 64.0}}),
    dict(alarm_rule_id=33, name='String SOC Imbalance', severity='Major',
         subsystem_api='BATTERY_BMS', subsystem_ui='Battery / BMS',
         signal_trigger='Rack Delta SOC > 3-5%', layer='telemetry',
         oracle={'hr': None, 'bit': None, 'mask': None, 'sig': 'telemetria Model 803 (string/PCS) vs umbral'}, oracle_independent=True,
         inject={'strings_or_pcs': {'soc': 44.0}}),
    dict(alarm_rule_id=38, name='PCS DC Bus Overvoltage', severity='Critical',
         subsystem_api='TRANSFORMER_PCS', subsystem_ui='PCS / Inverter',
         signal_trigger='DC Bus V exceeded the limit', layer='bit_e001',
         oracle={'hr': 9815, 'bit': 1, 'mask': '0x2', 'sig': 'Evt1_E001 (HR 9815) bit 1'}, oracle_independent=True,
         inject={'evt1_e001_bits': [1]}),
    dict(alarm_rule_id=40, name='PCS AC Overvoltage', severity='Major',
         subsystem_api='TRANSFORMER_PCS', subsystem_ui='PCS / Inverter',
         signal_trigger='AC V overrun (UL1741)', layer='bit_e001',
         oracle={'hr': 9815, 'bit': 10, 'mask': '0x400', 'sig': 'Evt1_E001 (HR 9815) bit 10'}, oracle_independent=True,
         inject={'evt1_e001_bits': [10]}),
    dict(alarm_rule_id=41, name='PCS AC Undervoltage', severity='Major',
         subsystem_api='TRANSFORMER_PCS', subsystem_ui='PCS / Inverter',
         signal_trigger='AC V < 0.9 p.u.', layer='bit_e001',
         oracle={'hr': 9815, 'bit': 11, 'mask': '0x800', 'sig': 'Evt1_E001 (HR 9815) bit 11'}, oracle_independent=True,
         inject={'evt1_e001_bits': [11]}),
    dict(alarm_rule_id=42, name='PCS AC Overcurrent', severity='Critical',
         subsystem_api='TRANSFORMER_PCS', subsystem_ui='PCS / Inverter',
         signal_trigger='AC Current exceeds standard', layer='telemetry',
         oracle={'hr': None, 'bit': None, 'mask': None, 'sig': 'telemetria Model 803 (string/PCS) vs umbral'}, oracle_independent=True,
         inject={'strings_or_pcs': {'inv_a': 90.0}}),
    dict(alarm_rule_id=43, name='PCS AC Undercurrent', severity='Minor',
         subsystem_api='TRANSFORMER_PCS', subsystem_ui='PCS / Inverter',
         signal_trigger='Output current lower than expected', layer='telemetry',
         oracle={'hr': None, 'bit': None, 'mask': None, 'sig': 'telemetria Model 803 (string/PCS) vs umbral'}, oracle_independent=True,
         inject={'strings_or_pcs': {'inv_a': 2.0}}),
    dict(alarm_rule_id=44, name='PCS Phase Loss', severity='Critical',
         subsystem_api='TRANSFORMER_PCS', subsystem_ui='PCS / Inverter',
         signal_trigger='Any phase V/I in L1/L2/L3 ~ 0', layer='ems',
         oracle={'hr': None, 'bit': None, 'mask': None, 'sig': 'N/A (causa fuera del Modbus)'}, oracle_independent=False,
         inject={'ems': [44]}),
    dict(alarm_rule_id=45, name='PCS Phase Imbalance', severity='Major',
         subsystem_api='TRANSFORMER_PCS', subsystem_ui='PCS / Inverter',
         signal_trigger='Three-phase V/I imbalance > 20%', layer='ems',
         oracle={'hr': None, 'bit': None, 'mask': None, 'sig': 'N/A (causa fuera del Modbus)'}, oracle_independent=False,
         inject={'ems': [45]}),
    dict(alarm_rule_id=46, name='PCS Ground Fault', severity='Critical',
         subsystem_api='TRANSFORMER_PCS', subsystem_ui='PCS / Inverter',
         signal_trigger='PCS IR too low', layer='bit_e001',
         oracle={'hr': 9815, 'bit': 0, 'mask': '0x1', 'sig': 'Evt1_E001 (HR 9815) bit 0'}, oracle_independent=True,
         inject={'evt1_e001_bits': [0]}),
    dict(alarm_rule_id=50, name='PCS Communication Lost', severity='Critical',
         subsystem_api='TRANSFORMER_PCS', subsystem_ui='PCS / Inverter',
         signal_trigger='PCS Port loses connection', layer='bit_pcsonline',
         oracle={'hr': 9822, 'bit': None, 'mask': None, 'sig': 'PcsOnline (HR 9822) PCS caido'}, oracle_independent=True,
         inject={'pcs_offline': [1]}),
    dict(alarm_rule_id=51, name='EMS-BMS Comm Lost', severity='Critical',
         subsystem_api='EMS_GATEWAY', subsystem_ui='EMS IPC & Gateway',
         signal_trigger='BMS Port loses connection', layer='ems',
         oracle={'hr': None, 'bit': None, 'mask': None, 'sig': 'N/A (causa fuera del Modbus)'}, oracle_independent=False,
         inject={'ems': [51]}),
    dict(alarm_rule_id=52, name='EMS-PCS Comm Lost', severity='Critical',
         subsystem_api='EMS_GATEWAY', subsystem_ui='EMS IPC & Gateway',
         signal_trigger='PCS Port loses connection', layer='ems',
         oracle={'hr': None, 'bit': None, 'mask': None, 'sig': 'N/A (causa fuera del Modbus)'}, oracle_independent=False,
         inject={'ems': [52]}),
    dict(alarm_rule_id=55, name='EMS Control Logic Fault', severity='Major',
         subsystem_api='EMS_GATEWAY', subsystem_ui='EMS IPC & Gateway',
         signal_trigger='Charge/Discharge directives contradictory', layer='ems',
         oracle={'hr': None, 'bit': None, 'mask': None, 'sig': 'N/A (causa fuera del Modbus)'}, oracle_independent=False,
         inject={'ems': [55]}),
    dict(alarm_rule_id=58, name='EMS Parameter Mismatch', severity='Major',
         subsystem_api='EMS_GATEWAY', subsystem_ui='EMS IPC & Gateway',
         signal_trigger='EMS setpoint exceeds BMS/PCS limits', layer='ems',
         oracle={'hr': None, 'bit': None, 'mask': None, 'sig': 'N/A (causa fuera del Modbus)'}, oracle_independent=False,
         inject={'ems': [58]}),
    dict(alarm_rule_id=66, name='Container Smoke Detected', severity='Critical',
         subsystem_api='FIRE_SAFETY', subsystem_ui='Fire & Safety',
         signal_trigger='Smoke Sensor = ALARM', layer='bit_fire',
         oracle={'hr': 9818, 'bit': None, 'mask': None, 'sig': 'FireAlarm (HR 9818) mask contenedor'}, oracle_independent=True,
         inject={'fire_containers': [1]}),
    dict(alarm_rule_id=71, name='Critical sensor data drift/freeze', severity='Major',
         subsystem_api='EMS_GATEWAY', subsystem_ui='EMS IPC & Gateway',
         signal_trigger='Cell T change < 0.1C for 6h / dev > 10%', layer='trend',
         oracle={'hr': None, 'bit': None, 'mask': None, 'sig': 'N/A (causa fuera del Modbus)'}, oracle_independent=False,
         inject={'trend': [71]}),
    dict(alarm_rule_id=73, name='PCS power factor anomalous deviation', severity='Minor',
         subsystem_api='EMS_GATEWAY', subsystem_ui='EMS IPC & Gateway',
         signal_trigger='PF deviates from EMS target > 0.05 for 30 min', layer='trend',
         oracle={'hr': None, 'bit': None, 'mask': None, 'sig': 'N/A (causa fuera del Modbus)'}, oracle_independent=False,
         inject={'trend': [73]}),
    dict(alarm_rule_id=74, name='Meter data and PCS data mismatch', severity='Warning',
         subsystem_api='EMS_GATEWAY', subsystem_ui='EMS IPC & Gateway',
         signal_trigger='Meter vs PCS AC power > 1% over 7 days', layer='trend',
         oracle={'hr': None, 'bit': None, 'mask': None, 'sig': 'N/A (causa fuera del Modbus)'}, oracle_independent=False,
         inject={'trend': [74]}),
    dict(alarm_rule_id=78, name='PCS idle power drift', severity='Warning',
         subsystem_api='EMS_GATEWAY', subsystem_ui='EMS IPC & Gateway',
         signal_trigger='Idle PCS AC P > 5 kW for 1 h', layer='trend',
         oracle={'hr': None, 'bit': None, 'mask': None, 'sig': 'N/A (causa fuera del Modbus)'}, oracle_independent=False,
         inject={'trend': [78]}),
]
BY_RULE_ID = {a['alarm_rule_id']: a for a in ALARMS}
IN_SCOPE_IDS = [a['alarm_rule_id'] for a in ALARMS]

def find_api_alarm(api_list, rule_id):
    return next((x for x in api_list if x.get('alarmRuleId') == rule_id), None)

def read_bit(modbus_read_u32, hr, bit):
    """Lee un registro de 32 bits (2 HR) y devuelve True si <bit> esta encendido.
    modbus_read_u32(hr) debe devolver el entero de 32 bits (hi<<16 | lo)."""
    return bool(modbus_read_u32(hr) & (1 << bit))

def verdict(expected, api_alarm, cause_present):
    """Correlaciona causa (crudo) vs alarma (API). (estado, motivos)."""
    alarm_present = api_alarm is not None
    if cause_present and alarm_present:
        m = []
        if api_alarm.get('severity') != expected['severity']:
            m.append('severity %r != %r' % (api_alarm.get('severity'), expected['severity']))
        if api_alarm.get('subsystem') != expected['subsystem_api']:
            m.append('subsystem %r != %r' % (api_alarm.get('subsystem'), expected['subsystem_api']))
        return ('PASA' if not m else 'FALLA', m)
    if alarm_present and not cause_present:
        return ('FALLA', ['ALARMA FALSA: aparece sin causa en el crudo'])
    if cause_present and not alarm_present:
        return ('FALLA', ['NO DETECTADA: causa presente sin alarma'])
    return ('PASA', ['sano'])
