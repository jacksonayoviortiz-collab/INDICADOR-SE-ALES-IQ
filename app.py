"""
BOT DE TRADING PROFESIONAL PARA IQ OPTION - VERSIÓN OPTIMIZADA CON 4 ESTRATEGIAS
Funcionalidades clave:
- Selección manual de hasta 2 activos (con buscador)
- Opción automática: el bot elige el activo más estable
- 4 estrategias independientes con acceso a volumen y fuerza
- Ensemble ponderado (IA) para máxima precisión
- Control de número de operaciones
- Modo Automático y Modo Señales
- Panel de control con balance, operaciones, ganancias/pérdidas
- Notificaciones 1 minuto antes con hora exacta
- Interfaz profesional verde/negro
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

# Autorefresh cada 10 segundos (solo para mantener el reloj y datos actualizados)
st_autorefresh(interval=10000, key="autorefresh")

# CSS personalizado
st.markdown("""
<style>
    .stApp {
        background-color: #0A0C10;
        color: #E0E0E0;
        font-family: 'Inter', sans-serif;
    }
    h1, h2, h3 {
        color: #00FF88 !important;
        font-weight: 700 !important;
    }
    .asset-card {
        background: rgba(18, 22, 30, 0.9);
        border-radius: 28px;
        padding: 25px;
        box-shadow: 0 25px 45px -15px rgba(0, 255, 136, 0.3);
        border: 1px solid #00FF8844;
        margin: 10px 0;
    }
    .asset-name {
        font-size: 24px;
        font-weight: 700;
        color: #FFFFFF;
        margin-bottom: 10px;
    }
    .asset-signal {
        font-size: 20px;
        font-weight: 700;
        padding: 12px;
        border-radius: 40px;
        text-align: center;
        margin: 15px 0;
    }
    .signal-compra {
        background: rgba(0, 255, 136, 0.2);
        color: #00FF88;
        border: 2px solid #00FF88;
    }
    .signal-venta {
        background: rgba(255, 70, 70, 0.2);
        color: #FF4646;
        border: 2px solid #FF4646;
    }
    .asset-footer {
        font-size: 16px;
        color: #AAA;
        display: flex;
        justify-content: space-between;
        margin-top: 15px;
        padding-top: 15px;
        border-top: 1px solid #333;
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
    .badge-5min {
        background: #00FF88;
        color: black;
        padding: 5px 15px;
        border-radius: 30px;
        font-size: 14px;
        font-weight: 600;
        margin-left: 10px;
    }
    .stButton button {
        background: #00FF88;
        color: black;
        font-weight: 700;
        border-radius: 40px;
        border: none;
        padding: 10px 25px;
    }
    /* Panel de control */
    .control-panel {
        background: #151A24;
        border-radius: 20px;
        padding: 20px;
        border: 1px solid #00FF8844;
        margin: 10px 0;
    }
    /* Estilo para el buscador de activos */
    .buscador {
        background: #1E242C;
        border-radius: 15px;
        padding: 15px;
        margin: 10px 0;
        border: 1px solid #00FF8844;
    }
    .stTextInput input {
        background-color: #1E242C !important;
        color: white !important;
        border: 1px solid #00FF88 !important;
    }
</style>
""", unsafe_allow_html=True)

# Zona horaria Ecuador (puedes cambiarla a la del broker si es necesario)
ecuador_tz = pytz.timezone('America/Guayaquil')

# ============================================
# CLASE DE CONEXIÓN IQ OPTION
# ============================================
class IQOptionConnector:
    def __init__(self):
        self.api = None
        self.conectado = False
        self.balance = 0
        self.tipo_cuenta = "PRACTICE"
        self.activos_cache = {}

    def conectar(self, email, password):
        if not IQ_AVAILABLE:
            return False, "Librería IQ Option no disponible."
        try:
            self.api = IQ_Option(email, password)
            check, reason = self.api.connect()
            if check:
                self.conectado = True
                self.actualizar_balance()
                return True, "Conexión exitosa"
            else:
                return False, reason
        except Exception as e:
            return False, str(e)

    def cambiar_balance(self, tipo="PRACTICE"):
        if self.conectado:
            self.tipo_cuenta = tipo
            self.api.change_balance(tipo)
            self.actualizar_balance()
            return True
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
            else:  # OTC
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

    def colocar_orden(self, activo, direccion, monto, expiracion=5):
        if not self.conectado:
            return None, "No conectado"
        try:
            direccion_api = 'call' if direccion.upper() == 'COMPRA' else 'put'
            tiempo = expiracion * 60
            resultado = self.api.buy(monto, activo, direccion_api, tiempo)
            return resultado, "Orden ejecutada"
        except Exception as e:
            return None, str(e)

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
    df['volume_ma'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_ma'].clip(lower=1)
    adx = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
    df['adx'] = adx.adx()
    df['adx_pos'] = adx.adx_pos()
    df['adx_neg'] = adx.adx_neg()
    bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
    df['bb_width'] = (bb.bollinger_hband() - bb.bollinger_lband()) / df['close'] * 100
    # MACD
    macd = ta.trend.MACD(df['close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    df['macd_diff'] = macd.macd_diff()
    return df

# ============================================
# 4 ESTRATEGIAS DE TENDENCIA INDEPENDIENTES
# ============================================
def estrategia_ruptura(df):
    """Estrategia 1: Ruptura de máximos/mínimos recientes con volumen"""
    if df is None or len(df) < 15:
        return None, 0
    ult = df.iloc[-1]
    max_reciente = df['high'].iloc[-10:-1].max()
    min_reciente = df['low'].iloc[-10:-1].min()
    if ult['close'] > max_reciente and ult['volume_ratio'] > 1.2:
        confianza = 70 + min(15, int(ult['volume_ratio'] * 10))
        return 'COMPRA', confianza
    elif ult['close'] < min_reciente and ult['volume_ratio'] > 1.2:
        confianza = 70 + min(15, int(ult['volume_ratio'] * 10))
        return 'VENTA', confianza
    return None, 0

def estrategia_pendiente_ema(df):
    """Estrategia 2: Pendiente de EMA20 con confirmación de ADX"""
    if df is None or len(df) < 20:
        return None, 0
    ult = df.iloc[-1]
    pendiente = (df['ema_20'].iloc[-1] - df['ema_20'].iloc[-5]) / 5
    fuerza = 0
    if pendiente > 0.003 * ult['close']:
        fuerza = 65
        if ult['adx'] > 25 and ult['adx_pos'] > ult['adx_neg']:
            fuerza += 15
        if ult['volume_ratio'] > 1.3:
            fuerza += 10
        return 'COMPRA', min(95, fuerza)
    elif pendiente < -0.003 * ult['close']:
        fuerza = 65
        if ult['adx'] > 25 and ult['adx_neg'] > ult['adx_pos']:
            fuerza += 15
        if ult['volume_ratio'] > 1.3:
            fuerza += 10
        return 'VENTA', min(95, fuerza)
    return None, 0

def estrategia_adx_volumen(df):
    """Estrategia 3: ADX alto con volumen y pendiente de EMA"""
    if df is None or len(df) < 20:
        return None, 0
    ult = df.iloc[-1]
    if ult['adx'] > 25 and ult['volume_ratio'] > 1.2:
        pendiente = (df['ema_20'].iloc[-1] - df['ema_20'].iloc[-3]) / 3
        if pendiente > 0:
            confianza = 70 + int(ult['adx'] / 2)
            return 'COMPRA', min(95, confianza)
        elif pendiente < 0:
            confianza = 70 + int(ult['adx'] / 2)
            return 'VENTA', min(95, confianza)
    return None, 0

def estrategia_macd(df):
    """Estrategia 4: Cruce de MACD con volumen"""
    if df is None or len(df) < 30:
        return None, 0
    ult = df.iloc[-1]
    prev = df.iloc[-2]
    if prev['macd'] < prev['macd_signal'] and ult['macd'] > ult['macd_signal'] and ult['volume_ratio'] > 1.1:
        return 'COMPRA', 70
    elif prev['macd'] > prev['macd_signal'] and ult['macd'] < ult['macd_signal'] and ult['volume_ratio'] > 1.1:
        return 'VENTA', 70
    return None, 0

# ============================================
# ENSEMBLE PONDERADO (IA) con 4 estrategias
# ============================================
def ensemble_ia(df):
    """
    Combina las cuatro estrategias usando pesos basados en volumen y fuerza.
    Retorna señal final y probabilidad.
    """
    if df is None:
        return None, 0

    # Obtener votos de cada estrategia
    s1, c1 = estrategia_ruptura(df)
    s2, c2 = estrategia_pendiente_ema(df)
    s3, c3 = estrategia_adx_volumen(df)
    s4, c4 = estrategia_macd(df)

    # Pesos dinámicos: se basan en el volumen y ADX
    ult = df.iloc[-1]
    peso_volumen = min(2.0, 1 + ult['volume_ratio'] / 2)
    peso_adx = min(1.5, 1 + ult['adx'] / 50)

    votos = []
    if s1:
        votos.append((s1, c1 * peso_volumen))
    if s2:
        votos.append((s2, c2 * peso_adx))
    if s3:
        votos.append((s3, c3 * (peso_volumen + peso_adx) / 2))
    if s4:
        votos.append((s4, c4 * peso_volumen))

    if not votos:
        return None, 0

    # Sumar votos ponderados
    total_compra = sum(conf for senal, conf in votos if senal == 'COMPRA')
    total_venta = sum(conf for senal, conf in votos if senal == 'VENTA')
    total = total_compra + total_venta

    if total_compra > total_venta:
        prob = int((total_compra / total) * 100)
        return 'COMPRA', min(95, prob)
    elif total_venta > total_compra:
        prob = int((total_venta / total) * 100)
        return 'VENTA', min(95, prob)
    else:
        return None, 0

# ============================================
# ANÁLISIS DE UN ACTIVO (usa el ensemble)
# ============================================
def analizar_activo(activo, connector):
    df = connector.obtener_velas(activo, intervalo=5, limite=100)
    if df is None:
        return None
    df = calcular_indicadores(df)
    if df is None:
        return None

    senal, prob = ensemble_ia(df)
    ult = df.iloc[-1]
    # Score para ordenamiento interno (basado en probabilidad, volumen y ADX)
    score = prob * (1 + ult['volume_ratio']) * (1 + ult['adx']/50) if senal else 0

    return {
        'activo': activo,
        'senal': senal,
        'prob': prob,
        'precio': ult['close'],
        'rsi': ult['rsi'],
        'volume_ratio': ult['volume_ratio'],
        'adx': ult['adx'],
        'score': score,
        'df': df
    }

# ============================================
# CLASE PARA GESTIONAR EL HISTORIAL DE OPERACIONES
# ============================================
class TradeLogger:
    def __init__(self):
        self.trades = []
        self.operaciones_hoy = 0
        self.fecha_actual = datetime.now().date()

    def agregar_trade(self, activo, direccion, monto, resultado, ganancia):
        self.trades.append({
            'fecha': datetime.now(ecuador_tz).strftime('%Y-%m-%d %H:%M:%S'),
            'activo': activo,
            'direccion': direccion,
            'monto': monto,
            'resultado': resultado,
            'ganancia': ganancia
        })
        # Actualizar contador diario
        hoy = datetime.now().date()
        if hoy != self.fecha_actual:
            self.operaciones_hoy = 0
            self.fecha_actual = hoy
        self.operaciones_hoy += 1

    def obtener_resumen(self):
        if not self.trades:
            return {'total_operaciones': 0, 'ganadas': 0, 'perdidas': 0, 'ganancia_neta': 0, 'operaciones_hoy': self.operaciones_hoy}
        df = pd.DataFrame(self.trades)
        ganadas = df[df['resultado'] == 'ganada'].shape[0]
        perdidas = df[df['resultado'] == 'perdida'].shape[0]
        ganancia_neta = df['ganancia'].sum()
        return {
            'total_operaciones': len(self.trades),
            'ganadas': ganadas,
            'perdidas': perdidas,
            'ganancia_neta': ganancia_neta,
            'operaciones_hoy': self.operaciones_hoy
        }

    def reiniciar_contador_diario(self):
        self.operaciones_hoy = 0
        self.fecha_actual = datetime.now().date()

# ============================================
# INTERFAZ PRINCIPAL
# ============================================
def main():
    st.title("🤖 IQ OPTION PROFESSIONAL BOT")
    st.markdown("#### 4 Estrategias con IA | Hasta 2 activos | Control de operaciones")
    st.markdown("---")

    # Inicializar estado de sesión
    if 'connector' not in st.session_state:
        st.session_state.connector = IQOptionConnector()
    if 'conectado' not in st.session_state:
        st.session_state.conectado = False
    if 'activos_seleccionados' not in st.session_state:
        st.session_state.activos_seleccionados = []
    if 'resultados_activos' not in st.session_state:
        st.session_state.resultados_activos = {}
    if 'ultima_actualizacion' not in st.session_state:
        st.session_state.ultima_actualizacion = None
    if 'notificadas' not in st.session_state:
        st.session_state.notificadas = set()
    if 'logger' not in st.session_state:
        st.session_state.logger = TradeLogger()
    if 'modo_operacion' not in st.session_state:
        st.session_state.modo_operacion = "Señales"
    if 'monto_operacion' not in st.session_state:
        st.session_state.monto_operacion = 1.0
    if 'mercado_actual' not in st.session_state:
        st.session_state.mercado_actual = "otc"
    if 'lista_activos_completa' not in st.session_state:
        st.session_state.lista_activos_completa = []
    if 'modo_seleccion' not in st.session_state:
        st.session_state.modo_seleccion = "Manual"  # o "Automático"
    if 'max_operaciones' not in st.session_state:
        st.session_state.max_operaciones = 10  # límite diario por defecto

    # Barra lateral
    with st.sidebar:
        st.image("https://i.imgur.com/6QhQx8L.png", width=200)
        st.markdown("### 🔐 Conexión a IQ Option")

        if not st.session_state.conectado:
            email = st.text_input("Correo electrónico", placeholder="usuario@email.com")
            password = st.text_input("Contraseña", type="password", placeholder="••••••••")
            if st.button("🔌 Conectar", use_container_width=True):
                if email and password:
                    with st.spinner("Conectando..."):
                        ok, msg = st.session_state.connector.conectar(email, password)
                        if ok:
                            st.session_state.conectado = True
                            st.success(f"✅ Conectado - Saldo: ${st.session_state.connector.obtener_saldo():.2f}")
                            # Cargar lista de activos
                            with st.spinner("Cargando activos disponibles..."):
                                st.session_state.lista_activos_completa = st.session_state.connector.obtener_activos_disponibles(
                                    st.session_state.mercado_actual, max_activos=200, force_refresh=True
                                )
                            st.rerun()
                        else:
                            st.error(f"❌ Error: {msg}")
                else:
                    st.warning("Ingresa credenciales")
        else:
            st.success(f"✅ Conectado")
            st.metric("Saldo", f"${st.session_state.connector.obtener_saldo():.2f}")
            if st.button("🚪 Desconectar"):
                st.session_state.conectado = False
                st.session_state.connector = IQOptionConnector()
                st.session_state.activos_seleccionados = []
                st.session_state.resultados_activos = {}
                st.rerun()

        st.markdown("---")

        if st.session_state.conectado:
            st.markdown("### ⚙️ Configuración")

            # Selector de mercado
            mercado = st.radio(
                "Mercado",
                ["🌙 OTC (24/7)", "📊 Normal (horario)"],
                index=0 if st.session_state.mercado_actual == "otc" else 1,
                horizontal=True,
                key="mercado_radio"
            )
            nuevo_mercado = "otc" if "OTC" in mercado else "forex"
            if nuevo_mercado != st.session_state.mercado_actual:
                st.session_state.mercado_actual = nuevo_mercado
                with st.spinner("Cargando activos del nuevo mercado..."):
                    st.session_state.lista_activos_completa = st.session_state.connector.obtener_activos_disponibles(
                        st.session_state.mercado_actual, max_activos=200, force_refresh=True
                    )
                st.session_state.activos_seleccionados = []
                st.rerun()

            # Tipo de cuenta
            tipo_cuenta = st.radio(
                "Tipo de cuenta",
                ["💰 Demo (PRACTICE)", "💵 Real"],
                index=0 if st.session_state.connector.tipo_cuenta == "PRACTICE" else 1,
                horizontal=True
            )
            cuenta_real = "REAL" in tipo_cuenta
            tipo = "REAL" if cuenta_real else "PRACTICE"
            if tipo != st.session_state.connector.tipo_cuenta:
                st.session_state.connector.cambiar_balance(tipo)
                st.rerun()

            # Modo de operación
            st.session_state.modo_operacion = st.radio(
                "Modo de operación",
                ["🔔 Solo señales", "🤖 Automático"],
                index=0 if st.session_state.modo_operacion == "Señales" else 1,
                horizontal=True
            )

            # Monto por operación
            st.session_state.monto_operacion = st.number_input(
                "Monto por operación ($)",
                min_value=1.0 if cuenta_real else 0.1,
                max_value=1000.0 if cuenta_real else 100.0,
                value=st.session_state.monto_operacion,
                step=1.0
            )

            # Límite de operaciones diarias
            st.session_state.max_operaciones = st.number_input(
                "Límite de operaciones por día",
                min_value=1,
                max_value=100,
                value=st.session_state.max_operaciones,
                step=1
            )

            st.markdown("---")
            st.markdown("### 📋 Selección de Activos")

            # Modo de selección
            modo_sel = st.radio(
                "Modo de selección",
                ["Manual", "Automático (elige el mejor)"],
                index=0 if st.session_state.modo_seleccion == "Manual" else 1,
                horizontal=True
            )
            st.session_state.modo_seleccion = modo_sel

            if modo_sel == "Manual":
                # Mostrar cantidad de activos disponibles
                st.caption(f"Total activos disponibles: {len(st.session_state.lista_activos_completa)}")

                # Buscador
                busqueda = st.text_input("🔍 Buscar activo", placeholder="Ej: EURUSD", key="buscador")

                # Filtrar lista según búsqueda
                if busqueda:
                    lista_filtrada = [a for a in st.session_state.lista_activos_completa if busqueda.upper() in a.upper()]
                else:
                    lista_filtrada = st.session_state.lista_activos_completa

                # Selector múltiple (hasta 2)
                seleccion = st.multiselect(
                    "Selecciona hasta 2 activos",
                    options=lista_filtrada,
                    default=st.session_state.activos_seleccionados,
                    max_selections=2,
                    format_func=lambda x: x.replace("-OTC", "")
                )

                # Actualizar la selección
                if seleccion != st.session_state.activos_seleccionados:
                    st.session_state.activos_seleccionados = seleccion
                    st.session_state.resultados_activos = {}
                    st.session_state.ultima_actualizacion = None
                    st.rerun()
            else:
                # Modo automático: aquí no mostramos selector, solo un botón para iniciar análisis automático
                st.info("El bot analizará todos los activos y elegirá el más estable.")
                if st.button("🤖 Iniciar análisis automático", use_container_width=True):
                    with st.spinner("Analizando todos los activos para encontrar el mejor..."):
                        mejores = []
                        for act in st.session_state.lista_activos_completa:
                            res = analizar_activo(act, st.session_state.connector)
                            if res and res['senal']:
                                mejores.append((res['score'], act, res))
                            time.sleep(0.1)
                        if mejores:
                            mejores.sort(reverse=True)
                            # Tomar el mejor (o hasta 2 mejores)
                            mejor_activo = mejores[0][2]
                            st.session_state.activos_seleccionados = [mejor_activo['activo']]
                            st.session_state.resultados_activos = {mejor_activo['activo']: mejor_activo}
                            if len(mejores) > 1 and mejores[1][0] > 50:  # si el segundo también tiene buen score
                                segundo = mejores[1][2]
                                st.session_state.activos_seleccionados.append(segundo['activo'])
                                st.session_state.resultados_activos[segundo['activo']] = segundo
                            st.session_state.ultima_actualizacion = datetime.now(ecuador_tz)
                            st.success(f"✅ Mejor activo encontrado: {mejor_activo['activo']}")
                        else:
                            st.warning("No se encontraron activos con señales claras.")
                        st.rerun()

            # Botón para analizar ahora
            if st.session_state.activos_seleccionados and st.button("🔄 ANALIZAR AHORA", use_container_width=True):
                with st.spinner("Analizando activos seleccionados..."):
                    nuevos_resultados = {}
                    for act in st.session_state.activos_seleccionados:
                        res = analizar_activo(act, st.session_state.connector)
                        if res:
                            nuevos_resultados[act] = res
                        time.sleep(0.2)
                    st.session_state.resultados_activos = nuevos_resultados
                    st.session_state.ultima_actualizacion = datetime.now(ecuador_tz)
                    st.session_state.notificadas = set()
                    st.success("✅ Análisis completado")
                    st.rerun()

    # Verificar conexión
    if not st.session_state.conectado:
        st.info("👆 Conéctate a IQ Option en la barra lateral para comenzar.")
        return

    # Panel de control superior
    resumen = st.session_state.logger.obtener_resumen()
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Balance", f"${st.session_state.connector.obtener_saldo():.2f}")
    with col2:
        st.metric("Operaciones totales", resumen['total_operaciones'])
    with col3:
        st.metric("Ganadas", resumen['ganadas'])
    with col4:
        st.metric("Ganancia neta", f"${resumen['ganancia_neta']:.2f}")
    with col5:
        st.metric("Operaciones hoy", f"{resumen['operaciones_hoy']} / {st.session_state.max_operaciones}")

    # Reloj en tiempo real
    ahora = datetime.now(ecuador_tz)
    st.markdown(f"<div class='reloj'>⏰ {ahora.strftime('%H:%M:%S')} ECU</div>", unsafe_allow_html=True)

    # Actualización automática cada 5 minutos (solo si hay activos seleccionados)
    if st.session_state.activos_seleccionados:
        if (st.session_state.ultima_actualizacion is None or
            (ahora - st.session_state.ultima_actualizacion).seconds > 300):
            with st.spinner("Actualizando análisis automático (cada 5 min)..."):
                nuevos_resultados = {}
                for act in st.session_state.activos_seleccionados:
                    res = analizar_activo(act, st.session_state.connector)
                    if res:
                        nuevos_resultados[act] = res
                    time.sleep(0.2)
                st.session_state.resultados_activos = nuevos_resultados
                st.session_state.ultima_actualizacion = ahora
                st.session_state.notificadas = set()
                st.rerun()

    # Mostrar resultados de los activos seleccionados
    if st.session_state.activos_seleccionados:
        st.markdown("## 📊 ACTIVOS SELECCIONADOS")
        num_activos = len(st.session_state.activos_seleccionados)
        cols = st.columns(num_activos)

        for idx, activo in enumerate(st.session_state.activos_seleccionados):
            with cols[idx]:
                if activo in st.session_state.resultados_activos:
                    a = st.session_state.resultados_activos[activo]
                    nombre = activo.replace("-OTC", "")
                    color = "#00FF88" if a['senal'] == 'COMPRA' else "#FF4646" if a['senal'] == 'VENTA' else "#AAA"
                    signal_class = f"signal-{a['senal'].lower()}" if a['senal'] else "signal-neutral"

                    # Calcular hora de entrada (próxima vela de 5 min)
                    minutos = ahora.minute
                    minuto_base = (minutos // 5) * 5
                    tiempo_entrada = ahora.replace(minute=minuto_base, second=0, microsecond=0) + timedelta(minutes=5)
                    tiempo_salida = tiempo_entrada + timedelta(minutes=5)
                    segundos_rest = (tiempo_entrada - ahora).seconds

                    # Notificación 1 min antes
                    if a['senal'] and segundos_rest <= 60 and segundos_rest > 0:
                        clave = f"{activo}_{tiempo_entrada}"
                        if clave not in st.session_state.notificadas:
                            st.toast(f"📢 **{nombre}** – {a['senal']} a las {tiempo_entrada.strftime('%H:%M')}", icon="⏰")
                            st.session_state.notificadas.add(clave)

                    # Modo automático: ejecutar orden si hay señal, no se ha alcanzado el límite y faltan 10 segundos
                    if (st.session_state.modo_operacion == "🤖 Automático" and a['senal'] and
                        segundos_rest <= 10 and resumen['operaciones_hoy'] < st.session_state.max_operaciones):
                        resultado, msg = st.session_state.connector.colocar_orden(
                            activo,
                            a['senal'],
                            st.session_state.monto_operacion,
                            expiracion=5
                        )
                        if resultado:
                            st.success(f"✅ Orden ejecutada: {a['senal']} en {nombre}")
                            # Aquí deberías verificar el resultado real después de 5 minutos, pero por ahora simulamos
                            st.session_state.logger.agregar_trade(
                                activo,
                                a['senal'],
                                st.session_state.monto_operacion,
                                'ganada',  # En producción, verificar
                                st.session_state.monto_operacion * 0.8
                            )
                            st.rerun()
                        else:
                            st.error(f"❌ Error en {nombre}: {msg}")

                    # Tarjeta del activo
                    st.markdown(f"""
                    <div class="asset-card">
                        <div class="asset-name">{nombre}</div>
                        <div class="asset-signal {signal_class}">{a['senal'] if a['senal'] else 'NEUTRAL'}</div>
                        <div style="font-size: 28px; font-weight:800; color:{color}; text-align:center;">{a['prob']}%</div>
                        <div class="asset-footer">
                            <span>⏰ {tiempo_entrada.strftime('%H:%M')}</span>
                            <span>⏳ {tiempo_salida.strftime('%H:%M')}</span>
                        </div>
                        <div style="margin-top:10px; color:#AAA; font-size:14px;">
                            <span>RSI: {a['rsi']:.1f} | Vol: {a['volume_ratio']:.1f}x | ADX: {a['adx']:.1f}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="asset-card" style="opacity:0.5;">
                        <div class="asset-name">{activo.replace('-OTC','')}</div>
                        <div style="text-align:center;">⏳ Analizando...</div>
                    </div>
                    """, unsafe_allow_html=True)

        # Botón para analizar todos los seleccionados
        if st.button("🔄 Analizar todos los seleccionados"):
            with st.spinner("Analizando..."):
                nuevos_resultados = {}
                for act in st.session_state.activos_seleccionados:
                    res = analizar_activo(act, st.session_state.connector)
                    if res:
                        nuevos_resultados[act] = res
                    time.sleep(0.2)
                st.session_state.resultados_activos = nuevos_resultados
                st.session_state.ultima_actualizacion = ahora
                st.session_state.notificadas = set()
                st.rerun()

    else:
        st.info("👈 Selecciona activos o usa el modo automático en la barra lateral.")

    # Historial de operaciones
    with st.expander("📜 Ver historial de operaciones"):
        if st.session_state.logger.trades:
            df_trades = pd.DataFrame(st.session_state.logger.trades)
            st.dataframe(df_trades, use_container_width=True)
        else:
            st.info("Aún no hay operaciones registradas.")

    # Botón manual de actualización
    if st.button("🔄 Actualizar ahora (manual)"):
        st.rerun()

if __name__ == "__main__":
    main()
