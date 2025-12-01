from dataclasses import dataclass
from websocket import WebSocketApp
from threading import Thread
from datetime import datetime
from dateutil.relativedelta import relativedelta            # type: ignore
import time
import json
from copy import deepcopy
from collections import defaultdict
from .support import full_feed , bidask_feed , bar_feed , greek_feed , tick_feed

from colorama import Style, Fore                            # type: ignore

import traceback




class LiveClient(WebSocketApp):

    def __init__(self, parent_app, url, *args):
        WebSocketApp.__init__(self, url, on_open=self.ws_open, on_error=self.ws_error, on_message=self.on_msg_func, on_close=self.ws_close, *args)
        self.segments = []
        self.max_symbols = 0
        self.remaining_symbols = 0
        self.valid_until = ''
        self.contract_mapping = {}
        self.subscription_type = ''
        self.confirm_heartbeats = 1
        self.store_last_n_heartbeats = self.confirm_heartbeats + 7
        self.heartbeat_interval = 5
        self.heartbeat_buffer = 0.5
        time_of_creation = datetime.now()
        self.last_n_heartbeat = [time_of_creation - relativedelta(seconds=i * self.heartbeat_interval) for i in range(-self.store_last_n_heartbeats, 0)]
        self.parent_app = parent_app
        self.logger = self.parent_app.logger
        self.disconnect_flag = False
        self.heartbeat_check_thread = Thread(target=self.check_heartbeat, daemon=True)
        self.trade_callback = None
        self.full_feed_trade_callback = None
        self.full_feed_bar_callback = None
        self.bidask_callback = None
        self.one_min_bar_callback = None
        self.five_min_bar_callback = None
        self.greek_callback = None
        self.subs = ''
        # if self.parent_app.live_port == 8086 or self.parent_app.live_port == 8084:
        #     # self.heartbeat_check_thread.start()
        #     pass

    def check_connection(self):
        base_heartbeat = self.last_n_heartbeat[-self.confirm_heartbeats]
        check_time = datetime.now()
        time_diff = check_time - base_heartbeat
        is_connected = time_diff.total_seconds() > ((self.heartbeat_interval + self.heartbeat_buffer) * self.confirm_heartbeats)  # 3 > 5 + 0.5
        return is_connected

    def check_heartbeat(self):
        while True:
            time.sleep(self.heartbeat_interval)
            if self.disconnect_flag:
                self.logger.info(f"{Fore.WHITE}Removing hand from the pulse...{Style.RESET_ALL}")
                break
            if self.check_connection():
                self.logger.debug(f"{Style.BRIGHT}{Fore.RED}Failed Heartbeat @ {datetime.now()} because of last at {self.last_n_heartbeat[-self.confirm_heartbeats]}{Style.RESET_ALL}")
                self.logger.info(f"{Style.BRIGHT}{Fore.RED}Attempting reconnect @ {Fore.CYAN}{datetime.now()}{Style.RESET_ALL}")
                restart_successful = self.reconnect()
                if restart_successful:
                    self.logger.info(f"{Style.BRIGHT}{Fore.GREEN}Successful restart @ {Fore.CYAN}{datetime.now()}{Style.RESET_ALL}")
                    time.sleep((self.heartbeat_interval + self.heartbeat_buffer))
                    recover_start, recover_end = self.get_largest_diff(self.last_n_heartbeat)
                    # self.logger.debug(f"\t\t\t{len(self.last_n_heartbeat)} - {self.last_n_heartbeat}")
                    self.recover_from_time_missed(recover_start, recover_end)
                else:
                    self.logger.info(f"{Style.BRIGHT}{Fore.RED}Failed restart @ {Fore.CYAN}{datetime.now()}{Style.RESET_ALL}")

    @staticmethod
    def get_largest_diff(time_series):
        big_li = deepcopy(time_series.pop(0))
        small_li = deepcopy(time_series.pop())
        diffs = [i[0]-i[1] for i in zip(big_li, small_li)]
        start_gap_index = max(range(len(diffs)), key=lambda i: diffs[i])
        return time_series[start_gap_index], time_series[start_gap_index+1]

    def recover_from_time_missed(self, start_time, end_time):
        self.logger.info(f"{Style.BRIGHT}{Fore.YELLOW}Initiating recovery from {Fore.GREEN}{start_time}{Fore.YELLOW} till {Fore.GREEN}{end_time}{Fore.YELLOW} "
                         f"which are last green heartbeats from server...{Style.RESET_ALL}")

    def reconnect(self):
        self.close()
        time.sleep(2)
        t = Thread(target=self.run_forever, daemon=True)
        t.start()
        is_td_connected = False
        while not is_td_connected:
            time.sleep(self.heartbeat_interval + self.heartbeat_buffer)
            is_td_connected = self.check_connection()
        return is_td_connected

    def on_msg_func(self, *args):
        try:
            message = args[-1]
            msg = json.loads(message)
            msg_keys = msg.keys()
            # print(msg) 
            if 'message' in msg_keys:
                self.handle_message_data(msg)
            if self.parent_app.full_feed:
                if 'trade' in msg_keys :
                    feed_tick = full_feed( raw_tick=msg['trade'] ,symbol=self.parent_app.symbol_id_map_dict[msg['trade'][0]] )
                    self.full_feed_trade_callback( feed_tick ) if self.full_feed_trade_callback else None   
                if ('bidask' in msg_keys or 'bidaskL2' in msg_keys )  :
                    if 'bidask' in msg_keys:
                        bid_ask = bidask_feed( raw_tick=msg['bidask'] , symbol=self.parent_app.symbol_id_map_dict[msg['bidask'][0]] , level= "L1" )
                    else:
                        bid_ask = bidask_feed( raw_tick=msg['bidaskL2'] , symbol=self.parent_app.symbol_id_map_dict[msg['bidaskL2'][0]] , level= "L2" )
                    self.bidask_callback( bid_ask ) if self.bidask_callback else None  
                if 'interval' in msg_keys  :
                    bar_data = map(lambda x : bar_feed(x , self.parent_app.symbol_id_map_dict[ str( x[1]) ]), msg["data"]) 
                    for bar in list(bar_data):
                        self.full_feed_bar_callback ( bar ) if self.full_feed_bar_callback else None
                if 'greeks' in msg_keys:
                    greeks = greek_feed( raw_tick=msg['greeks'] , symbol= self.parent_app.symbol_id_map_dict[msg['greeks'][0]] )
                    self.greek_callback(greeks) if self.greek_callback else None
            else:
                if 'trade' in msg_keys:
                    trade_tick = self.handle_trade_data( msg['trade'] )
                elif 'bidask' in msg_keys:
                    bid_ask = bidask_feed( raw_tick=msg['bidask'] , symbol=self.contract_mapping[int(msg['bidask'][0])] , level = "L1" )
                    self.bidask_callback( bid_ask ) if self.bidask_callback else None
                elif 'bidaskL2' in msg_keys :
                    bid_ask = bidask_feed( raw_tick=msg['bidaskL2'] , symbol=self.contract_mapping[int(msg['bidaskL2'][0])] , level = "L2" )
                    self.bidask_callback( bid_ask ) if self.bidask_callback else None
                elif 'bar1min' in msg_keys:
                    self.handle_bar_data( msg['bar1min'] , bar_type= '1min' )
                elif 'bar5min' in msg_keys:
                    self.handle_bar_data( msg['bar5min'] , bar_type= '5min')
                elif 'greeks' in msg_keys:
                    greeks = greek_feed( raw_tick=msg['greeks'] , symbol=self.contract_mapping[int(msg['greeks'][0])] )
                    self.greek_callback(greeks) if self.greek_callback else None
        except KeyError as e:
            self.logger.warning(f"{Style.BRIGHT}{Fore.RED}Symbol id - {e.args[0]} is not availavble in the masters and cannot be mapped.{Style.RESET_ALL}")
        except Exception :
            traceback.print_exc()
            exit()

    def handle_message_data(self, msg):
        if msg['success']:
            if msg['message'] == 'HeartBeat':
                self.handle_heartbeat(msg['timestamp'])
            elif msg['message'] == 'TrueData Real Time Data Service':  # Connection success message
                # self.logger.info(f"{Style.BRIGHT}{Fore.WHITE}You have subscribed for {msg['maxsymbols']} "
                #                  f"symbols across {msg['segments']} until {msg['validity']} with type of stream "
                #                  f"as {msg['subscription']}...{Style.RESET_ALL}")
                self.logger.warning(f"{Style.NORMAL}{Fore.BLUE}Connected successfully to {msg['message']}... {Style.RESET_ALL}")
                self.subscription_type = msg['subscription']
                self.subs = self.subscription_type.split('+')
                # print(self.subscription_type)
            elif msg['message'] in ['symbols added', 'touchline']:
                self.add_contract_details(msg['symbollist'])
            elif msg['message'] == 'symbols removed':
                self.remove_symbols(msg['symbollist'])
            elif msg['message'] == 'marketstatus':
                self.logger.debug(f"Market status message -> {msg['data']}") 
        else:
            self.logger.error(f"{Style.BRIGHT}{Fore.RED}The request encountered an error - {msg['message']}{Style.RESET_ALL}")

    def handle_heartbeat(self, server_timestamp):
        self.logger.debug(f'Server heartbeat received at {server_timestamp}')
        timestamp = datetime.strptime(server_timestamp, "%Y-%m-%dT%H:%M:%S.%f")  # old format + ((26 - len(server_timestamp)) * "0")
        self.last_n_heartbeat = self.last_n_heartbeat[1:]
        self.last_n_heartbeat.append(timestamp)

    def remove_symbols(self, contracts):
        for contract_info in contracts:
            contract = contract_info.split(':')[0]
            for req_id in self.parent_app.symbol_mkt_id_map[contract.upper()]:
                del self.parent_app.live_data[req_id]
                del self.parent_app.touchline_data[req_id]
                if '+' in self.subscription_type:
                    del self.parent_app.one_min_live_data[req_id]
            del self.parent_app.symbol_mkt_id_map[contract.upper()]

    def add_contract_details(self, contracts_list):
        for contract_details in contracts_list:
            if contract_details is not None:
                self.contract_mapping[int(contract_details[1])] = symbol = contract_details[0]
                for ticker_id in self.parent_app.symbol_mkt_id_map[symbol]:
                    self.parent_app.touchline_data[ticker_id].symbol = symbol
                    self.parent_app.touchline_data[ticker_id].symbol_id = int(contract_details[1])
                    self.parent_app.touchline_data[ticker_id].timestamp = datetime.strptime(contract_details[2], '%Y-%m-%dT%H:%M:%S')
                    self.parent_app.touchline_data[ticker_id].ltp = float(contract_details[3])
                    self.parent_app.touchline_data[ticker_id].ltq = float(contract_details[4])
                    self.parent_app.touchline_data[ticker_id].atp = float(contract_details[5])
                    self.parent_app.touchline_data[ticker_id].ttq = int(contract_details[6])
                    self.parent_app.touchline_data[ticker_id].open = float(contract_details[7])
                    self.parent_app.touchline_data[ticker_id].high = float(contract_details[8])
                    self.parent_app.touchline_data[ticker_id].low = float(contract_details[9])
                    self.parent_app.touchline_data[ticker_id].prev_close = float(contract_details[10])
                    self.parent_app.touchline_data[ticker_id].oi = int(contract_details[11])
                    self.parent_app.touchline_data[ticker_id].prev_oi = int(contract_details[12])
                    self.parent_app.touchline_data[ticker_id].turnover = float(contract_details[13])
                    self.parent_app.touchline_data[ticker_id].best_bid_price = float(contract_details[14])
                    self.parent_app.touchline_data[ticker_id].best_bid_qty = float(contract_details[15])
                    self.parent_app.touchline_data[ticker_id].best_ask_price = float(contract_details[16])
                    self.parent_app.touchline_data[ticker_id].best_ask_qty = float(contract_details[17])
                    if 'tick' in self.subs:
                        self.parent_app.live_data[ticker_id].populate_using_touchline(self.parent_app.live_data[ticker_id], self.parent_app.touchline_data[ticker_id])
                    if '1min' in self.subs:
                        self.parent_app.one_min_live_data[ticker_id].populate_using_touchline(self.parent_app.one_min_live_data[ticker_id], self.parent_app.touchline_data[ticker_id])
                    if '5min' in self.subs:
                        self.parent_app.five_min_live_data[ticker_id].populate_using_touchline(self.parent_app.five_min_live_data[ticker_id], self.parent_app.touchline_data[ticker_id])
                self.logger.info(f"Updated touchline data for {symbol} and related live data objects...")
            else:
                self.logger.debug(f'{Style.BRIGHT}{Fore.YELLOW}Probable repeated symbol...{Style.RESET_ALL}')

    def handle_trade_data(self, trade_tick):
        try:
            symbol = self.contract_mapping[int(trade_tick[0])]
            for ticker_id in self.parent_app.symbol_mkt_id_map[symbol]:
                self.parent_app.live_data[ticker_id].symbol_id = int(trade_tick[0])
                self.parent_app.live_data[ticker_id].timestamp = datetime.strptime(trade_tick[1], '%Y-%m-%dT%H:%M:%S')
                self.parent_app.live_data[ticker_id].symbol = symbol
                self.parent_app.live_data[ticker_id].ltp = self.parent_app.touchline_data[ticker_id].ltp = ltp = float(trade_tick[2])
                self.parent_app.live_data[ticker_id].ltq = float(trade_tick[3])
                self.parent_app.live_data[ticker_id].atp = float(trade_tick[4])
                self.parent_app.live_data[ticker_id].ttq = float(trade_tick[5])
                self.parent_app.live_data[ticker_id].day_open = self.parent_app.touchline_data[ticker_id].open = float(trade_tick[6])
                self.parent_app.live_data[ticker_id].day_high = float(trade_tick[7])
                self.parent_app.live_data[ticker_id].day_low = float(trade_tick[8])
                self.parent_app.live_data[ticker_id].prev_day_close = float(trade_tick[9])
                self.parent_app.live_data[ticker_id].oi = int(trade_tick[10])
                self.parent_app.live_data[ticker_id].prev_day_oi = int(trade_tick[11])
                self.parent_app.live_data[ticker_id].turnover = float(trade_tick[12])
                self.parent_app.live_data[ticker_id].special_tag = special_tag = str(trade_tick[13])
                if special_tag != "":
                    if special_tag == 'H':
                        self.parent_app.touchline_data[ticker_id].high = ltp
                    elif special_tag == 'L':
                        self.parent_app.touchline_data[ticker_id].low = ltp
                self.parent_app.live_data[ticker_id].tick_seq = int(trade_tick[14])
                self.parent_app.live_data[ticker_id].tick_type = 1
                try:
                    self.parent_app.live_data[ticker_id].best_bid_price = float(trade_tick[15])
                    self.parent_app.live_data[ticker_id].best_bid_qty = int(trade_tick[16])
                    self.parent_app.live_data[ticker_id].best_ask_price = float(trade_tick[17])
                    self.parent_app.live_data[ticker_id].best_ask_qty = int(trade_tick[18])
                except (IndexError, ValueError, TypeError):
                    try:
                        del self.parent_app.live_data[ticker_id].best_bid_price
                        del self.parent_app.live_data[ticker_id].best_bid_qty
                        del self.parent_app.live_data[ticker_id].best_ask_price
                        del self.parent_app.live_data[ticker_id].best_ask_qty
                    except AttributeError:
                        pass
                except Exception as e:
                    self.logger.error(e)
                if self.trade_callback:
                    try:
                        tick = tick_feed( raw_tick= self.parent_app.live_data[ticker_id].to_dict())
                        self.trade_callback( tick )
                    except Exception as e:
                        self.logger.error(f'{Style.BRIGHT}{Fore.RED}Encountered error with trade_callback - {type(e)} - {e}{Style.RESET_ALL}')
        except KeyError:
            pass
        except Exception as e:
            self.logger.error(f'{Style.BRIGHT}{Fore.RED}Encountered error with tick feed - {type(e)}{Style.RESET_ALL}')

    def handle_bar_data(self, bar_data , bar_type ):
        try:
            symbol = self.contract_mapping[int(bar_data[0])]
            ticker_ids =  list(self.parent_app.symbol_mkt_id_map[symbol])
            if (len(ticker_ids) > 1 ):           #checking multiple id then deepcopying with same touchline data
                for t_id in ticker_ids[1:]:
                    if bar_type == '1min':
                        self.parent_app.one_min_live_data[t_id] = deepcopy(self.parent_app.one_min_live_data[ticker_ids[0]])
                    else:
                        self.parent_app.five_min_live_data[t_id] = deepcopy(self.parent_app.five_min_live_data[ticker_ids[0]])
            for ticker_id in self.parent_app.symbol_mkt_id_map[symbol]:
                if bar_type == '1min':
                    obj_to_edit = self.parent_app.one_min_live_data[ticker_id]
                    obj_to_edit.bar_type = '1min'
                elif bar_type == '5min':
                    obj_to_edit = self.parent_app.five_min_live_data[ticker_id]
                    obj_to_edit.bar_type = '5min' 
                obj_to_edit.symbol_id = int(bar_data[0])
                obj_to_edit.timestamp = datetime.strptime(bar_data[1], '%Y-%m-%dT%H:%M:%S')
                obj_to_edit.symbol = symbol
                obj_to_edit.open = float(bar_data[2])
                obj_to_edit.high = bar_high = float(bar_data[3])
                if bar_high > obj_to_edit.day_high:
                    obj_to_edit.day_high = self.parent_app.touchline_data[ticker_id].high = bar_high
                obj_to_edit.low = bar_low = float(bar_data[4])
                if bar_low < obj_to_edit.day_low:
                    obj_to_edit.day_low = self.parent_app.touchline_data[ticker_id].low = bar_low
                obj_to_edit.close = self.parent_app.touchline_data[ticker_id].ltp = float(bar_data[5])
                obj_to_edit.volume = float(bar_data[6])
                obj_to_edit.oi = float(bar_data[7])
                # moving data to live_data dict if not subcribed to ticks inorder to work chain
                if len(self.subs) == 1 :
                    self.parent_app.live_data[ticker_id] = deepcopy(obj_to_edit)
                elif len(self.subs) == 2 and 'tick' not in self.subs and bar_type == '1min':
                    self.parent_app.live_data[ticker_id] = deepcopy(obj_to_edit)
                
                if self.one_min_bar_callback and bar_type == '1min' :
                    self.execute_callbacks( ticker_id , obj_to_edit , '1min')  
                elif self.five_min_bar_callback and bar_type == '5min' :
                    self.execute_callbacks( ticker_id , obj_to_edit , '5min' ) 
        except KeyError as e:
            # print('error' , e)
            pass
        except Exception as e:
            self.logger.error(f'{Style.BRIGHT}{Fore.RED}Bar feed encountered - {e}{Style.RESET_ALL}')

    def execute_callbacks(self , ticker_id , obj_to_edit , bar_type ):
        try:
            self.one_min_bar_callback(ticker_id, obj_to_edit) if bar_type == '1min' else self.five_min_bar_callback(ticker_id, obj_to_edit)
        except Exception as e:
            self.logger.error(f'{Style.BRIGHT}{Fore.RED}Encountered error with bar_callback - {type(e)} - {e}{Style.RESET_ALL}')

    def ws_error(self, *args):
        error = args[-1]
        if any(isinstance(error, conn_error) for conn_error in [ConnectionResetError, TimeoutError]):
            self.logger.error(f"Raising WS error = {error}")
            self.last_ping_tm = self.last_pong_tm = 0

    # noinspection PyUnusedLocal
    def ws_open(self, *args):
        self.last_ping_tm = time.time()
        self.sock.ping()
        self.sock.settimeout(15)
        if self.parent_app.symbol_mkt_id_map:
            self.logger.info("connection dropped due to timeout. trying reconnecting.....")
            old_symbol_map = temp_symbol_map = deepcopy(self.parent_app.symbol_mkt_id_map)  # temp_symbol_map is destructed while restarting the data
            temp_symbol_map = dict(temp_symbol_map)
            req_id = temp_symbol_map.values()
            req_id  = list(map(lambda x : next(iter(x)) , req_id))
            self.logger.debug(f'{list(temp_symbol_map.keys())} needs resuming here.')
            restart_symbols = list(temp_symbol_map.keys())
            self.sock.ping()
            time.sleep(3)
            self.parent_app.start_live_data(restart_symbols, req_id=req_id , restart_flag = True )
            temp_symbol_map = {symbol: symbol_set for (symbol, symbol_set) in temp_symbol_map.items() if symbol_set}
            assert old_symbol_map == self.parent_app.symbol_mkt_id_map
            self.logger.info(f'All streaming symbols have been resumed.')
            

    # noinspection PyUnusedLocal
    def ws_close(self, *args):
        # self.logger.error('Live WebSocket Closed')
        self.sock.close() if self.sock is not None else 0
        self.sock = None
        if self.last_ping_tm == 0 == self.last_pong_tm:
            self.logger.debug('DISCONNECTION TYPE(1) FROM SERVER...')
            try:
                time.sleep(1)
                self.run_forever(ping_interval=10, ping_timeout=5)
            except Exception as e:
                self.logger.error(f'{type(e)} in reconnection => {e}')
        if self.last_ping_tm > self.last_pong_tm:
            self.logger.debug('DISCONNECTION TYPE(2) FROM SERVER...')
            try:
                time.sleep(1)
                self.run_forever(ping_interval=10, ping_timeout=5)
            except Exception as e:
                self.logger.error(f'{type(e)} in reconnection2 => {e}')
        # self.logger.error(f'CLOSE: {self.last_ping_tm} -> {self.last_pong_tm}')


