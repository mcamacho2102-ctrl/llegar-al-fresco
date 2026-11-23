"""Lectura y asociación conservadora de aforos peatonales municipales."""

from collections import defaultdict
import csv
from datetime import datetime
from math import dist
import re
from statistics import mean

from ciudad.fuentes import RAW
from ciudad.motor import TO_METERS, normal

PERMANENT_SOURCE = (
    "https://datos.madrid.es/dataset/300321-0-aforos-peatones-bicicletas/downloads"
)
CAMPAIGN_SOURCE = "https://datos.madrid.es/dataset/300197-0-aforo-trafico/downloads"


def decimal_coordinate(raw):
    value = raw.strip().replace(",", ".")
    if re.fullmatch(r"-?\d+(?:\.\d{3}){2}", value):
        return int(value.replace(".", "")) / 1e6
    return float(value)


def permanent_stations(city):
    source = RAW / "aforos/peatones-permanentes-2024.csv"
    if not source.is_file():
        return []
    stations = {}
    counts = defaultdict(dict)
    with source.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle, delimiter=";"):
            try:
                moment = datetime.strptime(row["fecha"], "%d/%m/%Y %H:%M")
                amount = int(row["peatones"])
                location = tuple(
                    decimal_coordinate(row[key]) for key in ("longitude", "latitude")
                )
                if amount < 0 or not (-4 < location[0] < -3 and 40 < location[1] < 41):
                    continue
            except (ValueError, TypeError):
                continue
            station = (row["device_id"], location)
            if station not in stations:
                xy = TO_METERS.transform(*location)
                dock = city.locate(*location, bench=True)
                if dock is not None and dock.offset > 4:
                    dock = None
                stations[station] = {
                    "id": f'{row["device_id"]}:{location[0]}:{location[1]}',
                    "label": row["direccion"].strip(),
                    "side": row["observaciones_direccion"].strip(),
                    "coordinates": location,
                    "xy": xy,
                    "edge": dock.edge if dock else None,
                    "kind": "permanent",
                    "source": PERMANENT_SOURCE,
                }
            counts[station][moment] = amount

    for station, observations in counts.items():
        hours = defaultdict(list)
        for moment, amount in observations.items():
            day = max(0, moment.weekday() - 4)
            hours[day, moment.hour].append((moment.date(), amount))
        stations[station]["hours"] = hours
    return list(stations.values())


def campaign_points(city):
    source = RAW / "aforos/peatones-campana-octubre-2024.csv"
    if not source.is_file():
        return []
    points = []
    with source.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle, delimiter=";"):
            if not row["Nº CONTROL"] or not row["DIRECCIÓN"]:
                continue
            street = re.sub(r"^P[º°]", "Paseo", row["DIRECCIÓN"], flags=re.I)
            numbers = re.findall(r"\d+", row["Nº"])
            for parity, column in enumerate(("PAR", "IMPAR")):
                portals = {n for n in numbers if int(n) % 2 == parity}
                if len(portals) != 1:
                    continue
                number = portals.pop()
                matches = city.search(f"{street} {number}")
                exact = {
                    tuple(place["coordinates"]): place["label"]
                    for place in matches
                    if normal(place["label"].partition(",")[2]) == str(int(number))
                }
                if len(exact) != 1:
                    continue
                location, address = exact.popitem()
                try:
                    amount = int(row[column])
                except (ValueError, TypeError):
                    continue
                if amount < 0:
                    continue
                points.append(
                    {
                        "id": f'campaign:{row["Nº CONTROL"]}:{column}',
                        "label": address,
                        "side": "Lado par" if parity == 0 else "Lado impar",
                        "coordinates": location,
                        "xy": TO_METERS.transform(*location),
                        "kind": "campaign",
                        "period": "Campaña de octubre de 2024",
                        "count": amount,
                        "source": CAMPAIGN_SOURCE,
                    }
                )
    return points


def read_footfall(city):
    return permanent_stations(city) + campaign_points(city)


def nearby_footfall(stations, center, radius, when):
    result = []
    for station in stations:
        distance = dist(station["xy"], center)
        if distance > radius:
            continue
        reading = {
            key: value
            for key, value in station.items()
            if key not in {"hours", "xy", "edge"}
        }
        reading["distanceM"] = round(distance)
        if station["kind"] == "permanent":
            hour = when.hour
            group = max(0, when.weekday() - 4)
            observations = station["hours"].get((group, hour), [])
            dates = [date for date, _ in observations]
            reading["hour"] = f"{hour:02d}:00"
            reading["dayType"] = ("lunes a viernes", "sábado", "domingo")[group]
            reading["days"] = len(dates)
            reading["count"] = (
                round(mean(amount for _, amount in observations)) if dates else None
            )
            reading["period"] = (
                f"{min(dates):%d/%m/%Y}–{max(dates):%d/%m/%Y}" if dates else None
            )
        result.append((distance, station, reading))
    return sorted(result, key=lambda item: (item[0], item[2]["id"]))


def count_on_edge(footfall, dock):
    matches = [
        (dist(station["xy"], dock.xy), reading)
        for _, station, reading in footfall
        if station["kind"] == "permanent"
        and bool(station["side"])
        and station["edge"] == dock.edge
        and dist(station["xy"], dock.xy) <= 20
        and reading["count"] is not None
    ]
    if len(matches) == 1:
        return matches[0][1]
    return None
