from typing import Any

from dotenv import load_dotenv
from flask import Flask, abort, request

from trx_website.settings import TRX_DOCS_DIR
from trx_website.templating import catalog
from trx_website.trx_docs import get_trx_docs, make_docs_nav, sync_trx_docs
from trx_website.trx_releases import get_trx_releases, sync_trx_releases
from trx_website.utils import cache_for

load_dotenv()
app = Flask(__name__)


catalog.jinja_env.globals.update(app.jinja_env.globals)
catalog.jinja_env.filters.update(app.jinja_env.filters)


@cache_for(duration=600)
def get_global_context() -> dict[str, Any]:
    releases = get_trx_releases()
    tr1x_releases = [r for r in releases if "TR1X" in (r.name or "")]
    tr2x_releases = [r for r in releases if "TR2X" in (r.name or "")]
    prerelease = [r for r in releases if r.prerelease][0]
    last_tr1x_release = tr1x_releases[0]
    last_tr2x_release = tr2x_releases[0]
    return dict(
        tr1x_releases=tr1x_releases,
        tr2x_releases=tr2x_releases,
        prerelease=prerelease,
        last_tr1x_release=last_tr1x_release,
        last_tr2x_release=last_tr2x_release,
        last_tr1x_video=[r for r in tr1x_releases if r.video_embed_url][
            0
        ].video_embed_url,
        last_tr2x_video=[r for r in tr2x_releases if r.video_embed_url][
            0
        ].video_embed_url,
        socials=dict(
            discord="https://discord.gg/AaAnsquVxU",
            github="https://github.com/LostArtefacts/",
            youtube="https://www.youtube.com/@lostartefacts",
        ),
    )


def _render(template: str, **kwargs: Any) -> Any:
    return catalog.render(template, **kwargs, _globals=get_global_context())


@app.route("/")
def index() -> Any:
    return _render("Home")


@app.route("/tr1x/")
def tr1x_landing() -> Any:
    return _render("TR1XLanding")


@app.route("/tr1x/download")
def tr1x_download() -> Any:
    return _render("TR1XDownload")


@app.route("/tr1x/install_guide/", defaults={"branch": None, "version": "tr1"})
@app.route("/tr2x/install_guide/", defaults={"branch": None, "version": "tr2"})
@app.route("/tr1x/install_guide/<branch>/", defaults={"version": "tr1"})
@app.route("/tr2x/install_guide/<branch>/", defaults={"version": "tr2"})
def trx_install_guide(branch: str, version: str) -> Any:
    branches = sorted([p.name for p in TRX_DOCS_DIR.iterdir() if p.is_dir()])
    if not branches:
        abort(404)
    if branch is None:
        branch = "stable" if "stable" in branches else branches[0]
    elif branch not in branches:
        abort(404)

    # build docs tree with title/order hierarchy
    docs = get_trx_docs(branch)
    doc = docs.get(f"{version}/installing")
    if not doc:
        abort(404)

    return _render(
        {
            "tr1": "TR1XInstallGuide",
            "tr2": "TR2XInstallGuide",
        }[version],
        doc=doc,
    )


@app.route("/tr1x/releases")
def tr1x_releases() -> Any:
    return _render("TR1XReleases")


@app.route("/tr2x/")
def tr2x_landing() -> Any:
    return _render("TR2XLanding")


@app.route("/tr2x/download")
def tr2x_download() -> Any:
    return _render("TR2XDownload")


@app.route("/tr2x/releases")
def tr2x_releases() -> Any:
    return _render("TR2XReleases")


@app.route("/rando/")
def rando_landing() -> Any:
    return _render("RandoLanding")


@app.route("/trx/docs/", defaults={"branch": None, "doc_path": None})
@app.route("/trx/docs/<branch>/", defaults={"doc_path": None})
@app.route("/trx/docs/<branch>/<path:doc_path>")
def trx_docs(branch: str | None, doc_path: str | None) -> Any:
    branches = sorted([p.name for p in TRX_DOCS_DIR.iterdir() if p.is_dir()])
    if not branches:
        abort(404)
    if branch is None:
        branch = "stable" if "stable" in branches else branches[0]
    elif branch not in branches:
        abort(404)

    # build docs tree with title/order hierarchy
    docs = get_trx_docs(branch)

    if not doc_path:
        doc_path = list(docs.keys())[0]
    doc = docs.get(doc_path)
    if not doc:
        abort(404)

    return _render(
        "TRXDocs",
        branches=branches,
        current_branch=branch,
        nav=make_docs_nav(docs),
        doc=doc,
    )


@app.route("/about/")
def about() -> Any:
    return _render(
        "About",
        team=[
            dict(
                name="Dash",
                github_profile="rr-",
                roles=["TRX lead", "Coder", "Website fairy"],
            ),
            dict(
                name="Lahm",
                github_profile="lahm86",
                roles=["Rando lead", "Coder", "Assets artisan"],
            ),
            dict(
                name="walkawayy",
                github_profile="walkawayy",
                roles=["Coder", "Core Design engine wizard"],
            ),
            dict(
                name="aredfan",
                github_profile="aredfan",
                roles=["Bug hunter", "Gameplay QA"],
            ),
        ],
    )


@app.route("/webhook/", methods=["GET", "PUT", "POST"])
def webhook() -> Any:
    if request.headers.get("X-GitHub-Event") == "release":
        sync_trx_releases()
        return {"message": "updated releases"}, 200
    elif request.headers.get("X-GitHub-Event") == "push" and request.json.get(
        "ref"
    ) in ["stable", "refs/heads/stable", "develop", "refs/heads/develop"]:
        sync_trx_docs()
        return {"message": "updated docs"}, 200
    return {}, 200


if __name__ == "__main__":
    app.run(debug=True)
