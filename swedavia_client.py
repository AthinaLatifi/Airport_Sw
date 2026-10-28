"""
swedavia_client.py - Shared API client and utility library for Swedavia FlightInfo v2.

Features:
- Configuration management and secure key loading from .env via python-dotenv.
- HTTP client using `requests` with robust error handling (401, 404, 429, timeouts, network issues).
- Full endpoint support:
    1. GET /{airport}/arrivals/{YYYY-MM-DD}
    2. GET /{airport}/departures/{YYYY-MM-DD}
    3. GET /query?filter=... (OData query with continuation token support)
    4. GET /heartBeat (health check)
- Timezone conversions using standard library `zoneinfo` (Europe/Stockholm: CET/CEST).
- Paging output formatter (50 flights per page) with ghost flight filtering.
- Demo mode fallback with realistic simulated flights when no API key is configured.
"""

from __future__ import annotations

import os
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Ensure UTF-8 encoding on Windows consoles
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Base URL for Swedavia FlightInfo API v2
BASE_URL = "https://api.swedavia.se/flightinfo/v2"

# Stockholm timezone for local time conversions (CET / CEST)
STOCKHOLM_TZ = ZoneInfo("Europe/Stockholm")

# Swedavia 10 Swedish State-Owned Airports (IATA code -> details)
AIRPORTS: Dict[str, Dict[str, str]] = {
    "ARN": {
        "iata": "ARN",
        "city": "Stockholm",
        "name": "Stockholm Arlanda Airport",
        "swedish_name": "Stockholm Arlanda",
    },
    "GOT": {
        "iata": "GOT",
        "city": "Göteborg",
        "name": "Göteborg Landvetter Airport",
        "swedish_name": "Göteborg Landvetter",
    },
    "BMA": {
        "iata": "BMA",
        "city": "Stockholm",
        "name": "Stockholm Bromma Airport",
        "swedish_name": "Stockholm Bromma",
    },
    "MMX": {
        "iata": "MMX",
        "city": "Malmö",
        "name": "Malmö Airport",
        "swedish_name": "Malmö Airport",
    },
    "LLA": {
        "iata": "LLA",
        "city": "Luleå",
        "name": "Luleå Airport",
        "swedish_name": "Luleå Airport",
    },
    "UME": {
        "iata": "UME",
        "city": "Umeå",
        "name": "Umeå Airport",
        "swedish_name": "Umeå Airport",
    },
    "OSD": {
        "iata": "OSD",
        "city": "Östersund",
        "name": "Åre Östersund Airport",
        "swedish_name": "Åre Östersund",
    },
    "VBY": {
        "iata": "VBY",
        "city": "Visby",
        "name": "Visby Airport",
        "swedish_name": "Visby Airport",
    },
    "RNB": {
        "iata": "RNB",
        "city": "Ronneby",
        "name": "Ronneby Airport",
        "swedish_name": "Ronneby Airport",
    },
    "KRN": {
        "iata": "KRN",
        "city": "Kiruna",
        "name": "Kiruna Airport",
        "swedish_name": "Kiruna Airport",
    },
}

# Swedish status to English translation fallback
STATUS_SV_TO_EN = {
    "Enligt tidtabell": "Scheduled",
    "Landat": "Landed",
    "Avgått": "Departed",
    "Försenad": "Delayed",
    "Inställd": "Cancelled",
    "Boarding": "Boarding",
    "Gate stängd": "Gate closed",
    "Gå till gate": "Go to gate",
    "Ny tid": "New time",
    "Bagage ankommer": "Baggage arriving",
    "SCH": "Scheduled",
    "ACT": "Active",
    "DEL": "Delayed",
    "CAN": "Cancelled",
    "DIV": "Diverted",
    "ARR": "Arrived",
    "DEP": "Departed",
}


def normalize_text(text: str) -> str:
    """Normalize text: strip, lowercase, and decompose accented characters."""
    if not text:
        return ""
    text = text.strip().lower()
    # Replace special swedish characters smoothly
    replacements = {
        "ä": "a",
        "å": "a",
        "ö": "o",
        "é": "e",
        "ü": "u",
    }
    for char, rep in replacements.items():
        text = text.replace(char, rep)
    # Generic unicode normalization
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def get_api_key() -> str:
    """
    Retrieve the Swedavia API subscription key from environment.
    Never hardcode the key.
    """
    return os.getenv("SWEDAVIA_API_KEY", "").strip()


