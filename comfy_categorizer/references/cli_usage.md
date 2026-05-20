# コマンドライン使用方法

## 基本構文

```bash
python comfy_categorizer.py [target_num],[workflow_type]
```

## 引数の説明

### target_num
- 省略 → 最新履歴または新規生成
- 数字指定 → その履歴番号を再生成
- 例: `5` → 5件目の履歴を再生成

### workflow_type
- `default` - 標準設定
- `detailed` - 詳細設定（顔・髪など細分化）
- `nsfw_full` - NSFW全許可
- `simple` - シンプル設定

## 使用例

```bash
# 最新プロンプトをdefault設定で実行
python comfy_categorizer.py

# 5件目をdetailed設定で再生成
python comfy_categorizer.py 5,detailed

# 3件目をnsfw_full設定で再生成
python comfy_categorizer.py 3,nsfw_full

# default設定で実行
python comfy_categorizer.py default
```

## 戻り値

- `"Success: <画像パス>"` - 生成成功＋Discord送信
- `"Success (no discord)"` - 生成成功（Discord送信なし）
- `"API Error: ..."` - APIエラー
- `{"error": "..."}` - 実行エラー

## エラー処理

- 3回連続エラー → テストスクリプト例を提案
- ComfyUI起動失敗 → エラーメッセージ出力
- タイムアウト → 最大10分待機後エラー

## Discordチャンネル設定

`openclaw.json`の`channels.discord.token`からBotToken取得。
`skills.entries.ComfyBridge.config.discord_target_channel`で送信先指定。