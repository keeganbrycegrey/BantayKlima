import streamlit as st
import requests
import pandas as pd
import pydeck as pdk

st.set_page_config(page_title="PH Weather & Hazard Monitor", page_icon="🌏", layout="wide")

# -----------------------------------------------------------
# Sidebar Inputs
# -----------------------------------------------------------
st.sidebar.title("🇵🇭 PH Weather + Hazard Monitoring")

place = st.sidebar.text_input("City / Municipality (optional)")

lat = st.sidebar.number_input("Latitude", value=14.5995, format="%.6f")
lon = st.sidebar.number_input("Longitude", value=120.9842, format="%.6f")

forecast_type = st.sidebar.radio("Forecast Type", 
                                 ["Current Weather", "Hourly Forecast", "Daily Forecast"])

hazards_enabled = st.sidebar.multiselect(
    "Hazards to Display",
    ["Flood", "Landslide", "Tsunami", "Typhoon Track", "Rainfall Radar"],
    default=["Flood", "Landslide", "Typhoon Track"]
)

st.sidebar.markdown("---")
st.sidebar.caption("Weather: Open-Meteo | Hazards: Public ArcGIS / GDACS (no API key)")

# -----------------------------------------------------------
# Geocoding (Open-Meteo)
# -----------------------------------------------------------
def geocode(query):
    url = "https://geocoding-api.open-meteo.com/v1/search"
    r = requests.get(url, params={"name": query, "count": 1})
    if r.status_code == 200:
        results = r.json().get("results", [])
        if results:
            return results[0]["latitude"], results[0]["longitude"], results[0]["name"]
    return None

if place:
    geo = geocode(place)
    if geo:
        lat, lon, resolved_name = geo
        st.sidebar.success(f"Location matched: {resolved_name}")
    else:
        st.sidebar.error("Location not found. Using manual lat/lon.")

# -----------------------------------------------------------
# Weather API – Open-Meteo
# -----------------------------------------------------------
BASE_URL = "https://api.open-meteo.com/v1/forecast"

def get_weather(lat, lon, hourly=None, daily=None, current=True):
    params = {"latitude": lat, "longitude": lon, "timezone": "Asia/Manila"}

    if current:
        params["current"] = "temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m"
    if hourly:
        params["hourly"] = hourly
    if daily:
        params["daily"] = daily

    r = requests.get(BASE_URL, params=params)
    r.raise_for_status()
    return r.json()

# -----------------------------------------------------------
# Hazard API calls (public ArcGIS)
# -----------------------------------------------------------
def arcgis_geojson(url):
    r = requests.get(url, params={
        "where": "1=1",
        "outFields": "*",
        "f": "geojson",
        "returnGeometry": "true"
    })
    if r.status_code == 200:
        return r.json()
    return {"features": []}

# ✅ Flood Susceptibility (public)
FLOOD_URL = "https://geoportal1-philippines-arcgis.com/arcgis/rest/services/MGB/Flood_Susceptibility/MapServer/0/query"

# ✅ Landslide Susceptibility
LANDSLIDE_URL = "https://geoportal1-philippines-arcgis.com/arcgis/rest/services/MGB/Landslide_Susceptibility/MapServer/0/query"

# ✅ Tsunami Zones (PHIVOLCS public)
TSUNAMI_URL = "https://hazardhunter.georisk.gov.ph/server/rest/services/Tsunami/Tsunami_Hazard/MapServer/0/query"

# ✅ Rainfall Radar
RAINFALL_URL = "https://portal.georisk.gov.ph/arcgis/rest/services/PAGASA/PAGASA/MapServer/0/query"

# ✅ Typhoon Tracks – GDACS (no token)
def fetch_typhoon_tracks():
    url = "https://www.gdacs.org/gdacsapi/api/TC/get?eventlist=ongoing"
    r = requests.get(url)
    if r.status_code == 200:
        return r.json().get("features", [])
    return []

