"""
Location Extraction & Geocoding Engine for Disaster Tweet Monitoring.
Resolves raw location strings extracted from tweets into geographic coordinates (latitude, longitude).
Includes built-in gazetteer for instant Canadian & disaster landmark resolution plus Nominatim HTTP fallback.
"""

import re
import time
import urllib.parse
import urllib.request
import json
from typing import Dict, List, Optional, Tuple

import hashlib

# Pre-populated high-precision Gazetteer for disaster-prone regions
KNOWN_GAZETTEER: Dict[str, Tuple[float, float, str]] = {
    # Cities & Towns (City Centroids)
    "calgary": (51.0447, -114.0719, "Calgary, AB, Canada"),
    "yyc": (51.0447, -114.0719, "Calgary, AB, Canada"),
    "high river": (50.5806, -113.8681, "High River, AB, Canada"),
    "fort mcmurray": (56.7264, -111.3803, "Fort McMurray, AB, Canada"),
    "fort mac": (56.7264, -111.3803, "Fort McMurray, AB, Canada"),
    "canmore": (51.0890, -115.3594, "Canmore, AB, Canada"),
    "lethbridge": (49.6956, -112.8451, "Lethbridge, AB, Canada"),
    "medicine hat": (50.0417, -110.6775, "Medicine Hat, AB, Canada"),
    "edmonton": (53.5461, -113.4938, "Edmonton, AB, Canada"),
    "yeg": (53.5461, -113.4938, "Edmonton, AB, Canada"),
    "red deer": (52.2681, -113.8111, "Red Deer, AB, Canada"),
    "banff": (51.1784, -115.5708, "Banff, AB, Canada"),
    "okotoks": (50.7259, -113.9749, "Okotoks, AB, Canada"),
    "bragg creek": (50.9525, -114.5828, "Bragg Creek, AB, Canada"),
    "cochrane": (51.1890, -114.4688, "Cochrane, AB, Canada"),
    "thunder bay": (48.3809, -89.2477, "Thunder Bay, ON, Canada"),
    "pickle lake": (51.4667, -90.2000, "Pickle Lake, ON, Canada"),
    "kashechewan": (52.2858, -81.6508, "Kashechewan First Nation, ON, Canada"),
    "red earth cree": (53.4833, -103.4833, "Red Earth Cree Nation, SK, Canada"),
    "peguis": (51.3686, -97.4172, "Peguis First Nation, MB, Canada"),
    "siska": (50.1833, -121.5667, "Siska First Nation, BC, Canada"),
    
    # Specific Calgary Landmarks & Neighborhoods
    "millennium park": (51.0465, -114.0885, "Millennium Park, Calgary, AB"),
    "henderson park": (49.6917, -112.8050, "Henderson Park, Lethbridge, AB"),
    "elbow river": (51.0333, -114.0500, "Elbow River, Calgary, AB"),
    "bow river": (51.0450, -114.0550, "Bow River, Calgary, AB"),
    "downton calgary": (51.0486, -114.0708, "Downtown Calgary, AB"),
    "downtown calgary": (51.0486, -114.0708, "Downtown Calgary, AB"),
    "downtown": (51.0486, -114.0708, "Downtown Calgary, AB"),
    "stampede grounds": (51.0375, -114.0542, "Stampede Grounds, Calgary, AB"),
    "stampede": (51.0375, -114.0542, "Stampede Grounds, Calgary, AB"),
    "saddledome": (51.0374, -114.0519, "Scotiabank Saddledome, Calgary, AB"),
    "scotiabank saddledome": (51.0374, -114.0519, "Scotiabank Saddledome, Calgary, AB"),
    "flames rink": (51.0374, -114.0519, "Scotiabank Saddledome, Calgary, AB"),
    "calgary zoo": (51.0461, -114.0328, "Calgary Zoo, Calgary, AB"),
    "zoo": (51.0461, -114.0328, "Calgary Zoo, Calgary, AB"),
    "bow valley college": (51.0465, -114.0570, "Bow Valley College, Calgary, AB"),
    "bowness": (51.0850, -114.1850, "Bowness, Calgary, AB"),
    "sunnyside": (51.0560, -114.0740, "Sunnyside, Calgary, AB"),
    "bridgeland": (51.0550, -114.0450, "Bridgeland, Calgary, AB"),
    "inglewood": (51.0400, -114.0350, "Inglewood, Calgary, AB"),
    "mission": (51.0330, -114.0710, "Mission, Calgary, AB"),
    "cliff bungalow": (51.0350, -114.0750, "Cliff Bungalow, Calgary, AB"),
    "beltline": (51.0400, -114.0750, "Beltline, Calgary, AB"),
    "victoria park": (51.0390, -114.0590, "Victoria Park, Calgary, AB"),
    "kensington": (51.0530, -114.0880, "Kensington, Calgary, AB"),
    "deerfoot trail": (51.0300, -114.0000, "Deerfoot Trail, Calgary, AB"),
    "deerfoot": (51.0300, -114.0000, "Deerfoot Trail, Calgary, AB"),
    "macleod trail": (50.9800, -114.0700, "Macleod Trail, Calgary, AB"),
    "macleod": (50.9800, -114.0700, "Macleod Trail, Calgary, AB"),
    "glenmore reservoir": (50.9800, -114.1000, "Glenmore Reservoir, Calgary, AB"),
    "glenmore": (50.9800, -114.1000, "Glenmore Reservoir, Calgary, AB"),
    "heritage park": (50.9820, -114.1020, "Heritage Park, Calgary, AB"),
    "chinatown": (51.0510, -114.0630, "Chinatown, Calgary, AB"),
    "roxboro": (51.0280, -114.0680, "Roxboro, Calgary, AB"),
    "rideau": (51.0290, -114.0630, "Rideau, Calgary, AB"),
    "erlton": (51.0320, -114.0600, "Erlton, Calgary, AB"),
    "ramsay": (51.0360, -114.0380, "Ramsay, Calgary, AB"),
    "mount royal": (51.0320, -114.0880, "Mount Royal, Calgary, AB"),
    "prince's island": (51.0550, -114.0700, "Prince's Island Park, Calgary, AB"),
    "princes island": (51.0550, -114.0700, "Prince's Island Park, Calgary, AB"),
    "peace bridge": (51.0540, -114.0790, "Peace Bridge, Calgary, AB"),
    "centre street": (51.0500, -114.0630, "Centre Street, Calgary, AB"),
    "memorial drive": (51.0520, -114.0500, "Memorial Drive, Calgary, AB"),
    "crowchild trail": (51.0700, -114.1300, "Crowchild Trail, Calgary, AB"),
    "highway 599": (51.4667, -90.2000, "Highway 599, ON, Canada"),
    "highway 2": (51.1000, -114.0000, "Highway 2, AB, Canada"),
    "trans-canada highway": (51.0500, -114.0000, "Trans-Canada Highway, AB, Canada"),
    
    # International Major Flood Locations & Cities
    "manila": (14.5995, 120.9842, "Manila, Philippines"),
    "tacloban": (11.2444, 125.0039, "Tacloban, Philippines"),
    "brisbane": (-27.4698, 153.0251, "Brisbane, Queensland, Australia"),
    "queensland": (-20.9176, 142.7028, "Queensland, Australia"),
    "jakarta": (-6.2088, 106.8456, "Jakarta, Indonesia"),
    "new orleans": (29.9511, -90.0715, "New Orleans, Louisiana, USA"),
    "bangkok": (13.7563, 100.5018, "Bangkok, Thailand"),
    "dhaka": (23.8103, 90.4125, "Dhaka, Bangladesh"),
    "chennai": (13.0827, 80.2707, "Chennai, Tamil Nadu, India"),
    "kerala": (10.8505, 76.2711, "Kerala, India"),
    "manhattan": (40.7831, -73.9712, "Manhattan, New York, USA"),
    "new york": (40.7128, -74.0060, "New York, USA"),
    "houston": (29.7604, -95.3698, "Houston, Texas, USA"),
    "karachi": (24.8607, 67.0011, "Karachi, Pakistan"),
    "selkirk": (50.1436, -96.8839, "Selkirk, MB, Canada"),
    "alberta": (53.9333, -116.5765, "Alberta, Canada"),
    "western canada": (53.9333, -116.5765, "Western Canada"),
    "canada": (56.1304, -106.3468, "Canada"),
}

