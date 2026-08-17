# Presencia de este archivo + pythonpath=. en pytest.ini hacen que los paquetes
# (core, calc, alarms, ui, ...) se importen bien al correr `pytest` desde la raíz.
import os
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)
