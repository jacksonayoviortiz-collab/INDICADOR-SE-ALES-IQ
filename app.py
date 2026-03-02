"""
BOT DE TRADING PROFESIONAL PARA IQ OPTION - VERSIÓN TIEMPO REAL
Características:
- Actualización automática cada 10 segundos (autorefresh)
- Reloj en tiempo real
- 2 paneles: 1 activo de 5 min y 1 activo de 1 min (los más confiables)
- Escaneo completo de activos en cada ciclo
- Estrategias robustas con volumen simulado si es necesario
- Notificaciones con 1 min de anticipación para 5 min y "Opera ahora" para 1 min
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

# Para autorefresh
from streamlit_autorefresh import st_autorefresh

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

# Importar API de IQ Option
try:
    from iqoptionapi.stable_api import IQ_Option
    IQ_AVAILABLE = True
except ImportError:
    IQ_AVAILABLE = False
    st.error("""
    ⚠️ **Error crítico:** No se pudo importar la librería `iqoptionapi`.
    Verifica que esté correctamente instalada desde GitHub.
    """)

# Configuración de página
st.set_page_config(
    page_title="IQ Option Real-Time Scanner",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Autorefresh cada 10 segundos (para mantener reloj y datos actualizados)
count = st_autorefresh(interval=10000, key="autorefresh")

# CSS personalizado (simplificado y profesional)
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
    .badge-1min {
        background: #FFAA00;
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
</style>
""", unsafe_allow_html=True)

# Zona horaria Ecuador
ecuador_tz = pytz.timezone('America/Guayaquil')

# === CLASE DE CONEXIÓN ===
class IQOptionConnector:
    def __init__(self):
        self.api = None
        self.conectado = False

    def conectar(self, email, password):
        if not IQ_AVAILABLE:
            return False, "Librería IQ Option no disponible."
        try:
            self.api = IQ_Option(email, password)
            check, reason = self.api.connect()
            if check:
                self.conectado = True
                return True, "Conexión exitosa"
            else:
                return False, reason
        except Exception as e:
            return False, str(e)

    def cambiar_balance(self, tipo="PRACTICE"):
        if self.conectado:
            return self.api.change_balance(tipo)
        return False

    def obtener_saldo(self):
        if self.conectado:
            return self.api.get_balance()
        return 0

    def obtener_activos_disponibles(self, mercado="otc", max_activos=50):
        if not self.conectado:
            return []
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
            return sorted(activos)[:max_activos]
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

# === INDICADORES COMUNES ===
def calcular_indicadores(df):
    if df is None or len(df) < 20:
        return None
    # Si el volumen es cero, lo simulamos con rango de precios
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
    return df

# === ESTRATEGIAS PARA 5 MINUTOS ===
def estrategia_ruptura_5min(df):
    if df is None or len(df) < 15:
        return None, 0
    ult = df.iloc[-1]
    max_reciente = df['high'].iloc[-10:-1].max()
    min_reciente = df['low'].iloc[-10:-1].min()
    if ult['close'] > max_reciente and ult['volume_ratio'] > 1.2:
        if ult['adx'] > 20 and ult['adx_pos'] > ult['adx_neg']:
            return 'COMPRA', 80
        else:
            return 'COMPRA', 65
    elif ult['close'] < min_reciente and ult['volume_ratio'] > 1.2:
        if ult['adx'] > 20 and ult['adx_neg'] > ult['adx_pos']:
            return 'VENTA', 80
        else:
            return 'VENTA', 65
    return None, 0

def estrategia_pendiente_5min(df):
    if df is None or len(df) < 20:
        return None, 0
    ult = df.iloc[-1]
    pendiente = (df['ema_20'].iloc[-1] - df['ema_20'].iloc[-5]) / 5
    if pendiente > 0.005 * ult['close']:
        if ult['volume_ratio'] > 1.2 and ult['adx'] > 20:
            return 'COMPRA', 75
        elif ult['volume_ratio'] > 1.0:
            return 'COMPRA', 60
    elif pendiente < -0.005 * ult['close']:
        if ult['volume_ratio'] > 1.2 and ult['adx'] > 20:
            return 'VENTA', 75
        elif ult['volume_ratio'] > 1.0:
            return 'VENTA', 60
    return None, 0

