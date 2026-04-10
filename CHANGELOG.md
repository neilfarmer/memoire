# Changelog

## [0.10.0](https://github.com/neilfarmer/memoire/compare/v0.9.0...v0.10.0) (2026-04-10)


### Features

* **assistant:** AI profile — seed and inspect assistant memory ([#83](https://github.com/neilfarmer/memoire/issues/83)) ([f5819ce](https://github.com/neilfarmer/memoire/commit/f5819cecd849a59a5e6705daa1c2bee4bbaf06e9))
* **bookmarks:** bookmark manager with metadata scraping ([#94](https://github.com/neilfarmer/memoire/issues/94)) ([5bdc77d](https://github.com/neilfarmer/memoire/commit/5bdc77dca3092be0efdfa764afecbe552f976107))
* **finances:** financial snapshot tracker ([#90](https://github.com/neilfarmer/memoire/issues/90)) ([e0399b2](https://github.com/neilfarmer/memoire/commit/e0399b244d7ddf341a1ba2894bd27faca738eef5))
* **frontend:** mobile and tablet responsive layout ([#93](https://github.com/neilfarmer/memoire/issues/93)) ([1321d6c](https://github.com/neilfarmer/memoire/commit/1321d6ca2e8ff89b0ccd48e73027851281767299))
* Split about me and ai analysis page ([#85](https://github.com/neilfarmer/memoire/issues/85)) ([62d4aa4](https://github.com/neilfarmer/memoire/commit/62d4aa4480f866488371447ef2a734b3b65ad40f))


### Bug Fixes

* tokens UI, RSS autodiscovery, nutrition float fix, misc ([#92](https://github.com/neilfarmer/memoire/issues/92)) ([725ef81](https://github.com/neilfarmer/memoire/commit/725ef81007808f8979437a0eb86070b20e4f262f))

## [0.9.0](https://github.com/neilfarmer/memoire/compare/v0.8.0...v0.9.0) (2026-04-07)


### Features

* **assistant:** stream Bedrock response tokens via Lambda Function URL ([#80](https://github.com/neilfarmer/memoire/issues/80)) ([97f4b27](https://github.com/neilfarmer/memoire/commit/97f4b278e35b039b187e3ecc35ace6d698004a25))
* **diagrams:** Excalidraw diagramming feature ([#82](https://github.com/neilfarmer/memoire/issues/82)) ([1ea87a7](https://github.com/neilfarmer/memoire/commit/1ea87a785859c45697786ada76863bba018135d1))


### Bug Fixes

* **lambda:** redact headers from CloudWatch event logs ([#78](https://github.com/neilfarmer/memoire/issues/78)) ([6800282](https://github.com/neilfarmer/memoire/commit/6800282072c5f77a4badd70a3845fa0852371e64))

## [0.9.0] (2026-04-06)

### Features

* **diagrams:** Excalidraw integration — create, rename, and delete diagrams; full canvas with dark mode default; lazy-loaded from CDN
* **diagrams:** DynamoDB-backed persistence (title, elements, app_state) with 100-diagram cap per user
* **diagrams:** inline naming inputs replace browser prompts for new diagram and rename flows

### Bug Fixes

* **diagrams:** hide AI pal FAB on diagrams page to avoid covering Excalidraw help button
* **csp:** add unpkg.com to script-src and font-src for Excalidraw 0.17.6 lazy-loaded chunks and fonts
* **tests:** fix cross-feature sys.modules collision in conftest — bare stem always overwritten before exec_module

---

## [0.8.0](https://github.com/neilfarmer/memoire/compare/v0.7.0...v0.8.0) (2026-04-05)


### Features

* AI pal, themes, security scanning, and test coverage ([#68](https://github.com/neilfarmer/memoire/issues/68)) ([dcbcedd](https://github.com/neilfarmer/memoire/commit/dcbcedd41a6f50e4652f4035d87d8a841b1845e8))


### Bug Fixes

* **ci:** pin renovatebot/github-action to v46.1.7 ([a891bb1](https://github.com/neilfarmer/memoire/commit/a891bb11fb48d9fba25ffa459fcd153f6c709673))
* **ci:** update renovatebot/github-action to v46 ([285f7e4](https://github.com/neilfarmer/memoire/commit/285f7e4e98c4e5028429b93fbd67f5b3bc09402c))
* **terraform-tests:** supply valid JSON mock for aws_iam_policy_document ([2a18106](https://github.com/neilfarmer/memoire/commit/2a1810636ddfefc81341e5a5c9b078fd7c0345a0))
* **terraform-tests:** use one() for set-typed rule block in SSE assertion ([a22aed7](https://github.com/neilfarmer/memoire/commit/a22aed73371df64cd3c777997d57d89883273904))


### Reverts

* remove Infracost workflow (paid service) ([5592698](https://github.com/neilfarmer/memoire/commit/55926984f2daa2418fc5c6cfea6b53e975f8666e))

## [0.7.0](https://github.com/neilfarmer/memoire/compare/v0.6.0...v0.7.0) (2026-04-04)


### Features

* add unit test suite for all Lambda functions ([8cc45db](https://github.com/neilfarmer/memoire/commit/8cc45db25f11f7d2957c88ad143a5c3f142878ed))
* CI integration tests + content seeding script ([2fb8aaa](https://github.com/neilfarmer/memoire/commit/2fb8aaa5ac832e63a3b991dd50257e9bf743ec82))
* **ui:** UI improvements across all sections ([#66](https://github.com/neilfarmer/memoire/issues/66)) ([dc6479b](https://github.com/neilfarmer/memoire/commit/dc6479be6d5cc6f2d28bc7f497cc4b436428a26e))


### Bug Fixes

* /tokens routes break after cookie auth migration ([#25](https://github.com/neilfarmer/memoire/issues/25)) ([b895e06](https://github.com/neilfarmer/memoire/commit/b895e068f63e38c9b2a9fe4c1abc3ea5f2269e4e))
* /tokens routes break after cookie auth migration ([#25](https://github.com/neilfarmer/memoire/issues/25)) ([8d1ac8b](https://github.com/neilfarmer/memoire/commit/8d1ac8b33ac93feac254b610c2ac02b8b119fd31))
* **#10,#11,#16:** Makefile scripts, display_name setting, handler error handling ([74186b3](https://github.com/neilfarmer/memoire/commit/74186b3327d5adecda407efd443ca2ce278db421))
* **#10,#11,#16:** Makefile scripts, display_name setting, handler error handling ([05eb6fc](https://github.com/neilfarmer/memoire/commit/05eb6fca60427fcf5a3b67f46d7e36479f0a1c3a))
* **#12,#13,#24:** SSRF validation, XSS sanitization, per-Lambda IAM roles ([417c97e](https://github.com/neilfarmer/memoire/commit/417c97e99731db774a5ecb648e03528af3220cbb))
* **#17,#18,#21:** integration tests for health/nutrition/goals/export, cleanup on failure, parallel habit queries ([9f92a62](https://github.com/neilfarmer/memoire/commit/9f92a62263ebb4fce6ab644c6310f1625a59b532))
* **#17,#18,#21:** integration tests for health/nutrition/goals/export, test cleanup, parallel habit queries ([0aff2a6](https://github.com/neilfarmer/memoire/commit/0aff2a648c545e30fd4c6f6da231adfb3de0abfc))
* **#19,#22,#23:** CI linting, export OOM via S3 presigned URL, watcher query-per-user ([1b991c3](https://github.com/neilfarmer/memoire/commit/1b991c306788c71b03da3c1a48b3e08d9a8278fe))
* **#19,#22,#23:** CI linting, export OOM, watcher table scan ([06616e9](https://github.com/neilfarmer/memoire/commit/06616e9f0091b5bca57847b4c62388cc1b087072))
* **#26:** scope habit logs to user_id with habit_logs_v2 table ([247a5de](https://github.com/neilfarmer/memoire/commit/247a5defb1e022276b36c1f82e8e4f3873c08e77))
* **#28,#29,#30:** CORS lockdown, rate limiting, admin stats access control ([4c107ce](https://github.com/neilfarmer/memoire/commit/4c107cef64cad2d90886247312b2bb2c38258e9d))
* **#31,#32,#33:** attachment type validation, auth audit logging, input size limits ([c29d99b](https://github.com/neilfarmer/memoire/commit/c29d99bb01a2776be47aed186ac315bbd807e170))
* **#9,#14,#15:** DynamoDB pagination, S3 note/folder cleanup, habit log orphaning ([62866c5](https://github.com/neilfarmer/memoire/commit/62866c5af6258b6f8326e69eb1560878370d8583))
* **#9,#14,#15:** paginate DynamoDB queries, clean up S3 on note/folder delete, fix habit log orphaning ([b2a3a43](https://github.com/neilfarmer/memoire/commit/b2a3a4378f9e8c0ed21601208fae02551b75bdcc))
* accept 403 for PAT-blocked token operations in integration tests ([44923da](https://github.com/neilfarmer/memoire/commit/44923da3a84b2f6557f3080c0e57fed62f564f0e))
* attachment type validation, auth audit logging, input size limits ([#31](https://github.com/neilfarmer/memoire/issues/31), [#32](https://github.com/neilfarmer/memoire/issues/32), [#33](https://github.com/neilfarmer/memoire/issues/33)) ([f40c1db](https://github.com/neilfarmer/memoire/commit/f40c1db2884758aac55fe450a8a1e90d8a5e6292))
* **auth:** strip trailing slash from logout_uri ([#49](https://github.com/neilfarmer/memoire/issues/49)) ([c5b8b44](https://github.com/neilfarmer/memoire/commit/c5b8b44171289c12cf08177dabcddf70c4f6a429))
* **ci:** install requirements-test.txt before make test-unit in integration workflow ([d457125](https://github.com/neilfarmer/memoire/commit/d457125c63415a3441bca8c1a972c8defbda6fa7))
* CORS lockdown, rate limiting, admin stats access control ([#28](https://github.com/neilfarmer/memoire/issues/28), [#29](https://github.com/neilfarmer/memoire/issues/29), [#30](https://github.com/neilfarmer/memoire/issues/30)) ([e764fce](https://github.com/neilfarmer/memoire/commit/e764fce83cea773305918eb2a324f32c194f772d))
* **csp:** allow unsafe-inline scripts for SPA inline script block ([#48](https://github.com/neilfarmer/memoire/issues/48)) ([a11157b](https://github.com/neilfarmer/memoire/commit/a11157b137dadf8933d59c9fca3145d7452621ef))
* declare TEST_PAT environment in CI job to access environment secret ([ddc1bdf](https://github.com/neilfarmer/memoire/commit/ddc1bdff79560545cd7d0caef42763dc1f6105bc))
* handle identitySource as list in authorizer + migrate tests to PAT auth ([c1e3ac3](https://github.com/neilfarmer/memoire/commit/c1e3ac3c660fbed7f562a11e51466b88219daf37))
* make content deploy idempotent + fix invalid mood value ([e72b01b](https://github.com/neilfarmer/memoire/commit/e72b01bb14e9793b370a071c3d119a90f26734bb))
* pass TEST_PAT via env in CI workflow ([e9b681b](https://github.com/neilfarmer/memoire/commit/e9b681b046da020e5c99699cce188a65a34aae6d))
* S3 path traversal ([#27](https://github.com/neilfarmer/memoire/issues/27)) + habit logs user isolation ([#26](https://github.com/neilfarmer/memoire/issues/26)) ([66feb76](https://github.com/neilfarmer/memoire/commit/66feb764c1af3e4ff62752a1d54fb26a19636cf3))
* SSRF validation, XSS sanitization, per-Lambda IAM roles ([#12](https://github.com/neilfarmer/memoire/issues/12), [#13](https://github.com/neilfarmer/memoire/issues/13), [#24](https://github.com/neilfarmer/memoire/issues/24)) ([a77c3f7](https://github.com/neilfarmer/memoire/commit/a77c3f7703eafd249c5bd3353442b980c2236ac1))
* **terraform:** break CloudFront ↔ API Gateway cycle in response headers policy ([68c0fd1](https://github.com/neilfarmer/memoire/commit/68c0fd12b2c79b9353e974509e77547c217a5abd))
* **terraform:** properly break CloudFront ↔ API Gateway cycle in CSP ([300925f](https://github.com/neilfarmer/memoire/commit/300925f4deab48221d20efbe78bd08f0fbebabad))
* **terraform:** properly break CloudFront CSP dependency cycle ([f647558](https://github.com/neilfarmer/memoire/commit/f647558586522ce714b7bc7b50c031ea3b890ecf))
* update auth enforcement test to accept 403 ([efa13fc](https://github.com/neilfarmer/memoire/commit/efa13fc4f452bdcfac3a9c63dbf0f6af272f91d6))
* update test_habits.py for habit_logs_v2 schema ([247d128](https://github.com/neilfarmer/memoire/commit/247d1283994bf63b8644b3e75741fae9677dec3e))

## [0.6.0](https://github.com/neilfarmer/memoire/compare/v0.5.0...v0.6.0) (2026-03-30)


### Features

* add folder dropdown to task modal for moving tasks ([d0872f5](https://github.com/neilfarmer/memoire/commit/d0872f5049b44e763422cbd705bc5fb896af29c2))

## [0.5.0](https://github.com/neilfarmer/memoire/compare/v0.4.0...v0.5.0) (2026-03-30)


### Features

* add goals, habits, and task folders to export ([5bad612](https://github.com/neilfarmer/memoire/commit/5bad6129189c52cb6a1e3712d4ebd9b5dfb3483b))
* add timezone setting for date calculations ([755b3c2](https://github.com/neilfarmer/memoire/commit/755b3c249fd66a4d5c688f96fe03ea4dedcbe2cb))
* show journal, exercise, and nutrition day view on calendar click ([d2cc4da](https://github.com/neilfarmer/memoire/commit/d2cc4da5743340e80062302738718240404118c4))
* split tasks into user-created folders ([8c048ad](https://github.com/neilfarmer/memoire/commit/8c048adafb5f4faf0e71ce5189e58a3696d554e6))


### Bug Fixes

* preload health and nutrition so journal calendar dots appear ([e2aa4f9](https://github.com/neilfarmer/memoire/commit/e2aa4f99180812420b75717273b7839bed40a868))
* show journal body in day view (was using wrong field name) ([8026c2d](https://github.com/neilfarmer/memoire/commit/8026c2d77430fecedf5df2fd3ee133b3e4b155ca))

## [0.4.0](https://github.com/neilfarmer/memoire/compare/v0.3.0...v0.4.0) (2026-03-29)


### Features

* add name_prefix override and random bucket suffix ([09df66f](https://github.com/neilfarmer/memoire/commit/09df66f60aa7d955b14dc9aec666c63462cc89cc))

## [0.3.0](https://github.com/neilfarmer/memoire/compare/v0.2.0...v0.3.0) (2026-03-29)


### Features

* replace direct auth with OAuth PKCE flow ([734beb5](https://github.com/neilfarmer/memoire/commit/734beb59a9f0c75bcd77ab3d746da0ad9fe916c0))

## [0.2.0](https://github.com/neilfarmer/memoire/compare/v0.1.0...v0.2.0) (2026-03-29)


### Features

* prepare repo for public release as reusable Terraform module ([567c2bb](https://github.com/neilfarmer/memoire/commit/567c2bbb1ab39fce9f8273db7ed4496b2895bef0))
