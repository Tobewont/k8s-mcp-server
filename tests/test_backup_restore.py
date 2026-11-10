"""备份与恢复：资源原样 YAML 可以写回。"""
import copy
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.k8s_advanced.backup_restore import BackupRestoreMixin
from utils.backup_paths import list_backup_files, resolve_backup_file
from utils.resource_yaml import (
    ApplyConflict,
    ApplyNotFound,
    apply_manifest_ops,
    dumps_manifests,
    loads_manifests,
    prepare_for_write,
)


def _secret():
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": "db",
            "namespace": "prod",
            "labels": {"app": "yes"},
            "annotations": {
                "note": "2024-01-01T00:00:00Z",
                "plain": "keep-me",
            },
            "resourceVersion": "3",
            "uid": "uid-1",
            "generation": 2,
            "creationTimestamp": "2024-01-01T00:00:00Z",
            "managedFields": [{"manager": "kubectl", "time": "2024-01-01T00:00:00Z"}],
            "ownerReferences": [{"apiVersion": "v1", "kind": "ConfigMap", "name": "owner", "uid": "u"}],
        },
        "type": "Opaque",
        "data": {
            "password": "yes",
            "count": "0123",
            "token": "1234",
            "flag": "true",
            "empty": "",
            "padded": "eA==",
            "multiline": "line1\nline2\n",
            "json": '{"a": 1}',
            "space": " true ",
            "blob": "A" * 180 + "+/=",
        },
        "status": {"phase": "kept-in-file"},
    }


