import math

def position_size(capital: float, risk_pct: float, entry: float, stop: float,
                  max_allocation_pct: float = 20.0) -> dict:
    if capital <= 0 or entry <= 0 or stop <= 0 or entry <= stop:
        return {"quantity": 0, "notional": 0.0, "risk_amount": 0.0, "valid": False}
    risk_amount = capital * risk_pct / 100
    qty_by_risk = math.floor(risk_amount / (entry - stop))
    qty_by_allocation = math.floor((capital * max_allocation_pct / 100) / entry)
    qty = max(0, min(qty_by_risk, qty_by_allocation))
    return {"quantity": qty, "notional": qty * entry,
            "risk_amount": qty * (entry - stop), "valid": qty > 0}