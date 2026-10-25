#!/bin/sh

set -eu

python_bin="${PYTHON_BIN:-python3.14}"
stage_dir="$(mktemp -d)"
trap 'rm -rf "$stage_dir"' EXIT

case "$(uname -m)" in
    x86_64)
        msgpack_hash="0e2bf9280bceb5efca998435904b5d3e9fdbcc11d90dc9df30aec7973252b720" # pragma: allowlist secret -- public wheel integrity hash
        ;;
    aarch64)
        msgpack_hash="ca0dacff965c47afdc3749a8469d7302a8f801d6a28758d55120d75e66ce6889" # pragma: allowlist secret -- public wheel integrity hash
        ;;
    *)
        echo "Unsupported architecture for pinned msgpack wheel: $(uname -m)" >&2
        exit 1
        ;;
esac

cat > "$stage_dir/requirements.txt" <<EOF
certifi==2026.10.23 --hash=sha256:e9b54de76e530bb6cf0ccd036787103acb58fd42ba930ea8bf948ddbaa2f61d1
msgpack==1.2.1 --hash=sha256:${msgpack_hash}
setuptools==78.1.1 --hash=sha256:c3a9c4211ff4c309edb8b8c4f1cbfa7ae324c4ba9f91ff254e3d305b9fd54561
urllib3==2.8.0 --hash=sha256:0cf3cae568d36aa9576b28dfb35f11328f1cb974ca7647d9475ebb86c75ac6e3
EOF

"$python_bin" -m pip install \
    --disable-pip-version-check \
    --no-cache-dir \
    --no-deps \
    --only-binary=:all: \
    --require-hashes \
    --target "$stage_dir" \
    -r "$stage_dir/requirements.txt"

STAGE_DIR="$stage_dir" "$python_bin" - <<'PY'
import json
import os
import re
import shutil
from pathlib import Path

stage = Path(os.environ["STAGE_DIR"])
certifi_core = stage / "certifi" / "core.py"
source = certifi_core.read_text(encoding="utf-8")
for old, new in (
    ('files("certifi")', 'files("pip._vendor.certifi")'),
    ('get_path("certifi",', 'get_path("pip._vendor.certifi",'),
    ('read_text("certifi",', 'read_text("pip._vendor.certifi",'),
):
    if old not in source:
        raise SystemExit(f"unexpected certifi import-resource expression: {old}")
    source = source.replace(old, new)
certifi_core.write_text(source, encoding="utf-8")

urllib3_request = stage / "urllib3" / "util" / "request.py"
source = urllib3_request.read_text(encoding="utf-8")
brotli_block = re.compile(
    r"\ntry:\n"
    r"    try:\n"
    r"        import brotlicffi as _unused_module_brotli.*?\n"
    r"    except ImportError:\n"
    r"        import brotli as _unused_module_brotli.*?\n"
    r"except ImportError:\n"
    r"    pass\n"
    r"else:\n"
    r"    ACCEPT_ENCODING \+= \",br\"\n",
    flags=re.DOTALL,
)
source, count = brotli_block.subn("\n", source, count=1)
if count != 1:
    raise SystemExit("unexpected urllib3 brotli vendoring block")
urllib3_request.write_text(source, encoding="utf-8")

pkg_resources = stage / "pkg_resources" / "__init__.py"
source = pkg_resources.read_text(encoding="utf-8")

packaging_imports = """import packaging.markers
import packaging.requirements
import packaging.specifiers
import packaging.utils
import packaging.version
"""
patched_packaging_imports = """import pip._vendor.packaging as packaging
import pip._vendor.packaging.markers
import pip._vendor.packaging.requirements
import pip._vendor.packaging.specifiers
import pip._vendor.packaging.utils
import pip._vendor.packaging.version
"""
if packaging_imports not in source:
    raise SystemExit("unexpected setuptools pkg_resources packaging imports")
source = source.replace(packaging_imports, patched_packaging_imports, 1)

jaraco_import = "from jaraco.text import drop_comment, join_continuation, yield_lines"
patched_jaraco_import = "from pip._internal.utils._jaraco_text import drop_comment, join_continuation, yield_lines"
if jaraco_import not in source:
    raise SystemExit("unexpected setuptools pkg_resources jaraco import")
source = source.replace(jaraco_import, patched_jaraco_import, 1)

platformdirs_import = "from platformdirs import user_cache_dir as _user_cache_dir"
patched_platformdirs_import = "from pip._vendor.platformdirs import user_cache_dir as _user_cache_dir"
if platformdirs_import not in source:
    raise SystemExit("unexpected setuptools pkg_resources platformdirs import")
source = source.replace(platformdirs_import, patched_platformdirs_import, 1)

