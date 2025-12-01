from .support import historical_decorator, access_token_decorator
from io import StringIO
from datetime import datetime, timedelta
from datetime import datetime as dt
from logging import Logger
from threading import RLock
from colorama import Style, Fore
from typing import List, Dict
import os
import requests
import pandas as pd
import json
import lz4.block
import struct
import base64
import shutil
import pickle

class HistoricalREST:
    def __init__(self, login_id: str, password: str, url: str, broker_token: str, logger: Logger):  # NO PORT, broker token needed from now on
        self.login_id = login_id
        self.password = password
        self.url = url
        self.broker_token = broker_token
        self.logger = logger
        self.thread_lock = RLock()
        self.access_token = None
        self.bhavcopy_last_completed = None
        self.access_token_expiry_time = None
        try:
            self.hist_login()
        except Exception as e:
            self.logger.error(f"Failed to connect REST historical API -> {type(e)} = {e}")

    def get_new_token(self ):
        url_auth = "https://auth.truedata.in/token"
        payload = f"username={self.login_id}&password={self.password}&grant_type=password"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        token_json = requests.request("POST", url_auth, headers=headers, data=payload).json()
        return token_json

    def hist_login(self):
        token_json = self.get_new_token()
        try:
            if token_json['access_token']:
                self.access_token = token_json['access_token']
                self.access_token_expiry_time = datetime.now() + timedelta(seconds=token_json['expires_in'] - 15)  # 15 seconds is random buffer time
                self.logger.warning(f"{Style.NORMAL}{Fore.BLUE}Connected successfully to TrueData Historical Data Service... {Style.RESET_ALL}")
        except Exception as e:
            self.logger.error(f"Failed to connect -> {token_json['error_description']}{type(e)} = {e}")
            self.access_token = None

    # noinspection PyUnusedLocal
    @access_token_decorator
    @historical_decorator
    def get_n_historic_bars(self, contract, end_time, no_of_bars, bar_size, options=None, bidask=False):
        source_bar_type_string = 'getlastnbars'
        if 'data_type' not in options.keys():
            options['data_type'] = 'csv'
        try:
            encoded_payload = {
                'symbol': contract,
                'interval': bar_size,
                'response': options['data_type'],
                'bidask': 0 ,
                'comp': 'true',
            }
            unencoded_payload = {}
            unencoded_payload = "&".join(unencoded_payload)
            if bar_size == 'tick':
                encoded_payload['nticks'] = no_of_bars
                source_bar_type_string = 'getlastnticks'
                if bidask:
                    encoded_payload['bidask'] = 1
            else:  # Not ticks
                encoded_payload['nbars'] = no_of_bars
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }

            with self.thread_lock:
                url = f"{self.url}/{source_bar_type_string}?{unencoded_payload}"
                response = requests.get(url, headers=headers, params=encoded_payload)
                if response.status_code == 429:
                    error = base64.b64decode(response.content).decode('utf-8')
                    raise TooManyRequestsError(error)
                hist_data = HistoricalREST.decompress_data(response.content)
        except Exception as e:
            self.logger.error(f"{type(e)} -> {e}")
            return None
            # json_response = {"success": False, "message": f"({type(e)}) {addn_err_str} -> {e}"}
        hist_data = self.parse_data(hist_data, options)
        return options['processor_to_call'][options['data_type']](hist_data, time_format=options['time_format'])

    @access_token_decorator
    @historical_decorator
    def get_historic_data(self, contract, end_time, start_time, bar_size, delivery = False , options=None, bidask=False ):
        source_bar_type_string = 'getbars'
        if 'data_type' not in options.keys():
            options['data_type'] = 'csv'
        try:
            encoded_payload = {
                'symbol': contract,
                'interval': bar_size,
                'response': options['data_type'],
                'comp': 'true',
            }
            encoded_payload.update({'delivery' : 'true'}) if delivery and bar_size =="eod" else 0
            unencoded_payload = {
                f"from={start_time}",
                f"to={end_time}"
            }
            unencoded_payload = "&".join(unencoded_payload)
            if bar_size == 'tick':
                encoded_payload['bidask'] = 0
                source_bar_type_string = 'getticks'
                if bidask:
                    encoded_payload['bidask'] = 1
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }
            with self.thread_lock:
                url = f"{self.url}/{source_bar_type_string}?{unencoded_payload}"
                response = requests.get(url, headers=headers, params=encoded_payload)
                if response.status_code == 429:
                    error = base64.b64decode(response.content).decode('utf-8')
                    raise TooManyRequestsError(error)
                hist_data = HistoricalREST.decompress_data(response.content)
        except Exception as e:
            self.logger.error(f"{type(e)} -> {e}")
            return None
            # json_response = {"success": False, "message": f"({type(e)}) {addn_err_str} -> {e}"}
        hist_data = self.parse_data(hist_data, options)
        if delivery:
            return options['processor_to_call'][options['data_type']](hist_data, time_format=options['time_format'] , delivery = delivery)
        return options['processor_to_call'][options['data_type']](hist_data, time_format=options['time_format'])

    def get_gainers_losers(self , segment, topn , gainers , df_style ):
        source_string = "gettopngainers" if gainers else "gettopnlosers"
        headers = {'Authorization': f'Bearer {self.access_token}'}
        payload = {'segment': segment , 'topn': topn , 'response':'csv' }
        url = f"{self.url}/{source_string}?"
        try:
            with self.thread_lock:
                response = requests.get(url, headers=headers , params=payload )
                out = response.text
            df = pd.read_csv(StringIO(out))
            df = df if df_style else list(df.T.to_dict().values())
            df.set_index(["symbol"] , inplace=True) if df_style else 0
        except Exception as e:
            self.logger.error(f"{type(e)} -> No match found for this segment {segment}")
            df = []
        return df


    def parse_data(self, hist_data, options):
        if options['data_type'] == 'csv':
            if hist_data.startswith('No data exists for') or hist_data.startswith('Symbol does not exist'):
                self.logger.error(f'{hist_data}')
                return ''  # Note to devs: Leave this as str to avoid "split" error
            else:
                return hist_data
        else:  # JSON format
            try:
                hist_data = json.loads(hist_data)
            except json.decoder.JSONDecodeError:
                self.logger.error(f'Caught a JSONDecodeError for this request')
                return []
            if hist_data['status'] != 'Success':
                self.logger.error(f"{hist_data['status']}")
                return []
            else:
                return hist_data['Records']

    def bhavcopy_status(self, segment: str):
        url = f'https://history.truedata.in/getbhavcopystatus?segment={segment}&response=csv'
        payload = {}
        headers = {
            'Authorization': f'Bearer {self.access_token}'
        }
        response = requests.request("GET", url, headers=headers, data=payload)
        status = response.text.strip().split('\r\n')[-1].split(',')
        assert segment == status[0]
        self.bhavcopy_last_completed = datetime.strptime(status[1], "%Y-%m-%dT%H:%M:%S")

    @access_token_decorator
    def bhavcopy(self, segment: str, date: datetime, return_completed: bool) -> List[Dict]:
        try:
            self.bhavcopy_status(segment)
            if return_completed:
                if date > self.bhavcopy_last_completed:
                    self.logger.error(f"{Style.BRIGHT}{Fore.RED}No complete bhavcopy found for requested date."
                                      f" Last available for {self.bhavcopy_last_completed.strftime('%Y-%m-%d %H:%M:%S')}.{Style.RESET_ALL}")
                    return []
            url_bhavcopy = f"https://history.truedata.in/getbhavcopy?segment={segment}&date={date.strftime('%Y-%m-%d')}&response=csv"
            payload = { 'comp' : 'true' }
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }
            response = requests.request( "GET", url_bhavcopy, headers=headers, params=payload )
            response = HistoricalREST.decompress_data( response.content )
            bhavcopy_data = response.strip().split('\r\n')
            data_list = []
            # headers = hist_data[0]
            bhavcopy_data = bhavcopy_data[1:]
            for j in bhavcopy_data:
                j = j.split(',')
                data_list.append({'symbol_id': int(j[0]),
                                  'symbol': str(j[1]),
                                  'date': datetime.strptime(str(j[2]), '%Y-%m-%d'),
                                  'o': float(j[3]),
                                  'h': float(j[4]),
                                  'l': float(j[5]),
                                  'c': float(j[6]),
                                  'v': int(j[7]),
                                  'oi': int(j[8])})
            return data_list
        except Exception as e:
            self.logger.error(f"{type(e)} -> {e}")

    @staticmethod
    def hist_json_tick_data_to_dict_list(hist_data, time_format):
        data_list = []
        for j in hist_data:
            try:
                data_list.append({'time': datetime.strptime(j[0], time_format),
                                  'ltp': float(j[1]),
                                  'volume': int(j[2]),
                                  'oi': int(j[3] ) if len(j[3]) >= 1 else 0,
                                  'bid': float(j[4]),
                                  'bid_qty': int(j[5]),
                                  'ask': float(j[6]),
                                  'ask_qty': int(j[7])})
            except IndexError:  # No bid-ask data
                data_list.append({'time': datetime.strptime(j[0], time_format),
                                  'ltp': float(j[1]),
                                  'volume': int(j[2]),
                                  'oi': int(j[3]) if len(j[3]) >= 1 else 0 })
                continue
        return data_list

    @staticmethod
    def hist_json_bar_data_to_dict_list(hist_data, time_format):
        data_list = []
        for j in hist_data:
            data_list.append({'time': datetime.strptime(j[0], time_format),
                              'o': float(j[1]),
                              'h': float(j[2]),
                              'l': float(j[3]),
                              'c': float(j[4]),
                              'v': int(j[5]),
                              'oi': int(j[6]) if len(j[6]) >= 1 else 0 })
        return data_list

    @staticmethod
    def hist_csv_tick_data_to_dict_list(hist_data, time_format):
        hist_data = hist_data.split()
        data_list = []
        # headers = hist_data[0]
        hist_data = hist_data[1:]
        count = 0
        for j in hist_data:
            j = j.split(',')
            try:
                data_list.append({'time': datetime.strptime(j[0], time_format),
                                  'ltp': float(j[1]),
                                  'volume': int(j[2]),
                                  'oi': int(j[3]) if len(j[3]) >= 1 else 0,
                                  'bid': float(j[4]),
                                  'bid_qty': int(j[5]),
                                  'ask': float(j[6]),
                                  'ask_qty': int(j[7])})
            except IndexError:  # No bid-ask data
                data_list.append({'time': datetime.strptime(j[0], time_format),
                                  'ltp': float(j[1]),
                                  'volume': int(j[2]),
                                  'oi': int(j[3]) if len(j[3]) >= 1 else 0 })
                continue
            count = count + 1
        return data_list

    @staticmethod
    def hist_csv_bar_data_to_dict_list(hist_data, time_format , delivery = False):
        hist_data = hist_data.split()
        data_list = []
        # headers = hist_data[0]
        hist_data = hist_data[1:]
        for j in hist_data:
            j = j.split(',')
            # time_format = '%Y-%m-%dT%H:%M:%S'
            data_list.append({'time': datetime.strptime(j[0], time_format),
                              'o': float(j[1]),
                              'h': float(j[2]),
                              'l': float(j[3]),
                              'c': float(j[4]),
                              'v': int(j[5]),
                              'oi': int(j[6]) if len(j[6]) >= 1 else 0 })
            if delivery:
                data_list[-1].update({'dv' :int(j[7]) if not j[7] =="" else 0,
                                     'dp' : float(j[8])if not j[7] =="" else 0} )
        return data_list

    @staticmethod
    def decompress_data(data):
        uncom_length = struct.unpack('<I', data[:4])[0]
        com_length = struct.unpack('<I', data[4:8])[0]
        dc = lz4.block.decompress( data[8:], uncom_length ) if com_length != uncom_length else data[8:]
        return dc.decode()
    

