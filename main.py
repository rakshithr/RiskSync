import MetaTrader5 as mt5
import json
import time
import logging
import os
from datetime import datetime

# --- CONFIGURACIÓN INICIAL ---
CONFIG_FILE = 'config.json'
STATE_FILE = 'state.json'
LOG_DIR = 'logs'
LOG_FILE = os.path.join(LOG_DIR, 'RiskSync.log')

# Crear directorio de logs si no existe
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Configurar el sistema de logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler() # Para ver logs en la consola en tiempo real
    ]
)

# --- FUNCIONES AUXILIARES ---

def load_json(file_path):
    """Carga un archivo JSON de forma segura."""
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logging.error(f"Error al leer {file_path}: {e}")
        return {}

def save_json(data, file_path):
    """Guarda datos en un archivo JSON de forma segura."""
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)
    except IOError as e:
        logging.error(f"Error al escribir en {file_path}: {e}")

def initialize_mt5(account_config):
    """Inicializa la conexión con una terminal MT5 específica."""
    path = account_config.get('mt5_path')
    if not mt5.initialize(path=path,
                        login=account_config['login'],
                        password=account_config['password'],
                        server=account_config['server']):
        logging.error(f"Fallo al inicializar MT5 para login {account_config['login']} en la ruta {path}: {mt5.last_error()}")
        return False
    logging.info(f"Conectado a la cuenta {account_config['login']} en {account_config['server']}")
    return True

def calculate_lot_size(master_pos, risk_usd, mt5_conn):
    """Calcula el tamaño del lote basado en el riesgo en USD."""
    symbol_info = mt5_conn.symbol_info(master_pos.symbol)
    if not symbol_info:
        logging.warning(f"No se pudo obtener información del símbolo {master_pos.symbol}")
        return None

    # Validar que la operación tiene SL
    if master_pos.sl == 0.0:
        return None

    # Cálculo de la distancia del SL en puntos
    sl_points = abs(master_pos.price_open - master_pos.sl)

    # Obtener el valor del tick y el tamaño del tick
    tick_value = symbol_info.trade_tick_value
    tick_size = symbol_info.trade_tick_size

    if tick_size == 0: # Evitar división por cero
        logging.error(f"El tamaño del tick para {master_pos.symbol} es cero.")
        return None

    # Valor monetario de un punto
    value_per_point = tick_value / tick_size

    # Riesgo total para un lote estándar
    risk_per_lot = sl_points * value_per_point

    if risk_per_lot == 0: # Evitar división por cero
        logging.warning(f"El riesgo calculado por lote es cero para {master_pos.symbol}. No se puede calcular el lotaje.")
        return None

    # Cálculo del lotaje
    lot_size = risk_usd / risk_per_lot

    # Redondear y ajustar al volumen mínimo y al paso de volumen
    min_volume = symbol_info.volume_min
    volume_step = symbol_info.volume_step
    
    lot_size = max(min_volume, round(lot_size / volume_step) * volume_step)
    
    return round(lot_size, 2)


def place_order(slave_login, master_pos, lot_size, comment):
    """Coloca una orden en una cuenta slave."""
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": master_pos.symbol,
        "volume": lot_size,
        "type": master_pos.type,
        "price": mt5.symbol_info_tick(master_pos.symbol).ask if master_pos.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(master_pos.symbol).bid,
        "sl": master_pos.sl,
        "tp": master_pos.tp,
        "comment": comment,
        "magic": master_pos.magic,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC, # O mt5.ORDER_FILLING_FOK
    }
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logging.error(f"[Slave {slave_login}] Fallo al copiar orden {master_pos.ticket}: {result.comment}")
        return None
    
    logging.info(f"[Slave {slave_login}] Orden {master_pos.ticket} copiada con éxito. Ticket: {result.order}, Lote: {lot_size}")
    return result.order

# --- FLUJO PRINCIPAL ---

