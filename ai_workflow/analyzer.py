"""
Disaster Response Tweet Analyzer Engine
Analyzes tweets according to strict requirements:
1. is_relevant (boolean)
2. relevance_confidence (float 0.0 - 1.0)
3. category (infrastructure_damage, evacuation, medical_need, request_for_help, official_update, volunteer_relief_effort, general_concern, other)
4. severity (low, medium, high, critical)
5. locations (array of {"raw_text": str, "location_confidence": float})
6. reasoning (string justification)

Supports both the official Hackathon Gemini API proxy and high-accuracy offline NLP Rule Engine.
"""

import os
import re
import json
import logging
import requests
from typing import Dict, Any, List, Optional, Tuple
from dotenv import load_dotenv

from prompt_template import (
    SYSTEM_PROMPT,
    BATCH_RESPONSE_SCHEMA,
    format_tweet_prompt,
    format_batch_prompt,
    format_summary_prompt,
)
from geocoder import resolve_locations

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

HACKATHON_API_BASE = "https://hackathon-api-new-152590733511.northamerica-northeast2.run.app"

# Multilingual Flood relevance patterns (English, French, Spanish, German, Indonesian, Portuguese, Italian, Chinese + Hashtags)
FLOOD_RELEVANCE_PATTERNS = [
    r'\b(flood|floods|flooding|flooded|inundat(e|ed|ing|ion|ions)|submerge|submerged|under\s+water|underwater|storm\s+surge|flash\s+flood|flashflood|high\s+water|rising\s+water|water\s+rising)\b',
    r'\b(banjir|inondation|inondations|inondé|inonde|submergé|submerge|inundación|inundacion|inundaciones|anegado|hochwasser|überschwemmung|ueberschwemmung|alluvione|enchente|alagamento|洪水)\b',
    r'\b(sandbag|sandbags|sandbagging|dike|levee|dam\s+overflow|overflowing)\b',
    r'#(abflood|mbflood|skflood|onflood|qcflood|bcflood|yycflood|yccflood|calgaryflood|highriverflood|qldflood|rescueph|flood|floods|flooding|inondation|inundacion|hochwasser|banjir)\b',
    # Any hashtag containing "flood" (#qldfloods, #coflood, #floodph, #boulderflood) and #bigwet
    r'#\w*flood\w*|#bigwet',
]

# Non-flood disaster patterns for disaster_type classification
DISASTER_TYPE_PATTERNS = {
    "explosion": r'\b(explosion|explosions|explode|exploded|bomb|bombs|bombing|blast|blasts|detonation|ied)\b|#(prayforboston|bostonmarathon|bostonstrong|westtx|westexplosion)\b',
    "wildfire": r'\b(wildfire|wildfires|bushfire|bushfires|forest\s+fire|fire|fires|blaze|flames)\b|#\w*fires?\b',
    "earthquake": r'\b(earthquake|earthquakes|quake|quakes|tsunami|aftershock|seismic)\b',
    "storm": r'\b(hurricane|typhoon|cyclone|tornado|tornadoes|twister|storm|blizzard|gale)\b',
    "shooting": r'\b(shooting|shootings|gunman|active\s+shooter|gunfire|shot\s+dead|massacre)\b',
    "transport_accident": r'\b(derail|derailment|train\s+crash|plane\s+crash|air\s+crash|shipwreck|car\s+crash|collision|flight\s+crash)\b',
    "haze": r'\b(haze|smog|choking\s+smoke|air\s+pollution)\b|#\w*haze\b',
}

# Sarcasm / Casual / Non-disaster filters
NON_RELEVANT_PATTERNS = [
    r'\b(camping|vacation|party|taco|tequila|skated|tanning|movie|game|poker)\b',
    r'\b(just a joke|lol|haha|lmao|sarcasm|funny)\b',
]

