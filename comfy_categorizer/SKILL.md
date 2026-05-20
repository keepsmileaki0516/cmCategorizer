---
name: icc
description: ComfyUIプロンプトをカテゴリ分類して画像を生成
---

# ComfyCategorizer Skill

## Overview
ComfyCategorizer extends ComfyBridge to automatically categorize prompts into predefined categories and route them to specific nodes in the workflow.

## Features

### Prompt Categorization
- Splits comma-separated prompts into individual words
- Matches words against 8 category dictionaries:
  - background.txt, body.txt, clothing.txt, head.txt, limbs.txt, nsfw.txt, pose.txt, quality.txt

### NSFW Filter
- Words matching nsfw.txt are completely excluded from generation
- NSFW terms are tracked for logging purposes

### Unclassified Word Handling
- Words not matching any category are saved to unclassified.txt
- Duplicate checking prevents redundant entries
- Unclassified words are excluded from generation

### Workflow Integration
- Detects DualPromptEncoder nodes by class_type and title
- Maps node titles to category dictionaries via workflow_settings.json
- Falls back to legacy mode if no DualEncoder is found

## Usage

### Basic Usage (Inherited from ComfyBridge)
```python
from comfy_categorizer import ComfyCategorizer

cc = ComfyCategorizer()
result = cc.draw(prompt="1girl, beautiful face, red hair", workflow_type="default")
```

### Direct Categorization
```python
cc = ComfyCategorizer()
result = cc.categorize_prompt("1girl, beautiful face, red hair, standing, high quality")
```

### Clean Prompt (NSFW Excluded)
```python
clean_prompt = cc.remove_nsfw_from_prompt("nsfw content, beautiful, high quality")
```

### Get Divided Prompts
```python
divided = cc.get_divided_prompt("1girl, red hair, standing")
```

## Configuration

Edit `workflow_settings.json` to customize:
- Workflow type definitions
- Node title to category mappings
- NSFW filter settings
- Unclassified word handling

## Node Detection Logic

1. Scan workflow for nodes with class_type == "DualPromptEncoder"
2. Extract node title from "title" or "name" field
3. Match title against workflow_settings.json node_category_mapping
4. Route categorized prompts to matching nodes

## Error Handling
- No error output during execution
- After 3 consecutive errors, suggests a minimal test script
- Designed for one-shot execution to minimize token usage