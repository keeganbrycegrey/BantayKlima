import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
import streamlit.components.v1 as components
from datetime import datetime, timedelta
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
        font-size: 2.8rem;
        font-weight: 800;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        margin-bottom: 2rem;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.8rem;
        font-weight: 600;
    }
    .stAlert {
        border-radius: 10px;
        border-left: 5px solid;
    }
    .weather-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 15px;
        color: white;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
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
    """Get air quality status"""
    if aqi_index == 1:
        return "Good", "🟢", "#4CAF50"
    elif aqi_index == 2:
        return "Moderate", "🟡", "#FFC107"
    elif aqi_index == 3:
        return "Unhealthy for Sensitive", "🟠", "#FF9800"
    elif aqi_index == 4:
        return "Unhealthy", "🔴", "#F44336"
    elif aqi_index == 5:
        return "Very Unhealthy", "🟣", "#9C27B0"
    elif aqi_index == 6:
        return "Hazardous", "🟤", "#795548"
    return "Unknown", "⚪", "#9E9E9E"

def format_wind_direction(degrees):
    """Convert degrees to cardinal direction"""
    directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                  'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
    idx = int((degrees + 11.25) / 22.5) % 16
    return directions[idx]

def get_uv_category(uv_index):
    """Get UV index category"""
    if uv_index < 3:
        return "Low", "🟢"
    elif uv_index < 6:
        return "Moderate", "🟡"
    elif uv_index < 8:
        return "High", "🟠"
    elif uv_index < 11:
        return "Very High", "🔴"
    else:
        return "Extreme", "🟣"

# ---------------- Cache Configuration ----------------
@st.cache_data(ttl=300, show_spinner=False)
def geocode(query):
    """Geocode location"""
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
    """Fetch current weather"""
    try:
        r = requests.get(
            "http://api.weatherapi.com/v1/current.json",
            params={"key": WEATHERAPI_KEY, "q": f"{lat},{lon}", "aqi": "yes"},
            timeout=20
        )
        r.raise_for_status()
        return r.json()
    except:
        return None

@st.cache_data(ttl=300, show_spinner=False)
def get_weather_forecast(lat, lon, days=7):
    """Fetch forecast weather"""
    try:
        r = requests.get(
            "http://api.weatherapi.com/v1/forecast.json",
            params={"key": WEATHERAPI_KEY, "q": f"{lat},{lon}", "days": days, "aqi": "yes", "alerts": "yes"},
            timeout=20
        )
        r.raise_for_status()
        return r.json()
    except:
        return None

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_typhoon_tracks():
    """Fetch typhoon tracks"""
    try:
        r = requests.get("https://www.gdacs.org/gdacsapi/api/TC/get?eventlist=ongoing", timeout=20)
        r.raise_for_status()
        return r.json().get("features", [])
    except:
        return []

# ---------------- Sidebar ----------------
with st.sidebar:
    st.markdown("# 🌏 BantayKlima")
    st.caption("Philippine Weather Monitor")
    st.markdown("---")
    
    # Location
    st.markdown("### 📍 Location")
    place = st.text_input("🔍 Search Location", placeholder="Manila, Cebu, Davao...")
    
    if place:
        with st.spinner("🔍 Searching..."):
            results = geocode(place)
            if results:
                location_options = [f"{r.get('name', '')}, {r.get('admin1', '')} - {r.get('country', '')}" for r in results]
                selected = st.selectbox("Select:", location_options)
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
            lat = st.number_input("Lat", value=14.5995, format="%.6f")
        with col2:
            lon = st.number_input("Lon", value=120.9842, format="%.6f")
    
    st.markdown("---")
    
    # Forecast Type
    st.markdown("### 🌤️ Forecast")
    forecast_type = st.radio("Type:", ["Current", "Hourly (48h)", "Daily (7d)"], label_visibility="collapsed")
    
    st.markdown("---")
    
    # Map Settings
    st.markdown("### 🗺️ Map Layers")
    weather_layers = st.multiselect(
        "Weather overlays:",
        ["Temperature", "Precipitation", "Wind Animation", "Clouds", "Pressure", "Humidity"],
        default=["Temperature", "Precipitation"],
        label_visibility="collapsed"
    )
    
    map_opacity = st.slider("Opacity", 0.3, 1.0, 0.6, 0.1)
    map_zoom = st.slider("Default Zoom", 5, 12, 8, 1)
    
    st.markdown("---")
    
    # Typhoon Toggle
    st.markdown("### 🌀 Typhoon")
    show_typhoons = st.checkbox("Show Active Typhoons", value=True)
    
    st.markdown("---")
    st.caption("**Data Sources:**")
    st.caption("• WeatherAPI.com")
    st.caption("• OpenWeatherMap")
    st.caption("• GDACS")
    st.caption(f"🕐 {datetime.now().strftime('%I:%M %p')}")

