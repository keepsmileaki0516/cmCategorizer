# 画像生成の詳細仕様

## draw()メソッドのフロー

1. **Civitai API呼び出し** - `_fetch_and_process_new()`でプロンプト送信
2. **ワークフロー更新** - カテゴリ分類結果をノードに適用
3. **ComfyUI実行** - APIで画像生成開始
4. **完了待機** - 最大10分（300回 × 2秒）
5. **Discord送信** - 生成完了画像を指定チャンネルに送信

## Civitai API連携

`fetch_civitai(prompt)`で以下を実行:
- API URL + `/v1/image/interrogate` にPOST
- プロンプトをbase64エンコードして送信
- 応答から画像URLを抽出

## Discord送信

- Bot.Token使用
- target_channel: 1498225996149817415
- 画像ファイルを送信

## 履歴管理

`processed_urls.txt`に処理済みURLを記録:
- 重複チェック
- 新規URLのみ追加
- 改行区切りで保存