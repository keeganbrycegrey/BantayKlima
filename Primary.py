# app.py
import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
import streamlit.components.v1 as components

st.set_page_config(page_title="PH Weather & Hazards", page_icon="🌏", layout="wide")

# ---------------- Sidebar ----------------
st.sidebar.title("🇵🇭 PH Weather + Hazards")
place = st.sidebar.text_input("City / Municipality (optional)")
lat = st.sidebar.number_input("Latitude", value=14.5995, format="%.6f")
lon = st.sidebar.number_input("Longitude", value=120.9842, format="%.6f")
forecast_type = st.sidebar.radio("Forecast Type", ["Current", "Hourly", "Daily"])
hazards_enabled = st.sidebar.multiselect(
    "Hazards to show",
    ["Flood", "Landslide", "Tsunami", "Typhoon Track", "Rainfall Radar"],
    default=["Flood", "Landslide", "Typhoon Track"]
)
windy_layer = st.sidebar.selectbox(
    "Windy Map Layer",
    ["wind", "precipitation", "temperature", "storm"]
)
st.sidebar.markdown("---")
st.sidebar.caption("Weather: Open-Meteo + Windy. Hazards: public ArcGIS / GDACS")

# ---------------- Geocoding ----------------
def geocode(query):
    try:
        r = requests.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": query, "count": 1}, timeout=10)
        r.raise_for_status()
        results = r.json().get("results")
        if results:
            return results[0]["latitude"], results[0]["longitude"], results[0]["name"]
    except:
        return None
    return None

if place:
    geo = geocode(place)
    if geo:
        lat, lon, resolved_name = geo
        st.sidebar.success(f"Location matched: {resolved_name}")
    else:
        st.sidebar.error("Location not found, using manual lat/lon.")

# ---------------- Weather API ----------------
def get_weather(lat, lon, hourly=None, daily=None, current=True):
    params = {"latitude": lat, "longitude": lon, "timezone": "Asia/Manila"}
    if current:
        params["current_weather"] = True
    if hourly:
        params["hourly"] = hourly
    if daily:
        params["daily"] = daily
    r = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=20)
    r.raise_for_status()
    return r.json()

# ---------------- Hazard Layer URLs ----------------
FLOOD_URL = "https://controlmap.mgb.gov.ph/arcgis/rest/services/GeospatialDataInventory/GDI_Detailed_Flood_Susceptibility/FeatureServer/0/query"
LANDSLIDE_URL = "https://hazardhunter.georisk.gov.ph/server/rest/services/Landslide/Rain_Induced_Landslide_Hazard/MapServer/0/query"
TSUNAMI_URL = "https://hazardhunter.georisk.gov.ph/server/rest/services/Tsunami/Tsunami_Hazard/MapServer/0/query"
RAINFALL_URL = "https://portal.georisk.gov.ph/arcgis/rest/services/PAGASA/PAGASA/MapServer/0/query"
TYPHOON_TRACK_URL = "https://www.gdacs.org/gdacsapi/api/TC/get?eventlist=ongoing"

