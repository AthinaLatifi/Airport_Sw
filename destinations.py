"""
destinations.py - Analyze unique flight destinations or origins for an airport and date.

Features:
- Fetches arrivals or departures for an airport and date using SwedaviaClient.
- Cleans city names by stripping trailing airport codes (e.g. "London LHR" -> "London").
- Maps unique cities to their respective countries using `city_country.json`.
- Aggregates and ranks cities sorted by flight volume descending.
- Supports optional filtering by city name or country name.
- Beautiful terminal output with flight counts, percentage shares, and visual bar charts.
- Supports both interactive terminal mode and command-line arguments.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from swedavia_client import (
    AIRPORTS,
    SwedaviaClient,
    filter_valid_flights,
    normalize_text,
    parse_date_input,
    prompt_airport,
    prompt_date,
    resolve_airport,
)

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Path to city-country mapping JSON file
DATA_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "city_country.json")


def load_city_country_data() -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    """
    Load city-to-country and country-to-cities mappings from city_country.json.
    """
    if not os.path.exists(DATA_FILE_PATH):
        return {}, {}

    try:
        with open(DATA_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("city_to_country", {}), data.get("country_to_cities", {})
    except Exception as e:
        print(f"[!] Warning: Could not load city_country.json: {e}", file=sys.stderr)
        return {}, {}


def clean_city_name(raw_name: str) -> str:
    """
    Clean an airport/city name by removing trailing airport codes and whitespace.
    Examples:
      'London LHR'          -> 'London'
      'Paris CDG'           -> 'Paris'
      'Stockholm ARN'       -> 'Stockholm'
      'Frankfurt FRA'       -> 'Frankfurt'
      'London (LHR)'        -> 'London'
      'Palma de Mallorca PMI' -> 'Palma de Mallorca'
    """
    if not raw_name:
        return "Unknown"

    name = raw_name.strip()

    # Remove 3-letter IATA code at the end, whether in parentheses or preceded by space/dash
    # e.g., 'London LHR', 'London (LHR)', 'London - LHR'
    name = re.sub(r"[\s\-/]+(\(?[A-Za-z]{3}\)?)$", "", name).strip()

    # Remove generic airport words if present at the end
    name = re.sub(r"(?i)\s+(airport|flygplats|intl|international)$", "", name).strip()

    # Simplify dual airport-city Swedish names
    simplifications = {
        "Stockholm Arlanda": "Stockholm",
        "Stockholm Bromma": "Stockholm",
        "Göteborg Landvetter": "Göteborg",
        "Goteborg Landvetter": "Göteborg",
        "Malmö Sturup": "Malmö",
        "Malmo Sturup": "Malmö",
        "Åre Östersund": "Östersund",
        "Are Ostersund": "Östersund",
    }
    if name in simplifications:
        return simplifications[name]

    return name or "Unknown"


def lookup_country(city_name: str, city_to_country: Dict[str, str]) -> str:
    """
    Look up the country for a given city name with normalization fallbacks.
    """
    if not city_name or city_name == "Unknown":
        return "Unknown"

    # 1. Exact match
    if city_name in city_to_country:
        return city_to_country[city_name]

    # 2. Case-insensitive exact match
    city_lower = city_name.lower()
    for c, country in city_to_country.items():
        if c.lower() == city_lower:
            return country

    # 3. Normalized without accents (e.g. Umea -> Umeå)
    norm_city = normalize_text(city_name)
    for c, country in city_to_country.items():
        if normalize_text(c) == norm_city:
            return country

    # 4. First word match (e.g. "Paris Charles de Gaulle" -> "Paris")
    first_word = city_name.split()[0] if " " in city_name else ""
    if first_word and first_word in city_to_country:
        return city_to_country[first_word]

    # 5. Check if any known city is a substring of the city name
    for c, country in city_to_country.items():
        if len(c) > 3 and c.lower() in city_lower:
            return country

    return "Unknown"


def extract_city_from_flight(flight: dict, direction: str = "departure") -> str:
    """
    Extract and clean destination or origin city name from raw flight dict.
    For departures: destination city.
    For arrivals: origin city.
    """
    # Handle wrapped items from query
    if "arrival" in flight:
        flight = flight.get("arrival") or {}
        direction = "arrival"
    elif "departure" in flight:
        flight = flight.get("departure") or {}
        direction = "departure"

    leg = flight.get("flightLegIdentifier") or {}

    if direction == "arrival":
        raw_place = (
            flight.get("departureAirportEnglish")
            or flight.get("departureAirportSwedish")
            or leg.get("departureAirportIata")
            or "Unknown"
        )
    else:
        raw_place = (
            flight.get("arrivalAirportEnglish")
            or flight.get("arrivalAirportSwedish")
            or leg.get("arrivalAirportIata")
            or "Unknown"
        )

    return clean_city_name(raw_place)


def analyze_destinations(
    flights: List[dict],
    direction: str = "departure",
    filter_text: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Process flight list, clean city names, map to countries, count frequencies,
    apply optional country or city filter, and sort by flight count descending.
    """
    city_to_country, _ = load_city_country_data()
    valid_flights = filter_valid_flights(flights, direction)

    city_counts: Dict[str, int] = defaultdict(int)
    city_countries: Dict[str, str] = {}

    for fl in valid_flights:
        city = extract_city_from_flight(fl, direction)
        country = lookup_country(city, city_to_country)
        city_counts[city] += 1
        city_countries[city] = country

    # Prepare ranked items
    ranked_entries = []
    filter_norm = filter_text.strip().lower() if filter_text else None

    for city, count in city_counts.items():
        country = city_countries[city]

        # Apply optional filter on city or country name
        if filter_norm:
            if filter_norm not in city.lower() and filter_norm not in country.lower():
                continue

        ranked_entries.append({
            "city": city,
            "country": country,
            "flights": count,
        })

    # Sort descending by flights, then alphabetically by city name
    ranked_entries.sort(key=lambda x: (-x["flights"], x["city"]))

    total_filtered_flights = sum(e["flights"] for e in ranked_entries)
    unique_countries = len(set(e["country"] for e in ranked_entries if e["country"] != "Unknown"))

    return {
        "entries": ranked_entries,
        "total_flights": total_filtered_flights,
        "unique_cities": len(ranked_entries),
        "unique_countries": unique_countries,
        "total_unfiltered_flights": len(valid_flights),
    }


