import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
import streamlit.components.v1 as components
from datetime import datetime, timedelta
import json

st.set_page_config(
    page_title="PH Weather & Hazards",
    page_icon="🌏",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------- Configuration ----------------
WEATHERAPI_KEY = "01cce600297f40debe2164114250911"
OPENWEATHER_KEY = "f72458378cda7bd747aaa6415f7d1a98"

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

@st.cache_data(ttl=600, show_spinner=False)
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

@st.cache_data(ttl=600, show_spinner=False)
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

@st.cache_data(ttl=1800, show_spinner=False)
def arcgis_geojson(url):
    """Fetch ArcGIS GeoJSON with better error handling"""
    try:
        r = requests.get(url, params={
            "where": "1=1",
            "outFields": "*",
            "f": "geojson",
            "returnGeometry": "true",
            "resultRecordCount": 500
        }, timeout=45)
        r.raise_for_status()
        data = r.json()
        return data if data.get("features") else {"type": "FeatureCollection", "features": []}
    except requests.exceptions.Timeout:
        st.warning(f"Request timeout for {url.split('/')[-3]}")
        return {"type": "FeatureCollection", "features": []}
    except Exception as e:
        st.warning(f"Could not fetch layer: {str(e)[:50]}")
        return {"type": "FeatureCollection", "features": []}

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

# ---------------- Hazard URLs ----------------
HAZARD_LAYERS = {
    "Flood": {
        "url": "https://controlmap.mgb.gov.ph/arcgis/rest/services/GeospatialDataInventory/GDI_Detailed_Flood_Susceptibility/FeatureServer/0/query",
        "color": "[100, 100, 255, 180]",
        "line_color": [0, 0, 255],
        "icon": "🌊"
    },
    "Landslide": {
        "url": "https://hazardhunter.georisk.gov.ph/server/rest/services/Landslide/Rain_Induced_Landslide_Hazard/MapServer/0/query",
        "color": "[255, 165, 0, 180]",
        "line_color": [255, 100, 0],
        "icon": "⛰️"
    },
    "Tsunami": {
        "url": "https://hazardhunter.georisk.gov.ph/server/rest/services/Tsunami/Tsunami_Hazard/MapServer/0/query",
        "color": "[255, 0, 0, 150]",
        "line_color": [200, 0, 0],
        "icon": "🌊"
    },
    "Rainfall": {
        "url": "https://portal.georisk.gov.ph/arcgis/rest/services/PAGASA/PAGASA/MapServer/0/query",
        "color": "[0, 150, 255, 150]",
        "line_color": [0, 100, 200],
        "icon": "🌧️"
    }
}

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
    
    # Weather Map Layers
    st.markdown("### 🗺️ Weather Layers")
    weather_layers = st.multiselect(
        "Select weather overlays:",
        ["Precipitation", "Temperature", "Clouds", "Wind Speed", "Pressure"],
        default=["Precipitation"],
        label_visibility="collapsed"
    )
    
    map_opacity = st.slider("Layer Opacity", 0.0, 1.0, 0.6, 0.1)
    
    st.markdown("---")
    
    # Hazard Layers
    st.markdown("### 🛑 Hazard Layers")
    hazards_enabled = st.multiselect(
        "Select hazards:",
        ["Flood", "Landslide", "Tsunami", "Typhoon Track", "Rainfall"],
        default=["Typhoon Track"],
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    st.caption("**📊 Data Sources:**")
    st.caption("• WeatherAPI.com")
    st.caption("• OpenWeatherMap")
    st.caption("• MGB, PHIVOLCS, PAGASA, GDACS")
    st.caption(f"🕐 Updated: {datetime.now().strftime('%I:%M %p')}")

# ---------------- Main Content ----------------
st.markdown('<p class="main-header">🌏 Philippine Weather & Hazard Monitor</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Real-time weather forecasts and disaster risk mapping</p>', unsafe_allow_html=True)

# Weather Alerts Banner
weather_data_check = get_weather_forecast(lat, lon, days=1)
if weather_data_check:
    alerts = weather_data_check.get("alerts", {}).get("alert", [])
    if alerts:
        for alert in alerts:
            st.error(f"⚠️ **WEATHER ALERT**: {alert.get('headline', 'Alert')}")

# Main content tabs
tab1, tab2, tab3 = st.tabs(["📊 Weather Forecast", "🗺️ Weather Map", "🛑 Hazard Map"])

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

# ---------------- Tab 2: Weather Map ----------------
with tab2:
    st.markdown("### 🌤️ Live Weather Overlay Map")
    
    if not weather_layers:
        st.info("👆 Select weather layers from the sidebar to display on the map")
    else:
        st.caption(f"Showing: {', '.join(weather_layers)} | Opacity: {int(map_opacity*100)}%")
    
    layer_map = {
        "Precipitation": "precipitation_new",
        "Temperature": "temp_new",
        "Clouds": "clouds_new",
        "Wind Speed": "wind_new",
        "Pressure": "pressure_new"
    }
    
    # Enhanced Leaflet map with advanced features
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
                height: 700px; 
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
                max-width: 200px;
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
                font-size: 12px;
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
            .info-box {{
                background: rgba(255, 255, 255, 0.95);
                padding: 12px;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.2);
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                font-size: 13px;
                max-width: 250px;
            }}
            .info-box h4 {{
                margin: 0 0 8px;
                font-size: 15px;
                color: #667eea;
                font-weight: 600;
            }}
            .coordinates {{
                background: rgba(0, 0, 0, 0.7);
                color: white;
                padding: 8px 12px;
                border-radius: 6px;
                font-family: 'Courier New', monospace;
                font-size: 12px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.3);
            }}
            .leaflet-popup-content-wrapper {{
                border-radius: 8px;
                box-shadow: 0 3px 14px rgba(0,0,0,0.3);
            }}
            .leaflet-popup-content {{
                margin: 15px;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            }}
            .pulse {{
                animation: pulse 2s infinite;
            }}
            @keyframes pulse {{
                0% {{ opacity: 1; }}
                50% {{ opacity: 0.5; }}
                100% {{ opacity: 1; }}
            }}
        </style>
    </head>
    <body>
        <div id="map"></div>
        <script>
            // Initialize map with better settings
            var map = L.map('map', {{
                center: [{lat}, {lon}],
                zoom: 8,
                zoomControl: true,
                minZoom: 5,
                maxZoom: 18,
                attributionControl: true
            }});
            
            // Base layer options
            var baseLayers = {{
                "Dark": L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
                    attribution: '© OpenStreetMap, © CartoDB',
                    maxZoom: 19
                }}),
                "Satellite": L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
                    attribution: 'Tiles © Esri',
                    maxZoom: 19
                }}),
                "Streets": L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                    attribution: '© OpenStreetMap contributors',
                    maxZoom: 19
                }}),
                "Terrain": L.tileLayer('https://stamen-tiles-{{s}}.a.ssl.fastly.net/terrain/{{z}}/{{x}}/{{y}}.jpg', {{
                    attribution: 'Map tiles by Stamen Design, CC BY 3.0',
                    maxZoom: 18
                }})
            }};
            
            // Add default base layer
            baseLayers["Dark"].addTo(map);
            
            // Weather layers object
            var weatherLayers = {{}};
    """
    
    # Add weather layers with better controls
    for layer_name in weather_layers:
        owm_layer = layer_map.get(layer_name)
        if owm_layer:
            map_html += f"""
            weatherLayers["{layer_name}"] = L.tileLayer('https://tile.openweathermap.org/map/{owm_layer}/{{z}}/{{x}}/{{y}}.png?appid={OPENWEATHER_KEY}', {{
                attribution: 'Weather: OpenWeatherMap',
                opacity: {map_opacity},
                maxZoom: 19
            }}).addTo(map);
    """
    
    # Add location marker with pulsing effect
    current_weather = get_weather_current(lat, lon)
    temp_display = "N/A"
    condition_display = "Loading..."
    if current_weather:
        temp_display = f"{current_weather.get('current', {}).get('temp_c', 'N/A')}°C"
        condition_display = current_weather.get('current', {}).get('condition', {}).get('text', 'N/A')
    
    map_html += f"""
            // Custom pulsing marker
            var pulsingIcon = L.divIcon({{
                className: 'custom-div-icon',
                html: `
                    <div style="position: relative;">
                        <div style="
                            width: 30px; 
                            height: 30px; 
                            background: rgba(255, 0, 0, 0.3);
                            border-radius: 50%;
                            position: absolute;
                            top: -15px;
                            left: -15px;
                            animation: pulse 2s infinite;
                        "></div>
                        <div style="
                            width: 15px; 
                            height: 15px; 
                            background: #ff0000;
                            border: 3px solid white;
                            border-radius: 50%;
                            position: absolute;
                            top: -7.5px;
                            left: -7.5px;
                            box-shadow: 0 0 10px rgba(255,0,0,0.5);
                        "></div>
                    </div>
                `,
                iconSize: [30, 30],
                iconAnchor: [15, 15]
            }});
            
            var locationMarker = L.marker([{lat}, {lon}], {{icon: pulsingIcon}}).addTo(map);
            locationMarker.bindPopup(`
                <div style="min-width: 200px;">
                    <h3 style="margin: 0 0 10px; color: #667eea; font-size: 16px;">
                        📍 Your Location
                    </h3>
                    <div style="margin: 8px 0;">
                        <strong>🌡️ Temperature:</strong> {temp_display}
                    </div>
                    <div style="margin: 8px 0;">
                        <strong>☁️ Conditions:</strong> {condition_display}
                    </div>
                    <div style="margin: 8px 0; font-size: 11px; color: #666;">
                        <strong>Coordinates:</strong><br>
                        Lat: {lat:.6f}<br>
                        Lon: {lon:.6f}
                    </div>
                </div>
            `).openPopup();
            
            // Add circle around location
            L.circle([{lat}, {lon}], {{
                color: '#667eea',
                fillColor: '#667eea',
                fillOpacity: 0.1,
                radius: 20000,
                weight: 2,
                dashArray: '5, 5'
            }}).addTo(map);
            
            // Layer control
            L.control.layers(baseLayers, weatherLayers, {{
                position: 'topright',
                collapsed: false
            }}).addTo(map);
            
            // Add scale control
            L.control.scale({{
                position: 'bottomleft',
                imperial: false,
                metric: true
            }}).addTo(map);
            
            // Custom legend control
            var legend = L.control({{ position: 'bottomright' }});
            legend.onAdd = function(map) {{
                var div = L.DomUtil.create('div', 'legend');
                div.innerHTML = `
                    <h4>🗺️ Active Layers</h4>
    """
    
    # Add legend items for each weather layer
    for layer_name in weather_layers:
        color = "#3388ff"
        if layer_name == "Precipitation":
            color = "#0099ff"
        elif layer_name == "Temperature":
            color = "#ff4444"
        elif layer_name == "Clouds":
            color = "#cccccc"
        elif layer_name == "Wind Speed":
            color = "#44ff44"
        elif layer_name == "Pressure":
            color = "#ff9944"
        
        map_html += f"""
                    <div class="legend-item">
                        <div class="legend-icon" style="background: {color};"></div>
                        <span>{layer_name}</span>
                    </div>
    """
    
    map_html += """
                `;
                return div;
            }};
            legend.addTo(map);
            
            // Coordinates display control
            var coordsDisplay = L.control({ position: 'topleft' });
            coordsDisplay.onAdd = function(map) {
                var div = L.DomUtil.create('div', 'coordinates');
                div.id = 'coords';
                div.innerHTML = `
                    <div style="font-weight: bold; margin-bottom: 3px;">📍 Cursor Position</div>
                    <div id="coord-text">Move mouse over map</div>
                `;
                return div;
            };
            coordsDisplay.addTo(map);
            
            // Update coordinates on mouse move
            map.on('mousemove', function(e) {
                var coordText = document.getElementById('coord-text');
                if (coordText) {
                    coordText.innerHTML = 
                        'Lat: ' + e.latlng.lat.toFixed(5) + '<br>' +
                        'Lon: ' + e.latlng.lng.toFixed(5);
                }
            });
            
            // Info box control
            var info = L.control({ position: 'topright' });
            info.onAdd = function(map) {
                var div = L.DomUtil.create('div', 'info-box');
                div.innerHTML = `
                    <h4>💡 Map Tips</h4>
                    <div style="margin: 5px 0;">
                        🖱️ <strong>Click</strong> to get details<br>
                        🔍 <strong>Scroll</strong> to zoom<br>
                        👆 <strong>Drag</strong> to pan<br>
                        📊 <strong>Layers</strong> on top-right
                    </div>
                `;
                return div;
            };
            info.addTo(map);
            
            // Add click handler for weather info at any location
            map.on('click', function(e) {
                L.popup()
                    .setLatLng(e.latlng)
                    .setContent(`
                        <div style="min-width: 180px;">
                            <h4 style="margin: 0 0 8px; color: #667eea;">📍 Location</h4>
                            <div style="font-size: 12px;">
                                <strong>Latitude:</strong> ${e.latlng.lat.toFixed(5)}<br>
                                <strong>Longitude:</strong> ${e.latlng.lng.toFixed(5)}
                            </div>
                            <div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid #ddd; font-size: 11px; color: #666;">
                                Click the marker to see weather data
                            </div>
                        </div>
                    `)
                    .openOn(map);
            });
            
            // Fit bounds to show Philippines
            var philippinesBounds = L.latLngBounds(
                L.latLng(4.5, 116.0),  // Southwest
                L.latLng(21.0, 127.0)  // Northeast
            );
            
            // Add "Reset View" button
            L.Control.ResetView = L.Control.extend({
                onAdd: function(map) {
                    var button = L.DomUtil.create('div');
                    button.innerHTML = `
                        <button style="
                            background: white;
                            border: 2px solid rgba(0,0,0,0.2);
                            border-radius: 4px;
                            padding: 8px 12px;
                            cursor: pointer;
                            font-size: 13px;
                            font-weight: 600;
                            box-shadow: 0 1px 5px rgba(0,0,0,0.2);
                        " onmouseover="this.style.background='#f0f0f0'" 
                           onmouseout="this.style.background='white'"
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
    
    components.html(map_html, height=700)
    
    # Weather layer legend
    if weather_layers:
        with st.expander("🎨 Layer Legend"):
            for layer in weather_layers:
                if layer == "Precipitation":
                    st.markdown("**🌧️ Precipitation**: Darker blue = heavier rain/snow")
                elif layer == "Temperature":
                    st.markdown("**🌡️ Temperature**: Blue (cold) → Red (hot)")
                elif layer == "Clouds":
                    st.markdown("**☁️ Clouds**: White areas show cloud coverage")
                elif layer == "Wind Speed":
                    st.markdown("**💨 Wind Speed**: Streamlines show wind direction and intensity")
                elif layer == "Pressure":
                    st.markdown("**🌡️ Pressure**: Contour lines show atmospheric pressure (mb)")

# ---------------- Tab 3: Hazard Map ----------------
with tab3:
    st.markdown("### 🛑 Natural Hazard Risk Layers")
    
    if not hazards_enabled:
        st.info("👆 Select hazard layers from the sidebar to display")
    else:
        with st.spinner("Loading hazard data layers..."):
            layers = []
            
            # Process hazard layers
            for hazard_name in hazards_enabled:
                if hazard_name in HAZARD_LAYERS:
                    hazard_config = HAZARD_LAYERS[hazard_name]
                    geo_data = arcgis_geojson(hazard_config["url"])
                    
                    if geo_data.get("features"):
                        layers.append(pdk.Layer(
                            "GeoJsonLayer",
                            data=geo_data,
                            opacity=0.5,
                            stroked=True,
                            filled=True,
                            pickable=True,
                            get_fill_color=hazard_config["color"],
                            get_line_color=hazard_config["line_color"],
                            line_width_min_pixels=1,
                            auto_highlight=True
                        ))
                        st.success(f"{hazard_config['icon']} {hazard_name} layer loaded ({len(geo_data['features'])} features)")
                    else:
                        st.warning(f"⚠️ {hazard_name} layer has no data for this area")
            
            # Typhoon tracks
            if "Typhoon Track" in hazards_enabled:
                track_feats = fetch_typhoon_tracks()
                if track_feats:
                    layers.append(pdk.Layer(
                        "GeoJsonLayer",
                        data={"type": "FeatureCollection", "features": track_feats},
                        stroked=True,
                        filled=False,
                        get_line_color=[255, 0, 0],
                        get_line_width=5,
                        line_width_min_pixels=3,
                        pickable=True
                    ))
                    st.success(f"🌀 Typhoon Track loaded ({len(track_feats)} active systems)")
                else:
                    st.info("✅ No active typhoons detected")
            
            # User location marker
            layers.append(pdk.Layer(
                "ScatterplotLayer",
                data=[{"lat": lat, "lon": lon}],
                get_position='[lon, lat]',
                get_radius=8000,
                get_fill_color=[255, 0, 0, 200],
                pickable=True
            ))
            
            if layers:
                deck = pdk.Deck(
                    initial_view_state=pdk.ViewState(
                        latitude=lat,
                        longitude=lon,
                        zoom=8,
                        pitch=0
                    ),
                    layers=layers,
                    tooltip={
                        "html": "<b>{properties.name}</b><br/>Severity: {properties.severity}",
                        "style": {"color": "white"}
                    }
                )
