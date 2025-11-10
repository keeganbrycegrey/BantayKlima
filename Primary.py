import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
import streamlit.components.v1 as components
from datetime import datetime, timedelta
import os

st.set_page_config(
    page_title="PH Weather Monitor",
    page_icon="🌏",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------- Configuration ----------------
# Load API keys from Streamlit secrets or environment variables
try:
    
    WEATHERAPI_KEY = st.secrets["WEATHERAPI_KEY"]
    OPENWEATHER_KEY = st.secrets["OPENWEATHER_KEY"]
except (FileNotFoundError, KeyError):
    # Fallback to environment variables (for local development)
    WEATHERAPI_KEY = os.getenv("WEATHERAPI_KEY")
    OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY")
    
    # If still no keys, show error
    if not WEATHERAPI_KEY or not OPENWEATHER_KEY:
        st.error("""
        ⚠️ **API Keys Not Found!**
        
        Please set up your API keys using one of these methods:
        
        **Method 1: Streamlit Secrets (Recommended for deployment)**
        1. Create `.streamlit/secrets.toml` file
        2. Add your keys:
        ```
        WEATHERAPI_KEY = "your_weatherapi_key"
        OPENWEATHER_KEY = "your_openweather_key"
        ```
        
        **Method 2: Environment Variables (For local development)**
        1. Create `.env` file
        2. Add your keys:
        ```
        WEATHERAPI_KEY=your_weatherapi_key
        OPENWEATHER_KEY=your_openweather_key
        ```
        3. Load with: `export $(cat .env | xargs)` (Mac/Linux) or set in Windows
        
        **Get your API keys:**
        - WeatherAPI: https://weatherapi.com
        - OpenWeatherMap: https://openweathermap.org/api
        """)
        st.stop()

# ---------------- Custom CSS ----------------
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1f77b4;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #666;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .stAlert {
        border-radius: 10px;
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

def get_aqi_status(aqi_index):
    """Get air quality status based on US EPA index"""
    if aqi_index == 1:
        return "Good", "🟢"
    elif aqi_index == 2:
        return "Moderate", "🟡"
    elif aqi_index == 3:
        return "Unhealthy for Sensitive", "🟠"
    elif aqi_index == 4:
        return "Unhealthy", "🔴"
    elif aqi_index == 5:
        return "Very Unhealthy", "🟣"
    elif aqi_index == 6:
        return "Hazardous", "🟤"
    return "Unknown", "⚪"

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
            params={"name": query, "count": 3},
            timeout=10
        )
        r.raise_for_status()
        return r.json().get("results", [])
    except Exception as e:
        st.error(f"Geocoding error: {e}")
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
        st.error(f"Weather API error: {e}")
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
        data = r.json()
        features = data.get("features", [])
        return features if features else []
    except Exception as e:
        return []