KNOWN_LOCATIONS_REGEX = [
    # Canadian Specific Neighborhoods & Landmarks
    (r'\b(saddledome|scotiabank saddledome|flames rink)\b', 'Scotiabank Saddledome, Calgary, AB', 0.95),
    (r'\b(calgary zoo|zoo)\b', 'Calgary Zoo, Calgary, AB', 0.95),
    (r'\b(stampede grounds|stampede park|stampede parade|stampede)\b', 'Stampede Grounds, Calgary, AB', 0.95),
    (r'\b(bow valley college)\b', 'Bow Valley College, Calgary, AB', 0.95),
    (r'\b(kensington)\b', 'Kensington, Calgary, AB', 0.95),
    (r'\b(downtown calgary|downtown yyc|downtown)\b', 'Downtown Calgary, AB', 0.90),
    (r'\b(deerfoot trail|deerfoot)\b', 'Deerfoot Trail, Calgary, AB', 0.95),
    (r'\b(macleod trail|macleod)\b', 'Macleod Trail, Calgary, AB', 0.95),
    (r'\b(glenmore reservoir|glenmore)\b', 'Glenmore Reservoir, Calgary, AB', 0.95),
    (r'\b(heritage park)\b', 'Heritage Park, Calgary, AB', 0.95),
    (r'\b(chinatown)\b', 'Chinatown, Calgary, AB', 0.95),
    (r'\b(roxboro)\b', 'Roxboro, Calgary, AB', 0.95),
    (r'\b(rideau)\b', 'Rideau, Calgary, AB', 0.95),
    (r'\b(erlton)\b', 'Erlton, Calgary, AB', 0.95),
    (r'\b(ramsay)\b', 'Ramsay, Calgary, AB', 0.95),
    (r'\b(mount royal)\b', 'Mount Royal, Calgary, AB', 0.95),
    (r'\b(prince\'s island|princes island)\b', 'Prince\'s Island Park, Calgary, AB', 0.95),
    (r'\b(peace bridge)\b', 'Peace Bridge, Calgary, AB', 0.95),
    (r'\b(centre street|center street)\b', 'Centre Street, Calgary, AB', 0.90),
    (r'\b(memorial drive)\b', 'Memorial Drive, Calgary, AB', 0.90),
    (r'\b(crowchild trail|crowchild)\b', 'Crowchild Trail, Calgary, AB', 0.95),
    (r'\b(beltline)\b', 'Beltline, Calgary, AB', 0.95),
    (r'\b(millennium park)\b', 'Millennium Park, Calgary, AB', 0.90),
    (r'\b(elbow river)\b', 'Elbow River, Calgary, AB', 0.90),
    (r'\b(bow river)\b', 'Bow River, Calgary, AB', 0.90),
    (r'\b(bowness)\b', 'Bowness, Calgary, AB', 0.90),
    (r'\b(sunnyside)\b', 'Sunnyside, Calgary, AB', 0.90),
    (r'\b(bridgeland)\b', 'Bridgeland, Calgary, AB', 0.90),
    (r'\b(inglewood)\b', 'Inglewood, Calgary, AB', 0.90),
    (r'\b(mission)\b', 'Mission, Calgary, AB', 0.85),
    (r'\b(cliff bungalow)\b', 'Cliff Bungalow, Calgary, AB', 0.90),
    (r'\b(victoria park)\b', 'Victoria Park, Calgary, AB', 0.90),
    (r'\b(high river)\b', 'High River, Alberta', 0.90),
    (r'\b(fort mcmurray|fort mac)\b', 'Fort McMurray, Alberta', 0.90),
    (r'\b(canmore)\b', 'Canmore, Alberta', 0.90),
    (r'\b(lethbridge)\b', 'Lethbridge, Alberta', 0.90),
    (r'\b(medicine hat)\b', 'Medicine Hat, Alberta', 0.90),
    (r'\b(edmonton|yeg)\b', 'Edmonton, Alberta', 0.85),
    (r'\b(banff)\b', 'Banff, Alberta', 0.90),
    (r'\b(okotoks)\b', 'Okotoks, Alberta', 0.90),
    (r'\b(bragg creek)\b', 'Bragg Creek, Alberta', 0.90),
    (r'\b(cochrane)\b', 'Cochrane, Alberta', 0.90),
    (r'\b(thunder bay)\b', 'Thunder Bay, Ontario', 0.90),
    (r'\b(pickle lake)\b', 'Pickle Lake, Ontario', 0.90),
    (r'\b(kashechewan)\b', 'Kashechewan, Ontario', 0.90),
    (r'\b(red earth cree)\b', 'Red Earth Cree, Saskatchewan', 0.90),
    (r'\b(peguis)\b', 'Peguis, Manitoba', 0.90),
    (r'\b(siska)\b', 'Siska, British Columbia', 0.90),
    (r'\b(selkirk)\b', 'Selkirk, Manitoba', 0.90),
    
    # Generic City Fallback
    (r'\b(calgary|yyc)\b', 'Calgary, AB, Canada', 0.75),
    
    # International Locations (with city & country)
    (r'\b(tacloban)\b', 'Tacloban, Philippines', 0.95),
    (r'\b(manila)\b', 'Manila, Philippines', 0.95),
    (r'\b(brisbane)\b', 'Brisbane, Queensland, Australia', 0.95),
    (r'\b(queensland)\b', 'Queensland, Australia', 0.85),
    (r'\b(jakarta)\b', 'Jakarta, Indonesia', 0.95),
    (r'\b(new orleans)\b', 'New Orleans, Louisiana, USA', 0.95),
    (r'\b(bangkok)\b', 'Bangkok, Thailand', 0.95),
    (r'\b(dhaka)\b', 'Dhaka, Bangladesh', 0.95),
    (r'\b(chennai)\b', 'Chennai, Tamil Nadu, India', 0.95),
    (r'\b(kerala)\b', 'Kerala, India', 0.90),
    (r'\b(manhattan)\b', 'Manhattan, New York', 0.95),
    (r'\b(new york|nyc)\b', 'New York, USA', 0.90),
    (r'\b(houston)\b', 'Houston, Texas, USA', 0.95),
    (r'\b(karachi)\b', 'Karachi, Pakistan', 0.95),
    (r'\b(tokyo)\b', 'Tokyo, Japan', 0.95),
    (r'\b(guangzhou)\b', 'Guangzhou, China', 0.95),
    (r'\b(sydney)\b', 'Sydney, Australia', 0.95),
    (r'\b(melbourne)\b', 'Melbourne, Australia', 0.95),
]

