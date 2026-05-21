---
name: FluxPromptImage
description: Discord コマンドを使用して、05_flux.json ワークフローのポジティブプロンプトを引数で置き換え画像生成
---

# FluxPromptImage Skill

## Overview
FluxPromptImage extends Discord capabilities to generate images using ComfyUI with user-provided prompts and automatically deliver results to Discord channels.

## Features

### Workflow Integration
- Uses `05_flux.json` workflow as the base
- Accepts positive prompts as command arguments
- Replaces placeholder prompts in the workflow configuration
- Executes image generation via ComfyBridge

### Discord Delivery
- Automatically sends generated images to the Discord channel where the command was invoked
- Includes prompt details and image metadata in the delivery message
- Handles image attachment and proper formatting for Discord

### Prompt Handling
- Parses prompt arguments from Discord command
- Validates and sanitizes input prompts
- Replaces workflow's positive prompt placeholder
- Generates single image or batch based on prompt configuration

## Usage

### Basic Usage
```python
from FluxPromptImage import FluxPromptImage

fpi = FluxPromptImage()
result = fpi.generate(prompt="beautiful anime girl, blue eyes")
```

### Discord Command
```
/fpi beautiful anime girl, blue eyes
```

## Configuration

### Required Files
- `05_flux.json` - ComfyUI workflow with positive prompt placeholder
- `workflow_config.json` - Workflow settings (optional, defaults to workspace)
- `positive_prompt_placeholder.txt` - Placeholder string for replacement

### Workflow Settings (workflow_config.json)
```json
{
  "workflow_file": "05_flux.json",
  "positive_prompt_key": "positive",
  "negative_prompt_key": "negative",
  "prompt_placeholder": "__POSITIVE_PROMPT__",
  "output_directory": "output",
  "max_images": 1,
  "enable_auto_delivery": true,
  "default_channel": null
}
```

## Command Syntax

```
/fpi <positive_prompt> [negative_prompt] [options]
```

### Arguments
- `positive_prompt`: Required. The positive prompt to use for generation
- `negative_prompt`: Optional. Negative prompt (defaults to workflow's negative if not provided)
- `--n`: Number of images (optional, defaults to 1)
- `--seed`: Random seed (optional)
- `--channel`: Target Discord channel (optional, overrides default)

### Examples

```
/fpi beautiful girl, long hair --n 3
/fpi cyberpunk city, neon lights --seed 42
/fpi anime landscape, sunset --n 2 --channel #images
```

## Implementation Notes

1. **Prompt Replacement**: 
   - Searches workflow JSON for the positive prompt placeholder
   - Replaces with provided positive prompt
   - Preserves negative prompt structure

2. **Image Generation**:
   - Executes via ComfyBridge with modified workflow
   - Monitors execution progress
   - Retrieves generated image paths

3. **Discord Delivery**:
   - Reads delivery configuration from workflow_config.json
   - Attaches generated images to Discord message
   - Includes prompt and metadata in message text

## Error Handling
- Invalid prompts are rejected with helpful error messages
- Missing workflow files are reported with file paths
- Execution failures trigger automatic retry or error reporting
- Discord delivery errors are caught and logged without stopping execution

## Security
- Prompt input is sanitized to prevent injection
- Output directory is restricted to configured workspace
- No external model downloads without explicit configuration
- Rate limiting recommended for Discord channel delivery
