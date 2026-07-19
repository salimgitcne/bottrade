import alpaca_trade_api as tradeapi
import pandas as pd
import time
import os
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer

# --- CONFIGURATION DE L'API ALPACA ---
# Le code récupère vos clés enregistrées dans l'onglet "Environment" de Render.
API_KEY = os.getenv('ALPACA_API_KEY')
SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')
BASE_URL = 'https://paper-api.alpaca.markets'  # URL pour de l'argent virtuel (Paper Trading)

# Connexion à l'API Alpaca
api = tradeapi.REST(API_KEY, SECRET_KEY, BASE_URL, api_version='v2')

# Paramètres du bot (Modifiables selon vos préférences)
SYMBOL = 'TSLA'        # Action à trader (Ex: Apple)
QTY = 1                # Nombre d'actions à acheter/vendre par trade
BAR_TIMEFRAME = '1Day' # Analyse sur des bougies journalières (plus robuste)

def run_fake_server():
    """Lance un mini serveur web pour empêcher Render de couper le bot."""
    port = int(os.getenv('PORT', 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    print(f"🌍 Serveur web factice actif sur le port {port} pour maintenir Render en ligne.")
    server.serve_forever()

def get_signals():
    """Calcule les moyennes mobiles et génère un signal d'achat ou de vente."""
    print(f" Analyse des données de marché pour {SYMBOL}...")
    
    try:
        # Récupérer les 250 derniers jours de bourse pour calculer les moyennes mobiles longues
        bars = api.get_bars(SYMBOL, BAR_TIMEFRAME, limit=250).df
        
        if bars.empty:
            print("❌ Erreur : Impossible de récupérer les données du marché.")
            return 'HOLD'

        # Calcul des Moyennes Mobiles Simples (SMA 50 et 200)
        bars['SMA50'] = bars['close'].rolling(window=50).mean()
        bars['SMA200'] = bars['close'].rolling(window=200).mean()

        # Récupération des dernières valeurs
        last_close = bars['close'].iloc[-1]
        current_sma50 = bars['SMA50'].iloc[-1]
        current_sma200 = bars['SMA200'].iloc[-1]
        
        # Valeurs de la veille pour valider le croisement exact
        prev_sma50 = bars['SMA50'].iloc[-2]
        prev_sma200 = bars['SMA200'].iloc[-2]

        print(f"📊 [Info] Prix : ${last_close:.2f} | SMA50 : ${current_sma50:.2f} | SMA200 : ${current_sma200:.2f}")

        # --- STRATÉGIE DU GOLDEN CROSS / DEATH CROSS ---
        # Signal d'Achat : La SMA50 croise à la hausse la SMA200
        if prev_sma50 <= prev_sma200 and current_sma50 > current_sma200:
            return 'BUY'
        
        # Signal de Vente : La SMA50 croise à la baisse la SMA200
        elif prev_sma50 >= prev_sma200 and current_sma50 < current_sma200:
            return 'SELL'
            
    except Exception as e:
        print(f"❌ Erreur lors du calcul des signaux : {e}")
    
    return 'HOLD'

def trade_logic():
    """Exécute les ordres d'achat ou de vente selon le signal détecté."""
    try:
        signal = get_signals()
        
        # Vérifier si on possède déjà l'action dans notre portefeuille virtuel
        try:
            position = api.get_position(SYMBOL)
            has_position = True
            current_qty = int(position.qty)
        except:
            has_position = False
            current_qty = 0

        # Application du signal
        if signal == 'BUY' and not has_position:
            print(f"🚀 SIGNAL D'ACHAT DÉTECTÉ ! Achat de {QTY} actions {SYMBOL}.")
            api.submit_order(
                symbol=SYMBOL,
                qty=QTY,
                side='buy',
                type='market',
                time_in_force='gtc'
            )
        elif signal == 'SELL' and has_position:
            print(f"📉 SIGNAL DE VENTE DÉTECTÉ ! Clôture de la position sur {SYMBOL}.")
            api.submit_order(
                symbol=SYMBOL,
                qty=current_qty,
                side='sell',
                type='market',
                time_in_force='gtc'
            )
        else:
            print("⚖️ Statut : Aucun changement de tendance majeur. En attente.")

    except Exception as e:
        print(f"❌ Une erreur est survenue lors du passage d'ordre : {e}")

# Boucle principale du Bot
if __name__ == "__main__":
    print("--- 🤖 Le Bot Alpaca Stock est en ligne (Mode Simulation) ---")
    
    # 1. Lancer le mini serveur web en arrière-plan pour satisfaire les scans de Render
    server_thread = threading.Thread(target=run_fake_server, daemon=True)
    server_thread.start()
    
    # 2. Lancer la routine de trading
    while True:
        try:
            clock = api.get_clock()
            if clock.is_open:
                trade_logic()
                # Le trading d'action quotidien demande une analyse lente (ici toutes les heures)
                time.sleep(3600) 
            else:
                print("💤 Le marché américain est fermé. Prochaine vérification dans 15 minutes...")
                time.sleep(900)
        except Exception as e:
            print(f"⚠️ Erreur de connexion au serveur Alpaca : {e}. Nouvelle tentative dans 60 secondes...")
            time.sleep(60)