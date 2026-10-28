"""
airport.py - Interactive Terminal Application for Swedavia FlightInfo API v2.

Main interactive menu:
  1. Arrivals for an airport & date
  2. Departures for an airport & date
  3. Search a specific flight number
  4. OData query (choose airport, date, type A/D, optional flight number)
  5. HeartBeat - API health check
  6. Demo all endpoints automatically
  q. Quit
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from typing import List

from destinations import analyze_destinations, display_destinations_table
from swedavia_client import (
    AIRPORTS,
    SwedaviaClient,
    format_flight_card,
    is_demo_mode,
    paginate_flights,
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


def print_banner(client: SwedaviaClient) -> None:
    """Print the application header and current operating mode."""
    mode_str = "DEMO MODE (Simulated data - no API key set)" if client.is_demo() else "LIVE API (api.swedavia.se)"
    airport_codes = " ".join(AIRPORTS.keys())

    print()
    print("╔═══════════════════════════════════════════════════════════════════════════╗")
    print("║               SWEDAVIA FLIGHT INFORMATION SYSTEM v2                       ║")
    print(f"║  Mode: {mode_str:<66} ║")
    print(f"║  Airports: {airport_codes:<62} ║")
    print("╚═══════════════════════════════════════════════════════════════════════════╝")


def show_menu() -> None:
    """Display the main menu options."""
    print("Main Menu:")
    print("  1. Arrivals for an airport & date")
    print("  2. Departures for an airport & date")
    print("  3. Search a specific flight number")
    print("  4. OData query (choose airport, date, type A/D, optional flight number)")
    print("  5. HeartBeat - API health check")
    print("  6. Demo all endpoints automatically")
    print("  7. Destination analytics & country ranking")
    print("  q. Quit")
    print()


def handle_arrivals(client: SwedaviaClient) -> None:
    """Fetch and display arrivals for a given airport and date."""
    print("\n--- 1. Arrivals for an Airport & Date ---")
    airport = prompt_airport("Airport (IATA or city, e.g. ARN, Visby)", default="ARN")
    date_str = prompt_date("Date (YYYY-MM-DD, today, tomorrow, yesterday)", default="today")

    print(f"\n  Fetching arrivals for {airport} on {date_str}...")
    try:
        flights = client.get_arrivals(airport, date_str)
        print(f"  Received {len(flights)} flight record(s).\n")
        paginate_flights(flights, direction="arrival", current_airport=airport, page_size=50)
    except Exception as exc:
        print(f"\n  [ERROR] {exc}\n")


def handle_departures(client: SwedaviaClient) -> None:
    """Fetch and display departures for a given airport and date."""
    print("\n--- 2. Departures for an Airport & Date ---")
    airport = prompt_airport("Airport (IATA or city, e.g. ARN, Visby)", default="ARN")
    date_str = prompt_date("Date (YYYY-MM-DD, today, tomorrow, yesterday)", default="today")

    print(f"\n  Fetching departures for {airport} on {date_str}...")
    try:
        flights = client.get_departures(airport, date_str)
        print(f"  Received {len(flights)} flight record(s).\n")
        paginate_flights(flights, direction="departure", current_airport=airport, page_size=50)
    except Exception as exc:
        print(f"\n  [ERROR] {exc}\n")


def handle_search_flight(client: SwedaviaClient) -> None:
    """Search for a specific flight number."""
    print("\n--- 3. Search a Specific Flight Number ---")
    while True:
        flight_id = input("Enter flight number (e.g. SK532, DY4001): ").strip().upper()
        if flight_id:
            break
        print("  [!] Flight number cannot be empty.")

    airport = prompt_airport("Airport to search at", default="ARN")
    date_str = prompt_date("Date (YYYY-MM-DD, today, tomorrow, yesterday)", default="today")

    print(f"\n  Searching for flight {flight_id} at {airport} on {date_str}...")
    try:
        matches = client.search_flight_number(flight_id, airport=airport, date_str=date_str)
        if not matches:
            print(f"  [i] No flights found matching '{flight_id}' for {airport} on {date_str}.\n")
            return

        print(f"  Found {len(matches)} matching flight(s):\n")
        paginate_flights(matches, direction="departure", current_airport=airport, page_size=50)
    except Exception as exc:
        print(f"\n  [ERROR] {exc}\n")


def handle_odata_query(client: SwedaviaClient) -> None:
    """
    Construct and execute an OData filter query:
    e.g. airport eq 'ARN' and scheduled eq '20261026' and flightId eq 'SK532'
    """
    print("\n--- 4. OData Query ---")
    airport = prompt_airport("Choose airport (e.g. ARN)", default="ARN")
    date_str = prompt_date("Choose date (YYYY-MM-DD, today, tomorrow, yesterday)", default="today")
    date_compact = date_str.replace("-", "")

    # Flight type selection
    while True:
        type_input = input("Flight type - [A]rrival, [D]eparture, or [B]oth [B]: ").strip().upper()
        if not type_input or type_input in ("B", "BOTH"):
            chosen_type = "BOTH"
            break
        elif type_input in ("A", "ARRIVAL", "ARRIVALS"):
            chosen_type = "A"
            break
        elif type_input in ("D", "DEPARTURE", "DEPARTURES"):
            chosen_type = "D"
            break
        print("  [!] Please enter 'A', 'D', or 'B'.")

    flight_id_input = input("Optional flight number filter (e.g. SK532, or press Enter for all): ").strip().upper()

    # Build OData filter expression
    filter_parts = [
        f"airport eq '{airport}'",
        f"scheduled eq '{date_compact}'",
    ]
    if flight_id_input:
        filter_parts.append(f"flightId eq '{flight_id_input}'")

    odata_filter = " and ".join(filter_parts)

    print()
    print("=" * 70)
    print(f" Generated OData Filter: {odata_filter}")
    print("=" * 70)
    print("  Executing query...")

    try:
        raw_results, next_token = client.query(odata_filter, count=50)

        # Filter by type if user selected Arrival or Departure only
        filtered_results = []
        for item in raw_results:
            if chosen_type == "A" and "arrival" not in item:
                continue
            if chosen_type == "D" and "departure" not in item:
                continue
            filtered_results.append(item)

        print(f"  Query returned {len(filtered_results)} flight result(s).\n")
        if next_token:
            print(f"  [i] Continuation token available: {next_token[:30]}...")

        paginate_flights(filtered_results, direction="departure", current_airport=airport, page_size=50)
    except Exception as exc:
        print(f"\n  [ERROR] {exc}\n")


def handle_heartbeat(client: SwedaviaClient) -> None:
    """Check API health status."""
    print("\n--- 5. HeartBeat - API Health Check ---")
    print(f"  Pinging {client.base_url}/heartBeat...")
    try:
        hb = client.get_heartbeat()
        status = hb.get("status", "Unknown")
        code = hb.get("statusCode", "N/A")
        latency = hb.get("latencyMs", "N/A")
        is_demo = hb.get("demo", False)

        print()
        print("  ╔════════════════════════════════════════════════════╗")
        print(f"  ║ Status     : {status:<35} ║")
        print(f"  ║ HTTP Code  : {str(code):<35} ║")
        if not is_demo:
            print(f"  ║ Latency    : {f'{latency} ms':<35} ║")
        print(f"  ║ Mode       : {'Demo Mode' if is_demo else 'Live Swedavia API':<35} ║")
        print("  ╚════════════════════════════════════════════════════╝")
        print("  Health check completed successfully.\n")
    except Exception as exc:
        print(f"\n  [ERROR] HeartBeat failed: {exc}\n")


def handle_demo_all(client: SwedaviaClient) -> None:
    """
    Run an automated demonstration of all endpoints in sequence:
    1. Heartbeat
    2. Arrivals
    3. Departures
    4. Search flight SK532
    5. OData query
    6. Destinations analysis
    """
    print("\n" + "=" * 75)
    print("           AUTOMATED DEMONSTRATION OF ALL API ENDPOINTS")
    print("=" * 75)

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_compact = today_str.replace("-", "")

    # 1. Heartbeat
    print("\n[Step 1/6] Testing GET /heartBeat (Health Check)...")
    try:
        hb = client.get_heartbeat()
        print(f"  -> Result: Status = {hb.get('status')}, HTTP Code = {hb.get('statusCode')}")
    except Exception as e:
        print(f"  -> Error: {e}")

    # 2. Arrivals
    print(f"\n[Step 2/6] Testing GET /ARN/arrivals/{today_str}...")
    try:
        arrs = client.get_arrivals("ARN", today_str)
        print(f"  -> Fetched {len(arrs)} arrival flights.")
        if arrs:
            print("  -> Sample Arrival Flight Card:")
            print(format_flight_card(arrs[0], 1, direction="arrival", current_airport="ARN"))
    except Exception as e:
        print(f"  -> Error: {e}")

    # 3. Departures
    print(f"\n[Step 3/6] Testing GET /ARN/departures/{today_str}...")
    try:
        deps = client.get_departures("ARN", today_str)
        print(f"  -> Fetched {len(deps)} departure flights.")
        if deps:
            print("  -> Sample Departure Flight Card:")
            print(format_flight_card(deps[0], 1, direction="departure", current_airport="ARN"))
    except Exception as e:
        print(f"  -> Error: {e}")

    # 4. Search Flight Number
    print(f"\n[Step 4/6] Searching for specific flight 'SK532'...")
    try:
        results = client.search_flight_number("SK532", airport="ARN", date_str=today_str)
        print(f"  -> Found {len(results)} match(es).")
        for i, match in enumerate(results, start=1):
            print(format_flight_card(match, i, direction="arrival", current_airport="ARN"))
    except Exception as e:
        print(f"  -> Error: {e}")

    # 5. OData Query
    test_filter = f"airport eq 'ARN' and scheduled eq '{today_compact}' and flightId eq 'SK532'"
    print(f"\n[Step 5/6] Testing GET /query?filter={test_filter}...")
    try:
        q_results, token = client.query(test_filter)
        print(f"  -> Query returned {len(q_results)} flight(s). Continuation token: {token}")
        if q_results:
            print(format_flight_card(q_results[0], 1, direction="departure", current_airport="ARN"))
    except Exception as e:
        print(f"  -> Error: {e}")

    # 6. Destinations Analysis
    print(f"\n[Step 6/6] Analyzing unique destinations from ARN departures...")
    try:
        deps = client.get_departures("ARN", today_str)
        analysis = analyze_destinations(deps, direction="departure")
        display_destinations_table(analysis, "ARN", "departure", today_str)
    except Exception as e:
        print(f"  -> Error: {e}")

    print("=" * 75)
    print("           AUTOMATED DEMONSTRATION COMPLETE")
    print("=" * 75 + "\n")


def handle_destinations(client: SwedaviaClient) -> None:
    """Interactive destination analysis from airport.py."""
    print("\n--- 7. Destination Analytics & Country Ranking ---")
    airport = prompt_airport("Airport (IATA or city, e.g. ARN, Visby)", default="ARN")
    while True:
        dir_input = input("Flight direction - [D]epartures or [A]rrivals [D]: ").strip().lower()
        if not dir_input or dir_input.startswith("d"):
            direction = "departure"
            break
        elif dir_input.startswith("a"):
            direction = "arrival"
            break
        print("  [!] Please enter 'D' or 'A'.")

    date_str = prompt_date("Date (YYYY-MM-DD, today, tomorrow, yesterday)", default="today")
    filter_input = input("Optional filter by city or country name (Enter for all): ").strip()
    filter_text = filter_input if filter_input else None

    print(f"\n  Fetching {direction}s for {airport} on {date_str}...")
    try:
        if direction == "departure":
            flights = client.get_departures(airport, date_str)
        else:
            flights = client.get_arrivals(airport, date_str)

        analysis = analyze_destinations(flights, direction, filter_text)
        display_destinations_table(analysis, airport, direction, date_str, filter_text)
    except Exception as exc:
        print(f"\n  [ERROR] {exc}\n")


def main() -> None:
    """Main application loop."""
    client = SwedaviaClient()

    if client.is_demo():
        print()
        print("  [!] NOTICE: SWEDAVIA_API_KEY environment variable is not configured.")
        print("      Running in DEMO MODE with realistic simulated flight data.")
        print("      To use real live data, copy .env.example to .env and insert your API key.")
        print("      Get a free key at: https://apideveloper.swedavia.se/")

    while True:
        try:
            print_banner(client)
            show_menu()
            choice = input("Enter choice (1-7, q to quit): ").strip().lower()

            if choice == "1":
                handle_arrivals(client)
            elif choice == "2":
                handle_departures(client)
            elif choice == "3":
                handle_search_flight(client)
            elif choice == "4":
                handle_odata_query(client)
            elif choice == "5":
                handle_heartbeat(client)
            elif choice == "6":
                handle_demo_all(client)
            elif choice == "7":
                handle_destinations(client)
            elif choice in ("q", "quit", "exit"):
                print("\n  Thank you for using the Swedavia Flight Information System. Goodbye!\n")
                sys.exit(0)
            else:
                print(f"\n  [!] Invalid selection '{choice}'. Please enter a number 1-7 or 'q'.\n")

            input("Press [Enter] to return to the main menu...")
        except KeyboardInterrupt:
            print("\n\n  Operation cancelled by user. Returning to menu...\n")
            time.sleep(0.5)
        except Exception as e:
            print(f"\n  [UNEXPECTED ERROR] {e}\n")
            input("Press [Enter] to continue...")


if __name__ == "__main__":
    main()
