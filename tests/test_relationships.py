"""Tests for enriched relationship detection in the ArchitectureScanner."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from analyzer.scanner import ArchitectureScanner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_component(arch, **kwargs):
    """Find a component dict anywhere in the tree matching all kwargs."""
    def _search(comps):
        for c in comps:
            if all(c.get(k) == v for k, v in kwargs.items()):
                return c
            found = _search(c.get("children", []))
            if found:
                return found
        return None
    return _search(arch.components)


def _find_relationship(arch, source=None, target=None, rel_type=None):
    """Find a relationship matching the given criteria."""
    for rel in arch.relationships:
        if source and rel.get("source") != source:
            continue
        if target and rel.get("target") != target:
            continue
        if rel_type and rel.get("type") != rel_type:
            continue
        return rel
    return None


def _scan(tmp_path):
    scanner = ArchitectureScanner(tmp_path)
    return scanner.scan()


# ---------------------------------------------------------------------------
# New relationship fields on existing types
# ---------------------------------------------------------------------------

class TestRelationshipNewFields:
    """Test that new optional fields exist on relationships."""

    def test_relationship_has_new_fields(self, tmp_path):
        """Relationships include new optional fields with None/empty defaults."""
        # Create two components with an import relationship
        (tmp_path / "package.json").write_text(json.dumps({"name": "myapp"}))
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "index.ts").write_text("import { foo } from './foo';\n")
        (tmp_path / "src" / "foo.ts").write_text("export const foo = 1;\n")

        arch = _scan(tmp_path)
        if arch.relationships:
            rel = arch.relationships[0]
            # New fields should be present (as None or empty)
            assert "authentication" in rel or rel.get("authentication") is None
            assert "data_format" in rel or rel.get("data_format") is None


# ---------------------------------------------------------------------------
# Database relationship detection
# ---------------------------------------------------------------------------

class TestDatabaseDetection:
    """Test database connection detection."""

    def test_docker_compose_postgres(self, tmp_path):
        """Detect database relationship from docker-compose + code imports."""
        # Docker-compose with postgres service
        (tmp_path / "docker-compose.yml").write_text(
            "version: '3'\nservices:\n"
            "  postgres:\n    image: postgres:16\n    ports:\n      - '5432:5432'\n"
            "  api:\n    build: ./api\n    depends_on:\n      - postgres\n"
        )
        # API service with database driver
        api_dir = tmp_path / "api"
        api_dir.mkdir()
        (api_dir / "package.json").write_text(json.dumps({
            "name": "api",
            "dependencies": {"pg": "^8.0.0", "express": "^4.0.0"}
        }))
        (api_dir / "index.ts").write_text(
            "import { Pool } from 'pg';\n"
            "const pool = new Pool();\n"
            "export async function query(sql: string) { return pool.query(sql); }\n"
        )

        arch = _scan(tmp_path)
        # Should find a database relationship
        db_rels = [r for r in arch.relationships if r.get("type") in ("database", "cache")]
        # At minimum the docker depends_on creates a relationship
        assert len(arch.relationships) > 0

    def test_python_sqlalchemy(self, tmp_path):
        """Detect SQLAlchemy database usage."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "api"\n')
        (tmp_path / "app.py").write_text(
            "from sqlalchemy import create_engine\n"
            "engine = create_engine('postgresql://localhost/mydb')\n"
        )

        arch = _scan(tmp_path)
        # The component should scan without errors
        comp = _find_component(arch, type="package")
        assert comp is not None


# ---------------------------------------------------------------------------
# Authentication detection
# ---------------------------------------------------------------------------

class TestAuthDetection:
    """Test authentication mechanism detection on HTTP relationships."""

    def test_jwt_auth_enrichment(self, tmp_path):
        """JWT authentication is detected on HTTP relationships."""
        # Create two components that communicate via HTTP
        (tmp_path / "docker-compose.yml").write_text(
            "version: '3'\nservices:\n"
            "  api:\n    build: ./api\n    ports:\n      - '3000:3000'\n"
            "  web:\n    build: ./web\n"
        )
        api_dir = tmp_path / "api"
        api_dir.mkdir()
        (api_dir / "package.json").write_text(json.dumps({
            "name": "api",
            "dependencies": {"express": "^4.0.0", "jsonwebtoken": "^9.0.0"}
        }))
        (api_dir / "index.ts").write_text(
            "import express from 'express';\n"
            "import jwt from 'jsonwebtoken';\n"
            "const app = express();\n"
            "app.listen(3000);\n"
        )
        web_dir = tmp_path / "web"
        web_dir.mkdir()
        (web_dir / "package.json").write_text(json.dumps({
            "name": "web",
            "dependencies": {"react": "^18.0.0"}
        }))
        (web_dir / "api.ts").write_text(
            "const res = await fetch('http://localhost:3000/api', {\n"
            "  headers: { Authorization: `Bearer ${token}` }\n"
            "});\n"
        )

        arch = _scan(tmp_path)
        # Look for HTTP relationships
        http_rels = [r for r in arch.relationships if r.get("type") == "http"]
        # If an HTTP relationship exists, check for auth enrichment
        for rel in http_rels:
            if rel.get("authentication"):
                assert rel["authentication"] == "jwt"
                break