def render_bar(percentage: float, max_width: int = 15) -> str:
    """Render a terminal unicode block bar representing a percentage."""
    if percentage <= 0:
        return ""
    length = int(round((percentage / 100.0) * max_width))
    length = max(1, min(length, max_width))
    return "█" * length


def display_destinations_table(
    analysis: Dict[str, Any],
    airport: str,
    direction: str,
    date_str: str,
    filter_text: Optional[str] = None,
) -> None:
    """
    Format and print the analyzed destinations into a clean, aligned terminal table.
    """
    entries = analysis["entries"]
    total_flights = analysis["total_flights"]
    unique_cities = analysis["unique_cities"]
    unique_countries = analysis["unique_countries"]

    airport_info = AIRPORTS.get(airport, {})
    airport_title = airport_info.get("name", airport)
    mode_label = "Destinations (Departures)" if direction == "departure" else "Origins (Arrivals)"

    print()
    print("=" * 80)
    print(f" {mode_label} for {airport_title} ({airport}) - {date_str}")
    if filter_text:
        print(f" Filter applied: '{filter_text}' (Matches: {unique_cities} cities, {total_flights} flights)")
    print("=" * 80)

    if not entries:
        print("\n  [i] No destinations found matching your criteria.\n")
        print("=" * 80)
        return

    # Table Header
    print(f"{'#':<4} {'City':<24} {'Country':<22} {'Flights':>8}   {'Share':>6}  {'Distribution'}")
    print("-" * 80)

    for i, entry in enumerate(entries, start=1):
        city = entry["city"][:23]
        country = entry["country"][:21]
        count = entry["flights"]
        share = (count / total_flights * 100.0) if total_flights > 0 else 0.0
        bar = render_bar(share, max_width=12)

        print(f"{i:<4} {city:<24} {country:<22} {count:>8}   {share:>5.1f}%  {bar}")

    print("-" * 80)
    summary_text = (
        f" Total: {total_flights} flights across {unique_cities} unique cities"
        f" in {unique_countries} countries."
    )
    if filter_text and analysis["total_unfiltered_flights"] != total_flights:
        summary_text += f" (out of {analysis['total_unfiltered_flights']} total flights)"
    print(summary_text)
    print("=" * 80)
    print()


