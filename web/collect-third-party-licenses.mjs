#!/usr/bin/env node

import { createHash } from "node:crypto";
import { existsSync, lstatSync, readFileSync, readdirSync, realpathSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";

const nodeModules = resolve(process.argv[2] || "node_modules");
const output = resolve(process.argv[3] || "THIRD_PARTY_LICENSES.txt");
const installLock = join(nodeModules, ".package-lock.json");
const installRoot = dirname(nodeModules);
const maxTextBytes = 2 * 1024 * 1024;

function fail(message) {
  throw new Error(`third-party license gate: ${message}`);
}

function inside(parent, child) {
  const rel = relative(parent, child);
  return rel === "" || (!rel.startsWith(`..${sep}`) && rel !== "..");
}

function regularText(file, packageDirectory) {
  const real = realpathSync(file);
  if (!inside(realpathSync(packageDirectory), real)) {
    fail(`license path escapes package directory: ${file}`);
  }
  const stat = lstatSync(file);
  if (!stat.isFile() || stat.isSymbolicLink()) {
    fail(`license artifact is not a regular file: ${file}`);
  }
  if (stat.size === 0 || stat.size > maxTextBytes) {
    fail(`license artifact has an invalid size: ${file}`);
  }
  const value = readFileSync(file, "utf8");
  if (value.includes("\uFFFD") || value.includes("\0")) {
    fail(`license artifact is not plain UTF-8 text: ${file}`);
  }
  return value.endsWith("\n") ? value : `${value}\n`;
}

function declaredLicense(packageJson, lockEntry) {
  const value = packageJson.license ?? lockEntry.license;
  if (typeof value === "string" && value.trim()) return value.trim();
  if (value && typeof value.type === "string" && value.type.trim()) return value.type.trim();
  return "NOASSERTION (see bundled license text)";
}

function licenseTexts(packageDirectory) {
  const names = readdirSync(packageDirectory)
    .filter((name) => /^(licen[cs]e|copying|notice)(\..*)?$/i.test(name))
    .sort((left, right) => left.localeCompare(right, "en"));
  if (names.length) {
    return names.map((name) => ({ source: name, text: regularText(join(packageDirectory, name), packageDirectory) }));
  }

  const readmes = readdirSync(packageDirectory)
    .filter((name) => /^readme(?:\..*)?$/i.test(name))
    .sort((left, right) => left.localeCompare(right, "en"));
  for (const name of readmes) {
    const readme = regularText(join(packageDirectory, name), packageDirectory);
    const marker = /^#{1,3}\s+licen[cs]e\s*$/im.exec(readme);
    if (marker) {
      const text = readme.slice(marker.index + marker[0].length).trim();
      if (text) return [{ source: `${name}#License`, text: `${text}\n` }];
    }
  }
  return [];
}

if (!existsSync(installLock)) fail(`${installLock} does not exist; run npm ci first`);
const lock = JSON.parse(readFileSync(installLock, "utf8"));
const packages = [];
const texts = new Map();

for (const [lockPath, lockEntry] of Object.entries(lock.packages || {})) {
  if (!lockPath || lockEntry.dev === true || !lockPath.startsWith("node_modules/")) continue;
  const packageDirectory = resolve(installRoot, lockPath);
  if (!inside(installRoot, packageDirectory)) fail(`invalid package-lock path: ${lockPath}`);
  const packageJsonPath = join(packageDirectory, "package.json");
  if (!existsSync(packageJsonPath)) {
    if (lockEntry.optional === true) continue;
    fail(`installed production package is missing: ${lockPath}`);
  }
  const packageJson = JSON.parse(readFileSync(packageJsonPath, "utf8"));
  const name = String(packageJson.name || lockPath.slice("node_modules/".length));
  const version = String(packageJson.version || lockEntry.version || "unknown");
  const artifacts = licenseTexts(packageDirectory);
  if (!artifacts.length) fail(`${name}@${version} does not carry a license or NOTICE text`);

  const hashes = [];
  for (const artifact of artifacts) {
    const hash = createHash("sha256").update(artifact.text, "utf8").digest("hex");
    hashes.push(hash);
    const record = texts.get(hash) || { text: artifact.text, consumers: [] };
    record.consumers.push(`${name}@${version} (${artifact.source})`);
    texts.set(hash, record);
  }
  packages.push({ name, version, license: declaredLicense(packageJson, lockEntry), hashes: [...new Set(hashes)].sort() });
}

packages.sort((left, right) => `${left.name}@${left.version}`.localeCompare(`${right.name}@${right.version}`, "en"));
if (!packages.length) fail("no installed production packages were found");

const lines = [
  "RTFM FRONTEND THIRD-PARTY LICENSES",
  "",
  "Generated deterministically from the production entries installed by package-lock.json.",
  "Do not edit this artifact by hand; change the lockfile or collector and rebuild.",
  "",
  `Production packages: ${packages.length}`,
  `Unique license/NOTICE texts: ${texts.size}`,
  "",
  "PACKAGE INVENTORY",
  "",
];

for (const item of packages) {
  lines.push(`${item.name}@${item.version} | declared=${item.license} | texts=${item.hashes.join(",")}`);
}

for (const [hash, record] of [...texts.entries()].sort(([left], [right]) => left.localeCompare(right))) {
  lines.push("", `===== BEGIN THIRD-PARTY TEXT sha256:${hash} =====`);
  lines.push(`Packages: ${record.consumers.sort((left, right) => left.localeCompare(right, "en")).join("; ")}`);
  lines.push("", record.text.trimEnd(), `===== END THIRD-PARTY TEXT sha256:${hash} =====`);
}

writeFileSync(output, `${lines.join("\n")}\n`, { encoding: "utf8", mode: 0o644 });
console.log(`wrote ${output}: ${packages.length} packages, ${texts.size} unique texts`);