JUNK_LOCATION_WORDS = {
    'prince', 'hope', 'titanic', 'criminal minds', 'canada', 'alberta', 'ontario',
    'manitoba', 'saskatchewan', 'quebec', 'british columbia', 'global news', 'news',
    'facebook', 'twitter', 'youtube', 'instagram', 'god', 'lord', 'happy', 'lol',
    'omg', 'rt', 'canadian', 'america', 'american', 'daily', 'today', 'tonight',
    'yesterday', 'tomorrow', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday',
    'saturday', 'sunday', 'january', 'february', 'march', 'april', 'may', 'june',
    'july', 'august', 'september', 'october', 'november', 'december', 'photo',
    'video', 'pics', 'image', 'water', 'flood', 'floods', 'flooding', 'evacuation',
    'here', 'there', 'somewhere', 'everywhere', 'nowhere'
}


def analyze_tweet_nlp(tweet_text: str) -> Dict[str, Any]:
    """
    High-accuracy rule-based & pattern matching analyzer for offline fallback.
    Strictly filters for flood relevance while accurately categorizing non-flood disaster types.
    Supports worldwide location extraction including city, province, and country.
    """
    text = tweet_text.strip()
    text_lower = text.lower()

    # 1. Check for casual/joke context
    is_joke_or_casual = False
    if any(re.search(pat, text_lower) for pat in NON_RELEVANT_PATTERNS):
        if not any(kw in text_lower for kw in ['displace', 'evacuat', 'trapped', 'without power', 'floods displace', 'under water', 'submerged', 'need help', 'storm surge']):
            is_joke_or_casual = True

    # 2. Check Flood Relevance
    flood_matches = []
    for pattern in FLOOD_RELEVANCE_PATTERNS:
        if re.search(pattern, text_lower):
            flood_matches.append(pattern)

    is_relevant = len(flood_matches) > 0 and not is_joke_or_casual

    # 3. Classify disaster_type
    if is_relevant:
        disaster_type = "flood"
    else:
        # Check non-flood disaster keyword rules
        disaster_type = "none"
        if not is_joke_or_casual:
            for dtype, pat in DISASTER_TYPE_PATTERNS.items():
                if re.search(pat, text_lower):
                    disaster_type = dtype
                    break

    confidence = round(min(0.95, 0.75 + (len(flood_matches) * 0.10)), 2) if is_relevant else (0.90 if disaster_type != "none" or is_joke_or_casual else 0.80)

    # 4. Location Extraction (Worldwide & Canadian Gazetteer + Regex)
    extracted_locations = []
    seen_locs = set()

    # Known worldwide & Canadian places
    for pattern, place_name, loc_conf in KNOWN_LOCATIONS_REGEX:
        if re.search(pattern, text_lower):
            if place_name.lower() not in seen_locs:
                seen_locs.add(place_name.lower())
                extracted_locations.append({
                    "raw_text": place_name,
                    "location_confidence": loc_conf
                })

    # Filter out generic city centroids if a specific landmark/neighborhood was extracted
    generic_cities = {'calgary, ab, canada', 'calgary, alberta', 'edmonton, alberta', 'alberta, canada'}
    has_specific = any(loc["raw_text"].lower() not in generic_cities for loc in extracted_locations)
    if has_specific:
        extracted_locations = [loc for loc in extracted_locations if loc["raw_text"].lower() not in generic_cities]

    # Regex for "City, Country" or "City, Province/State, Country" explicitly in text
    formatted_place_matches = re.findall(r'\b([A-Z][a-zA-Z\s]+,\s*[A-Z][a-zA-Z\s]+(?:\s*,\s*[A-Z][a-zA-Z\s]+)?)\b', text)
    for fpm in formatted_place_matches:
        fpm_clean = fpm.strip()
        fpm_lower = fpm_clean.lower()
        if fpm_lower not in seen_locs and not any(w in JUNK_LOCATION_WORDS for w in fpm_lower.split(',')):
            seen_locs.add(fpm_lower)
            extracted_locations.append({
                "raw_text": fpm_clean,
                "location_confidence": 0.90
            })

    # Hashtag location extraction
    hashtags = re.findall(r'#([A-Za-z0-9]+)', text)
    for tag in hashtags:
        tag_clean = tag.lower()
        if tag_clean in ['calgary', 'lethbridge', 'fortmac', 'highriver', 'canmore', 'yyc', 'yeg', 'peguis', 'selkirk', 'tacloban', 'manila', 'brisbane', 'jakarta', 'neworleans']:
            if tag_clean not in seen_locs:
                seen_locs.add(tag_clean)
                extracted_locations.append({
                    "raw_text": tag,
                    "location_confidence": 0.85
                })

    # Strict phrase extractor: requires specific location keywords or multi-word proper nouns not in junk list
    place_candidates = re.findall(r'\b(?:in|near|at|around|de|à|a)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', text)
    location_indicators = {'river', 'park', 'lake', 'road', 'street', 'hwy', 'highway', 'route', 'city', 'town', 'nation', 'bridge', 'creek', 'bay', 'island', 'valley'}

    for p in place_candidates:
        p_clean = p.strip()
        p_lower = p_clean.lower()
        words = p_lower.split()

        # Reject junk words or bare provinces/countries/vague terms
        if any(w in JUNK_LOCATION_WORDS for w in words):
            continue
        if len(p_clean) < 3:
            continue

        has_indicator = any(ind in p_lower for ind in location_indicators)

        if has_indicator or len(words) >= 2:
            if p_lower not in seen_locs:
                seen_locs.add(p_lower)
                extracted_locations.append({
                    "raw_text": p_clean,
                    "location_confidence": 0.80 if has_indicator else 0.70
                })

    if not is_relevant:
        reasoning_map = {
            "explosion": "Tweet describes an explosion event, not flood-related.",
            "wildfire": "Tweet describes a wildfire or fire event, not flood-related.",
            "earthquake": "Tweet describes earthquake activity, not flood-related.",
            "storm": "Tweet describes storm/hurricane conditions without report of flooding.",
            "shooting": "Tweet describes a shooting event, not flood-related.",
            "transport_accident": "Tweet describes a transport accident, not flood-related.",
            "haze": "Tweet describes haze or air pollution, not flood-related.",
            "other": "Tweet describes a non-flood event.",
            "none": "Tweet does not describe active flood or disaster conditions."
        }
        return {
            "is_relevant": False,
            "relevance_confidence": confidence,
            "category": None,
            "severity": None,
            "disaster_type": disaster_type,
            "locations": extracted_locations,
            "reasoning": reasoning_map.get(disaster_type, "Tweet is not flood-related.")
        }

    # 5. Category Classification (for relevant flood tweets)
    category = "general_concern"

    # A request for help, not any mention of "rescue": "rescue team", "Fire & Rescue",
    # "wildlife rescue", "to the rescue" and "rescued" describe responders, not a person in danger.
    strong_request = re.search(
        r"\b(trapped|stranded|sos|send help|need(s|ed)? (a )?rescu\w*|please rescue|rescue (me|us|them|needed)|"
        r"can'?t get out|missing (person|people|man|woman|child|children|boy|girl|senior|elder)|secours)\b|#rescueph",
        text_lower)
    # "Please help" in an appeal (donate, drop off supplies, RT, clean-up, stolen items) is
    # a relief request, not a person in danger.
    weak_request = re.search(r"\b(need help|needs help|please help|help needed)\b", text_lower)
    appeal = re.search(r"donat|drop.?off|supplies|\brt\b|retweet|clean.?up|volunteer|stolen|"
                       r"businesses|services|fundrais|red ?cross|union|spread the word|"
                       # offers of help, not requests: "Need help? Get in touch", "DM if you need help"
                       r"need help\?|if you (need|have)|\bdm\b|get in touch|come on down|offering|#\w*helps\b",
                       text_lower)
    urgent_request = strong_request or (weak_request and not appeal)
    animals_only = (re.search(r'\b(animals?|pets?|dogs?|cats?|horses?|cattle|livestock|wildlife|zoo)\b', text_lower)
                    and not re.search(r'\b(people|person|residents?|family|families|child|children|kids?|man|woman|elderly|senior)\b', text_lower))
    if urgent_request and not animals_only:
        category = "request_for_help"
    elif re.search(r'\b(doctor|hospital|injured|ambulance|medical|blood|triage|blessé)\b', text_lower):
        category = "medical_need"
    elif re.search(r'\b(evacuat|évacuation|evacuation|displac|flee|leave home|shelter order)\b', text_lower):
        category = "evacuation"
    elif re.search(r'\b(bridge|road|route|power|outage|submerged|basement|home flood|under water|underwater|building|dam|dike|impassable|closed|fermée|fermee)\b', text_lower):
        category = "infrastructure_damage"
    elif re.search(r'\b(official|news|city of|police|officials say|mayor|statement|gov|announcement|press release)\b', text_lower) or text.startswith('#News') or 'http' in text_lower:
        category = "official_update"
    elif re.search(r'\b(volunteer|sandbag|donation|red cross|shelter open|food bank|supplies|helping)\b', text_lower):
        category = "volunteer_relief_effort"
    elif re.search(r'\b(pray|solidarity|proud|stay safe|thoughts|thinking of|hope)\b', text_lower):
        category = "general_concern"
    else:
        category = "other"

    # 6. Severity Classification
    severity = "medium"

    hyperbole = re.search(r'drowning in (work|homework|school|debt|tears|emails?|paper(work)?|love|assignments)', text_lower)
    if (category == "request_for_help"
            or (re.search(r'\b(trapped|drowning|life threatening|missing person|injured|emergency call)\b', text_lower)
                and not animals_only and not hyperbole)):
        severity = "critical"
    elif category == "evacuation" or re.search(r'\b(without power|30,000|displace|home flooded|homes under water|under water|no clean water|impassable|major damage|mandatory)\b', text_lower):
        severity = "high"
    elif category in ["general_concern", "volunteer_relief_effort"] or re.search(r'\b(minor|postponed|skated|pics|solidarity|proud)\b', text_lower):
        severity = "low"
    else:
        severity = "medium"

    reasoning_map = {
        "evacuation": "Tweet reports active flood evacuations or displacement.",
        "infrastructure_damage": "Tweet describes physical flood damage to infrastructure or homes.",
        "request_for_help": "Tweet indicates an urgent call for flood emergency rescue.",
        "medical_need": "Tweet highlights medical needs during flood conditions.",
        "official_update": "Tweet shares official flood emergency announcements.",
        "volunteer_relief_effort": "Tweet mentions community flood relief or sandbagging.",
        "general_concern": "Tweet expresses public reaction regarding flood impact.",
        "other": "Tweet provides flood-related emergency information."
    }
    reasoning = reasoning_map.get(category, "Tweet contains flood-related disaster information.")

    return {
        "is_relevant": True,
        "relevance_confidence": confidence,
        "category": category,
        "severity": severity,
        "disaster_type": "flood",
        "locations": extracted_locations,
        "reasoning": reasoning
    }


