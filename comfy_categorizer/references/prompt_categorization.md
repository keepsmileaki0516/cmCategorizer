# プロンプト分類の詳細仕様

## categorize_prompt(prompt) メソッド

プロンプト文をカテゴリ別に分類する。

### 処理フロー

1. **カンマ区切りで単語分割** - プロンプトを`,`で分割して単語単位にする
2. **単語クリーニング** - 各単語から以下を取り除く:
   - LoRAタグ: `<type:variant>`, `<lora:xxx:weight>`
   - 括弧: `(word)`, `[word]`
   - 重み記号: `:` (重み指定)
3. **カテゴリ照合** - クリーニング後の単語を8カテゴリ辞書と照合:
   - `background.txt` - 背景・環境
   - `body.txt` - 身体
   - `clothing.txt` - 服装
   - `head.txt` - 頭部（顔・髪）
   - `limbs.txt` - 手足
   - `nsfw.txt` - NSFW除外語
   - `pose.txt` - ポーズ
   - `quality.txt` - 品質指定
4. **分類結果保存** - 結果を`self.categories`辞書に格納

### unclassified処理

- どのカテゴリにも一致しない単語を`unclassified`に追加
- 重複チェック后才える
- `unclassified.txt`に保存（設定による）

### 重み処理

- `(word:1.2)` のような重み付き単語から重み部分を分離
- 重み付き単語は cleaning_priority_weights リストに保存
- 最終プロンプト生成時に再付与可能