def is_demo_mode() -> bool:
    """
    Check if the application is running in Demo Mode.
    Activated when no API key is set, or if key contains a placeholder value.
    """
    key = get_api_key()
    placeholders = {
        "",
        "your_api_key_here",
        "your_subscription_key_here",
        "your_key_here",
        "key",
        "dummy",
    }
    return key.lower() in placeholders


def resolve_airport(input_str: str) -> Optional[str]:
    """
    Resolve an airport input to an uppercase 3-letter IATA code.
    Supports IATA codes (e.g. 'ARN') or city/airport names (e.g. 'visby', 'goteborg', 'arlanda').
    """
    if not input_str:
        return None

    raw_clean = input_str.strip().upper()
    if raw_clean in AIRPORTS:
        return raw_clean

    norm = normalize_text(input_str)

    # City/Airport alias mappings
    aliases = {
        "arlanda": "ARN",
        "stockholm arlanda": "ARN",
        "stockholm": "ARN",
        "landvetter": "GOT",
        "goteborg": "GOT",
        "gothenburg": "GOT",
        "goteborg landvetter": "GOT",
        "bromma": "BMA",
        "stockholm bromma": "BMA",
        "malmo": "MMX",
        "sturup": "MMX",
        "malmo sturup": "MMX",
        "lulea": "LLA",
        "kallax": "LLA",
        "umea": "UME",
        "ostersund": "OSD",
        "are": "OSD",
        "are ostersund": "OSD",
        "froson": "OSD",
        "visby": "VBY",
        "gotland": "VBY",
        "ronneby": "RNB",
        "kallinge": "RNB",
        "blekinge": "RNB",
        "kiruna": "KRN",
    }

    if norm in aliases:
        return aliases[norm]

    # Partial substring check
    for alias_key, iata in aliases.items():
        if alias_key in norm or norm in alias_key:
            return iata

    return None


def prompt_airport(prompt_label: str = "Airport (IATA or city, e.g. ARN, Visby)", default: str = "ARN") -> str:
    """
    Interactively prompt user for an airport and loop until valid.
    """
    while True:
        user_input = input(f"{prompt_label} [{default}]: ").strip()
        if not user_input:
            return default
        resolved = resolve_airport(user_input)
        if resolved:
            return resolved
        print(f"  [!] Unknown airport '{user_input}'. Valid codes: {', '.join(AIRPORTS.keys())}")
        print("      Or type a city name (e.g., Visby, Göteborg, Kiruna, Arlanda).")


def parse_date_input(input_str: str) -> Optional[str]:
    """
    Parse a date string: accepts 'YYYY-MM-DD', 'today', 'tomorrow', 'yesterday'.
    Returns standardized 'YYYY-MM-DD' or None if invalid.
    """
    if not input_str:
        return None

    clean = input_str.strip().lower()
    now_utc = datetime.now(timezone.utc)

    if clean in ("today", "t"):
        return now_utc.strftime("%Y-%m-%d")
    elif clean in ("tomorrow", "tom"):
        return (now_utc + timedelta(days=1)).strftime("%Y-%m-%d")
    elif clean in ("yesterday", "yest"):
        return (now_utc - timedelta(days=1)).strftime("%Y-%m-%d")

    # Check YYYY-MM-DD format
    try:
        dt = datetime.strptime(clean, "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        pass

    # Support YYYYMMDD format as convenience
    if len(clean) == 8 and clean.isdigit():
        try:
            dt = datetime.strptime(clean, "%Y%m%d")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    return None


def prompt_date(prompt_label: str = "Date (YYYY-MM-DD, today, tomorrow, yesterday)", default: str = "today") -> str:
    """
    Interactively prompt user for a date and loop until valid.
    """
    while True:
        user_input = input(f"{prompt_label} [{default}]: ").strip()
        if not user_input:
            user_input = default
        parsed = parse_date_input(user_input)
        if parsed:
            return parsed
        print(f"  [!] Invalid date format '{user_input}'. Please use YYYY-MM-DD, 'today', 'tomorrow', or 'yesterday'.")


def format_time_stockholm(iso_utc_str: Optional[str]) -> str:
    """
    Convert an ISO UTC timestamp (e.g. '2026-10-26T16:25:00Z') to:
    '16:25 UTC → 17:25 CET' (or CEST in summer) using zoneinfo Europe/Stockholm.
    Returns '–' if string is empty or invalid.
    """
    if not iso_utc_str:
        return "–"

    iso_clean = iso_utc_str.strip()
    if not iso_clean:
        return "–"

    try:
        # Handle trailing Z or timezone offsets
        if iso_clean.endswith("Z"):
            iso_clean = iso_clean[:-1] + "+00:00"
        dt_utc = datetime.fromisoformat(iso_clean)
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)

        # Convert to Stockholm time
        dt_sthlm = dt_utc.astimezone(STOCKHOLM_TZ)
        tz_name = dt_sthlm.tzname() or "CET"

        utc_hm = dt_utc.strftime("%H:%M")
        sthlm_hm = dt_sthlm.strftime("%H:%M")

        return f"{utc_hm} UTC → {sthlm_hm} {tz_name}"
    except Exception:
        # Fallback if unparseable
        return iso_utc_str


