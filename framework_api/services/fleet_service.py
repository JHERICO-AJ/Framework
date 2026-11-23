"""FleetService — the FLEET-wide domain (availability distribution).

Confirmed 2026-08-31 by sniffing the network traffic during a real UI
session: GET /api/DataProcessing/fleet/availability-distribution?days=N is
what the Fleet Availability bar/card actually reads. Returns
{'normalPercentage', 'warningPercentage', 'criticalPercentage',
'fleetAvailability'} -- 'fleetAvailability' equals 'normalPercentage' (same
number, two keys), matching what the UI card/bar-legend both display."""
from __future__ import annotations


from framework_api.models.fleet_availability import FleetAvailability
from framework_api.services.base_service import BaseService


class FleetService(BaseService):
    PATH = "/api/DataProcessing/fleet/availability-distribution"

    def get_availability_distribution(self, days=1) -> FleetAvailability:
        payload = self.client.get(self.PATH, days=days)
        return FleetAvailability.from_json(payload)