def estrategia_adx_5min(df):
    if df is None or len(df) < 20:
        return None, 0
    ult = df.iloc[-1]
    if ult['adx'] > 25 and ult['volume_ratio'] > 1.2:
        pendiente = (df['ema_20'].iloc[-1] - df['ema_20'].iloc[-3]) / 3
        if pendiente > 0:
            return 'COMPRA', 70
        elif pendiente < 0:
            return 'VENTA', 70
    return None, 0

# === ESTRATEGIAS PARA 1 MINUTO ===
def estrategia_ruptura_1min(df):
    if df is None or len(df) < 10:
        return None, 0
    ult = df.iloc[-1]
    max_reciente = df['high'].iloc[-5:-1].max()
    min_reciente = df['low'].iloc[-5:-1].max()
    if ult['close'] > max_reciente and ult['volume_ratio'] > 1.3:
        return 'COMPRA', 75
    elif ult['close'] < min_reciente and ult['volume_ratio'] > 1.3:
        return 'VENTA', 75
    return None, 0

def estrategia_rsi_1min(df):
    if df is None or len(df) < 14:
        return None, 0
    ult = df.iloc[-1]
    if ult['rsi'] < 30 and ult['volume_ratio'] > 1.2:
        return 'COMPRA', 70
    elif ult['rsi'] > 70 and ult['volume_ratio'] > 1.2:
        return 'VENTA', 70
    return None, 0

# === ANÁLISIS DE UN ACTIVO PARA 5 MIN ===
def analizar_5min(activo, connector):
    df = connector.obtener_velas(activo, intervalo=5, limite=100)
    if df is None:
        return None
    df = calcular_indicadores(df)
    if df is None:
        return None

    estrategias = [
        estrategia_ruptura_5min,
        estrategia_pendiente_5min,
        estrategia_adx_5min
    ]
    votos_compra = 0
    votos_venta = 0
    peso_total = 0
    for func in estrategias:
        senal, conf = func(df)
        if senal == 'COMPRA':
            votos_compra += conf
            peso_total += conf
        elif senal == 'VENTA':
            votos_venta += conf
            peso_total += conf

    if peso_total == 0:
        senal_final = None
        prob = 0
    else:
        if votos_compra > votos_venta:
            prob = int((votos_compra / peso_total) * 100)
            senal_final = 'COMPRA'
        elif votos_venta > votos_compra:
            prob = int((votos_venta / peso_total) * 100)
            senal_final = 'VENTA'
        else:
            senal_final = None
            prob = 0

    ult = df.iloc[-1]
    # Score: probabilidad * (1 + volumen/2) * (1 + adx/50)
    score = prob * (1 + ult['volume_ratio']/2) * (1 + ult['adx']/50) if senal_final else 0
    return {
        'activo': activo,
        'score': score,
        'senal': senal_final,
        'prob': prob,
        'precio': ult['close'],
        'rsi': ult['rsi'],
        'volume_ratio': ult['volume_ratio'],
        'adx': ult['adx'],
        'df': df
    }

