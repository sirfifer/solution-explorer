import { describe, it, expect } from "vitest";
import { validateBearerToken } from "./index";

// INGEST_TOKEN auth uses a constant-time (digest-then-compare) check so a
// wrong token cannot be recovered via a timing side channel (F-PL-7). These
// tests pin the observable behavior: only the exact token authorizes.
function req(auth?: string): Request {
  const headers = new Headers();
  if (auth !== undefined) {
    headers.set("Authorization", auth);
  }
  return new Request("https://example.com/ingest", { method: "POST", headers });
}

describe("validateBearerToken", () => {
  const secret = "s3cret-ingest-token";

  it("accepts the exact bearer token", async () => {
    expect(await validateBearerToken(req(`Bearer ${secret}`), secret)).toBe(true);
  });

  it("rejects a wrong token of the same length", async () => {
    const wrong = "s3cret-ingest-tokeX";
    expect(wrong.length).toBe(secret.length);
    expect(await validateBearerToken(req(`Bearer ${wrong}`), secret)).toBe(false);
  });

  it("rejects a token that is a prefix of the secret", async () => {
    expect(await validateBearerToken(req(`Bearer ${secret.slice(0, -1)}`), secret)).toBe(false);
  });

  it("rejects a longer token that starts with the secret", async () => {
    expect(await validateBearerToken(req(`Bearer ${secret}extra`), secret)).toBe(false);
  });

  it("rejects a missing Authorization header", async () => {
    expect(await validateBearerToken(req(), secret)).toBe(false);
  });

  it("rejects a non-Bearer scheme", async () => {
    expect(await validateBearerToken(req(`Basic ${secret}`), secret)).toBe(false);
  });
});
