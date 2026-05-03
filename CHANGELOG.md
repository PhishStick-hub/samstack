# Changelog

## [2.3.0](https://github.com/PhishStick-hub/samstack/compare/v2.2.0...v2.3.0) (2026-05-03)


### Features

* **08-01:** implement _xdist coordination module ([b508707](https://github.com/PhishStick-hub/samstack/commit/b508707cd1f70f8aad1b455e0467ab5a030c7c6b))
* **08-02:** wire docker_network fixture for xdist awareness ([76f6c38](https://github.com/PhishStick-hub/samstack/commit/76f6c384f10397d9ca37e68461df5e36137ca1b4))
* **09-01:** implement xdist-aware localstack_container with _LocalStackContainerProxy ([685deb6](https://github.com/PhishStick-hub/samstack/commit/685deb6358ee8aedfc8a7e013c657d957df6123e))
* **09-02:** make sam_build xdist-aware with build_complete state flag ([5ac1213](https://github.com/PhishStick-hub/samstack/commit/5ac121318914f01993a594e74f86c6bd593918aa))
* **10-01:** add xdist branching to sam_api fixture ([045ace9](https://github.com/PhishStick-hub/samstack/commit/045ace9f73c6984f4fcbb89f921d07cb49cd5c7f))
* **10-sam-api-lambda-xdist-awareness:** implement xdist branching for sam_lambda_endpoint fixture ([1460d6c](https://github.com/PhishStick-hub/samstack/commit/1460d6c387e6a23eea273cb52ee7513868dedd23))
* **11-01:** add xdist coordination to make_lambda_mock ([8099d46](https://github.com/PhishStick-hub/samstack/commit/8099d46310bea5bb83cb07f3119c229c4f279f2e))
* **12-01:** add crash recovery test and update root conftest ([f17a377](https://github.com/PhishStick-hub/samstack/commit/f17a377e6960cbc7db84d38cff4ba8488ec23db8))
* **12-01:** add resource parallelism tests for xdist ([08ccfb7](https://github.com/PhishStick-hub/samstack/commit/08ccfb7b34a6e6beb6a82e0acf5de3d27e24cead))
* **12-01:** create xdist integration conftest and basic tests ([c96af6b](https://github.com/PhishStick-hub/samstack/commit/c96af6bcf61cf57414f9844f118edc59365127ef))
* **12-02:** add performance benchmark script comparing baseline vs xdist ([e7bfe18](https://github.com/PhishStick-hub/samstack/commit/e7bfe185e5d59688a728e17cd83a57230e73f4cf))
* **ci:** parallel matrix + fix SESSION_ID assertions for xdist ([8355663](https://github.com/PhishStick-hub/samstack/commit/83556633cafa37706a6c10cae44e2df1f322fb34))
* **xdist:** add error_prefix to xdist_shared_session ([bcbd4ee](https://github.com/PhishStick-hub/samstack/commit/bcbd4ee34ca97a2eacfc96e298a914ceab5bcf40))
* **xdist:** pytest-xdist parallel testing support ([#21](https://github.com/PhishStick-hub/samstack/issues/21)) ([34d9151](https://github.com/PhishStick-hub/samstack/commit/34d9151bf85d33e412992ebfc044eeedea8eac22))


### Bug Fixes

* **09-02:** remove unused import and apply ruff formatting to test file ([3aceb88](https://github.com/PhishStick-hub/samstack/commit/3aceb8859a473f755160217f5cfa0ed58d7b4b34))
* **09:** CR-01 release infra lock in docker_network except block before re-raising ([3f024ae](https://github.com/PhishStick-hub/samstack/commit/3f024ae8c8a909e2fdc95ed835b9d8e235c540bf))
* **09:** CR-02 change pytest.skip to pytest.fail in wait_for_state_key so infra failures surface as red in CI ([771da82](https://github.com/PhishStick-hub/samstack/commit/771da82019812a319b78a2e44c18cd615e3b2af6))
* **09:** CR-02 update tests to expect pytest.fail.Exception instead of pytest.skip.Exception ([aa2f459](https://github.com/PhishStick-hub/samstack/commit/aa2f4595df3c50497a27ec75992acf86ee504c55))
* **09:** WR-01 move wait_for_state_key coordination from docker_network_name into docker_network for gw1+ workers ([81b603a](https://github.com/PhishStick-hub/samstack/commit/81b603a6c5ad5c986197d2efd3e1467ccd61ce91))
* **09:** WR-02 wrap container.stop() in try/except in localstack_container finally block to prevent swallowing original exception ([c8af09c](https://github.com/PhishStick-hub/samstack/commit/c8af09c4e05d8b85e324b8fd982ec010c38d3e7a))
* **09:** WR-03 remove redundant is_controller double-stub from localstack tests; let real is_controller execute from get_worker_id patch ([47af715](https://github.com/PhishStick-hub/samstack/commit/47af71551443637e45b56f1a77864d200d933b00))
* **10:** WR-01 close HTTP response in _pre_warm_api_routes to prevent socket leak ([6c91594](https://github.com/PhishStick-hub/samstack/commit/6c9159468900bc13127e8b2f1f901ade3e05c596))
* **12:** benchmark — replace missing test files, exclude session-ID-incompatible tests, add -n 8, remove -n auto (overwhelms Docker at 10 workers) ([e8a878e](https://github.com/PhishStick-hub/samstack/commit/e8a878e85271bd21a507f22061f25afbe5ce67b8))
* **12:** cap benchmark at -n 4 — -n auto spawns 10 workers on 10-core machine, overwhelms Docker ([b2331a2](https://github.com/PhishStick-hub/samstack/commit/b2331a263ba2b0e2f1088dc71953cd80377d04b7))
* **12:** cap benchmark at -n 4 — SAM Flask drops connections at -n 6+ ([d7a0265](https://github.com/PhishStick-hub/samstack/commit/d7a0265586057e7dfab6f0d854834e84766b7434))
* **12:** correct benchmark test targets — replace nonexistent test_localstack.py and test_docker_network.py with actual integration test files ([b06e2da](https://github.com/PhishStick-hub/samstack/commit/b06e2da27e468fb35b988ba11604e07d2bb3a8e8))
* **12:** CR-01 fix cross-process TOCTOU race in write_state_file ([93da618](https://github.com/PhishStick-hub/samstack/commit/93da6187bc2878e62e5c6e880ffdebdc9bf9facc))
* **12:** exclude test_ryuk_sam_labels.py from benchmark — incompatible with xdist (session ID mismatch across workers) ([19e55fe](https://github.com/PhishStick-hub/samstack/commit/19e55fed3c616c2ffdf1bcd9395abc98db2f7092))
* **12:** WR-01 fail loudly when gw0 cannot acquire infra lock ([c4e9c2e](https://github.com/PhishStick-hub/samstack/commit/c4e9c2eaf49e8257a860f24c05bfa00a3cecb210))
* **ci:** ignore test_crash/ directory not just test_crash.py — test_infra_trigger.py leaks into -n 2 run ([a023436](https://github.com/PhishStick-hub/samstack/commit/a023436fdf74fd866d36fdef76b14339b63542dc))
* **ci:** move test_subcontainer_teardown.py to serial step — subprocess sessions conflict under -n 4 ([12ef0f4](https://github.com/PhishStick-hub/samstack/commit/12ef0f427031e8d27cfd1693ee2d1a7902232d19))
* **ci:** pre-warm HelloWorldFunction and raise crash poll timeout ([4351fb1](https://github.com/PhishStick-hub/samstack/commit/4351fb1d9da605a3bfe7d8ede4166abfa339d910))
* **ci:** pre-warm Lambda A+MockB in multi suite; raise xdist timeouts for slow CI ([7fc17b3](https://github.com/PhishStick-hub/samstack/commit/7fc17b34570c1b999e5022fdf049d3468c3a6ae4))
* **crash:** register Ryuk network filter to clean Lambda runtime containers ([c113e96](https://github.com/PhishStick-hub/samstack/commit/c113e96bc20e0480d233310f5785e2843d6060f0))
* **tests:** prevent HelloWorldFunction pre-warm bleeding into multi_lambda suite ([1d07b87](https://github.com/PhishStick-hub/samstack/commit/1d07b87f4828ac75bbfa2292a781544709b10a2d))
* **xdist:** signal worker-done on session exit and raise infra wait timeouts to 300s ([701e4ca](https://github.com/PhishStick-hub/samstack/commit/701e4ca82d8ccbbcd84a69e0a40ea2c084af70c1))
* **xdist:** wait for workers in each shared-resource teardown, not docker_network ([315a098](https://github.com/PhishStick-hub/samstack/commit/315a0980b9efd402d4b9d88c9c4b566251a41ed4))


### Performance Improvements

* **ci:** parallelize integration tests at -n 4 — split xdist-incompatible session-ID/crash tests to serial step ([cd94416](https://github.com/PhishStick-hub/samstack/commit/cd9441679b14490f0333d10d8dbe70a6afe4e58d))


### Documentation

* **08:** create phase plan for Core Xdist Coordination (2 plans) ([f87917a](https://github.com/PhishStick-hub/samstack/commit/f87917a1eb34a2ea3eb2e44a81e26c0f27cac1aa))
* **09-01:** complete localstack xdist-awareness plan (SUMMARY.md) ([260ee7f](https://github.com/PhishStick-hub/samstack/commit/260ee7fa1ec7dc7052ba3f71d1297091df4a3185))
* **09-02:** complete sam_build xdist-awareness plan ([5f33f00](https://github.com/PhishStick-hub/samstack/commit/5f33f00c4586e87a2c9358c87239d0353a8f94cb))
* **09:** add code review fix report ([974173d](https://github.com/PhishStick-hub/samstack/commit/974173de4fa19bc9fbefae264a60211b31dbd0c0))
* **09:** add code review report ([13542e8](https://github.com/PhishStick-hub/samstack/commit/13542e8f0d377a2444cf046b76fc55ed10395ff6))
* **09:** create phase plan for Docker Infra Xdist-Awareness ([a3d4211](https://github.com/PhishStick-hub/samstack/commit/a3d4211ca5dbd149361082343c96dec0b58aedd8))
* **10-01:** complete sam_api xdist awareness plan ([e8f25f8](https://github.com/PhishStick-hub/samstack/commit/e8f25f820c264bc5ca32026693008c987b6fb862))
* **10-02:** complete sam_lambda_endpoint xdist awareness plan ([59a348f](https://github.com/PhishStick-hub/samstack/commit/59a348fc3a83b818b51a9078369e7b9da4527358))
* **10:** create phase plan — SAM API + Lambda xdist-awareness (2 plans) ([ad1475c](https://github.com/PhishStick-hub/samstack/commit/ad1475ccc8c36e49d3df1aaa88853e0c7203882c))
* **11-01:** complete mock coordination plan summary ([99f89a0](https://github.com/PhishStick-hub/samstack/commit/99f89a0e8255d1940d59e1be4d7a29b532264a36))
* **11:** create phase plan for mock coordination ([eef23e4](https://github.com/PhishStick-hub/samstack/commit/eef23e4b34fe87873bd9cd207208106c609cf2b1))
* **12-01:** complete xdist integration test suite plan ([9f719b4](https://github.com/PhishStick-hub/samstack/commit/9f719b4960a658d09132bed0c2e17585a351f534))
* **12-02:** add Parallel testing with pytest-xdist section to README ([4022bb6](https://github.com/PhishStick-hub/samstack/commit/4022bb6f0358a14da05c124179af94eaa05a6f84))
* **12-02:** complete user-facing xdist deliverables plan ([3a19b56](https://github.com/PhishStick-hub/samstack/commit/3a19b56c12f7f37ba4836d7e90070b1bd244d174))
* **12:** add code review fix report .planning/phases/12-integration-testing-ci-docs-benchmarking/12-REVIEW-FIX.md ([4a793e1](https://github.com/PhishStick-hub/samstack/commit/4a793e1a91b2d44c8ecd95c42399f05db76ee9e1))
* **12:** add phase research for integration testing, CI, docs, and benchmarking ([a610af3](https://github.com/PhishStick-hub/samstack/commit/a610af39dbb267746d1134c6a6f528fd26ad3da9))
* **12:** add UAT quick-start instructions for human verification ([de6d16d](https://github.com/PhishStick-hub/samstack/commit/de6d16df4e286e4b830de023b744ab87a824f71c))
* **12:** create phase plans for integration testing, CI, docs, and benchmarking ([9bbe758](https://github.com/PhishStick-hub/samstack/commit/9bbe758f3315c31d9e5f3949a1842c5aed1d2ed3))
* **12:** record UAT results — 4/5 passed, 1 skipped (crash test macOS) ([d3e9f92](https://github.com/PhishStick-hub/samstack/commit/d3e9f922a1af2cc66fb3660f6c50db1adda4def4))
* complete project research for v2.3.0 pytest-xdist ([b254757](https://github.com/PhishStick-hub/samstack/commit/b2547578457be23bbc0316cd2d8c11c3dce8900c))
* create milestone v2.3.0 roadmap (5 phases, 22 reqs) ([68f7c27](https://github.com/PhishStick-hub/samstack/commit/68f7c27030fafcb02494dac56eb51845c9056971))
* define milestone v2.3.0 requirements (22 reqs, 5 categories) ([1d6441d](https://github.com/PhishStick-hub/samstack/commit/1d6441d247bcffb1757c13b3a109fc121b61b989))
* fix stale version references in README ([d8b2237](https://github.com/PhishStick-hub/samstack/commit/d8b22372def1a0b97b992267c899742013de9185))
* merge Installation + Minimal setup into Quick start section ([834c9de](https://github.com/PhishStick-hub/samstack/commit/834c9de7b88de7dd9db2a6f7950332bbcb27083d))
* **milestone:** complete v2.3.0 pytest-xdist support milestone ([c12406d](https://github.com/PhishStick-hub/samstack/commit/c12406d6b6cdacd2a77448f8194d7329729b2a02))
* **phase-08:** update tracking after waves 1-2 ([dd18b17](https://github.com/PhishStick-hub/samstack/commit/dd18b1768005d70dddac7b52c051bcf8073fca2e))
* **phase-09:** add validation strategy with Nyquist compliance sign-off ([97b9b99](https://github.com/PhishStick-hub/samstack/commit/97b9b990a1cd4bcf5c2d697c60b71be6acd63878))
* **phase-09:** add/update security threat verification ([7fef0a5](https://github.com/PhishStick-hub/samstack/commit/7fef0a5c6933ad6ffcbf6856483371afe409e8d3))
* **phase-09:** mark phase complete and transition to Phase 10 ([bb5cbc1](https://github.com/PhishStick-hub/samstack/commit/bb5cbc1532d583448e6f5e41624370c276666239))
* **phase-09:** update tracking after wave 1 ([28e6dda](https://github.com/PhishStick-hub/samstack/commit/28e6dda612ff5fe1092e8269362fb611f4981cbf))
* **phase-12:** complete phase execution .planning/ROADMAP.md .planning/STATE.md .planning/REQUIREMENTS.md .planning/phases/12-integration-testing-ci-docs-benchmarking/12-VERIFICATION.md ([f37a7b2](https://github.com/PhishStick-hub/samstack/commit/f37a7b221a2315d24db96ff69e8bdb47619b6895))
* **phase-12:** evolve PROJECT.md after phase completion .planning/PROJECT.md ([17726ac](https://github.com/PhishStick-hub/samstack/commit/17726ac339912393ddba9db42ddcbbdaf4e08dfe))
* **phase-12:** update tracking after wave 1 .planning/ROADMAP.md .planning/STATE.md ([67de944](https://github.com/PhishStick-hub/samstack/commit/67de94494f42509fa7134e90e576c39fa63ae387))
* start milestone v2.3.0 pytest-xdist support ([52e8f8b](https://github.com/PhishStick-hub/samstack/commit/52e8f8b7f6d3e8d629d7702ea085a11ecdab6db3))

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
