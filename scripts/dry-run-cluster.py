#!/usr/bin/env python3
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
K3S_ROOT = SCRIPT_DIR.parent
APPS_DIR = K3S_ROOT / "argocd" / "overlays" / "base"


def load_applications():
    apps = []
    for path in sorted(APPS_DIR.glob("*.yaml")):
        if path.name == "kustomization.yaml":
            continue
        doc = yaml.safe_load(path.read_text())
        if not doc or doc.get("kind") != "Application":
            continue
        apps.append((path, doc))
    return apps


def classify(doc):
    spec = doc["spec"]
    namespace = spec["destination"]["namespace"]
    if "sources" in spec:
        chart_source = next(s for s in spec["sources"] if "chart" in s)
        value_files = chart_source.get("helm", {}).get("valueFiles", [])
        values = [K3S_ROOT / vf.replace("$values/", "") for vf in value_files]
        return {
            "type": "helm",
            "repoURL": chart_source["repoURL"],
            "chart": chart_source["chart"],
            "version": chart_source["targetRevision"],
            "values": values,
            "namespace": namespace,
        }
    source = spec["source"]
    return {
        "type": "kustomize",
        "path": K3S_ROOT / source["path"],
        "namespace": namespace,
    }


def repo_alias(url):
    netloc = urlparse(url).netloc or url
    return re.sub(r"[^a-z0-9]+", "-", netloc.lower()).strip("-")


def ensure_helm_repos(apps):
    aliases = {}
    for _, doc in apps:
        info = classify(doc)
        if info["type"] != "helm":
            continue
        url = info["repoURL"]
        if url in aliases:
            continue
        alias = repo_alias(url)
        aliases[url] = alias
        subprocess.run(
            ["helm", "repo", "add", alias, url, "--force-update"],
            capture_output=True, text=True,
        )
    if aliases:
        subprocess.run(["helm", "repo", "update", *aliases.values()], capture_output=True, text=True)


def run_helm(name, info):
    cmd = [
        "helm", "template", name, f"{repo_alias(info['repoURL'])}/{info['chart']}",
        "--version", info["version"],
        "--namespace", info["namespace"],
    ]
    for vf in info["values"]:
        cmd += ["-f", str(vf)]
    label = f"{info['chart']}@{info['version']}"
    return label, subprocess.run(cmd, capture_output=True, text=True)


def run_kustomize(name, info):
    cmd = ["kustomize", "build", str(info["path"])]
    label = str(info["path"].relative_to(K3S_ROOT))
    return label, subprocess.run(cmd, capture_output=True, text=True)


def run_kubeconform(rendered):
    if shutil.which("kubeconform") is None:
        return None
    cmd = ["kubeconform", "-strict", "-ignore-missing-schemas", "-summary"]
    return subprocess.run(cmd, input=rendered, capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser(description="dry-run render every ArgoCD Application in this repo")
    parser.add_argument("--only", help="check a single application by name")
    parser.add_argument("--verbose", action="store_true", help="print rendered output summary even on success")
    parser.add_argument("--kubeconform", action="store_true", help="also validate rendered manifests against k8s schemas")
    args = parser.parse_args()

    apps = load_applications()
    if not apps:
        print(f"no Application manifests found under {APPS_DIR}")
        sys.exit(2)

    ensure_helm_repos(apps)

    results = []
    for path, doc in apps:
        name = doc["metadata"]["name"]
        if args.only and args.only != name:
            continue
        info = classify(doc)
        if info["type"] == "helm":
            label, result = run_helm(name, info)
        else:
            label, result = run_kustomize(name, info)

        ok = result.returncode == 0
        kind_count = sum(1 for line in result.stdout.splitlines() if line.startswith("kind:"))
        status = "OK  " if ok else "FAIL"
        print(f"[{status}] {name:<24} {label:<40} {kind_count} objects")

        if not ok:
            err = (result.stderr.strip() or result.stdout.strip()).splitlines()
            for line in err[:15]:
                print(f"          {line}")
        elif args.kubeconform:
            kc = run_kubeconform(result.stdout)
            if kc is None:
                print("          kubeconform not installed, skipped schema check")
            elif kc.returncode != 0:
                ok = False
                for line in (kc.stdout + kc.stderr).strip().splitlines()[:15]:
                    print(f"          {line}")

        results.append((name, ok))

    print()
    failed = [n for n, ok in results if not ok]
    print(f"{len(results)} apps checked, {len(results) - len(failed)} ok, {len(failed)} failed")
    if failed:
        print("failed: " + ", ".join(failed))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
