# Changelog

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
