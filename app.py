"""
BOT DE TRADING PROFESIONAL AUTÓNOMO PARA IQ OPTION - VERSIÓN CON VENCIMIENTO VARIABLE
- Prioriza activos por fuerza de tendencia
- Vencimiento 1 min (fuerza ≥70%, volumen alto, sin retroceso)
- Vencimiento 5 min (retroceso en tendencia fuerte)
- 5 estrategias independientes que votan
- Cambio automático de activo cada 5 min si no hay señal
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pytz
from datetime import datetime, timedelta
import ta
import time
import logging
import warnings
warnings.filterwarnings('ignore')

from streamlit_autorefresh import st_autorefresh

# Importar la API de IQ Option
try:
    from iqoptionapi.stable_api import IQ_Option
    IQ_AVAILABLE = True
except ImportError as e:
    IQ_AVAILABLE = False
    st.error(f"""
    ⚠️ **Error crítico:** No se pudo importar la librería `iqoptionapi`.
    Verifica que la línea en `requirements.txt` sea exactamente:
    `git+https://github.com/williansandi/iqoptionapi-2025-Atualizada-.git#egg=iqoptionapi`
    Detalle del error: {e}
    """)

# Configuración de página
st.set_page_config(
    page_title="IQ Option Pro Bot",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Autorefresh cada 5 segundos
st_autorefresh(interval=5000, key="autorefresh")

# CSS personalizado
st.markdown("""
<style>
    @import url('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css');
    .stApp {
        background-color: #0A0C10;
        color: #E0E0E0;
        font-family: 'Inter', sans-serif;
    }
    h1, h2, h3 {
        color: #00FF88 !important;
        font-weight: 700 !important;
    }
    .status-card {
        background: rgba(18, 22, 30, 0.9);
        border-radius: 20px;
        padding: 20px;
        border: 1px solid #00FF8844;
        margin: 10px 0;
        backdrop-filter: blur(10px);
    }
    .evento {
        background: #1E242C;
        border-left: 4px solid #00FF88;
        padding: 10px;
        margin: 5px 0;
        border-radius: 5px;
        font-size: 14px;
    }
    .reloj {
        font-size: 28px;
        font-weight: 700;
        color: #00FF88;
        text-align: center;
        background: #151A24;
        padding: 15px;
        border-radius: 50px;
        margin-bottom: 20px;
        border: 1px solid #00FF88;
    }
    .stButton button {
        background: #00FF88;
        color: black;
        font-weight: 700;
        border-radius: 40px;
        border: none;
        padding: 10px 25px;
        transition: all 0.3s;
    }
    .stButton button:hover {
        background: #00CC66;
        transform: scale(1.05);
        box-shadow: 0 0 15px #00FF88;
    }
    .metric-card {
        background: #151A24;
        border-radius: 15px;
        padding: 15px;
        border: 1px solid #00FF8844;
    }
    .icono-estado {
        font-size: 24px;
        margin-right: 10px;
    }
    .signal-badge {
        font-size: 18px;
        font-weight: 700;
        padding: 5px 10px;
        border-radius: 20px;
        display: inline-block;
    }
    .signal-compra {
        background: rgba(0, 255, 136, 0.2);
        color: #00FF88;
        border: 1px solid #00FF88;
    }
    .signal-venta {
        background: rgba(255, 70, 70, 0.2);
        color: #FF4646;
        border: 1px solid #FF4646;
    }
    .signal-neutro {
        background: rgba(255, 255, 255, 0.1);
        color: #AAAAAA;
        border: 1px solid #AAAAAA;
    }
    .signal-ejecutada {
        background: rgba(255, 215, 0, 0.2);
        color: gold;
        border: 1px solid gold;
    }
