"use strict";

const { isAbsolute, parse, resolve } = require("node:path");
const { statSync } = require("node:fs");
const { globSync: maintainedGlobSync, isDynamicPattern } = require("tinyglobby");

// Only the pinned Next lint plugin's root-directory lookup is supported. This
// is not a general fast-glob implementation or a runtime upload/URL resolver.
function globSync(pattern, options) {
  if (typeof pattern !== "string" || !pattern || pattern.length > 2048 || pattern.includes("\0")) {
    throw new TypeError("Invalid lint root pattern");
  }
  if (!options || options.onlyDirectories !== true || Object.keys(options).some((key) => key !== "onlyDirectories")) {
    throw new TypeError("Unsupported lint glob options; review the Next plugin integration");
  }
  let depth = 0;
  for (let index = 0; index < pattern.length; index += 1) {
    if (pattern[index] === "\\") { index += 1; continue; }
    if ("{([".includes(pattern[index])) depth += 1;
    if ("})]".includes(pattern[index])) depth = Math.max(0, depth - 1);
    if (depth > 16) throw new TypeError("Lint root pattern nesting exceeds the safety limit");
  }
  // A literal equal to cwd normalizes to an empty matcher in tinyglobby. Resolve
  // literal directories directly, just as fast-glob's static-path branch does.
  if (!isDynamicPattern(pattern)) {
    try {
      if (!statSync(resolve(pattern)).isDirectory()) return [];
    } catch (error) {
      if (error.code === "ENOENT" || error.code === "ENOTDIR") return [];
      throw error;
    }
    return [pattern === parse(pattern).root ? pattern : pattern.replace(/\/$/, "")];
  }
  return maintainedGlobSync(pattern, {
    onlyDirectories: true,
    expandDirectories: false,
    // fast-glob retains absolute patterns as absolute results. tinyglobby does
    // not do that by default, and expands literal directories unless disabled.
    absolute: isAbsolute(pattern),
  }).map((entry) => entry === parse(entry).root ? entry : entry.replace(/\/$/, ""));
}

module.exports = { globSync };
