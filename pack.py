#!/usr/bin/python3

import glob
import os
import subprocess
import sys
import urllib.error
import xml.dom.minidom
from urllib import request
import argparse
import pathlib
import json


class Package:
    def __init__(self, id: str, path: str = None, version: str = None):
        self.id = id
        self._path = None
        if path is not None:
            self.path = path
        self.version = version
        self.refs = set()
        self._is_pushed = None

    @property
    def path(self) -> pathlib.Path:
        return self._path

    @path.setter
    def path(self, value: str):
        self._path = pathlib.Path(value)

    def __eq__(self, other):
        return (
            isinstance(other, self.__class__) and getattr(other, "id", None) == self.id
        )

    def __hash__(self):
        return hash(self.id)

    def restore(self):
        cmd = subprocess.run(
            ["dotnet", "restore", "--no-cache"],
            text=True,
            capture_output=True,
            cwd=self.path.parent,
        )
        self._check_error("restore", cmd)

    def pack(self):
        cmd = subprocess.run(
            ["dotnet", "pack", self.path, "-c", "Release", "-o", os.getcwd()],
            text=True,
            capture_output=True,
        )
        self._check_error("pack", cmd)

    def push(self, source: str):
        cmd = subprocess.run(
            [
                "nuget",
                "push",
                "%s/%s.%s.nupkg" % (os.getcwd(), self.id, self.version),
                "-Source",
                source,
            ],
            text=True,
            capture_output=True,
        )
        self._check_error("push", cmd)
        self._is_pushed = True

    def try_push(self, args: argparse.Namespace) -> bool:
        if self.is_pushed(args):
            print(f"{self.id} {self.version} skipped")
            return False

        for dep in self.refs:
            dep.try_push(args)

        self.restore()
        self.pack()
        self.push(args.source)
        print(f"{self.id} {self.version} pushed")

        return True

    def is_pushed(self, args: argparse.Namespace) -> bool:
        if self._is_pushed is not None:
            return self._is_pushed

        data = {"versions": []}

        try:
            req = request.Request(
                f"{args.api_url}/projects/{args.project_id}/packages/nuget/download/{self.id}/index",
            )

            with request.urlopen(req) as resp:
                code = resp.getcode()
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            code = e.code

        if code == 200 and self.version in data["versions"]:
            self._is_pushed = True
            return self._is_pushed
        elif code not in [200, 404]:
            raise Exception(f"{self.id} {self.version} returned {code}")

        self._is_pushed = False
        return self._is_pushed

    def _format_error(self, action: str, cmd: subprocess.CompletedProcess) -> str:
        return f"{self.id} {self.version} {action} failed with {cmd.returncode}\n{cmd.stdout[-2048:]}"

    def _check_error(self, action: str, cmd: subprocess.CompletedProcess):
        if cmd.returncode != 0:
            raise Exception(self._format_error(action, cmd))


def main(args: argparse.Namespace):
    pwd_manager = request.HTTPPasswordMgrWithDefaultRealm()
    pwd_manager.add_password(None, args.api_url, args.api_username, args.api_password)
    auth_handler = request.HTTPBasicAuthHandler(pwd_manager)
    opener = request.build_opener(auth_handler)
    request.install_opener(opener)

    packages = dict()

    for f in glob.glob(os.getcwd() + "/**/*.csproj", recursive=True):
        with xml.dom.minidom.parse(f) as dom:
            packable = dom.getElementsByTagName("IsPackable")

            if len(packable) == 0:
                continue

            if packable[0].firstChild.nodeValue.lower() != "true":
                continue

            package_id = dom.getElementsByTagName("PackageId")
            version_id = dom.getElementsByTagName("PackageVersion")
            version = version_id[0].firstChild.nodeValue
            package_id = package_id[0].firstChild.nodeValue

            if package_id in packages:
                package = packages[package_id]
                package.path = f
                package.version = version
            else:
                package = Package(id=package_id, path=f, version=version)
                packages[package_id] = package

            for r in dom.getElementsByTagName("PackageReference"):
                name = r.getAttribute("Include")
                if "Shared" in name:
                    if name not in packages:
                        dep = Package(id=name)
                        packages[name] = dep
                    else:
                        dep = packages[name]
                    package.refs.add(dep)

    for _, package in packages.items():
        package.try_push(args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    
    parser.add_argument("--source", type=str, help="Nuget source", required=True)
    parser.add_argument(
        "--project-id", type=str, help="Gitlab project id", required=True
    )
    parser.add_argument("--api-url", type=str, help="Gitlab API URL", required=True)
    parser.add_argument(
        "--api-username", type=str, help="Gitlab API username", required=True
    )
    parser.add_argument(
        "--api-password", type=str, help="Gitlab API password", required=True
    )

    args = parser.parse_args()

    try:
        main(args)
        sys.exit(0)
    except Exception as e:
        print(e)
        sys.exit(1)