def is_ghost_flight(flight_raw: dict, direction: str = "departure") -> bool:
    """
    Skip empty 'ghost' flights with no flightId, place or scheduled time.
    """
    if not isinstance(flight_raw, dict):
        return True

    # Handle wrapped items from /query
    if "arrival" in flight_raw:
        flight_raw = flight_raw.get("arrival") or {}
        direction = "arrival"
    elif "departure" in flight_raw:
        flight_raw = flight_raw.get("departure") or {}
        direction = "departure"

    flight_id = flight_raw.get("flightId")
    if not flight_id or not str(flight_id).strip():
        return True

    leg = flight_raw.get("flightLegIdentifier") or {}
    if direction == "arrival":
        place = (
            flight_raw.get("departureAirportEnglish")
            or flight_raw.get("departureAirportSwedish")
            or leg.get("departureAirportIata")
        )
        time_info = flight_raw.get("arrivalTime") or {}
    else:
        place = (
            flight_raw.get("arrivalAirportEnglish")
            or flight_raw.get("arrivalAirportSwedish")
            or leg.get("arrivalAirportIata")
        )
        time_info = flight_raw.get("departureTime") or {}

    sched = time_info.get("scheduledUtc")

    # If it has neither a destination/origin place nor a scheduled time, skip it
    if not place and not sched:
        return True

    return False


def filter_valid_flights(flights: List[dict], direction: str = "departure") -> List[dict]:
    """Filter out empty ghost flights from a flight list."""
    return [f for f in flights if not is_ghost_flight(f, direction)]


