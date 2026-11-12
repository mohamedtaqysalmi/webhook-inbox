// Run with: node --test tests/js
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const { compute } = require("../../site/signature.js");
const { cases } = JSON.parse(readFileSync(new URL("../../site/signature-vectors.json", import.meta.url), "utf8"));

for (const vector of cases) {
  test(`browser code reproduces the Python vector: ${vector.name}`, async () => {
    assert.equal(await compute(vector), vector.expected);
  });
}

test("stripe mode rejects a non-numeric timestamp", async () => {
  await assert.rejects(compute({ mode: "stripe", secret: "k", body: "x", timestamp: "abc" }), /unix seconds/);
});

test("unknown hash is rejected", async () => {
  await assert.rejects(compute({ mode: "hmac-hex", secret: "k", body: "x", algorithm: "md5" }), /unsupported hash/);
});