# ---------------- Main Content ----------------
st.markdown('<p class="main-header">🌏 BantayKlima</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Real-time Philippine Weather Monitoring System</p>', unsafe_allow_html=True)

# Weather Alerts
weather_check = get_weather_forecast(lat, lon, days=1)
if weather_check:
    alerts = weather_check.get("alerts", {}).get("alert", [])
    if alerts:
        for alert in alerts:
            st.error(f"🚨 **{alert.get('headline', 'Weather Alert')}**")

# Main tabs
tab1, tab2, tab3 = st.tabs(["📊 Weather Data", "🗺️ Interactive Map", "📈 Analysis"])

# ---------------- Tab 1: Weather Data ----------------
with tab1:
    if forecast_type == "Current":
        weather_data = get_weather_current(lat, lon)
        
        if weather_data:
            current = weather_data.get("current", {})
            location = weather_data.get("location", {})
            condition = current.get("condition", {})
            
            # Header
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
                st.metric("💨 Wind", f"{current.get('wind_kph', 'N/A')} km/h", delta=f"{wind_dir}", delta_color="off")
            with col4:
                st.metric("🌧️ Precipitation", f"{current.get('precip_mm', 'N/A')} mm")
            
            st.markdown("---")
        
        # Weather patterns
        st.markdown("#### 🔍 Weather Patterns & Recommendations")
        
        col_a1, col_a2 = st.columns(2)
        
        with col_a1:
            # Rain analysis
            rainy_days = sum(1 for r in rain_chances if r > 50)
            if rainy_days >= 4:
                st.warning(f"☔ **High Rain Probability**: {rainy_days}/7 days with >50% chance of rain. Carry umbrella daily!")
            elif rainy_days >= 2:
                st.info(f"🌧️ **Moderate Rain**: {rainy_days}/7 days with rain expected. Plan accordingly.")
            else:
                st.success(f"☀️ **Mostly Dry**: Only {rainy_days}/7 days with rain. Good week for outdoor activities!")
            
            # Temperature analysis
            max_temp = max(temps) if temps else 0
            min_temp = min(temps) if temps else 0
            temp_range = max_temp - min_temp
            
            if temp_range > 8:
                st.warning(f"🌡️ **High Temperature Variation**: {temp_range:.1f}°C range. Prepare for varying conditions!")
            else:
                st.success(f"🌡️ **Stable Temperatures**: {temp_range:.1f}°C variation. Consistent weather expected.")
        
        with col_a2:
            # UV warnings
            max_uv = max([d.get("day", {}).get("uv", 0) for d in forecast])
            if max_uv >= 8:
                st.error(f"☀️ **High UV Alert**: Max UV index {max_uv:.0f}. Use sunscreen and protective clothing!")
            elif max_uv >= 6:
                st.warning(f"☀️ **Moderate UV**: Max UV index {max_uv:.0f}. Sun protection recommended.")
            else:
                st.info(f"☀️ **Low UV**: Max UV index {max_uv:.0f}. Minimal sun protection needed.")
            
            # Wind analysis
            max_wind = max([d.get("day", {}).get("maxwind_kph", 0) for d in forecast])
            if max_wind > 40:
                st.warning(f"💨 **Strong Winds Expected**: Up to {max_wind:.0f} km/h. Secure loose objects!")
            elif max_wind > 25:
                st.info(f"💨 **Moderate Winds**: Up to {max_wind:.0f} km/h. Expect breezy conditions.")
            else:
                st.success(f"💨 **Calm Conditions**: Max {max_wind:.0f} km/h. Light winds throughout the week.")
        
        st.markdown("---")
        
        # Best days analysis
        st.markdown("#### 🌟 Best Days This Week")
        
        daily_scores = []
        for i, day in enumerate(forecast):
            day_data = day.get("day", {})
            date = day.get("date", "")
            
            # Calculate comfort score (0-100)
            score = 100
            
            # Temperature factor (ideal: 25-28°C)
            avg_temp = day_data.get("avgtemp_c", 25)
            if avg_temp < 20 or avg_temp > 32:
                score -= 20
            elif avg_temp < 23 or avg_temp > 30:
                score -= 10
            
            # Rain factor
            rain_chance = day_data.get("daily_chance_of_rain", 0)
            score -= rain_chance * 0.5
            
            # Wind factor
            wind = day_data.get("maxwind_kph", 0)
            if wind > 40:
                score -= 20
            elif wind > 25:
                score -= 10
            
            # UV factor
            uv = day_data.get("uv", 0)
            if uv > 8:
                score -= 10
            
            daily_scores.append({
                "date": pd.to_datetime(date),
                "score": max(0, score),
                "condition": day_data.get("condition", {}).get("text", ""),
                "temp": day_data.get("avgtemp_c", 0),
                "rain_chance": rain_chance
            })
        
        # Sort by score
        daily_scores.sort(key=lambda x: x["score"], reverse=True)
        
        col_best1, col_best2, col_best3 = st.columns(3)
        
        for i, col in enumerate([col_best1, col_best2, col_best3]):
            if i < len(daily_scores):
                day_info = daily_scores[i]
                medal = ["🥇", "🥈", "🥉"][i]
                
                with col:
                    st.markdown(f"""
                    <div style='background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                                padding:1rem;border-radius:10px;color:white;text-align:center;'>
                        <h2>{medal}</h2>
                        <h3>{day_info['date'].strftime('%A, %b %d')}</h3>
                        <p style='font-size:1.2rem;margin:10px 0;'>{day_info['condition']}</p>
                        <p style='font-size:1rem;'>🌡️ {day_info['temp']:.1f}°C</p>
                        <p style='font-size:1rem;'>☔ {day_info['rain_chance']:.0f}% rain</p>
                        <p style='font-size:0.9rem;margin-top:10px;opacity:0.9;'>
                            Comfort Score: {day_info['score']:.0f}/100
                        </p>
                    </div>
                    """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Activity recommendations
        st.markdown("#### 🎯 Activity Recommendations")
        
        col_act1, col_act2 = st.columns(2)
        
        with col_act1:
            st.markdown("##### 🏖️ Outdoor Activities")
            good_outdoor_days = [d for d in daily_scores if d['score'] >= 70 and d['rain_chance'] < 30]
            
            if good_outdoor_days:
                st.success(f"✅ **{len(good_outdoor_days)} good days** for outdoor activities!")
                for day in good_outdoor_days[:3]:
                    st.caption(f"• {day['date'].strftime('%A, %b %d')} - {day['condition']}")
            else:
                st.warning("⚠️ Limited ideal outdoor days this week. Plan flexible activities.")
        
        with col_act2:
            st.markdown("##### 🏠 Indoor Planning")
            poor_days = [d for d in daily_scores if d['score'] < 60 or d['rain_chance'] > 60]
            
            if poor_days:
                st.info(f"🏠 **{len(poor_days)} days** better suited for indoor activities")
                for day in poor_days[:3]:
                    st.caption(f"• {day['date'].strftime('%A, %b %d')} - {day['rain_chance']:.0f}% rain chance")
            else:
                st.success("✅ Great week ahead! All days suitable for outdoor plans.")

# ---------------- Footer ----------------
st.markdown("---")

# Typhoon status
typhoon_info = fetch_typhoon_tracks()
if typhoon_info:
    st.warning(f"🌀 **{len(typhoon_info)} Active Typhoon(s)** detected in the region. Stay updated with official advisories!")

st.markdown("""
<div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
            padding: 30px; border-radius: 15px; text-align: center; color: white; margin-top: 20px;'>
    <h2 style='margin: 0; color: white;'>🌏 BantayKlima</h2>
    <p style='margin: 15px 0 5px 0; font-size: 1rem; opacity: 0.95;'>
        Philippine Weather Monitoring System
    </p>
    <p style='margin: 5px 0; font-size: 0.9rem; opacity: 0.85;'>
        Powered by WeatherAPI.com • OpenWeatherMap Maps 2.0 • GDACS
    </p>
    <p style='margin: 15px 0 5px 0; font-size: 0.85rem; opacity: 0.8;'>
        ⚠️ For emergencies, always follow official PAGASA advisories
    </p>
    <p style='margin: 5px 0 0 0; font-size: 0.75rem; opacity: 0.75;'>
        Data updates: Weather ~5min • Maps ~60min • Typhoons ~Real-time
    </p>
</div>
""", unsafe_allow_html=True)

# ---------------- Sidebar Extras ----------------
with st.sidebar:
    st.markdown("---")
    
    # Quick Info
    with st.expander("ℹ️ About BantayKlima", expanded=False):
        st.markdown("""
        **BantayKlima** means "Weather Watch" in Filipino.
        
        🎯 **Features:**
        - Real-time weather data
        - 7-day forecasts
        - Interactive Maps 2.0
        - Typhoon tracking
        - Air quality monitoring
        - Weather analysis & insights
        - Activity recommendations
        
        🔄 **Data Freshness:**
        - Weather: 5 minutes
        - Map tiles: 1 hour
        - Typhoons: Real-time
        
        🌐 **Coverage:**
        - Philippines & surrounding regions
        - Global weather maps
        """)
    
    # Tips
    with st.expander("💡 Pro Tips", expanded=False):
        st.markdown("""
        **Map Navigation:**
        - Click layers to toggle
        - Switch base maps
        - Hover for coordinates
        - Use reset button
        
        **Best Practices:**
        - Check daily before planning
        - Monitor typhoon alerts
        - Use Analysis tab for planning
        - Compare multiple days
        
        **Layer Combinations:**
        - Temp + Wind Animation
        - Precipitation + Clouds
        - All layers for full picture
        """)
    
    # Data accuracy
    with st.expander("📊 Data Sources", expanded=False):
        st.markdown("""
        **Weather Data:**
        - Provider: WeatherAPI.com
        - Update: Every 15 minutes
        - Accuracy: High (professional grade)
        
        **Map Visualization:**
        - Provider: OpenWeatherMap
        - API: Maps 2.0
        - Update: Hourly
        - Resolution: High-definition
        
        **Typhoon Tracking:**
        - Provider: GDACS
        - Sources: Multiple agencies
        - Update: Real-time
        - Coverage: Global disasters
        """)
    
    # Refresh button
    st.markdown("---")
    if st.button("🔄 Refresh Data", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    st.caption("Made with ❤️ for the Philippines")
            
            # Secondary metrics
            col5, col6, col7, col8 = st.columns(4)
            with col5:
                st.metric("☁️ Clouds", f"{current.get('cloud', 'N/A')}%")
            with col6:
                st.metric("👁️ Visibility", f"{current.get('vis_km', 'N/A')} km")
            with col7:
                st.metric("🌡️ Pressure", f"{current.get('pressure_mb', 'N/A')} mb")
            with col8:
                uv = current.get('uv', 0)
                uv_cat, uv_icon = get_uv_category(uv)
                st.metric("☀️ UV Index", f"{uv} {uv_icon}", delta=uv_cat, delta_color="off")

            # Air Quality
            if current.get('air_quality'):
                st.markdown("---")
                st.markdown("### 🌫️ Air Quality")

                aqi = current['air_quality']
                epa = aqi.get('us-epa-index', 0)
                status, icon, color = get_aqi_status(epa)

                col_aqi1,...
    
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
                        "feelslike_c": hour.get("feelslike_c"),
                        "humidity": hour.get("humidity"),
                        "precip_mm": hour.get("precip_mm"),
                        "wind_kph": hour.get("wind_kph"),
                        "condition": hour.get("condition", {}).get("text"),
                        "chance_of_rain": hour.get("chance_of_rain"),
                        "uv": hour.get("uv"),
                        "pressure_mb": hour.get("pressure_mb")
                    })
            
            df = pd.DataFrame(hourly_data[:48])
            df["time"] = pd.to_datetime(df["time"])
            
            tab_chart, tab_table = st.tabs(["📊 Charts", "📋 Table"])
            
            with tab_chart:
                st.markdown("**🌡️ Temperature**")
                st.line_chart(df.set_index("time")[["temp_c", "feelslike_c"]], height=300)
                
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    st.markdown("**🌧️ Precipitation**")
                    st.area_chart(df.set_index("time")[["precip_mm"]], height=250)
                with col_c2:
                    st.markdown("**💨 Wind Speed**")
                    st.line_chart(df.set_index("time")[["wind_kph"]], height=250)
            
            with tab_table:
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
                    "avgtemp_c": day_data.get("avgtemp_c"),
                    "totalprecip_mm": day_data.get("totalprecip_mm"),
                    "avghumidity": day_data.get("avghumidity"),
                    "maxwind_kph": day_data.get("maxwind_kph"),
                    "daily_chance_of_rain": day_data.get("daily_chance_of_rain"),
                    "uv": day_data.get("uv")
                })
            
            df = pd.DataFrame(daily_data)
            df["date"] = pd.to_datetime(df["date"])
            
            tab_chart, tab_table = st.tabs(["📊 Charts", "📋 Table"])
            
            with tab_chart:
                st.markdown("**🌡️ Temperature Range**")
                st.line_chart(df.set_index("date")[["maxtemp_c", "mintemp_c", "avgtemp_c"]], height=300)
                
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    st.markdown("**🌧️ Precipitation**")
                    st.bar_chart(df.set_index("date")[["totalprecip_mm"]], height=250)
                with col_c2:
                    st.markdown("**☔ Rain Probability**")
                    st.line_chart(df.set_index("date")[["daily_chance_of_rain"]], height=250)
            
            with tab_table:
                st.dataframe(df, use_container_width=True)

