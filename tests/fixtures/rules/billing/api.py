"""An API handler whose body carries a rule, to exercise the trigger link.

The guard clause's enclosing symbol is the route handler, which is also the
defining symbol of the derived ``api`` capability, so the rule's trigger
context resolves to that capability (P5-5 trigger-context linkage).
"""

from flask import Flask, request

app = Flask(__name__)


@app.post("/charges")
def create_charge():
    amount = request.json.get("amount")
    if amount is None or amount <= 0:
        raise ValueError("amount must be a positive number")
    return {"ok": True}