def call_hackathon_gemini_api(prompt: str, response_schema: Optional[Dict] = None) -> Tuple[Optional[str], Optional[int]]:
    """
    Calls the official Hackathon Gemini API proxy at:
    POST https://hackathon-api-new-152590733511.northamerica-northeast2.run.app/api/generate
    Headers: X-API-Key: <HACKATHON_API_KEY / GEMINI_API_KEY / GOOGLE_API_KEY>

    Returns (text_response, requests_remaining).

    QUOTA LOCK: these calls are one request PER TWEET, and the hackathon quota is
    small, so they only happen when ALLOW_PER_TWEET_LLM=1 is set on purpose.
    Otherwise callers (batch_processor.py, app.py) fall back to the free NLP engine.
    The deployed backend doesn't use this — it batches 50 tweets per request itself.
    """
    if os.environ.get("ALLOW_PER_TWEET_LLM", "0").lower() not in ("1", "true", "yes"):
        return None, None

    api_key = (
        os.environ.get("HACKATHON_API_KEY") or
        os.environ.get("GEMINI_API_KEY") or
        os.environ.get("GOOGLE_API_KEY")
    )
    if not api_key:
        logger.warning("No API key configured in HACKATHON_API_KEY, GEMINI_API_KEY, or GOOGLE_API_KEY.")
        return None, None

    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "contents": prompt
    }
    if response_schema:
        payload["response_schema"] = response_schema

    try:
        url = f"{HACKATHON_API_BASE}/api/generate"
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        if res.status_code == 200:
            data = res.json()
            text = data.get("text")
            remaining = data.get("requests_remaining")
            return text, remaining
        else:
            logger.warning(f"Hackathon API returned status {res.status_code}: {res.text}")
            return None, None
    except Exception as e:
        logger.warning(f"Hackathon API exception: {e}")
        return None, None


