"""
Master site registry for TAHMO/Arable installations.

Source: Arable_site_installations_Sites.xlsx
  - GPS/metadata from the "Arable Sites" tab (lat/lon, region, org, install date)
  - Current install status from the "22.01.2026" tab (device ID, site name, status, country)

These two tabs are keyed by device ID, but several devices were physically
swapped at the same site over time (old unit removed, new one installed),
so a handful of rows below are matched by SITE NAME instead of device ID.
Those are flagged with match="name" so it's auditable rather than a silent
guess. Two devices in the current tab have no site left at all (uninstalled,
no replacement) and are given lat=None, lon=None -- they show up in tables,
not on the map.

If any of this doesn't match reality (a name-matched row is wrong, an
install date is off), it's easiest to just edit the entry below directly.
"""

# match: "id"   -> device ID appears directly in both tabs, high confidence
#        "name" -> device ID changed (unit swapped); matched by site/org name instead
SITE_REGISTRY = [
    {"device_id": "D007084", "site_name": "Homa Bay – Otieno's Farm", "status": "Active",
     "country": "Kenya", "region": "Homa Bay", "org": "SGS",
     "lat": -0.62507, "lon": 34.6131, "install_date": "2024-08-27", "match": "id"},

    {"device_id": "D006023", "site_name": "Moi University", "status": "Active",
     "country": "Kenya", "region": "Eldoret", "org": "Moi University",
     "lat": 0.28959, "lon": 35.294809, "install_date": "2024-08-26", "match": "name",
     "note": "Replaced original device D006093 at same site."},

    {"device_id": "D005886", "site_name": "Meru SGS Formal Site", "status": "Active",
     "country": "Kenya", "region": "Meru", "org": "SGS",
     "lat": 0.0881667, "lon": 37.80714, "install_date": "2024-08-16", "match": "id"},

    {"device_id": "D006092", "site_name": "Mwea", "status": "Active",
     "country": "Kenya", "region": "Mwea", "org": "Mwea Irrigation Scheme (+IRRI)",
     "lat": -0.737344, "lon": 37.34474, "install_date": "2024-08-26", "match": "id"},

    {"device_id": "D006989", "site_name": "Nandi Farm – Sang's Farm", "status": "Active",
     "country": "Kenya", "region": "Nandi Falls", "org": "Sang's Farm",
     "lat": 0.20766, "lon": 35.30925, "install_date": "2024-08-27", "match": "id"},

    {"device_id": "D007106", "site_name": "Naivasha KARLO", "status": "Active",
     "country": "Kenya", "region": "Naivasha", "org": "KALRO",
     "lat": -0.680629, "lon": 36.414696, "install_date": "2024-08-26", "match": "id"},

    {"device_id": "D007042", "site_name": "Kenarava Farm", "status": "Active",
     "country": "Kenya", "region": "Nairobi", "org": "Kenarava Test Farm",
     "lat": -1.2248, "lon": 36.78257, "install_date": "2024-08-01", "match": "id"},

    {"device_id": "D005994", "site_name": "Mang'ola_Yara Farm", "status": "Active",
     "country": "Tanzania", "region": "Mang'ola", "org": "Mang'ola_Yara Farm",
     "lat": -3.45656, "lon": 35.50838, "install_date": "2025-02-21", "match": "id"},

    {"device_id": "D007449", "site_name": "Mbeya Farm (MUSTI Mbeya)", "status": "Active",
     "country": "Tanzania", "region": "Mbeya", "org": "Mbeya Farm",
     "lat": -8.94157, "lon": 33.42619, "install_date": "2025-02-19", "match": "name",
     "note": "Replaced original device D006980 (now removed) at same site."},

    {"device_id": "D008331", "site_name": "Maseno University", "status": "Active",
     "country": "Kenya", "region": "Kisumu", "org": "Maseno University",
     "lat": -0.0027274, "lon": 34.5969239, "install_date": "2024-08-28", "match": "name",
     "note": "Device at this site has been swapped more than once; install date is the original."},

    {"device_id": "D006098", "site_name": "Ndovu", "status": "Active",
     "country": "Kenya", "region": "Ololunga", "org": "Ndovu Farm",
     "lat": -1.05788, "lon": 35.63959, "install_date": "2024-11-20", "match": "id"},

    {"device_id": "D005926", "site_name": "Kibwezi YNDU Farm", "status": "Active",
     "country": "Kenya", "region": "Kibwezi", "org": "YNDU Farm",
     "lat": -2.502397, "lon": 38.211188, "install_date": "2024-11-06", "match": "id"},

    {"device_id": "D008281", "site_name": "Kilgoris", "status": "Active",
     "country": "Kenya", "region": "Kilgoris", "org": "Saitoti's Farm",
     "lat": -1.12164, "lon": 34.87178, "install_date": "2024-11-21", "match": "id"},

    {"device_id": "D006135", "site_name": "AusQuest Farm", "status": "Active",
     "country": "Kenya", "region": "Machakos", "org": "Ausquest Farm",
     "lat": -1.583907, "lon": 37.079766, "install_date": "2024-08-15", "match": "id"},

    {"device_id": "D006168", "site_name": "Kwale", "status": "Active",
     "country": "Kenya", "region": "Kwale, East Coast", "org": "KALRO",
     "lat": -4.165991, "lon": 39.572865, "install_date": "2024-08-21", "match": "id"},

    {"device_id": "D008303", "site_name": "Ikerege", "status": "Active",
     "country": "Kenya", "region": "Ikerege", "org": "Juma Swagi Farm",
     "lat": -1.19587, "lon": 34.5622, "install_date": "2024-11-21", "match": "id"},

    {"device_id": "D007030", "site_name": "Katumani Research Station", "status": "Inactive (Low Battery)",
     "country": "Kenya", "region": "Katumani", "org": "KALRO Machakos",
     "lat": -1.5822, "lon": 37.245, "install_date": "2024-08-15", "match": "id"},

    {"device_id": "D007015", "site_name": "Lake View – Bunda Farm", "status": "Inactive (Low Battery)",
     "country": "Tanzania", "region": "Bunda", "org": "Lake View Bunda Farm",
     "lat": -2.12007, "lon": 33.68775, "install_date": "2025-02-27", "match": "name",
     "note": "Replaced original device D007011 (now removed) at same site."},

    {"device_id": "D006997", "site_name": "Nakuru Agrico", "status": "Inactive (Low Battery)",
     "country": "Kenya", "region": "Nakuru", "org": "Agrico",
     "lat": -0.1770817, "lon": 36.0391733, "install_date": "2024-09-01", "match": "name",
     "note": "Replacement device at the same Nakuru Agrico site as D006221."},

    {"device_id": "D006221", "site_name": "Nakuru Agrico (removed)", "status": "Inactive",
     "country": "Kenya", "region": "Nakuru", "org": "Agrico",
     "lat": -0.1770817, "lon": 36.0391733, "install_date": "2024-09-01", "match": "id",
     "note": "Uninstalled; needs deactivating on the Arable portal."},

    {"device_id": "D007095", "site_name": "(not installed)", "status": "Not Installed",
     "country": "Kenya", "region": None, "org": None,
     "lat": None, "lon": None, "install_date": None, "match": "none",
     "note": "Not yet installed at any current site."},

    {"device_id": "D007035", "site_name": "(uninstalled)", "status": "Uninstalled",
     "country": "Kenya", "region": None, "org": None,
     "lat": None, "lon": None, "install_date": None, "match": "none",
     "note": "Removed due to battery drainage; no confirmed site match in the GPS tab."},

    {"device_id": "D005868", "site_name": "Kenarava Farm (removed)", "status": "Uninstalled",
     "country": "Kenya", "region": "Nairobi", "org": "Kenarava Test Farm",
     "lat": -1.2248, "lon": 36.78257, "install_date": None, "match": "name",
     "note": "Former device at the Kenarava Farm site (now D007042 is active there)."},

    {"device_id": "D007011", "site_name": "Lake View – Bunda Farm (removed)", "status": "Uninstalled",
     "country": "Tanzania", "region": "Bunda", "org": "Lake View Bunda Farm",
     "lat": -2.12007, "lon": 33.68775, "install_date": None, "match": "name",
     "note": "Former device at the Bunda site (now D007015 is active there)."},

    {"device_id": "D006980", "site_name": "Mbeya Farm (removed)", "status": "Uninstalled",
     "country": "Tanzania", "region": "Mbeya", "org": "Mbeya Farm",
     "lat": -8.94157, "lon": 33.42619, "install_date": None, "match": "name",
     "note": "Former device at the Mbeya site (now D007449 is active there)."},
]
