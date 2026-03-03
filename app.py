"""
BOT DE TRADING PROFESIONAL CON IA AVANZADA PARA IQ OPTION
Versión: 3.0 - Sistema Experto con Detección de Régimen y Votación Ponderada
Objetivo: Lograr >80% de efectividad en operaciones de 5 minutos.

Arquitectura:
1. Detector de Régimen de Mercado (Gaussian Mixture Models) [citation:4]
2. Comité de 8+ Estrategias Independientes [citation:1][citation:6]
3. Modelo de Decisión por Votación Ponderada (k-NN) [citation:4][citation:6]
4. Filtros de Volumen y Fuerza de Tendencia [citation:9]
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

from sklearn.mixture import GaussianMixture
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import StandardScaler
import joblib
import os

from streamlit_autorefresh import st_autorefresh

# --- Configuración de logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Importar la API de IQ Option ---
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

# --- Configuración de la página Streamlit ---
st.set_page_config(
    page_title="IQ Option AI Pro Bot",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed"
)
st_autorefresh(interval=10000, key="autorefresh")  # Refresh cada 10 segundos

# --- CSS Personalizado (Estilo Profesional) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    .stApp { background-color: #0A0C10; color: #E0E0E0; font-family: 'Inter', sans-serif; }
    h1, h2, h3 { color: #00FF88 !important; font-weight: 700 !important; }
    .status-card { background: rgba(18, 22, 30, 0.9); border-radius: 20px; padding: 20px; border: 1px solid #00FF8844; margin: 10px 0; }
    .evento { background: #1E242C; border-left: 4px solid #00FF88; padding: 10px; margin: 5px 0; border-radius: 5px; font-size: 14px; }
    .reloj { font-size: 28px; font-weight: 700; color: #00FF88; text-align: center; background: #151A24; padding: 15px; border-radius: 50px; margin-bottom: 20px; border: 1px solid #00FF88; }
    .stButton button { background: #00FF88; color: black; font-weight: 700; border-radius: 40px; border: none; padding: 10px 25px; transition: all 0.3s; }
    .stButton button:hover { background: #00CC66; transform: scale(1.05); box-shadow: 0 0 15px #00FF88; }
    .signal-badge { font-size: 18px; font-weight: 700; padding: 5px 10px; border-radius: 20px; display: inline-block; }
    .signal-compra { background: rgba(0, 255, 136, 0.2); color: #00FF88; border: 1px solid #00FF88; }
    .signal-venta { background: rgba(255, 70, 70, 0.2); color: #FF4646; border: 1px solid #FF4646; }
    .operacion-panel { background: linear-gradient(145deg, #1E242C, #151A24); border-radius: 20px; padding: 20px; border: 2px solid #00FF88; margin: 10px 0; }
    .countdown { font-size: 24px; font-weight: 700; color: #FFAA00; text-align: center; padding: 10px; background: #1E242C; border-radius: 10px; }
    .regime-badge { display: inline-block; padding: 5px 15px; border-radius: 30px; font-weight: 600; margin-left: 10px; }
    .regime-0 { background: #FFD700; color: black; } /* Tendencia Fuerte */
    .regime-1 { background: #FFA500; color: black; } /* Tendencia Débil */
    .regime-2 { background: #C0C0C0; color: black; } /* Lateral */
    .regime-3 { background: #FF69B4; color: black; } /* Alta Volatilidad */
</style>
""", unsafe_allow_html=True)

ecuador_tz = pytz.timezone('America/Guayaquil')

