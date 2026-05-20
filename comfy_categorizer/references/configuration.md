# 設定と設定ファイルの詳細仕様

## 設定ファイルの場所

`~/.openclaw/openclaw.json`（USERPROFILE環境変数使用）

## 設定の読み込み方法

1. JSONファイルをUTF-8で読み込み
2. `skills.entries.ComfyBridge.config`から取得
3. 辞書アクセスを安全に処理（途中に文字列があっても無視）

## 読み込まれる設定項目

```python
self.api_url = config.get("comfyui_api_url", "127.0.0.1:8188")
self.comfy_path = config.get("comfy_path", "C:\\Users\\owner\\Downloads\\Data\\Packages\\ComfyUI")
self.history_dir = config.get("history_dir", ...)
self.discord_token = config.get("discord.token")
self.target_channel = config.get("discord_target_channel", "1498225996149817415")
```

## カテゴリ辞書ファイル

`categorized_prompts/`フォルダ内の`.txt`ファイル:
- `background.txt` - 背景・環境関連
- `body.txt` - 身体・解剖学関連
- `clothing.txt` - 服装・装飾関連
- `head.txt` - 顔・髪・表情関連
- `limbs.txt` - 手・足・指関連
- `nsfw.txt` - 除外対象
- `pose.txt` - ポーズ・アクション
- `quality.txt` - 品質タグ
- `unclassified.txt` - 未分類語（自動生成）

## seedrandom.lock

- 生成処理のロック用ファイル
- 同時実行防止

## NSFWフィルタ設定

`workflow_settings.json`で以下を設定:
- `nsfw_categories.filter_enabled` - フィルタ有効/無効
- `nsfw_categories.action_on_detect` - 検出時の動作

## unclassifiedHandling

```json
{
  "save_to_file": true,
  "file_path": "unclassified.txt",
  "check_duplicates": true,
  "exclude_from_generation": true
}
```