</style>
""", unsafe_allow_html=True)

# Zona horaria Ecuador
ecuador_tz = pytz.timezone('America/Guayaquil')

# ============================================
# CLASE DE CONEXIÓN IQ OPTION (MEJORADA CON REINTENTOS)
# ============================================
class IQOptionConnector:
    def __init__(self):
        self.api = None
        self.conectado = False
        self.balance = 0
        self.tipo_cuenta = "PRACTICE"
        self.activos_cache = {}
        self.ordenes_pendientes = {}
        self.max_reintentos = 3
        self.timeout = 30

    def conectar(self, email, password):
        if not IQ_AVAILABLE:
            return False, "Librería IQ Option no disponible."
        for intento in range(1, self.max_reintentos + 1):
            try:
                self.api = IQ_Option(email, password)
                check, reason = self.api.connect()
                if check:
                    self.conectado = True
                    self.balance = self.api.get_balance()
                    return True, f"Conexión exitosa en intento {intento}"
                else:
                    if "authentication" in reason.lower() or "credenciales" in reason.lower():
                        return False, f"Error de autenticación: {reason}"
                    if intento < self.max_reintentos:
                        time.sleep(2)
                    else:
                        return False, f"Error tras {intento} intentos: {reason}"
            except Exception as e:
                error_msg = str(e)
                if intento < self.max_reintentos:
                    time.sleep(2)
                else:
                    return False, f"Excepción en conexión: {error_msg}"
        return False, "No se pudo conectar después de reintentos"

    def cambiar_balance(self, tipo="PRACTICE"):
        if self.conectado:
            try:
                self.api.change_balance(tipo)
                self.tipo_cuenta = tipo
                time.sleep(1)
                self.balance = self.api.get_balance()
                return True
            except Exception as e:
                logging.error(f"Error al cambiar balance: {e}")
                return False
        return False

    def actualizar_balance(self):
        if self.conectado:
            self.balance = self.api.get_balance()
        return self.balance

    def obtener_saldo(self):
        return self.balance

    def obtener_activos_disponibles(self, mercado="otc", max_activos=200, force_refresh=False):
        if not self.conectado:
            return []
        cache_key = f"{mercado}_{max_activos}"
        if not force_refresh and cache_key in self.activos_cache:
            return self.activos_cache[cache_key]
        try:
            activos_data = self.api.get_all_open_time()
            activos = []
            if mercado == "forex":
                for activo, data in activos_data.get("forex", {}).items():
                    if data.get("open", False) and "-OTC" not in activo:
                        activos.append(activo)
            else:
                for categoria in ["binary", "turbo"]:
                    for activo, data in activos_data.get(categoria, {}).items():
                        if data.get("open", False) and "-OTC" in activo:
                            activos.append(activo)
            activos = sorted(activos)[:max_activos]
            self.activos_cache[cache_key] = activos
            return activos
        except Exception as e:
            st.error(f"Error obteniendo activos: {e}")
            return []

    def obtener_velas(self, activo, intervalo=5, limite=100):
        if not self.conectado:
            return None
        try:
            time.sleep(0.15)
            if intervalo == 5:
                velas = self.api.get_candles(activo, 60, limite * 5, time.time())
            else:
                velas = self.api.get_candles(activo, 60, limite, time.time())
            if not velas:
                return None
            df = pd.DataFrame(velas)
            df['datetime'] = pd.to_datetime(df['from'], unit='s')
            df = df.set_index('datetime')
            df = df.rename(columns={
                'open': 'open',
                'max': 'high',
                'min': 'low',
                'close': 'close',
                'volume': 'volume'
            })
            df = df[['open', 'high', 'low', 'close', 'volume']].astype(float).sort_index()
            if intervalo == 5:
                df = df.resample('5T').agg({
                    'open': 'first',
                    'high': 'max',
                    'low': 'min',
                    'close': 'last',
                    'volume': 'sum'
                }).dropna()
            return df
        except Exception as e:
            logging.error(f"Error obteniendo velas de {activo}: {e}")
            return None

    def colocar_orden(self, activo, direccion, monto, expiracion):
        if not self.conectado:
            return None, "No conectado"
        try:
            direccion_api = 'call' if direccion.upper() == 'COMPRA' else 'put'
            tiempo = expiracion * 60
            resultado = self.api.buy(monto, activo, direccion_api, tiempo)
            if resultado and len(resultado) > 0:
                id_orden = resultado[0] if isinstance(resultado, list) else resultado
                self.ordenes_pendientes[id_orden] = {
                    'activo': activo,
                    'direccion': direccion,
                    'monto': monto,
                    'expiracion': expiracion,
                    'timestamp': time.time()
                }
                return id_orden, "Orden ejecutada"
            else:
                return None, "Error al ejecutar orden"
        except Exception as e:
            return None, str(e)

    def verificar_orden(self, id_orden):
        """Consulta el resultado de una orden por su ID (debes adaptarlo según tu API)."""
        try:
            # Ejemplo: self.api.get_optioninfo(id_orden)
            # Retorna un dict con 'win' booleano y 'amount'
            return None  # Implementar según la API
        except Exception as e:
            logging.error(f"Error verificando orden {id_orden}: {e}")
            return None

# ============================================
# INDICADORES TÉCNICOS
# ============================================
def calcular_indicadores(df):
    if df is None or len(df) < 30:
        return None
    if df['volume'].sum() == 0:
        df['volume'] = (df['high'] - df['low']) * 1000 / df['close']
    df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    df['ema_20'] = ta.trend.EMAIndicator(df['close'], window=20).ema_indicator()
    df['ema_50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
    df['ema_200'] = ta.trend.EMAIndicator(df['close'], window=200).ema_indicator()
    df['volume_ma'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_ma'].clip(lower=1)
    adx = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
    df['adx'] = adx.adx()
    df['adx_pos'] = adx.adx_pos()
    df['adx_neg'] = adx.adx_neg()
    bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
    df['bb_width'] = (bb.bollinger_hband() - bb.bollinger_lband()) / df['close'] * 100
    df['bb_lower'] = bb.bollinger_lband()
    df['bb_upper'] = bb.bollinger_hband()
    df['psar'] = ta.trend.PSARIndicator(df['high'], df['low'], df['close']).psar()
    return df

# ============================================
# DETECCIÓN DE SOPORTES Y RESISTENCIAS
# ============================================
def detectar_soportes_resistencias(df, ventana=20):
    if df is None or len(df) < ventana:
        return [], []
    highs = df['high'].values
    lows = df['low'].values
    soportes = []
    resistencias = []
    for i in range(1, len(df)-1):
        if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
            resistencias.append(highs[i])
        if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
            soportes.append(lows[i])
    if len(resistencias) == 0:
        resistencias = [df['high'].max()]
    if len(soportes) == 0:
        soportes = [df['low'].min()]
    return soportes[-3:], resistencias[-3:]

# ============================================
# DETECCIÓN DE TENDENCIA Y FUERZA
# ============================================
def detectar_tendencia(df):
    if df is None or len(df) < 50:
        return 'lateral', 0, 'lateral'
    ult = df.iloc[-1]
    pendiente_ema20 = (df['ema_20'].iloc[-1] - df['ema_20'].iloc[-10]) / 10
    pendiente_ema50 = (df['ema_50'].iloc[-1] - df['ema_50'].iloc[-10]) / 10
    sobre_ema20 = ult['close'] > ult['ema_20']
    sobre_ema50 = ult['close'] > ult['ema_50']
    sobre_ema200 = ult['close'] > ult['ema_200']
    volumen_fuerte = ult['volume_ratio'] > 1.2
    adx_fuerte = ult['adx'] > 25

    fuerza = 0
    if pendiente_ema20 > 0:
        fuerza += 20
    if pendiente_ema50 > 0:
        fuerza += 15
    if sobre_ema20:
        fuerza += 10
    if sobre_ema50:
        fuerza += 10
    if sobre_ema200:
        fuerza += 10
    if volumen_fuerte:
        fuerza += 15
    if adx_fuerte:
        fuerza += 20

    direccion = 'lateral'
    if (pendiente_ema20 > 0 and pendiente_ema50 > 0) or (sobre_ema20 and sobre_ema50 and sobre_ema200):
        direccion = 'alcista'
    elif (pendiente_ema20 < 0 and pendiente_ema50 < 0) or (not sobre_ema20 and not sobre_ema50 and not sobre_ema200):
        direccion = 'bajista'

    if direccion == 'lateral':
        return 'lateral', 0, 'lateral'
    elif fuerza >= 70:
        return direccion, min(100, fuerza), 'muy fuerte'
    elif fuerza >= 50:
        return direccion, min(100, fuerza), 'fuerte'
    elif fuerza >= 35:
        return direccion, min(100, fuerza), 'débil'
    elif fuerza >= 20:
        return direccion, min(100, fuerza), 'micro'
    else:
        return direccion, min(100, fuerza), 'muy débil'

# ============================================
# ESTRATEGIAS INDEPENDIENTES (5)
# ============================================
def estrategia_1_ruptura_con_volumen(df):
    if df is None or len(df) < 15:
        return 0, 0
    ult = df.iloc[-1]
    max_10 = df['high'].iloc[-10:-1].max()
    min_10 = df['low'].iloc[-10:-1].min()
    if ult['close'] > max_10 and ult['volume_ratio'] > 1.1:
        return 1, 75
    elif ult['close'] < min_10 and ult['volume_ratio'] > 1.1:
        return -1, 75
    return 0, 0

def estrategia_2_pendiente_ema_adx(df):
    if df is None or len(df) < 20:
        return 0, 0
    ult = df.iloc[-1]
    pendiente = (df['ema_20'].iloc[-1] - df['ema_20'].iloc[-5]) / 5
    if pendiente > 0.0015 * ult['close'] and ult['adx'] > 20 and ult['adx_pos'] > ult['adx_neg']:
        return 1, 70
    elif pendiente < -0.0015 * ult['close'] and ult['adx'] > 20 and ult['adx_neg'] > ult['adx_pos']:
        return -1, 70
    return 0, 0

def estrategia_3_bandas_bollinger_rsi(df):
    if df is None or len(df) < 20:
        return 0, 0
    ult = df.iloc[-1]
    if ult['close'] <= ult['bb_lower'] and ult['rsi'] < 45 and ult['volume_ratio'] > 1.0:
        return 1, 65
    elif ult['close'] >= ult['bb_upper'] and ult['rsi'] > 55 and ult['volume_ratio'] > 1.0:
        return -1, 65
    return 0, 0

def estrategia_4_macd_histograma(df):
    if df is None or len(df) < 30:
        return 0, 0
    macd = ta.trend.MACD(df['close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    if df['macd'].iloc[-1] > df['macd_signal'].iloc[-1] and df['macd'].iloc[-2] <= df['macd_signal'].iloc[-2] and df['volume_ratio'].iloc[-1] > 1.0:
        return 1, 68
    elif df['macd'].iloc[-1] < df['macd_signal'].iloc[-1] and df['macd'].iloc[-2] >= df['macd_signal'].iloc[-2] and df['volume_ratio'].iloc[-1] > 1.0:
        return -1, 68
    return 0, 0

def estrategia_5_parabolic_sar_volumen(df):
    if df is None or len(df) < 20:
        return 0, 0
    ult = df.iloc[-1]
    prev = df.iloc[-2]
    if prev['psar'] > prev['close'] and ult['psar'] < ult['close'] and ult['volume_ratio'] > 1.1:
        return 1, 72
    elif prev['psar'] < prev['close'] and ult['psar'] > ult['close'] and ult['volume_ratio'] > 1.1:
        return -1, 72
    return 0, 0

# ============================================
# IA DE CONFIRMACIÓN (voto por mayoría)
# ============================================
def confirmar_operacion(df, tendencia, fuerza_tendencia):
    resultados = [
        estrategia_1_ruptura_con_volumen(df),
        estrategia_2_pendiente_ema_adx(df),
        estrategia_3_bandas_bollinger_rsi(df),
        estrategia_4_macd_histograma(df),
        estrategia_5_parabolic_sar_volumen(df)
    ]

    compra_count = 0
    venta_count = 0
    for dir_, conf in resultados:
        if dir_ == 1:
            compra_count += 1
        elif dir_ == -1:
            venta_count += 1

    # Dar peso extra a la tendencia
    if tendencia == 'alcista':
        compra_count += 1
    elif tendencia == 'bajista':
        venta_count += 1

    if compra_count >= 3:
        conf_promedio = sum(conf for dir_, conf in resultados if dir_ == 1) // max(1, compra_count)
        return 1, conf_promedio
    elif venta_count >= 3:
        conf_promedio = sum(conf for dir_, conf in resultados if dir_ == -1) // max(1, venta_count)
        return -1, conf_promedio
    else:
        return 0, 0

# ============================================
# DETECCIÓN DE RETROCESO Y DECISIÓN DE VENCIMIENTO
# ============================================
def evaluar_retroceso_y_vencimiento(df, tendencia, fuerza):
    """
    Retorna (hay_retroceso, vencimiento_recomendado)
    vencimiento: 1 o 5 minutos
    """
    if df is None or len(df) < 20:
        return False, 5
    ult = df.iloc[-1]
    soportes, resistencias = detectar_soportes_resistencias(df)

    # Caso 1: Tendencia muy fuerte (≥70%) y volumen alto y sin retroceso -> 1 minuto
    if fuerza >= 70 and ult['volume_ratio'] > 1.5:
        # Verificar si está cerca de un extremo (posible retroceso inminente)
        cerca_soporte = any(abs(ult['close'] - s) < 0.001 * ult['close'] for s in soportes) if tendencia == 'alcista' else False
        cerca_resistencia = any(abs(ult['close'] - r) < 0.001 * ult['close'] for r in resistencias) if tendencia == 'bajista' else False
        if not cerca_soporte and not cerca_resistencia:
            # No hay señal de retroceso cercano -> operación rápida de 1 min
            return False, 1

    # Caso 2: Buscar retroceso para operar a 5 minutos
    if tendencia == 'alcista':
        # Soporte cercano o EMA20 por debajo
        soporte_cercano = min([s for s in soportes if s < ult['close']], default=None)
        if soporte_cercano and (ult['close'] - soporte_cercano) < 0.002 * ult['close']:
            return True, 5
        if ult['close'] > ult['ema_20'] and (ult['close'] - ult['ema_20']) < 0.0015 * ult['close']:
            return True, 5
    elif tendencia == 'bajista':
        resistencia_cercana = max([r for r in resistencias if r > ult['close']], default=None)
        if resistencia_cercana and (resistencia_cercana - ult['close']) < 0.002 * ult['close']:
            return True, 5
        if ult['close'] < ult['ema_20'] and (ult['ema_20'] - ult['close']) < 0.0015 * ult['close']:
            return True, 5

    return False, 5  # Por defecto, 5 minutos si no hay condición especial

# ============================================
# CLASE PARA GESTIONAR OPERACIONES Y LÍMITES
# ============================================
class TradingManager:
    def __init__(self):
        self.activo_actual = None
        self.estado = "Detenido"
        self.operaciones_hoy = 0
        self.ultimo_cambio_activo = time.time()  # Inicializado correctamente
        self.historial = []
        self.log_eventos = []
        self.ordenes_pendientes = {}
        self.ultima_operacion_timestamp = None

    def agregar_evento(self, mensaje, icono="ℹ️"):
        timestamp = datetime.now(ecuador_tz).strftime('%H:%M:%S')
        self.log_eventos.append(f"[{timestamp}] {icono} {mensaje}")
        if len(self.log_eventos) > 20:
            self.log_eventos = self.log_eventos[-20:]

    def agregar_operacion(self, activo, direccion, monto, expiracion, resultado, ganancia):
        self.historial.append({
            'fecha': datetime.now(ecuador_tz).strftime('%Y-%m-%d %H:%M:%S'),
            'activo': activo,
            'direccion': direccion,
            'monto': monto,
            'expiracion': expiracion,
            'resultado': resultado,
            'ganancia': ganancia
        })
        self.operaciones_hoy += 1
        self.ultima_operacion_timestamp = time.time()

    def actualizar_resultados(self, connector):
        for id_orden, info in list(self.ordenes_pendientes.items()):
            if time.time() - info['timestamp'] > info['expiracion'] * 60 + 10:
                resultado = connector.verificar_orden(id_orden)
                if resultado:
                    if resultado.get('win'):
                        ganancia = info['monto'] * 0.8
                        self.agregar_operacion(info['activo'], info['direccion'], info['monto'], info['expiracion'], 'ganada', ganancia)
                        self.agregar_evento(f"💰 Operación GANADA en {info['activo']} (${ganancia:.2f}) - {info['expiracion']} min", "💰")
                    else:
                        perdida = -info['monto']
                        self.agregar_operacion(info['activo'], info['direccion'], info['monto'], info['expiracion'], 'perdida', perdida)
                        self.agregar_evento(f"💸 Operación PERDIDA en {info['activo']} - ${perdida:.2f}", "💸")
                    del self.ordenes_pendientes[id_orden]

    def obtener_resumen(self):
        if not self.historial:
            return {'total': 0, 'ganadas': 0, 'perdidas': 0, 'neto': 0}
        df = pd.DataFrame(self.historial)
        ganadas = df[df['resultado'] == 'ganada'].shape[0]
        perdidas = df[df['resultado'] == 'perdida'].shape[0]
        neto = df['ganancia'].sum()
        return {
            'total': len(self.historial),
            'ganadas': ganadas,
            'perdidas': perdidas,
            'neto': neto
        }

# ============================================
# CICLO PRINCIPAL DE ANÁLISIS Y EJECUCIÓN
# ============================================
def ciclo_principal(connector, manager, config):
    tiempo_actual = time.time()

    if manager.operaciones_hoy >= config['limite_diario']:
        if manager.estado != "Límite alcanzado":
            manager.estado = "Límite alcanzado"
            manager.agregar_evento("⛔ Límite de operaciones diarias alcanzado. Bot detenido.", "⛔")
        return

    manager.actualizar_resultados(connector)

    # Decidir si buscar nuevo activo
    if manager.activo_actual is None:
        buscar_nuevo = True
    else:
        if manager.estado == "Analizando" and tiempo_actual - manager.ultimo_cambio_activo > 300:
            manager.agregar_evento(f"⏱️ Tiempo sin señal en {manager.activo_actual}. Buscando otro...", "⏱️")
            buscar_nuevo = True
        else:
            buscar_nuevo = False

    if buscar_nuevo:
        manager.estado = "🔍 Buscando activos..."
        manager.agregar_evento("Buscando activos con tendencias...", "🔍")
        activos = connector.obtener_activos_disponibles(config['mercado'], max_activos=100)
        mejores_activos = []
        for act in activos[:50]:
            df = connector.obtener_velas(act, intervalo=5, limite=100)
            if df is None:
                continue
            df = calcular_indicadores(df)
            if df is None:
                continue
            tendencia, fuerza, tipo = detectar_tendencia(df)
            if tendencia != 'lateral' and fuerza >= 20:
                mejores_activos.append((act, fuerza, tendencia, tipo, df))

        if mejores_activos:
            # Ordenar por fuerza descendente
            mejores_activos.sort(key=lambda x: x[1], reverse=True)
            mejor = mejores_activos[0]
            manager.activo_actual = mejor[0]
            manager.ultimo_cambio_activo = tiempo_actual
            manager.agregar_evento(f"✅ Mejor activo: {mejor[0]} - Tendencia {mejor[2]} ({mejor[3]}) - Fuerza {mejor[1]}%", "✅")
            manager.estado = "Analizando"
        else:
            manager.agregar_evento("⚠️ No se encontró ningún activo. Reintentando en 5 min...", "⚠️")
            return

    # Analizar activo actual
    df = connector.obtener_velas(manager.activo_actual, intervalo=5, limite=100)
    if df is None:
        manager.agregar_evento(f"❌ Error al obtener datos de {manager.activo_actual}. Buscando otro...", "❌")
        manager.activo_actual = None
        return
    df = calcular_indicadores(df)
    if df is None:
        manager.activo_actual = None
        return

    tendencia, fuerza, tipo = detectar_tendencia(df)
    ult = df.iloc[-1]

    # Determinar tipo de volumen (compra/venta)
    volumen_tipo = "COMPRA" if ult['close'] > ult['open'] else "VENTA"

    # Guardar en session_state
    st.session_state.tendencia_actual = tendencia
    st.session_state.fuerza_actual = fuerza
    st.session_state.tipo_tendencia = tipo
    st.session_state.precio_actual = ult['close']
    st.session_state.volumen_actual = ult['volume_ratio']
    st.session_state.volumen_tipo = volumen_tipo
    st.session_state.activo_actual = manager.activo_actual

    if tendencia == 'lateral' or fuerza < 20:
        manager.agregar_evento(f"🔄 Mercado sin tendencia en {manager.activo_actual}. Buscando otro...", "🔄")
        manager.activo_actual = None
        manager.estado = "Buscando"
        return

    if manager.estado == "Analizando":
        decision, confianza = confirmar_operacion(df, tendencia, fuerza)
        if decision != 0:
            # Evaluar si hay retroceso y decidir vencimiento
            hay_retroceso, vencimiento = evaluar_retroceso_y_vencimiento(df, tendencia, fuerza)
            direccion = "COMPRA" if decision == 1 else "VENTA"

            if vencimiento == 1:
                # Operación rápida: sin esperar retroceso
                id_orden, msg = connector.colocar_orden(
                    manager.activo_actual,
                    direccion,
                    config['monto'],
                    expiracion=1
                )
                if id_orden:
                    manager.agregar_evento(f"✅ OPERACIÓN EJECUTADA: {direccion} en {manager.activo_actual} - Vencimiento 1 minuto (ID: {id_orden})", "✅")
                    manager.ordenes_pendientes[id_orden] = {
                        'activo': manager.activo_actual,
                        'direccion': direccion,
                        'monto': config['monto'],
                        'expiracion': 1,
                        'timestamp': time.time()
                    }
                    st.session_state.senal_actual = "EJECUTADA 1m"
                    connector.actualizar_balance()
                else:
                    manager.agregar_evento(f"❌ Error al ejecutar orden 1m: {msg}", "❌")
            else:
                # Operación a 5 minutos: esperar retroceso
                precio_entrada = None
                if hay_retroceso:
                    # Calcular punto de retroceso
                    if tendencia == 'alcista':
                        soportes, _ = detectar_soportes_resistencias(df)
                        soporte_cercano = min([s for s in soportes if s < ult['close']], default=ult['ema_20'])
                        precio_entrada = max(soporte_cercano, ult['ema_20'])
                    else:
                        _, resistencias = detectar_soportes_resistencias(df)
                        resistencia_cercana = max([r for r in resistencias if r > ult['close']], default=ult['ema_20'])
                        precio_entrada = min(resistencia_cercana, ult['ema_20'])
                else:
                    # Si no hay retroceso claro, usar EMA20
                    precio_entrada = ult['ema_20']

                manager.agregar_evento(f"🎯 Oportunidad a 5 min en {manager.activo_actual} - {direccion} (confianza {confianza}%)", "🎯")
                manager.agregar_evento(f"📉 Esperando retroceso a {precio_entrada:.5f}...", "📉")
                manager.estado = "EsperandoRetroceso"
                manager.precio_objetivo = precio_entrada
                manager.direccion = direccion
                manager.confianza = confianza
                st.session_state.senal_actual = direccion
        else:
            st.session_state.senal_actual = "NEUTRO"
            manager.agregar_evento(f"⏳ {manager.activo_actual} en tendencia {tendencia} ({tipo}, fuerza {fuerza}%) pero sin señal clara...", "⏳")

    elif manager.estado == "EsperandoRetroceso":
        if (manager.direccion == "COMPRA" and ult['close'] <= manager.precio_objetivo) or \
           (manager.direccion == "VENTA" and ult['close'] >= manager.precio_objetivo):
            id_orden, msg = connector.colocar_orden(
                manager.activo_actual,
                manager.direccion,
                config['monto'],
                expiracion=5
            )
            if id_orden:
                manager.agregar_evento(f"✅ OPERACIÓN EJECUTADA: {manager.direccion} en {manager.activo_actual} - Vencimiento 5 minutos (ID: {id_orden})", "✅")
                manager.ordenes_pendientes[id_orden] = {
                    'activo': manager.activo_actual,
                    'direccion': manager.direccion,
                    'monto': config['monto'],
                    'expiracion': 5,
                    'timestamp': time.time()
                }
                manager.estado = "Analizando"
                connector.actualizar_balance()
                st.session_state.senal_actual = "EJECUTADA 5m"
            else:
                manager.agregar_evento(f"❌ Error al ejecutar orden: {msg}", "❌")
                manager.estado = "Analizando"
        else:
            if manager.direccion == "COMPRA" and ult['close'] > manager.precio_objetivo * 1.01:
                manager.agregar_evento("⏹️ Retroceso cancelado - precio se alejó", "⏹️")
                manager.estado = "Analizando"
            elif manager.direccion == "VENTA" and ult['close'] < manager.precio_objetivo * 0.99:
                manager.agregar_evento("⏹️ Retroceso cancelado - precio se alejó", "⏹️")
                manager.estado = "Analizando"

# ============================================
# INTERFAZ PRINCIPAL
# ============================================
def main():
    st.title("🤖 IQ OPTION PROFESSIONAL BOT")
    st.markdown("#### Modo autónomo con vencimiento variable (1/5 min) | Prioriza tendencias fuertes")
    st.markdown("---")

    # Inicializar estado de sesión
    if 'connector' not in st.session_state:
        st.session_state.connector = IQOptionConnector()
    if 'conectado' not in st.session_state:
        st.session_state.conectado = False
    if 'manager' not in st.session_state:
        st.session_state.manager = TradingManager()
    if 'config' not in st.session_state:
        st.session_state.config = {
            'mercado': 'otc',
            'monto': 1.0,
            'limite_diario': 5
        }
    if 'bot_activo' not in st.session_state:
        st.session_state.bot_activo = False
    if 'tendencia_actual' not in st.session_state:
        st.session_state.tendencia_actual = 'desconocida'
        st.session_state.fuerza_actual = 0
        st.session_state.tipo_tendencia = 'desconocida'
        st.session_state.precio_actual = 0
        st.session_state.volumen_actual = 0
        st.session_state.volumen_tipo = 'N/A'
        st.session_state.senal_actual = 'NEUTRO'
        st.session_state.activo_actual = 'Ninguno'

    # Panel superior de configuración
    with st.container():
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown("### 🔐 Conexión")
            if not st.session_state.conectado:
                email = st.text_input("Email", placeholder="usuario@email.com", key="email")
                password = st.text_input("Contraseña", type="password", placeholder="••••••••", key="pass")
                if st.button("🔌 Conectar", use_container_width=True):
                    if email and password:
                        with st.spinner("Conectando..."):
                            ok, msg = st.session_state.connector.conectar(email, password)
                            if ok:
                                st.session_state.conectado = True
                                st.success(f"✅ Conectado - Saldo: ${st.session_state.connector.obtener_saldo():.2f}")
                                st.rerun()
                            else:
                                st.error(f"❌ {msg}")
            else:
                st.success("✅ Conectado")
                st.metric("Saldo", f"${st.session_state.connector.obtener_saldo():.2f}")

        with col2:
            st.markdown("### ⚙️ Configuración")
            cuenta = st.radio("Cuenta", ["💰 Demo", "💵 Real"], horizontal=True, key="cuenta")
            tipo_cuenta = "PRACTICE" if "Demo" in cuenta else "REAL"
            if tipo_cuenta != st.session_state.connector.tipo_cuenta and st.session_state.conectado:
                with st.spinner("Cambiando cuenta..."):
                    exito = st.session_state.connector.cambiar_balance(tipo_cuenta)
                    if exito:
                        st.success(f"Cuenta cambiada a {tipo_cuenta}")
                    else:
                        st.error("Error al cambiar cuenta")
                st.rerun()

            mercado = st.radio("Mercado", ["🌙 OTC", "📊 Normal"], horizontal=True, key="mercado")
            st.session_state.config['mercado'] = "otc" if "OTC" in mercado else "forex"

        with col3:
            st.markdown("### 💰 Monto")
            st.session_state.config['monto'] = st.number_input(
                "Por operación ($)",
                min_value=1.0 if "Real" in cuenta else 0.1,
                max_value=1000.0 if "Real" in cuenta else 100.0,
                value=st.session_state.config['monto'],
                step=1.0
            )

        with col4:
            st.markdown("### ⏱️ Límite")
            st.session_state.config['limite_diario'] = st.number_input(
                "Operaciones/día",
                min_value=1,
                max_value=50,
                value=st.session_state.config['limite_diario'],
                step=1
            )
            if st.session_state.conectado:
                if st.session_state.bot_activo:
                    if st.button("⏹️ DETENER BOT", use_container_width=True):
                        st.session_state.bot_activo = False
                        st.session_state.manager.estado = "Detenido"
                        st.session_state.manager.agregar_evento("⏹️ Bot detenido manualmente", "⏹️")
                        st.rerun()
                else:
                    if st.button("▶️ INICIAR BOT", use_container_width=True):
                        st.session_state.bot_activo = True
                        st.session_state.manager.estado = "Buscando"
                        st.session_state.manager.agregar_evento("▶️ Bot iniciado", "▶️")
                        st.rerun()

    st.markdown("---")

    if not st.session_state.conectado:
        st.info("👆 Conéctate a IQ Option para comenzar.")
        return

    ahora = datetime.now(ecuador_tz)
    st.markdown(f"<div class='reloj'>⏰ {ahora.strftime('%H:%M:%S')} ECU</div>", unsafe_allow_html=True)

    if st.session_state.bot_activo:
        ciclo_principal(st.session_state.connector, st.session_state.manager, st.session_state.config)

    col1, col2 = st.columns([1.2, 0.8])
    with col1:
        st.markdown("### 📊 Estado del Bot")
        manager = st.session_state.manager
        resumen = manager.obtener_resumen()

        icono_estado = {
            "Detenido": "⏹️",
            "Buscando": "🔍",
            "Analizando": "📊",
            "EsperandoRetroceso": "⏳",
            "Límite alcanzado": "⛔"
        }.get(manager.estado, "🤖")

        if st.session_state.senal_actual == 'COMPRA':
            signal_class = 'signal-compra'
            signal_text = 'COMPRA'
        elif st.session_state.senal_actual == 'VENTA':
            signal_class = 'signal-venta'
            signal_text = 'VENTA'
        elif st.session_state.senal_actual == 'EJECUTADA 1m':
            signal_class = 'signal-ejecutada'
            signal_text = 'EJECUTADA 1m'
        elif st.session_state.senal_actual == 'EJECUTADA 5m':
            signal_class = 'signal-ejecutada'
            signal_text = 'EJECUTADA 5m'
        else:
            signal_class = 'signal-neutro'
            signal_text = 'NEUTRO'

        st.markdown(f"""
        <div class="status-card">
            <h3><span class="icono-estado">{icono_estado}</span> {manager.estado}</h3>
            <p><strong>Activo actual:</strong> {st.session_state.activo_actual}</p>
            <p><strong>Tendencia:</strong> {st.session_state.tendencia_actual} ({st.session_state.tipo_tendencia}) - Fuerza {st.session_state.fuerza_actual}%</p>
            <p><strong>Precio actual:</strong> {st.session_state.precio_actual:.5f}</p>
            <p><strong>Volumen:</strong> {st.session_state.volumen_actual:.2f}x ({st.session_state.volumen_tipo})</p>
            <p><strong>Señal:</strong> <span class="signal-badge {signal_class}">{signal_text}</span></p>
            <p><strong>Operaciones hoy:</strong> {manager.operaciones_hoy} / {st.session_state.config['limite_diario']}</p>
        </div>
        """, unsafe_allow_html=True)

        if st.session_state.bot_activo and manager.estado not in ["Detenido", "Límite alcanzado"]:
            st.progress(0.5, text="Analizando mercado...")

        with st.expander("📋 Ver eventos recientes", expanded=True):
            for ev in manager.log_eventos[-10:]:
                st.markdown(f"<div class='evento'>{ev}</div>", unsafe_allow_html=True)

    with col2:
        st.markdown("### 📈 Resumen de operaciones")
        st.metric("Total operaciones", resumen['total'])
        st.metric("Ganadas", resumen['ganadas'])
        st.metric("Perdidas", resumen['perdidas'])
        st.metric("Ganancia neta", f"${resumen['neto']:.2f}")

    if manager.activo_actual:
        st.markdown("### 📉 Gráfico en tiempo real")
        df = st.session_state.connector.obtener_velas(manager.activo_actual, intervalo=5, limite=50)
        if df is not None:
            df = calcular_indicadores(df)
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                row_heights=[0.7, 0.3],
                                subplot_titles=(f"{manager.activo_actual}", "Volumen"))
            fig.add_trace(go.Candlestick(x=df.index,
                                          open=df['open'],
                                          high=df['high'],
                                          low=df['low'],
                                          close=df['close'],
                                          increasing_line_color='#00FF88',
                                          decreasing_line_color='#FF4646'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['ema_20'],
                                      line=dict(color='#2962FF', width=2), name="EMA 20"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['ema_50'],
                                      line=dict(color='#FFAA00', width=2), name="EMA 50"), row=1, col=1)
            soportes, resistencias = detectar_soportes_resistencias(df)
            for s in soportes:
                fig.add_hline(y=s, line_dash="dash", line_color="green", row=1, col=1)
            for r in resistencias:
                fig.add_hline(y=r, line_dash="dash", line_color="red", row=1, col=1)
            fig.add_trace(go.Bar(x=df.index, y=df['volume'],
                                  marker_color='#00FF88', name="Volumen"), row=2, col=1)
            fig.update_layout(height=500, template="plotly_dark", showlegend=False,
                              paper_bgcolor="#0A0C10", plot_bgcolor="#0A0C10")
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.markdown("""
        <div style="text-align:center; padding:50px; background:#151A24; border-radius:20px;">
            <i class="fas fa-chart-line" style="font-size:60px; color:#00FF88;"></i>
            <h3 style="color:#00FF88;">Esperando activo...</h3>
            <p>El bot está buscando el mejor activo para operar.</p>
        </div>
        """, unsafe_allow_html=True)

    with st.expander("📜 Ver historial completo de operaciones"):
        if manager.historial:
            df_hist = pd.DataFrame(manager.historial)
            st.dataframe(df_hist, use_container_width=True)
        else:
            st.info("Aún no hay operaciones registradas.")

    if st.button("🔄 Actualizar ahora", use_container_width=True):
        st.rerun()

if __name__ == "__main__":
    main()
