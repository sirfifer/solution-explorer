"""Config file parsers for metadata extraction."""

import json
import os
import re
from pathlib import Path


def parse_package_json(path: Path) -> dict:
    """Extract metadata from package.json."""
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        return {
            "name": data.get("name", path.parent.name),
            "description": data.get("description", ""),
            "version": data.get("version", ""),
            "dependencies": sorted(set(
                list(data.get("dependencies", {}).keys()) +
                list(data.get("devDependencies", {}).keys())
            )),
            "scripts": list(data.get("scripts", {}).keys()),
        }
    except (json.JSONDecodeError, OSError):
        return {}


def parse_cargo_toml(path: Path) -> dict:
    """Extract metadata from Cargo.toml (basic TOML parsing)."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        info = {"name": "", "description": "", "dependencies": []}

        # Extract package name
        m = re.search(r'^\[package\]\s*\n(?:.*\n)*?name\s*=\s*"([^"]+)"', content, re.MULTILINE)
        if m:
            info["name"] = m.group(1)

        # Extract dependencies
        in_deps = False
        for line in content.split("\n"):
            if re.match(r'\[(?:.*)?dependencies(?:\.\w+)?\]', line):
                in_deps = True
                continue
            if line.startswith("[") and in_deps:
                in_deps = False
            if in_deps:
                m = re.match(r'(\w[\w-]*)\s*=', line)
                if m:
                    info["dependencies"].append(m.group(1))
        return info
    except OSError:
        return {}


def parse_pyproject_toml(path: Path) -> dict:
    """Extract metadata from pyproject.toml."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        info = {"name": "", "description": "", "dependencies": []}
        m = re.search(r'name\s*=\s*"([^"]+)"', content)
        if m:
            info["name"] = m.group(1)
        # Extract deps
        for m in re.finditer(r'"([\w-]+)(?:[><=!~]|$)', content):
            dep = m.group(1)
            if dep not in ("python",):
                info["dependencies"].append(dep)
        return info
    except OSError:
        return {}


def parse_info_plist(path: Path) -> dict:
    """Parse Info.plist for app metadata using stdlib plistlib."""
    try:
        import plistlib
        with open(path, "rb") as f:
            plist = plistlib.load(f)
        name = plist.get("CFBundleDisplayName") or plist.get("CFBundleName") or ""
        # Reject build-time variable placeholders like $(PRODUCT_NAME)
        if name and ("$(" in name or "${" in name):
            name = ""
        return {
            "name": name,
            "bundle_id": plist.get("CFBundleIdentifier", ""),
        }
    except Exception:
        return {}


def _extract_ruby_app_name(base_dir: Path) -> str:
    """Try multiple strategies to find a Ruby/Rails app name from a directory."""
    # Strategy 1: config/application.rb (Rails convention)
    app_rb = base_dir / "config" / "application.rb"
    if app_rb.exists():
        try:
            content = app_rb.read_text(encoding="utf-8", errors="replace")
            m = re.search(r'module\s+(\w+)', content)
            if m:
                return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', m.group(1))
        except OSError:
            pass

    # Strategy 2: config.ru (Rack convention: run AppName::Application)
    config_ru = base_dir / "config.ru"
    if config_ru.exists():
        try:
            content = config_ru.read_text(encoding="utf-8", errors="replace")
            m = re.search(r'run\s+(\w+)::Application', content)
            if m:
                return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', m.group(1))
        except OSError:
            pass

    # Strategy 3: bin/rails or Rakefile mentioning the app
    rakefile = base_dir / "Rakefile"
    if rakefile.exists():
        try:
            content = rakefile.read_text(encoding="utf-8", errors="replace")
            m = re.search(r'(\w+)::Application\.load_tasks', content)
            if m:
                return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', m.group(1))
        except OSError:
            pass

    return ""