def format_flight_card(
    flight: dict,
    index: int,
    direction: str = "departure",
    current_airport: str = "ARN",
) -> str:
    """
    Format a single flight in the exact required layout:
      [1] SK532 | SAS Scandinavian Airlines (SK)
         From     : London LHR
         To       : (ARN)
         Status   : Scheduled
         Terminal : T5   Gate: N/A
         Baggage  : 3
         Sched    : 16:25 UTC → 17:25 CET
         Est      : –
         Actual   : –
         D/I      : I
    """
    # Check if wrapped from query
    if "arrival" in flight:
        flight = flight.get("arrival") or {}
        direction = "arrival"
    elif "departure" in flight:
        flight = flight.get("departure") or {}
        direction = "departure"

    # Flight ID
    flight_id = flight.get("flightId") or "N/A"

    # Airline operator
    airline_obj = flight.get("airlineOperator") or {}
    airline_name = airline_obj.get("name")
    airline_iata = airline_obj.get("iata")
    if airline_name and airline_iata:
        airline_str = f"{airline_name} ({airline_iata})"
    elif airline_name:
        airline_str = airline_name
    elif airline_iata:
        airline_str = airline_iata
    else:
        airline_str = "N/A"

    # Airport identifiers
    leg = flight.get("flightLegIdentifier") or {}

    if direction == "arrival":
        dep_place = (
            flight.get("departureAirportEnglish")
            or flight.get("departureAirportSwedish")
            or leg.get("departureAirportIata")
            or "N/A"
        )
        arr_place = f"({current_airport})"
        from_str = dep_place
        to_str = arr_place
        time_dict = flight.get("arrivalTime") or {}
    else:
        dep_place = f"({current_airport})"
        arr_place = (
            flight.get("arrivalAirportEnglish")
            or flight.get("arrivalAirportSwedish")
            or leg.get("arrivalAirportIata")
            or "N/A"
        )
        from_str = dep_place
        to_str = arr_place
        time_dict = flight.get("departureTime") or {}

    # Status
    loc = flight.get("locationAndStatus") or {}
    status_en = loc.get("flightLegStatusEnglish")
    status_sv = loc.get("flightLegStatusSwedish")
    status_code = loc.get("flightLegStatus")

    if status_en:
        status_str = status_en
    elif status_sv and status_sv in STATUS_SV_TO_EN:
        status_str = STATUS_SV_TO_EN[status_sv]
    elif status_sv:
        status_str = status_sv
    elif status_code and status_code in STATUS_SV_TO_EN:
        status_str = STATUS_SV_TO_EN[status_code]
    elif status_code:
        status_str = status_code
    else:
        status_str = "Scheduled"

    # Terminal & Gate
    terminal = loc.get("terminal") or "N/A"
    gate = loc.get("gate") or "N/A"

    # Baggage
    if direction == "arrival":
        baggage_obj = flight.get("baggage") or {}
        baggage = baggage_obj.get("baggageClaimUnit") or "N/A"
    else:
        baggage = "N/A"

    # Times
    sched_utc = time_dict.get("scheduledUtc")
    est_utc = time_dict.get("estimatedUtc")
    act_utc = time_dict.get("actualUtc")

    sched_str = format_time_stockholm(sched_utc)
    est_str = format_time_stockholm(est_utc)
    act_str = format_time_stockholm(act_utc)

    # Domestic / International indicator
    di_indicator = flight.get("diIndicator") or "N/A"

    card = (
        f"[{index}] {flight_id} | {airline_str}\n"
        f"   From     : {from_str}\n"
        f"   To       : {to_str}\n"
        f"   Status   : {status_str}\n"
        f"   Terminal : {terminal:<4} Gate: {gate}\n"
        f"   Baggage  : {baggage}\n"
        f"   Sched    : {sched_str}\n"
        f"   Est      : {est_str}\n"
        f"   Actual   : {act_str}\n"
        f"   D/I      : {di_indicator}"
    )
    return card


def paginate_flights(
    flights: List[dict],
    direction: str = "departure",
    current_airport: str = "ARN",
    page_size: int = 50,
) -> None:
    """
    Display flights in batches of 50:
    "── Showing 50/217 ── (167 left)"
    then "[Enter] next page | [a] show all | [q] back to menu"
    """
    valid_flights = filter_valid_flights(flights, direction)
    total_count = len(valid_flights)

    if total_count == 0:
        print("\n  [i] No flights found matching the criteria.\n")
        return

    current_idx = 0
    show_all = False

    while current_idx < total_count:
        end_idx = min(current_idx + page_size, total_count) if not show_all else total_count
        chunk = valid_flights[current_idx:end_idx]

        for i, fl in enumerate(chunk, start=current_idx + 1):
            print(format_flight_card(fl, i, direction, current_airport))

        current_idx = end_idx
        left_count = total_count - current_idx

        if current_idx < total_count and not show_all:
            banner = f"── Showing {current_idx}/{total_count} ── ({left_count} left)"
            print(f"\n{banner}")
            prompt = "[Enter] next page | [a] show all | [q] back to menu: "
            choice = input(prompt).strip().lower()
            print()
            if choice == "q":
                print("  Returning to menu...")
                break
            elif choice == "a":
                show_all = True
            # [Enter] simply loops to display the next 50
        else:
            print(f"\n── Finished displaying all {total_count} flight(s) ──\n")
            break


# ==============================================================================
# DEMO MODE REALISTIC DATA GENERATOR
# ==============================================================================

