(function () {
  "use strict";

  const form = document.getElementById("sig-form");
  const mode = document.getElementById("mode");
  const secretInput = document.getElementById("secret");
  const bodyInput = document.getElementById("body");
  const timestampInput = document.getElementById("timestamp");
  const tsWrap = document.getElementById("ts-wrap");
  const result = document.getElementById("result");
  const output = document.getElementById("output");

  function encoder() {
    return new TextEncoder();
  }

  function toHex(buffer) {
    return [...new Uint8Array(buffer)].map((b) => b.toString(16).padStart(2, "0")).join("");
  }

  function toBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    bytes.forEach((b) => {
      binary += String.fromCharCode(b);
    });
    return btoa(binary);
  }

  async function hmacSha256(secret, messageBytes) {
    const key = await crypto.subtle.importKey(
      "raw",
      encoder().encode(secret),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign"]
    );
    return crypto.subtle.sign("HMAC", key, messageBytes);
  }

  function syncMode() {
    const stripe = mode.value === "stripe";
    tsWrap.classList.toggle("hidden", !stripe);
  }

  mode.addEventListener("change", syncMode);
  syncMode();

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const secret = secretInput.value;
    const body = bodyInput.value;
    const bodyBytes = encoder().encode(body);

    try {
      let text = "";
      if (mode.value === "github") {
        const digest = toHex(await hmacSha256(secret, bodyBytes));
        text = `X-Hub-Signature-256: sha256=${digest}\n\nsha256=${digest}`;
      } else if (mode.value === "stripe") {
        const ts = (timestampInput.value || Math.floor(Date.now() / 1000)).toString();
        if (!/^\d+$/.test(ts)) {
          throw new Error("timestamp must be unix seconds");
        }
        const payload = encoder().encode(`${ts}.`);
        const joined = new Uint8Array(payload.length + bodyBytes.length);
        joined.set(payload, 0);
        joined.set(bodyBytes, payload.length);
        const digest = toHex(await hmacSha256(secret, joined));
        text = `Stripe-Signature: t=${ts},v1=${digest}\n\nt=${ts},v1=${digest}`;
      } else if (mode.value === "hmac-hex") {
        const digest = toHex(await hmacSha256(secret, bodyBytes));
        text = digest;
      } else {
        const digest = toBase64(await hmacSha256(secret, bodyBytes));
        text = digest;
      }
      output.textContent = text;
      result.hidden = false;
    } catch (err) {
      output.textContent = err instanceof Error ? err.message : String(err);
      result.hidden = false;
    }
  });

  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      const id = button.getAttribute("data-copy");
      const node = document.getElementById(id);
      if (!node) return;
      const value = node.innerText || node.textContent || "";
      try {
        await navigator.clipboard.writeText(value);
        const previous = button.textContent;
        button.textContent = "Copied";
        setTimeout(() => {
          button.textContent = previous;
        }, 1200);
      } catch {
        button.textContent = "Copy failed";
      }
    });
  });
})();
