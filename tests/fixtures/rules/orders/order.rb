# Order rules fixture: all four rule kinds in Ruby.

class Order < ApplicationRecord
  # validation (certain): a Rails validates declaration.
  validates :email, presence: true
  validates :total, numericality: true

  # policy (certain): an authorization gate.
  before_action :authorize_owner

  def compute_total(subtotal, tax_rate)
    # calculation (inferred): a formula over domain operands.
    tax = subtotal * tax_rate
    grand_total = subtotal + tax
    grand_total
  end

  def status_label(status)
    # policy (inferred): a decision table over a domain value.
    case status
    when "open"
      "Open"
    when "closed"
      "Closed"
    when "pending"
      "Pending"
    end
  end

  def validate_amount(amount)
    # validation (inferred): a guard clause raising a validation error.
    raise ArgumentError, "amount must be positive" unless amount > 0
  end
end
