import alpaca_trade_api as tradeapi
import pandas as pd
import time
import os
import threading
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

# --- CONFIGURATION DE L'API ALPACA ---
API_KEY = os.getenv('ALPACA_API_KEY')
SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')
BASE_URL = 'https://paper-api.alpaca.markets'

api = tradeapi.REST(API_KEY, SECRET_KEY, BASE_URL, api_version='v2')

# Paramètres du bot
SYMBOL = 'TSLA'        
QTY = 1                
BAR_TIMEFRAME = '1Day' 

# Variable globale pour stocker les dernières données du Bot (lues par l'API)
bot_status = {
    "status": "Initialisation...",
    "symbol": SYMBOL,
    "last_price": 0.0,
    "sma50": 0.0,
    "sma200": 0.0,
    "signal": "HOLD",
    "market_open": False,
    "last_update": ""
}

class APIHandler(BaseHTTPRequestHandler):
    """Gère les requêtes web et renvoie l'état du bot en JSON"""
    def do_GET(self):
        # Autoriser votre site web externe à lire les données (CORS)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*') # Permet l'affichage sur service-it.dz
        self.end_headers()
        
        # Envoyer les données au format JSON
        self.wfile.write(json.dumps(bot_status).encode('utf-8'))

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()

def run_api_server():
    port = int(os.getenv('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), APIHandler)
    print(f"🌍 API du Bot active sur le port {port}")
    server.serve_forever()

def get_signals():
    print(f" Analyse des données de marché pour {SYMBOL}...")
    try:
        bars = api.get_bars(SYMBOL, BAR_TIMEFRAME, limit=250).df
        if bars.empty:
            return 'HOLD'

        bars['SMA50'] = bars['close'].rolling(window=50).mean()
        bars['SMA200'] = bars['close'].rolling(window=200).mean()

        last_close = float(bars['close'].iloc[-1])
        current_sma50 = float(bars['SMA50'].iloc[-1])
        current_sma200 = float(bars['SMA200'].iloc[-1])
        prev_sma50 = bars['SMA50'].iloc[-2]
        prev_sma200 = bars['SMA200'].iloc[-2]

        # Mettre à jour les données partagées
        bot_status["last_price"] = last_close
        bot_status["sma50"] = current_sma50
        bot_status["sma200"] = current_sma200
        bot_status["last_update"] = time.strftime('%Y-%m-%d %H:%M:%S')

        if prev_sma50 <= prev_sma200 and current_sma50 > current_sma200:
            return 'BUY'
        elif prev_sma50 >= prev_sma200 and current_sma50 < current_sma200:
            return 'SELL'
            
    except Exception as e:
        print(f"❌ Erreur signaux : {e}")
    return 'HOLD'

def trade_logic():
    global bot_status
    try:
        signal = get_signals()
        bot_status["signal"] = signal
        bot_status["status"] = "Analyse en cours..."
        
        try:
            position = api.get_position(SYMBOL)
            has_position = True
            current_qty = int(position.qty)
        except:
            has_position = False
            current_qty = 0

        if signal == 'BUY' and not has_position:
            api.submit_order(symbol=SYMBOL, qty=QTY, side='buy', type='market', time_in_force='gtc')
            bot_status["status"] = f"🚀 Ordre d'ACHAT passé pour {QTY} action(s)"
        elif signal == 'SELL' and has_position:
            api.submit_order(symbol=SYMBOL, qty=current_qty, side='sell', type='market', time_in_force='gtc')
            bot_status["status"] = f"📉 Ordre de VENTE passé pour {current_qty} action(s)"
        else:
            bot_status["status"] = "⚖️ En attente d'un croisement de tendance."

    except Exception as e:
        print(f"❌ Erreur trade_logic : {e}")

if __name__ == "__main__":
    print("--- 🤖 Le Bot Alpaca Stock est en ligne ---")
    
    # Lancer l'API en arrière-plan
    server_thread = threading.Thread(target=run_api_server, daemon=True)
    server_thread.start()
    
    while True:
        try:
            clock = api.get_clock()
            bot_status["market_open"] = clock.is_open
            if clock.is_open:
                trade_logic()
                time.sleep(3600) 
            else:
                bot_status["status"] = "💤 Le marché américain est fermé."
                time.sleep(900)
        except Exception as e:
            time.sleep(60)