# ---------------- Sidebar ----------------
with st.sidebar:
    st.title("🇵🇭 PH Weather Monitor")
    st.markdown("---")
    
    # Location Section
    st.markdown("### 📍 Location")
    place = st.text_input("🔍 Search City/Municipality", placeholder="e.g., Manila, Cebu, Davao")
    
    # Geocoding with multiple results
    if place:
        with st.spinner("🔍 Searching..."):
            results = geocode(place)
            if results:
                location_options = [f"{r.get('name', '')}, {r.get('admin1', '')}" for r in results]
                selected = st.selectbox("Select location:", location_options)
                if selected:
                    idx = location_options.index(selected)
                    lat = results[idx]["latitude"]
                    lon = results[idx]["longitude"]
                    st.success(f"✓ {selected}")
            else:
                st.error("❌ Location not found")
                lat = 14.5995
                lon = 120.9842
    else:
        col1, col2 = st.columns(2)
        with col1:
            lat = st.number_input("Latitude", value=14.5995, format="%.6f")
        with col2:
            lon = st.number_input("Longitude", value=120.9842, format="%.6f")
    
    st.markdown("---")
    
    # Weather Forecast Type
    st.markdown("### 🌤️ Forecast")
    forecast_type = st.radio(
        "Select forecast type:",
        ["Current", "Hourly", "Daily"],
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    
    # Weather Map Layers - Maps 2.0
    st.markdown("### 🗺️ Weather Layers")
    st.caption("OpenWeatherMap Maps 2.0 (Updated hourly)")
    
    weather_layers = st.multiselect(
        "Select weather overlays:",
        [
            "Temperature", 
            "Precipitation", 
            "Wind Animation",
            "Clouds", 
            "Pressure",
            "Humidity"
        ],
        default=["Temperature", "Wind Animation"],
        label_visibility="collapsed"
    )
    
    map_opacity = st.slider("Layer Opacity", 0.3, 1.0, 0.7, 0.1)
    
    st.markdown("---")
    
    # Typhoon Tracking
    st.markdown("### 🌀 Typhoon Tracking")
    show_typhoons = st.checkbox("Show Active Typhoons", value=True)
    
    st.markdown("---")
    st.caption("**📊 Data Sources:**")
    st.caption("• WeatherAPI.com (Weather Data)")
    st.caption("• OpenWeatherMap Maps 2.0 (Map Layers)")
    st.caption("• GDACS (Typhoon Tracking)")
    st.caption(f"🕐 Updated: {datetime.now().strftime('%I:%M %p')}")

# ---------------- Main Content ----------------
st.markdown('<p class="main-header">🌏 Philippine Weather Monitor</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Real-time weather data with hourly-updated Maps 2.0 visualization</p>', unsafe_allow_html=True)

# Weather Alerts Banner
weather_data_check = get_weather_forecast(lat, lon, days=1)
if weather_data_check:
    alerts = weather_data_check.get("alerts", {}).get("alert", [])
    if alerts:
        for alert in alerts:
            st.error(f"⚠️ **WEATHER ALERT**: {alert.get('headline', 'Alert')}")

# Main content tabs
tab1, tab2 = st.tabs(["📊 Weather Forecast", "🗺️ Interactive Weather Map"])

# ---------------- Tab 1: Weather Forecast ----------------
with tab1:
    if forecast_type == "Current":
        weather_data = get_weather_current(lat, lon)
        
        if weather_data:
            current = weather_data.get("current", {})
            location = weather_data.get("location", {})
            condition = current.get("condition", {})
            
            # Location header
            col_head1, col_head2 = st.columns([3, 1])
            with col_head1:
                st.markdown(f"### 📍 {location.get('name', '')}, {location.get('region', '')}")
                st.caption(f"🕐 {location.get('localtime', '')} | Coordinates: {lat:.4f}, {lon:.4f}")
            with col_head2:
                weather_icon = get_weather_icon(condition.get('text', ''))
                st.markdown(f"<div style='text-align: center; font-size: 4rem;'>{weather_icon}</div>", unsafe_allow_html=True)
            
            st.markdown(f"**{condition.get('text', 'N/A')}**")
            
            # Primary metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric(
                    "🌡️ Temperature",
                    f"{current.get('temp_c', 'N/A')}°C",
                    delta=f"Feels {current.get('feelslike_c', 'N/A')}°C",
                    delta_color="off"
                )
            with col2:
                st.metric(
                    "💧 Humidity",
                    f"{current.get('humidity', 'N/A')}%"
                )
            with col3:
                wind_dir = format_wind_direction(current.get('wind_degree', 0))
                st.metric(
                    "💨 Wind",
                    f"{current.get('wind_kph', 'N/A')} km/h",
                    delta=f"{wind_dir}",
                    delta_color="off"
                )
            with col4:
                st.metric(
                    "🌧️ Precipitation",
                    f"{current.get('precip_mm', 'N/A')} mm"
                )
            
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
                uv_value = current.get('uv', 0)
                uv_color = "🟢" if uv_value < 3 else "🟡" if uv_value < 6 else "🟠" if uv_value < 8 else "🔴"
                st.metric("☀️ UV Index", f"{uv_value} {uv_color}")
            
            # Air Quality
            if current.get('air_quality'):
                st.markdown("---")
                st.markdown("### 🌫️ Air Quality Index")
                
                aqi = current['air_quality']
                epa_index = aqi.get('us-epa-index', 0)
                status, status_icon = get_aqi_status(epa_index)
                
                col_aqi1, col_aqi2, col_aqi3, col_aqi4 = st.columns(4)
                with col_aqi1:
                    st.metric("Overall", f"{status} {status_icon}")
                with col_aqi2:
                    st.metric("PM2.5", f"{aqi.get('pm2_5', 0):.1f} μg/m³")
                with col_aqi3:
                    st.metric("PM10", f"{aqi.get('pm10', 0):.1f} μg/m³")
                with col_aqi4:
                    st.metric("CO", f"{aqi.get('co', 0):.1f} μg/m³")
    
    elif forecast_type == "Hourly":
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
                        "feelslike_c": hour.get("feelslike_c"),
                        "humidity": hour.get("humidity"),
                        "precip_mm": hour.get("precip_mm"),
                        "wind_kph": hour.get("wind_kph"),
                        "condition": hour.get("condition", {}).get("text"),
                        "chance_of_rain": hour.get("chance_of_rain"),
                        "uv": hour.get("uv")
                    })
            
            df = pd.DataFrame(hourly_data[:48])
            df["time"] = pd.to_datetime(df["time"])
            
            subtab1, subtab2 = st.tabs(["📊 Visualizations", "📋 Data Table"])
            
            with subtab1:
                st.markdown("**🌡️ Temperature Forecast**")
                st.line_chart(
                    df.set_index("time")[["temp_c", "feelslike_c"]],
                    height=300,
                    use_container_width=True
                )
                
                col_chart1, col_chart2 = st.columns(2)
                with col_chart1:
                    st.markdown("**🌧️ Precipitation (mm)**")
                    st.area_chart(df.set_index("time")[["precip_mm"]], height=250)
                
                with col_chart2:
                    st.markdown("**💨 Wind Speed (km/h)**")
                    st.line_chart(df.set_index("time")[["wind_kph"]], height=250)
            
            with subtab2:
                st.dataframe(
                    df,
                    column_config={
                        "time": st.column_config.DatetimeColumn("Time", format="MMM D, h:mm a"),
                        "temp_c": st.column_config.NumberColumn("Temp °C", format="%.1f"),
                        "feelslike_c": st.column_config.NumberColumn("Feels °C", format="%.1f"),
                        "humidity": st.column_config.NumberColumn("Humidity %", format="%.0f"),
                        "precip_mm": st.column_config.NumberColumn("Rain mm", format="%.1f"),
                        "wind_kph": st.column_config.NumberColumn("Wind km/h", format="%.1f"),
                        "chance_of_rain": st.column_config.NumberColumn("Rain %", format="%.0f"),
                        "uv": st.column_config.NumberColumn("UV", format="%.1f"),
                        "condition": "Conditions"
                    },
                    hide_index=True,
                    use_container_width=True,
                    height=400
                )
    
    else:  # Daily forecast
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
                    "avgtemp_c": day_data.get("avgtemp_c"),
                    "totalprecip_mm": day_data.get("totalprecip_mm"),
                    "avghumidity": day_data.get("avghumidity"),
                    "maxwind_kph": day_data.get("maxwind_kph"),
                    "daily_chance_of_rain": day_data.get("daily_chance_of_rain"),
                    "uv": day_data.get("uv")
                })
            
            df = pd.DataFrame(daily_data)
            df["date"] = pd.to_datetime(df["date"])
            
            subtab1, subtab2 = st.tabs(["📊 Visualizations", "📋 Data Table"])
            
            with subtab1:
                st.markdown("**🌡️ Temperature Range**")
                st.line_chart(
                    df.set_index("date")[["maxtemp_c", "mintemp_c", "avgtemp_c"]],
                    height=300,
                    use_container_width=True
                )
                
                col_chart1, col_chart2 = st.columns(2)
                with col_chart1:
                    st.markdown("**🌧️ Total Precipitation (mm)**")
                    st.bar_chart(df.set_index("date")[["totalprecip_mm"]], height=250)
                
                with col_chart2:
                    st.markdown("**☔ Rain Probability (%)**")
                    st.line_chart(df.set_index("date")[["daily_chance_of_rain"]], height=250)
            
            with subtab2:
                st.dataframe(
                    df,
                    column_config={
                        "date": st.column_config.DatetimeColumn("Date", format="ddd, MMM D"),
                        "condition": "Conditions",
                        "maxtemp_c": st.column_config.NumberColumn("Max °C", format="%.1f"),
                        "mintemp_c": st.column_config.NumberColumn("Min °C", format="%.1f"),
                        "avgtemp_c": st.column_config.NumberColumn("Avg °C", format="%.1f"),
                        "totalprecip_mm": st.column_config.NumberColumn("Rain mm", format="%.1f"),
                        "avghumidity": st.column_config.NumberColumn("Humidity %", format="%.0f"),
                        "maxwind_kph": st.column_config.NumberColumn("Wind km/h", format="%.1f"),
                        "daily_chance_of_rain": st.column_config.NumberColumn("Rain %", format="%.0f"),
                        "uv": st.column_config.NumberColumn("UV", format="%.1f")
                    },
                    hide_index=True,
                    use_container_width=True
                )