def generate_demo_flights(
    airport: str,
    direction: str,
    date_str: str,
    target_flight_id: Optional[str] = None,
) -> List[dict]:
    """
    Generate realistic simulated flights matching Swedavia v2 schema.
    Used when running without an API key.
    """
    demo_destinations = [
        ("LHR", "London LHR", "I", "T5"),
        ("CPH", "Copenhagen CPH", "I", "T5"),
        ("OSL", "Oslo OSL", "I", "T5"),
        ("HEL", "Helsinki HEL", "I", "T5"),
        ("FRA", "Frankfurt FRA", "I", "T5"),
        ("AMS", "Amsterdam AMS", "I", "T5"),
        ("CDG", "Paris CDG", "I", "T5"),
        ("MUC", "Munich MUC", "I", "T5"),
        ("BER", "Berlin BER", "I", "T5"),
        ("FCO", "Rome FCO", "I", "T5"),
        ("BCN", "Barcelona BCN", "I", "T5"),
        ("MAD", "Madrid MAD", "I", "T5"),
        ("ZRH", "Zurich ZRH", "I", "T5"),
        ("VIE", "Vienna VIE", "I", "T5"),
        ("BRU", "Brussels BRU", "I", "T5"),
        ("DOH", "Doha DOH", "I", "T5"),
        ("DXB", "Dubai DXB", "I", "T5"),
        ("VBY", "Visby VBY", "D", "T4"),
        ("LLA", "Luleå LLA", "D", "T4"),
        ("UME", "Umeå UME", "D", "T4"),
        ("KRN", "Kiruna KRN", "D", "T4"),
        ("GOT", "Göteborg GOT", "D", "T4"),
        ("MMX", "Malmö MMX", "D", "T4"),
        ("OSD", "Östersund OSD", "D", "T4"),
        ("RNB", "Ronneby RNB", "D", "T4"),
    ]

    airline_profiles = [
        ("SK", "SAS", "SAS Scandinavian Airlines"),
        ("LH", "DLH", "Lufthansa"),
        ("BA", "BAW", "British Airways"),
        ("KL", "KLM", "KLM Royal Dutch Airlines"),
        ("AF", "AFR", "Air France"),
        ("AY", "FIN", "Finnair"),
        ("DY", "NOZ", "Norwegian Air Shuttle"),
        ("FR", "RYR", "Ryanair"),
        ("LX", "SWR", "Swiss International Air Lines"),
    ]

    flights: List[dict] = []

    # Ensure SK532 is explicitly present with prompt attributes
    sk532_rec = {
        "flightId": "SK532",
        "departureAirportEnglish": "London LHR" if direction == "arrival" else "Stockholm Arlanda",
        "arrivalAirportEnglish": "Stockholm Arlanda" if direction == "arrival" else "London LHR",
        "airlineOperator": {
            "iata": "SK",
            "icao": "SAS",
            "name": "SAS Scandinavian Airlines",
        },
        "arrivalTime" if direction == "arrival" else "departureTime": {
            "scheduledUtc": f"{date_str}T16:25:00Z",
            "estimatedUtc": None,
            "actualUtc": None,
        },
        "locationAndStatus": {
            "terminal": "T5",
            "gate": None,
            "flightLegStatusEnglish": "Scheduled",
            "flightLegStatus": "SCH",
        },
        "baggage": {
            "baggageClaimUnit": "3",
        },
        "flightLegIdentifier": {
            "flightId": "SK532",
            "departureAirportIata": "LHR" if direction == "arrival" else airport,
            "arrivalAirportIata": airport if direction == "arrival" else "LHR",
        },
        "diIndicator": "I",
    }

    if target_flight_id and target_flight_id.upper() == "SK532":
        return [sk532_rec]

    flights.append(sk532_rec)

    # Generate 65 total flights so the 50-flight paging is exercised
    base_hours = [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22]
    flight_counter = 100

    for i in range(64):
        dest_code, dest_name, di, term = demo_destinations[i % len(demo_destinations)]
        al_iata, al_icao, al_name = airline_profiles[i % len(airline_profiles)]

        flight_counter += 7
        fid = f"{al_iata}{flight_counter}"

        hour = base_hours[i % len(base_hours)]
        minute = (i * 13) % 60
        sched_iso = f"{date_str}T{hour:02d}:{minute:02d}:00Z"

        # Realistic status variety
        if hour < 11:
            status = "Landed" if direction == "arrival" else "Departed"
            act_iso = f"{date_str}T{hour:02d}:{(minute + 4) % 60:02d}:00Z"
            est_iso = None
        elif hour < 14:
            status = "Delayed"
            est_iso = f"{date_str}T{hour:02d}:{(minute + 25) % 60:02d}:00Z"
            act_iso = None
        else:
            status = "Scheduled"
            est_iso = None
            act_iso = None

        gate_num = f"{(i % 28) + 1}" if hour < 20 else None
        baggage_belt = str((i % 7) + 1)

        f_data = {
            "flightId": fid,
            "departureAirportEnglish": dest_name if direction == "arrival" else AIRPORTS.get(airport, {}).get("name", airport),
            "arrivalAirportEnglish": AIRPORTS.get(airport, {}).get("name", airport) if direction == "arrival" else dest_name,
            "airlineOperator": {
                "iata": al_iata,
                "icao": al_icao,
                "name": al_name,
            },
            "arrivalTime" if direction == "arrival" else "departureTime": {
                "scheduledUtc": sched_iso,
                "estimatedUtc": est_iso,
                "actualUtc": act_iso,
            },
            "locationAndStatus": {
                "terminal": term,
                "gate": gate_num,
                "flightLegStatusEnglish": status,
                "flightLegStatus": "SCH" if status == "Scheduled" else ("DEL" if status == "Delayed" else "ACT"),
            },
            "baggage": {
                "baggageClaimUnit": baggage_belt,
            },
            "flightLegIdentifier": {
                "flightId": fid,
                "departureAirportIata": dest_code if direction == "arrival" else airport,
                "arrivalAirportIata": airport if direction == "arrival" else dest_code,
            },
            "diIndicator": di,
        }

        if target_flight_id and target_flight_id.upper() != fid.upper():
            continue

        flights.append(f_data)

    # Sort flights chronologically by scheduled time
    time_key = "arrivalTime" if direction == "arrival" else "departureTime"
    flights.sort(key=lambda x: (x.get(time_key) or {}).get("scheduledUtc") or "")
    return flights


