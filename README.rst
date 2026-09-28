Monika
=========


This package assists to analyse and export data obtained from different sensors that are mounted on the MONICA platform. It provides a framework that has been tested for LTC datalogger from the company Solinst Canada Ltd and the CHIRP Sonar from Deeper UAB 

Data obtained from differents sensors are connected with each other using the time. The plotting routine provides both, time series and transect plots.
There are 3 test cases in the ``tests`` directory that  provide real field data  from monitoring campaigns
.. code:: python

   from src.monika import Monika

   # load the yml file which provides the configuration of a campaign
   spree_campaign = Monika(config_path = Path.cwd() / 'tests' / 'Spree_20251127' / 'monika_spree.yml')

   # Load all the devices in accordance to the defined setup
   spree_campaign.add_devices()

   # Export the results
	spree_campaign.export_results()
   
..
