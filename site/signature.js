// Signature computation for the page. Uses Web Crypto only, no dependencies.
// The same file is loaded by tests/js/signature-vectors.test.mjs under Node.
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.WebhookSignatures = api;
  }
})(globalThis, function () {
  "use strict";

  const HASHES = { sha256: "SHA-256", sha384: "SHA-384", sha512: "SHA-512" };

  function toHex(buffer) {
    return Array.from(new Uint8Array(buffer), (b) => b.toString(16).padStart(2, "0")).join("");
  }

  function toBase64(buffer) {
    let binary = "";
    new Uint8Array(buffer).forEach((b) => {
      binary += String.fromCharCode(b);
    });
    return btoa(binary);
  }

  async function mac(secret, message, algorithm) {
    const hash = HASHES[algorithm];
    if (!hash) throw new Error("unsupported hash: " + algorithm);
    const enc = new TextEncoder();
    const key = await crypto.subtle.importKey(
      "raw",
      enc.encode(secret),
      { name: "HMAC", hash },
      false,
      ["sign"],
    );
    return crypto.subtle.sign("HMAC", key, enc.encode(message));
  }

  // Returns the exact string the Python helpers expect for the same mode:
  //   github       sha256=<hex>                       (X-Hub-Signature-256)
  //   stripe       t=<unix seconds>,v1=<hex>          (<t>.<body> is signed)
  //   hmac-hex     <hex digest>
  //   hmac-base64  <base64 digest>
  async function compute({ mode, secret, body, timestamp, algorithm = "sha256" }) {
    if (mode === "github") {
      return "sha256=" + toHex(await mac(secret, body, "sha256"));
    }
    if (mode === "stripe") {
      const ts = String(timestamp ?? "").trim();
      if (!/^\d+$/.test(ts)) throw new Error("Timestamp must be whole unix seconds.");
      return "t=" + ts + ",v1=" + toHex(await mac(secret, ts + "." + body, "sha256"));
    }
    if (mode === "hmac-hex") return toHex(await mac(secret, body, algorithm));
    if (mode === "hmac-base64") return toBase64(await mac(secret, body, algorithm));
    throw new Error("unknown mode: " + mode);
  }

  return { compute, HASHES };
});