# ==============================================================================
# API CLIENT CLASS
# ==============================================================================

class SwedaviaClient:
    """
    Client for Swedavia FlightInfo API v2.
    Handles authentication, error handling, requests, and demo fallback.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key if api_key is not None else get_api_key()
        self.base_url = BASE_URL.rstrip("/")
        self.session = requests.Session()

    def is_demo(self) -> bool:
        """Return True if no valid key is provided."""
        return is_demo_mode() or not self.api_key

    def _headers(self) -> Dict[str, str]:
        """Construct required headers for Swedavia FlightInfo API."""
        return {
            "Ocp-Apim-Subscription-Key": self.api_key,
            "Accept": "application/json",
            "User-Agent": "SwedaviaTerminalApp/2.0",
        }

    def _handle_response_errors(self, response: requests.Response) -> None:
        """
        Check HTTP status codes and raise descriptive, user-friendly exceptions.
        Handles 401, 404, 429, 500, etc.
        """
        status = response.status_code
        if status == 200:
            return

        if status == 401:
            raise PermissionError(
                "401 Unauthorized: Invalid or missing API subscription key.\n"
                "Please verify that 'SWEDAVIA_API_KEY' is correctly set in your .env file.\n"
                "Obtain a key at: https://apideveloper.swedavia.se/"
            )
        elif status == 404:
            raise FileNotFoundError(
                f"404 Not Found: The requested endpoint was not found ({response.url}).\n"
                "Please check the airport code and date format."
            )
        elif status == 429:
            raise ConnectionRefusedError(
                "429 Too Many Requests: Rate limit exceeded on the Swedavia FlightInfo API.\n"
                "The free subscription tier permits up to 10,000 requests per month.\n"
                "Please wait before sending more requests."
            )
        elif status >= 500:
            raise RuntimeError(
                f"{status} Server Error: Swedavia FlightInfo service is temporarily unavailable.\n"
                f"Response: {response.text[:200]}"
            )
        else:
            response.raise_for_status()

    def get_heartbeat(self) -> Dict[str, Any]:
        """
        Health check endpoint: GET /heartBeat.
        Returns API health status and response metadata.
        """
        if self.is_demo():
            return {
                "status": "Healthy (Demo Mode)",
                "statusCode": 200,
                "message": "Swedavia FlightInfo API v2 heartbeat simulated successfully.",
                "demo": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        url = f"{self.base_url}/heartBeat"
        try:
            resp = self.session.get(url, headers=self._headers(), timeout=10)
            self._handle_response_errors(resp)
            data = resp.json() if resp.text else {}
            return {
                "status": "Healthy",
                "statusCode": resp.status_code,
                "latencyMs": int(resp.elapsed.total_seconds() * 1000),
                "data": data,
                "demo": False,
            }
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Network error during heartBeat check: {e}") from e

    def get_arrivals(self, airport: str, date_str: str) -> List[dict]:
        """
        Fetch arrivals for an airport and date: GET /{airport}/arrivals/{YYYY-MM-DD}.
        """
        airport = airport.upper()
        if self.is_demo():
            return generate_demo_flights(airport, "arrival", date_str)

        url = f"{self.base_url}/{airport}/arrivals/{date_str}"
        try:
            resp = self.session.get(url, headers=self._headers(), timeout=15)
            self._handle_response_errors(resp)
            data = resp.json()
            return data.get("flights") or []
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Network error fetching arrivals: {e}") from e

    def get_departures(self, airport: str, date_str: str) -> List[dict]:
        """
        Fetch departures for an airport and date: GET /{airport}/departures/{YYYY-MM-DD}.
        """
        airport = airport.upper()
        if self.is_demo():
            return generate_demo_flights(airport, "departure", date_str)

        url = f"{self.base_url}/{airport}/departures/{date_str}"
        try:
            resp = self.session.get(url, headers=self._headers(), timeout=15)
            self._handle_response_errors(resp)
            data = resp.json()
            return data.get("flights") or []
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Network error fetching departures: {e}") from e

    def query(
        self,
        odata_filter: str,
        continuation_token: Optional[str] = None,
        count: int = 50,
    ) -> Tuple[List[dict], Optional[str]]:
        """
        Execute an OData query: GET /query?filter=...
        Supports continuation tokens for pagination.
        Returns (flights_list, next_continuation_token).
        """
        if self.is_demo():
            # Parse filter to generate appropriate mock data
            date_match = re.search(r"scheduled eq '(\d{8})'", odata_filter)
            if date_match:
                d_str = date_match.group(1)
                parsed_date = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:]}"
            else:
                parsed_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            airport_match = re.search(r"airport eq '([A-Z]{3})'", odata_filter)
            target_airport = airport_match.group(1) if airport_match else "ARN"

            flight_match = re.search(r"flightId eq '([^']+)'", odata_filter)
            target_flight = flight_match.group(1) if flight_match else None

            # Generate departures and arrivals wrapped in {"departure": ...} / {"arrival": ...}
            deps = generate_demo_flights(target_airport, "departure", parsed_date, target_flight)
            arrs = generate_demo_flights(target_airport, "arrival", parsed_date, target_flight)

            wrapped: List[dict] = []
            for d in deps:
                wrapped.append({"departure": d})
            for a in arrs:
                wrapped.append({"arrival": a})

            if target_flight:
                wrapped = [
                    w for w in wrapped
                    if (w.get("departure") or w.get("arrival") or {}).get("flightId", "").upper() == target_flight.upper()
                ]

            return wrapped, None

        url = f"{self.base_url}/query"
        params: Dict[str, Any] = {"filter": odata_filter}
        if continuation_token:
            params["continuationtoken"] = continuation_token
        if count:
            params["count"] = count

        try:
            resp = self.session.get(url, headers=self._headers(), params=params, timeout=15)
            self._handle_response_errors(resp)
            data = resp.json()
            flights = data.get("flights") or []
            next_token = data.get("continuationtoken") or None
            return flights, next_token
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Network error querying flights: {e}") from e

    def search_flight_number(
        self,
        flight_id: str,
        airport: str = "ARN",
        date_str: Optional[str] = None,
    ) -> List[dict]:
        """
        Search for a specific flight number across arrivals and departures.
        Uses /query when possible, or queries arrivals and departures directly.
        """
        flight_id = flight_id.strip().upper()
        if not date_str:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Convert date to YYYYMMDD for OData filter
        clean_date_digits = date_str.replace("-", "")

        odata_filter = f"airport eq '{airport}' and scheduled eq '{clean_date_digits}' and flightId eq '{flight_id}'"
        try:
            results, _ = self.query(odata_filter)
            if results:
                return results
        except Exception:
            # Fall back to fetching departures & arrivals directly
            pass

        # Direct search fallback
        matches = []
        try:
            deps = self.get_departures(airport, date_str)
            for d in deps:
                if (d.get("flightId") or "").upper() == flight_id:
                    matches.append({"departure": d})
        except Exception:
            pass

        try:
            arrs = self.get_arrivals(airport, date_str)
            for a in arrs:
                if (a.get("flightId") or "").upper() == flight_id:
                    matches.append({"arrival": a})
        except Exception:
            pass

        return matches