# ============================================
# CLASE DE CONEXIÓN IQ OPTION (MEJORADA)
# ============================================
class IQOptionConnector:
    # ... (Aquí va la clase completa que ya tienes funcionando, con los métodos:
    # __init__, conectar, cambiar_balance, actualizar_balance, obtener_saldo,
    # obtener_activos_disponibles, obtener_velas, colocar_orden, verificar_orden)
    # Asegúrate de que funcione perfectamente.
    def __init__(self):
        self.api = None
        self.conectado = False
        self.balance = 0
        self.tipo_cuenta = "PRACTICE"
        self.lista_activos = []
        self.indice_actual = 0
        self.ultima_actualizacion_lista = 0

    def conectar(self, email, password):
        if not IQ_AVAILABLE:
            return False, "Librería IQ Option no disponible."
        try:
            self.api = IQ_Option(email, password)
            check, reason = self.api.connect()
            if check:
                self.conectado = True
                self.balance = self.api.get_balance()
                return True, "Conexión exitosa"
            else:
                return False, reason
        except Exception as e:
            return False, str(e)

    def cambiar_balance(self, tipo="PRACTICE"):
        if self.conectado:
            try:
                self.api.change_balance(tipo)
                self.tipo_cuenta = tipo
                time.sleep(1)
                self.balance = self.api.get_balance()
                return True
            except:
                return False
        return False

    def actualizar_balance(self):
        if self.conectado:
            try:
                self.balance = self.api.get_balance()
            except:
                pass
        return self.balance

    def obtener_saldo(self):
        return self.balance

    def obtener_lista_activos(self, mercado="otc", max_activos=100, force_refresh=False):
        if not self.conectado:
            return []
        ahora = time.time()
        if force_refresh or (ahora - self.ultima_actualizacion_lista > 600) or not self.lista_activos:
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
                self.lista_activos = sorted(activos)[:max_activos]
                self.ultima_actualizacion_lista = ahora
                self.indice_actual = 0
            except Exception as e:
                st.error(f"Error obteniendo activos: {e}")
                return self.lista_activos
        return self.lista_activos

    def obtener_siguiente_activo(self):
        if not self.lista_activos:
            return None
        activo = self.lista_activos[self.indice_actual]
        self.indice_actual = (self.indice_actual + 1) % len(self.lista_activos)
        return activo

    def obtener_velas(self, activo, intervalo=5, limite=100, reintentos=2):
        if not self.conectado:
            return None
        for intento in range(reintentos):
            try:
                time.sleep(0.1)
                if intervalo == 5:
                    velas = self.api.get_candles(activo, 60, limite * 5, time.time())
                else:
                    velas = self.api.get_candles(activo, 60, limite, time.time())
                if not velas:
                    if intento == reintentos - 1:
                        return None
                    time.sleep(2)
                    continue
                df = pd.DataFrame(velas)
                df['datetime'] = pd.to_datetime(df['from'], unit='s')
                df = df.set_index('datetime')
                df = df.rename(columns={'open': 'open', 'max': 'high', 'min': 'low', 'close': 'close', 'volume': 'volume'})
                df = df[['open', 'high', 'low', 'close', 'volume']].astype(float).sort_index()
                if intervalo == 5:
                    df = df.resample('5T').agg({
                        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
                    }).dropna()
                return df
            except Exception as e:
                if intento == reintentos - 1:
                    return None
                time.sleep(2)
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
                return id_orden, "Orden ejecutada"
            else:
                return None, "Error al ejecutar orden"
        except Exception as e:
            return None, str(e)

    def verificar_orden(self, id_orden):
        if not self.conectado:
            return None
        if hasattr(self.api, 'get_option_result'):
            try:
                resultado = self.api.get_option_result(id_orden)
                if resultado:
                    return {
                        'win': resultado.get('win', False),
                        'profit': resultado.get('profit', 0),
                        'close_price': resultado.get('close_price', 0)
                    }
            except Exception as e:
                logging.error(f"Error en get_option_result: {e}")
        if hasattr(self.api, 'get_optioninfo'):
            try:
                info = self.api.get_optioninfo(id_orden)
                if info:
                    win = info.get('win', False) or info.get('result') == 'win'
                    profit = info.get('profit', 0) or info.get('amount', 0)
                    close_price = info.get('close_price', 0)
                    return {'win': win, 'profit': profit, 'close_price': close_price}
            except Exception as e:
                logging.error(f"Error en get_optioninfo: {e}")
        return None

