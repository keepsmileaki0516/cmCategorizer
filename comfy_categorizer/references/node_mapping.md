# ノードマッピング仕様

## DualPromptEncoderノードの検出

`get_dual_prompt_encoder_nodes()`メソッドで以下を検出:

1. workflow内の全ノードを走査
2. `class_type == "DualPromptEncoder"`のノードを抽出
3. `title`または`name`フィールドからノードタイトルを取得

## titleの処理

ノードタイトルはカンマ区切りで複数指定可能:
- `"all,nsfw"` → allカテゴリとnsfwカテゴリの両方の単語を結合
- `"head,face,hair"` → headカテゴリにマッピング

## workflow_settings.jsonのマッピング

```json
{
  "workflow_types": {
    "default": {...},
    "detailed": {...},
    "nsfw_full": {...},
    "simple": {...}
  }
}
```

### default設定
- `all` → 全カテゴリ
- 個別のbody,clothing,limbs,pose,quality,background対応
- NSFWフィルタ有効

### detailed設定
- より細かいカテゴリマッピング
- face,hair,expression,skin,breasts,figure,outfit,accessories対応
- hands,feet,fingersをlimbsにマッピング

### nsfw_full設定
- NSFWフィルタ無効
- unclassifiedをinclude（除外しない）
- 全カテゴリ有効

### simple設定
- `all`のみ
- 単一プロンプトワークフロー向け

## get_safe_prompt_for_node(target_category)

`all`指定時は全カテゴリから単語を結合して返す。それ以外のカテゴリはそのカテゴリのみ。

## フォールバック動作

- DualPromptEncoderがない場合 → legacy mode
- 設定がない場合 → default workflow使用
- カテゴリ一致なし → 単語をプロンプトから除外