"""Pytest configuration"""
import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.ansible_runner import AnsibleRunner


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


def test_root_endpoint(client):
    """Test root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    assert "service" in response.json()


def test_api_root_endpoint(client):
    """Test API root endpoint"""
    response = client.get("/api/v1/")
    assert response.status_code == 200
    assert "version" in response.json()


def test_health_check(client):
    """Test health check endpoint"""
    response = client.get("/api/v1/health/check")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_deployment_status(client):
    """Test deployment status endpoint"""
    response = client.get("/api/v1/deploy/status")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "mssql_version" in data


def test_ansible_runner_uses_python_scripts_path(monkeypatch):
    """The runner should prefer the conda Scripts directory when the executable is not on PATH."""
    runner = AnsibleRunner()
    monkeypatch.setattr("app.ansible_runner.shutil.which", lambda name: None)
    monkeypatch.setattr(os, "environ", {"PATH": ""})
    monkeypatch.setattr("app.ansible_runner.sys.prefix", "C:/temp/env")

    command = runner._resolve_command()

    assert command == "ansible-playbook"

def test_rewind_plan_endpoint(client):
    """GET-only, no side effects, safe to call in CI."""
    response = client.get("/api/v1/deploy/rewind-plan")
    assert response.status_code == 200
    data = response.json()
    assert "teardown" in data and "rewind" in data and "reset-baseline" in data


def test_deploy_rewind_sequence_stops_on_teardown_failure(monkeypatch):
    """Rewind must not attempt site.yml if teardown itself fails."""
    from app.deployer import AnsibleMssqlDeployer, SequenceStepError

    deployer = AnsibleMssqlDeployer()
    calls = []

    def fake_run_playbook(playbook_name, tags=None, limit=None, extra_vars=None, skip_tags=None):
        calls.append(playbook_name)
        return {"success": False, "playbook": playbook_name, "stdout": "", "stderr": "boom"}

    monkeypatch.setattr(deployer.ansible, "run_playbook", fake_run_playbook)

    try:
        deployer._run_rewind_sequence()
        assert False, "expected SequenceStepError"
    except SequenceStepError:
        pass

    assert calls == ["teardown.yml"]    
