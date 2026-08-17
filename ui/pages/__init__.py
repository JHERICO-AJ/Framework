"""
pages/ — Page Object Model (POM) de la capa pantalla.

Cada pantalla de OmniOps es una clase que guarda SUS selectores y SUS acciones.
Los tests/monitores no tocan selectores crudos: le piden a la página.
Si el front cambia un id o una clase, se corrige en UN solo lugar (la página).

  BasePage        -> lo común (¿estoy en login?, esperar carga)
  LoginPage       -> pantalla de login (#loginUser, #loginPassword, botón)
  MonitoringPage  -> dashboard (device-card "Actual PCS Power", tabla de alarmas)
"""

from ui.pages.base_page import BasePage
from ui.pages.login_page import LoginPage
from ui.pages.monitoring_page import MonitoringPage, parse_kw

__all__ = ["BasePage", "LoginPage", "MonitoringPage", "parse_kw"]
