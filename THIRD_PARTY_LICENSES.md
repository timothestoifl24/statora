# Third-party licenses

Statora is released under the [MIT License](LICENSE). It includes or depends on the following third-party software, each under its own license.

## Bundled with Statora

These files are shipped inside the repository, the Python package and the container image (`src/statora/static/vendor/`, `branding/fonts/`). Their full license texts are in [`src/statora/static/vendor/licenses/`](src/statora/static/vendor/licenses/).

| Component | Version | License | Files | Upstream |
|---|---|---|---|---|
| Tabler | 1.4.0 | MIT | `tabler.min.css`, `tabler.min.js` | https://github.com/tabler/tabler |
| Tabler Icons (webfont) | 3.31.0 | MIT | `tabler-icons.min.css`, `fonts/tabler-icons.woff2` | https://github.com/tabler/tabler-icons |
| htmx | 2.0.4 | 0BSD | `htmx.min.js` | https://github.com/bigskysoftware/htmx |
| ApexCharts | 3.54.1 | MIT | `apexcharts.min.js` | https://github.com/apexcharts/apexcharts.js |
| Swagger UI | 5.17.14 | Apache-2.0 (with NOTICE) | `swagger-ui-bundle.js`, `swagger-ui.css` | https://github.com/swagger-api/swagger-ui |
| ReDoc | 2.1.5 | MIT | `redoc.standalone.js` | https://github.com/Redocly/redoc |
| Manrope (logo wordmark source) | variable | OFL-1.1 | `branding/fonts/Manrope-Variable.ttf` ([license](branding/fonts/OFL.txt)) | https://github.com/sharanda/manrope |

The Statora logo is converted to outlines, so no font file is needed to display it.

## Installed dependencies

Python dependencies are installed from PyPI and listed in [`pyproject.toml`](pyproject.toml) and [`uv.lock`](uv.lock). The container image includes them. Almost all are under permissive licenses (MIT, BSD, Apache-2.0, ISC, PSF, Unlicense). Three use weak copyleft licenses:

| Package | License | Used for |
|---|---|---|
| `ldap3` | LGPL-3.0 | LDAP / Active Directory sign-in |
| `icmplib` | LGPL-3.0 | Ping monitors |
| `certifi` | MPL-2.0 | Root CA certificates for TLS checks |

Statora uses these as separate, unmodified libraries, which their licenses allow without affecting the license of Statora. If you modify one of them, its own license applies to your modifications. You can replace them with your own builds in a source installation or by rebuilding the image.

The container image is based on Debian (`debian:trixie-slim`), contains a CPython build from the [python-build-standalone](https://github.com/astral-sh/python-build-standalone) project (PSF-2.0), and system libraries such as libxml2, libxslt and xmlsec1 (MIT-style licenses). License files for the Python packages are inside the image under `/app/.venv/lib/python3.*/site-packages/*.dist-info/`, and for Debian packages under `/usr/share/doc/*/copyright`.