# === ANÁLISIS PARA 1 MIN ===
def analizar_1min(activo, connector):
    df = connector.obtener_velas(activo, intervalo=1, limite=100)
    if df is None:
        return None
    # Calcular solo lo necesario
    if df['volume'].sum() == 0:
        df['volume'] = (df['high'] - df['low']) * 1000 / df['close']
    df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    df['volume_ma'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_ma'].clip(lower=1)
    if len(df) < 10:
        return None

    senal1, conf1 = estrategia_ruptura_1min(df)
    senal2, conf2 = estrategia_rsi_1min(df)

    votos_compra = 0
    votos_venta = 0
    peso_total = 0
    if senal1 == 'COMPRA':
        votos_compra += conf1
        peso_total += conf1
    elif senal1 == 'VENTA':
        votos_venta += conf1
        peso_total += conf1
    if senal2 == 'COMPRA':
        votos_compra += conf2
        peso_total += conf2
    elif senal2 == 'VENTA':
        votos_venta += conf2
        peso_total += conf2

    if peso_total == 0:
        senal_final = None
        prob = 0
    else:
        if votos_compra > votos_venta:
            prob = int((votos_compra / peso_total) * 100)
            senal_final = 'COMPRA'
        elif votos_venta > votos_compra:
            prob = int((votos_venta / peso_total) * 100)
            senal_final = 'VENTA'
        else:
            senal_final = None
            prob = 0

    ult = df.iloc[-1]
    score = prob * (1 + ult['volume_ratio']) * (1 + (100 - ult['rsi'])/100) if senal_final else 0
    return {
        'activo': activo,
        'score': score,
        'senal': senal_final,
        'prob': prob,
        'precio': ult['close'],
        'rsi': ult['rsi'],
        'volume_ratio': ult['volume_ratio'],
        'df': df
    }

# === ESCANEO COMPLETO (se ejecuta en cada autorefresh) ===
def escanear(connector, mercado, max_activos=50):
    activos = connector.obtener_activos_disponibles(mercado, max_activos)
    if not activos:
        return None, None
    mejores_5min = None
    mejores_1min = None
    max_score_5 = -1
    max_score_1 = -1
    for act in activos:
        time.sleep(0.1)  # para no saturar
        res5 = analizar_5min(act, connector)
        if res5 and res5['score'] > max_score_5:
            max_score_5 = res5['score']
            mejores_5min = res5
        res1 = analizar_1min(act, connector)
        if res1 and res1['score'] > max_score_1:
            max_score_1 = res1['score']
            mejores_1min = res1
    return mejores_5min, mejores_1min

# === INTERFAZ PRINCIPAL ===
def main():
    # Inicializar estado
    if 'connector' not in st.session_state:
        st.session_state.connector = IQOptionConnector()
    if 'conectado' not in st.session_state:
        st.session_state.conectado = False
    if 'mejor_5min' not in st.session_state:
        st.session_state.mejor_5min = None
    if 'mejor_1min' not in st.session_state:
        st.session_state.mejor_1min = None
    if 'mercado_actual' not in st.session_state:
        st.session_state.mercado_actual = "otc"
    if 'notificadas_5min' not in st.session_state:
        st.session_state.notificadas_5min = set()
    if 'notificadas_1min' not in st.session_state:
        st.session_state.notificadas_1min = set()

    # Barra lateral
    with st.sidebar:
        st.image("https://i.imgur.com/6QhQx8L.png", width=200)
        st.markdown("### 🔐 Acceso a IQ Option")

        if not st.session_state.conectado:
            email = st.text_input("Correo", placeholder="usuario@email.com")
            password = st.text_input("Contraseña", type="password", placeholder="••••••••")
            tipo_cuenta = st.selectbox("Tipo", ["PRACTICE", "REAL"])

            if st.button("🔌 Conectar", use_container_width=True):
                if email and password:
                    with st.spinner("Conectando..."):
                        ok, msg = st.session_state.connector.conectar(email, password)
                        if ok:
                            st.session_state.connector.cambiar_balance(tipo_cuenta)
                            st.session_state.conectado = True
                            st.success(f"✅ Conectado - Saldo: ${st.session_state.connector.obtener_saldo():.2f}")
                            st.rerun()
                        else:
                            st.error(f"❌ Error: {msg}")
                else:
                    st.warning("Ingresa credenciales")
        else:
            st.success(f"✅ Conectado")
            saldo = st.session_state.connector.obtener_saldo()
            st.metric("Saldo", f"${saldo:.2f}" if saldo else "N/A")
            if st.button("🚪 Desconectar"):
                st.session_state.conectado = False
                st.session_state.connector = IQOptionConnector()
                st.session_state.mejor_5min = None
                st.session_state.mejor_1min = None
                st.rerun()

        st.markdown("---")

        if st.session_state.conectado:
            st.markdown("### ⚙️ Configuración")
            mercado = st.radio(
                "Mercado",
                ["🌙 OTC", "📊 Normal"],
                index=0,
                horizontal=True
            )
            st.session_state.mercado_actual = "otc" if "OTC" in mercado else "forex"

            st.caption("El análisis se actualiza automáticamente cada 10 segundos.")

    # Verificar conexión
    if not st.session_state.conectado:
        st.info("👆 Conéctate a IQ Option en la barra lateral.")
        return

    # Reloj en tiempo real
    ahora = datetime.now(ecuador_tz)
    st.markdown(f"<div class='reloj'>⏰ {ahora.strftime('%H:%M:%S')} ECU</div>", unsafe_allow_html=True)

    # Escanear activos (se ejecuta en cada autorefresh)
    mejor5, mejor1 = escanear(st.session_state.connector, st.session_state.mercado_actual, max_activos=50)
    if mejor5:
        st.session_state.mejor_5min = mejor5
    if mejor1:
        st.session_state.mejor_1min = mejor1

    # === ACTIVO DE 5 MINUTOS ===
    st.markdown("## 📈 Activo más confiable - Vencimiento 5 minutos")
    if st.session_state.mejor_5min:
        a = st.session_state.mejor_5min
        nombre = a['activo'].replace("-OTC", "")
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
            clave = f"{a['activo']}_{tiempo_entrada}"
            if clave not in st.session_state.notificadas_5min:
                st.toast(f"📢 **5 min:** Opera a las {tiempo_entrada.strftime('%H:%M')} – {nombre} – {a['senal']}", icon="⏰")
                st.session_state.notificadas_5min.add(clave)

        st.markdown(f"""
        <div class="asset-card">
            <div class="asset-name">{nombre} <span class="badge-5min">5 MIN</span></div>
            <div class="asset-signal {signal_class}">{a['senal'] if a['senal'] else 'NEUTRAL'}</div>
            <div style="font-size: 32px; font-weight:800; color:{color}; text-align:center;">{a['prob']}%</div>
            <div class="asset-footer">
                <span>⏰ Entrada: {tiempo_entrada.strftime('%H:%M')}</span>
                <span>⏳ Vence: {tiempo_salida.strftime('%H:%M')}</span>
            </div>
            <div style="display:flex; justify-content:space-between; margin-top:15px; color:#AAA;">
                <span>Precio: {a['precio']:.5f}</span>
                <span>RSI: {a['rsi']:.1f}</span>
                <span>Vol: {a['volume_ratio']:.1f}x</span>
                <span>ADX: {a['adx']:.1f}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.warning("No se encontró ningún activo con datos suficientes para 5 min.")

    # === ACTIVO DE 1 MINUTO ===
    st.markdown("## ⚡ Activo más confiable - Vencimiento 1 minuto")
    if st.session_state.mejor_1min:
        a = st.session_state.mejor_1min
        nombre = a['activo'].replace("-OTC", "")
        color = "#00FF88" if a['senal'] == 'COMPRA' else "#FF4646" if a['senal'] == 'VENTA' else "#AAA"
        signal_class = f"signal-{a['senal'].lower()}" if a['senal'] else "signal-neutral"

        # Hora de entrada: próximo minuto exacto
        tiempo_entrada = ahora.replace(second=0, microsecond=0) + timedelta(minutes=1)
        tiempo_salida = tiempo_entrada + timedelta(minutes=1)
        segundos_rest = (tiempo_entrada - ahora).seconds

        # Si faltan menos de 10 segundos, mostramos "Opera ahora"
        if segundos_rest <= 10 and a['senal']:
            mensaje_entrada = "🔥 ¡OPERA AHORA!"
            # Notificación
            clave = f"{a['activo']}_1min_{tiempo_entrada}"
            if clave not in st.session_state.notificadas_1min:
                st.toast(f"⚡ **1 min:** ¡Opera ahora! {nombre} – {a['senal']}", icon="🚀")
                st.session_state.notificadas_1min.add(clave)
        else:
            mensaje_entrada = f"⏰ Entrada: {tiempo_entrada.strftime('%H:%M:%S')}"

        st.markdown(f"""
        <div class="asset-card">
            <div class="asset-name">{nombre} <span class="badge-1min">1 MIN</span></div>
            <div class="asset-signal {signal_class}">{a['senal'] if a['senal'] else 'NEUTRAL'}</div>
            <div style="font-size: 32px; font-weight:800; color:{color}; text-align:center;">{a['prob']}%</div>
            <div class="asset-footer">
                <span>{mensaje_entrada}</span>
                <span>⏳ Vence: {tiempo_salida.strftime('%H:%M:%S')}</span>
            </div>
            <div style="display:flex; justify-content:space-between; margin-top:15px; color:#AAA;">
                <span>Precio: {a['precio']:.5f}</span>
                <span>RSI: {a['rsi']:.1f}</span>
                <span>Vol: {a['volume_ratio']:.1f}x</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("No se encontró ningún activo con datos suficientes para 1 min.")

    # Botón manual de actualización (por si acaso)
    if st.button("🔄 Actualizar ahora"):
        st.rerun()

if __name__ == "__main__":
    main()
