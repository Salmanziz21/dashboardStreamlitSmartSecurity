# app.py
import streamlit as st
import threading
import time
import json
from collections import deque
from datetime import datetime
import pandas as pd
import paho.mqtt.client as mqtt
from streamlit_autorefresh import st_autorefresh

# ---------------------------
# CONFIG
# ---------------------------
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
TOPIC_SENSOR = "esp32/motion/datasensor"
TOPIC_PRED = "esp32/motion/prediction"

HISTORY_MAX = 2000  # max record historis tersimpan

# Default auto-refresh (ms)
DEFAULT_REFRESH_MS = 1000

# ---------------------------
# SESSION STORAGE (thread-safe-ish)
# ---------------------------
if "mqtt_storage" not in st.session_state:
    st.session_state.mqtt_storage = {
        "sensors": deque(maxlen=HISTORY_MAX),
        "predictions": deque(maxlen=HISTORY_MAX),
        "last_sensor": None,
        "last_prediction": None,
        "connected": False,
        "client": None,
        "last_update": None
    }

storage = st.session_state.mqtt_storage

# ---------------------------
# MQTT CALLBACKS
# ---------------------------
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        storage["connected"] = True
        client.subscribe([(TOPIC_SENSOR, 0), (TOPIC_PRED, 0)])
        print("MQTT connected; subscribed.")
    else:
        storage["connected"] = False
        print("MQTT connect failed:", rc)

def parse_sensor_payload(payload_str):
    try:
        data = json.loads(payload_str)
        ts = data.get("timestamp")
        # convert to server receive time for consistency
        dt = datetime.now()
        item = {
            "timestamp": dt,
            "pir_value": int(data.get("pir_value", 0)),
            "hour": int(data.get("hour", dt.hour)),
            "is_night": int(data.get("is_night", 0))
        }
        return item
    except Exception as e:
        print("parse_sensor_payload error:", e)
        return None

def parse_prediction_payload(payload_str):
    try:
        data = json.loads(payload_str)
        label = None
        confidence = None
        if isinstance(data, dict):
            if "prediction" in data and isinstance(data["prediction"], dict):
                label = data["prediction"].get("label")
                confidence = data["prediction"].get("confidence")
            elif "label" in data:
                label = data.get("label")
                confidence = data.get("confidence")
        if label:
            return {"timestamp": datetime.now(), "label": str(label), "confidence": float(confidence) if confidence is not None else None}
    except Exception:
        text = payload_str.strip()
        mapping = {
            "NO MOTION DETECT": "no_motion",
            "NORMAL MOTION DETECT": "normal_motion",
            "SUSPICIOUS MOTION DETECT": "suspicious_motion"
        }
        label = mapping.get(text.upper(), text.lower().replace(" ", "_"))
        return {"timestamp": datetime.now(), "label": label, "confidence": None}

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode("utf-8", errors="ignore")
    except Exception as e:
        print("decode error:", e)
        return

    topic = msg.topic
    if topic == TOPIC_SENSOR:
        item = parse_sensor_payload(payload)
        if item:
            storage["sensors"].append(item)
            storage["last_sensor"] = item
            storage["last_update"] = datetime.now()
    elif topic == TOPIC_PRED:
        pred = parse_prediction_payload(payload)
        if pred:
            storage["predictions"].append(pred)
            storage["last_prediction"] = pred
            storage["last_update"] = datetime.now()

# ---------------------------
# MQTT CLIENT THREAD
# ---------------------------
def start_mqtt_client():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    except Exception as e:
        print("MQTT connect error:", e)
        storage["connected"] = False
        return
    storage["client"] = client
    client.loop_start()

# Launch MQTT once
if storage.get("client") is None:
    mqtt_thread = threading.Thread(target=start_mqtt_client, daemon=True)
    mqtt_thread.start()
    time.sleep(0.3)

# ---------------------------
# STREAMLIT UI & LAYOUT
# ---------------------------
st.set_page_config(page_title="ESP32 Motion Dashboard", layout="wide", initial_sidebar_state="expanded")
st.markdown("<style> .card {background:#ffffff; padding:12px; border-radius:12px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);} .muted{color:#6c757d; font-size:0.9rem;} </style>", unsafe_allow_html=True)

# Sidebar controls
with st.sidebar:
    st.header("Pengaturan Dashboard")
    refresh_ms = st.slider("Auto-refresh interval (ms)", 250, 5000, DEFAULT_REFRESH_MS, step=250, help="Interval reload UI untuk menampilkan data real-time.")
    st.markdown("---")
    st.write("MQTT Broker")
    st.text_input("Broker", value=MQTT_BROKER, key="broker_input", disabled=True)
    st.write(f"Port: `{MQTT_PORT}`")
    st.markdown("---")
    st.write("Data historis")
    history_points = st.slider("Jumlah titik historis pada chart", min_value=50, max_value=HISTORY_MAX, value=400, step=50)
    if st.button("Bersihkan history lokal"):
        storage["sensors"].clear()
        storage["predictions"].clear()
        storage["last_sensor"] = None
        storage["last_prediction"] = None
        st.success("History dibersihkan")