# ---------------- Tab 2: Interactive Map ----------------
with tab2:
    st.markdown("### 🗺️ Real-Time Weather Map")
    st.caption(f"Showing: {', '.join(weather_layers) if weather_layers else 'No layers selected'} • Opacity: {int(map_opacity*100)}%")
    
    if not weather_layers and not show_typhoons:
        st.info("👆 Select weather layers or enable typhoon tracking from the sidebar to view the map")
    
    # Layer codes
    layer_map = {
        "Temperature": "TA2",
        "Precipitation": "PR0",
        "Wind Animation": "WND",
        "Clouds": "CL",
        "Pressure": "APM",
        "Humidity": "HRD0"
    }
    
    # Get current weather for popup
    current_weather = get_weather_current(lat, lon)
    temp_display = "N/A"
    condition_display = "Loading..."
    wind_display = "N/A"
    
    if current_weather:
        curr = current_weather.get('current', {})
        temp_display = f"{curr.get('temp_c', 'N/A')}°C"
        condition_display = curr.get('condition', {}).get('text', 'N/A')
        wind_display = f"{curr.get('wind_kph', 'N/A')} km/h"
    
    # Build enhanced map HTML
    map_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        html, body {{ height: 100%; width: 100%; }}
        #map {{ 
            height: 100%; 
            width: 100%; 
            border-radius: 10px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        }}
        .legend {{
            background: rgba(255,255,255,0.95);
            padding: 12px 15px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
            font-family: 'Segoe UI', Arial, sans-serif;
            max-width: 200px;
            font-size: 12px;
        }}
        .legend h4 {{
            margin: 0 0 8px 0;
            font-size: 13px;
            font-weight: 600;
            color: #333;
            border-bottom: 2px solid #667eea;
            padding-bottom: 4px;
        }}
        .legend-item {{
            margin: 6px 0;
            display: flex;
            align-items: center;
            font-size: 11px;
            color: #555;
        }}
        .legend-color {{
            width: 18px;
            height: 18px;
            border-radius: 3px;
            margin-right: 6px;
            border: 1px solid rgba(0,0,0,0.2);
        }}
        .coords-box {{
            background: rgba(0,0,0,0.85);
            color: white;
            padding: 8px 12px;
            border-radius: 6px;
            font-family: 'Courier New', monospace;
            font-size: 11px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.4);
            line-height: 1.5;
        }}
        .leaflet-popup-content {{
            margin: 12px;
            font-family: 'Segoe UI', Arial, sans-serif;
        }}
        .leaflet-popup-content h3 {{
            margin: 0 0 10px 0;
            color: #667eea;
            font-size: 15px;
            border-bottom: 2px solid #667eea;
            padding-bottom: 4px;
        }}
        @keyframes pulse {{
            0% {{ transform: scale(1); opacity: 1; }}
            50% {{ transform: scale(1.3); opacity: 0.4; }}
            100% {{ transform: scale(1); opacity: 1; }}
        }}
        .pulse-marker {{
            animation: pulse 2s ease-in-out infinite;
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    <script>
        try {{
            // Initialize map
            var map = L.map('map', {{
                center: [{lat}, {lon}],
                zoom: {map_zoom},
                zoomControl: true,
                minZoom: 5,
                maxZoom: 15
            }});
            
            // Base layers
            var baseLayers = {{
                "🌙 Dark Mode": L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
                    attribution: '&copy; CartoDB',
                    maxZoom: 19
                }}),
                "🛰️ Satellite": L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
                    attribution: '&copy; Esri',
                    maxZoom: 19
                }}),
                "🗺️ Street Map": L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                    attribution: '&copy; OpenStreetMap',
                    maxZoom: 19
                }}),
                "🏔️ Terrain": L.tileLayer('https://stamen-tiles-{{s}}.a.ssl.fastly.net/terrain/{{z}}/{{x}}/{{y}}.jpg', {{
                    attribution: '&copy; Stamen Design',
                    maxZoom: 18
                }})
            }};
            
            // Add default base layer
            baseLayers["🌙 Dark Mode"].addTo(map);
            
            // Weather overlays
            var weatherOverlays = {{}};
            