class BackupPathTest(unittest.TestCase):
    def test_list_timestamp_includes_date(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = os.path.join(directory, "demo", "namespaces", "prod", "resources", "secrets", "db")
            os.makedirs(folder)
            filename = "db_auto_20261109_171432.yaml"
            with open(os.path.join(folder, filename), "w", encoding="utf-8") as handle:
                handle.write("apiVersion: v1\n")
            listed = list_backup_files(directory)
            self.assertEqual(listed[0]["timestamp"], "20261109_171432")
            self.assertEqual(listed[0]["namespace"], "prod")
            self.assertEqual(listed[0]["resource_type"], "secrets")

    def test_resolve_rejects_path_outside_backup_dir(self):
        with tempfile.TemporaryDirectory() as directory:
            outside = os.path.join(directory, "outside.yaml")
            with open(outside, "w", encoding="utf-8") as handle:
                handle.write("x")
            backup_dir = os.path.join(directory, "backup")
            os.makedirs(backup_dir)
            with self.assertRaises(ValueError):
                resolve_backup_file(backup_dir, outside)


class YamlRoundTripTest(unittest.TestCase):
    def test_secret_values_survive_yaml(self):
        original = _secret()
        text = dumps_manifests([original])
        loaded = loads_manifests(text)
        self.assertEqual(loaded, [original])
        self.assertNotIn("decoded_data", text)

    def test_multi_document_order(self):
        first = _secret()
        second = copy.deepcopy(first)
        second["metadata"]["name"] = "other"
        second["data"] = {"n": "no", "off": "off", "date": "2024-01-01"}
        loaded = loads_manifests(dumps_manifests([first, second]))
        self.assertEqual([item["metadata"]["name"] for item in loaded], ["db", "other"])
        self.assertEqual(loaded[1]["data"]["n"], "no")
        self.assertEqual(loaded[1]["data"]["date"], "2024-01-01")

    def test_legacy_wrapper_is_rejected(self):
        text = "metadata:\n  cluster_name: demo\nresource:\n  decoded_data:\n    password: hunter2\n"
        with self.assertRaises(ValueError):
            loads_manifests(text)

    def test_prepare_keeps_data_and_drops_server_fields(self):
        original = _secret()
        body = prepare_for_write(original, "99")
        self.assertEqual(body["data"], original["data"])
        self.assertEqual(body["metadata"]["ownerReferences"], original["metadata"]["ownerReferences"])
        self.assertEqual(body["metadata"]["labels"]["app"], "yes")
        self.assertEqual(body["metadata"]["resourceVersion"], "99")
        self.assertNotIn("uid", body["metadata"])
        self.assertNotIn("managedFields", body["metadata"])
        self.assertNotIn("status", body)
        self.assertEqual(original["metadata"]["uid"], "uid-1")
        self.assertIn("status", original)

    def test_replace_uses_live_version_and_backup_data(self):
        backup = _secret()
        live = copy.deepcopy(backup)
        live["metadata"]["resourceVersion"] = "9"
        live["data"] = {"password": "new"}
        sent = {}

        def get_live():
            return copy.deepcopy(live)

        def create(_body):
            raise AssertionError("不应创建")

        def replace(body):
            sent["body"] = body

        action = apply_manifest_ops(backup, get_live, create, replace)
        self.assertEqual(action, "replaced")
        self.assertEqual(sent["body"]["data"]["password"], "yes")
        self.assertEqual(sent["body"]["metadata"]["resourceVersion"], "9")
        self.assertNotIn("status", sent["body"])
        self.assertEqual(backup["metadata"]["resourceVersion"], "3")

    def test_create_when_missing(self):
        backup = _secret()
        sent = {}

        def get_live():
            raise ApplyNotFound()

        def create(body):
            sent["body"] = body

        def replace(_body):
            raise AssertionError("不应替换")

        action = apply_manifest_ops(backup, get_live, create, replace)
        self.assertEqual(action, "created")
        self.assertNotIn("resourceVersion", sent["body"]["metadata"])
        self.assertEqual(sent["body"]["data"]["count"], "0123")

    def test_conflict_retries_once(self):
        backup = _secret()
        calls = {"n": 0}

        def get_live():
            return {"metadata": {"resourceVersion": "9"}}

        def create(_body):
            raise AssertionError("不应创建")

        def replace(body):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ApplyConflict()
            self.assertEqual(body["metadata"]["resourceVersion"], "9")

        self.assertEqual(apply_manifest_ops(backup, get_live, create, replace), "replaced")
        self.assertEqual(calls["n"], 2)

    def test_repeated_conflict_fails(self):
        def get_live():
            return {"metadata": {"resourceVersion": "9"}}

        def create(_body):
            raise AssertionError("不应创建")

        def replace(_body):
            raise ApplyConflict()

        with self.assertRaises(RuntimeError):
            apply_manifest_ops(_secret(), get_live, create, replace)


class _K8s:
    async def get_cluster_info(self):
        return {"cluster_name": "demo"}


class _Dynamic:
    def __init__(self, objects, discovered=None):
        self.objects = objects
        self.discovered = discovered or []
        self.applied = []
        self.fail_list = set()
        self.gets = []
        self.lists = []

    async def list_available_resources_async(self):
        return list(self.discovered)

    async def get_manifest_async(self, api_version, kind, name, namespace):
        self.gets.append((api_version, kind, name, namespace))
        if kind == "Namespace":
            return {
                "apiVersion": "v1",
                "kind": "Namespace",
                "metadata": {"name": name, "labels": {"env": "yes"}},
            }
        key = (kind, name)
        if key not in self.objects:
            raise RuntimeError(f"资源不存在: {kind}/{name}")
        return copy.deepcopy(self.objects[key])

    async def list_manifests_async(self, api_version, kind, namespace):
        self.lists.append((api_version, kind, namespace))
        if kind in self.fail_list:
            raise RuntimeError(f"列出 {kind} 失败")
        if kind == "Ingress":
            raise ValueError(f"未找到资源: {api_version}/{kind}")
        return [
            copy.deepcopy(obj)
            for obj in self.objects.values()
            if obj.get("kind") == kind and obj.get("metadata", {}).get("namespace") == namespace
        ]

    async def apply_manifest_async(self, manifest):
        self.applied.append(copy.deepcopy(manifest))
        return "replaced"


class BackupServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.secret = _secret()
        self.secret["metadata"]["namespace"] = "prod"
        generated = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "kube-root-ca.crt", "namespace": "prod"},
            "data": {"ca.crt": "cert"},
        }
        user_cm = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "app", "namespace": "prod"},
            "data": {"mode": "yes"},
        }
        self.dynamic = _Dynamic({
            ("Secret", "db"): self.secret,
            ("ConfigMap", "kube-root-ca.crt"): generated,
            ("ConfigMap", "app"): user_cm,
        })
        self.service = BackupRestoreMixin()
        self.service.backup_dir = self.tmp.name
        self.service.k8s_service = _K8s()
        self.service._dynamic_service = self.dynamic

    def tearDown(self):
        self.tmp.cleanup()

    def test_resource_backup_file_is_the_api_object(self):
        path = self._run(self.service.backup_specific_resource("secret", "db", "prod", "demo"))
        loaded = loads_manifests(self._read(path))
        self.assertEqual(loaded, [self.secret])
        self.assertIn("status", loaded[0])

    def test_namespace_backup_keeps_secret_data_and_skips_generated(self):
        info = self._run(self.service.backup_namespace("prod", "demo", True))
        loaded = loads_manifests(self._read(info["backup_file"]))
        names = [(item["kind"], item["metadata"]["name"]) for item in loaded]
        self.assertIn(("Namespace", "prod"), names)
        self.assertIn(("Secret", "db"), names)
        self.assertIn(("ConfigMap", "app"), names)
        self.assertNotIn(("ConfigMap", "kube-root-ca.crt"), names)
        secret = next(item for item in loaded if item["kind"] == "Secret")
        self.assertEqual(secret["data"]["password"], "yes")
        self.assertTrue(any(item["resource_type"] == "ingresses" for item in info["skipped"]))

    def test_namespace_backup_can_exclude_secrets(self):
        info = self._run(self.service.backup_namespace("prod", "demo", False))
        loaded = loads_manifests(self._read(info["backup_file"]))
        self.assertFalse(any(item["kind"] == "Secret" for item in loaded))

    def test_failed_list_does_not_write_backup(self):
        self.dynamic.fail_list.add("Secret")
        with self.assertRaises(RuntimeError):
            self._run(self.service.backup_namespace("prod", "demo", True))
        yaml_files = []
        for root, _dirs, files in os.walk(self.tmp.name):
            yaml_files.extend(name for name in files if name.endswith(".yaml"))
        self.assertEqual(yaml_files, [])

    def test_restore_sends_original_secret(self):
        path = self._run(self.service.backup_specific_resource("secret", "db", "prod", "demo"))
        result = self._run(self.service.restore_from_backup(path, "prod"))
        self.assertEqual(result["failed"], [])
        self.assertEqual(self.dynamic.applied[0]["data"], self.secret["data"])
        self.assertEqual(self.dynamic.applied[0]["metadata"]["resourceVersion"], "3")

    def test_restore_rejects_other_namespace(self):
        path = self._run(self.service.backup_specific_resource("secret", "db", "prod", "demo"))
        with self.assertRaises(ValueError):
            self._run(self.service.restore_from_backup(path, "other"))

    def test_rejects_name_that_escapes_backup_dir(self):
        with self.assertRaises(RuntimeError):
            self._run(self.service.backup_specific_resource("secret", "../db", "prod", "demo"))

    def test_backup_crd_by_api_version_and_restore(self):
        mysql = {
            "apiVersion": "db.example.com/v1",
            "kind": "MySQL",
            "metadata": {"name": "main", "namespace": "prod"},
            "spec": {"replicas": 2, "password": "yes"},
        }
        self.dynamic.objects[("MySQL", "main")] = mysql
        path = self._run(self.service.backup_specific_resource(
            "MySQL", "main", "prod", "demo", "db.example.com/v1"
        ))
        self.assertEqual(self.dynamic.gets[-1][0], "db.example.com/v1")
        loaded = loads_manifests(self._read(path))
        self.assertEqual(loaded, [mysql])
        result = self._run(self.service.restore_from_backup(path, "prod"))
        self.assertEqual(result["failed"], [])
        self.assertEqual(self.dynamic.applied[-1], mysql)

    def test_backup_crd_by_discovered_plural(self):
        mysql = {
            "apiVersion": "db.example.com/v1",
            "kind": "MySQL",
            "metadata": {"name": "main", "namespace": "prod"},
            "spec": {"storage": "10Gi"},
        }
        self.dynamic.objects[("MySQL", "main")] = mysql
        self.dynamic.discovered.append({
            "group_version": "db.example.com/v1beta1",
            "kind": "MySQL",
            "namespaced": True,
            "name": "mysqls",
            "preferred": False,
        })
        self.dynamic.discovered.append({
            "group_version": "db.example.com/v1",
            "kind": "MySQL",
            "namespaced": True,
            "name": "mysqls",
            "preferred": True,
        })
        path = self._run(self.service.backup_specific_resource("mysqls", "main", "prod", "demo"))
        self.assertEqual(self.dynamic.gets[-1][:2], ("db.example.com/v1", "MySQL"))
        self.assertEqual(loads_manifests(self._read(path)), [mysql])

    def test_backup_crd_plural_with_api_version(self):
        mysql = {
            "apiVersion": "db.example.com/v1",
            "kind": "MySQL",
            "metadata": {"name": "main", "namespace": "prod"},
            "spec": {"storage": "10Gi"},
        }
        self.dynamic.objects[("MySQL", "main")] = mysql
        self.dynamic.discovered.append({
            "group_version": "db.example.com/v1",
            "kind": "MySQL",
            "namespaced": True,
            "name": "mysqls",
            "preferred": True,
        })
        path = self._run(self.service.backup_specific_resource(
            "mysqls", "main", "prod", "demo", "db.example.com/v1"
        ))
        self.assertEqual(self.dynamic.gets[-1][:2], ("db.example.com/v1", "MySQL"))
        self.assertEqual(loads_manifests(self._read(path)), [mysql])

    def test_ambiguous_crd_kind_requires_api_version(self):
        self.dynamic.discovered.extend([
            {"group_version": "a.example.com/v1", "kind": "Widget", "namespaced": True, "name": "widgets", "preferred": True},
            {"group_version": "b.example.com/v1", "kind": "Widget", "namespaced": True, "name": "widgets", "preferred": True},
        ])
        with self.assertRaises(RuntimeError) as raised:
            self._run(self.service.backup_specific_resource("Widget", "main", "prod", "demo"))
        self.assertIn("api_version", str(raised.exception))

    def test_namespace_backup_includes_namespaced_crd_only(self):
        mysql = {
            "apiVersion": "db.example.com/v1",
            "kind": "MySQL",
            "metadata": {"name": "main", "namespace": "prod"},
            "spec": {"password": "0123"},
        }
        cluster = {
            "apiVersion": "db.example.com/v1",
            "kind": "ClusterDB",
            "metadata": {"name": "global"},
            "spec": {"mode": "yes"},
        }
        self.dynamic.objects[("MySQL", "main")] = mysql
        self.dynamic.objects[("ClusterDB", "global")] = cluster
        self.dynamic.discovered.extend([
            {"group_version": "db.example.com/v1", "kind": "MySQL", "namespaced": True, "name": "mysqls", "preferred": True},
            {"group_version": "db.example.com/v1beta1", "kind": "MySQL", "namespaced": True, "name": "mysqls", "preferred": False},
            {"group_version": "db.example.com/v1", "kind": "ClusterDB", "namespaced": False, "name": "clusterdbs", "preferred": True},
            {"group_version": "apps/v1", "kind": "Deployment", "namespaced": True, "name": "deployments", "preferred": True},
        ])
        info = self._run(self.service.backup_namespace("prod", "demo", True))
        loaded = loads_manifests(self._read(info["backup_file"]))
        names = [(item["kind"], item["metadata"]["name"]) for item in loaded]
        self.assertIn(("MySQL", "main"), names)
        self.assertNotIn(("ClusterDB", "global"), names)
        mysql_lists = [item for item in self.dynamic.lists if item[1] == "MySQL"]
        self.assertEqual(mysql_lists, [("db.example.com/v1", "MySQL", "prod")])
        saved = next(item for item in loaded if item["kind"] == "MySQL")
        self.assertEqual(saved["spec"]["password"], "0123")

    def test_crd_read_failure_does_not_write_backup(self):
        self.dynamic.discovered.append({
            "group_version": "db.example.com/v1",
            "kind": "MySQL",
            "namespaced": True,
            "name": "mysqls",
            "preferred": True,
        })
        self.dynamic.fail_list.add("MySQL")
        with self.assertRaises(RuntimeError):
            self._run(self.service.backup_namespace("prod", "demo", True))
        yaml_files = []
        for root, _dirs, files in os.walk(self.tmp.name):
            yaml_files.extend(name for name in files if name.endswith(".yaml"))
        self.assertEqual(yaml_files, [])

    def test_service_fields_survive_yaml(self):
        service = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": "web", "namespace": "prod"},
            "spec": {
                "type": "NodePort",
                "clusterIP": "10.96.0.12",
                "clusterIPs": ["10.96.0.12"],
                "selector": {"app": "web"},
                "ports": [{"port": 80, "targetPort": 8080, "nodePort": 30080, "protocol": "TCP"}],
            },
        }
        loaded = loads_manifests(dumps_manifests([service]))
        self.assertEqual(loaded[0]["spec"]["clusterIP"], "10.96.0.12")
        self.assertEqual(loaded[0]["spec"]["ports"][0]["nodePort"], 30080)
        body = prepare_for_write(loaded[0], "5")
        self.assertEqual(body["spec"]["clusterIP"], "10.96.0.12")
        self.assertEqual(body["spec"]["ports"][0]["nodePort"], 30080)

    def _read(self, path):
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def _run(self, coro):
        import asyncio
        return asyncio.run(coro)


