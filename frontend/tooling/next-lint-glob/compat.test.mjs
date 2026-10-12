import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";

import { ESLint } from "eslint";

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const require = createRequire(import.meta.url);
const pluginRequire = createRequire(require.resolve("@next/eslint-plugin-next"));
const glob = pluginRequire("fast-glob");
const { getRootDirs } = pluginRequire("./utils/get-root-dirs.js");
const fixture = mkdtempSync(path.join(os.tmpdir(), "next-lint-roots-"));
for (const name of ["web", "other app"]) {
  mkdirSync(path.join(fixture, name, "src", "app"), { recursive: true });
  writeFileSync(path.join(fixture, name, "src", "app", "page.tsx"), "export default function Page() { return null; }\n");
}
writeFileSync(path.join(fixture, "not-a-directory"), "owned test fixture\n");
after(() => rmSync(fixture, { recursive: true, force: true }));

test("only the pinned plugin resolves to the private maintained-library adapter", () => {
  assert.equal(pluginRequire("../package.json").version, "16.3.8");
  assert.equal(pluginRequire("fast-glob/package.json").name, "@multimodal-rag/next-lint-glob");
  const lock = JSON.parse(readFileSync(path.join(frontend, "package-lock.json"), "utf8"));
  assert.ok(!Object.keys(lock.packages).some((key) => /node_modules\/(braces|micromatch)$/.test(key)));
});

test("literal roots are not expanded and absolute/relative results retain their shape", () => {
  assert.deepEqual(glob.globSync(fixture, { onlyDirectories: true }), [fixture]);
  const relative = path.relative(process.cwd(), path.join(fixture, "web"));
  assert.deepEqual(glob.globSync(relative, { onlyDirectories: true }), [relative]);
  assert.deepEqual(glob.globSync(path.join(fixture, "not-a-directory"), { onlyDirectories: true }), []);
  assert.deepEqual(glob.globSync(path.join(fixture, "missing"), { onlyDirectories: true }), []);
});

test("upstream root resolution supports wildcard, brace, array and default settings", () => {
  const expected = [path.join(fixture, "web"), path.join(fixture, "other app")].sort();
  const context = (rootDir) => ({ cwd: frontend, settings: { next: { rootDir } } });
  assert.deepEqual(getRootDirs(context(path.join(fixture, "*"))).sort(), expected);
  assert.deepEqual(getRootDirs(context(path.join(fixture, "{web,other app}"))).sort(), expected);
  assert.deepEqual(getRootDirs(context([path.join(fixture, "web"), path.join(fixture, "other app")])).sort(), expected);
  assert.deepEqual(getRootDirs({ cwd: frontend, settings: {} }), [frontend]);
});

test("unsupported options and pathological patterns fail before crawling", () => {
  assert.throws(() => glob.globSync(fixture, { onlyDirectories: true, ignore: "*" }), /Unsupported/);
  assert.throws(() => glob.globSync("{".repeat(1000)+"x"+"}".repeat(1000), { onlyDirectories: true }), /nesting/);
  assert.throws(() => glob.globSync("x".repeat(2049), { onlyDirectories: true }), /Invalid/);
});

test("the real Next, TypeScript and accessibility rule presets remain active", async () => {
  const linter = new ESLint({ cwd: frontend, overrideConfig: [{ settings: { next: { rootDir: frontend } } }] });
  const filePath = path.join(frontend, "src", "app", "lint-compat-fixture.tsx");
  const messages = async (source) => (await linter.lintText(source, { filePath }))[0].messages;
  const badLink = await messages('export default function Fixture() { return <a href="/projects">Projects</a>; }');
  assert.ok(badLink.some((message) => message.ruleId === "@next/next/no-html-link-for-pages" && message.severity === 2));
  const goodLink = await messages('import Link from "next/link"; export default function Fixture() { return <Link href="/projects">Projects</Link>; }');
  assert.equal(goodLink.length, 0);
  const missingAlt = await messages('export default function Fixture() { return <img src="/fixture.png" />; }');
  assert.ok(missingAlt.some((message) => message.ruleId === "jsx-a11y/alt-text"));
  const unsafeType = await messages('export function Fixture(value: any) { return value; }');
  assert.ok(unsafeType.some((message) => message.ruleId === "@typescript-eslint/no-explicit-any"));
  const asyncClient = await messages('"use client"; export default async function Fixture() { return null; }');
  assert.ok(asyncClient.some((message) => message.ruleId === "@next/next/no-async-client-component"));
});
