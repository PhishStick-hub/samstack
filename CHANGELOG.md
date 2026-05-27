# Changelog

## [3.2.1](https://github.com/PhishStick-hub/samstack/compare/v3.2.0...v3.2.1) (2026-05-27)


### Bug Fixes

* **ci:** fix pypi publish ([6f18f0e](https://github.com/PhishStick-hub/samstack/commit/6f18f0e8ed03d9dfe4732641134d066356d10b4e))

## [3.2.0](https://github.com/PhishStick-hub/samstack/compare/v3.1.2...v3.2.0) (2026-05-24)


### Features

* **ci:** rebuild CI/CD pipeline from scratch ([f751259](https://github.com/PhishStick-hub/samstack/commit/f751259fdc3b1189e8d420329db27d87edd6b1c1))


### Bug Fixes

* **ci:** move coverage gate to integration job (unit tests alone cover 25%) ([77fcde6](https://github.com/PhishStick-hub/samstack/commit/77fcde62f59378e375df066602aabd79a56836e5))
* **ci:** run coverage report before separate test suites ([433d2a7](https://github.com/PhishStick-hub/samstack/commit/433d2a70db4e64ad7a91f79ce3f97b3c19bee57e))
* **ci:** use --cov-append to accumulate coverage across test suites ([d1939f2](https://github.com/PhishStick-hub/samstack/commit/d1939f2bd9dccc24eda3a8027b62cc6a9d5f28b3))
* **ci:** use setup-uv@v7 (v8 major tag does not exist) ([f066afd](https://github.com/PhishStick-hub/samstack/commit/f066afdb23954ef930bc547a357753aa56c804b4))

## [3.1.2](https://github.com/PhishStick-hub/samstack/compare/v3.1.1...v3.1.2) (2026-05-21)


### Bug Fixes

* **ci:** add always() to publish job condition ([ac8ad22](https://github.com/PhishStick-hub/samstack/commit/ac8ad228b320f28a6e690f7363046f4d0b35e54e))
* **ci:** guard needs.check-tag.outputs access behind result check ([559ae50](https://github.com/PhishStick-hub/samstack/commit/559ae50cbef558dfe0835a76e45c333d9bd11afc))

## [3.1.1](https://github.com/PhishStick-hub/samstack/compare/v3.1.0...v3.1.1) (2026-05-21)


### Bug Fixes

* **ci:** fetch tags in check-tag job, remove 2-min retry loop ([66dadae](https://github.com/PhishStick-hub/samstack/commit/66dadae17cffd49248b189cd7256eadfb261859f))

## [3.1.0](https://github.com/PhishStick-hub/samstack/compare/v3.0.0...v3.1.0) (2026-05-21)


### Features

* **ci:** add release-please config with changelog sections for all commit types ([7fbd127](https://github.com/PhishStick-hub/samstack/commit/7fbd12765d353cefe48559ea23ae0a9d828170b6))


### Bug Fixes

* **ci:** split publish into check-tag + publish jobs to avoid approval noise ([6bd01cb](https://github.com/PhishStick-hub/samstack/commit/6bd01cbfb48528a866a3bbe38529d0f83453bf6d))
* **ci:** use PAT in lockfile workflow to enable CI chaining ([1a87c08](https://github.com/PhishStick-hub/samstack/commit/1a87c080c9f6aea20fd0308f34533e221def9b3b))


### Documentation

* document PR title conventions for release-please ([9778fbe](https://github.com/PhishStick-hub/samstack/commit/9778fbe4e1f3cc8acd904e788887c26b7e27c1f9))

## [3.0.0](https://github.com/PhishStick-hub/samstack/compare/v2.3.0...v3.0.0) (2026-05-20)


### ⚠ BREAKING CHANGES

* **fixtures:** _run_sam_service (internal, never exported) removed. Sam_api and sam_lambda_endpoint public fixture signatures preserved.

### Features

* **fixtures:** deduplicate sam_api/sam_lambda with SamServiceConfig + start_sam() ([#29](https://github.com/PhishStick-hub/samstack/issues/29)) ([600387b](https://github.com/PhishStick-hub/samstack/commit/600387bcd62651224074e31a956cc7ed93dd63ef))


### Reverts

* undo release v2.3.0 — logic is too complex ([b97dc6c](https://github.com/PhishStick-hub/samstack/commit/b97dc6c8a80937994e6885c1ed60f01122cd5bfd))

## [2.2.0](https://github.com/PhishStick-hub/samstack/compare/v2.1.0...v2.2.0) (2026-04-26)


### Features

* per-function warm container control ([57a368a](https://github.com/PhishStick-hub/samstack/commit/57a368a664ad1e45a263b545a1b83253504610e9))
* per-function warm container control (v2.2.0) ([f917b2a](https://github.com/PhishStick-hub/samstack/commit/f917b2a9abf750412757dfcb6137fccf2d5ee3a0))

## [2.1.0](https://github.com/PhishStick-hub/samstack/compare/v2.0.0...v2.1.0) (2026-04-25)


### Features

* **ryuk:** v1.0 Orphan Container Cleanup — crash-safe Docker infrastructure ([ef76409](https://github.com/PhishStick-hub/samstack/commit/ef7640968129e90e3f31e70a35e4438b2bff54b6))
* v1.0 Orphan Container Cleanup — Ryuk crash-safe Docker infrastructure ([0ac247f](https://github.com/PhishStick-hub/samstack/commit/0ac247f11a9a6fcdf1143be552dc00b564ff0d2b))

## [2.0.0](https://github.com/PhishStick-hub/samstack/compare/v1.0.0...v2.0.0) (2026-04-22)


### ⚠ BREAKING CHANGES

* **sqs:** SqsQueue.receive(max_messages=, wait_seconds=) is now SqsQueue.receive(max=, wait=). External callers using the old keyword names must update. Default max is now 10 (was 1) and default wait is now 1 (was 0).

### Features

* **sqs:** align SqsQueue.receive signature with docs ([a93da22](https://github.com/PhishStick-hub/samstack/commit/a93da223ddcbaac923b5a4d1f6551ad7b1f2f2cf))


### Bug Fixes

* resolve critical + high defects from python review ([a2958e2](https://github.com/PhishStick-hub/samstack/commit/a2958e2cea19b57d30ad35ee3bd7a7cf2e3e0ae7))
* resolve medium + H4 issues from python review ([b701ca6](https://github.com/PhishStick-hub/samstack/commit/b701ca6537ff4cce97c0059db7d47b635e26af7d))
* resolve python-review critical, high, and medium defects ([021cf5a](https://github.com/PhishStick-hub/samstack/commit/021cf5ab1ec3d69ae18627582021b6f4dbc219df))


### Documentation

* update SqsQueue.receive() signature in README examples ([7908609](https://github.com/PhishStick-hub/samstack/commit/79086096bc33b9ec086d650614577525ff51bf8b))

## [1.0.0](https://github.com/PhishStick-hub/samstack/compare/v0.2.0...v1.0.0) (2026-04-17)


### ⚠ BREAKING CHANGES

* sam_env_vars no longer sets a global AWS_ENDPOINT_URL. Per-service AWS_ENDPOINT_URL_<SERVICE> variables are emitted instead, with AWS_ENDPOINT_URL_LAMBDA pointing at the local SAM lambda runtime so Lambda-to-Lambda invokes stay in SAM rather than falling into LocalStack. Lambda code relying on the old variable must migrate.

### Features

* **logs:** consolidate all service logs under logs/ and stream LocalStack ([0229a49](https://github.com/PhishStick-hub/samstack/commit/0229a49af4a46c068fe98332f4551f894110a5e8))
* multi-lambda mock support with per-service endpoint routing ([007e5a0](https://github.com/PhishStick-hub/samstack/commit/007e5a05c4e41da1bffeba0c7532eb83bbb8704e))


### Bug Fixes

* **mock:** declare injected env vars in templates + autouse mock fixture ([853ca43](https://github.com/PhishStick-hub/samstack/commit/853ca439b3afa762163d0a53315f7672d2b60880))


### Documentation

* **claude:** sync CLAUDE.md with refactor changes ([a788616](https://github.com/PhishStick-hub/samstack/commit/a788616498fbf6bb0cc6ee0e2067693c2af98d58))

## [0.2.0](https://github.com/PhishStick-hub/samstack/compare/v0.1.3...v0.2.0) (2026-04-15)


### Features

* **fixtures:** add s3_resource and sqs_resource session fixtures ([2442916](https://github.com/PhishStick-hub/samstack/commit/244291672351afa1cf033d3877aee21b88dbdb6b))
* **fixtures:** add s3_resource, dynamodb_resource, sqs_resource session fixtures ([d9c3e0e](https://github.com/PhishStick-hub/samstack/commit/d9c3e0e111a9a984ce1133828cda3a0749941bf6))


### Documentation

* **fixtures:** document s3_resource, dynamodb_resource, sqs_resource fixtures ([52385e0](https://github.com/PhishStick-hub/samstack/commit/52385e0a844f6d27345554bc960f33eea275ff61))

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
