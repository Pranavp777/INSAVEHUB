/**
 * Zero-dependency Cloudflare build script invoked by `npm run build`.
 * Synchronizes static assets into ./dist/static and mirrors ./dist to ./public and ./build.
 * Runs in pure Node.js so Cloudflare builds never fail on missing Python C extensions (_sqlite3).
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, "..");
const distDir = path.join(rootDir, "dist");
const staticDir = path.join(rootDir, "static");

function copyRecursive(src, dest) {
  if (!fs.existsSync(src)) return;
  const stat = fs.statSync(src);
  if (stat.isDirectory()) {
    fs.mkdirSync(dest, { recursive: true });
    for (const entry of fs.readdirSync(src)) {
      copyRecursive(path.join(src, entry), path.join(dest, entry));
    }
  } else {
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.copyFileSync(src, dest);
  }
}

console.log("[INSTASAVE HUB Build] Syncing static assets into dist/static...");
fs.mkdirSync(distDir, { recursive: true });
copyRecursive(staticDir, path.join(distDir, "static"));

for (const alias of ["public", "build"]) {
  const aliasDir = path.join(rootDir, alias);
  copyRecursive(distDir, aliasDir);
}

console.log("[INSTASAVE HUB Build] Build completed successfully.");