def main():
    """Función principal que ejecuta el bucle de polling."""
    # 1. Cargar configuración y estado
    config = load_json(CONFIG_FILE)
    state = load_json(STATE_FILE)

    if not config:
        logging.error("No se pudo cargar config.json. Saliendo.")
        return

    # 2. Inicializar conexiones MT5
    if not initialize_mt5(config['master']):
        return

    slave_connections = {}
    for slave_config in config['slaves']:
        # Se crea una "conexión" lógica para cada slave, aunque MT5 no lo requiera explícitamente
        # La clave es usar el `mt5_path` correcto al inicializar antes de operar
        slave_connections[slave_config['login']] = slave_config

    logging.info("RiskSync iniciado. Monitoreando operaciones...")

    # 3. Bucle de monitoreo
    while True:
        try:
            # Reconectar a la cuenta master para asegurar la sesión
            if not initialize_mt5(config['master']):
                time.sleep(5) # Esperar antes de reintentar
                continue

            master_positions = mt5.positions_get()
            if master_positions is None:
                master_positions = []

            open_master_tickets = {pos.ticket for pos in master_positions}

            # --- A. DETECTAR OPERACIONES CERRADAS ---
            closed_tickets = [ticket for ticket in state if int(ticket) not in open_master_tickets]
            for ticket in closed_tickets:
                logging.info(f"[Master] Operación {ticket} cerrada.")
                for slave_login, slave_ticket in state[ticket]['slaves'].items():
                    if initialize_mt5(slave_connections[int(slave_login)]):
                        # Lógica para cerrar la posición en el slave
                        res = mt5.close_position(slave_ticket)
                        if res:
                            logging.info(f"[Slave {slave_login}] Posición {slave_ticket} cerrada.")
                        else:
                            logging.warning(f"[Slave {slave_login}] No se pudo cerrar la posición {slave_ticket}. Puede que ya esté cerrada.")
                del state[ticket]

            # --- B. DETECTAR OPERACIONES NUEVAS Y MODIFICADAS ---
            for pos in master_positions:
                ticket_str = str(pos.ticket)

                # Si la operación es nueva
                if ticket_str not in state:
                    logging.info(f"[Master] NUEVA operación detectada: {pos.symbol} {('BUY' if pos.type == 0 else 'SELL')} {pos.volume} @ {pos.price_open}")
                    
                    if config.get('ignore_no_sl', True) and pos.sl == 0.0:
                        logging.warning(f"Operación {pos.ticket} ignorada por falta de SL.")
                        continue

                    state[ticket_str] = {'slaves': {}}
                    for slave_config in config['slaves']:
                        if initialize_mt5(slave_config):
                            lot_size = calculate_lot_size(pos, slave_config['risk_usd'], mt5)
                            if lot_size:
                                slave_ticket = place_order(slave_config['login'], pos, lot_size, config.get('trade_comment', 'RiskSync'))
                                if slave_ticket:
                                    state[ticket_str]['slaves'][str(slave_config['login'])] = slave_ticket
                        else:
                            logging.error(f"No se pudo conectar al slave {slave_config['login']} para copiar la operación.")
                
                # Si la operación ya existe, comprobar modificaciones de SL/TP
                else:
                    cached_pos = state.get(ticket_str, {})
                    if cached_pos.get('sl') != pos.sl or cached_pos.get('tp') != pos.tp:
                        logging.info(f"[Master] Modificación de SL/TP detectada para {pos.ticket}. Nuevo SL: {pos.sl}, Nuevo TP: {pos.tp}")
                        for slave_login, slave_ticket in cached_pos['slaves'].items():
                            if initialize_mt5(slave_connections[int(slave_login)]):
                                request = {
                                    'action': mt5.TRADE_ACTION_SLTP,
                                    'position': slave_ticket,
                                    'sl': pos.sl,
                                    'tp': pos.tp
                                }
                                result = mt5.order_send(request)
                                if result.retcode == mt5.TRADE_RETCODE_DONE:
                                    logging.info(f"[Slave {slave_login}] SL/TP actualizado para {slave_ticket}.")
                                else:
                                    logging.error(f"[Slave {slave_login}] Fallo al actualizar SL/TP para {slave_ticket}: {result.comment}")
            
            # Guardar el estado actual
            save_json(state, STATE_FILE)

        except Exception as e:
            logging.error(f"Ocurrió un error en el bucle principal: {e}")
        
        # Esperar el intervalo definido
        time.sleep(config.get('loop_interval', 0.2))

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("RiskSync detenido por el usuario.")
        # Desconectar de todas las cuentas al salir
        mt5.shutdown()
