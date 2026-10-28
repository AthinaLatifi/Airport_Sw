"""
test_swedavia.py - Unit tests for Swedavia FlightInfo v2 terminal application.
"""

import io
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from destinations import (
    analyze_destinations,
    clean_city_name,
    extract_city_from_flight,
    load_city_country_data,
    lookup_country,
)
from swedavia_client import (
    AIRPORTS,
    SwedaviaClient,
    filter_valid_flights,
    format_flight_card,
    format_time_stockholm,
    is_demo_mode,
    is_ghost_flight,
    normalize_text,
    paginate_flights,
    parse_date_input,
    resolve_airport,
)


class TestAirportResolution(unittest.TestCase):
    """Test resolution of airport IATA codes and Swedish/English city names."""

    def test_iata_direct(self):
        for code in ["ARN", "GOT", "BMA", "MMX", "LLA", "UME", "OSD", "VBY", "RNB", "KRN"]:
            self.assertEqual(resolve_airport(code), code)
            self.assertEqual(resolve_airport(code.lower()), code)

    def test_city_names(self):
        self.assertEqual(resolve_airport("visby"), "VBY")
        self.assertEqual(resolve_airport("goteborg"), "GOT")
        self.assertEqual(resolve_airport("Göteborg"), "GOT")
        self.assertEqual(resolve_airport("gothenburg"), "GOT")
        self.assertEqual(resolve_airport("stockholm"), "ARN")
        self.assertEqual(resolve_airport("arlanda"), "ARN")
        self.assertEqual(resolve_airport("bromma"), "BMA")
        self.assertEqual(resolve_airport("malmo"), "MMX")
        self.assertEqual(resolve_airport("Malmö"), "MMX")
        self.assertEqual(resolve_airport("lulea"), "LLA")
        self.assertEqual(resolve_airport("Luleå"), "LLA")
        self.assertEqual(resolve_airport("umea"), "UME")
        self.assertEqual(resolve_airport("Umeå"), "UME")
        self.assertEqual(resolve_airport("ostersund"), "OSD")
        self.assertEqual(resolve_airport("Östersund"), "OSD")
        self.assertEqual(resolve_airport("kiruna"), "KRN")
        self.assertEqual(resolve_airport("ronneby"), "RNB")

    def test_unknown_airport(self):
        self.assertIsNone(resolve_airport("unknown_place_xyz"))
        self.assertIsNone(resolve_airport(""))


class TestDateParsing(unittest.TestCase):
    """Test date parsing for ISO dates and keywords."""

    def test_keywords(self):
        now_utc = datetime.now(timezone.utc)
        today = now_utc.strftime("%Y-%m-%d")
        self.assertEqual(parse_date_input("today"), today)
        self.assertEqual(parse_date_input("tomorrow"), parse_date_input("tom"))
        self.assertIsNotNone(parse_date_input("yesterday"))

    def test_iso_dates(self):
        self.assertEqual(parse_date_input("2026-10-26"), "2026-10-26")
        self.assertEqual(parse_date_input("20261026"), "2026-10-26")

    def test_invalid_dates(self):
        self.assertIsNone(parse_date_input("not-a-date"))
        self.assertIsNone(parse_date_input("2026-99-99"))


class TestTimeFormatting(unittest.TestCase):
    """Test timezone formatting into UTC and Europe/Stockholm local time."""

    def test_winter_time_cet(self):
        # 2026-10-26 is in CET (UTC+1)
        res = format_time_stockholm("2026-10-26T16:25:00Z")
        self.assertEqual(res, "16:25 UTC → 17:25 CET")

    def test_summer_time_cest(self):
        # 2026-07-15 is in CEST (UTC+2)
        res = format_time_stockholm("2026-07-15T16:25:00Z")
        self.assertEqual(res, "16:25 UTC → 18:25 CEST")

    def test_none_or_empty(self):
        self.assertEqual(format_time_stockholm(None), "–")
        self.assertEqual(format_time_stockholm(""), "–")


class TestGhostFlightDetection(unittest.TestCase):
    """Test filtering out empty ghost flights."""

    def test_empty_flight(self):
        self.assertTrue(is_ghost_flight({}))
        self.assertTrue(is_ghost_flight({"flightId": ""}))
        self.assertTrue(is_ghost_flight({"flightId": None}))

    def test_missing_place_and_time(self):
        # Has ID but no place and no scheduled time
        self.assertTrue(is_ghost_flight({"flightId": "SK123"}))

    def test_valid_flight(self):
        valid = {
            "flightId": "SK532",
            "departureAirportEnglish": "London LHR",
            "arrivalTime": {"scheduledUtc": "2026-10-26T16:25:00Z"},
        }
        self.assertFalse(is_ghost_flight(valid, direction="arrival"))