# -----------------------------------------------------------
# MAIN APP DISPLAY
# -----------------------------------------------------------
st.title("🌏 PH Weather + Hazard Monitor (Open Data)")
st.caption("No API keys required — fully open and free data sources.")

# WEATHER SECTION
try:
    if forecast_type == "Current Weather":
        data = get_weather(lat, lon, current=True)
        cur = data.get("current", {})

        st.subheader("🌡️ Current Conditions")
        st.metric("Temperature", f"{cur.get('temperature_2m','?')} °C")
        st.metric("Feels Like", f"{cur.get('apparent_temperature','?')} °C")
        st.metric("Humidity", f"{cur.get('relative_humidity_2m','?')} %")
        st.metric("Wind Speed", f"{cur.get('wind_speed_10m','?')} km/h")

    elif forecast_type == "Hourly Forecast":
        st.subheader("📅 Hourly Forecast (Next 48h)")
        data = get_weather(lat, lon, hourly="temperature_2m,precipitation,wind_speed_10m")
        df = pd.DataFrame(data["hourly"])
        df["time"] = pd.to_datetime(df["time"])
        st.line_chart(df.set_index("time"))

    else:
        st.subheader("📆 Daily Forecast (7 Days)")
        data = get_weather(
            lat, lon,
            daily="temperature_2m_max,temperature_2m_min,precipitation_sum"
        )
        df = pd.DataFrame(data["daily"])
        df["time"] = pd.to_datetime(df["time"])
        st.line_chart(df.set_index("time"))

except Exception as e:
    st.error(f"Weather error: {e}")

# -----------------------------------------------------------
# HAZARD LAYERS
# -----------------------------------------------------------
st.markdown("## 🛑 Hazard Map (PH)")

hazard_layers = []

# Hazard: Flood
if "Flood" in hazards_enabled:
    flood = arcgis_geojson(FLOOD_URL)
    hazard_layers.append(
        pdk.Layer(
            "GeoJsonLayer",
            data=flood,
            opacity=0.3,
        )
    )

# Hazard: Landslide
if "Landslide" in hazards_enabled:
    landslide = arcgis_geojson(LANDSLIDE_URL)
    hazard_layers.append(
        pdk.Layer(
            "GeoJsonLayer",
            data=landslide,
            opacity=0.3,
        )
    )

# Hazard: Tsunami
if "Tsunami" in hazards_enabled:
    tsunami = arcgis_geojson(TSUNAMI_URL)
    hazard_layers.append(
        pdk.Layer(
            "GeoJsonLayer",
            data=tsunami,
            opacity=0.3,
        )
    )

# Hazard: Rainfall Radar
if "Rainfall Radar" in hazards_enabled:
    rain = arcgis_geojson(RAINFALL_URL)
    hazard_layers.append(
        pdk.Layer(
            "GeoJsonLayer",
            data=rain,
            opacity=0.3,
        )
    )

# Hazard: Typhoon Tracks
if "Typhoon Track" in hazards_enabled:
    storms = fetch_typhoon_tracks()
    hazard_layers.append(
        pdk.Layer(
            "GeoJsonLayer",
            data={"type":"FeatureCollection", "features": storms},
            stroked=True,
            lineWidthMinPixels=3,
        )
    )

# Add point for selected location
hazard_layers.append(
    pdk.Layer(
        "ScatterplotLayer",
        data=[{"lat": lat, "lon": lon}],
        get_position='[lon, lat]',
        get_radius=3000,
    )
)

# Render map
hazard_map = pdk.Deck(
    initial_view_state=pdk.ViewState(
        latitude=lat,
        longitude=lon,
        zoom=8
    ),
    layers=hazard_layers
)

st.pydeck_chart(hazard_map)

st.markdown("---")
st.caption("Hazard Sources: PHIVOLCS, PAGASA ArcGIS, GeoRiskPH, GDACS (no API key).")