def arcgis_geojson(url):
    try:
        r = requests.get(url, params={
            "where": "1=1",
            "outFields": "*",
            "f": "geojson",
            "returnGeometry": "true"
        }, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.warning(f"Could not fetch layer {url}: {e}")
        return {"features": []}

def fetch_typhoon_tracks():
    try:
        r = requests.get(TYPHOON_TRACK_URL, timeout=20)
        r.raise_for_status()
        return r.json().get("features", [])
    except:
        return []

# ---------------- Main UI ----------------
st.title("🌏 PH Weather & Hazard Monitor")
st.caption("Weather: Open-Meteo + Windy | Hazards: MGB / PHIVOLCS / PAGASA / GDACS")

# ----- Weather Display -----
try:
    if forecast_type == "Current":
        data = get_weather(lat, lon, current=True)
        cw = data.get("current_weather", {})
        st.subheader("🌡️ Current Weather")
        st.metric("Temperature", f"{cw.get('temperature', '?')} °C")
        st.metric("Wind Speed", f"{cw.get('windspeed', '?')} km/h")
        st.metric("Wind Direction", f"{cw.get('winddirection', '?')}°")
    elif forecast_type == "Hourly":
        data = get_weather(lat, lon, hourly="temperature_2m,precipitation,wind_speed_10m")
        df = pd.DataFrame(data["hourly"])
        df["time"] = pd.to_datetime(df["time"])
        st.subheader("📅 Hourly Forecast (48h)")
        st.line_chart(df.set_index("time")[["temperature_2m","precipitation","wind_speed_10m"]])
        st.dataframe(df, use_container_width=True)
    else:
        data = get_weather(lat, lon, daily="temperature_2m_max,temperature_2m_min,precipitation_sum")
        df = pd.DataFrame(data["daily"])
        df["time"] = pd.to_datetime(df["time"])
        st.subheader("📆 Daily Forecast (7d)")
        st.line_chart(df.set_index("time")[["temperature_2m_max","temperature_2m_min","precipitation_sum"]])
        st.dataframe(df, use_container_width=True)
except Exception as e:
    st.error(f"Weather fetch error: {e}")

# ----- Hazard Map -----
st.markdown("## 🛑 Hazard Map Layers")
layers = []

if "Flood" in hazards_enabled:
    flood_geo = arcgis_geojson(FLOOD_URL)
    layers.append(pdk.Layer("GeoJsonLayer", data=flood_geo, opacity=0.4, stroked=False, pickable=True))
if "Landslide" in hazards_enabled:
    landslide_geo = arcgis_geojson(LANDSLIDE_URL)
    layers.append(pdk.Layer("GeoJsonLayer", data=landslide_geo, opacity=0.4, stroked=False, pickable=True))
if "Tsunami" in hazards_enabled:
    tsunami_geo = arcgis_geojson(TSUNAMI_URL)
    layers.append(pdk.Layer("GeoJsonLayer", data=tsunami_geo, opacity=0.4, stroked=False, pickable=True))
if "Rainfall Radar" in hazards_enabled:
    rain_geo = arcgis_geojson(RAINFALL_URL)
    layers.append(pdk.Layer("GeoJsonLayer", data=rain_geo, opacity=0.4, stroked=False, pickable=True))
if "Typhoon Track" in hazards_enabled:
    track_feats = fetch_typhoon_tracks()
    layers.append(pdk.Layer("GeoJsonLayer", data={"type":"FeatureCollection","features": track_feats}, stroked=True, get_line_width=4, pickable=True))

# User location
layers.append(pdk.Layer("ScatterplotLayer", data=[{"lat": lat, "lon": lon}], get_position='[lon, lat]', get_radius=5000, get_fill_color=[255,0,0]))

deck = pdk.Deck(initial_view_state=pdk.ViewState(latitude=lat, longitude=lon, zoom=8), layers=layers)
st.pydeck_chart(deck)

# ----- Windy Map Integration -----
st.markdown("## 🌬️ Windy Interactive Map")
WINDY_MAP_KEY = "lXMiJPbUWVAsVNyIVZVkLPynhrw6pYRP"  # map forecast
WINDY_POINT_KEY = "5reg6zehGFFw3yHplivmOEJQHMALST73"  # point forecast

windy_html = f"""
<div id="windy" style="width:100%; height:500px;"></div>
<script src="https://api.windy.com/assets/map-forecast/libBoot.js"></script>
<script>
  const options = {{
    key: '{WINDY_MAP_KEY}',
    lat: {lat},
    lon: {lon},
    zoom: 6,
    overlay: '{windy_layer}'
  }};
  windyInit(options, windyAPI => {{
    const {{store, picker, utils}} = windyAPI;
    windyAPI.map.on('click', e => {{
      const {{lat, lon}} = e.latlng;
      picker.open({{lat:lat, lon:lon}});
    }});
  }});
</script>
"""
components.html(windy_html, height=550)

st.markdown("---")
st.caption("Hazards: MGB, PHIVOLCS, PAGASA, GDACS. Weather: Open-Meteo + Windy.")
