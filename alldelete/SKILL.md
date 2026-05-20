---
name: alldelete
description: Discordチャンネル内の全てのメッセージを削除します。「/alldelete」で実行。サブエージェントで長時間処理を行います。
---

# Discord All Delete

指定されたDiscordチャンネルのすべてのメッセージを削除します。

### Usage

```bash
# チャンネルIDを指定して実行
python -c "from skills.alldelete.DiscordDeleter import run; run('CHANNEL_ID')"

# デフォルトチャンネルに执行
python -c "from skills.alldelete.DiscordDeleter import run; run()"
```

### 特性

- **1件ずつ削除**: API制限を避けるため0.5秒間隔で処理
- **長時間実行**: 最大5000件まで処理可能
- **サブエージェント推奨**: タイムアウトを防ぐためバックグラウンド実行
- **botメッセージ含む**: チャンネル内の全メッセージを削除

### 注意事項

- 削除は取り消せません
- 処理に時間がかかる場合があります
- Bot権限が必要です