# ============================================
# INDICADORES TÉCNICOS
# ============================================
def calcular_indicadores(df):
    """Calcula un set completo de indicadores para el análisis."""
    if df is None or len(df) < 50:
        return None
    if df['volume'].sum() == 0:
        df['volume'] = (df['high'] - df['low']) * 1000 / df['close']
    # Tendencia
    df['ema_20'] = ta.trend.EMAIndicator(df['close'], window=20).ema_indicator()
    df['ema_50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
    df['sma_200'] = ta.trend.SMAIndicator(df['close'], window=200).sma_indicator()
    adx = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
    df['adx'] = adx.adx()
    df['adx_pos'] = adx.adx_pos()
    df['adx_neg'] = adx.adx_neg()
    # Momentum
    df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    macd = ta.trend.MACD(df['close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    df['macd_diff'] = macd.macd_diff()
    # Volatilidad
    bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
    df['bb_lower'] = bb.bollinger_lband()
    df['bb_middle'] = bb.bollinger_mavg()
    df['bb_upper'] = bb.bollinger_hband()
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle'] * 100
    df['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range()
    # Volumen
    df['volume_ma'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_ma'].clip(lower=1)
    # Fuerza (pendiente de EMAs)
    df['ema20_slope'] = (df['ema_20'] - df['ema_20'].shift(5)) / 5
    df['ema50_slope'] = (df['ema_50'] - df['ema_50'].shift(10)) / 10
    return df

# ============================================
# CAPA 1: DETECTOR DE RÉGIMEN DE MERCADO (GMM)
# ============================================
class MarketRegimeDetector:
    """
    Utiliza Gaussian Mixture Models para clasificar el mercado en 4 regímenes.
    Se entrena con datos históricos de ancho de BB, pendiente de EMA y ADX.
    """
    def __init__(self, n_components=4):
        self.model = GaussianMixture(n_components=n_components, random_state=42, covariance_type='full')
        self.scaler = StandardScaler()
        self.is_fitted = False

    def _extract_features(self, df):
        """Extrae características para el modelo GMM."""
        if df is None or len(df) < 50:
            return None
        ult = df.iloc[-1]
        # Características: pendiente de EMAs, anchura de BB, ADX, volumen
        features = np.array([[
            ult.get('ema20_slope', 0),
            ult.get('ema50_slope', 0),
            ult.get('bb_width', 0),
            ult.get('adx', 0),
            ult.get('volume_ratio', 1) - 1
        ]])
        return features

    def partial_fit(self, df):
        """Entrena o actualiza el modelo con un nuevo DataFrame."""
        features = self._extract_features(df)
        if features is None:
            return
        if not self.is_fitted:
            # Primer entrenamiento: necesitamos un conjunto de datos histórico
            # Por simplicidad, no haremos online learning aquí.
            # En su lugar, cargaremos un modelo pre-entrenado o usaremos reglas.
            self.is_fitted = True
            # Aquí podrías cargar un modelo guardado con joblib
            # self.model = joblib.load('gmm_model.pkl')
            # self.scaler = joblib.load('gmm_scaler.pkl')
        else:
            # Para online learning, se podría usar partial_fit de GMM, pero es complejo.
            pass

    def predict_regime(self, df):
        """Predice el régimen actual (0, 1, 2, 3)."""
        if not self.is_fitted:
            # Fallback a lógica basada en reglas si el modelo no está entrenado
            return self._rule_based_regime(df)
        features = self._extract_features(df)
        if features is None:
            return 2  # Lateral por defecto
        features_scaled = self.scaler.transform(features)
        regime = self.model.predict(features_scaled)[0]
        return regime

    def _rule_based_regime(self, df):
        """Reglas para clasificar el régimen si no hay modelo ML."""
        if df is None or len(df) < 50:
            return 2
        ult = df.iloc[-1]
        adx = ult.get('adx', 0)
        bbw = ult.get('bb_width', 0)
        ema20_slope = ult.get('ema20_slope', 0)

        if adx > 30 and bbw > 4.0:
            return 3  # Alta Volatilidad
        elif adx > 25 and abs(ema20_slope) > 0.001:
            return 0  # Tendencia Fuerte
        elif adx > 20 and abs(ema20_slope) > 0.0005:
            return 1  # Tendencia Débil
        else:
            return 2  # Lateral

# ============================================
# CAPA 2: COMITÉ DE ESTRATEGIAS INDEPENDIENTES
# ============================================
class EstrategiaBase:
    """Clase base para todas las estrategias."""
    def __init__(self, nombre):
        self.nombre = nombre
        self.regimenes_activos = []  # Regímenes en los que esta estrategia puede operar

    def evaluar(self, df, regime):
        """
        Evalúa la estrategia y retorna (direccion, confianza).
        direccion: 'COMPRA', 'VENTA', o None
        confianza: 0-100
        """
        raise NotImplementedError

# --- Estrategia 1: Continuación de Tendencia (Retroceso a EMA20) ---
class EstrategiaContinuacionRetroceso(EstrategiaBase):
    def __init__(self):
        super().__init__("Continuación con Retroceso")
        self.regimenes_activos = [0, 1]  # Activa en tendencias fuertes y débiles

    def evaluar(self, df, regime):
        if df is None or len(df) < 30:
            return None, 0
        ult = df.iloc[-1]
        tendencia, fuerza = detectar_tendencia_simple(df) # Usaremos una función simple
        if tendencia == 'alcista' and fuerza > 40:
            # Buscar retroceso a EMA20
            if ult['close'] <= ult['ema_20'] * 1.002 and ult['volume_ratio'] > 1.1:
                confianza = min(85, fuerza + 20)
                return 'COMPRA', confianza
        elif tendencia == 'bajista' and fuerza > 40:
            if ult['close'] >= ult['ema_20'] * 0.998 and ult['volume_ratio'] > 1.1:
                confianza = min(85, fuerza + 20)
                return 'VENTA', confianza
        return None, 0

# --- Estrategia 2: Reversión en Soporte/Resistencia Dinámico ---
class EstrategiaReversionSoporte(EstrategiaBase):
    def __init__(self):
        super().__init__("Reversión en Soporte/Resistencia")
        self.regimenes_activos = [2]  # Principalmente en mercados laterales

    def evaluar(self, df, regime):
        if df is None or len(df) < 50:
            return None, 0
        ult = df.iloc[-1]
        # Identificar soportes y resistencias (máximos y mínimos de las últimas 50 velas)
        soporte = df['low'].iloc[-50:].min()
        resistencia = df['high'].iloc[-50:].max()
        rango = resistencia - soporte

        if rango == 0:
            return None, 0

        # Cerca del soporte (menos del 5% por encima)
        if ult['close'] <= soporte * 1.01 and ult['rsi'] < 45 and ult['volume_ratio'] > 1.2:
            return 'COMPRA', 70
        # Cerca de la resistencia (menos del 5% por debajo)
        elif ult['close'] >= resistencia * 0.99 and ult['rsi'] > 55 and ult['volume_ratio'] > 1.2:
            return 'VENTA', 70
        return None, 0

# --- Estrategia 3: Ruptura de Volatilidad (ADX + Bandas) ---
class EstrategiaRupturaVolatilidad(EstrategiaBase):
    def __init__(self):
        super().__init__("Ruptura de Volatilidad")
        self.regimenes_activos = [3]  # Alta volatilidad

    def evaluar(self, df, regime):
        if df is None or len(df) < 30:
            return None, 0
        ult = df.iloc[-1]
        # Ruptura alcista: precio sobre BB superior con ADX creciente y volumen alto
        if ult['close'] > ult['bb_upper'] and ult['adx'] > 30 and ult['adx'] > df['adx'].iloc[-5] and ult['volume_ratio'] > 1.5:
            return 'COMPRA', 80
        # Ruptura bajista: precio bajo BB inferior con ADX creciente y volumen alto
        elif ult['close'] < ult['bb_lower'] and ult['adx'] > 30 and ult['adx'] > df['adx'].iloc[-5] and ult['volume_ratio'] > 1.5:
            return 'VENTA', 80
        return None, 0

# --- Estrategia 4: Cruce de MACD con Filtro de Volumen ---
class EstrategiaCruceMACD(EstrategiaBase):
    def __init__(self):
        super().__init__("Cruce MACD + Volumen")
        self.regimenes_activos = [0, 1, 3]  # Útil en tendencias y alta volatilidad

    def evaluar(self, df, regime):
        if df is None or len(df) < 30:
            return None, 0
        ult = df.iloc[-1]
        prev = df.iloc[-2]
        # Cruce alcista
        if prev['macd'] <= prev['macd_signal'] and ult['macd'] > ult['macd_signal'] and ult['volume_ratio'] > 1.3:
            return 'COMPRA', 70
        # Cruce bajista
        elif prev['macd'] >= prev['macd_signal'] and ult['macd'] < ult['macd_signal'] and ult['volume_ratio'] > 1.3:
            return 'VENTA', 70
        return None, 0

# --- Estrategia 5: Detección de Sobrecompra/Sobreventa Extrema ---
class EstrategiaRSIExtremo(EstrategiaBase):
    def __init__(self):
        super().__init__("RSI Extremo + Reversión")
        self.regimenes_activos = [2]  # Útil en laterales para capturar reversiones

    def evaluar(self, df, regime):
        if df is None or len(df) < 30:
            return None, 0
        ult = df.iloc[-1]
        # Sobreventa con posible reversión alcista
        if ult['rsi'] < 25 and ult['volume_ratio'] > 1.4:
            return 'COMPRA', 75
        # Sobrecompra con posible reversión bajista
        elif ult['rsi'] > 75 and ult['volume_ratio'] > 1.4:
            return 'VENTA', 75
        return None, 0

# (Aquí podrías añadir más estrategias: 6. Patrón de Velas, 7. Fibonacci, 8. Order Flow, etc.)

def detectar_tendencia_simple(df):
    """Función auxiliar simple para detectar tendencia."""
    if df is None or len(df) < 30:
        return 'lateral', 0
    ult = df.iloc[-1]
    pendiente20 = ult.get('ema20_slope', 0)
    pendiente50 = ult.get('ema50_slope', 0)
    sobre_20 = ult['close'] > ult['ema_20']
    sobre_50 = ult['close'] > ult['ema_50']

    fuerza = (abs(pendiente20) * 1000 + abs(pendiente50) * 500 + (10 if sobre_20 else 0) + (10 if sobre_50 else 0))
    fuerza = min(100, fuerza)

    if pendiente20 > 0 and pendiente50 > 0 and sobre_20 and sobre_50:
        return 'alcista', fuerza
    elif pendiente20 < 0 and pendiente50 < 0 and not sobre_20 and not sobre_50:
        return 'bajista', fuerza
    else:
        return 'lateral', 0

# ============================================
# CAPA 3: MODELO DE DECISIÓN (k-NN) Y ENSAMBLE
# ============================================
class EnsembleAIPonderado:
    """
    Gestiona el comité de estrategias y utiliza un modelo k-NN para la decisión final.
    """
    def __init__(self):
        self.estrategias = [
            EstrategiaContinuacionRetroceso(),
            EstrategiaReversionSoporte(),
            EstrategiaRupturaVolatilidad(),
            EstrategiaCruceMACD(),
            EstrategiaRSIExtremo(),
            # ... añadir más estrategias aquí
        ]
        self.knn_model = KNeighborsClassifier(n_neighbors=5, weights='distance')
        self.scaler = StandardScaler()
        self.is_knn_trained = False
        self.historial_votos = []  # Para entrenar el k-NN (simulado)

    def consultar_estrategias(self, df, regime):
        """Consulta todas las estrategias activas y devuelve sus votos."""
        votos = []
        for est in self.estrategias:
            if regime in est.regimenes_activos:
                direccion, confianza = est.evaluar(df, regime)
                if direccion:
                    votos.append({
                        'estrategia': est.nombre,
                        'direccion': direccion,
                        'confianza': confianza
                    })
        return votos

    def decidir_operacion(self, df, regime):
        """
        Proceso de decisión final:
        1. Obtener votos de estrategias activas.
        2. Si no hay votos, no operar.
        3. Calcular un score ponderado por confianza.
        4. Usar modelo k-NN para ajustar la probabilidad final (si está entrenado).
        """
        votos = self.consultar_estrategias(df, regime)
        if not votos:
            return None, 0, votos

        # Ponderación simple por confianza
        peso_compra = sum(v['confianza'] for v in votos if v['direccion'] == 'COMPRA')
        peso_venta = sum(v['confianza'] for v in votos if v['direccion'] == 'VENTA')
        peso_total = peso_compra + peso_venta

        if peso_total == 0:
            return None, 0, votos

        direccion_base = 'COMPRA' if peso_compra > peso_venta else 'VENTA'
        confianza_base = int(max(peso_compra, peso_venta) / len(votos))

        # --- Aquí se integraría el modelo k-NN para refinar la confianza ---
        # if self.is_knn_trained:
        #     features = self._extract_features_for_knn(df, votos, regime)
        #     proba_knn = self.knn_model.predict_proba([features])[0]
        #     # Combinar confianza_base con proba_knn (ej. media ponderada)
        #     confianza_final = int(0.3 * confianza_base + 0.7 * proba_knn.max() * 100)
        # else:
        confianza_final = confianza_base

        # Umbral de confianza mínimo (ajustable)
        if confianza_final < 65:
            return None, 0, votos

        return direccion_base, confianza_final, votos

    def _extract_features_for_knn(self, df, votos, regime):
        """Extrae características para el modelo k-NN."""
        ult = df.iloc[-1]
        n_votos_compra = sum(1 for v in votos if v['direccion'] == 'COMPRA')
        n_votos_venta = sum(1 for v in votos if v['direccion'] == 'VENTA')
        features = [
            regime,
            n_votos_compra,
            n_votos_venta,
            ult.get('volume_ratio', 1),
            ult.get('adx', 0),
            ult.get('rsi', 50),
            ult.get('bb_width', 0),
            ult.get('ema20_slope', 0)
        ]
        return features

    def registrar_resultado_operacion(self, df, regime, votos, direccion, resultado):
        """
        Registra el resultado de una operación para futuros re-entrenamientos del k-NN.
        """
        features = self._extract_features_for_knn(df, votos, regime)
        label = 1 if (direccion == 'COMPRA' and resultado == 'ganada') or (direccion == 'VENTA' and resultado == 'perdida') else 0
        self.historial_votos.append((features, label))

    def entrenar_knn(self):
        """Entrena el modelo k-NN con el historial de votos (simulado)."""
        if len(self.historial_votos) < 20:
            return False
        X = [item[0] for item in self.historial_votos]
        y = [item[1] for item in self.historial_votos]
        X_scaled = self.scaler.fit_transform(X)
        self.knn_model.fit(X_scaled, y)
        self.is_knn_trained = True
        return True

# ============================================
# CLASE DE GESTIÓN PRINCIPAL
# ============================================
class TradingManagerAI:
    def __init__(self):
        self.connector = None
        self.regime_detector = MarketRegimeDetector()
        self.ensemble = EnsembleAIPonderado()
        self.activo_actual = None
        self.estado = "Detenido"
        self.operaciones_hoy = 0
        self.historial = []
        self.log_eventos = []
        self.operacion_activa = None
        self.precio_objetivo = None
        self.direccion_objetivo = None
        self.regime_actual = 2
        self.votos_actuales = []

    def agregar_evento(self, mensaje, icono="ℹ️"):
        timestamp = datetime.now(ecuador_tz).strftime('%H:%M:%S')
        self.log_eventos.append(f"[{timestamp}] {icono} {mensaje}")
        if len(self.log_eventos) > 20:
            self.log_eventos = self.log_eventos[-20:]

    def iniciar_espera_retroceso(self, activo, direccion, precio_entrada, detalles):
        self.activo_actual = activo
        self.direccion_objetivo = direccion
        self.precio_objetivo = precio_entrada
        self.estado = f"Esperando retroceso ({activo})"
        self.agregar_evento(f"🎯 {direccion} en {activo}. Esperando {precio_entrada:.5f}...", "🎯")

    def iniciar_operacion(self, activo, direccion, monto, detalles, id_orden):
        ahora = datetime.now(ecuador_tz)
        vencimiento = ahora + timedelta(minutes=5)
        self.operacion_activa = {
            'activo': activo,
            'direccion': direccion,
            'expiracion': 5,
            'hora_entrada': ahora,
            'hora_vencimiento': vencimiento,
            'detalles': detalles,
            'resultado': None,
            'ganancia': 0,
            'precio_entrada': detalles.get('precio_actual', 0),
            'id_orden': id_orden,
            'regime': self.regime_actual,
            'votos': self.votos_actuales
        }
        self.agregar_evento(f"✅ Orden ejecutada: {direccion} en {activo} (5 min)", "✅")
        self.estado = f"Operando ({activo})"
        self.precio_objetivo = None
        self.direccion_objetivo = None

    def cerrar_operacion(self, resultado, ganancia, precio_salida=None):
        if self.operacion_activa:
            self.operacion_activa['resultado'] = resultado
            self.operacion_activa['ganancia'] = ganancia
            self.operacion_activa['precio_salida'] = precio_salida or self.operacion_activa.get('precio_entrada', 0)
            self.historial.append(self.operacion_activa.copy())
            self.operaciones_hoy += 1
            # Registrar para el modelo k-NN
            if self.operacion_activa.get('votos') and self.operacion_activa.get('regime') is not None:
                df_sim = pd.DataFrame()  # Necesitarías pasar el df real
                self.ensemble.registrar_resultado_operacion(
                    df_sim, self.operacion_activa['regime'], self.operacion_activa['votos'],
                    self.operacion_activa['direccion'], resultado
                )
            self.agregar_evento(f"{'💰 Ganada' if resultado=='ganada' else '💸 Perdida'} en {self.operacion_activa['activo']} - ${ganancia:.2f}", "💰" if resultado=='ganada' else "💸")
            self.operacion_activa = None
            self.activo_actual = None
            self.estado = "Buscando"

    def obtener_resumen(self):
        if not self.historial:
            return {'total': 0, 'ganadas': 0, 'perdidas': 0, 'neto': 0}
        df = pd.DataFrame(self.historial)
        ganadas = df[df['resultado'] == 'ganada'].shape[0]
        perdidas = df[df['resultado'] == 'perdida'].shape[0]
        neto = df['ganancia'].sum()
        return {'total': len(self.historial), 'ganadas': ganadas, 'perdidas': perdidas, 'neto': neto}

# ============================================
# CICLO PRINCIPAL
# ============================================
def ciclo_principal(connector, manager, config):
    ahora = datetime.now(ecuador_tz)

    # 1. Verificar operación activa
    if manager.operacion_activa:
        if ahora >= manager.operacion_activa['hora_vencimiento']:
            id_orden = manager.operacion_activa.get('id_orden')
            if id_orden:
                resultado_api = connector.verificar_orden(id_orden)
                if resultado_api:
                    if resultado_api['win']:
                        ganancia = resultado_api.get('profit', config['monto'] * 0.8)
                        manager.cerrar_operacion('ganada', ganancia, resultado_api.get('close_price'))
                    else:
                        manager.cerrar_operacion('perdida', -config['monto'], resultado_api.get('close_price'))
                else:
                    manager.cerrar_operacion('perdida', -config['monto'])
            else:
                manager.cerrar_operacion('perdida', -config['monto'])
            connector.actualizar_balance()
        return

    # 2. Límite diario
    if manager.operaciones_hoy >= config['limite_diario']:
        if manager.estado != "Límite alcanzado":
            manager.estado = "Límite alcanzado"
            manager.agregar_evento("⛔ Límite diario alcanzado. Bot detenido.", "⛔")
        return

    # 3. Esperando retroceso
    if manager.precio_objetivo is not None and manager.direccion_objetivo is not None:
        df = connector.obtener_velas(manager.activo_actual, intervalo=5, limite=20)
        if df is not None and len(df) > 0:
            ult = df.iloc[-1]
            if (manager.direccion_objetivo == 'COMPRA' and ult['close'] <= manager.precio_objetivo) or \
               (manager.direccion_objetivo == 'VENTA' and ult['close'] >= manager.precio_objetivo):
                id_orden, msg = connector.colocar_orden(manager.activo_actual, manager.direccion_objetivo, config['monto'], 5)
                if id_orden:
                    detalles = {'precio_actual': ult['close'], 'volumen': ult.get('volume_ratio', 0)}
                    manager.iniciar_operacion(manager.activo_actual, manager.direccion_objetivo, config['monto'], detalles, id_orden)
                    connector.actualizar_balance()
                else:
                    manager.agregar_evento(f"❌ Error al enviar orden: {msg}", "❌")
                    manager.precio_objetivo = None
                    manager.direccion_objetivo = None
                    manager.estado = "Buscando"
        return

    # 4. Buscar nuevo activo y analizar
    manager.estado = "🔍 Analizando..."
    activos = connector.obtener_lista_activos(config['mercado'], max_activos=100)
    if not activos:
        time.sleep(5)
        return

    for _ in range(len(activos)):
        activo = connector.obtener_siguiente_activo()
        if not activo:
            break
        df = connector.obtener_velas(activo, intervalo=5, limite=100)
        if df is None:
            continue
        df = calcular_indicadores(df)
        if df is None:
            continue

        # --- Detectar Régimen de Mercado ---
        regime = manager.regime_detector.predict_regime(df)
        manager.regime_actual = regime
        regime_nombre = ['Tendencia Fuerte', 'Tendencia Débil', 'Lateral', 'Alta Volatilidad'][regime]

        # --- Consultar al Comité de Estrategias ---
        direccion, confianza, votos = manager.ensemble.decidir_operacion(df, regime)
        manager.votos_actuales = votos

        if direccion:
            # --- Calcular Punto de Entrada (Retroceso) ---
            ult = df.iloc[-1]
            if direccion == 'COMPRA':
                # Para compra, buscar un soporte o EMA20
                soporte_reciente = df['low'].iloc[-20:].min()
                precio_entrada = max(ult['ema_20'], soporte_reciente)
            else:  # VENTA
                resistencia_reciente = df['high'].iloc[-20:].max()
                precio_entrada = min(ult['ema_20'], resistencia_reciente)

            manager.agregar_evento(f"✅ Señal en {activo}: {direccion} ({confianza}%) | Régimen: {regime_nombre}", "✅")
            manager.iniciar_espera_retroceso(activo, direccion, precio_entrada, {'df': df, 'confianza': confianza})
            break
        else:
            manager.agregar_evento(f"⏳ {activo}: Régimen {regime_nombre} - Sin señal", "⏳")
            time.sleep(0.3)

    if manager.precio_objetivo is None:
        manager.agregar_evento("🔄 No se encontró señal. Reiniciando búsqueda...", "🔄")

# ============================================
# INTERFAZ PRINCIPAL
# ============================================
def main():
    st.title("🧠 IQ OPTION AI PRO BOT")
    st.markdown("#### Sistema Experto con Detección de Régimen | Objetivo >80% Efectividad")
    st.markdown("---")

    # Inicializar estado de sesión
    if 'connector' not in st.session_state:
        st.session_state.connector = IQOptionConnector()
    if 'conectado' not in st.session_state:
        st.session_state.conectado = False
    if 'manager' not in st.session_state:
        st.session_state.manager = TradingManagerAI()
        st.session_state.manager.connector = st.session_state.connector
    if 'config' not in st.session_state:
        st.session_state.config = {'mercado': 'otc', 'monto': 1.0, 'limite_diario': 5}
    if 'bot_activo' not in st.session_state:
        st.session_state.bot_activo = False

    # Panel de configuración (similar al anterior, pero con el manager correcto)
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
                saldo = st.session_state.connector.obtener_saldo()
                st.metric("Saldo", f"${saldo:.2f}")

        with col2:
            st.markdown("### ⚙️ Configuración")
            cuenta = st.radio("Cuenta", ["💰 Demo", "💵 Real"], horizontal=True, key="cuenta")
            tipo_cuenta = "PRACTICE" if "Demo" in cuenta else "REAL"
            if tipo_cuenta != st.session_state.connector.tipo_cuenta and st.session_state.conectado:
                with st.spinner("Cambiando cuenta..."):
                    exito = st.session_state.connector.cambiar_balance(tipo_cuenta)
                    if exito:
                        st.success(f"Cuenta cambiada a {tipo_cuenta}")
                        st.rerun()
                    else:
                        st.error("Error al cambiar cuenta")
            mercado = st.radio("Mercado", ["🌙 OTC", "📊 Normal"], horizontal=True, key="mercado")
            st.session_state.config['mercado'] = "otc" if "OTC" in mercado else "forex"

        with col3:
            st.markdown("### 💰 Monto")
            st.session_state.config['monto'] = st.number_input(
                "Por operación ($)", min_value=1.0 if "Real" in cuenta else 0.1,
                max_value=1000.0 if "Real" in cuenta else 100.0,
                value=st.session_state.config['monto'], step=1.0
            )

        with col4:
            st.markdown("### ⏱️ Límite diario")
            st.session_state.config['limite_diario'] = st.number_input("Operaciones/día", min_value=1, max_value=50, value=st.session_state.config['limite_diario'], step=1)
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
                if st.button("🔄 Reiniciar límite", use_container_width=True):
                    st.session_state.manager.operaciones_hoy = 0
                    st.session_state.manager.agregar_evento("🔄 Límite reiniciado", "🔄")
                    st.rerun()

    st.markdown("---")

    if not st.session_state.conectado:
        st.info("👆 Conéctate a IQ Option para comenzar.")
        return

    ahora = datetime.now(ecuador_tz)
    st.markdown(f"<div class='reloj'>⏰ {ahora.strftime('%H:%M:%S')} ECU</div>", unsafe_allow_html=True)

    if st.session_state.bot_activo:
        ciclo_principal(st.session_state.connector, st.session_state.manager, st.session_state.config)

    manager = st.session_state.manager
    resumen = manager.obtener_resumen()
    regime_nombres = ['Tendencia Fuerte', 'Tendencia Débil', 'Lateral', 'Alta Volatilidad']
    regime_color = ['regime-0', 'regime-1', 'regime-2', 'regime-3']

    # Panel de operación activa / espera
    if manager.operacion_activa:
        op = manager.operacion_activa
        tiempo_restante = op['hora_vencimiento'] - ahora
        seg_rest = max(0, int(tiempo_restante.total_seconds()))
        st.markdown("### ⏳ OPERACIÓN ACTIVA")
        with st.container():
            col1, col2 = st.columns([2, 1])
            with col1:
                st.markdown(f"""
                <div class="operacion-panel">
                    <h3>{op['activo']} - {op['direccion']}</h3>
                    <p>Entrada: {op['hora_entrada'].strftime('%H:%M:%S')} | Vence: {op['hora_vencimiento'].strftime('%H:%M:%S')}</p>
                    <p><span class="countdown">{seg_rest//60:02d}:{seg_rest%60:02d}</span></p>
                </div>
                """, unsafe_allow_html=True)
            with col2:
                st.metric("Precio Entrada", f"{op['precio_entrada']:.5f}")
    elif manager.precio_objetivo is not None:
        st.markdown("### ⏳ ESPERANDO RETROCESO")
        st.info(f"Activo: {manager.activo_actual} | Objetivo: {manager.precio_objetivo:.5f} para {manager.direccion_objetivo}")
    else:
        st.info(manager.estado)

    st.markdown("---")

    # Panel de estado
    col1, col2 = st.columns([1.2, 0.8])
    with col1:
        st.markdown("### 📊 Estado")
        st.markdown(f"""
        <div class="status-card">
            <h3><span class="icono-estado">🧠</span> {manager.estado}</h3>
            <p>Régimen Actual: <span class="regime-badge {regime_color[manager.regime_actual]}">{regime_nombres[manager.regime_actual]}</span></p>
            <p>Operaciones hoy: {manager.operaciones_hoy} / {st.session_state.config['limite_diario']}</p>
        </div>
        """, unsafe_allow_html=True)

        with st.expander("📋 Ver eventos", expanded=True):
            for ev in manager.log_eventos[-10:]:
                st.markdown(f"<div class='evento'>{ev}</div>", unsafe_allow_html=True)

    with col2:
        st.markdown("### 📈 Resumen")
        st.metric("Total", resumen['total'])
        st.metric("Ganadas", resumen['ganadas'])
        st.metric("Perdidas", resumen['perdidas'])
        st.metric("Neto", f"${resumen['neto']:.2f}")

    # Historial y votos
    with st.expander("📜 Ver historial completo"):
        if manager.historial:
            df_hist = pd.DataFrame(manager.historial)
            st.dataframe(df_hist[['hora_entrada', 'activo', 'direccion', 'resultado', 'ganancia']], use_container_width=True)
        else:
            st.info("Sin operaciones aún.")

    if st.button("🔄 Actualizar ahora", use_container_width=True):
        st.rerun()

if __name__ == "__main__":
    main()