# ---------------- Tab 2: Interactive Weather Map ----------------
with tab2:
    st.markdown("### 🗺️ OpenWeatherMap Maps 2.0 - Real-Time Weather Visualization")
    
    if not weather_layers and not show_typhoons:
        st.info("👆 Select weather layers or enable typhoon tracking from the sidebar")
    else:
        layer_info = []
        if weather_layers:
            layer_info.append(f"**Weather**: {', '.join(weather_layers)}")
        if show_typhoons:
            layer_info.append("**Typhoons**: Active tracking")
        
        st.caption(" | ".join(layer_info) + f" | Opacity: {int(map_opacity*100)}%")
    
    # OpenWeatherMap Maps 2.0 API layer codes
    layer_map = {
        "Precipitation": "PR0",
        "Temperature": "TA2",
        "Clouds": "CL",
        "Wind Speed": "WS10",
        "Pressure": "APM",
        "Wind Animation": "WND",
        "Humidity": "HRD0"
    }
    
    # Get current weather for popup
    current_weather = get_weather_current(lat, lon)
    temp_display = "N/A"
    condition_display = "Loading..."
    if current_weather:
        temp_display = f"{current_weather.get('current', {}).get('temp_c', 'N/A')}°C"
        condition_display = current_weather.get('current', {}).get('condition', {}).get('text', 'N/A')
    
    # Enhanced Leaflet map with Maps 2.0
    map_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
            body {{ margin: 0; padding: 0; }}
            #map {{ 
                height: 750px; 
                width: 100%; 
                border-radius: 12px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.3);
            }}
            .legend {{
                background: rgba(255, 255, 255, 0.95);
                padding: 15px;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.2);
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                max-width: 220px;
            }}
            .legend h4 {{ 
                margin: 0 0 10px; 
                font-size: 14px;
                font-weight: 600;
                color: #333;
                border-bottom: 2px solid #667eea;
                padding-bottom: 5px;
            }}
            .legend-item {{
                margin: 8px 0;
                font-size: 11px;
                color: #555;
                display: flex;
                align-items: center;
            }}
            .legend-icon {{
                width: 20px;
                height: 20px;
                border-radius: 3px;
                margin-right: 8px;
                display: inline-block;
            }}
            .coordinates {{
                background: rgba(0, 0, 0, 0.8);
                color: white;
                padding: 10px 14px;
                border-radius: 8px;
                font-family: 'Courier New', monospace;
                font-size: 12px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.4);
                line-height: 1.6;
            }}
            .info-box {{
                background: rgba(255, 255, 255, 0.95);
                padding: 12px;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.2);
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                font-size: 12px;
            }}
            .info-box h4 {{
                margin: 0 0 8px;
                font-size: 14px;
                color: #667eea;
                font-weight: 600;
            }}
            @keyframes pulse {{
                0% {{ transform: scale(1); opacity: 1; }}
                50% {{ transform: scale(1.3); opacity: 0.5; }}
                100% {{ transform: scale(1); opacity: 1; }}
            }}
        </style>
    </head>
    <body>
        <div id="map"></div>
        <script>
            var map = L.map('map', {{
                center: [{lat}, {lon}],
                zoom: 8,
                zoomControl: true,
                minZoom: 5,
                maxZoom: 15,
                attributionControl: true
            }});
            
            // Base layers
            var baseLayers = {{
                "🌙 Dark": L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
                    attribution: '© OpenStreetMap, © CartoDB'
                }}),
                "🛰️ Satellite": L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
                    attribution: '© Esri'
                }}),
                "🗺️ Streets": L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                    attribution: '© OpenStreetMap'
                }}),
                "🏔️ Terrain": L.tileLayer('https://stamen-tiles-{{s}}.a.ssl.fastly.net/terrain/{{z}}/{{x}}/{{y}}.jpg', {{
                    attribution: '© Stamen Design'
                }})
            }};
            
            baseLayers["🌙 Dark"].addTo(map);
            
            // Weather overlays using Maps 2.0
            var weatherOverlays = {{}};
    """
    
    # Add weather layers using Maps 2.0 API
    for layer_name in weather_layers:
        owm_layer = layer_map.get(layer_name)
        if owm_layer:
            map_html += f"""
            weatherOverlays["🌤️ {layer_name}"] = L.tileLayer(
                'https://maps.openweathermap.org/maps/2.0/weather/1h/{owm_layer}/{{z}}/{{x}}/{{y}}?appid={OPENWEATHER_KEY}&opacity={map_opacity}&fill_bound=true', 
                {{
                    attribution: 'OpenWeatherMap Maps 2.0',
                    opacity: 1.0,
                    maxZoom: 15
                }}
            ).addTo(map);
    """
    
    # Add typhoon tracks if enabled
    if show_typhoons:
        typhoon_data = fetch_typhoon_tracks()
        if typhoon_data:
            map_html += """
            var typhoonLayer = L.layerGroup();
            """
            for feature in typhoon_data:
                coords = feature.get('geometry', {}).get('coordinates', [])
                props = feature.get('properties', {})
                if coords:
                    # Convert coordinates for Leaflet (lon, lat to lat, lon)
                    if isinstance(coords[0], list):
                        # It's a LineString
                        latlngs = [[c[1], c[0]] for c in coords]
                        map_html += f"""
                        L.polyline({latlngs}, {{
                            color: 'red',
                            weight: 4,
                            opacity: 0.8
                        }}).bindPopup('<b>🌀 {props.get("name", "Typhoon")}</b><br>Status: Active').addTo(typhoonLayer);
                        """
                    else:
                        # It's a Point
                        map_html += f"""
                        L.circleMarker([{coords[1]}, {coords[0]}], {{
                            radius: 8,
                            fillColor: "#ff0000",
                            color: "#fff",
                            weight: 2,
                            opacity: 1,
                            fillOpacity: 0.8
                        }}).bindPopup('<b>🌀 {props.get("name", "Typhoon")}</b><br>Status: Active').addTo(typhoonLayer);
                        """
            
            map_html += """
            typhoonLayer.addTo(map);
            weatherOverlays["🌀 Typhoon Tracks"] = typhoonLayer;
            """
    
    map_html += f"""
            // Location marker with pulsing animation
            var pulsingIcon = L.divIcon({{
                className: 'custom-div-icon',
                html: `
                    <div style="position: relative;">
                        <div style="
                            width: 40px; 
                            height: 40px; 
                            background: rgba(255, 0, 0, 0.4);
                            border-radius: 50%;
                            position: absolute;
                            top: -20px;
                            left: -20px;
                            animation: pulse 2s infinite;
                        "></div>
                        <div style="
                            width: 20px; 
                            height: 20px; 
                            background: #ff0000;
                            border: 3px solid white;
                            border-radius: 50%;
                            position: absolute;
                            top: -10px;
                            left: -10px;
                            box-shadow: 0 0 15px rgba(255,0,0,0.7);
                        "></div>
                    </div>
                `,
                iconSize: [40, 40],
                iconAnchor: [20, 20]
            }});
            
            var locationMarker = L.marker([{lat}, {lon}], {{icon: pulsingIcon}}).addTo(map);
            locationMarker.bindPopup(`
                <div style="min-width: 220px; padding: 5px;">
                    <h3 style="margin: 0 0 12px; color: #667eea; font-size: 16px; border-bottom: 2px solid #667eea; padding-bottom: 5px;">
                        📍 Your Location
                    </h3>
                    <div style="margin: 8px 0; font-size: 13px;">
                        <strong>🌡️ Temperature:</strong> {temp_display}
                    </div>
                    <div style="margin: 8px 0; font-size: 13px;">
                        <strong>☁️ Conditions:</strong> {condition_display}
                    </div>
                    <div style="margin: 10px 0 5px; padding-top: 10px; border-top: 1px solid #ddd; font-size: 11px; color: #666;">
                        <strong>Coordinates:</strong><br>
                        Lat: {lat:.6f}<br>
                        Lon: {lon:.6f}
                    </div>
                </div>
            `).openPopup();
            
            // 20km radius circle
            L.circle([{lat}, {lon}], {{
                color: '#667eea',
                fillColor: '#667eea',
                fillOpacity: 0.08,
                radius: 20000,
                weight: 2,
                dashArray: '8, 6'
            }}).addTo(map);
            
            // Layer control
            L.control.layers(baseLayers, weatherOverlays, {{
                position: 'topright',
                collapsed: false
            }}).addTo(map);
            
            // Scale control
            L.control.scale({{
                position: 'bottomleft',
                imperial: false,
                metric: true
            }}).addTo(map);
            
            // Legend
            var legend = L.control({{ position: 'bottomright' }});
            legend.onAdd = function(map) {{
                var div = L.DomUtil.create('div', 'legend');
                div.innerHTML = '<h4>🗺️ Maps 2.0 Layers</h4>';
    """
    
    # Add legend items
    for layer_name in weather_layers:
        color_map = {
            "Temperature": "#ff4444",
            "Precipitation": "#0099ff",
            "Clouds": "#cccccc",
            "Wind Speed": "#44ff44",
            "Wind Animation": "#ffaa00",
            "Pressure": "#ff9944",
            "Humidity": "#66ccff"
        }
        color = color_map.get(layer_name, "#888888")
        layer_code = layer_map.get(layer_name, "")
        
        map_html += f"""
                div.innerHTML += '<div class="legend-item"><div class="legend-icon" style="background: {color};"></div><span>{layer_name} ({layer_code})</span></div>';
    """
    
    if show_typhoons:
        map_html += """
                div.innerHTML += '<div class="legend-item"><div class="legend-icon" style="background: #ff0000;"></div><span>Typhoon Tracks</span></div>';
    """
    
    map_html += """
                return div;
            }};
            legend.addTo(map);
            
            // Coordinates display
            var coordsDisplay = L.control({ position: 'topleft' });
            coordsDisplay.onAdd = function(map) {
                var div = L.DomUtil.create('div', 'coordinates');
                div.id = 'coords';
                div.innerHTML = '<div style="font-weight: bold; margin-bottom: 5px;">📍 Cursor Position</div><div id="coord-text">Hover over map</div>';
                return div;
            };
            coordsDisplay.addTo(map);
            
            // Update coordinates on mouse move
            map.on('mousemove', function(e) {
                var coordText = document.getElementById('coord-text');
                if (coordText) {
                    coordText.innerHTML = 'Lat: ' + e.latlng.lat.toFixed(5) + '<br>Lon: ' + e.latlng.lng.toFixed(5);
                }
            });
            
            // Info box
            var info = L.control({ position: 'topright' });
            info.onAdd = function(map) {
                var div = L.DomUtil.create('div', 'info-box');
                div.innerHTML = `
                    <h4>💡 Map Controls</h4>
                    <div style="line-height: 1.8;">
                        🖱️ <strong>Click</strong> for details<br>
                        🔍 <strong>Scroll</strong> to zoom<br>
                        👆 <strong>Drag</strong> to pan<br>
                        📊 <strong>Layers</strong> top-right<br>
                        🔄 Updates hourly
                    </div>
                `;
                return div;
            };
            info.addTo(map);
            
            // Click handler for location details
            map.on('click', function(e) {
                L.popup()
                    .setLatLng(e.latlng)
                    .setContent(`
                        <div style="min-width: 180px; padding: 5px;">
                            <h4 style="margin: 0 0 8px; color: #667eea;">📍 Location Info</h4>
                            <div style="font-size: 12px;">
                                <strong>Latitude:</strong> ${e.latlng.lat.toFixed(6)}<br>
                                <strong>Longitude:</strong> ${e.latlng.lng.toFixed(6)}
                            </div>
                            <div style="margin-top: 10px; padding-top: 8px; border-top: 1px solid #ddd; font-size: 11px; color: #666;">
                                Weather data updated hourly
                            </div>
                        </div>
                    `)
                    .openOn(map);
            });
            
            // Reset view button
            L.Control.ResetView = L.Control.extend({
                onAdd: function(map) {
                    var button = L.DomUtil.create('div');
                    button.innerHTML = `
                        <button style="
                            background: white;
                            border: 2px solid rgba(0,0,0,0.2);
                            border-radius: 6px;
                            padding: 10px 14px;
                            cursor: pointer;
                            font-size: 13px;
                            font-weight: 600;
                            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
                            transition: all 0.2s;
                        " 
                        onmouseover="this.style.background='#f0f0f0'; this.style.transform='translateY(-2px)'" 
                        onmouseout="this.style.background='white'; this.style.transform='translateY(0)'"
                        onclick="map.setView([{lat}, {lon}], 8)">
                            🎯 Reset View
                        </button>
                    `;
                    return button;
                },
                onRemove: function(map) {}
            });
            
            L.control.resetView = function(opts) {
                return new L.Control.ResetView(opts);
            };
            
            L.control.resetView({ position: 'topleft' }).addTo(map);
            
        </script>
    </body>
    </html>
    """
    
    components.html(map_html, height=800)
    
    # Weather layer information
    if weather_layers:
        with st.expander("📖 Maps 2.0 Layer Information", expanded=False):
            st.markdown("### OpenWeatherMap Maps 2.0 API")
            st.info("🔄 **Update Frequency:** Hourly | **Coverage:** Global | **Resolution:** High")
            
            st.markdown("---")
            
            for layer in weather_layers:
                if layer == "Temperature":
                    st.markdown("**🌡️ Air Temperature (TA2)**")
                    st.caption("Real-time air temperature at 2 meters above ground level. Color gradient from blue (cold) to red (hot).")
                    st.caption("📊 **Range:** -40°C to 50°C | **Unit:** Celsius")
                
                elif layer == "Precipitation":
                    st.markdown("**🌧️ Precipitation (PR0)**")
                    st.caption("Current rainfall and snowfall intensity. Darker blue indicates heavier precipitation.")
                    st.caption("📊 **Range:** 0-50+ mm/h | **Unit:** mm per hour")
                
                elif layer == "Wind Animation":
                    st.markdown("**🌪️ Wind Animation (WND)**")
                    st.caption("Animated wind flow showing direction and speed using particle effects. Most visually dynamic layer.")
                    st.caption("📊 **Display:** Real-time wind vectors | **Updates:** Live animation")
                
                elif layer == "Clouds":
                    st.markdown("**☁️ Cloud Coverage (CL)**")
                    st.caption("Percentage of sky covered by clouds. White/gray shading indicates cloud density.")
                    st.caption("📊 **Range:** 0-100% | **Unit:** Percentage")
                
                elif layer == "Wind Speed":
                    st.markdown("**💨 Wind Speed (WS10)**")
                    st.caption("Wind velocity at 10 meters height. Color-coded by intensity with direction indicators.")
                    st.caption("📊 **Range:** 0-50+ m/s | **Unit:** Meters per second")
                
                elif layer == "Pressure":
                    st.markdown("**🌡️ Atmospheric Pressure (APM)**")
                    st.caption("Sea level pressure with isobar contour lines. Shows high/low pressure systems.")
                    st.caption("📊 **Range:** 950-1050 hPa | **Unit:** Hectopascals")
                
                elif layer == "Humidity":
                    st.markdown("**💧 Relative Humidity (HRD0)**")
                    st.caption("Air moisture content as percentage. Higher humidity shown in darker blue.")
                    st.caption("📊 **Range:** 0-100% | **Unit:** Percentage")
                
                st.markdown("")
            
            st.markdown("---")
            st.success("💡 **Pro Tip:** Combine multiple layers to analyze complex weather patterns. Try Temperature + Wind Animation for comprehensive weather visualization!")

# ---------------- Footer ----------------
st.markdown("---")
st.markdown("""
<div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
            padding: 30px; border-radius: 10px; text-align: center; color: white;'>
    <h3 style='margin: 0; color: white;'>🌏 Philippine Weather Monitor</h3>
    <p style='margin: 10px 0 5px 0; font-size: 0.95rem;'>
        Powered by <strong>OpenWeatherMap Maps 2.0</strong> • Real-time hourly updates
    </p>
    <p style='margin: 5px 0; font-size: 0.85rem; opacity: 0.9;'>
        Weather Data: WeatherAPI.com | Map Layers: OpenWeatherMap Maps 2.0 | Typhoons: GDACS
    </p>
    <p style='margin: 10px 0 0 0; font-size: 0.75rem; opacity: 0.8;'>
        Built with Streamlit • Updates every 5 minutes
    </p>
