from src.monika import Monika
from pathlib import Path
#gps_campaign = Monika(config_path = Path.cwd() / 'tests' / 'GPS_Test' / 'monika_gps_test.yml')
#gps_campaign.add_devices()
#gps_campaign.export_results()

#spree_campaign = Monika(config_path = Path.cwd() / 'tests' / 'Spree_20251127' / 'monika_spree.yml')
#spree_campaign.add_devices()
#spree_campaign.export_results()
#priorgraben_campaign = Monika(config_path = Path.cwd() / 'tests' / 'GPS_Test' / 'monika_gps_test.yml')
priorgraben_campaign = Monika(config_path = Path.cwd() / 'tests' / 'Priorgraben_20260303' / 'monica_priorgraben.yml',paper_mode=True)
priorgraben_campaign.add_devices()
priorgraben_campaign.export_results()