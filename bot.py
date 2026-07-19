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

# Paramètres globaux modifiables à distance
SYMBOL = 'TSLA'        
QTY = 1                
BAR_TIMEFRAME = '1Day' 
SMA_SHORT = 50        # Paramètre modifiable
SMA_LONG = 200        # Paramètre modifiable

bot_status = {
    "status": "Initialisation...",
    "symbol": SYMBOL,
    "qty": QTY,
    "sma_short_param": SMA_SHORT,
    "sma_long_param": SMA_LONG,
    "last_price": 0.0,
    "sma50": 0.0,
    "sma200": 0.0,
    "signal": "HOLD",
    "market_open": False,
    "last_update": "",
    "trades": []
}

class APIHandler(BaseHTTPRequestHandler):
    """Gère l'affichage des données (GET) et la configuration (POST)"""
    
    def end_headers(self):
        # Configuration CORS complète pour autoriser l'envoi de données depuis service-it.dz
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        """Requis pour valider les requêtes de formulaires cross-domain"""
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(bot_status).encode('utf-8'))

    def do_POST(self):
        global SMA_SHORT, SMA_LONG, QTY, SYMBOL
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            action = data.get("action")
            
            # Action 1 : Modifier les paramètres des indicateurs
            if action == "update_params":
                SMA_SHORT = int(data.get("sma_short", SMA_SHORT))
                SMA_LONG = int(data.get("sma_long", SMA_LONG))
                QTY = int(data.get("qty", QTY))
                
                bot_status["sma_short_param"] = SMA_SHORT
                bot_status["sma_long_param"] = SMA_LONG
                bot_status["qty"] = QTY
                print(f"⚙️ Paramètres mis à jour : SMA {SMA_SHORT} / SMA {SMA_LONG} | Qté : {QTY}")
                
            # Action 2 : Forcer manuellement un ordre Achat/Vente depuis l'interface
            elif action == "force_order":
                side = data.get("side") # 'buy' ou 'sell'
                print(f"🚨 Ordre manuel forcé depuis le site web : {side}")
                api.submit_order(symbol=SYMBOL, qty=QTY, side=side, type='market', time_in_force='gtc')
                
                current_time = time.strftime('%Y-%m-%d %H:%M:%S')
                bot_status["trades"].insert(0, {
                    "date": current_time,
                    "type": f"MANUEL ({side.upper()})",
                    "qty": QTY,
                    "price": bot_status["last_price"]
                })

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode('utf-8'))
            
        except Exception as e:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

def run_api_server():
    port = int(os.getenv('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), APIHandler)
    print(f"🌍 API interactive active sur le port {port}")
    server.serve_forever()

def get_signals():
    global SMA_SHORT, SMA_LONG
    try:
        # On demande 300 bars pour couvrir les larges fenêtres d'indicateurs
        bars = api.get_bars(SYMBOL, BAR_TIMEFRAME, limit=300).df
        if bars.empty: return 'HOLD'

        # Calcul basé sur vos variables dynamiques obtenues depuis le HTML
        bars['SMA_S'] = bars['close'].rolling(window=SMA_SHORT).mean()
        bars['SMA_L'] = bars['close'].rolling(window=SMA_LONG).mean()

        last_close = float(bars['close'].iloc[-1])
        current_sma50 = float(bars['SMA_S'].iloc[-1])
        current_sma200 = float(bars['SMA_L'].iloc[-1])
        prev_sma50 = bars['SMA_S'].iloc[-2]
        prev_sma200 = bars['SMA_L'].iloc[-2]

        bot_status["last_price"] = last_close
        bot_status["sma50"] = current_sma50
        bot_status["sma200"] = current_sma200
        bot_status["last_update"] = time.strftime('%Y-%m-%d %H:%M:%S')

        if prev_sma50 <= prev_sma200 and current_sma50 > current_sma200: return 'BUY'
        elif prev_sma50 >= prev_sma200 and current_sma50 < current_sma200: return 'SELL'
            
    except Exception as e:
        print(f"❌ Erreur signaux : {e}")
    return 'HOLD'

def trade_logic():
    global bot_status
    try:
        signal = get_signals()
        bot_status["signal"] = signal
        
        try:
            position = api.get_position(SYMBOL)
            has_position = True
            current_qty = int(position.qty)
        except:
            has_position = False
            current_qty = 0

        current_time = time.strftime('%Y-%m-%d %H:%M:%S')

        if signal == 'BUY' and not has_position:
            api.submit_order(symbol=SYMBOL, qty=QTY, side='buy', type='market', time_in_force='gtc')
            bot_status["status"] = "🚀 Ordre d'ACHAT auto passé"
            bot_status["trades"].insert(0, {"date": current_time, "type": "ACHAT (AUTO)", "qty": QTY, "price": bot_status["last_price"]})
        elif signal == 'SELL' and has_position:
            api.submit_order(symbol=SYMBOL, qty=current_qty, side='sell', type='market', time_in_force='gtc')
            bot_status["status"] = "📉 Ordre de VENTE auto passé"
            bot_status["trades"].insert(0, {"date": current_time, "type": "VENTE (AUTO)", "qty": current_qty, "price": bot_status["last_price"]})
        else:
            bot_status["status"] = "⚖️ En attente d'un croisement de tendance."
    except Exception as e:
        print(f"❌ Erreur trade_logic : {e}")

if __name__ == "__main__":
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