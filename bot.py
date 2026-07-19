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

BAR_TIMEFRAME = '1Day'

# Base de données dynamique du Bot (Multi-symboles)
bot_status = {
    "status": "Initialisation...",
    "market_open": False,
    "last_update": "",
    "stocks": {
        "TSLA": {"qty": 1, "sma_short": 50, "sma_long": 200, "last_price": 0.0, "signal": "HOLD", "trades": []},
        "AAPL": {"qty": 2, "sma_short": 20, "sma_long": 50, "last_price": 0.0, "signal": "HOLD", "trades": []},
        "NVDA": {"qty": 5, "sma_short": 10, "sma_long": 30, "last_price": 0.0, "signal": "HOLD", "trades": []}
    }
}

class APIHandler(BaseHTTPRequestHandler):
    def send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, HEAD, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(bot_status).encode('utf-8'))

    def do_POST(self):
        global bot_status
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            action = data.get("action")
            symbol = data.get("symbol", "").upper()
            
            if not symbol or symbol not in bot_status["stocks"]:
                # Si le symbole n'existe pas encore dans notre dictionnaire, on le crée dynamiquement !
                if symbol:
                    bot_status["stocks"][symbol] = {"qty": 1, "sma_short": 50, "sma_long": 200, "last_price": 0.0, "signal": "HOLD", "trades": []}
                else:
                    raise Exception("Symbole manquant ou invalide")
            
            # Action 1 : Modifier ou Ajouter la configuration d'une action spécifique
            if action == "update_params":
                bot_status["stocks"][symbol]["sma_short"] = int(data.get("sma_short"))
                bot_status["stocks"][symbol]["sma_long"] = int(data.get("sma_long"))
                bot_status["stocks"][symbol]["qty"] = int(data.get("qty"))
                print(f"⚙️ Config mise à jour pour {symbol}: SMA {data.get('sma_short')}/{data.get('sma_long')} | Qté: {data.get('qty')}")
                
            # Action 2 : Forcer manuellement un ordre Achat/Vente sur cette action
            elif action == "force_order":
                side = data.get("side") # 'buy' ou 'sell'
                qty = bot_status["stocks"][symbol]["qty"]
                print(f"🚨 Ordre manuel forcé pour {symbol} : {side} (Qté: {qty})")
                
                api.submit_order(symbol=symbol, qty=qty, side=side, type='market', time_in_force='gtc')
                
                current_time = time.strftime('%Y-%m-%d %H:%M:%S')
                bot_status["stocks"][symbol]["trades"].insert(0, {
                    "date": current_time,
                    "type": f"MANUEL ({side.upper()})",
                    "qty": qty,
                    "price": bot_status["stocks"][symbol]["last_price"]
                })

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode('utf-8'))
            
        except Exception as e:
            self.send_response(400)
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

def analyze_stock(symbol, config):
    """Calcule les indicateurs et passe les ordres automatiques pour un symbole donné"""
    try:
        bars = api.get_bars(symbol, BAR_TIMEFRAME, limit=300).df
        if bars.empty: return

        bars['SMA_S'] = bars['close'].rolling(window=config["sma_short"]).mean()
        bars['SMA_L'] = bars['close'].rolling(window=config["sma_long"]).mean()

        last_close = float(bars['close'].iloc[-1])
        current_sma_s = float(bars['SMA_S'].iloc[-1])
        current_sma_l = float(bars['SMA_L'].iloc[-1])
        prev_sma_s = bars['SMA_S'].iloc[-2]
        prev_sma_l = bars['SMA_L'].iloc[-2]

        config["last_price"] = last_close
        
        # Algorithme de détection du signal
        signal = 'HOLD'
        if prev_sma_s <= prev_sma_l and current_sma_s > current_sma_l:
            signal = 'BUY'
        elif prev_sma_s >= prev_sma_l and current_sma_s < current_sma_l:
            signal = 'SELL'
            
        config["signal"] = signal
        current_time = time.strftime('%Y-%m-%d %H:%M:%S')

        # Exécution automatique
        if signal == 'BUY':
            api.submit_order(symbol=symbol, qty=config["qty"], side='buy', type='market', time_in_force='gtc')
            config["trades"].insert(0, {"date": current_time, "type": "ACHAT (AUTO)", "qty": config["qty"], "price": last_close})
        elif signal == 'SELL':
            # Tente de liquider la position actuelle
            try:
                pos = api.get_position(symbol)
                qty_to_sell = int(pos.qty)
            except:
                qty_to_sell = config["qty"]
            api.submit_order(symbol=symbol, qty=qty_to_sell, side='sell', type='market', time_in_force='gtc')
            config["trades"].insert(0, {"date": current_time, "type": "VENTE (AUTO)", "qty": qty_to_sell, "price": last_close})

    except Exception as e:
        print(f"❌ Erreur sur le symbole {symbol} : {e}")

def trade_loop():
    global bot_status
    while True:
        try:
            clock = api.get_clock()
            bot_status["market_open"] = clock.is_open
            bot_status["last_update"] = time.strftime('%Y-%m-%d %H:%M:%S')

            if clock.is_open:
                bot_status["status"] = "🚀 Analyse multi-actifs en cours..."
                # Parcourt et analyse toutes les actions configurées une par une
                for symbol, config in list(bot_status["stocks"].items()):
                    analyze_stock(symbol, config)
                time.sleep(3600)
            else:
                bot_status["status"] = "💤 Marché américain fermé."
                # Récupère au moins les derniers prix de clôture pour l'affichage hors session
                for symbol, config in list(bot_status["stocks"].items()):
                    try:
                        bars = api.get_bars(symbol, BAR_TIMEFRAME, limit=1).df
                        if not bars.empty: config["last_price"] = float(bars['close'].iloc[-1])
                    except: pass
                time.sleep(900)
        except Exception as e:
            print(f"Erreur boucle générale : {e}")
            time.sleep(60)

if __name__ == "__main__":
    print("--- 🤖 Le Bot Multi-Actifs Alpaca est actif ---")
    server_thread = threading.Thread(target=lambda: HTTPServer(('0.0.0.0', int(os.getenv('PORT', 10000))), APIHandler).serve_forever(), daemon=True)
    server_thread.start()
    trade_loop()