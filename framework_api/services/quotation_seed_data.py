"""Data only: the variety of the quotations that the historical seed creates (see tools/oem_quotation.py seed-historical).

The Historical Quotes tab (HU-05) can only be tested for paging, filters and search with more than ten approved quotations that differ in
OEM name, type of work, site and device. The OEM Name is just a field of the quotation: it does not have to match the OEM contact that signs,
so every quotation can carry a different OEM name while all the emails go to the one QA test mailbox. The OEM names are values the OEM filter
already offers; the two customer/site pairs are real catalog pairs (customerId + siteProjectId) that the quotation form can pick.
"""
CUSTOMER_SITES = {
    "valle_verde": dict(customerId=6, customerName="Andes Renewables SpA", siteName="Valle Verde", siteProjectId=7,
                        siteLocation="Camino El Sol 450, Rancagua", siteLatitude=-34.1708, siteLongitude=-70.7443),
    "pampa_norte": dict(customerId=5, customerName="Atacama Solar Ltda", siteName="Pampa Norte", siteProjectId=6,
                        siteLocation="Ruta 5 Norte km 1340, Antofagasta", siteLatitude=-23.6509, siteLongitude=-70.3975),
}
OEM_NAMES = ("Workflow Progress Test OEM", "Hithium Energy Storage", "Texas Grid Storage LLC")
COMMISSIONING, WARRANTY = "Commissioning", "Warranty Repair"

# (tag, oem name, type of work, customer/site key, device or None)
SEED_VARIANTS = [
    ("V1", OEM_NAMES[0], COMMISSIONING, "valle_verde", None),
    ("V2", OEM_NAMES[1], WARRANTY, "pampa_norte", "PCS-SEED-01"),
    ("V3", OEM_NAMES[2], COMMISSIONING, "valle_verde", "PCS-SEED-02"),
    ("V4", OEM_NAMES[0], WARRANTY, "valle_verde", None),
    ("V5", OEM_NAMES[1], COMMISSIONING, "pampa_norte", None),
    ("V6", OEM_NAMES[2], WARRANTY, "pampa_norte", "BMS-SEED-03"),
    ("V7", OEM_NAMES[1], COMMISSIONING, "valle_verde", "BMS-SEED-04"),
    ("V8", OEM_NAMES[0], COMMISSIONING, "pampa_norte", None),
]
