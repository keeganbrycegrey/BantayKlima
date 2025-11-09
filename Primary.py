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
    
    # Enhanced Leaflet map
    map_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
            #map {{ height: 650px; width: 100%; border-radius: 10px; }}
            .legend {{
                background: white;
                padding: 10px;
                border-radius: 5px;
                box-shadow: 0 0 15px rgba(0,0,0,0.2);
            }}
            .legend h4 {{ margin: 0 0 5px; }}
        </style>
    </head>
    <body>
        <div id="map"></div>
        <script>
            var map = L.map('map').setView([{lat}, {lon}], 7);
            
            // Dark base map for better visibility
            L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
                attribution: '© OpenStreetMap, © CartoDB',
                maxZoom: 19
            }}).addTo(map);
    """
    
    # Add weather layers
    for layer_name in weather_layers:
        owm_layer = layer_map.get(layer_name)
        if owm_layer:
            map_html += f"""
            L.tileLayer('https://tile.openweathermap.org/map/{owm_layer}/{{z}}/{{x}}/{{y}}.png?appid={OPENWEATHER_KEY}', {{
                attribution: 'Weather: OpenWeatherMap',
                opacity: {map_opacity}
            }}).addTo(map);
    """
    
    # Add location marker with custom icon
    map_html += f"""
            var redIcon = L.icon({{
                iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
                shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
                iconSize: [25, 41],
                iconAnchor: [12, 41],
                popupAnchor: [1, -34],
                shadowSize: [41, 41]
            }});
            
            L.marker([{lat}, {lon}], {{icon: redIcon}}).addTo(map)
                .bindPopup('<b>📍 Your Location</b><br>Lat: {lat:.4f}<br>Lon: {lon:.4f}')
                .openPopup();
            
            // Add scale
            L.control.scale().addTo(map);
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
