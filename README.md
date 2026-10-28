# Swedavia FlightInfo v2 Terminal Application

A Python 3 terminal application interfacing with Sweden's national airport operator API: **Swedavia FlightInfo API v2** (`https://api.swedavia.se/flightinfo/v2`).

Features real-time flight tracking, arrivals, departures, OData query filters, API health check monitoring, flight number search, 50-item terminal pagination, destination & route analytics with country mapping, and an automatic **Demo Mode** fallback when no API key is provided.

---

## Table of Contents
1. [Features](#features)
2. [Supported Airports](#supported-airports)
3. [Project Structure](#project-structure)
4. [Prerequisites & Installation](#prerequisites--installation)
5. [Configuration & API Key](#configuration--api-key)
6. [Usage Guide](#usage-guide)
   - [Main Menu (`airport.py`)](#main-menu-airportpy)
   - [Destination Analytics (`destinations.py`)](#destination-analytics-destinationspy)
   - [Running Unit Tests](#running-unit-tests)
7. [Demo Mode](#demo-mode)
8. [Error Handling](#error-handling)

---

## Features

- **Direct Endpoints**:
  - `GET /{airport}/arrivals/{YYYY-MM-DD}`: Real-time arrivals for any Swedavia airport and date.
  - `GET /{airport}/departures/{YYYY-MM-DD}`: Real-time departures for any Swedavia airport and date.
  - `GET /query?filter=...`: OData query filters (e.g., `airport eq 'ARN' and scheduled eq '20261026' and flightId eq 'SK532'`) with `continuationToken` support.
  - `GET /heartBeat`: Internal health check and response latency telemetry.
- **Flight Card Layout**:
  Formatted flight cards with status translation, terminals, gates, baggage belts, and dual timezone display:
  ```text
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
  ```
- **Dual Timezone Formatting**:
  Scheduled, estimated, and actual times are shown as `HH:MM UTC → HH:MM CET` (or `CEST` in summer) using Python's standard library `zoneinfo` (`Europe/Stockholm`).
- **Terminal Pagination**:
  Lists are rendered 50 flights at a time with a dynamic progress banner:
  ```text
  ── Showing 50/217 ── (167 left)
  [Enter] next page | [a] show all | [q] back to menu:
  ```
- **Ghost Flight Filtering**:
  Empty or phantom flight records without valid `flightId`, route endpoints, or scheduled times are skipped.
- **Safe `.get()` Fallbacks**:
  Every field access is guarded with default values (`"N/A"` or `"–"`) to prevent runtime crashes on partial data feeds.
- **Destination & Country Analytics**:
  `destinations.py` parses incoming and outgoing routes, cleans trailing airport codes (e.g. `"London LHR"` $\rightarrow$ `"London"`), correlates cities with countries via `city_country.json`, and outputs ranked tables with percentage distribution bars and optional country/city filters.
- **Demo Mode**:
  If `SWEDAVIA_API_KEY` is not set or contains a placeholder, the app operates in Demo Mode with realistic simulated flights matching Swedavia's v2 JSON schema.

---

## Supported Airports

You can enter 3-letter IATA codes or city/airport names (case-insensitive, accents optional):

| IATA | City | Airport Name | Aliases & City Names Accepted |
|------|------|--------------|-------------------------------|
| `ARN` | Stockholm | Stockholm Arlanda Airport | `arn`, `arlanda`, `stockholm`, `stockholm arlanda` |
| `GOT` | Göteborg | Göteborg Landvetter Airport | `got`, `goteborg`, `gothenburg`, `landvetter` |
| `BMA` | Stockholm | Stockholm Bromma Airport | `bma`, `bromma`, `stockholm bromma` |
| `MMX` | Malmö | Malmö Airport (Sturup) | `mmx`, `malmo`, `sturup` |
| `LLA` | Luleå | Luleå Airport (Kallax) | `lla`, `lulea`, `kallax` |
| `UME` | Umeå | Umeå Airport | `ume`, `umea` |
| `OSD` | Östersund | Åre Östersund Airport | `osd`, `ostersund`, `are`, `are ostersund`, `froson` |
| `VBY` | Visby | Visby Airport (Gotland) | `vby`, `visby`, `gotland` |
| `RNB` | Ronneby | Ronneby Airport (Blekinge) | `rnb`, `ronneby`, `kallinge`, `blekinge` |
| `KRN` | Kiruna | Kiruna Airport | `krn`, `kiruna` |

Dates accept `YYYY-MM-DD`, `today`, `tomorrow`, and `yesterday`.

---

## Project Structure

```text
airport/
├── airport.py             # Main interactive terminal application & menu loop
├── swedavia_client.py     # Shared client library, HTTP engine, config, and formatters
├── destinations.py        # City/country route analysis and aggregation tool
├── city_country.json      # Bi-directional mapping (city_to_country & country_to_cities)
├── test_swedavia.py       # Comprehensive unit test suite (20 tests)
├── requirements.txt       # Dependencies (requests, python-dotenv, tzdata)
├── .env.example           # Environment template for Swedavia API subscription key
├── .gitignore             # Git ignore file (excludes .env, cache, venvs)
└── README.md              # Project documentation
```

---

## Prerequisites & Installation

- **Python**: 3.9 or higher (Python 3.12+ recommended).
- **Git** (optional).

### 1. Clone or Open Workspace
```bash
cd airport
```

### 2. Create and Activate a Virtual Environment
- **Windows (PowerShell)**:
  ```powershell
  python -m venv .venv
  .venv\Scripts\Activate.ps1
  ```
- **macOS / Linux**:
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

---

## Configuration & API Key

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Open `.env` and set your key:
   ```ini
   SWEDAVIA_API_KEY=your_actual_api_key_here
   ```
3. To obtain a free key:
   - Register on the [Swedavia Developer Portal](https://apideveloper.swedavia.se/).
   - Subscribe to the **FlightInfo v2** API product (free tier offers 10,000 requests per 30-day period).
   - Copy the primary or secondary subscription key into your `.env`.

> [!NOTE]
> If `.env` is omitted or `SWEDAVIA_API_KEY` is not set, the application starts in **Demo Mode**, generating realistic simulated flights.

---

## Usage Guide

### Main Menu (`airport.py`)

Run the terminal application:
```bash
python airport.py
```

The interactive menu provides the following options:
```text
╔═══════════════════════════════════════════════════════════════════════════╗
║               SWEDAVIA FLIGHT INFORMATION SYSTEM v2                       ║
║  Mode: LIVE API (api.swedavia.se)                                         ║
║  Airports: ARN GOT BMA MMX LLA UME OSD VBY RNB KRN                         ║
╚═══════════════════════════════════════════════════════════════════════════╝
Main Menu:
  1. Arrivals for an airport & date
  2. Departures for an airport & date
  3. Search a specific flight number
  4. OData query (choose airport, date, type A/D, optional flight number)
  5. HeartBeat - API health check
  6. Demo all endpoints automatically
  7. Destination analytics & country ranking
  q. Quit

Enter choice (1-7, q to quit):
```

#### Menu Options:
1. **Arrivals for an airport & date**:
   Prompts for an airport (e.g. `ARN` or `Visby`) and date (`YYYY-MM-DD`, `today`, `tomorrow`, `yesterday`). Displays incoming flights in 50-flight batches.
2. **Departures for an airport & date**:
   Prompts for an airport and date, displaying outbound flights in 50-flight batches.
3. **Search a specific flight number**:
   Looks up a flight code (e.g. `SK532`, `DY4001`) across arrivals and departures.
4. **OData query**:
   Executes an OData query against `/query?filter=...` with airport, date (formatted as `YYYYMMDD`), direction (`A`/`D`/`Both`), and optional flight number.
5. **HeartBeat**:
   Sends `GET /heartBeat` to inspect API latency and health status.
6. **Demo all endpoints automatically**:
   Runs an end-to-end walkthrough demonstrating all endpoints sequentially without manual input.
7. **Destination analytics & country ranking**:
   Launches the route analyzer directly from the menu.

---

### Destination Analytics (`destinations.py`)

Analyze flight destinations or origins, clean airport suffixes (e.g. `"London LHR"` $\rightarrow$ `"London"`), map cities to countries, and rank by flight volume.

#### Interactive Mode:
```bash
python destinations.py
```

#### Command-Line Arguments:
```bash
# Analyze all departures from Stockholm Arlanda for today
python destinations.py --airport ARN --direction departures --date today

# Filter destinations from Göteborg Landvetter by country (e.g. Spain)
python destinations.py --airport GOT --direction departures --filter Spain

# Analyze arrivals into Visby from yesterday
python destinations.py --airport VBY --direction arrivals --date yesterday
```

#### Sample Output:
```text
================================================================================
 Destinations (Departures) for Stockholm Arlanda Airport (ARN) - 2026-10-26
 Filter applied: 'Spain' (Matches: 3 cities, 8 flights)
================================================================================
#    City                     Country                 Flights    Share  Distribution
--------------------------------------------------------------------------------
1    Barcelona                Spain                         3    37.5%  █████
2    Madrid                   Spain                         3    37.5%  █████
3    Malaga                   Spain                         2    25.0%  ███
--------------------------------------------------------------------------------
 Total: 8 flights across 3 unique cities in 1 countries. (out of 65 total flights)
================================================================================
```

---

### Running Unit Tests

Run the test suite with Python's built-in `unittest` runner:
```bash
python -m unittest test_swedavia.py -v
```
All 20 tests verify airport code resolution, ISO date parsing, timezone conversion, card layouts, pagination, ghost flight filtering, and city/country lookups.

---

## Demo Mode

When no API key is detected in `.env`, the client enters Demo Mode:
- Heartbeat returns simulated health metadata (`statusCode: 200`, `Healthy (Demo Mode)`).
- Arrivals, departures, and queries return realistic simulated flights covering real airlines (SAS, Lufthansa, British Airways, KLM, Air France, Finnair, Norwegian, Ryanair), terminals, gates, and statuses.
- Flight `SK532` (London LHR $\rightarrow$ Stockholm Arlanda ARN) is included with scheduled time `16:25 UTC → 17:25 CET`, Baggage claim belt `3`, Terminal `T5`, and Domestic/International indicator `I`.
- 65 flights are returned so the 50-item terminal paginator can be tested.

---

## Error Handling

The client incorporates error handling for common API and network conditions:
- **`401 Unauthorized`**: Explains that the key is missing or invalid and instructs how to configure `.env`.
- **`404 Not Found`**: Informs the user when an airport or date is not found.
- **`429 Too Many Requests`**: Explains rate limits (10,000 monthly calls on the free tier) and suggests retrying.
- **Network / Timeout Errors**: Catches connection failures cleanly with actionable error messages without crashing the interactive loop.
