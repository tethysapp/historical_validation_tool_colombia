import os
import uuid
import json
import pandas as pd
import numpy as np

from .auxFun import *

######################################################################
class Stations_manage:
    def __init__(self, path_dir):
        '''
        Stations management object
        '''

        self.path = os.sep.join(path_dir.split(os.sep)[:-1])
        self.full_data = self.__readfile__(path_dir)
        
        self.gnrl_dict = {'columns int search' : ['ID', 'new_COMID'],
                          'columns str search' : ['Name', 'Stream_Nam'],
                          'coord columns' : ['Latitude', 'Longitude']}
        
        self.__fix_columns__()


        self.data = self.full_data[self.gnrl_dict['columns int search'] + self.gnrl_dict['columns str search'] + self.gnrl_dict['coord columns']]
        self.data.reset_index(inplace=True)
        self.data.rename(columns={'index': 'ID_tmp'}, inplace=True)

        self.search_list = self.__extract_search_list__()

        print('Stations list loaded.')

    
    def __call__(self, search_id):
        '''
        Input: 
            search_data : str = value to search
        '''

        # Extract coords of the station
        coords = self.__coordssearch___(search_id)

        # Assert does not existence of the station
        if len(coords) < 1:
            return 'COLOMBIA.json', coords, 404, '', ''

        # Extract coords of the polygon
        lat_coord, lon_coord = get_zoom_coords(df=coords)

        # Build station output file
        output_station_file, station_file_cont = self.__printstaiongeojson__(df=coords)

        # Build coundary output file
        output_file, boundary_file_cont = self.__printgeojson__(lat_coord=lat_coord, lon_coord=lon_coord)

        return output_file, output_station_file, 200, station_file_cont, boundary_file_cont


    def __printstaiongeojson__(self, df):

        lon = self.gnrl_dict['coord columns'][1]
        lat = self.gnrl_dict['coord columns'][0]

        # TODO: Add variable name file for multyple user. And remove path
        # pathdir and name file
        # file_name = str(uuid.uuid4()) + '.json'
        file_name = 'station_geojson' + '.json'
        file_path = os.sep.join([self.path, file_name])


        # Build json
        feature = []
        for _, row in df.iterrows():
            feature.append({'type' : "Feature",
                            "geometry" : {"type" : "Point",
                                          "coordinates":[row[lon], row[lat]]}})
        json_file = {"type" : "FeatureCollection",
                     "features" : feature}


        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(json_file, f, ensure_ascii=False, indent=4)

        return file_name, json_file

    def __printgeojson__(self, lat_coord, lon_coord):
        
        # TODO: Add variable name file for multyple user. And remove path
        # pathdir and name file
        # file_name = str(uuid.uuid4()) + '.json'
        file_name = 'boundary_geojson' + '.json'
        file_path = os.sep.join([self.path, file_name])

        # Print json
        json_file = {"type":"FeatureCollection", 
                    "features": [{ "type" : "Feature",
                                   "geometry" : { "type"       : "Polygon",
                                                  "coordinates" : [[[lon_coord[0], lat_coord[0]],
                                                                    [lon_coord[1], lat_coord[1]],
                                                                    [lon_coord[3], lat_coord[3]],
                                                                    [lon_coord[2], lat_coord[2]]]]
                                                }
                                }]
                    }


        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(json_file, f, ensure_ascii=False, indent=4)
        
        return file_name, json_file


    def __coordssearch___(self, search_id):

        # Identify type of input
        try:
            # Search by code
            seach_case = 'int'
            search_id = str(int(search_id))
            columns_to_search = self.gnrl_dict['columns int search']
        except:
            # Search by name
            search_case = 'name'
            search_id = str(search_id).upper()
            columns_to_search = self.gnrl_dict['columns str search']

        
        # Extract column to search
        search_df = pd.DataFrame()
        for col in columns_to_search:
            tmp_df = pd.DataFrame()
            tmp_df['ID_tmp'] = self.data['ID_tmp']

           
            if seach_case == 'int':
                tmp_df['values'] = self.data[col].astype(str)
            elif seach_case == 'str':
                # TODO: Add decodifficator for spañish when by name is used
                tmp_df['values'] = self.data[col].astype(str)
            else:
                # TODO: Add search by lat,lon
                pass

            search_df = pd.concat([search_df, tmp_df], ignore_index=True)

        idtmp_to_search = search_df.loc[search_df['values'] == search_id]

        valids = self.data[columns_to_search].isin(idtmp_to_search['values'].values).values
        rv = self.data.loc[valids].copy()

        return rv


    def __extract_search_list__(self):
        rv = self.full_data[self.gnrl_dict['columns int search'] + self.gnrl_dict['columns str search']].copy()
        rv = np.unique(rv.values.ravel('F'))
        return rv.tolist()


    @staticmethod
    def __readfile__(path_dir):
        '''
        Read file for json (geojson) named -> IDEAM_Stations_v2.json
        '''
        data = json.load(open(path_dir))['features']
        df = pd.DataFrame()

        for line in data:
            line_data = line['properties']
            col_names = list(line_data.keys())
            col_data =[line_data[ii] for ii in col_names]
            tmp = pd.DataFrame(data = [col_data],
                               columns=col_names)
            df = pd.concat([df, tmp], ignore_index=True)

        for column in df.columns:
            df[column] = df[column].astype(str)

        return df
        

    def __fix_columns__(self):
        '''
        Fix the values of the columns depending of: integer value or string value
        '''
		# Change for str columns
        # for col_name in self.main_cols['str column name']:
        for col_name in self.gnrl_dict['columns str search']:

            # Replace null values
            self.full_data[col_name].fillna(value='na', inplace = True)

            # Replace other letters (ES)
            self.full_data[col_name] = self.full_data[col_name].str.lower()
            self.full_data[col_name] = list(map(lambda x: x.replace('á', 'a'), self.full_data[col_name]))
            self.full_data[col_name] = list(map(lambda x: x.replace('é', 'e'), self.full_data[col_name]))
            self.full_data[col_name] = list(map(lambda x: x.replace('í', 'i'), self.full_data[col_name]))
            self.full_data[col_name] = list(map(lambda x: x.replace('ó', 'o'), self.full_data[col_name]))
            self.full_data[col_name] = list(map(lambda x: x.replace('ú', 'u'), self.full_data[col_name]))
            # self.geoJSON[col_name] = list(map(lambda x: x.replace('ñ', 'n'), self.geoJSON[col_name]))
            self.full_data[col_name] = list(map(lambda x: x.replace('_', ' '), self.full_data[col_name]))
            self.full_data[col_name] = self.full_data[col_name].str.upper()
            self.full_data[col_name] = self.full_data[col_name].str.lstrip()
            self.full_data[col_name] = self.full_data[col_name].str.rstrip()

		# Change for int columns
        # for col_name in self.main_cols['int column name']:
        for col_name in self.gnrl_dict['columns int search']:
            self.full_data[col_name] = list(map(lambda x : str(int(float(x))), self.full_data[col_name]))

######################################################################