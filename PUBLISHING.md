# Publishing TEM graph tool updates

Repository: https://github.com/Greenbean0123/TEM-graph-tool

The bundled update address is `https://github.com/Greenbean0123/TEM-graph-tool/releases/latest/download/updates.json`.

## Signing key

The public Ed25519 verification key is in outputs/update_config.json. The matching private key is stored outside this checkout, under `%LOCALAPPDATA%/TEM Studio Publisher/update-signing-key.pem` on the publisher's Windows PC. Keep a protected backup; existing installations trust this key. Never commit it, print it in build logs, or bundle it in the app.

GitHub repository Actions secret `TEM_SIGNING_KEY` contains the private PEM. It is used only by the publish job, after all three platform builds succeed. The repository stores only the public key. Restore the secret from the protected private-key file if necessary.

## Release

1. Make changes and set a higher `major.minor.patch` version in outputs/app_version.py.
2. Run outputs/test_updates.py and outputs/test_tem_studio.py. Build locally if desired using outputs/build_app.py.
3. Commit the source, then push a matching tag such as `v1.1.1`.
4. The workflow builds and tests Windows x64, Mac Apple Silicon and Mac Intel. Each frozen app checks its own PDF export, statistics, scrolling and updater verification.
5. After all builds pass, the publish job assembles SHA256/size metadata, signs updates.json, and publishes a GitHub Release containing every platform asset.

Manual workflow dispatch builds artifacts without publishing. Failed builds do not publish a partial release or update manifest. Re-run a failed workflow before publishing, rather than manually editing a signed manifest.

## End-user update behavior

Startup checks run in a background thread. An available newer version prompts for confirmation, then downloads and verifies the platform-specific asset. The updater stages replacement, saves the current session, exits the app and replaces it using a detached helper. The previous executable/app remains as a recovery backup until the replacement signals successful startup. Startup failure restores and relaunches the previous version.

Mac packages must contain TEM-Studio.app with bundle identifier org.temstudio.app, matching version, architecture and a valid code signature. An app launched from a mounted DMG must first be moved to a writable local location. Source installations do not replace their own source tree.

## Limitations

Before the first successful GitHub Release, the configured latest-manifest URL will return not found; automatic checks stay quiet while manual checks report the error. Old versions created before updater support need one manual upgrade. Apple Developer ID signing/notarization is not configured; Mac builds use ad-hoc signatures.
