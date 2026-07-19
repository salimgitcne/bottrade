import alpaca_trade_api as tradeapi
import pandas as pd
import time
import os

# --- CONFIGURATION DE L'API ALPACA ---
# Pour le Paper Trading (Mode démo gratuit), utilisez l'URL de test d'Alpaca.
# Sur Render, vous ajouterez ces clés dans "Environment Variables".
API_KEY = os.getenv('ALPACA_API_KEY', 'VOTRE_API_KEY_DE_TEST')
SECRET_KEY = os.getenv('ALPACA_SECRET_KEY', 'VOTRE_SECRET_KEY_DE_TEST')
BASE_URL = 'https://paper-api.alpaca.markets'  # URL pour de l'argent virtuel

# Connexion à l'API Alpaca
api = tradeapi.REST(API_KEY, SECRET_KEY, BASE_URL, api_version='v2')

# Paramètres du bot
SYMBOL = 'AAPL'       # Action à trader (Ex: Apple)
QTY = 5               # Nombre d'actions à acheter/vendre par trade
BAR_TIMEFRAME = '1Day' # Analyse sur des bougies journalières (plus fiable)

def get_signals():
    """Calcule les moyennes mobiles et génère un signal d'achat ou de vente."""
    print(f"Analyse des données pour {SYMBOL}...")
    
    # Récupérer les 250 derniers jours de bourse
    bars = api.get_bars(SYMBOL, BAR_TIMEFRAME, limit=250).df
    
    if bars.empty:
        print("Erreur : Impossible de récupérer les données du marché.")
        return None

    # Calcul des indicateurs de tendance (Moyennes Mobiles Simples)
    bars['SMA50'] = bars['close'].rolling(window=50).mean()
    bars['SMA200'] = bars['close'].rolling(window=200).mean()

    # Récupération des dernières valeurs calculées
    last_close = bars['close'].iloc[-1]
    current_sma50 = bars['SMA50'].iloc[-1]
    current_sma200 = bars['SMA200'].iloc[-1]
    
    # Valeurs de la veille pour détecter le croisement exact
    prev_sma50 = bars['SMA50'].iloc[-2]
    prev_sma200 = bars['SMA200'].iloc[-2]

    print(f"Prix actuel : ${last_close:.2f} | SMA50 : ${current_sma50:.2f} | SMA200 : ${current_sma200:.2f}")

    # --- STRATÉGIE DU CROISEMENT D'OR (GOLDEN CROSS) ---
    # Signal d'Achat : La SMA50 passe au-dessus de la SMA200 (Tendance haussière confirmée)
    if prev_sma50 <= prev_sma200 and current_sma50 > current_sma200:
        return 'BUY'
    
    # Signal de Vente : La SMA50 passe en-dessous de la SMA200 (Tendance baissière)
    elif prev_sma50 >= prev_sma200 and current_sma50 < current_sma200:
        return 'SELL'
    
    return 'HOLD' # Rien à faire

def trade_logic():
    """Exécute les ordres d'achat ou de vente selon le signal."""
    try:
        signal = get_signals()
        
        # Vérifier si on possède déjà l'action
        try:
            position = api.get_position(SYMBOL)
            has_position = True
            current_qty = int(position.qty)
        except:
            has_position = False
            current_qty = 0

        if signal == 'BUY' and not has_position:
            print(f"🚀 SIGNAL D'ACHAT ! Passage d'un ordre de {QTY} actions de {SYMBOL}.")
            api.submit_order(
                symbol=SYMBOL,
                qty=QTY,
                side='buy',
                type='market',
                time_in_force='gtc'
            )
        elif signal == 'SELL' and has_position:
            print(f"📉 SIGNAL DE VENTE ! Fermeture de la position sur {SYMBOL}.")
            api.submit_order(
                symbol=SYMBOL,
                qty=current_qty,
                side='sell',
                type='market',
                time_in_force='gtc'
            )
        else:
            print("Pas de changement de tendance. Statut : En attente.")

    except Exception as e:
        print(f"Une erreur est survenue : {e}")

# Boucle principale du Bot
if __name__ == "__main__":
    print("--- Le Bot Alpaca Stock est actif (Mode Simulation) ---")
    while True:
        # Vérifier si la bourse américaine (NYSE/NASDAQ) est ouverte
        clock = api.get_clock()
        if clock.is_open:
            trade_logic()
            # On attend 1 heure avant la prochaine vérification (le trading d'actions quotidien est lent)
            time.sleep(3600) 
        else:
            print("Le marché est actuellement fermé. Prochaine vérification dans 15 minutes...")
            time.sleep(900)