</div>
""", unsafe_allow_html=True)

# ---------------- Sidebar Information Panel ----------------
with st.sidebar:
    st.markdown("---")
    
    # Quick Stats
    with st.expander("📈 Quick Stats", expanded=False):
        st.markdown(f"""
        **Active Layers:**
        - Weather: {len(weather_layers)}
        - Typhoons: {"Yes" if show_typhoons else "No"}
        
        **Location:**
        - Lat: {lat:.4f}
        - Lon: {lon:.4f}
        
        **Data Freshness:**
        - Weather: ~5 min
        - Maps 2.0: ~60 min
        - Typhoons: ~60 min
        """)
    
    # Maps 2.0 Info
    with st.expander("🗺️ About Maps 2.0", expanded=False):
        st.markdown("""
        **OpenWeatherMap Maps 2.0**
        
        Advanced weather mapping with:
        - ⏱️ Hourly updates
        - 🌍 Global coverage
        - 🎯 High resolution tiles
        - 🔄 Real-time data
        - 📊 Multiple parameters
        - 🎨 Professional visualization
        
        **Available Layers:**
        - Temperature (TA2)
        - Precipitation (PR0)
        - Wind Animation (WND)
        - Clouds (CL)
        - Wind Speed (WS10)
        - Pressure (APM)
        - Humidity (HRD0)
        """)
    
    # Help
    with st.expander("ℹ️ Help & Tips", expanded=False):
        st.markdown("""
        **Getting Started:**
        1. Search for your location
        2. Select weather layers
        3. Adjust opacity slider
        4. Explore the interactive map
        
        **Map Features:**
        - Switch base maps (top-right)
        - Toggle layers on/off
        - Click anywhere for coordinates
        - Hover for live position
        - Reset view button (top-left)
        
        **Best Combinations:**
        - Temperature + Wind Animation
        - Precipitation + Clouds
        - Pressure + Wind Speed
        """)
    
    # Data Sources
    with st.expander("📚 Data Sources", expanded=False):
        st.markdown("""
        **Weather Data:**
        - [WeatherAPI.com](https://weatherapi.com)
        - Updates: Every 15 minutes
        - Coverage: Global
        
        **Map Visualization:**
        - [OpenWeatherMap Maps 2.0](https://openweathermap.org/api/weathermaps)
        - Updates: Hourly
        - Resolution: High-def tiles
        
        **Typhoon Tracking:**
        - [GDACS](https://gdacs.org)
        - Updates: Real-time
        - Source: Multiple agencies
        """)

# Add refresh button
col_refresh1, col_refresh2, col_refresh3 = st.columns([1, 1, 1])
with col_refresh2:
    if st.button("🔄 Refresh All Data", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