"""
    
    # Add weather layers
    for layer_name in weather_layers:
        code = layer_map.get(layer_name)
        if code:
            map_html += f"""
            // Add {layer_name} layer
            weatherOverlays["🌤️ {layer_name}"] = L.tileLayer(
                'https://maps.openweathermap.org/maps/2.0/weather/1h/{code}/{{z}}/{{x}}/{{y}}?appid={OPENWEATHER_KEY}&opacity={map_opacity}',
                {{
                    attribution: 'OpenWeatherMap',
                    opacity: 1.0,
                    maxZoom: 15
                }}
            ).addTo(map);
            
"""
    
    # Add typhoon tracking
    if show_typhoons:
        typhoons = fetch_typhoon_tracks()
        if typhoons:
            map_html += """
            // Typhoon layer
            var typhoonLayer = L.layerGroup();
            
"""
            for idx, feature in enumerate(typhoons):
                coords = feature.get('geometry', {}).get('coordinates', [])
                props = feature.get('properties', {})
                name = props.get('name', f'Typhoon {idx+1}')
                
                if coords:
                    if isinstance(coords[0], list):
                        # It's a line (track)
                        latlngs = [[c[1], c[0]] for c in coords]
                        map_html += f"""
            L.polyline({latlngs}, {{
                color: '#ff0000',
                weight: 4,
                opacity: 0.8,
                dashArray: '10, 5'
            }}).bindPopup('<b>🌀 {name}</b><br>Track').addTo(typhoonLayer);
            