# Auto refresh trigger (uses streamlit-autorefresh)
# returns an incrementing counter; we don't need the value except to trigger rerun
count = st_autorefresh(interval=refresh_ms, limit=None, key="autorefresh")

# Header
st.title("📡 ESP32 Motion — Dashboard (Realtime MQTT)")
st.markdown("**Realtime monitoring** sensor PIR + hasil prediksi. Data diambil dari MQTT topics `esp32/motion/datasensor` & `esp32/motion/prediction`.")

# Top status cards
col_status_1, col_status_2, col_status_3, col_status_4 = st.columns([1.2,1.2,1.2,1.2])

with col_status_1:
    st.markdown('<div class="card"><h4>🕒 Last update</h4>', unsafe_allow_html=True)
    last_update = storage.get("last_update")
    if last_update:
        st.markdown(f"**{last_update.strftime('%Y-%m-%d %H:%M:%S')}**  \n<span class='muted'>server time</span>", unsafe_allow_html=True)
    else:
        st.markdown("—  \n<span class='muted'>belum ada data</span>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

with col_status_2:
    st.markdown('<div class="card"><h4>🔌 MQTT Status</h4>', unsafe_allow_html=True)
    status_text = "Terhubung" if storage.get("connected") else "Terputus"
    st.markdown(f"**{status_text}**  \n<span class='muted'>broker: {MQTT_BROKER}:{MQTT_PORT}</span>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

with col_status_3:
    st.markdown('<div class="card"><h4>📊 Total sensor</h4>', unsafe_allow_html=True)
    st.markdown(f"**{len(storage['sensors'])}**  \n<span class='muted'>rekaman tersimpan</span>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

with col_status_4:
    st.markdown('<div class="card"><h4>🧠 Total prediksi</h4>', unsafe_allow_html=True)
    st.markdown(f"**{len(storage['predictions'])}**  \n<span class='muted'>rekaman prediksi</span>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("---")

# Main content - two columns: left = charts/tables, right = detail/controls
left, right = st.columns([2.4, 1.0])

with left:
    # Latest sensor & prediction in a neat row
    s1, s2 = st.columns([1,1])
    with s1:
        st.subheader("Latest Sensor")
        last = storage["last_sensor"]
        if last:
            st.metric("pir_value", last["pir_value"], delta=None)
            st.write(f"- hour: **{last['hour']}**  \n- is_night: **{last['is_night']}**")
            st.write(f"⏱ diterima: {last['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            st.info("Belum ada data sensor.")

    with s2:
        st.subheader("Latest Prediction")
        lastp = storage["last_prediction"]
        if lastp:
            conf = f"{lastp['confidence']:.2f}%" if lastp.get("confidence") is not None else "N/A"
            st.metric("Label", lastp["label"], delta=None)
            st.write(f"- Confidence: **{conf}**")
            st.write(f"⏱ diterima: {lastp['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            st.info("Belum ada prediksi.")

    st.markdown("### Grafik Historis — pir_value")
    if len(storage["sensors"]) == 0:
        st.info("Menunggu data sensor...")
    else:
        df_plot = pd.DataFrame([{"timestamp": s["timestamp"], "pir_value": s["pir_value"]} for s in storage["sensors"]])
        df_plot = df_plot.sort_values("timestamp").tail(history_points)
        df_plot = df_plot.set_index("timestamp")
        st.line_chart(df_plot["pir_value"], height=320)

    st.markdown("### Timeline Events (gabungan sensor + prediksi)")
    events = []
    for s in storage["sensors"]:
        events.append({"time": s["timestamp"], "type": "sensor", "value": s["pir_value"], "detail": ""})
    for p in storage["predictions"]:
        events.append({"time": p["timestamp"], "type": "prediction", "value": None, "detail": p["label"]})
    if len(events) == 0:
        st.write("Belum ada events.")
    else:
        df_events = pd.DataFrame(events).sort_values("time").tail(200)
        st.dataframe(df_events.reset_index(drop=True), height=260)

with right:
    st.subheader("Kontrol & Export")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.write("Download data historis sensor (CSV)")
    if len(storage["sensors"]) > 0:
        df_all = pd.DataFrame([{
            "timestamp": s["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
            "pir_value": s["pir_value"],
            "hour": s["hour"],
            "is_night": s["is_night"]
        } for s in list(storage["sensors"])])
        csv = df_all.to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV", csv, "sensors_history.csv", "text/csv")
    else:
        st.write("Belum ada data untuk di-export")

    st.markdown("---")
    st.write("Quick filters")
    if st.button("Tampilkan 10 terakhir sensor"):
        last10 = list(storage["sensors"])[-10:][::-1]
        if last10:
            st.table(pd.DataFrame([{
                "time": s["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
                "pir_value": s["pir_value"],
                "hour": s["hour"]
            } for s in last10]))
        else:
            st.write("Tidak ada data")

    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("---")
st.caption("Dashboard by you — Streamlit + MQTT (improved layout + auto-refresh)")

# Footer debug (small)
with st.expander("Debug info (raw)"):
    st.write("Connected:", storage.get("connected"))
    st.write("Client instance:", bool(storage.get("client")))
    st.write("Sensors stored:", len(storage["sensors"]))
    st.write("Predictions stored:", len(storage["predictions"]))
