from io import StringIO
from copy import deepcopy
from datetime import datetime as dt
from datetime import time as t

import pandas as pd
import requests
import re
import numpy as np
import time



class OptionChain:

    chain_url ='https://api.truedata.in/getOptionChain?'
    close_time = t(15, 40)

    def __init__(self,
                 TD_OBJ ,
                 symbol ,
                 expiry ,
                 chain_length ,
                 future_price,
                 bid_ask ,
                 market_open_post_hours ):
        self.TD_OBJ = TD_OBJ
        self.login_id = TD_OBJ.login_id
        self.password = TD_OBJ.password
        self.symbol = symbol
        self.expiry = expiry
        self.chain_length = chain_length
        self.future_price = future_price
        self.strike_step = self.get_strike_step()
        self.option_symbols = self.get_option_symbols()
        self.chain_dataframe =  self.init_dataframe()
        self.chain_status = False
        self.bid_ask = bid_ask
        self.market_open_post_hours = market_open_post_hours

    def get_strike_step(self ):
        expiry = self.expiry.strftime('%Y%m%d')
        chain_link = f'{OptionChain.chain_url}user={self.login_id}&password={self.password}&symbol={self.symbol}&expiry={expiry}&csv=true'
        chain = requests.get(chain_link).text
        df = pd.read_csv(StringIO(chain) , header = None)
        df[1] = df[1].apply(lambda x : re.findall('\D+' , x)[0])
        df = df[df[1] == self.symbol]
        strikes = np.sort(df[6].unique())
        step = strikes[1]-strikes[0];
        for i in range(2 , len(strikes)):
            step = min(step, strikes[i]-strikes[i-1]);
        return step

    def get_option_symbols(self ):
        expiry = self.expiry.strftime('%y%m%d')
        future_atm = round(self.future_price / self.strike_step ) * self.strike_step
        start_strike = future_atm - self.strike_step * int(self.chain_length / 2 )
        end_strike = future_atm + self.strike_step * int( self.chain_length / 2)
        req_strikes = np.arange( start_strike , end_strike  , self.strike_step )
        if isinstance( self.strike_step , float ) :
            req_strikes = list(map(lambda x: int(x) if x.is_integer() else x , req_strikes))
        symbols = list(map(lambda x: f'{self.symbol}{expiry}{x}CE', req_strikes))
        symbols.extend(list(map(lambda x: f'{self.symbol}{expiry}{x}PE', req_strikes )))
        return symbols

    def init_dataframe(self):
        df = pd.DataFrame(columns=['symbols' , 'strike' , 'type' , 'ltp' , 'ltt' , 'ltq' , 'volume' , 'price_change' , 'price_change_perc', 'oi' , 
                                    'prev_oi' , 'oi_change' , 'oi_change_perc' , 'bid' , 'bid_qty' , 'ask' , 'ask_qty'])
        df.symbols = self.option_symbols
        df.strike = df.symbols.apply(lambda x: str(re.search(r"\d+(\.\d+)?", x ).group(0) )[6:])
        df.type = df.symbols.apply(lambda x: re.findall('\D+' , x )[-1] )
        df.set_index('symbols' , inplace=True)
        df.sort_values(by=['strike' , 'type'] , inplace=True)
        return df

    def initial_update_from_touchline(self , td_obj , symb_ids):
        prev_tick_obj = {}
        time.sleep(1)
        for symb_id in symb_ids:
            prev_tick_obj[symb_id] = deepcopy(td_obj.live_data[symb_id])
            try:
                oi_change_perc = round((td_obj.touchline_data[symb_id].oi - td_obj.touchline_data[symb_id].prev_oi)*100 / (td_obj.touchline_data[symb_id].prev_oi) , 2 )
                price_change_perc = round((td_obj.touchline_data[symb_id].ltp - td_obj.touchline_data[symb_id].prev_close)*100 / (td_obj.touchline_data[symb_id].prev_oi) , 4 )
            except (ZeroDivisionError , TypeError):
                oi_change_perc = 0
                price_change_perc = 0
            try:
                self.chain_dataframe.loc[td_obj.touchline_data[symb_id].symbol , ['ltp' , 'ltt'  , 'ltq' , 'volume' ,'price_change' , 'price_change_perc' , 'oi' , 
                                                        'prev_oi', 'oi_change' , 'oi_change_perc','bid' , 'bid_qty' , 'ask' , 'ask_qty' ]] = [
                    td_obj.touchline_data[symb_id].ltp, td_obj.touchline_data[symb_id].timestamp , td_obj.touchline_data[symb_id].ltq , 
                    td_obj.touchline_data[symb_id].ttq ,td_obj.touchline_data[symb_id].ltp - td_obj.touchline_data[symb_id].prev_close , 
                    price_change_perc , td_obj.touchline_data[symb_id].oi, td_obj.touchline_data[symb_id].prev_oi , 
                    td_obj.touchline_data[symb_id].oi - td_obj.touchline_data[symb_id].prev_oi ,oi_change_perc , 
                    td_obj.touchline_data[symb_id].best_bid_price, td_obj.touchline_data[symb_id].best_bid_qty,
                    td_obj.touchline_data[symb_id].best_ask_price, td_obj.touchline_data[symb_id].best_ask_qty 
                ]
            except TypeError:
                self.chain_dataframe.loc[td_obj.touchline_data[symb_id].symbol , ['ltp' , 'ltt' ,'ltq' , 'volume' , 'price_change' , 'price_change_perc',  'oi' , 'prev_oi', 'oi_change' ,
                                                            'oi_change_perc','bid' , 'bid_qty' , 'ask' , 'ask_qty' ]] =[ np.NaN for i in range(14)]
        return prev_tick_obj

    def update_chain(self ,td_obj , symb_ids ):
        self.chain_status = True
        prev_tick_obj = self.initial_update_from_touchline(td_obj, symb_ids)
        while self.chain_status:
            for symb_id in symb_ids:
                if not td_obj.live_data[symb_id] == prev_tick_obj[symb_id]:
                    try:
                        bid, bid_qnty = td_obj.live_data[symb_id].best_bid_price , td_obj.live_data[symb_id].best_bid_qty
                        ask , ask_qnty = td_obj.live_data[symb_id].best_ask_price, td_obj.live_data[symb_id].best_ask_qty
                    except Exception as e:
                        bid, bid_qnty, ask, ask_qnty = 0, 0, 0, 0
                    self.chain_dataframe.loc[td_obj.live_data[symb_id].symbol , ['ltt' , 'volume' , 'price_change','price_change_perc', 'oi' ,'prev_oi' , 'oi_change' ,
                                                                                'oi_change_perc' ,'bid' , 'bid_qty' , 'ask' , 'ask_qty' ]] = [
                        td_obj.live_data[symb_id].timestamp , td_obj.live_data[symb_id].ttq ,td_obj.live_data[symb_id].change, 
                        round(td_obj.live_data[symb_id].change_perc , 2) ,td_obj.live_data[symb_id].oi, td_obj.live_data[symb_id].prev_day_oi ,
                        td_obj.live_data[symb_id].oi_change ,round(td_obj.live_data[symb_id].to_dict()['oi_change_perc'] ,2 ) ,bid, bid_qnty, ask, ask_qnty 
                    ]
                    if 'ltp' in td_obj.live_data[symb_id].__dict__.keys():
                        self.chain_dataframe.loc[td_obj.live_data[symb_id].symbol , ['ltp'] ] = td_obj.live_data[symb_id].ltp    
                        self.chain_dataframe.loc[td_obj.live_data[symb_id].symbol , ['ltq'] ] = td_obj.live_data[symb_id].ltq if td_obj.live_data[symb_id].ltq is not None else 0
                    else:
                        self.chain_dataframe.loc[td_obj.live_data[symb_id].symbol , ['ltp'] ] = td_obj.live_data[symb_id].close
                        self.chain_dataframe.loc[td_obj.live_data[symb_id].symbol , ['ltq'] ] = td_obj.live_data[symb_id].volume if td_obj.live_data[symb_id].volume is not None else 0
                    prev_tick_obj[symb_id] = deepcopy(td_obj.live_data[symb_id])
            time.sleep(0.005)
            if not(self.market_open_post_hours) and dt.now().time() > OptionChain.close_time :
                break
        # print('exited chain thread')

    def get_option_chain(self):
        df = self.chain_dataframe.copy()
        df.dropna(inplace=True)
        df = df.astype({'ltq' : int , 'volume': int })
        if not self.bid_ask:
            df = df.drop(['bid' , 'bid_qty' , 'ask' , 'ask_qty'] , axis= 1  )
        return df

    def stop_option_chain(self):
        self.chain_status = False
        self.TD_OBJ.stop_live_data(self.option_symbols)

