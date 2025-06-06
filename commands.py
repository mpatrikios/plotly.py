from distutils import log
import json
import os
import platform
import shutil
from subprocess import check_call
import sys
import time

USAGE = "usage: python commands.py [updateplotlyjsdev | updateplotlyjs | codegen]"
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
NODE_ROOT = os.path.join(PROJECT_ROOT, "js")
NODE_MODULES = os.path.join(NODE_ROOT, "node_modules")
TARGETS = [
    os.path.join(PROJECT_ROOT, "plotly", "package_data", "widgetbundle.js"),
]

NPM_PATH = os.pathsep.join(
    [
        os.path.join(NODE_ROOT, "node_modules", ".bin"),
        os.environ.get("PATH", os.defpath),
    ]
)


# Load plotly.js version from js/package.json
def plotly_js_version():
    path = os.path.join(PROJECT_ROOT, "js", "package.json")
    with open(path, "rt") as f:
        package_json = json.load(f)
        version = package_json["dependencies"]["plotly.js"]
        version = version.replace("^", "")

    return version


# install package.json dependencies using npm
def install_js_deps(local):
    npmName = "npm"
    if platform.system() == "Windows":
        npmName = "npm.cmd"

    try:
        check_call([npmName, "--version"])
        has_npm = True
    except:
        has_npm = False

    skip_npm = os.environ.get("SKIP_NPM", False)
    if skip_npm:
        log.info("Skipping npm-installation")
        return

    if not has_npm:
        log.error(
            "`npm` unavailable.  If you're running this command using sudo, make sure `npm` is available to sudo"
        )

    env = os.environ.copy()
    env["PATH"] = NPM_PATH

    if has_npm:
        log.info("Installing build dependencies with npm.  This may take a while...")
        check_call(
            [npmName, "install"],
            cwd=NODE_ROOT,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        if local is not None:
            plotly_archive = os.path.join(local, "plotly.js.tgz")
            check_call(
                [npmName, "install", plotly_archive],
                cwd=NODE_ROOT,
                stdout=sys.stdout,
                stderr=sys.stderr,
            )
        check_call(
            [npmName, "run", "build"],
            cwd=NODE_ROOT,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        os.utime(NODE_MODULES, None)

    for t in TARGETS:
        if not os.path.exists(t):
            msg = "Missing file: %s" % t
            raise ValueError(msg)


# Generate class hierarchy from Plotly JSON schema
def run_codegen():
    if sys.version_info < (3, 8):
        raise ImportError("Code generation must be executed with Python >= 3.8")

    from codegen import perform_codegen

    perform_codegen()


def overwrite_schema_local(uri):
    path = os.path.join(PROJECT_ROOT, "codegen", "resources", "plot-schema.json")
    shutil.copyfile(uri, path)


def overwrite_schema(url):
    import requests

    req = requests.get(url)
    assert req.status_code == 200
    path = os.path.join(PROJECT_ROOT, "codegen", "resources", "plot-schema.json")
    with open(path, "wb") as f:
        f.write(req.content)


def overwrite_bundle_local(uri):
    path = os.path.join(PROJECT_ROOT, "plotly", "package_data", "plotly.min.js")
    shutil.copyfile(uri, path)


def overwrite_bundle(url):
    import requests

    req = requests.get(url)
    print("url:", url)
    assert req.status_code == 200
    path = os.path.join(PROJECT_ROOT, "plotly", "package_data", "plotly.min.js")
    with open(path, "wb") as f:
        f.write(req.content)


def overwrite_plotlyjs_version_file(plotlyjs_version):
    path = os.path.join(PROJECT_ROOT, "plotly", "offline", "_plotlyjs_version.py")
    with open(path, "w") as f:
        f.write(
            """\
# DO NOT EDIT
# This file is generated by the updatebundle commands.py command
__plotlyjs_version__ = "{plotlyjs_version}"
""".format(
                plotlyjs_version=plotlyjs_version
            )
        )


def request_json(url):
    import requests

    req = requests.get(url)
    return json.loads(req.content.decode("utf-8"))


def get_latest_publish_build_info(repo, branch):
    url = (
        r"https://circleci.com/api/v1.1/project/github/"
        r"{repo}/tree/{branch}?limit=100&filter=completed"
    ).format(repo=repo, branch=branch)

    branch_jobs = request_json(url)

    # Get most recent successful publish build for branch
    builds = [
        j
        for j in branch_jobs
        if j.get("workflows", {}).get("job_name", None) == "publish-dist"
        and j.get("status", None) == "success"
    ]
    build = builds[0]

    # Extract build info
    return {p: build[p] for p in ["vcs_revision", "build_num", "committer_date"]}


def get_bundle_schema_local(local):
    plotly_archive = os.path.join(local, "plotly.js.tgz")
    plotly_bundle = os.path.join(local, "dist/plotly.min.js")
    plotly_schemas = os.path.join(local, "dist/plot-schema.json")
    return plotly_archive, plotly_bundle, plotly_schemas


def get_bundle_schema_urls(build_num):
    url = (
        "https://circleci.com/api/v1.1/project/github/"
        "plotly/plotly.js/{build_num}/artifacts"
    ).format(build_num=build_num)

    artifacts = request_json(url)

    # Find archive
    archives = [a for a in artifacts if a.get("path", None) == "plotly.js.tgz"]
    archive = archives[0]

    # Find bundle
    bundles = [a for a in artifacts if a.get("path", None) == "dist/plotly.min.js"]
    bundle = bundles[0]

    # Find schema
    schemas = [a for a in artifacts if a.get("path", None) == "dist/plot-schema.json"]
    schema = schemas[0]

    return archive["url"], bundle["url"], schema["url"]


# Download latest version of the plot-schema JSON file
def update_schema(plotly_js_version):
    url = (
        "https://raw.githubusercontent.com/plotly/plotly.js/"
        "v%s/dist/plot-schema.json" % plotly_js_version
    )
    overwrite_schema(url)


# Download latest version of the plotly.js bundle
def update_bundle(plotly_js_version):
    url = (
        "https://raw.githubusercontent.com/plotly/plotly.js/"
        "v%s/dist/plotly.min.js" % plotly_js_version
    )
    overwrite_bundle(url)

    # Write plotly.js version file
    plotlyjs_version = plotly_js_version
    overwrite_plotlyjs_version_file(plotlyjs_version)


# Update project to a new version of plotly.js
def update_plotlyjs(plotly_js_version):
    update_bundle(plotly_js_version)
    update_schema(plotly_js_version)
    run_codegen()


# Update the plotly.js schema and bundle from master
def update_schema_bundle_from_master():

    if "--devrepo" in sys.argv:
        devrepo = sys.argv[sys.argv.index("--devrepo") + 1]
    else:
        devrepo = "plotly/plotly.js"

    if "--devbranch" in sys.argv:
        devbranch = sys.argv[sys.argv.index("--devbranch") + 1]
    else:
        devbranch = "master"

    if "--local" in sys.argv:
        local = sys.argv[sys.argv.index("--local") + 1]
    else:
        local = None

    if local is None:
        build_info = get_latest_publish_build_info(devrepo, devbranch)

        archive_url, bundle_url, schema_url = get_bundle_schema_urls(
            build_info["build_num"]
        )

        # Update bundle in package data
        overwrite_bundle(bundle_url)

        # Update schema in package data
        overwrite_schema(schema_url)
    else:
        # this info could be more informative but
        # it doesn't seem as useful in a local context
        # and requires dependencies and programming.
        build_info = {"vcs_revision": "local", "committer_date": str(time.time())}
        devrepo = local
        devbranch = ""

        archive_uri, bundle_uri, schema_uri = get_bundle_schema_local(local)
        overwrite_bundle_local(bundle_uri)
        overwrite_schema_local(schema_uri)

    # Update plotly.js url in package.json
    package_json_path = os.path.join(NODE_ROOT, "package.json")
    with open(package_json_path, "r") as f:
        package_json = json.load(f)

    # Replace version with bundle url
    package_json["dependencies"]["plotly.js"] = (
        archive_url if local is None else archive_uri
    )
    with open(package_json_path, "w") as f:
        json.dump(package_json, f, indent=2)

    # update plotly.js version in _plotlyjs_version
    rev = build_info["vcs_revision"]
    date = str(build_info["committer_date"])
    version = "_".join([devrepo, devbranch, date[:10], rev[:8]])
    overwrite_plotlyjs_version_file(version)
    install_js_deps(local)


# Update project to a new development version of plotly.js
def update_plotlyjs_dev():
    update_schema_bundle_from_master()
    run_codegen()


def main():
    if len(sys.argv) != 2:
        print(USAGE, file=sys.stderr)
        sys.exit(1)
    elif sys.argv[1] == "codegen":
        run_codegen()
    elif sys.argv[1] == "updateplotlyjsdev":
        update_plotlyjs_dev()
    elif sys.argv[1] == "updateplotlyjs":
        print(plotly_js_version())
        update_plotlyjs(plotly_js_version())


if __name__ == "__main__":
    main()