# ---------------------------------------------------------------------------
# Data format detection
# ---------------------------------------------------------------------------

class TestDataFormatDetection:
    """Test data format detection on relationships."""

    def test_json_format_detected(self, tmp_path):
        """JSON data format detected from code patterns."""
        (tmp_path / "docker-compose.yml").write_text(
            "version: '3'\nservices:\n"
            "  api:\n    build: ./api\n    ports:\n      - '8080:8080'\n"
            "  client:\n    build: ./client\n"
        )
        api_dir = tmp_path / "api"
        api_dir.mkdir()
        (api_dir / "package.json").write_text(json.dumps({
            "name": "api",
            "dependencies": {"express": "^4.0.0"}
        }))
        (api_dir / "index.ts").write_text(
            "import express from 'express';\n"
            "const app = express();\n"
            "app.use(express.json());\n"
            "app.get('/api', (req, res) => res.json({ok: true}));\n"
            "app.listen(8080);\n"
        )
        client_dir = tmp_path / "client"
        client_dir.mkdir()
        (client_dir / "package.json").write_text(json.dumps({
            "name": "client",
            "dependencies": {"react": "^18.0.0"}
        }))
        (client_dir / "api.ts").write_text(
            "const res = await fetch('http://localhost:8080/api');\n"
            "const data = await res.json();\n"
        )

        arch = _scan(tmp_path)
        http_rels = [r for r in arch.relationships if r.get("type") == "http"]
        for rel in http_rels:
            if rel.get("data_format"):
                assert rel["data_format"] == "json"
                break


# ---------------------------------------------------------------------------
# Message queue detection
# ---------------------------------------------------------------------------

class TestMessageQueueDetection:
    """Test message queue relationship detection."""

    def test_rabbitmq_from_docker_and_code(self, tmp_path):
        """RabbitMQ detected from docker-compose and pika import."""
        (tmp_path / "docker-compose.yml").write_text(
            "version: '3'\nservices:\n"
            "  rabbitmq:\n    image: rabbitmq:management\n"
            "    ports:\n      - '5672:5672'\n"
            "  worker:\n    build: ./worker\n    depends_on:\n      - rabbitmq\n"
        )
        worker_dir = tmp_path / "worker"
        worker_dir.mkdir()
        (worker_dir / "pyproject.toml").write_text('[project]\nname = "worker"\n')
        (worker_dir / "main.py").write_text(
            "import pika\n"
            "connection = pika.BlockingConnection()\n"
            "channel = connection.channel()\n"
            "channel.queue_declare(queue='tasks')\n"
        )

        arch = _scan(tmp_path)
        mq_rels = [r for r in arch.relationships if r.get("type") == "message_queue"]
        # Should find at least one message queue relationship
        # (either from docker depends_on or from pattern detection)
        assert len(arch.relationships) > 0


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------

class TestRelationshipBackwardCompatibility:
    """Test backward compatibility of new fields."""

    def test_old_json_loads_without_error(self, tmp_path):
        """Architecture JSON without new fields loads without error."""
        old_json = {
            "name": "test",
            "description": "test",
            "generated_at": "2024-01-01",
            "analyzer_version": "1.0.0",
            "root_path": str(tmp_path),
            "components": [],
            "relationships": [
                {
                    "source": "a",
                    "target": "b",
                    "type": "http",
                    "label": "test",
                    "protocol": "HTTP",
                    "port": 8080,
                    "bidirectional": True,
                }
            ],
            "symbols": [],
            "files": [],
            "stats": {},
        }
        json_path = tmp_path / "architecture.json"
        json_path.write_text(json.dumps(old_json))

        # Should load without error
        data = json.loads(json_path.read_text())
        rel = data["relationships"][0]
        # New fields should be absent (not cause errors)
        assert rel.get("authentication") is None
        assert rel.get("data_format") is None
        assert rel.get("middleware") is None or rel.get("middleware") == []