def parse_gemfile(path: Path) -> dict:
    """Parse Gemfile for Ruby dependencies and app name."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        gems = set()
        for m in re.finditer(r"""gem\s+['"]([^'"]+)['"]""", content):
            gems.add(m.group(1))
        name = _extract_ruby_app_name(path.parent)
        return {"name": name, "dependencies": list(gems)}
    except Exception:
        return {}


def parse_docker_compose(path: Path) -> dict:
    """Extract services from docker-compose.yml (basic YAML parsing)."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        services = []
        ports = []
        current_service = None
        in_services = False
        in_ports = False

        for line in content.split("\n"):
            if line.strip() == "services:":
                in_services = True
                continue
            if in_services and not line.startswith(" ") and line.strip() and not line.startswith("#"):
                in_services = False

            if in_services:
                # Service name (2-space indent)
                m = re.match(r'^  (\w[\w-]*):', line)
                if m:
                    current_service = m.group(1)
                    services.append(current_service)
                    in_ports = False

                if "ports:" in line:
                    in_ports = True
                    continue
                if in_ports and line.strip().startswith("-"):
                    port_match = re.search(r'(\d+):(\d+)', line)
                    if port_match:
                        ports.append({
                            "service": current_service,
                            "host": int(port_match.group(1)),
                            "container": int(port_match.group(2)),
                        })
                elif in_ports and not line.strip().startswith("-"):
                    in_ports = False

        return {"services": services, "ports": ports}
    except OSError:
        return {}


def parse_sam_template(path: Path) -> dict:
    """Extract Lambda functions and API info from AWS SAM template.yaml.

    Uses basic YAML line parsing (no external deps) to find
    AWS::Serverless::Function resources and their properties.
    """
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        functions = []
        current_resource = None
        current_type = None
        current_handler = None
        current_runtime = None
        current_code_uri = None
        in_resources = False

        for line in content.split("\n"):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            if stripped == "Resources:":
                in_resources = True
                continue

            if in_resources and not line.startswith(" ") and stripped.endswith(":"):
                # New top-level section, end of Resources
                in_resources = False
                continue

            if not in_resources:
                continue

            # Resource name (2-space indent under Resources)
            m = re.match(r'^  (\w[\w-]*):', line)
            if m:
                # Save previous resource if it was a Lambda function
                if current_resource and current_type and "Function" in current_type:
                    functions.append({
                        "name": current_resource,
                        "runtime": current_runtime or "",
                        "handler": current_handler or "",
                        "code_uri": current_code_uri or "",
                    })
                current_resource = m.group(1)
                current_type = None
                current_handler = None
                current_runtime = None
                current_code_uri = None
                continue

            if "Type:" in stripped:
                m = re.search(r'Type:\s*(.+)', stripped)
                if m:
                    current_type = m.group(1).strip()

            if "Handler:" in stripped:
                m = re.search(r'Handler:\s*(.+)', stripped)
                if m:
                    current_handler = m.group(1).strip()

            if "Runtime:" in stripped:
                m = re.search(r'Runtime:\s*(.+)', stripped)
                if m:
                    current_runtime = m.group(1).strip()

            if "CodeUri:" in stripped:
                m = re.search(r'CodeUri:\s*(.+)', stripped)
                if m:
                    current_code_uri = m.group(1).strip()

        # Save last resource
        if current_resource and current_type and "Function" in current_type:
            functions.append({
                "name": current_resource,
                "runtime": current_runtime or "",
                "handler": current_handler or "",
                "code_uri": current_code_uri or "",
            })

        # Detect API Gateway
        has_api = bool(re.search(r'AWS::Serverless::Api|AWS::ApiGateway', content))

        return {
            "functions": functions,
            "has_api_gateway": has_api,
            "type": "sam",
        }
    except OSError:
        return {}


def parse_serverless_yml(path: Path) -> dict:
    """Extract function info from serverless.yml (Serverless Framework)."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        functions = []
        in_functions = False
        current_fn = None

        for line in content.split("\n"):
            stripped = line.strip()
            if stripped == "functions:":
                in_functions = True
                continue
            if in_functions and not line.startswith(" ") and stripped.endswith(":"):
                in_functions = False
                continue
            if not in_functions:
                continue
            m = re.match(r'^  (\w[\w-]*):', line)
            if m:
                current_fn = m.group(1)
                functions.append({"name": current_fn})

        provider = ""
        m = re.search(r'provider:\s*\n\s+name:\s*(\w+)', content)
        if m:
            provider = m.group(1)

        return {"functions": functions, "provider": provider, "type": "serverless"}
    except OSError:
        return {}
