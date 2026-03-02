"""
BOT DE TRADING PROFESIONAL PARA IQ OPTION - VERSIÓN SIMPLIFICADA
Características:
- Actualización automática cada 10 segundos (autorefresh)
- Reloj en tiempo real
- 1 panel: activo más confiable con vencimiento de 5 minutos
- Escaneo completo de activos OTC o Normal según selección
- Estrategias robustas con volumen simulado si es necesario
- Notificación 1 minuto antes de la operación
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
    page_title="IQ Option Scanner 5min",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Autorefresh cada 10 segundos
count = st_autorefresh(interval=10000, key="autorefresh")

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
        padding: 30px;
        box-shadow: 0 25px 45px -15px rgba(0, 255, 136, 0.3);
        border: 1px solid #00FF8844;
        margin: 20px 0;
    }
    .asset-name {
        font-size: 28px;
        font-weight: 700;
        color: #FFFFFF;
        margin-bottom: 15px;
    }
    .asset-signal {
        font-size: 24px;
        font-weight: 700;
        padding: 15px;
        border-radius: 50px;
        text-align: center;
        margin: 20px 0;
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
        font-size: 18px;
        color: #AAA;
        display: flex;
        justify-content: space-between;
        margin-top: 20px;
        padding-top: 20px;
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
        font-size: 16px;
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
    .metric-box {
        background: #151A24;
        border-radius: 20px;
        padding: 10px;
        text-align: center;
        border: 1px solid #00FF8844;
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
            velas = self.api.get_candles(activo, 60, limite * 5, time.time())
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
            # Si el intervalo es 5, ya vienen de 5 minutos? No, vienen de 1 minuto, así que resampleamos
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

# === ESCANEO COMPLETO ===
def escanear(connector, mercado, max_activos=50):
    activos = connector.obtener_activos_disponibles(mercado, max_activos)
    if not activos:
        return None
    mejor = None
    max_score = -1
    total = len(activos)
    progreso = st.progress(0)
    for i, act in enumerate(activos):
        time.sleep(0.1)
        res = analizar_5min(act, connector)
        if res and res['score'] > max_score:
            max_score = res['score']
            mejor = res
        progreso.progress((i+1)/total)
    progreso.empty()
    return mejor

# === INTERFAZ PRINCIPAL ===
def main():
    # Inicializar estado
    if 'connector' not in st.session_state:
        st.session_state.connector = IQOptionConnector()
    if 'conectado' not in st.session_state:
        st.session_state.conectado = False
    if 'mejor_activo' not in st.session_state:
        st.session_state.mejor_activo = None
    if 'mercado_actual' not in st.session_state:
        st.session_state.mercado_actual = "otc"
    if 'notificadas' not in st.session_state:
        st.session_state.notificadas = set()

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
                st.session_state.mejor_activo = None
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

            if st.button("🔍 ANALIZAR AHORA", use_container_width=True):
                with st.spinner("Escaneando activos..."):
                    mejor = escanear(st.session_state.connector, st.session_state.mercado_actual, max_activos=50)
                    st.session_state.mejor_activo = mejor
                    st.session_state.notificadas = set()
                    if mejor:
                        st.success(f"✅ Activo encontrado: {mejor['activo']}")
                    else:
                        st.warning("No se encontró ningún activo con datos suficientes.")
                    st.rerun()

            st.caption("El análisis se actualiza automáticamente cada 10 segundos.")

    # Verificar conexión
    if not st.session_state.conectado:
        st.info("👆 Conéctate a IQ Option en la barra lateral.")
        return

    # Reloj en tiempo real
    ahora = datetime.now(ecuador_tz)
    st.markdown(f"<div class='reloj'>⏰ {ahora.strftime('%H:%M:%S')} ECU</div>", unsafe_allow_html=True)

    # Escaneo automático (se ejecuta en cada autorefresh)
    with st.spinner("Analizando mercado..."):
        mejor = escanear(st.session_state.connector, st.session_state.mercado_actual, max_activos=50)
        if mejor:
            st.session_state.mejor_activo = mejor
        else:
            st.session_state.mejor_activo = None

    # === ACTIVO MÁS CONFIABLE ===
    st.markdown("## 🎯 Activo más confiable - Vencimiento 5 minutos")

    if st.session_state.mejor_activo:
        a = st.session_state.mejor_activo
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
            if clave not in st.session_state.notificadas:
                st.toast(f"📢 **¡ATENCIÓN!** Opera a las {tiempo_entrada.strftime('%H:%M')} – {nombre} – {a['senal']}", icon="⏰")
                st.session_state.notificadas.add(clave)

        st.markdown(f"""
        <div class="asset-card">
            <div class="asset-name">
                {nombre} <span class="badge-5min">5 MIN</span>
                <span style="float:right; font-size:18px;">Score: {a['score']:.0f}</span>
            </div>
            <div class="asset-signal {signal_class}">{a['senal'] if a['senal'] else 'NEUTRAL'}</div>
            <div style="font-size: 48px; font-weight:800; color:{color}; text-align:center;">{a['prob']}%</div>
            <div class="asset-footer">
                <span>⏰ Entrada: {tiempo_entrada.strftime('%H:%M')}</span>
                <span>⏳ Vence: {tiempo_salida.strftime('%H:%M')}</span>
            </div>
            <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:10px; margin-top:20px;">
                <div class="metric-box">Precio<br><b>{a['precio']:.5f}</b></div>
                <div class="metric-box">RSI<br><b>{a['rsi']:.1f}</b></div>
                <div class="metric-box">Volumen<br><b>{a['volume_ratio']:.1f}x</b></div>
                <div class="metric-box">ADX<br><b>{a['adx']:.1f}</b></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Gráfico opcional
        if st.checkbox("📉 Mostrar gráfico de velas"):
            df_graf = a['df'].iloc[-30:].copy()
            fig = go.Figure(data=[go.Candlestick(x=df_graf.index,
                                                  open=df_graf['open'],
                                                  high=df_graf['high'],
                                                  low=df_graf['low'],
                                                  close=df_graf['close'],
                                                  increasing_line_color='#00FF88',
                                                  decreasing_line_color='#FF4646')])
            fig.add_trace(go.Scatter(x=df_graf.index, y=df_graf['ema_20'],
                                      line=dict(color='blue', width=1), name="EMA 20"))
            fig.add_trace(go.Scatter(x=df_graf.index, y=df_graf['ema_50'],
                                      line=dict(color='orange', width=1), name="EMA 50"))
            fig.update_layout(template="plotly_dark", height=500, margin=dict(l=0,r=0,t=30,b=0))
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No se encontró ningún activo con datos suficientes en este momento.")

    # Botón manual de actualización
    if st.button("🔄 Actualizar ahora"):
        st.rerun()

if __name__ == "__main__":
    main()
