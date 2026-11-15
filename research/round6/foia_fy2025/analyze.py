#!/usr/bin/env python3
"""Round 6 FOIA desk reconciliation (research only).

Reads the official FOIA.gov "All Agency Data" CSV ZIPs for FY2025 and FY2024,
verifies their SHA-256, excludes the 'All agencies' total row, reconciles
agency sums to that row and to the DOJ OIP published totals, and computes
descriptive per-agency ratios.

Nothing here is a cost per verified useful outcome (CPVO). Ratios are
descriptive: reported processing cost (requests + appeals administration)
divided by requests processed (all closure types).

Usage: python3 -I analyze.py <dir-with-zips> > results.json
Stdlib only.
"""
import csv, hashlib, io, json, statistics, sys, zipfile
from pathlib import Path

EXPECTED_SHA256 = {
    "all_agencies_csv_2025.zip": "7889799cfd4cd347b8d98d0d65222dfbfe9f6b46adfb53768ae0e94b1dfe41f7",
    "all_agencies_csv_2024.zip": "15a0a85680912a43170dd117407e4af6dc6d726b921481c43c1353ea010e6762",
    "all_agencies_csv_2023.zip": "1b1352c339d42f380f3d9e4f7a87246cb3cb6b7b08121328921ac8550294c4dc",
    "all_agencies_csv_2022.zip": "9efb6bc914e7195a1e725d9edb1b7af3da02e0e432e0317137faeb6194e5d258",
    "all_agencies_csv_2021.zip": "e9ca23b377c6976bedcda3bf3f20106de88c65ac365c268be7e18d02287586e0",
}
# NARA OGIS FY2025 Appendix B (CFO-Act cohort) values that GPT-6's audit relied on
NARA_FY24 = {"Environmental Protection Agency": 442230, "Department of Housing and Urban Development": 139159}
# Plausibility screen: reported processing cost per reported FOIA FTE.
# Federal loaded labor cost cannot plausibly be this low; flag, don't correct.
MIN_COST_PER_FTE = 20000
# DOJ OIP FY2025 summary (justice.gov/oip/media/1450791/dl)
DOJ_FY2025 = {"processed": 1635055, "received": 1707197,
              "processing_cost": 610670216.34, "litigation_cost": 50724642.09,
              "fte": 4823.17}
TABLES = {
    "cost": "costs-and-fees-collected",
    "req": "received-processed-and-pending-foia-requests",
    "fte": "foia-personnel",
    "disp": "disposition-of-foia-requests-all-processed-requests",
    "app": "received-processed-and-pending-administrative-appeals",
}
TOTAL_ROW = "All agencies"
SUBSTANTIVE = ["Number of Full Grants", "Number of Partial Grants/Partial Denials",
               "Number of Full Denials Based on Exemptions"]


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load(zpath, keys=tuple(TABLES)):
    out = {}
    with zipfile.ZipFile(zpath) as z:
        for key in keys:
            frag = TABLES[key]
            names = [n for n in z.namelist() if frag in n]
            assert len(names) == 1, (key, names)
            rows = list(csv.DictReader(io.TextIOWrapper(z.open(names[0]), encoding="utf-8-sig")))
            assert {r["Component"] for r in rows} == {"Agency Overall"}, key
            agencies = [r["Agency"].strip().lower() for r in rows]
            assert len(agencies) == len(set(agencies)), f"duplicate agency in {key}"
            out[key] = {"file": names[0], "rows": {r["Agency"].strip(): r for r in rows}}
    return out


def history(zips, agency):
    """Processing cost, processed requests and FTE by year for one agency (case-insensitive)."""
    h = {}
    for y, t in sorted(zips.items()):
        def get(k):
            m = {a.lower(): r for a, r in t[k]["rows"].items()}
            return m.get(agency.lower())
        c, r, f = get("cost"), get("req"), get("fte")
        if not c:
            continue
        pc, pr = num(c["Processing Costs"]), num(r["Number of Requests Processed in Fiscal Year"])
        fte = num(next(v for k, v in f.items() if k.startswith("Total Number")))
        h[y] = {"processing_cost": pc, "processed": pr, "fte": fte,
                "cost_per_processed": round(pc / pr, 2) if pr else None,
                "cost_per_fte": round(pc / fte) if fte else None}
    return h