class TestFlightCardFormatting(unittest.TestCase):
    """Test the exact output format of flight cards."""

    def test_exact_example_card(self):
        raw = {
            "flightId": "SK532",
            "departureAirportEnglish": "London LHR",
            "airlineOperator": {
                "iata": "SK",
                "name": "SAS Scandinavian Airlines",
            },
            "arrivalTime": {
                "scheduledUtc": "2026-10-26T16:25:00Z",
                "estimatedUtc": None,
                "actualUtc": None,
            },
            "locationAndStatus": {
                "terminal": "T5",
                "gate": None,
                "flightLegStatusEnglish": "Scheduled",
            },
            "baggage": {
                "baggageClaimUnit": "3",
            },
            "diIndicator": "I",
        }
        card = format_flight_card(raw, 1, direction="arrival", current_airport="ARN")
        lines = card.strip().split("\n")
        self.assertEqual(lines[0], "[1] SK532 | SAS Scandinavian Airlines (SK)")
        self.assertEqual(lines[1], "   From     : London LHR")
        self.assertEqual(lines[2], "   To       : (ARN)")
        self.assertEqual(lines[3], "   Status   : Scheduled")
        self.assertEqual(lines[4], "   Terminal : T5   Gate: N/A")
        self.assertEqual(lines[5], "   Baggage  : 3")
        self.assertEqual(lines[6], "   Sched    : 16:25 UTC → 17:25 CET")
        self.assertEqual(lines[7], "   Est      : –")
        self.assertEqual(lines[8], "   Actual   : –")
        self.assertEqual(lines[9], "   D/I      : I")


class TestCityNameCleaningAndLookup(unittest.TestCase):
    """Test city cleaning and country mapping in destinations.py."""

    def test_clean_city_name(self):
        self.assertEqual(clean_city_name("London LHR"), "London")
        self.assertEqual(clean_city_name("Paris CDG"), "Paris")
        self.assertEqual(clean_city_name("Frankfurt FRA"), "Frankfurt")
        self.assertEqual(clean_city_name("Palma de Mallorca PMI"), "Palma de Mallorca")
        self.assertEqual(clean_city_name("Stockholm Arlanda"), "Stockholm")
        self.assertEqual(clean_city_name("Visby VBY"), "Visby")
        self.assertEqual(clean_city_name("London (LHR)"), "London")

    def test_country_lookup(self):
        city_to_country, _ = load_city_country_data()
        self.assertEqual(lookup_country("London", city_to_country), "United Kingdom")
        self.assertEqual(lookup_country("Paris", city_to_country), "France")
        self.assertEqual(lookup_country("Berlin", city_to_country), "Germany")
        self.assertEqual(lookup_country("Visby", city_to_country), "Sweden")
        self.assertEqual(lookup_country("Goteborg", city_to_country), "Sweden")


class TestSwedaviaClient(unittest.TestCase):
    """Test SwedaviaClient endpoints in Demo Mode."""

    def setUp(self):
        self.client = SwedaviaClient(api_key="")

    def test_heartbeat(self):
        hb = self.client.get_heartbeat()
        self.assertEqual(hb["statusCode"], 200)
        self.assertTrue(hb["demo"])

    def test_arrivals(self):
        arrs = self.client.get_arrivals("ARN", "2026-10-26")
        self.assertGreater(len(arrs), 50)  # Paging requirement test

    def test_departures(self):
        deps = self.client.get_departures("ARN", "2026-10-26")
        self.assertGreater(len(deps), 50)

    def test_query(self):
        q, _ = self.client.query("airport eq 'ARN' and scheduled eq '20261026'")
        self.assertGreater(len(q), 0)
        # Verify wrapped structure
        first = q[0]
        self.assertTrue("departure" in first or "arrival" in first)

    def test_search_flight(self):
        results = self.client.search_flight_number("SK532", airport="ARN", date_str="2026-10-26")
        self.assertGreater(len(results), 0)


if __name__ == "__main__":
    unittest.main()