class WriteAbortTest(unittest.TestCase):
    def test_update_stops_when_backup_fails(self):
        from tools.batch_tools import batch_update_resources

        service = _AbortService(failed=True)

        async def scenario():
            with _patch_service(service):
                raw = await batch_update_resources(
                    json.dumps([{"kind": "Secret", "metadata": {"name": "db"}}]),
                    namespace="prod",
                )
            return json.loads(raw)

        data = self._run(scenario())
        self.assertFalse(data["success"])
        self.assertIn("已中止写操作", data["error"])
        self.assertFalse(service.updated)
        self.assertEqual(data["auto_backup"]["backup_failed"][0]["name"], "db")

    def test_update_proceeds_after_backup(self):
        from tools.batch_tools import batch_update_resources

        service = _AbortService(failed=False)

        async def scenario():
            with _patch_service(service):
                raw = await batch_update_resources(
                    json.dumps([{"kind": "Secret", "metadata": {"name": "db"}}]),
                    namespace="prod",
                )
            return json.loads(raw)

        data = self._run(scenario())
        self.assertTrue(data["success"])
        self.assertTrue(service.updated)
        self.assertEqual(data["auto_backup"]["backed_up"][0]["backup_file"], "db.yaml")

    def _run(self, coro):
        import asyncio
        return asyncio.run(coro)


class _AbortService:
    def __init__(self, failed):
        self.failed = failed
        self.updated = False

    async def auto_backup_resources(self, resources, namespace):
        if self.failed:
            return {"backed_up": [], "backup_failed": [{"kind": "Secret", "name": "db", "error": "读取失败"}]}
        return {"backed_up": [{"kind": "Secret", "name": "db", "backup_file": "db.yaml"}], "backup_failed": []}

    async def batch_update_resources(self, resources, namespace):
        self.updated = True
        return {"success": [{"name": "db", "kind": "secret"}], "failed": [], "total": 1}


class _patch_service:
    def __init__(self, service):
        self.service = service
        self.patches = []

    def __enter__(self):
        from unittest.mock import patch
        self.patches = [
            patch("tools.batch_tools.get_k8s_advanced_service", return_value=self.service),
            patch("tools.batch_tools.resolve_kubeconfig_path", return_value=None),
            patch("tools.batch_tools.log_operation"),
        ]
        for item in self.patches:
            item.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        for item in reversed(self.patches):
            item.stop()
        return False


if __name__ == "__main__":
    unittest.main()
