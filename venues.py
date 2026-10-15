"""
VENUES — team to stadium city + lat/lon for historical weather lookups.
=======================================================================
Lat/lon let us pull Open-Meteo historical weather for each game.
If a team's stadium is indoor (Miami Marlins, Rangers, etc.) we flag it
so the backtest skips weather modeling.
"""

# city → (lat, lon, indoor_flag)
_CITY_META = {
    # MLB
    "arizona":      (33.4453, -112.0667, True),   # Chase Field, retractable
    "atlanta":      (33.8906, -84.4677, False),
    "baltimore":    (39.2838, -76.6218, False),
    "boston":       (42.3467, -71.0972, False),
    "chicago":      (41.9484, -87.6553, False),   # Wrigley (NL) & Guaranteed (AL)
    "cincinnati":   (39.0974, -84.5080, False),
    "cleveland":    (41.4962, -81.6852, False),
    "colorado":     (39.7559, -104.9942, False),  # Coors
    "detroit":      (42.3390, -83.0485, False),
    "houston":      (29.7573, -95.3555, True),    # Minute Maid, retractable
    "kansas city":  (39.0517, -94.4803, False),
    "los angeles":  (34.0739, -118.2400, False),  # Dodger Stadium
    "miami":        (25.7781, -80.2197, True),    # loanDepot, retractable
    "milwaukee":    (43.0280, -87.9712, True),    # American Family, retractable
    "minnesota":    (44.9817, -93.2777, False),
    "new york":     (40.7571, -73.8458, False),   # Yankee / Citi both outdoor
    "oakland":      (37.7516, -122.2005, False),
    "philadelphia": (39.9061, -75.1665, False),
    "pittsburgh":   (40.4469, -80.0057, False),
    "san diego":    (32.7076, -117.1570, False),
    "san francisco":(37.7786, -122.3893, False),
    "seattle":      (47.5914, -122.3326, True),   # T-Mobile, retractable
    "st. louis":    (38.6226, -90.1928, False),
    "tampa":        (27.7682, -82.6534, True),    # Tropicana (dome)
    "texas":        (32.7473, -97.0847, True),    # Globe Life, retractable
    "arlington":    (32.7473, -97.0847, True),
    "toronto":      (43.6414, -79.3894, True),    # Rogers, retractable
    "washington":   (38.8730, -77.0074, False),

    # NFL (outdoor fields only tracked for weather; indoors ignored anyway)
    "buffalo":      (42.7738, -78.7869, False),   # Highmark
    "chicago bears":(41.8623, -87.6167, False),   # Soldier Field (city key chicago overlaps MLB)
    "green bay":    (44.5013, -88.0622, False),
    "nashville":    (36.1665, -86.7713, False),
    "denver":       (39.7439, -105.0201, False),
    "foxborough":   (42.0909, -71.2643, False),
    "east rutherford":(40.8135, -74.0745, False), # MetLife
    "jacksonville": (30.3239, -81.6373, False),
    "charlotte":    (35.2258, -80.8528, False),
    "miami gardens":(25.9580, -80.2389, False),

    # NBA / NHL ignored for weather (indoor only); not keyed here on purpose.
}


# Common ESPN team-name → stadium-city lookups.
# Only teams whose weather matters (MLB, NFL outdoor) are listed; others
# fall through to None and the backtest treats them as weather-irrelevant.
TEAM_TO_CITY = {
    # MLB
    "Arizona Diamondbacks":    "arizona",
    "Atlanta Braves":          "atlanta",
    "Baltimore Orioles":       "baltimore",
    "Boston Red Sox":          "boston",
    "Chicago Cubs":            "chicago",
    "Chicago White Sox":       "chicago",
    "Cincinnati Reds":         "cincinnati",
    "Cleveland Guardians":     "cleveland",
    "Colorado Rockies":        "colorado",
    "Detroit Tigers":          "detroit",
    "Houston Astros":          "houston",
    "Kansas City Royals":      "kansas city",
    "Los Angeles Angels":      "los angeles",
    "Los Angeles Dodgers":     "los angeles",
    "Miami Marlins":           "miami",
    "Milwaukee Brewers":       "milwaukee",
    "Minnesota Twins":         "minnesota",
    "New York Mets":           "new york",
    "New York Yankees":        "new york",
    "Oakland Athletics":       "oakland",
    "Athletics":               "oakland",
    "Philadelphia Phillies":   "philadelphia",
    "Pittsburgh Pirates":      "pittsburgh",
    "San Diego Padres":        "san diego",
    "San Francisco Giants":    "san francisco",
    "Seattle Mariners":        "seattle",
    "St. Louis Cardinals":     "st. louis",
    "Tampa Bay Rays":          "tampa",
    "Texas Rangers":           "arlington",
    "Toronto Blue Jays":       "toronto",
    "Washington Nationals":    "washington",

    # NFL
    "Buffalo Bills":           "buffalo",
    "Chicago Bears":           "chicago bears",
    "Green Bay Packers":       "green bay",
    "Tennessee Titans":        "nashville",
    "Denver Broncos":          "denver",
    "New England Patriots":    "foxborough",
    "New York Jets":           "east rutherford",
    "New York Giants":         "east rutherford",
    "Jacksonville Jaguars":    "jacksonville",
    "Carolina Panthers":       "charlotte",
    "Miami Dolphins":          "miami gardens",
    "Pittsburgh Steelers":     "pittsburgh",
    "Cincinnati Bengals":      "cincinnati",
    "Cleveland Browns":        "cleveland",
    "Kansas City Chiefs":      "kansas city",
    "Baltimore Ravens":        "baltimore",
    "Washington Commanders":   "washington",
    "Philadelphia Eagles":     "philadelphia",
}


def venue_for(home_team: str) -> dict:
    """
    Returns {'city': str, 'lat': float, 'lon': float, 'indoor': bool} for
    the home team's stadium, or {} if we don't track that venue.
    """
    city = TEAM_TO_CITY.get(home_team)
    if not city:
        return {}
    meta = _CITY_META.get(city)
    if not meta:
        return {}
    lat, lon, indoor = meta
    return {"city": city, "lat": lat, "lon": lon, "indoor": indoor}
