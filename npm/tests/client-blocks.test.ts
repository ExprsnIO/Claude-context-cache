/**
 * Tests for `buildSystemBlocks` cache-control placement.
 *
 * The placement and admission rules drive whether `ccc ask` actually
 * benefits from prompt caching. These tests lock the rules in:
 *
 * 1. The `cache_control` marker sits on the LAST block, never on the
 *    user message — Anthropic walks the prefix top-to-bottom, so a
 *    marker below volatile content produces zero cache hits.
 * 2. Prefixes shorter than the API's minimum-cacheable-tokens floor
 *    skip the marker entirely, since the 25% cache-write premium
 *    would never amortize.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  MIN_CACHE_PREFIX_CHARS,
  buildSystemBlocks,
  type SystemBlock,
} from "../src/client.js";

const hasMarker = (block: SystemBlock): boolean =>
  block.cache_control?.type === "ephemeral";

test("marker on last block when topic is present and prefix clears the floor", () => {
  const base = "x".repeat(Math.floor(MIN_CACHE_PREFIX_CHARS / 2));
  const topic = "y".repeat(Math.floor(MIN_CACHE_PREFIX_CHARS / 2) + 1);
  const blocks = buildSystemBlocks(base, topic);
  assert.equal(blocks.length, 2);
  assert.equal(hasMarker(blocks[0]!), false);
  assert.equal(hasMarker(blocks[1]!), true);
});

test("marker on the only block when no topic but prefix is long enough", () => {
  const base = "x".repeat(MIN_CACHE_PREFIX_CHARS + 1);
  const blocks = buildSystemBlocks(base, "");
  assert.equal(blocks.length, 1);
  assert.equal(hasMarker(blocks[0]!), true);
});

test("no marker when prefix is below the floor with topic", () => {
  const blocks = buildSystemBlocks("x".repeat(100), "y".repeat(100));
  assert.equal(blocks.length, 2);
  assert.equal(blocks.some(hasMarker), false);
});

test("no marker when prefix is below the floor without topic", () => {
  const blocks = buildSystemBlocks("tiny prompt", "");
  assert.equal(blocks.length, 1);
  assert.equal(hasMarker(blocks[0]!), false);
});
