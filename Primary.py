import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
import streamlit.components.v1 as components
from datetime import datetime, timedelta
import time

st.set_page_config(page_title="PH Weather & Hazards", page_icon="🌏", layout="wide")

# ---------------- Cache Configuration ----------------
@st.cache_data(ttl=300)  # 5 minutes
def geocode(query):
    """Geocode location with caching"""
    try:
        r = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": query, "count": 1},
            timeout=10
        )
        r.raise_for_status()
        results = r.json().get("results")
        if results:
            return results[0]["latitude"], results[0]["longitude"], results[0]["name"]
    except Exception as e:
        st.error(f"Geocoding error: {e}")
        return None
    return None

@st.cache_data(ttl=600)  # 10 minutes
def get_weather(lat, lon, hourly=None, daily=None, current=True):
    """Fetch weather data with caching"""
    params = {
        "latitude": lat,
        "longitude": lon,
        "timezone": "Asia/Manila"
    }
    if current:
        params["current_weather"] = True
    if hourly:
        params["hourly"] = hourly
    if daily:
        params["daily"] = daily
    
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params=params,
            timeout=20
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Weather API error: {e}")
        return None

@st.cache_data(ttl=1800)  # 30 minutes
def arcgis_geojson(url, fallback=None):
    """Fetch ArcGIS GeoJSON with fallback"""
    try:
        r = requests.get(url, params={
            "where": "1=1",
            "outFields": "*",
            "f": "geojson",
            "returnGeometry": "true",
            "resultRecordCount": 1000  # Limit results
        }, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        if fallback:
            try:
                r = requests.get(fallback, timeout=20)
                r.raise_for_status()
                return r.json()
            except:
                pass
        return {"type": "FeatureCollection", "features": []}

@st.cache_data(ttl=3600)  # 1 hour
def fetch_typhoon_tracks():
    """Fetch typhoon tracks from GDACS"""
    try:
        r = requests.get(
            "https://www.gdacs.org/gdacsapi/api/TC/get?eventlist=ongoing",
            timeout=20
        )
        r.raise_for_status()
        data = r.json()
        return data.get("features", [])
    except Exception as e:
        st.warning(f"Could not fetch typhoon tracks: {e}")
        return []

# ---------------- Hazard URLs ----------------
FLOOD_URL = "https://controlmap.mgb.gov.ph/arcgis/rest/services/GeospatialDataInventory/GDI_Detailed_Flood_Susceptibility/FeatureServer/0/query"
LANDSLIDE_URL = "https://hazardhunter.georisk.gov.ph/server/rest/services/Landslide/Rain_Induced_Landslide_Hazard/MapServer/0/query"
TSUNAMI_URL = "https://hazardhunter.georisk.gov.ph/server/rest/services/Tsunami/Tsunami_Hazard/MapServer/0/query"
RAINFALL_URL = "https://portal.georisk.gov.ph/arcgis/rest/services/PAGASA/PAGASA/MapServer/0/query"

# ---------------- Sidebar ----------------
st.sidebar.title("🇵🇭 PH Weather + Hazards")
st.sidebar.markdown("### 📍 Location")

# Location input
place = st.sidebar.text_input("City / Municipality", placeholder="e.g., Manila, Cebu, Davao")
col1, col2 = st.sidebar.columns(2)
with col1:
    lat = st.number_input("Latitude", value=14.5995, format="%.6f", key="lat")
with col2:
    lon = st.number_input("Longitude", value=120.9842, format="%.6f", key="lon")

# Geocoding
if place:
    with st.spinner("🔍 Finding location..."):
        geo = geocode(place)
        if geo:
            lat, lon, resolved_name = geo
            st.sidebar.success(f"✓ {resolved_name}")
            st.session_state['lat'] = lat
            st.session_state['lon'] = lon
        else:
            st.sidebar.error("❌ Location not found")

st.sidebar.markdown("### 🌤️ Weather")
forecast_type = st.sidebar.radio(
    "Forecast Type",
    ["Current", "Hourly (48h)", "Daily (7d)"],
    label_visibility="collapsed"
)

st.sidebar.markdown("### 🛑 Hazard Layers")
hazards_enabled = st.sidebar.multiselect(
    "Select hazards to display",
    ["Flood", "Landslide", "Tsunami", "Typhoon Track", "Rainfall"],
    default=["Flood", "Typhoon Track"],
    label_visibility="collapsed"
)

st.sidebar.markdown("### 🌬️ Windy Layer")
windy_layer = st.sidebar.selectbox(
    "Map overlay",
    ["wind", "precipitation", "temperature", "clouds", "pressure"],
    label_visibility="collapsed"
)

st.sidebar.markdown("---")
st.sidebar.caption("**Data Sources:**")
st.sidebar.caption("• Weather: Open-Meteo + Windy")
st.sidebar.caption("• Hazards: MGB, PHIVOLCS, PAGASA, GDACS")
st.sidebar.caption(f"Last updated: {datetime.now().strftime('%I:%M %p')}")

# ---------------- Main Content ----------------
st.title("🌏 PH Weather & Hazard Monitor")
st.markdown("Real-time weather forecasts and hazard mapping for the Philippines")

# Weather display
col1, col2 = st.columns([2, 1])

with col1:
    st.markdown("### 🌤️ Weather Forecast")
    
    weather_data = get_weather(
        lat, lon,
        hourly="temperature_2m,precipitation,wind_speed_10m,relative_humidity_2m" if forecast_type == "Hourly (48h)" else None,
        daily="temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max" if forecast_type == "Daily (7d)" else None,
        current=True
    )
    
    if weather_data:
        if forecast_type == "Current":
            cw = weather_data.get("current_weather", {})
            metric_cols = st.columns(4)
            with metric_cols[0]:
                st.metric("🌡️ Temperature", f"{cw.get('temperature', 'N/A')}°C")
            with metric_cols[1]:
                st.metric("💨 Wind Speed", f"{cw.get('windspeed', 'N/A')} km/h")
            with metric_cols[2]:
                st.metric("🧭 Direction", f"{cw.get('winddirection', 'N/A')}°")
            with metric_cols[3]:
                weather_code = cw.get('weathercode', 0)
                st.metric("☁️ Conditions", f"Code {weather_code}")
        
        elif forecast_type == "Hourly (48h)":
            df = pd.DataFrame(weather_data["hourly"])
            df["time"] = pd.to_datetime(df["time"])
            
            tab1, tab2 = st.tabs(["📊 Chart", "📋 Table"])
            with tab1:
                st.line_chart(
                    df.set_index("time")[["temperature_2m", "precipitation", "wind_speed_10m"]],
                    height=300
                )
            with tab2:
                st.dataframe(
                    df.head(24),
                    column_config={
                        "time": st.column_config.DatetimeColumn("Time", format="MMM D, h:mm a"),
                        "temperature_2m": st.column_config.NumberColumn("Temp (°C)", format="%.1f"),
                        "precipitation": st.column_config.NumberColumn("Rain (mm)", format="%.1f"),
                        "wind_speed_10m": st.column_config.NumberColumn("Wind (km/h)", format="%.1f")
                    },
                    hide_index=True,
                    use_container_width=True
                )
        
        else:  # Daily
            df = pd.DataFrame(weather_data["daily"])
            df["time"] = pd.to_datetime(df["time"])
            
            tab1, tab2 = st.tabs(["📊 Chart", "📋 Table"])
            with tab1:
                st.line_chart(
                    df.set_index("time")[["temperature_2m_max", "temperature_2m_min", "precipitation_sum"]],
                    height=300
                )
            with tab2:
                st.dataframe(
                    df,
                    column_config={
                        "time": st.column_config.DatetimeColumn("Date", format="MMM D, YYYY"),
                        "temperature_2m_max": st.column_config.NumberColumn("Max °C", format="%.1f"),
                        "temperature_2m_min": st.column_config.NumberColumn("Min °C", format="%.1f"),
                        "precipitation_sum": st.column_config.NumberColumn("Rain (mm)", format="%.1f")
                    },
                    hide_index=True,
                    use_container_width=True
                )

with col2:
    st.markdown("### ⚠️ Active Hazards")
    
    hazard_count = len(hazards_enabled)
    if hazard_count > 0:
        st.info(f"Displaying {hazard_count} hazard layer(s)")
        for hazard in hazards_enabled:
            if hazard == "Typhoon Track":
                st.warning("🌀 Typhoon Track Active")
            elif hazard == "Flood":
                st.error("🌊 Flood Susceptibility")
            elif hazard == "Landslide":
                st.error("⛰️ Landslide Risk")
            elif hazard == "Tsunami":
                st.warning("🌊 Tsunami Zones")
            elif hazard == "Rainfall":
                st.info("🌧️ Rainfall Radar")
    else:
        st.success("No hazard layers selected")

# Hazard Map
st.markdown("---")
st.markdown("### 🗺️ Interactive Hazard Map")

with st.spinner("Loading hazard data..."):
    layers = []
    
    if "Flood" in hazards_enabled:
        flood_geo = arcgis_geojson(FLOOD_URL)
        if flood_geo.get("features"):
            layers.append(pdk.Layer(
                "GeoJsonLayer",
                data=flood_geo,
                opacity=0.5,
                stroked=True,
                filled=True,
                pickable=True,
                get_fill_color="[100, 100, 255, 180]",
                get_line_color=[0, 0, 255],
                line_width_min_pixels=1,
                auto_highlight=True
            ))
    
    if "Landslide" in hazards_enabled:
        landslide_geo = arcgis_geojson(LANDSLIDE_URL)
        if landslide_geo.get("features"):
            layers.append(pdk.Layer(
                "GeoJsonLayer",
                data=landslide_geo,
                opacity=0.5,
                stroked=True,
                filled=True,
                pickable=True,
                get_fill_color="[255, 165, 0, 180]",
                get_line_color=[255, 100, 0],
                line_width_min_pixels=1,
                auto_highlight=True
            ))
    
    if "Tsunami" in hazards_enabled:
        tsunami_geo = arcgis_geojson(TSUNAMI_URL)
        if tsunami_geo.get("features"):
            layers.append(pdk.Layer(
                "GeoJsonLayer",
                data=tsunami_geo,
                opacity=0.4,
                stroked=True,
                filled=True,
                pickable=True,
                get_fill_color="[255, 0, 0, 150]",
                get_line_color=[200, 0, 0],
                line_width_min_pixels=1,
                auto_highlight=True
            ))
    
    if "Rainfall" in hazards_enabled:
        rain_geo = arcgis_geojson(RAINFALL_URL)
        if rain_geo.get("features"):
            layers.append(pdk.Layer(
                "GeoJsonLayer",
                data=rain_geo,
                opacity=0.4,
                stroked=True,
                filled=True,
                pickable=True,
                get_fill_color="[0, 150, 255, 150]",
                get_line_color=[0, 100, 200],
                line_width_min_pixels=1,
                auto_highlight=True
            ))
    
    if "Typhoon Track" in hazards_enabled:
        track_feats = fetch_typhoon_tracks()
        if track_feats:
            layers.append(pdk.Layer(
                "GeoJsonLayer",
                data={"type": "FeatureCollection", "features": track_feats},
                stroked=True,
                filled=False,
                get_line_color=[255, 0, 0],
                get_line_width=4,
                line_width_min_pixels=2,
                pickable=True
            ))
    
    # User location marker
    layers.append(pdk.Layer(
        "ScatterplotLayer",
        data=[{"lat": lat, "lon": lon}],
        get_position='[lon, lat]',
        get_radius=5000,
        get_fill_color=[255, 0, 0, 200],
        pickable=True
    ))
    
    # Create deck
    deck = pdk.Deck(
        initial_view_state=pdk.ViewState(
            latitude=lat,
            longitude=lon,
            zoom=8,
            pitch=0
        ),
        layers=layers,
        tooltip={"html": "<b>{properties.name}</b><br/>Severity: {properties.severity}"}
    )
    
    st.pydeck_chart(deck, use_container_width=True)

# Windy Map
st.markdown("---")
st.markdown("### 🌬️ Windy Interactive Forecast")

WINDY_MAP_KEY = "lXMiJPbUWVAsVNyIVZVkLPynhrw6pYRP"

windy_html = f"""
<div id="windy" style="width:100%; height:500px; border-radius: 8px; overflow: hidden;"></div>
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
    const {{map, store, picker}} = windyAPI;
    
    // Add click handler for point forecast
    map.on('click', e => {{
      const {{lat, lng}} = e.latlng;
      picker.open({{lat: lat, lon: lng}});
    }});
    
    // Set initial overlay
    store.set('overlay', '{windy_layer}');
  }});
</script>
"""

components.html(windy_html, height=550)

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 20px;'>
    <p><strong>Philippine Weather & Hazard Monitor</strong></p>
    <p>Data Sources: Open-Meteo, Windy, MGB, PHIVOLCS, PAGASA, GDACS</p>
    <p style='font-size: 0.8em;'>For emergency situations, always follow official government advisories</p>
</div>
""", unsafe_allow_html=True)