def analyze_tweet_llm(tweet_text: str) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
    """
    Evaluates tweet using the official Hackathon Gemini API proxy.
    Returns (result_dict, requests_remaining).
    """
    prompt = format_tweet_prompt(tweet_text)
    text_resp, remaining = call_hackathon_gemini_api(prompt)
    if text_resp:
        try:
            content = text_resp.strip()
            if content.startswith("```"):
                content = re.sub(r'^```json\s*', '', content)
                content = re.sub(r'^```\s*', '', content)
                content = re.sub(r'\s*```$', '', content)
            return json.loads(content), remaining
        except Exception as e:
            logger.warning(f"Failed to parse LLM JSON response: {e}")
    return None, remaining


def analyze_tweet(tweet_text: str, geocode: bool = True) -> Dict[str, Any]:
    """
    Main entrypoint for analyzing a tweet.
    Tries LLM first via Hackathon API proxy, falls back seamlessly to NLP rule engine.
    """
    result, _ = analyze_tweet_llm(tweet_text)
    if not result:
        result = analyze_tweet_nlp(tweet_text)

    if "is_relevant" not in result:
        result["is_relevant"] = False
    if "relevance_confidence" not in result:
        result["relevance_confidence"] = 0.5
    if "category" not in result:
        result["category"] = None
    if "disaster_type" not in result:
        result["disaster_type"] = "flood" if result.get("is_relevant") else "none"
    if "locations" not in result or not isinstance(result["locations"], list):
        result["locations"] = []
    if "reasoning" not in result:
        result["reasoning"] = "Analysis complete."

    if result["is_relevant"] and geocode and result["locations"]:
        # Standardize format for geocoder
        formatted_locs = []
        for l in result["locations"]:
            if isinstance(l, dict):
                formatted_locs.append(l)
            elif isinstance(l, str):
                formatted_locs.append({"raw_text": l, "location_confidence": 0.85})
        result["locations"] = resolve_locations(formatted_locs, tweet_text=tweet_text)

    return result