def num(s):
    s = (s or "").replace(",", "").strip()
    return float(s) if s not in ("", "N/A") else None


def quartiles(xs):
    q = statistics.quantiles(xs, n=4, method="inclusive")
    return {"p25": round(q[0], 2), "median": round(q[1], 2), "p75": round(q[2], 2)}


def main(d):
    d = Path(d)
    prov = {}
    for f, h in EXPECTED_SHA256.items():
        got = sha256(d / f)
        prov[f] = {"sha256": got, "matches_expected": got == h}
        assert got == h, f
    y25, y24 = load(d / "all_agencies_csv_2025.zip"), load(d / "all_agencies_csv_2024.zip")
    prov["tables_2025"] = {k: v["file"] for k, v in y25.items()}
    years = {f"FY{y}": load(d / f"all_agencies_csv_{y}.zip", ("cost", "req", "fte"))
             for y in range(2021, 2026)}

    agencies = sorted(a for a in y25["cost"]["rows"] if a != TOTAL_ROW)
    for k in TABLES:
        assert sorted(a for a in y25[k]["rows"] if a != TOTAL_ROW) == agencies, f"agency set mismatch in {k}"

    recs, missing = [], []
    for a in agencies:
        c = y25["cost"]["rows"][a]; r = y25["req"]["rows"][a]
        f = y25["fte"]["rows"][a]; dp = y25["disp"]["rows"][a]; ap = y25["app"]["rows"][a]
        pc, proc = num(c["Processing Costs"]), num(r["Number of Requests Processed in Fiscal Year"])
        fte = num(f['Total Number of "Full-Time FOIA Staff"'])
        subst = sum(num(dp[k]) or 0 for k in SUBSTANTIVE)
        c24 = y24["cost"]["rows"].get(a, {})
        rec = {
            "agency": a, "processing_cost": pc, "litigation_cost": num(c["Litigation-Related Costs"]),
            "processed": proc, "received": num(r["Number of Requests Received in Fiscal Year"]),
            "fte": fte, "substantive_closures": subst,
            "appeals_processed": num(ap["Number of Appeals Processed in Fiscal Year"]),
            "processing_cost_fy2024": num(c24.get("Processing Costs")),
        }
        rec["cost_per_processed"] = round(pc / proc, 2) if pc is not None and proc else None
        rec["cost_per_substantive"] = round(pc / subst, 2) if pc is not None and subst else None
        rec["processed_per_fte"] = round(proc / fte, 1) if proc is not None and fte else None
        if rec["cost_per_processed"] is None:
            missing.append({"agency": a, "processing_cost": pc, "processed": proc})
        recs.append(rec)

    def tot(key):
        return sum(x[key] or 0 for x in recs)

    T = y25
    tr = lambda k, col: num(T[k]["rows"][TOTAL_ROW][col])
    recon = {
        "processing_cost": {"sum_agencies": round(tot("processing_cost"), 2),
                            "all_agencies_row": tr("cost", "Processing Costs"),
                            "doj_summary": DOJ_FY2025["processing_cost"]},
        "litigation_cost": {"sum_agencies": round(tot("litigation_cost"), 2),
                            "all_agencies_row": tr("cost", "Litigation-Related Costs"),
                            "doj_summary": DOJ_FY2025["litigation_cost"]},
        "processed": {"sum_agencies": tot("processed"),
                      "all_agencies_row": tr("req", "Number of Requests Processed in Fiscal Year"),
                      "doj_summary": DOJ_FY2025["processed"]},
        "received": {"sum_agencies": tot("received"),
                     "all_agencies_row": tr("req", "Number of Requests Received in Fiscal Year"),
                     "doj_summary": DOJ_FY2025["received"]},
        "fte": {"sum_agencies": round(tot("fte"), 2),
                "all_agencies_row": tr("fte", 'Total Number of "Full-Time FOIA Staff"'),
                "doj_summary": DOJ_FY2025["fte"]},
        "appeals_processed": {"sum_agencies": tot("appeals_processed"),
                              "all_agencies_row": tr("app", "Number of Appeals Processed in Fiscal Year")},
        "substantive_closures": {"sum_agencies": tot("substantive_closures")},
    }

    valid = [x for x in recs if x["cost_per_processed"] is not None]
    ratios = [x["cost_per_processed"] for x in valid]
    big = [x for x in valid if x["processed"] >= 1000]
    weighted = tot("processing_cost") / tot("processed")
    excl = {"Environmental Protection Agency", "Department of Housing and Urban Development"}
    pc_ex = sum(x["processing_cost"] for x in valid if x["agency"] not in excl)
    pr_ex = sum(x["processed"] for x in valid if x["agency"] not in excl)

    def share_top(n):
        s = sorted(valid, key=lambda x: -x["processing_cost"])[:n]
        return {"agencies": [x["agency"] for x in s],
                "cost_share": round(sum(x["processing_cost"] for x in s) / tot("processing_cost"), 4),
                "processed_share": round(sum(x["processed"] for x in s) / tot("processed"), 4)}

    yoy = []
    for x in valid:
        a, b = x["processing_cost_fy2024"], x["processing_cost"]
        if a and b and a > 0 and (b / a >= 5 or b / a <= 0.2) and max(a, b) >= 1e6:
            yoy.append({"agency": x["agency"], "fy2024": a, "fy2025": b, "ratio": round(b / a, 2)})

    plaus = [{"agency": x["agency"], "processing_cost": x["processing_cost"], "fte": x["fte"],
              "cost_per_fte": round(x["processing_cost"] / x["fte"])}
             for x in valid if x["fte"] and x["fte"] >= 1 and x["processing_cost"] / x["fte"] < MIN_COST_PER_FTE]
    nara_check = {a: {"nara_fy2024": v, "foia_gov_fy2024": history(years, a).get("FY2024", {}).get("processing_cost"),
                      "history": history(years, a)} for a, v in NARA_FY24.items()}
    plaus_hist = {}
    for y, t in years.items():
        flagged = []
        for a in t["cost"]["rows"]:
            if a == TOTAL_ROW:
                continue
            h = history({y: t}, a).get(y)
            if h and h["fte"] and h["fte"] >= 5 and h["cost_per_fte"] is not None and h["cost_per_fte"] < MIN_COST_PER_FTE:
                flagged.append({"agency": a, **h})
        plaus_hist[y] = flagged
    national_hist = {y: history({y: t}, TOTAL_ROW)[y] for y, t in years.items()}

    res = {
        "provenance": prov,
        "coverage": {"agencies": len(agencies), "with_ratio": len(valid), "excluded": missing},
        "reconciliation": recon,
        "national_weighted": {
            "cost_per_processed": round(weighted, 2),
            "cost_per_processed_excl_EPA_HUD": round(pc_ex / pr_ex, 2),
            "cost_per_substantive_closure": round(tot("processing_cost") / tot("substantive_closures"), 2),
            "processed_per_fte": round(tot("processed") / tot("fte"), 1),
            "substantive_share_of_processed": round(tot("substantive_closures") / tot("processed"), 4),
            "appeals_per_processed_request": round(tot("appeals_processed") / tot("processed"), 4),
        },
        "unweighted_agency_distribution": {
            "cost_per_processed_all": {"n": len(ratios), **quartiles(ratios)},
            "cost_per_processed_ge1000_processed": {"n": len(big), **quartiles([x["cost_per_processed"] for x in big])},
            "processed_per_fte_all": {"n": len([x for x in valid if x["processed_per_fte"]]),
                                      **quartiles([x["processed_per_fte"] for x in valid if x["processed_per_fte"]])},
        },
        "concentration": {"top1": share_top(1), "top5": share_top(5), "top10": share_top(10)},
        "yoy_cost_swings_5x_over_1M": sorted(yoy, key=lambda x: -x["ratio"]),
        "nara_vs_foia_gov_fy2024": nara_check,
        "plausibility_fy2025_cost_per_fte_below_min": plaus,
        "plausibility_by_year_fte_ge5": plaus_hist,
        "national_history": national_hist,
        "agencies": recs,
    }
    json.dump(res, sys.stdout, indent=1, sort_keys=False)


if __name__ == "__main__":
    main(sys.argv[1])
