from .support import TickLiveData, MinLiveData, TouchlineData
from .support import TDLiveDataError, TDHistoricDataError
from .TD_live import LiveClient
from .TD_hist import HistoricalREST , cache_symbol_id , remove_all_cache
from .TD_chain import OptionChain
from threading import Thread
from typing import Union, Callable, Any
from collections import defaultdict

from datetime import datetime
from dateutil.relativedelta import relativedelta                                # type: ignore
from typing import List, Dict
from colorama import Style, Fore                                                # type: ignore
import time
import json
import logging

# import traceback

class TD:
    def __init__(self,
                 login_id,
                 password,
                 broker_token=None,
                 url='push.truedata.in',  # This arg is used for LIVE URL only
                 live_port=8082,
                 historical_api=True,
                 # tz='Asia/Kolkata',
                 log_level=logging.WARNING,
                 log_handler=None,
                 log_format=None,
                 hist_url='https://history.truedata.in',
                 full_feed = False ,
                 dry_run = False):
        self.live_websocket = None
        self.historical_datasource = None
        self.login_id = login_id
        self.password = password
        self.live_url = url
        self.hist_url = hist_url
        self.live_port = live_port
        self.connect_historical = historical_api
        self.full_feed = full_feed
        self.dry_run = dry_run
        if log_format is None:
            # log_format = "%(levelname)s : %(message)s"
            log_format = "(%(asctime)s) %(levelname)s :: %(message)s (PID:%(process)d Thread:%(thread)d)"
        if log_handler is None:
            log_formatter = logging.Formatter(log_format)
            # log_formatter = logging.Formatter("%(message)s")
            self.log_handler = logging.StreamHandler()
            self.log_handler.setLevel(log_level)
            self.log_handler.setFormatter(log_formatter)
        else:
            self.log_handler = log_handler
        self.logger = logging.getLogger(__name__)
        self.logger.addHandler(self.log_handler)
        self.logger.setLevel(self.log_handler.level)
        self.logger.debug("Logger ready...")
        if live_port is None:
            self.connect_live = False
        else:
            self.connect_live = True
        self.broker_token = broker_token
        self.hist_data = {}
        self.live_data = {}
        self.one_min_live_data = {}
        self.five_min_live_data = {}
        self.symbol_mkt_id_map = defaultdict(set)
        # self.streaming_symbols = {}
        self.touchline_data = {}
        self.default_market_data_id = 2000
        self.symbol_id_map_dict = dict()
        self.connect()

    def connect(self):
        broker_append = ''
        if self.dry_run:
            remove_all_cache()
        self.symbol_id_map_dict = cache_symbol_id(self.login_id , self.password  , self ) if self.full_feed else 0
        if self.broker_token is not None:
            broker_append = f'&brokertoken={self.broker_token}'
        if self.connect_live:
            self.live_websocket = LiveClient(self, f"wss://{self.live_url}:{self.live_port}?user={self.login_id}&password={self.password}{broker_append}")
            t = Thread(target=self.connect_thread, args=(), daemon=True)
            t.start()
        if self.connect_historical:
            self.historical_datasource = HistoricalREST(self.login_id, self.password, self.hist_url, self.broker_token, self.logger)
        while self.connect_live and self.live_websocket.subscription_type == '':
            time.sleep(1)

    def connect_thread(self):
        self.live_websocket.run_forever(ping_interval=10, ping_timeout=5)
        while not self.live_websocket.disconnect_flag:
            self.logger.info(f"{Style.BRIGHT}{Fore.RED}Connection dropped due to no network , Attempting reconnect @ {Fore.CYAN}{datetime.now()}{Style.RESET_ALL}")
            self.live_websocket.reconnect()
            time.sleep(10)
        self.logger.debug('Goodbye (properly) !!')

    def disconnect(self):
        if self.connect_live:
            self.live_websocket.disconnect_flag = True
            self.live_websocket.close()
            # self.logger.info(f"{Fore.GREEN}Disconnected LIVE TrueData...{Style.RESET_ALL}")
            self.logger.warning(f"{Style.NORMAL}{Fore.BLUE}Disconnected from Real Time Data WebSocket Connection !{Style.RESET_ALL}")
        if self.connect_historical:
            # self.logger.info(f"{Fore.GREEN}Disconnected HISTORICAL TrueData...{Style.RESET_ALL}")
            self.logger.warning(f"{Style.NORMAL}{Fore.BLUE}Disconnected from Historical Data REST Connection !{Style.RESET_ALL}")

    @staticmethod
    def truedata_duration_map(regular_format, end_date):
        duration_units = regular_format.split()[1].upper()
        if len(duration_units) > 1:
            raise TDHistoricDataError("Misconfigured duration argument")
        duration_size = int(regular_format.split()[0])
        if duration_units == 'D':
            return (end_date - relativedelta(days=duration_size - 1)).date()
        elif duration_units == 'W':
            return (end_date - relativedelta(weeks=duration_size)).date()
        elif duration_units == 'M':
            return (end_date - relativedelta(months=duration_size)).date()
        elif duration_units == 'Y':
            return (end_date - relativedelta(years=duration_size)).date()

    def get_historic_data(self, contract,
                          ticker_id=None,
                          end_time=None,
                          duration=None,
                          start_time=None,
                          bar_size="1 min",
                          options=None,
                          bidask=False,
                          delivery=False):
        if delivery and not bar_size.lower() == "eod":
            delivery = False
        if start_time is not None and duration is None:
            return self.get_historical_data_from_start_time(contract=contract,
                                                            ticker_id=ticker_id,
                                                            end_time=end_time,
                                                            start_time=start_time,
                                                            bar_size=bar_size,
                                                            options=options,
                                                            bidask=bidask,
                                                            delivery = delivery)
        else:
            return self.get_historical_data_from_duration(contract=contract,
                                                          ticker_id=ticker_id,
                                                          end_time=end_time,
                                                          duration=duration,
                                                          bar_size=bar_size,
                                                          options=options,
                                                          bidask=bidask,
                                                          delivery = delivery)

    def get_n_historical_bars(self, contract,
                              ticker_id=None,
                              end_time: datetime = None,
                              no_of_bars: int = 1,
                              bar_size="1 min",
                              options=None,
                              bidask=False):
        if end_time is None:
            end_time = datetime.today()
        end_time = end_time.strftime('%y%m%dT%H:%M:%S')    # This is the request format
        hist_data = self.historical_datasource.get_n_historic_bars(contract,
                                                                   end_time,
                                                                   no_of_bars,
                                                                   bar_size,
                                                                   options=options,
                                                                   bidask=bidask)
        if ticker_id is not None:
            self.hist_data[ticker_id] = hist_data
        return hist_data

    def get_historical_data_from_duration(  self, contract,
                                            delivery,
                                            ticker_id=None,
                                            end_time: datetime = None,
                                            duration=None,
                                            bar_size="1 min",
                                            options=None,
                                            bidask=False,
                                           ):
        if duration is None:
            duration = "1 D"
        if end_time is None:
            end_time = datetime.today()
        start_time = self.truedata_duration_map(duration, end_time)
        end_time = end_time.strftime('%y%m%d') + 'T23:59:59'    # This is the request format
        start_time = start_time.strftime('%y%m%d') + 'T00:00:00'    # This is the request format
        hist_data = self.historical_datasource.get_historic_data(contract, end_time, start_time, bar_size, 
                                                                    options=options, bidask=bidask ,delivery = delivery )
        if ticker_id is not None:
            self.hist_data[ticker_id] = hist_data
        return hist_data

    def get_historical_data_from_start_time(self, contract,
                                            delivery,
                                            ticker_id=None,
                                            end_time: datetime = None,
                                            start_time: datetime = None,
                                            bar_size="1 min",
                                            options=None,
                                            bidask=False):
        if end_time is None:
            end_time = datetime.today().replace(hour=23, minute=59, second=59)
        if start_time is None:
            start_time = datetime.today().replace(hour=0, minute=0, second=0)

        end_time = end_time.strftime('%y%m%dT%H:%M:%S')    # This is the request format
        start_time = start_time.strftime('%y%m%dT%H:%M:%S')    # This is the request format
        hist_data = self.historical_datasource.get_historic_data(contract, end_time, start_time, bar_size, 
                                                                options=options, bidask=bidask , delivery = delivery)
        if ticker_id is not None:
            self.hist_data[ticker_id] = hist_data
        return hist_data

    def get_bhavcopy(self, segment: str, date: datetime = None, return_completed: bool = True) -> List[Dict]:
        if date is None:
            date = datetime.now().replace(hour=0, minute=0, second=0)
        # return_completed = True  # Uncomment and remove arg to disallow user choice
        return self.historical_datasource.bhavcopy(segment, date, return_completed)

    def get_gainers(self , segment , topn , df_style = True ):
        topn = 10 if topn is None else topn
        return self.historical_datasource.get_gainers_losers(segment, topn , gainers = True , df_style = df_style )

    def get_losers(self , segment , topn , df_style = True ):
        topn = 10 if topn is None else topn
        return self.historical_datasource.get_gainers_losers(segment , topn , gainers = False , df_style = df_style )


    @staticmethod
    def get_req_id_list(req_id: Union[int, list], len_contracts: int) -> list:
        if type(req_id) == list:
            if len(req_id) == len_contracts:
                return req_id
            else:
                raise TDLiveDataError("Lengths do not match...")
        elif type(req_id) == int:
            curr_req_id = req_id
            return [curr_req_id + i for i in range(0, len_contracts)]
        else:
            raise TDLiveDataError("Invalid req_id datatype...")

    
    def map_subscriptions(self , resolved_contract , req_id):
        subs = self.live_websocket.subscription_type.split('+')
        if resolved_contract in self.symbol_mkt_id_map.keys():
            self.live_data[req_id] = self.live_data[list(self.symbol_mkt_id_map[resolved_contract])[0]]
        if 'tick' in subs :
            if req_id not in self.live_data.keys() :
                self.live_data[req_id] = TickLiveData(resolved_contract)
        if '1min' in subs:
            if req_id not in self.one_min_live_data.keys() :
                self.one_min_live_data[req_id] = MinLiveData(resolved_contract)
        if '5min' in subs:
            if req_id not in self.five_min_live_data.keys() :
                self.five_min_live_data[req_id] = MinLiveData(resolved_contract)
        if 'tick' not in subs:
            self.live_data[req_id] = MinLiveData(resolved_contract)


    def start_live_data(self, resolved_contracts, req_id=None , restart_flag = False):  # TODO: Prevent reuse of req_ids
        if restart_flag:
            self.live_websocket.send(f'{{"method": "addsymbol", "symbols": {json.dumps(resolved_contracts)}}}')
            return req_id
        symbols_to_call = []
        resolved_contracts = list(set(resolved_contracts))
        if req_id is not None:
            req_ids = self.get_req_id_list(req_id, len(resolved_contracts))
        else:
            req_ids = self.get_req_id_list(self.default_market_data_id, len(resolved_contracts))
            self.default_market_data_id = self.default_market_data_id + len(resolved_contracts)
        for i , req_id in enumerate(req_ids):
            resolved_contract = resolved_contracts[i].upper()
            if resolved_contract in self.symbol_mkt_id_map.keys():
                self.touchline_data[req_id] = self.touchline_data[list(self.symbol_mkt_id_map[resolved_contract])[0]]
            else:
                self.touchline_data[req_id] = TouchlineData()
            self.map_subscriptions(resolved_contract , req_id)
            if resolved_contract not in self.symbol_mkt_id_map.keys():
                symbols_to_call.append(resolved_contract)
            self.symbol_mkt_id_map[resolved_contract].update({req_id})
        if len(symbols_to_call) > 0:
            self.live_websocket.send(f'{{"method": "addsymbol", "symbols": {json.dumps(symbols_to_call)}}}')
        return req_ids

    def stop_live_data(self, contracts):  # Clearing objects is done after server confirmation
        remove_symbols = []
        for sym in contracts:
            if len(self.symbol_mkt_id_map[sym]) > 1:
                self.symbol_mkt_id_map[sym].remove(list(self.symbol_mkt_id_map[sym])[-1])
            else:
                remove_symbols.append(sym)
                self.symbol_mkt_id_map.pop(sym , None)
        self.live_websocket.send(f'{{"method": "removesymbol", "symbols": {json.dumps(remove_symbols)}}}')

    def trade_callback(self, func: Callable[[TickLiveData], Any]):
        self.logger.info(f"Defining {func} as trade_callback...")
        self.live_websocket.trade_callback = func

    def clear_trade_callback(self):
        self.logger.info(f"Clearing trade_callback...")
        self.live_websocket.trade_callback = None

    def bidask_callback(self, func: Callable[[TickLiveData], Any]):
        self.logger.info(f"Defining bidask_callback...")
        self.live_websocket.bidask_callback = func

    def clear_bidask_callback(self):
        self.logger.info(f"Clearing bidask_callback...")
        self.live_websocket.bidask_callback = None

    def one_min_bar_callback(self, func: Callable):
        self.logger.info(f"Defining one min bar_callback...")
        self.live_websocket.one_min_bar_callback = func

    def clear_one_min_bar_callback(self):
        self.logger.info(f"Clearing one min bar_callback...")
        self.live_websocket.one_min_bar_callback = None

    def five_min_bar_callback(self, func: Callable) :
        self.logger.info(f"Defining five min bar_callback...")
        self.live_websocket.five_min_bar_callback = func

    def clear_five_min_bar_callback(self):
        self.logger.info(f"Clearing five min bar_callback...")
        self.live_websocket.five_min_bar_callback = None

    def full_feed_trade_callback(self , func: Callable ):
        self.logger.info(f"Defining full feed tick_callback...")
        self.live_websocket.full_feed_trade_callback = func

    def clear_full_feed_trade_callback(self):
        self.logger.info(f"Clearing full feed trade_callback...")
        self.live_websocket.full_feed_trade_callback = None
    
    def full_feed_bar_callback(self , func: Callable ):
        self.logger.info(f"Defining full feed bar_callback...")
        self.live_websocket.full_feed_bar_callback = func

    def clear_full_feed_bar_callback(self):
        self.logger.info(f"Clearing full feed bar_callback...")
        self.live_websocket.full_feed_bar_callback = None

    def greek_callback(self , func: Callable ):
        self.logger.info(f"Defining greek feed callback...")
        self.live_websocket.greek_callback = func

    def clear_greek_callback(self):
        self.logger.info(f"Clearing greek feed callback...")
        self.live_websocket.greek_callback = None

    # def get_touchline(self):
    #     self.live_websocket.send(f'{{"method": "touchline"}}')

    def start_option_chain( self , symbol , expiry , chain_length = None , bid_ask = False , market_open_post_hours = False , bse_option = False ):
        chain_length = 10 if chain_length is None else chain_length  # setting default value for chain length
        if not bse_option :
            future_price = self.get_n_historical_bars(f'{symbol}-I' )[0]['c']
        else :
            future_price = self.get_n_historical_bars(f'{symbol}' )[0]['c']
        try:
            chain = OptionChain(self , symbol, expiry , chain_length , future_price , bid_ask  , market_open_post_hours )
        except Exception as e:
            # traceback.print_exc()
            print(f'Please check symbol: {symbol} and its expiry: {expiry.date()}')
            exit()
        symb_ids = self.start_live_data(chain.option_symbols)
        option_thread = Thread(target=chain.update_chain, args=( self , symb_ids ), daemon=True)
        option_thread.start()
        return chain
