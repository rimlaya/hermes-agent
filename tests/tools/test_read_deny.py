"""Tests for is_read_denied() — verifies read denylist blocks sensitive paths."""

import os
from pathlib import Path

from agent.file_safety import is_read_denied


class TestReadDenyExactPaths:
    def test_etc_shadow(self):
        assert is_read_denied("/etc/shadow") is True

    def test_etc_sudoers(self):
        assert is_read_denied("/etc/sudoers") is True

    def test_ssh_id_rsa(self):
        path = os.path.join(str(Path.home()), ".ssh", "id_rsa")
        assert is_read_denied(path) is True

    def test_ssh_id_ed25519(self):
        path = os.path.join(str(Path.home()), ".ssh", "id_ed25519")
        assert is_read_denied(path) is True

    def test_ssh_id_ecdsa(self):
        path = os.path.join(str(Path.home()), ".ssh", "id_ecdsa")
        assert is_read_denied(path) is True

    def test_netrc(self):
        path = os.path.join(str(Path.home()), ".netrc")
        assert is_read_denied(path) is True

    def test_pgpass(self):
        path = os.path.join(str(Path.home()), ".pgpass")
        assert is_read_denied(path) is True

    def test_npmrc(self):
        path = os.path.join(str(Path.home()), ".npmrc")
        assert is_read_denied(path) is True

    def test_pypirc(self):
        path = os.path.join(str(Path.home()), ".pypirc")
        assert is_read_denied(path) is True

    def test_hermes_env(self):
        from hermes_constants import get_hermes_home
        path = str(get_hermes_home() / ".env")
        assert is_read_denied(path) is True


class TestReadDenyPrefixes:
    def test_ssh_prefix(self):
        path = os.path.join(str(Path.home()), ".ssh", "some_key")
        assert is_read_denied(path) is True

    def test_aws_credentials(self):
        path = os.path.join(str(Path.home()), ".aws", "credentials")
        assert is_read_denied(path) is True

    def test_gnupg_prefix(self):
        path = os.path.join(str(Path.home()), ".gnupg", "secring.gpg")
        assert is_read_denied(path) is True

    def test_kube_prefix(self):
        path = os.path.join(str(Path.home()), ".kube", "config")
        assert is_read_denied(path) is True

    def test_docker_prefix(self):
        path = os.path.join(str(Path.home()), ".docker", "config.json")
        assert is_read_denied(path) is True

    def test_azure_prefix(self):
        path = os.path.join(str(Path.home()), ".azure", "accessTokens.json")
        assert is_read_denied(path) is True

    def test_gh_config_prefix(self):
        path = os.path.join(str(Path.home()), ".config", "gh", "hosts.yml")
        assert is_read_denied(path) is True

    def test_sudoers_d_prefix(self):
        assert is_read_denied("/etc/sudoers.d/custom") is True


class TestReadAllowed:
    def test_tmp_file(self):
        assert is_read_denied("/tmp/safe_file.json") is False

    def test_project_file(self):
        assert is_read_denied("/home/user/project/config.json") is False

    def test_hermes_config_not_env(self):
        # config.yaml is fine to read; only the .env inside HERMES_HOME is denied.
        path = os.path.join(str(Path.home()), ".hermes", "config.yaml")
        assert is_read_denied(path) is False

    def test_project_env_example(self):
        # .env.example templates are normal docs and stay readable.
        assert is_read_denied("/home/user/project/.env.example") is False

    def test_ssh_known_hosts_blocked_by_prefix(self):
        # known_hosts is not a credential per se but lives inside .ssh,
        # and the write side already denies the whole prefix; mirror that.
        path = os.path.join(str(Path.home()), ".ssh", "known_hosts")
        assert is_read_denied(path) is True
