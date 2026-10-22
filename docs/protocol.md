# CLI protocol v1

Invoke a single process per operation, e.g. `wechat-emoji --json --home STATE_DIR extract --out OUTPUT_DIR`.

Read stdout line by line; do not wait for a complete JSON array. Read stderr concurrently to avoid blocking the process. The final result/error event and process exit code together define completion. `action_required` asks the UI to show login instructions; it does not grant additional privileges.

```json
{"protocol_version":1,"task_id":"UUID","type":"started","time":"UTC ISO8601","command":"extract"}
{"protocol_version":1,"task_id":"UUID","type":"progress","time":"UTC ISO8601","current":50,"total":996,"message":"Validating images"}
{"protocol_version":1,"task_id":"UUID","type":"result","time":"UTC ISO8601","status":"complete","code":null,"result":{"exported":996}}
```

Error example:

```json
{"protocol_version":1,"task_id":"UUID","type":"error","time":"UTC ISO8601","status":"failed","code":"CAPACITY_EXCEEDED","result":{"message":"Import selection exceeds available capacity"}}
```

`--json feishu plan` may complete successfully with `fits:false`: planning itself succeeded, but import must not proceed. `feishu import` enforces the plan again before opening a browser.

Do not treat a missing progress percentage as zero progress or failure: the external extraction engine has stages where only phase messages are available. User cancellation uses SIGINT; do not blindly re-launch an interrupted import, because the current batch may already have reached Feishu.

Account names are local profile labels. The caller must ensure that the actual browser login corresponds to the intended account and provide the current personal-sticker count. The CLI does not claim to have independently verified a remote account ID or remaining quota.
