from src.monika import Monika
from pathlib import Path
#gps_campaign = Monika(config_path = Path.cwd() / 'tests' / 'GPS_Test' / 'monika_gps_test.yml')
#gps_campaign.add_devices()
#gps_campaign.export_results()

#spree_campaign = Monika(config_path = Path.cwd() / 'tests' / 'Spree_20251127' / 'monika_spree.yml')
#spree_campaign.add_devices()
#spree_campaign.export_results()

kl_spree_campaign = Monika(config_path = Path.cwd() / 'tests' / 'Kleine_Spree_20251217' / 'monika_kl_spree.yml')
kl_spree_campaign.add_devices()
kl_spree_campaign.export_results()