class TooManyRequestsError(Exception):
    def __init__(self, msg):
        self.msg = msg
    def __str__(self ):
        return self.msg


def get_symbol_id(segments , url , user_id , password , cache_dir):
    cache = {}
    params =  { 'user': user_id ,'password' : password,
                'allexpiry':'false', 'csv':'true','csvheader':'true'}
    for segment in segments:
        params.update({'segment': f'{segment}'.lower(),})
        response = requests.get(url, params= params).text
        df = pd.read_csv(StringIO(response) , dtype='unicode' )
        df = df[['symbolid', 'symbol']]
        df.set_index('symbolid' , inplace = True )
        seg = df.to_dict()['symbol']
        cache.update(seg)
    os.makedirs(cache_dir , exist_ok=True )
    with open( f"{cache_dir}/sym_cache_{dt.now().strftime('%d%m%y')}.pkl" , 'wb') as pkl:
        pickle.dump(cache , pkl)


def cache_symbol_id(username , password , td_obj ):
    if os.name == 'nt':
        sym_cache_dir = '/'.join(__file__.split('\\')[:-1]) + '/cache/sym_cache/'
    else: 
        sym_cache_dir = '/'.join(__file__.split('/')[:-1]) + '/cache/sym_cache/'
    url = 'https://api.truedata.in/getAllSymbols?'
    segments = ['EQ', 'FO', 'MCX', 'CDS', 'IN' , 'BSEEQ' , 'BSEFO']
    if not os.path.exists(sym_cache_dir) or not os.path.exists(f'{sym_cache_dir}/sym_cache_{dt.now().strftime("%d%m%y")}.pkl'):
        td_obj.logger.warning(f'{Style.NORMAL}{Fore.BLUE}please wait two minute to download master contracts for today{Style.RESET_ALL}')
        shutil.rmtree(sym_cache_dir, ignore_errors=True, onerror=None)
        get_symbol_id(segments , url , username , password , sym_cache_dir )
    with open( f"{sym_cache_dir}/sym_cache_{dt.now().strftime('%d%m%y')}.pkl" , 'rb') as pkl:
        symbols_map = pickle.load(pkl)
    return symbols_map

def remove_all_cache():
    if os.name == 'nt':
        cache_dir = '/'.join(__file__.split('\\')[:-1]) + '/cache'
    else: 
        cache_dir = '/'.join(__file__.split('/')[:-1]) + '/cache'
    shutil.rmtree(cache_dir, ignore_errors=True, onerror=None)
    