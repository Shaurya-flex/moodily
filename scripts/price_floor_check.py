#!/usr/bin/env python3
"""Internal price-floor check (owner only). Never publishes anything.

Reads   src/data/services.json            (public prices)
        private/pricing-internal.json      (gitignored: hours, cash costs, target prices)
Prints  for each service the labour floor at three hourly-value floors (₹750 / ₹1,250 / ₹2,000)
        and flags public prices that sit below a floor.

floor = hours × (1 + revision_allowance) × (1 + pm_buffer) × hourly_value + cash_cost
Urgency and integration complexity are priced per quote (estimator multipliers), not in the floor.
Template: scripts/pricing-internal.example.json — copy to private/pricing-internal.json and fill real numbers.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = ROOT / "private" / "pricing-internal.json"


def main():
    if not PRIVATE.exists():
        sys.exit("Missing {} — copy scripts/pricing-internal.example.json there (the folder is gitignored).".format(PRIVATE.relative_to(ROOT)))
    cfg = json.loads(PRIVATE.read_text(encoding="utf-8"))
    rates = cfg.get("hourly_floors", [750, 1250, 2000])
    rev, pm = cfg.get("revision_allowance", 0.15), cfg.get("pm_buffer", 0.15)
    services = json.loads((ROOT / "src/data/services.json").read_text(encoding="utf-8"))["services"]
    print("{:<38} {:>10} {:>7} {:>7}  {}".format("service", "public ₹", "hours", "cash ₹", "  ".join("floor@{}".format(r) for r in rates)))
    below = 0
    for s in services:
        if not s.get("active", True):
            continue
        row = cfg["services"].get(s["id"])
        price = s.get("price_from")
        if not row or row.get("estimatedHoursInternal") is None:
            print("{:<38} {:>10}   (no internal estimate)".format(s["id"], price if price is not None else "custom"))
            continue
        hours, cash = row["estimatedHoursInternal"], row.get("cashCostInternal", 0) or 0
        floors = [round(hours * (1 + rev) * (1 + pm) * r + cash) for r in rates]
        marks = []
        for f in floors:
            flag = "!" if price is not None and price < f else " "
            below += flag == "!"
            marks.append("{:>9}{}".format(f, flag))
        print("{:<38} {:>10} {:>7} {:>7}  {}".format(s["id"], price if price is not None else "custom", hours, cash, " ".join(marks)))
    print("\n'!' = public price below that floor ({} cells). Unit for monthly services = per month. Review before changing prices.".format(below))


if __name__ == "__main__":
    main()
