/**
 * GitHub webhook signature validation using Web Crypto API.
 * Uses timing-safe comparison to prevent timing side-channel attacks.
 */

const encoder = new TextEncoder();

/**
 * Verify a GitHub webhook signature against the expected HMAC-SHA256.
 * Returns true if the signature is valid.
 */
export async function verifyWebhookSignature(
  payload: string,
  signatureHeader: string,
  secret: string,
): Promise<boolean> {
  if (!signatureHeader.startsWith("sha256=")) {
    return false;
  }

  const receivedHex = signatureHeader.slice(7);
  if (receivedHex.length !== 64) {
    return false;
  }

  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );

  const signatureBuffer = await crypto.subtle.sign(
    "HMAC",
    key,
    encoder.encode(payload),
  );

  const computedHex = Array.from(new Uint8Array(signatureBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  return timingSafeEqual(computedHex, receivedHex);
}

/**
 * Constant-time string comparison. Compares every character regardless of
 * where mismatches occur, preventing timing side-channel attacks.
 *
 * The early return on length mismatch is safe because both inputs are
 * hex-encoded SHA-256 digests with a fixed known length (64 chars).
 */
function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) {
    return false;
  }
  let result = 0;
  for (let i = 0; i < a.length; i++) {
    result |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return result === 0;
}
