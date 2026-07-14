"""Billing rules fixture: all four rule kinds in Python.

Rule-bearing code only; ordinary control flow lives in the noise unit tests.
"""

from django.db import models
from pydantic import BaseModel, field_validator


class InvoiceForm(BaseModel):
    email: str
    amount: float

    @field_validator("email")
    def check_email(cls, value):
        # validation (inferred): a guard clause raising a validation error.
        if not value or "@" not in value:
            raise ValueError("email is required and must contain @")
        return value


class Invoice(models.Model):
    # io (certain): declarative field bounds on a model field.
    number = models.CharField(max_length=32, null=False)
    note = models.CharField(max_length=200)


def compute_total(subtotal, tax_rate, discount):
    # calculation (inferred): a formula over domain operands.
    tax = subtotal * tax_rate
    total = subtotal + tax - discount
    return total


def price_for_tier(tier):
    # policy (inferred): a decision-table match over a domain value.
    match tier:
        case "free":
            return 0
        case "pro":
            return 20
        case "enterprise":
            return 100


def can_refund(user, invoice):
    # policy (certain): a permission gate.
    return user.is_staff and invoice.amount > 0