"""
                    else:
                        # It's a point (current position)
                        map_html += f"""
            L.circleMarker([{coords[1]}, {coords[0]}], {{
                radius: 10,
                fillColor: '#ff0000',
                color: '#ffffff',
                weight: 3,
                opacity: 1,
                fillOpacity: 0.8
            }}).bindPopup('<b>🌀 {name}</b><br>Current Position').addTo(typhoonLayer);
            
"""
            
            map_html += """
            typhoonLayer.addTo(map);
            weatherOverlays["🌀 Active Typhoons"] = typhoonLayer;
            
"""
    
    # Add location marker and controls
    map_html += f"""
            // User location marker with pulsing effect
            var locationIcon = L.divIcon({{
                className: 'pulse-marker',
                html: '<div style="width:20px;height:20px;background:#ff0000;border:4px solid white;border-radius:50%;box-shadow:0 0 20px rgba(255,0,0,0.8);"></div>',
                iconSize: [28, 28],
                iconAnchor: [14, 14]
            }});
            
            var marker = L.marker([{lat}, {lon}], {{ icon: locationIcon }}).addTo(map);
            
            marker.bindPopup(`
                <h3>📍 Your Location</h3>
                <div style="margin-top:8px;font-size:13px;">
                    <p style="margin:4px 0;"><strong>🌡️ Temperature:</strong> {temp_display}</p>
                    <p style="margin:4px 0;"><strong>☁️ Conditions:</strong> {condition_display}</p>
                    <p style="margin:4px 0;"><strong>💨 Wind:</strong> {wind_display}</p>
                </div>
                <div style="margin-top:10px;padding-top:8px;border-top:1px solid #ddd;font-size:11px;color:#666;">
                    <strong>Coordinates:</strong><br>
                    Lat: {lat:.6f}<br>
                    Lon: {lon:.6f}
                </div>
            `).openPopup();
            
            // 20km radius circle
            L.circle([{lat}, {lon}], {{
                color: '#667eea',
                fillColor: '#667eea',
                fillOpacity: 0.06,
                radius: 20000,
                weight: 2,
                dashArray: '10, 5'
            }}).addTo(map);
            
            // Add layer control
            L.control.layers(baseLayers, weatherOverlays, {{
                position: 'topright',
                collapsed: false
            }}).addTo(map);
            
            // Add scale
            L.control.scale({{
                position: 'bottomleft',
                imperial: false,
                metric: true
            }}).addTo(map);
            
            // Coordinates display
            var coordControl = L.control({{ position: 'topleft' }});
            coordControl.onAdd = function(map) {{
                var div = L.DomUtil.create('div', 'coords-box');
                div.innerHTML = '<strong>📍 Cursor</strong><div id="coords">Hover map</div>';
                return div;
            }};
            coordControl.addTo(map);
            
            // Update coordinates on hover
            map.on('mousemove', function(e) {{
                var coordsDiv = document.getElementById('coords');
                if (coordsDiv) {{
                    coordsDiv.innerHTML = 'Lat: ' + e.latlng.lat.toFixed(5) + '<br>Lon: ' + e.latlng.lng.toFixed(5);
                }}
            }});
            
            // Reset view button
            var resetControl = L.control({{ position: 'topleft' }});
            resetControl.onAdd = function(map) {{
                var div = L.DomUtil.create('div', 'leaflet-bar leaflet-control');
                div.innerHTML = `<a href="#" style="
                    display:block;
                    padding:6px 12px;
                    background:white;
                    color:#333;
                    text-decoration:none;
                    font-size:12px;
                    font-weight:600;
                    border-radius:4px;
                    box-shadow:0 1px 5px rgba(0,0,0,0.4);
                " title="Reset View">🎯 Reset</a>`;
                
                div.onclick = function(e) {{
                    e.preventDefault();
                    map.setView([{lat}, {lon}], {map_zoom});
                }};
                
                return div;
            }};
            resetControl.addTo(map);
            
            console.log('Map initialized successfully');
            
        }} catch (error) {{
            console.error('Map initialization error:', error);
            document.getElementById('map').innerHTML = '<div style="padding:20px;text-align:center;color:#666;">⚠️ Map failed to load. Please refresh the page.</div>';
        }}
    </script>
