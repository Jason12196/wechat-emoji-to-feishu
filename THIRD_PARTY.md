# Upstream sources

- [henrytian1998/wechatemoji](https://github.com/henrytian1998/wechatemoji), commit `ecd6b55ce0d1eac9f74babf50c3820a2074db22a`. MIT; original copyright and full license retained in LICENSE and engines/LICENSE.wechatemoji. The Python uploader, image helpers and configuration have been adapted into a package.
- [liusheng22/export-wechat-emoji](https://github.com/liusheng22/export-wechat-emoji), commit `f1196314b66eddbe4da2a8b958c8082b5945aa1f`. The CLI Cargo.toml declares MIT. CLI and key-dumper source retained under vendor/wxemoticon, including the original fishhook attribution comments.

Rust modifications: --metadata-out for private resource metadata; Rust 1.85-compatible time dependencies and integer remainder check. Python modifications: packaged imports, macOS extraction adapter, image validation/decryption/recovery, animated-image preparation, conservative personal-upload ledger.

This repository contains no WeChat databases, keys, resource URLs, browser profiles, user images or session recordings.
