# Changelog

## [0.1.3](https://github.com/PhishStick-hub/samstack/compare/v0.1.2...v0.1.3) (2026-04-12)


### Documentation

* **contributing:** note why publish is chained, not tag-triggered ([a2a630f](https://github.com/PhishStick-hub/samstack/commit/a2a630fe6705866ec8d767643e816b4167071e05))

## [0.1.2](https://github.com/PhishStick-hub/samstack/compare/v0.1.1...v0.1.2) (2026-04-12)


### Documentation

* update CONTRIBUTING with commit type warning, correct tag pattern, pipeline diagram ([23ee6d2](https://github.com/PhishStick-hub/samstack/commit/23ee6d27a9534a7f1bb0cae32e01204af098bdc9))

## [0.1.1](https://github.com/PhishStick-hub/samstack/compare/v0.1.0...v0.1.1) (2026-04-12)


### Bug Fixes

* **ci:** correct tag glob pattern for publish-pypi trigger ([0396116](https://github.com/PhishStick-hub/samstack/commit/0396116ed1fb1e2dbdcce598709ae674a8f1ff2c))

## 0.1.0 (2026-04-12)


### Features

* **ci:** add release-please workflow for automated releases ([a0d6411](https://github.com/PhishStick-hub/samstack/commit/a0d6411a7b7f76c16ed22fd29cf5bddd648635dc))
* initial release of samstack pytest plugin ([89f855a](https://github.com/PhishStick-hub/samstack/commit/89f855af2b6702a436bcf7b85800f230f672a774))
* **release:** auto-increment dev version per commit via hatch-vcs local_scheme ([eaf0897](https://github.com/PhishStick-hub/samstack/commit/eaf0897eaf45d77f8a58bdef4cdff0bb96d81530))
* **release:** dynamic versioning via hatch-vcs, switch pre-release tags to PEP 440 alpha format ([e6e3eac](https://github.com/PhishStick-hub/samstack/commit/e6e3eace30f330cc0e3282af383a8ec297dcc66e))


### Bug Fixes

* **ci:** decouple ci from validate to prevent skip propagation in publish job ([6d35017](https://github.com/PhishStick-hub/samstack/commit/6d350172fce98a52b148c1772a7a71695d409f9b))
* **ci:** format hatch-vcs generated _version.py ([e98cc1b](https://github.com/PhishStick-hub/samstack/commit/e98cc1be305677b7fcae92bc8243f557d1606890))
* **ci:** restrict publish-pypi trigger to stable version tags only ([b7506d2](https://github.com/PhishStick-hub/samstack/commit/b7506d267f9a33bfafc0160e8e7395a264b40ad3))
* **fixtures:** pass --template to sam build and sam local commands ([e1ca8e9](https://github.com/PhishStick-hub/samstack/commit/e1ca8e909db686a09a5b62c7d6c5eb3c986453a7))
* **fixtures:** remove arm64 architecture from test template ([3be14d7](https://github.com/PhishStick-hub/samstack/commit/3be14d78bab55d35543d090ce140680101122692))
* **fixtures:** skip --skip-pull-image in CI so Lambda runtime image is pulled ([088d5ef](https://github.com/PhishStick-hub/samstack/commit/088d5efa1d3f2d3da6f486957a2d3c7f43b70a16))


### Documentation

* add CONTRIBUTING.md with workflow and release guide ([50c3450](https://github.com/PhishStick-hub/samstack/commit/50c3450ff79a277fa2b7e71d51dc40a0a663a14f))
