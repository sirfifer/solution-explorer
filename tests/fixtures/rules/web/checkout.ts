// Checkout rules fixture: all four rule kinds in TypeScript.

import { z } from "zod";

// validation (certain): a zod field chain with constraints.
export const CheckoutSchema = z.object({
  email: z.string().email(),
  quantity: z.number().min(1).max(999),
});

// io (certain): declarative field bounds via class-validator decorators.
export class ShippingDto {
  @MaxLength(120)
  address!: string;

  @IsEmail()
  email!: string;
}

export function computeCharge(subtotal: number, taxRate: number): number {
  // calculation (inferred): a formula over domain operands.
  const tax = subtotal * taxRate;
  if (subtotal < 0) {
    // validation (inferred): a guard clause that throws a validation error.
    throw new ValidationError("subtotal must be non-negative");
  }
  return subtotal + tax;
}

export function shippingCost(zone: string): number {
  // policy (inferred): a decision table over a domain value.
  switch (zone) {
    case "domestic":
      return 5;
    case "regional":
      return 12;
    case "international":
      return 30;
    default:
      return 0;
  }
}
