import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT_DIR / "bin"
TARGET_EXE = BIN_DIR / "cloudflared.exe"
TARGET_LICENSE = BIN_DIR / "LICENSE-cloudflared.txt"

APACHE_2_LICENSE_TEXT = """                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   Copyright (c) Cloudflare, Inc.

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""


def get_latest_release_info():
    url = "https://api.github.com/repos/cloudflare/cloudflared/releases/latest"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "IssueSlipManager-Build/1.0"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data


def download_cloudflared(force: bool = False) -> bool:
    BIN_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Write License file
    with open(TARGET_LICENSE, "w", encoding="utf-8") as f:
        f.write(APACHE_2_LICENSE_TEXT)
    print(f"Created Apache 2.0 license notice at: {TARGET_LICENSE}")

    if TARGET_EXE.exists() and not force:
        print(f"cloudflared.exe already exists at: {TARGET_EXE}")
        return True

    print("Fetching latest cloudflared release information from GitHub...")
    try:
        release = get_latest_release_info()
        tag = release.get("tag_name", "latest")
        print(f"Latest release tag: {tag}")

        assets = release.get("assets", [])
        exe_asset = None
        sha_asset = None

        for a in assets:
            name = a["name"].lower()
            if name == "cloudflared-windows-amd64.exe":
                exe_asset = a
            elif "sha256" in name and ("windows-amd64" in name or "checksum" in name or name == "sha256sum.txt"):
                sha_asset = a

        if not exe_asset:
            print("Error: Could not find cloudflared-windows-amd64.exe in release assets!")
            return False

        exe_url = exe_asset["browser_download_url"]
        expected_sha256 = ""

        # Fetch checksum if available
        if sha_asset:
            try:
                sha_url = sha_asset["browser_download_url"]
                req = urllib.request.Request(sha_url, headers={"User-Agent": "IssueSlipManager-Build/1.0"})
                with urllib.request.urlopen(req, timeout=15) as s_resp:
                    content = s_resp.read().decode("utf-8")
                    for line in content.splitlines():
                        if "cloudflared-windows-amd64.exe" in line or (len(line.strip().split()) == 1 and len(line.strip()) == 64):
                            expected_sha256 = line.strip().split()[0].lower()
                            break
            except Exception as e:
                print(f"Warning: Could not fetch separate checksum file: {e}")

        print(f"Downloading {exe_url} ...")
        temp_download = TARGET_EXE.with_suffix(".tmp")
        req = urllib.request.Request(exe_url, headers={"User-Agent": "IssueSlipManager-Build/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(temp_download, "wb") as out:
            shutil_copy_chunks(resp, out)

        # Compute SHA-256
        hasher = hashlib.sha256()
        with open(temp_download, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        actual_sha256 = hasher.hexdigest().lower()
        print(f"Downloaded file SHA-256: {actual_sha256}")

        if expected_sha256:
            print(f"Expected SHA-256:        {expected_sha256}")
            if actual_sha256 != expected_sha256:
                temp_download.unlink(missing_ok=True)
                print("FATAL: SHA-256 checksum verification failed!")
                return False
            print("Checksum verified successfully.")

        if TARGET_EXE.exists():
            TARGET_EXE.unlink()
        temp_download.rename(TARGET_EXE)
        print(f"Saved verified binary to: {TARGET_EXE}")
        return True

    except Exception as exc:
        print(f"Download failed: {exc}")
        return False


def shutil_copy_chunks(src, dst):
    while True:
        chunk = src.read(65536)
        if not chunk:
            break
        dst.write(chunk)


if __name__ == "__main__":
    force_download = "--force" in sys.argv
    success = download_cloudflared(force=force_download)
    sys.exit(0 if success else 1)
