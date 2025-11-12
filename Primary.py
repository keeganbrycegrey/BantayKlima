import streamlit as st
import requests
import pandas as pd
import streamlit.components.v1 as components
from datetime import datetime
import os

st.set_page_config(
    page_title="BantayKlima - PH Weather",
    page_icon="🌏",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------- Configuration ----------------
try:
    WEATHERAPI_KEY = st.secrets["WEATHERAPI_KEY"]
    OPENWEATHER_KEY = st.secrets["OPENWEATHER_KEY"]
except (FileNotFoundError, KeyError):
    WEATHERAPI_KEY = os.getenv("WEATHERAPI_KEY")
    OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY")
    
    if not WEATHERAPI_KEY or not OPENWEATHER_KEY:
        st.error("⚠️ **API Keys Not Found!** Please check README.md for setup instructions.")
        st.stop()

# ---------------- Custom CSS ----------------
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.5rem;
    }
</style>
""", unsafe_allow_html=True)

# ---------------- Helper Functions ----------------
def get_weather_icon(condition_text):
    """Map weather condition to emoji"""
    condition = condition_text.lower()
    if "sunny" in condition or "clear" in condition:
        return "☀️"
    elif "partly cloudy" in condition:
        return "⛅"
    elif "cloudy" in condition or "overcast" in condition:
        return "☁️"
    elif "rain" in condition or "drizzle" in condition:
        return "🌧️"
    elif "storm" in condition or "thunder" in condition:
        return "⛈️"
    elif "snow" in condition:
        return "❄️"
    elif "fog" in condition or "mist" in condition:
        return "🌫️"
    return "🌤️"

def format_wind_direction(degrees):
    """Convert wind degrees to cardinal direction"""
    directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                  'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
    idx = int((degrees + 11.25) / 22.5) % 16
    return directions[idx]

# ---------------- Cache Configuration ----------------
@st.cache_data(ttl=300, show_spinner=False)
def geocode(query):
    """Geocode location with caching"""
    try:
        r = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": query, "count": 5},
            timeout=10
        )
        r.raise_for_status()
        return r.json().get("results", [])
    except:
        return []

@st.cache_data(ttl=300, show_spinner=False)
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

@st.cache_data(ttl=300, show_spinner=False)
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
        st.error(f"Forecast API error: {e}")
        return None

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_typhoon_tracks():
    """Fetch typhoon tracks from GDACS"""
    try:
        r = requests.get(
            "https://www.gdacs.org/gdacsapi/api/TC/get?eventlist=ongoing",
            timeout=20
        )
        r.raise_for_status()
        return r.json().get("features", [])
    except:
        return []

# ---------------- Sidebar ----------------
with st.sidebar:
    st.markdown("# 🌏 BantayKlima")
    st.caption("Philippine Weather Monitor")
    st.markdown("---")
    
    # Location Section
    st.markdown("### 📍 Location")
    place = st.text_input("🔍 Search Location", placeholder="Manila, Cebu, Davao...")
    
    # Geocoding with multiple results
    if place:
        with st.spinner("🔍 Searching..."):
            results = geocode(place)
            if results:
                location_options = [f"{r.get('name', '')}, {r.get('admin1', '')} - {r.get('country', '')}" for r in results]
                selected = st.selectbox("Select location:", location_options)
                if selected:
                    idx = location_options.index(selected)
                    lat = results[idx]["latitude"]
                    lon = results[idx]["longitude"]
                    st.success(f"✓ Found!")
            else:
                st.warning("Location not found")
                lat = 14.5995
                lon = 120.9842
    else:
        col1, col2 = st.columns(2)
        with col1:
            lat = st.number_input("Latitude", value=14.5995, format="%.6f")
        with col2:
            lon = st.number_input("Longitude", value=120.9842, format="%.6f")
    
    st.markdown("---")
    
    # Forecast Type
    st.markdown("### 🌤️ Forecast")
    forecast_type = st.radio(
        "Select forecast type:",
        ["Current", "Hourly (48h)", "Daily (7d)"],
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    
    # Weather Map Layers
    st.markdown("### 🗺️ Weather Layers")
    weather_layers = st.multiselect(
        "Select weather overlays:",
        ["Temperature", "Precipitation", "Wind Animation", "Clouds", "Pressure"],
        default=["Temperature"],
        label_visibility="collapsed"
    )
    
    map_opacity = st.slider("Layer Opacity", 0.3, 1.0, 0.6, 0.1)
    
    st.markdown("---")
    
    # Typhoon Tracking
    st.markdown("### 🌀 Typhoon")
    show_typhoons = st.checkbox("Show Active Typhoons", value=True)
    
    st.markdown("---")
    st.caption("**📊 Data Sources:**")
    st.caption("• WeatherAPI.com")
    st.caption("• OpenWeatherMap")
    st.caption("• GDACS")
    st.caption(f"🕐 {datetime.now().strftime('%I:%M %p')}")

# ---------------- Main Content ----------------
st.markdown('<p class="main-header">🌏 BantayKlima</p>', unsafe_allow_html=True)
st.markdown("Real-time Philippine Weather Monitoring System")

# Weather Alerts Banner
weather_check = get_weather_forecast(lat, lon, days=1)
if weather_check:
    alerts = weather_check.get("alerts", {}).get("alert", [])
    if alerts:
        for alert in alerts:
            st.error(f"🚨 **{alert.get('headline', 'Weather Alert')}**")

# Main content tabs
tab1, tab2 = st.tabs(["📊 Weather Forecast", "🗺️ Interactive Map"])

# ---------------- Tab 1: Weather Forecast ----------------
with tab1:
    if forecast_type == "Current":
        weather_data = get_weather_current(lat, lon)
        
        if weather_data:
            current = weather_data.get("current", {})
            location = weather_data.get("location", {})
            condition = current.get("condition", {})
            
            # Location header
            col_h1, col_h2 = st.columns([3, 1])
            with col_h1:
                st.markdown(f"### 📍 {location.get('name', '')}, {location.get('region', '')}")
                st.caption(f"🕐 {location.get('localtime', '')} • {lat:.4f}, {lon:.4f}")
            with col_h2:
                icon = get_weather_icon(condition.get('text', ''))
                st.markdown(f"<div style='text-align:center;font-size:4rem;'>{icon}</div>", unsafe_allow_html=True)
            
            st.markdown(f"### {condition.get('text', 'N/A')}")
            
            # Main metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("🌡️ Temperature", f"{current.get('temp_c', 'N/A')}°C", 
                         delta=f"Feels {current.get('feelslike_c', 'N/A')}°C", delta_color="off")
            with col2:
                st.metric("💧 Humidity", f"{current.get('humidity', 'N/A')}%")
            with col3:
                wind_dir = format_wind_direction(current.get('wind_degree', 0))
                st.metric("💨 Wind", f"{current.get('wind_kph', 'N/A')} km/h", 
                         delta=f"{wind_dir}", delta_color="off")
            with col4:
                st.metric("🌧️ Precipitation", f"{current.get('precip_mm', 'N/A')} mm")
            
            st.markdown("---")
            
            # Secondary metrics
            col5, col6, col7, col8 = st.columns(4)
            with col5:
                st.metric("☁️ Clouds", f"{current.get('cloud', 'N/A')}%")
            with col6:
                st.metric("👁️ Visibility", f"{current.get('vis_km', 'N/A')} km")
            with col7:
                st.metric("🌡️ Pressure", f"{current.get('pressure_mb', 'N/A')} mb")
            with col8:
                st.metric("☀️ UV Index", f"{current.get('uv', 'N/A')}")
            
            # Air Quality
            if current.get('air_quality'):
                st.markdown("---")
                st.markdown("### 🌫️ Air Quality")
                
                aqi = current['air_quality']
                col_aqi1, col_aqi2, col_aqi3, col_aqi4 = st.columns(4)
                with col_aqi1:
                    st.metric("EPA Index", f"{aqi.get('us-epa-index', 'N/A')}")
                with col_aqi2:
                    st.metric("PM2.5", f"{aqi.get('pm2_5', 0):.1f} μg/m³")
                with col_aqi3:
                    st.metric("PM10", f"{aqi.get('pm10', 0):.1f} μg/m³")
                with col_aqi4:
                    st.metric("CO", f"{aqi.get('co', 0):.1f} μg/m³")
    
    elif forecast_type == "Hourly (48h)":
        weather_data = get_weather_forecast(lat, lon, days=2)
        
        if weather_data:
            st.markdown("### ⏰ 48-Hour Forecast")
            
            forecast = weather_data.get("forecast", {}).get("forecastday", [])
            hourly_data = []
            
            for day in forecast:
                for hour in day.get("hour", []):
                    hourly_data.append({
                        "time": hour.get("time"),
                        "temp_c": hour.get("temp_c"),
                        "humidity": hour.get("humidity"),
                        "precip_mm": hour.get("precip_mm"),
                        "wind_kph": hour.get("wind_kph"),
                        "condition": hour.get("condition", {}).get("text")
                    })
            
            df = pd.DataFrame(hourly_data[:48])
            df["time"] = pd.to_datetime(df["time"])
            
            st.line_chart(df.set_index("time")[["temp_c"]], height=300)
            st.dataframe(df, use_container_width=True, height=400)
    
    else:  # Daily
        weather_data = get_weather_forecast(lat, lon, days=7)
        
        if weather_data:
            st.markdown("### 📅 7-Day Forecast")
            
            forecast = weather_data.get("forecast", {}).get("forecastday", [])
            daily_data = []
            
            for day in forecast:
                day_data = day.get("day", {})
                daily_data.append({
                    "date": day.get("date"),
                    "condition": day_data.get("condition", {}).get("text"),
                    "maxtemp_c": day_data.get("maxtemp_c"),
                    "mintemp_c": day_data.get("mintemp_c"),
                    "totalprecip_mm": day_data.get("totalprecip_mm"),
                    "maxwind_kph": day_data.get("maxwind_kph")
                })
            
            df = pd.DataFrame(daily_data)
            df["date"] = pd.to_datetime(df["date"])
            
            st.line_chart(df.set_index("date")[["maxtemp_c", "mintemp_c"]], height=300)
            st.dataframe(df, use_container_width=True)

# ---------------- Tab 2: Interactive Map ----------------
with tab2:
    st.markdown("### 🗺️ Real-Time Weather Map")
    
    if not weather_layers and not show_typhoons:
        st.info("👆 Select weather layers or enable typhoon tracking from the sidebar")
    
    # Get current weather for marker
    current_weather = get_weather_current(lat, lon)
    temp_text = "Loading..."
    condition_text = "Loading..."
    
    if current_weather:
        curr = current_weather.get('current', {})
        temp_text = f"{curr.get('temp_c', 'N/A')}°C"
        condition_text = curr.get('condition', {}).get('text', 'N/A')
    
    # OpenWeatherMap layer codes
    layer_codes = {
        "Temperature": "TA2",
        "Precipitation": "PR0",
        "Wind Animation": "WND",
        "Clouds": "CL",
        "Pressure": "APM"
    }
    
    # Build map HTML
    map_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body {{ margin: 0; padding: 0; }}
        #map {{ height: 700px; width: 100%; }}
        .leaflet-popup-content {{ font-family: Arial; }}
        .leaflet-popup-content h3 {{ margin: 0 0 10px 0; color: #667eea; }}
    </style>
</head>
<body>
    <div id="map"></div>
    <script>
        // Initialize map
        var map = L.map('map').setView([{lat}, {lon}], 8);
        
        // Base layer
        L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
            attribution: '&copy; CartoDB',
            maxZoom: 19
        }}).addTo(map);
"""
    
    # Add weather layers
    for layer_name in weather_layers:
        code = layer_codes.get(layer_name)
        if code:
            map_html += f"""
        // Add {layer_name}
        L.tileLayer('https://maps.openweathermap.org/maps/2.0/weather/1h/{code}/{{z}}/{{x}}/{{y}}?appid={OPENWEATHER_KEY}&opacity={map_opacity}', {{
            attribution: 'OpenWeatherMap',
            opacity: 1.0
        }}).addTo(map);
"""
    
    # Add typhoon tracks
    if show_typhoons:
        typhoons = fetch_typhoon_tracks()
        if typhoons:
            for feature in typhoons:
                coords = feature.get('geometry', {}).get('coordinates', [])
                props = feature.get('properties', {})
                name = props.get('name', 'Typhoon')
                
                if coords:
                    if isinstance(coords[0], list):
                        latlngs = [[c[1], c[0]] for c in coords]
                        map_html += f"""
        L.polyline({latlngs}, {{
            color: 'red',
            weight: 4
        }}).bindPopup('<b>🌀 {name}</b>').addTo(map);
"""
                    else:
                        map_html += f"""
        L.circleMarker([{coords[1]}, {coords[0]}], {{
            radius: 8,
            fillColor: 'red',
            color: 'white',
            weight: 2,
            fillOpacity: 0.8
        }}).bindPopup('<b>🌀 {name}</b>').addTo(map);
"""
    
    # Add location marker
    map_html += f"""
        // Your location marker
        var marker = L.marker([{lat}, {lon}]).addTo(map);
        marker.bindPopup('<h3>📍 Your Location</h3><p><b>Temperature:</b> {temp_text}</p><p><b>Conditions:</b> {condition_text}</p><p><b>Coordinates:</b> {lat:.4f}, {lon:.4f}</p>').openPopup();
        
        // Add scale
        L.control.scale().addTo(map);
    </script>
</body>
</html>
"""
    
    # Render the map
    components.html(map_html, height=750)
    
    # Layer info
    if weather_layers:
        st.info(f"**Active layers:** {', '.join(weather_layers)}")

# ---------------- Footer ----------------
st.markdown("---")
st.markdown("""
<div style='text-align: center; padding: 20px;'>
    <h3>🌏 BantayKlima - Philippine Weather Monitor</h3>
    <p>Powered by WeatherAPI.com • OpenWeatherMap • GDACS</p>
    <p style='font-size: 0.8em;'>For emergencies, follow official PAGASA advisories</p>
</div>
""", unsafe_allow_html=True)

# Sidebar extras
with st.sidebar:
    st.markdown("---")
    if st.button("🔄 Refresh Data", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