</body>
</html>
"""
    
    # Render map
    components.html(map_html, height=800, scrolling=False)
    
    # Legend info
    if weather_layers:
        with st.expander("📖 Layer Information", expanded=False):
            st.markdown("#### OpenWeatherMap Maps 2.0 Layers")
            
            for layer in weather_layers:
                if layer == "Temperature":
                    st.markdown("**🌡️ Temperature (TA2)** - Air temperature at 2m height. Blue=cold, Red=hot")
                elif layer == "Precipitation":
                    st.markdown("**🌧️ Precipitation (PR0)** - Rainfall/snowfall intensity in mm/h")
                elif layer == "Wind Animation":
                    st.markdown("**🌪️ Wind Animation (WND)** - Live wind flow with particle effects")
                elif layer == "Clouds":
                    st.markdown("**☁️ Clouds (CL)** - Cloud coverage percentage")
                elif layer == "Pressure":
                    st.markdown("**🌡️ Pressure (APM)** - Atmospheric pressure in hPa")
                elif layer == "Humidity":
                    st.markdown("**💧 Humidity (HRD0)** - Relative humidity percentage")
            
            st.info("💡 **Tip**: Layers update every hour. Combine multiple layers for better analysis!")

# ---------------- Tab 3: Analysis ----------------
with tab3:
    st.markdown("### 📈 Weather Analysis & Insights")
    
    weather_data = get_weather_forecast(lat, lon, days=7)
    if weather_data:
        forecast = weather_data.get("forecast", {}).get("forecastday", [])
        
        # Summary stats
        col1, col2, col3 = st.columns(3)
        
        temps = [d.get("day", {}).get("avgtemp_c", 0) for d in forecast]
        precips = [d.get("day", {}).get("totalprecip_mm", 0) for d in forecast]
        rain_chances = [d.get("day", {}).get("daily_chance_of_rain", 0) for d in forecast]
        
        with col1:
            avg_temp = sum(temps) / len(temps) if temps else 0
            st.metric("📊 Avg Temperature (7d)", f"{avg_temp:.1f}°C")
        with col2:
            total_precip = sum(precips)
            st.metric("📊 Total Precipitation (7d)", f"{total_precip:.1f} mm")
        with col3:
            avg_rain = sum(rain_chances) / len(rain_chances) if rain_chances else 0
            st.metric("📊 Avg Rain Chance (7d)", f"{avg_rain:.0f}%")
        
        st.markdown("---")