deprecation_warning = '''warnings.warn(
    "pkg_resources is deprecated as an API. "
    "See https://setuptools.pypa.io/en/latest/pkg_resources.html",
    DeprecationWarning,
    stacklevel=2,
)
'''
if deprecation_warning not in source:
    raise SystemExit("unexpected setuptools pkg_resources warning")
source = source.replace(
    deprecation_warning,
    "# pip vendors pkg_resources for its Python <3.11 metadata backend.\n",
    1,
)
pkg_resources.write_text(source, encoding="utf-8")

roots = sorted(
    {
        path.parent
        for parent in (Path("/app"), Path("/opt/app-root"))
        if parent.exists()
        for path in parent.glob("**/pip/_vendor/vendor.txt")
    }
)
if not roots:
    raise SystemExit("no pip vendor roots found")

versions = {
    "certifi": "2026.10.23",
    "msgpack": "1.2.1",
    "setuptools": "78.1.1",
    "urllib3": "2.8.0",
}
for root in roots:
    for package in ("certifi", "msgpack", "urllib3", "pkg_resources"):
        destination = root / package
        if destination.exists() or destination.is_symlink():
            if destination.is_dir() and not destination.is_symlink():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        ignore = shutil.ignore_patterns("tests", "api_tests.txt") if package == "pkg_resources" else None
        shutil.copytree(stage / package, destination, ignore=ignore)
        if package == "pkg_resources":
            assert not (destination / "tests").exists()
            assert not (destination / "api_tests.txt").exists()

    vendor_txt = root / "vendor.txt"
    lines = vendor_txt.read_text(encoding="utf-8").splitlines()
    replacements = {
        "certifi": f"certifi=={versions['certifi']}",
        "msgpack": f"msgpack=={versions['msgpack']}",
        "setuptools": f"setuptools=={versions['setuptools']}",
        "urllib3": f"urllib3=={versions['urllib3']}",
    }
    seen = set()
    for index, line in enumerate(lines):
        name = line.strip().split("==", 1)[0]
        if name in replacements:
            indent = line[: len(line) - len(line.lstrip())]
            lines[index] = indent + replacements[name]
            seen.add(name)
    if seen != set(replacements):
        raise SystemExit(f"vendor.txt package list mismatch in {vendor_txt}: {seen}")
    vendor_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    bom_path = root / "bom.cdx.json"
    bom = json.loads(bom_path.read_text(encoding="utf-8"))
    refs = {}
    for component in bom.get("components", []):
        name = component.get("name")
        if name in versions:
            old_ref = component.get("bom-ref")
            new_ref = f"pkg:pypi/{name}@{versions[name]}"
            if old_ref:
                refs[old_ref] = new_ref
            component["bom-ref"] = new_ref
            component["purl"] = new_ref
            component["version"] = versions[name]
    if len(refs) != len(versions):
        raise SystemExit(f"BOM package list mismatch in {bom_path}: {refs}")

    def replace_refs(value):
        if isinstance(value, dict):
            return {key: replace_refs(item) for key, item in value.items()}
        if isinstance(value, list):
            return [replace_refs(item) for item in value]
        return refs.get(value, value)

    bom_path.write_text(json.dumps(replace_refs(bom), indent=2) + "\n", encoding="utf-8")

    certifi_source = (root / "certifi" / "core.py").read_text(encoding="utf-8")
    assert 'files("pip._vendor.certifi")' in certifi_source
    assert 'get_path("pip._vendor.certifi",' in certifi_source
    assert 'read_text("pip._vendor.certifi",' in certifi_source
    urllib3_source = (root / "urllib3" / "util" / "request.py").read_text(encoding="utf-8")
    assert ",br" not in urllib3_source
    assert not (root / "pkg_resources" / "tests").exists()
    assert not (root / "pkg_resources" / "api_tests.txt").exists()
PY

"$python_bin" - <<'PY'
from pathlib import Path

from pip._vendor import certifi, msgpack, pkg_resources, urllib3

assert certifi.__version__ == "2026.10.23", certifi.__version__
assert msgpack.__version__ == "1.2.1", msgpack.__version__
assert urllib3.__version__ == "2.8.0", urllib3.__version__
assert "br" not in urllib3.util.request.ACCEPT_ENCODING, urllib3.util.request.ACCEPT_ENCODING
assert urllib3.util.request.ACCEPT_ENCODING in {"gzip,deflate", "gzip,deflate,zstd"}
assert Path(certifi.where()).as_posix().endswith("/pip/_vendor/certifi/cacert.pem"), certifi.where()
assert certifi.contents() == Path(certifi.where()).read_text(encoding="ascii")
assert str(pkg_resources.Requirement.parse("openxflow>=1")) == "openxflow>=1"
PY

"$python_bin" -m pip --version >/dev/null