def run_interactive():
    """Run destination analysis in an interactive loop."""
    client = SwedaviaClient()
    if client.is_demo():
        print("\n  [INFO] Running in Demo Mode (simulated Swedavia flight data).")

    print("\n--- Swedavia Destination & Route Analyzer ---")
    airport = prompt_airport("Select airport (IATA or city name)", default="ARN")

    # Prompt direction
    while True:
        dir_input = input("Flight direction - [D]epartures or [A]rrivals [D]: ").strip().lower()
        if not dir_input or dir_input.startswith("d"):
            direction = "departure"
            break
        elif dir_input.startswith("a"):
            direction = "arrival"
            break
        print("  [!] Please enter 'D' for departures or 'A' for arrivals.")

    # Prompt date
    date_str = prompt_date("Select date (YYYY-MM-DD, today, tomorrow, yesterday)", default="today")

    # Prompt optional filter
    filter_input = input("Optional filter by city or country name (press Enter for all): ").strip()
    filter_text = filter_input if filter_input else None

    print(f"\n  Fetching {direction}s for {airport} on {date_str}...")
    try:
        if direction == "departure":
            raw_flights = client.get_departures(airport, date_str)
        else:
            raw_flights = client.get_arrivals(airport, date_str)

        analysis = analyze_destinations(raw_flights, direction, filter_text)
        display_destinations_table(analysis, airport, direction, date_str, filter_text)
    except Exception as exc:
        print(f"\n  [ERROR] {exc}\n")


def main():
    """Command-line entry point with arguments parsing."""
    parser = argparse.ArgumentParser(
        description="Swedavia Flight Destinations & Origins Analyzer",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-a", "--airport",
        type=str,
        default=None,
        help="Airport IATA code or city name (e.g. ARN, GOT, Visby, Bromma). Default: ARN",
    )
    parser.add_argument(
        "-d", "--direction",
        type=str,
        choices=["departures", "arrivals", "dep", "arr", "D", "A"],
        default=None,
        help="Flight direction: 'departures' or 'arrivals'. Default: departures",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Flight date (YYYY-MM-DD, 'today', 'tomorrow', 'yesterday'). Default: today",
    )
    parser.add_argument(
        "-f", "--filter",
        type=str,
        default=None,
        help="Filter results by city name or country name (e.g. 'Spain', 'London')",
    )
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Launch interactive prompts",
    )

    args = parser.parse_args()

    # If --interactive or no arguments provided, launch interactive prompt
    if args.interactive or (args.airport is None and args.direction is None and args.date is None):
        run_interactive()
        return

    # Non-interactive CLI mode
    client = SwedaviaClient()
    airport_code = resolve_airport(args.airport or "ARN") or "ARN"

    direction_raw = (args.direction or "departures").lower()
    direction = "arrival" if direction_raw in ("arrivals", "arr", "a") else "departure"

    date_str = parse_date_input(args.date or "today") or parse_date_input("today")

    try:
        if direction == "departure":
            raw_flights = client.get_departures(airport_code, date_str)
        else:
            raw_flights = client.get_arrivals(airport_code, date_str)

        analysis = analyze_destinations(raw_flights, direction, args.filter)
        display_destinations_table(analysis, airport_code, direction, date_str, args.filter)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
