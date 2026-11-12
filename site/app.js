(function () {
  "use strict";

  const form = document.getElementById("calc-form");
  const modeSelect = document.getElementById("mode");
  const algoField = document.getElementById("algo-field");
  const algoSelect = document.getElementById("algorithm");
  const tsField = document.getElementById("ts-field");
  const tsInput = document.getElementById("timestamp");
  const secretInput = document.getElementById("secret");
  const bodyInput = document.getElementById("body");
  const output = document.getElementById("result");
  const headerName = document.getElementById("header-name");
  const meta = document.getElementById("calc-meta");
  const vectorFact = document.getElementById("fact-vectors");
  const vectorList = document.getElementById("vector-list");
  const samples = document.getElementById("samples");

  const HEADER_NAMES = {
    github: "X-Hub-Signature-256",
    stripe: "Stripe-Signature",
    "hmac-hex": "Signature (hex)",
    "hmac-base64": "Signature (base64)",
  };

  let vectors = [];

  function syncMode() {
    const mode = modeSelect.value;
    tsField.hidden = mode !== "stripe";
    algoField.hidden = !mode.startsWith("hmac");
    headerName.textContent = HEADER_NAMES[mode];
  }

  async function update() {
    const mode = modeSelect.value;
    if (!secretInput.value) {
      output.textContent = "Enter a secret to see the signature.";
      meta.textContent = "";
      return;
    }
    try {
      const timestamp = tsInput.value.trim() || String(Math.floor(Date.now() / 1000));
      output.textContent = await window.WebhookSignatures.compute({
        mode,
        secret: secretInput.value,
        body: bodyInput.value,
        timestamp,
        algorithm: algoSelect.value,
      });
      meta.textContent =
        mode === "stripe" && !tsInput.value.trim()
          ? "No timestamp given, so the current time is used."
          : "";
    } catch (error) {
      output.textContent = "";
      meta.textContent = error instanceof Error ? error.message : String(error);
    }
  }

  function load(vector) {
    modeSelect.value = vector.mode;
    algoSelect.value = vector.algorithm;
    secretInput.value = vector.secret;
    bodyInput.value = vector.body;
    tsInput.value = vector.timestamp || "";
    syncMode();
    update();
  }

  async function checkVectors() {
    let data;
    try {
      data = await fetch("signature-vectors.json").then((response) => response.json());
    } catch {
      vectorFact.textContent = "unavailable";
      return;
    }
    vectors = data.cases;
    let passed = 0;
    vectorList.replaceChildren();
    for (const vector of vectors) {
      let actual = "";
      try {
        actual = await window.WebhookSignatures.compute(vector);
      } catch {
        actual = "";
      }
      const ok = actual === vector.expected;
      if (ok) passed += 1;
      const li = document.createElement("li");
      const tag = document.createElement("span");
      tag.className = "tag " + (ok ? "tag-ok" : "tag-no");
      tag.textContent = ok ? "match" : "differs";
      const text = document.createElement("span");
      text.textContent = vector.name;
      li.append(tag, text);
      vectorList.appendChild(li);

      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "chip";
      chip.textContent = vector.name;
      chip.addEventListener("click", () => load(vector));
      samples.appendChild(chip);
    }
    vectorFact.textContent = passed + " of " + vectors.length + " match";
  }

  [modeSelect, algoSelect].forEach((el) =>
    el.addEventListener("change", () => {
      syncMode();
      update();
    }),
  );
  [secretInput, bodyInput, tsInput].forEach((el) => el.addEventListener("input", update));
  form.addEventListener("submit", (event) => event.preventDefault());

  syncMode();
  update();
  checkVectors();
})();
