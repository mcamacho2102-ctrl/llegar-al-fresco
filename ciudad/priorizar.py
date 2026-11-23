"""Compara ubicaciones para un solo banco sobre la misma muestra de portales."""

from bisect import bisect_right
from collections import defaultdict
from math import dist
from statistics import median

from shapely.geometry import LineString

from ciudad.aforos import count_on_edge, nearby_footfall
from ciudad.motor import TO_METERS, coordinates, finite

SEARCH_BUDGET = 14000
MAX_CANDIDATES = 12


def not_near_bench(city, xy):
    nearby = city.poi_tree.query_ball_point(xy, 12)
    return all(city.pois[i]["kind"] != "bench" for i in nearby)


def suggest_sites(city, center, radius, origins, baseline, evaluate, rest_limit):
    grid = defaultdict(dict)
    for index, (origin, (base, incomplete)) in enumerate(zip(origins, baseline)):
        if incomplete:
            continue
        if base is None:
            base, _ = evaluate(origin, None, enforce_rest=False)
        if not base or base["maxWithoutRest"] < rest_limit * 0.6:
            continue
        line = LineString(
            [TO_METERS.transform(*point) for point in base["geometry"]["coordinates"]]
        )
        breaks = [
            0,
            *(rest["atM"] for rest in base["rests"] if 0 < rest["atM"] < line.length),
            line.length,
        ]
        # Probe the middle of long gaps and sample the corridor at regular intervals.
        probes = {
            start + (end - start) / 2
            for start, end in zip(breaks, breaks[1:])
            if end - start >= rest_limit * 0.6
        }
        step = min(35, max(12, rest_limit // 6))
        probes.update(range(step // 2, round(line.length), step))
        for offset in sorted(probes):
            segment = bisect_right(breaks, offset) - 1
            if segment + 1 >= len(breaks):
                continue
            start, end = breaks[segment : segment + 2]
            left, right = offset - start, end - offset
            if min(left, right) < 8 or end - start < rest_limit * 0.6:
                continue
            point = line.interpolate(offset)
            xy = point.x, point.y
            if dist(xy, center) > radius - 0.1:
                continue
            gain = int(baseline[index][0] is None and max(left, right) <= rest_limit)
            score = (gain, min(left, right), -offset)
            key = (int((xy[0] - center[0]) // 24), int((xy[1] - center[1]) // 24))
            previous = grid[key].get(index)
            if previous is None or score > previous[0]:
                grid[key][index] = (score, xy)

    clusters = sorted(
        grid.values(),
        key=lambda sites: (
            sum(score[0] for score, _ in sites.values()),
            len(sites),
            sum(score[1] for score, _ in sites.values()),
        ),
        reverse=True,
    )
    selected = []
    for cluster in clusters:
        for _, xy in sorted(cluster.values(), reverse=True):
            dock = city.locate(*coordinates(xy), bench=True)
            if (
                dock is not None
                and dock.offset < 0.4
                and dist(dock.xy, center) <= radius
                and all(dist(dock.xy, existing.xy) >= 26 for existing in selected)
                and not_near_bench(city, dock.xy)
            ):
                selected.append(dock)
                break
        if len(selected) == MAX_CANDIDATES:
            break
    return selected


def site_label(city, dock):
    street = city.names[city.name[dock.edge]]
    if street:
        return street
    x, y = dock.xy
    with city.db_connect() as conn:
        near = conn.execute(
            """SELECT label FROM portals
               WHERE x BETWEEN :lo_x AND :hi_x AND y BETWEEN :lo_y AND :hi_y
               ORDER BY (x-:x)*(x-:x)+(y-:y)*(y-:y) LIMIT 1""",
            {
                "x": x,
                "y": y,
                "lo_x": x - 50,
                "hi_x": x + 50,
                "lo_y": y - 50,
                "hi_y": y + 50,
            },
        ).fetchone()
    return "Junto a " + near["label"] if near else "Tramo peatonal cartografiado"


def measured_effect(samples, baseline, routes, complete, populations):
    gained, lost, reductions = [], 0, []
    for i in complete:
        before, after = baseline[i][0], routes[i][0]
        used_bench = after and any(rest["simulated"] for rest in after["rests"])
        if before is None and used_bench:
            gained.append(samples[i]["section"])
        elif before is not None and after is None:
            lost += 1
        elif before and after:
            reductions.append(
                before["maxWithoutRest"] - after["maxWithoutRest"] if used_bench else 0
            )
    sections = set(gained)
    population, older = populations
    known = all(section in population for section in sections)
    return {
        "newPaths": len(gained),
        "lostPaths": lost,
        "reducedGaps": sum(v > 0 for v in reductions),
        "pairedPaths": len(reductions),
        # Mediana solo entre las rutas que el banco acorta de verdad.
        "medianReductionM": (
            round(median([v for v in reductions if v > 0]), 1)
            if any(v > 0 for v in reductions)
            else None
        ),
        "newSections": len(sections),
        "olderInNewSections": (
            sum(older[section] for section in sections) if known else None
        ),
    }


def compare_banks(
    city,
    samples,
    center,
    radius,
    when,
    rest_limit,
    populations,
    stations,
    evaluate,
    improvement,
):
    origins = [tuple(coordinates((row["x"], row["y"]))) for row in samples]
    baseline = [evaluate(origin, None) for origin in origins]
    sites = suggest_sites(city, center, radius, origins, baseline, evaluate, rest_limit)
    scenarios = [improvement(dock) for dock in sites]
    alternatives = [
        [evaluate(origin, scenario) for origin in origins] for scenario in scenarios
    ]
    # A failed search is excluded from every comparison, including the baseline.
    complete = [
        i
        for i, (_, incomplete) in enumerate(baseline)
        if not incomplete and all(not result[i][1] for result in alternatives)
    ]
    footfall = nearby_footfall(stations, center, radius, when)
    zone_sections = {row["section"] for row in samples}
    population, older = populations
    cards = []
    for dock, scenario, results in zip(sites, scenarios, alternatives):
        effect = measured_effect(samples, baseline, results, complete, populations)
        width = finite(city.explicit_width[dock.edge])
        if width is None:
            width = finite(city.attrs[dock.edge, 0])
        sun = city.exposure(dock.edge, int(when.timestamp() // 900))
        cards.append(
            {
                "id": f"{dock.edge}:{dock.ratio:.6f}",
                "label": site_label(city, dock),
                "scenario": scenario.model_dump(),
                **effect,
                "widthM": round(width, 2) if width is not None else None,
                "sunFraction": round(sun, 2) if sun is not None else None,
                "footfall": count_on_edge(footfall, dock),
            }
        )
    cards.sort(
        key=lambda row: (
            row["newPaths"] - row["lostPaths"],
            row["newPaths"],
            row["reducedGaps"],
            (
                row["medianReductionM"]
                if row["medianReductionM"] is not None
                else float("-inf")
            ),
            row["olderInNewSections"] if row["olderInNewSections"] is not None else -1,
        ),
        reverse=True,
    )
    return {
        "sample": len(origins),
        "completed": len(complete),
        "baselinePaths": sum(baseline[i][0] is not None for i in complete),
        "sitesTested": len(sites),
        "radiusM": radius,
        "restM": rest_limit,
        "olderInSampleSections": (
            sum(older[s] for s in zone_sections)
            if zone_sections and all(s in population for s in zone_sections)
            else None
        ),
        "options": cards[:3],
        "footfall": [reading for _, _, reading in footfall],
    }
