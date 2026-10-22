// Convert the checked-in PNG into macOS icon sizes. No image service is needed.
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

if (process.platform !== "darwin") throw new Error("Icon conversion requires macOS.");
const root = fileURLToPath(new URL("../", import.meta.url));
const temporary = mkdtempSync(join(tmpdir(), "wechat-emoji-icons-"));
const iconset = join(temporary, "app.iconset");
try {
  execFileSync("/bin/mkdir", [iconset]);
  for (const size of [16, 32, 128, 256, 512]) {
    for (const scale of [1, 2]) {
      const pixels = String(size * scale);
      const name = `icon_${size}x${size}${scale === 2 ? "@2x" : ""}.png`;
      execFileSync("/usr/bin/sips", ["-z", pixels, pixels, resolve(root, "desktop/assets/icon.png"), "--out", join(iconset, name)], { stdio: "ignore" });
    }
  }
  execFileSync("/usr/bin/iconutil", ["-c", "icns", iconset, "-o", resolve(root, "desktop/assets/icon.icns")]);
  console.log("Updated desktop/assets/icon.icns");
} finally {
  rmSync(temporary, { recursive: true, force: true });
}
