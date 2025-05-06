
from binance.client import Client
from binance import ThreadedWebsocketManager
from binance.enums import *
import time
from collections import deque
import numpy as np
import talib
import math
from binance.exceptions import BinanceAPIException

API_KEY = 'Your API key'
API_SECRET = 'Your secret key'

client = Client(API_KEY, API_SECRET)


SYMBOL = 'x'
INTERVAL = Client.KLINE_INTERVAL_5MINUTE 
LOOKBACK = 10000 
POLL_INTERVAL = 60  
MAX_REQUEST_LIMIT = 1000  


candles = []

def get_precision_for_symbol(client: Client=client, symbol: str = SYMBOL) -> int:
    info = client.futures_exchange_info()
    for s in info['symbols']:
        if s['symbol'] == symbol:
            step_size = float([f for f in s['filters'] if f['filterType'] == 'LOT_SIZE'][0]['stepSize'])
            return abs(int(round(-math.log10(step_size))))
    raise ValueError(f"Symbol TSLA not found.")

def buy(client: Client = client, symbol: str = SYMBOL, safety_margin: float = 0.99):
    try:       
        precision = get_precision_for_symbol(client, symbol)    
        balance_info = client.futures_account_balance()
        usdt_balance = next(b for b in balance_info if b['asset'] == 'USDT')
        available_balance = float(usdt_balance['availableBalance']) * safety_margin 
        price = float(client.futures_symbol_ticker(symbol=symbol)['price']) 
        quantity = round(available_balance / price, precision)  
        order = client.futures_create_order(
            symbol=symbol,
            side=SIDE_BUY,
            type=ORDER_TYPE_MARKET,
            quantity=quantity
        )

        print(f" Market buy order placed: {quantity} {symbol}")
        return order

    except Exception as e:
        print(f"Error placing market buy: {e}")
        return None

def sell(client: Client = client, symbol: str = SYMBOL, safety_margin: float = 0.99):
    try:
        precision = get_precision_for_symbol(client, symbol)

        positions = client.futures_position_information(symbol=symbol)
        position = next((p for p in positions if p['symbol'] == symbol), None)

        if not position:
            print(f" No position found for {symbol}")
            return None

        position_amt = float(position['positionAmt'])

        if position_amt == 0:
            print(f"No open position to sell for {symbol}")
            return None

        if position_amt > 0:
            quantity = round(abs(position_amt) * safety_margin, precision)

        
            order = client.futures_create_order(
                symbol=symbol,
                side=SIDE_SELL,
                type=ORDER_TYPE_MARKET,
                quantity=quantity
            )

            print(f" Market sell order placed: {quantity} {symbol}")
            return order
        else:
            print(f" Position is already short (negative), nothing to sell.")
            return None

    except Exception as e:
        print(f" Error placing market sell: {e}")
        return None

def get_historical_klines(symbol, interval, limit):
    all_candles = []
    remaining = limit
    end_time = None  

    while remaining > 0:
        try:
            fetch_size = min(remaining, MAX_REQUEST_LIMIT)

            new_candles = client.futures_klines(
                symbol=symbol,
                interval=interval,
                limit=fetch_size,
                endTime=end_time
            )

            if not new_candles:
                break

            all_candles = new_candles + all_candles
            remaining -= len(new_candles)

          
            first_candle_time = new_candles[0][0]
            end_time = first_candle_time - 1

            time.sleep(0.2)

        except BinanceAPIException as e:
            print(f"API Error: {e}")
            time.sleep(5)
            continue
        except Exception as e:
            print(f"Unexpected error: {e}")
            time.sleep(10)
            continue

    return all_candles[-limit:]

def is_valid_candle(c):
 
    return all([
        c['open'] > 0,
        c['close'] > 0,
        c['high'] >= c['low'],
        c['high'] >= max(c['open'], c['close']),
        c['low'] <= min(c['open'], c['close'])
    ])

def fetch_and_process():
    
    global candles
    
    try:
        
        new_candles = client.futures_klines(
            symbol=SYMBOL,
            interval=INTERVAL,
            limit=5  
        )
        
        
        valid_updates = []
        for c in new_candles:
            formatted = {
                'open_time': c[0],
                'open': float(c[1]),
                'high': float(c[2]),
                'low': float(c[3]),
                'close': float(c[4]),
                'volume': float(c[5]),
                'close_time': c[6]
            }
            if is_valid_candle(formatted):
                valid_updates.append(formatted)
        
       
        for new_candle in valid_updates:
            
            existing_index = next(
                (i for i, c in enumerate(candles) if c['open_time'] == new_candle['open_time']),
                None
            )
            
            if existing_index is not None:
                
                candles[existing_index] = new_candle
            else:
                
                candles.append(new_candle)
        
        
        candles = candles[-LOOKBACK:]
        
      
        array_close = np.array([c['close'] for c in candles])
        array_open = np.array([c["open"] for c in candles])
        array_low = np.array([c["low"] for c in candles])
        array_volume = np.array([c["volume"] for c in candles])
        array_high = np.array([c["high"] for c in candles])

  
        if len(array_close) >= LOOKBACK:
            """logic here"""
        
     
    
    except Exception as e:
        print(f"Error in fetch_and_process: {e}")

def main():
    global candles
    
    print(f"Starting polling strategy for TSLA {INTERVAL}...")
    
 
    print("Loading historical data...")
    try:
        kline_data = get_historical_klines(SYMBOL, INTERVAL, LOOKBACK)
        candles = [{
            'open_time': c[0],
            'open': float(c[1]),
            'high': float(c[2]),
            'low': float(c[3]),
            'close': float(c[4]),
            'volume': float(c[5]),
            'close_time': c[6]
        } for c in kline_data if is_valid_candle({ 
            'open': float(c[1]),
            'close': float(c[4]),
            'high': float(c[2]),
            'low': float(c[3])
        })]
        
        print(f"Successfully loaded {len(candles)} valid candles")
        
      
        while True:
            fetch_and_process()
            time.sleep(POLL_INTERVAL)
            
    except KeyboardInterrupt:
        print("Stopping strategy...")
    except Exception as e:
        print(f"Fatal error: {e}")

if __name__ == "__main__":
    main()