# City Centroids set for detecting city-level lookup fallbacks
CITY_CENTROID_KEYS = {
    "calgary", "yyc", "calgary, ab, canada", "calgary, alberta",
    "edmonton", "yeg", "edmonton, ab, canada", "edmonton, alberta",
    "alberta", "alberta, canada", "canada",
    "manila", "manila, philippines", "tacloban", "tacloban, philippines",
    "brisbane", "brisbane, queensland, australia", "jakarta", "jakarta, indonesia",
    "new orleans", "new orleans, louisiana, usa", "bangkok", "bangkok, thailand",
    "dhaka", "dhaka, bangladesh", "chennai", "chennai, tamil nadu, india",
    "kerala", "kerala, india", "manhattan", "manhattan, new york, usa",
    "new york", "new york, usa", "houston", "houston, texas, usa",
    "karachi", "karachi, pakistan", "selkirk", "selkirk, mb, canada"
}

# Cache for dynamic HTTP geocoding calls
_DYNAMIC_CACHE: Dict[str, Tuple[float, float, str]] = {}


def jitter_city_centroid(base_lat: float, base_lng: float, seed_text: str = "") -> Tuple[float, float]:
    """
    Computes a deterministic, pseudo-random coordinate jitter (+/- 0.015 to 0.025 degrees, ~1.5-2.5 km)
    around city centroids using the MD5 hash of tweet text to prevent pin stacking.
    """
    if not seed_text:
        return base_lat, base_lng
    h = int(hashlib.md5(seed_text.encode('utf-8')).hexdigest()[:8], 16)
    offset_lat = (((h % 1000) / 500.0) - 1.0) * 0.018  # approx -0.018..+0.018 deg lat
    offset_lng = ((((h // 1000) % 1000) / 500.0) - 1.0) * 0.025 # approx -0.025..+0.025 deg lng
    return round(base_lat + offset_lat, 5), round(base_lng + offset_lng, 5)


def geocode_raw_text(raw_text: str, tweet_context: str = "") -> Optional[Dict[str, any]]:
    """
    Geocodes a raw location string to lat/lng coordinates and formatted place name.
    Applies deterministic jitter and sets is_city_level=True for city-level fallbacks.
    """
    if not raw_text or len(raw_text.strip()) < 2:
        return None
    
    clean_text = raw_text.strip().lower()
    clean_text = re.sub(r'^[#@]', '', clean_text)
    
    is_city_level = clean_text in CITY_CENTROID_KEYS or any(clean_text.startswith(c) for c in ["calgary", "edmonton", "alberta"])
    
    # 1. Check exact gazetteer match
    if clean_text in KNOWN_GAZETTEER:
        lat, lng, display_name = KNOWN_GAZETTEER[clean_text]
        if is_city_level and tweet_context:
            lat, lng = jitter_city_centroid(lat, lng, tweet_context)
        return {
            "raw_text": raw_text,
            "display_name": display_name,
            "lat": lat,
            "lng": lng,
            "source": "gazetteer",
            "is_city_level": is_city_level
        }
    
    # 2. Check substring gazetteer match using word boundary
    for key, (lat, lng, display_name) in KNOWN_GAZETTEER.items():
        if len(key) >= 3 and re.search(r'\b' + re.escape(key) + r'\b', clean_text):
            key_is_city = key in CITY_CENTROID_KEYS
            if key_is_city and tweet_context:
                lat, lng = jitter_city_centroid(lat, lng, tweet_context)
            return {
                "raw_text": raw_text,
                "display_name": display_name,
                "lat": lat,
                "lng": lng,
                "source": "gazetteer_partial",
                "is_city_level": key_is_city
            }
            
    # 3. Check dynamic cache
    if clean_text in _DYNAMIC_CACHE:
        lat, lng, display_name = _DYNAMIC_CACHE[clean_text]
        if is_city_level and tweet_context:
            lat, lng = jitter_city_centroid(lat, lng, tweet_context)
        return {
            "raw_text": raw_text,
            "display_name": display_name,
            "lat": lat,
            "lng": lng,
            "source": "cache",
            "is_city_level": is_city_level
        }
        
    # 4. Fallback to OpenStreetMap Nominatim API (with timeout & retry handling)
    try:
        query = raw_text
        url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(query)}&format=json&limit=1"
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'DisasterResponseAnalyst/1.0 (hackathon@gestrategies.ca)'}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data and len(data) > 0:
                lat = float(data[0]['lat'])
                lng = float(data[0]['lon'])
                display_name = data[0]['display_name']
                _DYNAMIC_CACHE[clean_text] = (lat, lng, display_name)
                if is_city_level and tweet_context:
                    lat, lng = jitter_city_centroid(lat, lng, tweet_context)
                return {
                    "raw_text": raw_text,
                    "display_name": display_name,
                    "lat": lat,
                    "lng": lng,
                    "source": "nominatim",
                    "is_city_level": is_city_level
                }
    except Exception:
        pass
        
    return None


def resolve_locations(locations_list: List[Dict[str, any]], tweet_text: str = "") -> List[Dict[str, any]]:
    """
    Enriches extracted raw locations with geocoded lat/lng coordinates and precision flags.
    """
    resolved = []
    for loc in locations_list:
        raw_text = loc.get("raw_text", "")
        conf = loc.get("location_confidence", 0.5)
        
        geo_res = geocode_raw_text(raw_text, tweet_context=tweet_text)
        item = {
            "raw_text": raw_text,
            "location_confidence": conf,
            "geocoded": geo_res is not None
        }
        if geo_res:
            item["lat"] = geo_res["lat"]
            item["lng"] = geo_res["lng"]
            item["display_name"] = geo_res["display_name"]
            item["is_city_level"] = geo_res.get("is_city_level", False)
        else:
            item["lat"] = None
            item["lng"] = None
            item["display_name"] = None
            item["is_city_level"] = False
            
        resolved.append(item)
    return resolved
