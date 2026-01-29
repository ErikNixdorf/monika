import os
import pandas as pd
from datetime import timedelta,datetime
import matplotlib.pyplot as plt
from zoneinfo import ZoneInfo
import geopandas as gpd
import rasterio
import numpy as np
import pytz
import yaml
#%% Write a class Monika for this
from pathlib import Path
        
class Monika():
    def __init__(self,
                 config_path=Path(),wd=None,
                 name='monika1'):
        
        # load obvious ones    
        self.name = name
        if wd is None:
            self.wd = Path.cwd()
        else:
            self.wd=wd        
        #%% read the config file
        with open(config_path) as c:
            self.monika_cfg = yaml.safe_load(c)
        
        
        self.campaign = self.monika_cfg['info']['campaign']
        self.time_zone = self.monika_cfg['info']['time_zone']
        self.coordinate_system = self.monika_cfg['info']['coordinate_system']
        self.output_dir = self.wd /'output' / self.campaign
        
        #data path
        self.data_path = self.wd /self.monika_cfg['info']['data_dir'] / self.campaign
        
        #create some empty space for data
        self.data = pd.DataFrame()
        self.sonar_reflections=dict()
        
    @property
    def deeper(self):
        return self.data[self.data["type"] == "deeper"]
    
    @property
    def logger(self):
        return self.data[self.data["type"] == "logger"]
    
    
    #fill nans of the position data by the mean of existing data for each time step
    @staticmethod
    def _add_spatial_coordinates(df,gps_device =['deeper_1']):
        """
        fill nans of the position data by the mean of existing data for each time steps

        Parameters
        ----------
        df : TYPE
            DESCRIPTION.
        location_cols : TYPE, optional
            DESCRIPTION. The default is ['HW','RW'].

        Returns
        -------
        None.

        """
        df_out =df.copy()
        #get the valid GPS data from the requested device
        df_coords = df[df['name'] == gps_device][['HW','RW']].dropna()
        
        df_out.loc[:,['HW','RW']] = df_out[['HW','RW']].fillna(df_coords.reset_index()[['HW','RW','time']].groupby('time').mean())
        return df_out
    # delete all subsets which only consist of nan
    @staticmethod
    def _remove_noentry_devices(df_in,parameter = 'ec25',device_name_col='name'):
        """
        # delete all subsets which only consist of nan, which means the requested parameter has not been measured by the device
        #count non nan entries per device

        Parameters
        ----------
        df : TYPE
            DESCRIPTION.
        parameter : TYPE, optional
            DESCRIPTION. The default is 'ec25'.
        device_name_col : TYPE, optional
            DESCRIPTION. The default is 'name'.

        Returns
        -------
        None.

        """
        df = df_in.copy()
        #count non nan entries per device
        samples_per_sensor = df.groupby(device_name_col).agg({parameter:'count'})[parameter]
        valid_sensors = samples_per_sensor[samples_per_sensor>0].index
        df = df[df[device_name_col].isin(valid_sensors)]
        return df
    @staticmethod
    def _convert_unixtime(t,tz = "Europe/Berlin"):
        t = datetime(1970,1,1, tzinfo=ZoneInfo("UTC")) + timedelta(days=t/86400000)
        t = t.astimezone(ZoneInfo(tz))
        return t
    
    def add_devices(self):
        """
        Add and configure devices as specified in the configuration file.
        
        Iterates over all devices defined in the configuration and initializes
        them according to their declared type and settings.
        """
        # all devices requested by the config file
        for device_name,device in self.monika_cfg['devices'].items():            
            match device['type']:
                case 'logger':
                    self.add_logger(device['config'],
                                    name=device_name,
                                    data_path = self.data_path / device['file_name'],
                                    fabricate=device['fabricate'])
                
                case 'deeper':
                    if device['sonar']['use_sonar_reflection_data']:
                        device['sonar']['data_path'] = self.data_path / device['sonar']['file_name']
                    self.add_deeper(fabricate=device['fabricate'],
                                    name=device_name,
                                    data_path = self.data_path / device['file_name'],
                                    sonar_config = device['sonar'])
                case 'gps':
                    self.add_gps(fabricate=device['fabricate'],
                                    name=device_name,
                                    data_path = self.data_path / device['file_name'],
                                    )
            
                case _:
                    raise ValueError(f"Unsupported device type: {device['type']}")
            
    
    def export_results(self,output_dir=None):
        """
        Plot as requested

        Returns
        -------
        None.

        """
        if output_dir is None:
            output_dir = self.output_dir
        else:
            output_dir = output_dir
        
        self.plot_dir = output_dir / 'plots'
        self.plot_dir.mkdir(exist_ok=True,parents=True)
        
        for _,vis in self.monika_cfg['output'].items():
            
            match vis['type']:                
                case 'trajectory':
                    _ = self.plot_trajectory(vis['config'])
                case 'timeseries':
                    _ = self.plot_timeseries(vis['config'])
                case 'sonar_strength':
                    _ = self.plot_sonar_strength(name = vis['device_name'])
                    
        
        
        
        
        
    
    
    def add_deeper(self,name='deeper_1',fabricate= 'deepersonar_chirp3',
                        data_path = str(),sonar_config=dict()):
        
        df_deeper = self.read_bathymetry_data(data_path = self.wd / data_path)        
        if sonar_config['use_sonar_reflection_data']:
            sonar_config.update({'name':name,'fabricate':fabricate})
            df_sonar= self.read_sonardata(cfg=sonar_config)
            df_sonar=df_sonar.reindex(df_deeper.index)
            df_deeper['raw_sonar_depth'] = df_sonar
            
        df_deeper['name'] = name
        df_deeper['type'] = 'deeper'
        df_deeper['fabricate'] = fabricate
        self.data = pd.concat([self.data,df_deeper])
        
    def read_bathymetry_data(self,data_path = str()):
        """
        
        Read data and converts time and space
        Parameters
        ----------
        filename : TYPE, optional
            DESCRIPTION. The default is str().
        time_zone : TYPE, optional
            DESCRIPTION. The default is 'UTC'.

        Returns
        -------
        t : TYPE
            DESCRIPTION.

        """

        
        
        df_deeper = pd.read_csv(data_path)
        if len(df_deeper.columns) ==4:
            df_deeper.columns = ['Y[WGS84]','X[WGS84]','water_depth','t_unix']
        elif len(df_deeper.columns) ==5:
            df_deeper.columns = ['Y[WGS84]','X[WGS84]','water_depth','temp','t_unix']
        else:
            raise ValueError(f'{len(df_deeper.columns)} is unknown number of columns for labelling them automatically, check data')
            
        #replace 0 by nan in location data
        df_deeper[['Y[WGS84]','X[WGS84]']] = df_deeper[['Y[WGS84]','X[WGS84]']].replace(0,np.nan)

        # fix the time
        df_deeper['time'] = df_deeper['t_unix'].apply(lambda x:self._convert_unixtime(x,tz=self.time_zone))
        #bring to pytz standard
        df_deeper['time'] = (df_deeper['time'].dt.tz_convert("UTC").dt.tz_convert(pytz.timezone(self.time_zone)))
        #round to next second
        df_deeper = df_deeper.set_index('time',drop=True)
        #interpolate to next second
        df_deeper = df_deeper.loc[~df_deeper.index.duplicated(keep='first'), :]
        df_deeper = df_deeper.resample('1s').mean()
        df_deeper.index.freq=None
        #fix the space
        #convert to geodataframe
        df_deeper = gpd.GeoDataFrame(df_deeper, geometry = gpd.points_from_xy(df_deeper['X[WGS84]'],df_deeper['Y[WGS84]'],crs='4326'),crs='4326').to_crs(self.coordinate_system)
        df_deeper['HW'] = df_deeper.geometry.y
        df_deeper['RW'] = df_deeper.geometry.x
        
        
        return df_deeper        
        
    def read_sonardata(self,cfg={'data_path': str(),
                                       'pixel_resolution':0.0025,
                                       'min_water_depth' : 0.2,
                                       'resample_resolution' : None,
                                       }
                       ):
        """
        Copy from the other dataset the raw sensor data, experimental

        Returns
        -------
        None.

        """
        from scipy import signal
        def infer_bottom (df,min_water_depth=0.2,pixel_resolution = 0.0025):
            """
            Infers the bottom depth from an echo strength profile using peak detection.
        
            Parameters:
            ----------
            df : pandas.Series
                A 1D profile of echo strength values at a single time step.
                The index is assumed to represent depth bins or pixel indices.
            min_water_depth : float, optional (default=0.2)
                The minimum valid depth (in meters) to consider as a bottom.
                Shallower peaks are discarded.
            pixel_resolution : float, optional (default=0.0025)
                The vertical resolution (in meters per pixel) of the profile.
        
            Returns:
            -------
            float or np.nan
                Estimated bottom depth in meters. Returns NaN if no valid peak is found.
            """
            # --- Hyperparameter Calculation ---
            min_distance_samples = int((min_water_depth / pixel_resolution) / 2)
            prominence_threshold = df.std()
            
            # --- Peak Detection ---
            idx_peaks, _ = signal.find_peaks(df.values,height=None,
                                              distance=min_distance_samples,
                                              prominence = prominence_threshold)    
            
            # --- Convert to Depth and Filter ---
            peak_depths = np.array(idx_peaks) * pixel_resolution
            valid_peaks = peak_depths[peak_depths > min_water_depth]
            
            # --- Return ---
            if valid_peaks.size == 0:
                print(f'No valid bottom depth for time step {df.name}')
                return np.nan
            else:
                return valid_peaks[0]
            
        def sonar_dataframe_to_dataarray(df_sonar):
            """
            Converts a wide-format sonar DataFrame (time x depth) into an xarray DataArray.
        
            Parameters:
            ----------
            df_sonar : pandas.DataFrame
                A DataFrame where rows are timestamps (as index) and columns are depths (in meters),
                with values representing echo strength.
        
            Returns:
            -------
            xarray.DataArray
                A 2D DataArray with dimensions [depth, time], containing echo strength values.
            """
            # Reshape to long format
            df_long = df_sonar.reset_index().melt(
                id_vars='time',
                var_name='depth',
                value_name='echo_strength'
            )
        
            # Set MultiIndex and remove duplicates
            df_long = df_long.set_index(['time', 'depth'])
            df_long = df_long[~df_long.index.duplicated(keep=False)]
        
            # Convert to xarray and transpose to [depth, time]
            da = df_long.to_xarray().transpose('depth', 'time')
            
            return da
        
        
        
        # --- Determine max number of columns in sonar file dynamically ---
        with open(cfg['data_path']) as file:
            max_cols = max(len(line.split(',')) for line in file)
    
        # --- Load sonar data into DataFrame ---
        column_names = [round(i * cfg['pixel_resolution'], 4) for i in range(max_cols)]
        df_sonar = pd.read_csv(cfg['data_path'], header=None, names=column_names)
        
        # --- Convert Unix timestamps (ms) to datetime and set as index ---
        df_sonar['time'] = df_sonar.iloc[:,0].apply(lambda x:self._convert_unixtime(x,tz=self.time_zone))
        df_sonar['time'] = (df_sonar['time'].dt.tz_convert("UTC").dt.tz_convert(pytz.timezone(self.time_zone)))
        #df_sonar to next second
        df_sonar = df_sonar.set_index('time',drop=True)
        df_sonar = df_sonar.drop(columns=[0])
        # resample
        if cfg['resample_resolution'] is not None:
            df_sonar = df_sonar.loc[~df_sonar.index.duplicated(keep='first'), :]
            df_sonar = df_sonar.resample(cfg['resample_resolution']).mean()

        #get the peak    
        sonar_depth = df_sonar.apply(lambda x: infer_bottom(x, min_water_depth=cfg['min_water_depth'], 
                                                             pixel_resolution=cfg['pixel_resolution']),
                                      axis=1,
                                      )
        
        #rearrange and form a dataarray for plotting
        sonar_reflection = sonar_dataframe_to_dataarray(df_sonar)
        #add metadata
        sonar_reflection.attrs = cfg
        #add to collection
        self.sonar_reflections[cfg['name']] = sonar_reflection
        return sonar_depth
        
            

    
    
    def add_logger(self,config,name=str(),data_path=Path(),fabricate='solinst_ltc'):
        """
        

        Parameters
        ----------
        name : TYPE, optional
            DESCRIPTION. The default is str().
        data_path : TYPE, optional
            DESCRIPTION. The default is Path().
        logger_type : TYPE, optional
            DESCRIPTION. The default is 'solinst_ltc'.
        timeshift : TYPE, optional
            Timeshift in hours, in case logger is e.g on european summer time. The default is 0.

        Returns
        -------
        None.

        """
        df_logger = self.read_logger(data_path,config=config)
        df_logger['name'] = name
        df_logger['type'] = 'logger'
        df_logger['fabricate'] = fabricate
        
        self.data = pd.concat([self.data,df_logger])
        
        
        
        
        
        
    def read_logger(self,data_path=Path(),config=dict()):
        """
        Parameters
        ----------
        ec_lim : TYPE, optional
            DESCRIPTION. The default is [50,5000].
        temperature_correction_factor : TYPE, optional
            DESCRIPTION. The default is 0.019. Set it to 0 in order to not do temperature correction

        Returns
        -------
        None.

        """
        df = pd.read_csv(self.wd / data_path ,
                         skiprows=config['rows_to_skip'],
                         encoding='latin1',
                         sep=r"\s+",
                         skipfooter=1, 
                         names = ['date','hours','level','temp','ec'],
                         engine='python',
                         )
        df['time'] = pd.to_datetime(df['date'] + ' '+ df['hours'])
        df['time'] = df['time'].dt.tz_localize(self.time_zone)
        df['time'] = df['time'] + timedelta(hours=config['timeshift'])   
        df= df.set_index('time',drop=True)
        # add time zone
        df['EC25'] = df['ec'] / (1 + config['temperature_correction_factor'] * (df['temp'] - 25))
        #find the entries outside the range
        mask = ~df['EC25'].between(config['ec_lim'][0], config['ec_lim'][1])
        df.loc[mask,:] =np.nan
        df['name'] = data_path
        return df
    
    
    def add_gps(self,name='onboard_gps1',
                   fabricate='onboard_gps',
                   data_path = Path(''),
                   ):
        """
        Reads GPS Data from Company XYZ

        Parameters
        ----------
        name : TYPE, optional
            DESCRIPTION. The default is 'onboard_gps1'.
        fabricate : TYPE, optional
            DESCRIPTION. The default is 'onboard_gps'.
        data_path : TYPE, optional
            DESCRIPTION. The default is Path('').
         : TYPE
            DESCRIPTION.

        Returns
        -------
        None.

        """
        def nmea_to_wgs84(value, direction):
            """
            Convert NMEA lat/lon to WGS84 decimal degrees.
            value: float or str (ddmm.mmmm or dddmm.mmmm)
            """
            value = float(value)
        
            degrees = int(value // 100)
            minutes = value - degrees * 100
        
            decimal = degrees + minutes / 60
        
            if direction in ("S", "W"):
                decimal *= -1
        
            return decimal
        
        
        def extract_nmea(line,print_out=True):
    
            """
            Extract selected information from NMEA 0183 GGA or RMC sentences.
        
            Supported sentence types
            ------------------------
            - GGA: Global Positioning System Fix Data
            - RMC: Recommended Minimum Navigation Information
        
            Extracted fields
            ----------------
            - time : datetime.time
                UTC time parsed from the NMEA sentence.
            - date : datetime.date or None
                Date parsed from RMC sentences; None for GGA sentences.
            - lat : str
                Latitude in NMEA format (DDMM.MMMM + hemisphere letter).
            - lng : str
                Longitude in NMEA format (DDDMM.MMMM + hemisphere letter).
            - height : str or None
                Altitude including unit (from GGA only).
            - sat_number : int or None
                Number of satellites used for the fix (from GGA only).
            - dop_precision : float or None
                Horizontal dilution of precision (HDOP) from GGA only.
        
            Parameters
            ----------
            line : str
                A single NMEA sentence (e.g. "$GPGGA,...", "$GPRMC,...").
            print_out : bool, optional
                If True, prints a human-readable summary to stdout.
        
            Returns
            -------
            dict or None
                Dictionary with extracted values if the line is a GGA or RMC
                sentence, otherwise None.
        
            Notes
            -----
            - Latitude and longitude are NOT converted to decimal degrees.
            - The function assumes valid NMEA formatting and does not perform
              checksum validation.
            """
            def nmea_to_wgs84(value, direction):
                """
                Convert NMEA lat/lon to WGS84 decimal degrees.
                value: float or str (ddmm.mmmm or dddmm.mmmm)
                """
                value = float(value)
            
                degrees = int(value // 100)
                minutes = value - degrees * 100
            
                decimal = degrees + minutes / 60
            
                if direction in ("S", "W"):
                    decimal *= -1
            
                return decimal
            
            
            if line.startswith('$') and ('GGA' in line or 'RMC' in line):
                properties =line.split(',')
                # UTC time (hhmmss.sss)
                time = datetime.strptime(properties[1],'%H%M%S.%f').time()
                # lat and lon
                #NMEA 0183 uses a representation consisting of degrees and minutes. 
                #For geographical latitude, “XXYY.ZZZZ” and for geographical longitude, “XXXYY.ZZZZ”; 
                #with ‘X’ for degrees, “Y.Z” for minutes (including decimal places). 
                #The number of decimal places for the minutes may vary.
                lat_id = 2
                if properties[2].lower() in ['a','v']:
                    lat_id += 1
                # NMEA coordinate format: degrees + minutes + hemisphere, hemisphere will control the signs  
                lat = nmea_to_wgs84(properties[lat_id],properties[lat_id+1])
                lng = nmea_to_wgs84(properties[lat_id+2],properties[lat_id+3])                
                
                # Defaults for optional fields
                height = None
                sat_number = None
                dop_precision = None
                date_str = ''      
                
                if 'GGA' in properties[0]:
                    line_type = 'GGA'
                    height = properties[9]#+properties[10]
                    sat_number = int(properties[lat_id+5])
                    dop_precision= float(properties[lat_id+6])
                
                if 'RMC' in properties[0]:
                    line_type='RMC'
                    date_str = datetime.strptime(properties[-4],'%d%m%y').date()
                
                if print_out:
                    print(f"--- Zeit: {time}{date_str} ---")
                    print(f"Breitengrad: {float(lat[:-1]):.6f} {lat[-1]}")
                    print(f"Längengrad:  {float(lng[:-1]):.6f} {lng[-1]}")
                    if 'GGA' in properties[0]:
                        print(f"Höhe:        {height} {properties[10]}")
                        print(f"Satelliten:  {sat_number}")
                        print(f"Satelliten_DOP:  {dop_precision}")
                    
                    print("-" * 30)
                
                #write output
                output=dict({'lat':lat,
                                   'lng':lng,
                                   'height':height,
                                   'sat_number':sat_number,
                                   'dop_precision': dop_precision,
                                   'date':date_str,
                                   'time':time,
                                   'line_type':line_type
                                   }
                            )
                return output
            else:
                return
        
        #%% Open the data and extract the lines
        line_id =0
        nmea_lines=dict()
        with open(data_path) as file:
            for line in file:
                nmea_lines.update({line_id :extract_nmea(line,print_out=False)})
                line_id+=1
        
        df_gps_raw = pd.DataFrame.from_dict(nmea_lines).T
        #split into the two relevant categories
        df_GGA = df_gps_raw[df_gps_raw['line_type'] == 'GGA'].set_index('time').drop(columns=['line_type','date'])
        df_RMC = df_gps_raw[df_gps_raw['line_type'] == 'RMC'].set_index('time')['date']
        print('GPS GGA and RMC fusion based on same time but date is not considered. For multiple day operation the current implementation fails')
        df_gps = pd.concat([df_GGA,df_RMC.to_frame()],axis=1)
        
        #change the index to true time
        df_gps.index= pd.to_datetime(df_gps["date"].astype(str).values + " " + df_gps.index.astype(str).values,format='mixed')
        df_gps.index = df_gps.index.tz_localize(self.time_zone)
        df_gps.index.name= 'time'
        #clean  cols
        df_gps = df_gps.drop(columns=['date'])
        #enforce numeric
        df_gps = df_gps.apply(pd.to_numeric, errors="coerce")
        
        
        
        #interpolate to the next second
        df_gps = df_gps.loc[~df_gps.index.duplicated(keep='first'), :]
        df_gps = df_gps.resample('1s').mean()
        df_gps.index.freq=None
        # fix the space
        gdf_gps = gpd.GeoDataFrame(df_gps, geometry = gpd.points_from_xy(df_gps['lng'],df_gps['lat'],crs='4326'),crs='4326').to_crs(self.coordinate_system)
        df_gps['HW'] = gdf_gps.geometry.y
        df_gps['RW'] = gdf_gps.geometry.x
        
        df_gps['name'] = name
        df_gps['type'] = 'gps'
        df_gps['fabricate'] = fabricate
        self.data = pd.concat([self.data,df_gps])
        
    
    def plot_trajectory(self,plt_cfg):
        """
        Plot device trajectories on a georeferenced background image.
    
        Parameters
        ----------
        plt_cfg : dict
            Plot configuration containing:
            - parameter : str
            - device_name : str or "all"
            - label_interval : int (minutes)
            - background_image : str
            -location_cols : list
    
        Returns
        -------
        pandas.DataFrame
            Processed trajectory data used for plotting.
        """
        
        # --- Config ---
        param = plt_cfg["parameter"]
        device_name = plt_cfg["device_name"]
        label_interval = int(plt_cfg["label_interval"])
        background_image = plt_cfg["background_image"]
        gps_to_use = plt_cfg['gps_to_use']
        
        # --- Data preparation ---
        df_traject  = self.data[['HW', 'RW',param,'type','name','fabricate']].copy()
        
        #fill nans of the position data by the mean of existing data for each time ste
        df_traject = self._add_spatial_coordinates(df_traject,
                                                   gps_device =gps_to_use)        
        # delete all subsets which only consist of nan
        df_traject = self._remove_noentry_devices(df_traject,
                                                  parameter = param,
                                                  device_name_col='name')
        
        #delete all without location and reset time
        df_traject = df_traject[df_traject[['HW', 'RW']].count(axis=1)>1].reset_index(drop=False)
        
        # --- Device selection & title ---        
        if device_name [0]  != 'all':
            title_str = f"Trajectory of {device_name} during {self.campaign} colored by the mean of {param}"
            df_traject = df_traject[df_traject['name'].isin(device_name)]
        else:
            title_str = f"Trajectory of {device_name} Devices during {self.campaign} colored by the mean of {param}"
        #get the mean
        df_traject = df_traject.groupby('time').mean(numeric_only=True).reset_index(drop=False)
        # --- Label selection ---
        label_interval = pd.Timedelta(minutes=label_interval)
        t0 = df_traject["time"].iloc[0]
        label_mask = (
            (df_traject["time"] - t0) % label_interval
            < pd.Timedelta(seconds=1)
        )
        df_labels = df_traject[label_mask]


        # --- Load background raster ---
        tiff_path = self.data_path / background_image
        with rasterio.open(tiff_path) as src:
            img = src.read()  # shape: (bands, height, width)
            extent = [
                src.bounds.left,
                src.bounds.right,
                src.bounds.bottom,
                src.bounds.top
            ]


        # --- Plot ---
        fig, ax = plt.subplots(figsize=(16, 9))

        # Show background
        # transpose the image from (bands, H, W) → (H, W, bands)
        ax.imshow(img.transpose(1, 2, 0), extent=extent)

        sc = ax.scatter(
            df_traject['RW'],
            df_traject['HW'],
            c=df_traject[param],
            cmap="viridis",
            s=20
        )

        cbar = plt.colorbar(sc, ax=ax)
        cbar.set_label(param)
        
        ax.set(
            xlabel="Easting",
            ylabel="Northing",
            title=title_str,
        )

        for _, row in df_labels.iterrows():
            ax.text(
                row['RW'],
                row['HW'],
                row["time"].strftime("%H:%M"),
                fontsize=12,
                ha="left",
                va="bottom",
            bbox=dict(
                boxstyle="round,pad=0.2",
                facecolor="grey",
                edgecolor="black",
                alpha=0.5
            )
            )
            
            
        # --- Save outputs ---
        plot_name = f"trajectory_of_{param}_during_{self.campaign}"
        plot_path = self.output_dir / "plots"    
        plt.savefig(plot_path / f"{plot_name}.png", dpi=300)

        plt.close()

        df_traject.to_csv(plot_path / f"{plot_name}.csv")
        
        
        return df_traject
        

    def plot_timeseries(self,plt_cfg):
        """
        
        Parameters
        ----------
        label_interval : TYPE
            gives label of distance from starting point.
        parameter : TYPE, optional
            DESCRIPTION. The default is 'EC25'.
    
        Returns
        -------
        None.
    
        """
        
        # --- Config ---
        parameter = plt_cfg["parameter"]
        device_name = plt_cfg["device_name"]
        label_interval = int(plt_cfg["label_interval"])
        remove_entries_with_no_location = plt_cfg["remove_entries_with_no_location"]  
        gps_to_use = plt_cfg['gps_to_use']
        
        
        # extract data
        df_ts = self.data[['HW', 'RW',parameter,'type','name','fabricate']].copy()
        
        location_cols = ['HW', 'RW']
        #fill nans of the position data by the mean of existing data for each time ste
        df_ts = self._add_spatial_coordinates(df_ts,gps_device =gps_to_use)        
        # delete all subsets which only consist of nan
        df_ts = self._remove_noentry_devices(df_ts,parameter = parameter,device_name_col='name')    
        
        # reduce data 
        if device_name[0].lower() != 'all':
            df_ts = df_ts[df_ts['name'].isin(device_name)]
            
            
        #start figure    
        fig, ax= plt.subplots(
            nrows=1,
            ncols=1,
            figsize=(12, 8)
        )
    
        # -----------------------------
        # plot the parameter    # -----------------------------
        if label_interval>0:
            plot_label=True
        else:
            plot_label= False
        for logger, group in df_ts.groupby("name"):
            group = group.sort_index()
            
            # check that we label the correct distances
            group['has_coordinate'] =group[location_cols].count(axis=1)>1            
            if remove_entries_with_no_location:
                group = group[group['has_coordinate']]
            
            
            _ = ax.plot(
                group.index,
                group[parameter],
                label=logger,
                linewidth=2,
                alpha=0.9
            )
            # get the color
            
            
            if plot_label:
                # calculate the distance from first point
                dx = group['RW'].diff()
                dy = group['HW'].diff()
                group['distance'] = np.sqrt(dx**2 + dy**2)
                #accumulate and replace nan
                group['distance'] = group['distance'].cumsum().replace(np.nan,0)
                
                #add mask for label
                group['mask'] = (group['distance']  % label_interval).diff()<0
                

                
                t_label_start = group[group['has_coordinate']].iloc[0].name
                group['distance'] = group['distance'].replace(0,np.nan)
                group.loc[t_label_start,'distance'] = 0
                group.loc[t_label_start,'mask'] = True
                    
                
                df_labels = group[group['mask']]
                df_labels=df_labels[~df_labels['distance'].isna()]
                for time, row in df_labels.iterrows():
                    ax.text(
                        time,
                        row[parameter],
                        f'{np.floor(row["distance"])} m',
                        fontsize=12,
                        ha="left",
                        va="bottom",
                    bbox=dict(
                        boxstyle="round,pad=0.2",
                        facecolor='grey',
                        edgecolor="black",
                        alpha=0.5
                    )
                    )
                    
                    #plot also a vertical line
                    ax.axvline(x=time,linestyle='--',color='grey',alpha=0.6)
                    
                #set label_tool to False
                plot_label=False
                
            
    
        ax.set_title(f"Times Series of Parameter {parameter} of {device_name} Devices during {self.campaign}", fontsize=16, pad=10)
        ax.set_ylabel(parameter, fontsize=13)
        ax.grid(True, linestyle="--", alpha=0.4)
        ax.legend(title="Device", frameon=True)
        ax.set_xlabel('time', fontsize=13)
        # Rotate x-axis tick labels
        #plt.setp(ax2.get_xticklabels(), rotation=30)
    
        # Adjust layout and save figure
        plt.tight_layout()
        plt.show()
        
        plot_name = f"TS_of_{parameter}_during_{self.campaign}"
        plot_path = self.output_dir / "plots"    
        plt.savefig(plot_path / f"{plot_name}.png", dpi=300)
        plt.close()
        df_ts.to_csv(plot_path / f"{plot_name}.csv")
        
        return df_ts
        
        # plot and 
        
    def plot_sonar_strength(self,name='deeper_1'):
        """
        Plots the sonar strengths

        Returns
        -------
        None.

        """
        if not hasattr(self, 'sonar_reflections'):
            raise Warning('No sonar data available for plotting, run add_deeper first')
            return
        fig, ax = plt.subplots(figsize=(12, 6))
        da_sonar = self.sonar_reflections[name]
        da_sonar['echo_strength'].plot(ax=ax)
        
        #extract_direct_bathymetrydata
        df_ref = self.data[self.data['name'] == da_sonar.attrs['name']]
        #    You need to ensure the x-axis for the new line matches the DataArray's x-axis
        ax.plot(df_ref.index,
                df_ref['water_depth'],
                color='red', 
                linestyle='-', label='Water Depth Internally Computed by Deeper')
        
        ax.plot(df_ref.index,
                df_ref['raw_sonar_depth'],
                color='magenta', 
                linestyle='-', label='Water Depth Computed by Echo Analysis',
                linewidth=1.5)
        
        
        ax.xaxis.tick_top()
        ax.xaxis.set_label_position('top')
        ax.invert_yaxis()
        ax.set_title(f"Echo Strength Profile for {name}")
        ax.set_xlabel("Time (UTC)")
        ax.set_ylabel("Distance/Depth (m)")        
        ax.legend(loc='lower center')
        
        plot_name = f"Echo_Reflection_Strength_Profile_for{name}"
        plot_path = self.output_dir / "plots"    
        plt.savefig(plot_path / f"{plot_name}.png", dpi=300)
        plt.close()


#%% test the scheme
def run_demo(plot=True,config_path=Path.cwd() / 'tests' / 'Kleine_Spree_20251217' / 'monika_kl_spree.yml' ):
    """Run a demonstration of the MONIKA processing and plotting pipeline."""

    monika = Monika(
        wd=Path.cwd(),
        config_path=config_path)
    
    monika.add_devices()
    if plot:
        monika.export_results()
    """

    monika.add_deeper(
        data_path=Path("deeper_kleine_spree.csv"),
        name="deeper_1",
        add_sonar_depth=True,
        sonar_config={'sonar_path': "sonar.csv",
                   'pixel_resolution':0.0025,
                   'min_water_depth' : 0.1,
                   'resample_resolution' : '1s',
                   }
    )
    
    monika.add_gps(name='onboard_gps1',
                   fabricate='onboard_gps',
                   data_path = Path(''),
                   )
    
    
        
   

    monika.add_logger(
        name="monika_left",
        data_path=Path("monika_left.lev"),
        logger_type="solinst_ltc",
        timeshift=0,
    )

    monika.add_logger(
        name="monika_right",
        data_path=Path("monika_right.lev"),
        logger_type="solinst_ltc",
        timeshift=0,
    )
    
    if plot:
    
        monika.plot_trajectory(
            background_image=Path("study_site.tif"),
            label_interval=1,
            parameter="temp",
        )
    
        monika.plot_timeseries(
            label_interval=100,
            parameter="temp",
            remove_entries_with_no_location=True,
        )
        
        monika.plot_sonar_strength(name='deeper_1')
    
    """
if __name__ == "__main__":
    run_demo()

