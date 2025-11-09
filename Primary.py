import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
from datetime import datetime, timedelta

st.set_page_config(page_title="PH Weather & Hazards", page_icon="🌏", layout="wide")

# ---------------- Configuration ----------------
WEATHERAPI_KEY = "01cce600297f40debe2164114250911"

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
def get_weather_current(lat, lon):
    """Fetch current weather from WeatherAPI"""
    try:
        r = requests.get(
            "http://api.weatherapi.com/v1/current.json",
            params={
                "key": WEATHERAPI_KEY,
                "q": f"{lat},{lon}",
                "aqi": "yes"
            },
            timeout=20
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Weather API error: {e}")
        return None

@st.cache_data(ttl=600)  # 10 minutes
def get_weather_forecast(lat, lon, days=7):
    """Fetch forecast weather from WeatherAPI"""
    try:
        r = requests.get(
            "http://api.weatherapi.com/v1/forecast.json",
            params={
                "key": WEATHERAPI_KEY,
                "q": f"{lat},{lon}",
                "days": days,
                "aqi": "yes",
                "alerts": "yes"
            },
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

st.sidebar.markdown("---")
st.sidebar.caption("**Data Sources:**")
st.sidebar.caption("• Weather: WeatherAPI.com")
st.sidebar.caption("• Hazards: MGB, PHIVOLCS, PAGASA, GDACS")
st.sidebar.caption(f"Last updated: {datetime.now().strftime('%I:%M %p')}")

# ---------------- Main Content ----------------
st.title("🌏 PH Weather & Hazard Monitor")
st.markdown("Real-time weather forecasts and hazard mapping for the Philippines")

# Weather display
col1, col2 = st.columns([2, 1])

with col1:
    st.markdown("### 🌤️ Weather Forecast")
    
    if forecast_type == "Current":
        weather_data = get_weather_current(lat, lon)
        
        if weather_data:
            current = weather_data.get("current", {})
            location = weather_data.get("location", {})
            
            # Location info
            st.caption(f"📍 {location.get('name', '')}, {location.get('region', '')}, {location.get('country', '')}")
            st.caption(f"🕐 Local time: {location.get('localtime', '')}")
            
            # Main metrics
            metric_cols = st.columns(4)
            with metric_cols[0]:
                st.metric("🌡️ Temperature", f"{current.get('temp_c', 'N/A')}°C", 
                         delta=f"Feels like {current.get('feelslike_c', 'N/A')}°C")
            with metric_cols[1]:
                st.metric("💧 Humidity", f"{current.get('humidity', 'N/A')}%")
            with metric_cols[2]:
                st.metric("💨 Wind", f"{current.get('wind_kph', 'N/A')} km/h",
                         delta=current.get('wind_dir', ''))
            with metric_cols[3]:
                st.metric("🌧️ Precipitation", f"{current.get('precip_mm', 'N/A')} mm")
            
            # Additional metrics
            metric_cols2 = st.columns(4)
            with metric_cols2[0]:
                st.metric("☁️ Cloud Cover", f"{current.get('cloud', 'N/A')}%")
            with metric_cols2[1]:
                st.metric("👁️ Visibility", f"{current.get('vis_km', 'N/A')} km")
            with metric_cols2[2]:
                st.metric("🌡️ Pressure", f"{current.get('pressure_mb', 'N/A')} mb")
            with metric_cols2[3]:
                st.metric("☀️ UV Index", f"{current.get('uv', 'N/A')}")
            
            # Condition
            condition = current.get("condition", {})
            st.info(f"**Current Conditions:** {condition.get('text', 'N/A')}")
            
            # Air Quality if available
            if current.get('air_quality'):
                aqi = current['air_quality']
                st.markdown("#### 🌫️ Air Quality")
                aqi_cols = st.columns(3)
                with aqi_cols[0]:
                    st.metric("PM2.5", f"{aqi.get('pm2_5', 'N/A'):.1f}")
                with aqi_cols[1]:
                    st.metric("PM10", f"{aqi.get('pm10', 'N/A'):.1f}")
                with aqi_cols[2]:
                    st.metric("US EPA Index", f"{aqi.get('us-epa-index', 'N/A')}")
    
    elif forecast_type == "Hourly (48h)":
        weather_data = get_weather_forecast(lat, lon, days=3)
        
        if weather_data:
            forecast = weather_data.get("forecast", {}).get("forecastday", [])
            
            # Build hourly dataframe
            hourly_data = []
            for day in forecast:
                for hour in day.get("hour", []):
                    hourly_data.append({
                        "time": hour.get("time"),
                        "temp_c": hour.get("temp_c"),
                        "feelslike_c": hour.get("feelslike_c"),
                        "humidity": hour.get("humidity"),
                        "precip_mm": hour.get("precip_mm"),
                        "wind_kph": hour.get("wind_kph"),
                        "condition": hour.get("condition", {}).get("text"),
                        "chance_of_rain": hour.get("chance_of_rain")
                    })
            
            df = pd.DataFrame(hourly_data[:48])  # Limit to 48 hours
            df["time"] = pd.to_datetime(df["time"])
            
            tab1, tab2 = st.tabs(["📊 Charts", "📋 Table"])
            
            with tab1:
                st.markdown("**Temperature & Feels Like**")
                st.line_chart(df.set_index("time")[["temp_c", "feelslike_c"]], height=250)
                
                st.markdown("**Precipitation & Rain Chance**")
                chart_cols = st.columns(2)
                with chart_cols[0]:
                    st.line_chart(df.set_index("time")[["precip_mm"]], height=200)
                with chart_cols[1]:
                    st.line_chart(df.set_index("time")[["chance_of_rain"]], height=200)
            
            with tab2:
                st.dataframe(
                    df,
                    column_config={
                        "time": st.column_config.DatetimeColumn("Time", format="MMM D, h:mm a"),
                        "temp_c": st.column_config.NumberColumn("Temp (°C)", format="%.1f"),
                        "feelslike_c": st.column_config.NumberColumn("Feels (°C)", format="%.1f"),
                        "humidity": st.column_config.NumberColumn("Humidity (%)", format="%.0f"),
                        "precip_mm": st.column_config.NumberColumn("Rain (mm)", format="%.1f"),
                        "wind_kph": st.column_config.NumberColumn("Wind (km/h)", format="%.1f"),
                        "chance_of_rain": st.column_config.NumberColumn("Rain Chance (%)", format="%.0f"),
                        "condition": "Conditions"
                    },
                    hide_index=True,
                    use_container_width=True
                )
    
    else:  # Daily (7d)
        weather_data = get_weather_forecast(lat, lon, days=7)
        
        if weather_data:
            forecast = weather_data.get("forecast", {}).get("forecastday", [])
            
            # Build daily dataframe
            daily_data = []
            for day in forecast:
                day_data = day.get("day", {})
                daily_data.append({
                    "date": day.get("date"),
                    "maxtemp_c": day_data.get("maxtemp_c"),
                    "mintemp_c": day_data.get("mintemp_c"),
                    "avgtemp_c": day_data.get("avgtemp_c"),
                    "totalprecip_mm": day_data.get("totalprecip_mm"),
                    "avghumidity": day_data.get("avghumidity"),
                    "maxwind_kph": day_data.get("maxwind_kph"),
                    "condition": day_data.get("condition", {}).get("text"),
                    "daily_chance_of_rain": day_data.get("daily_chance_of_rain"),
                    "uv": day_data.get("uv")
                })
            
            df = pd.DataFrame(daily_data)
            df["date"] = pd.to_datetime(df["date"])
            
            tab1, tab2 = st.tabs(["📊 Charts", "📋 Table"])
            
            with tab1:
                st.markdown("**Temperature Range**")
                st.line_chart(df.set_index("date")[["maxtemp_c", "mintemp_c", "avgtemp_c"]], height=250)
                
                st.markdown("**Precipitation & Rain Chance**")
                chart_cols = st.columns(2)
                with chart_cols[0]:
                    st.bar_chart(df.set_index("date")[["totalprecip_mm"]], height=200)
                with chart_cols[1]:
                    st.line_chart(df.set_index("date")[["daily_chance_of_rain"]], height=200)
            
            with tab2:
                st.dataframe(
                    df,
                    column_config={
                        "date": st.column_config.DatetimeColumn("Date", format="MMM D, YYYY"),
                        "maxtemp_c": st.column_config.NumberColumn("Max °C", format="%.1f"),
                        "mintemp_c": st.column_config.NumberColumn("Min °C", format="%.1f"),
                        "avgtemp_c": st.column_config.NumberColumn("Avg °C", format="%.1f"),
                        "totalprecip_mm": st.column_config.NumberColumn("Rain (mm)", format="%.1f"),
                        "avghumidity": st.column_config.NumberColumn("Humidity (%)", format="%.0f"),
                        "maxwind_kph": st.column_config.NumberColumn("Max Wind (km/h)", format="%.1f"),
                        "daily_chance_of_rain": st.column_config.NumberColumn("Rain Chance (%)", format="%.0f"),
                        "uv": st.column_config.NumberColumn("UV Index", format="%.1f"),
                        "condition": "Conditions"
                    },
                    hide_index=True,
                    use_container_width=True
                )
            
            # Weather alerts if available
            alerts = weather_data.get("alerts", {}).get("alert", [])
            if alerts:
                st.markdown("#### ⚠️ Weather Alerts")
                for alert in alerts:
                    st.warning(f"**{alert.get('headline')}**\n\n{alert.get('desc', '')}")

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

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 20px;'>
    <p><strong>Philippine Weather & Hazard Monitor</strong></p>
    <p>Weather Data: WeatherAPI.com | Hazards: MGB, PHIVOLCS, PAGASA, GDACS</p>
    <p style='font-size: 0.8em;'>For emergency situations, always follow official government advisories</p>
</div>
""", unsafe_allow_html=True)
