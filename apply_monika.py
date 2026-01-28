from src.monika import Monika
from pathlib import Path
gps_campaign = Monika(config_path = Path.cwd() / 'tests' / 'GPS_Test' / 'monika_gps_test.yml')
gps_campaign.add_devices()
gps_campaign.export_results()