"""
FluxPromptImage - Discord command skill for generating images with Flux workflow.

Usage:
    /fpi <positive_prompt> [negative_prompt] [options]

Example:
    /fpi beautiful anime girl, blue eyes
    /fpi cyberpunk city --n 3
"""

import os
import json
import re
import logging
from typing import Optional, Dict, Any
from pathlib import Path

# Try to import OpenClaw tools (will fail if not available in skill environment)
try:
    from openclaw import skills
    from openclaw.tools import ComfyBridge
except ImportError:
    skills = None
    ComfyBridge = None


logger = logging.getLogger(__name__)


class FluxPromptImage:
    """
    Discord command skill that generates images using Flux workflow
    with user-provided positive prompts.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize FluxPromptImage.
        
        Args:
            config: Configuration dictionary with workflow settings
        """
        self.config = config or self._load_default_config()
        self.workflows_dir = Path(self.config.get('workflows_dir', 
                                            os.path.join(os.path.dirname(__file__), 
                                                          '..', '..', 'workflows')))
        self.output_dir = Path(self.config.get('output_directory', 'output'))
        
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize ComfyBridge if available
        if ComfyBridge:
            self.comfy_bridge = ComfyBridge()
        else:
            logger.warning("ComfyBridge not available. Image generation skipped.")
            self.comfy_bridge = None
    
    def _load_default_config(self) -> Dict[str, Any]:
        """Load default configuration."""
        # Try to load from skill's parent directory
        config_path = Path(__file__).parent / 'workflow_config.json'
        
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        return {
            'workflow_file': '05_flux.json',
            'positive_prompt_key': 'positive',
            'negative_prompt_key': 'negative',
            'prompt_placeholder': '__POSITIVE_PROMPT__',
            'output_directory': 'output',
            'max_images': 1,
            'enable_auto_delivery': False,
            'default_channel': None
        }
    
    def _load_workflow(self, workflow_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Load and process the workflow JSON.
        
        Args:
            workflow_path: Path to workflow JSON. Defaults to 05_flux.json in workflows_dir
            
        Returns:
            Processed workflow dictionary with prompts replaced
            
        Raises:
            FileNotFoundError: If workflow file not found
            ValueError: If workflow structure invalid
        """
        if not workflow_path:
            # Look for 05_flux.json in the expected location
            possible_paths = [
                self.workflows_dir / workflow_path,
                self.workflows_dir / '05_flux.json',
                Path(__file__).parent.parent / 'workflows' / workflow_path,
                Path(__file__).parent.parent.parent / 'workflows' / workflow_path
            ]
            
            for path in possible_paths:
                if path.exists():
                    workflow_path = path
                    break
            
        if not workflow_path:
            raise FileNotFoundError(
                f"Workflow file not found. Expected at: 05_flux.json "
                f"or in one of: {', '.join(str(p) for p in possible_paths)}"
            )
        
        with open(workflow_path, 'r', encoding='utf-8') as f:
            workflow = json.load(f)
        
        # Replace positive prompt placeholder
        if self.config.get('prompt_placeholder', '__POSITIVE_PROMPT__') in workflow:
            positive_prompt = self.config.get('positive_prompt_key', 'positive')
            placeholder = self.config.get('prompt_placeholder', '__POSITIVE_PROMPT__')
            
            # Handle both string and list values
            if isinstance(workflow, dict):
                for key in ['positive_prompt', positive_prompt]:
                    if key in workflow and isinstance(workflow[key], str):
                        workflow[key] = workflow[key].replace(placeholder, 
                                                                self._sanitize_prompt(
                                                                    workflow[key]
                                                                ))
                    elif key in workflow and isinstance(workflow[key], list):
                        workflow[key] = [
                            item.replace(placeholder, self._sanitize_prompt(item))
                            for item in workflow[key]
                        ]
                    elif key in workflow:
                        logger.warning(f"Workflow '{key}' is not a string/list, skipping replacement")
        
        return workflow
    
    def _sanitize_prompt(self, prompt: str) -> str:
        """
        Sanitize prompt input to prevent injection attacks.
        
        Args:
            prompt: Raw prompt string
            
        Returns:
            Sanitized prompt string
        """
        if not prompt:
            return ""
        
        # Remove null bytes
        prompt = prompt.replace('\x00', '')
        
        # Limit length
        max_length = 5000  # Reasonable limit for Flux
        prompt = prompt[:max_length]
        
        # Escape control characters
        prompt = re.sub(r'[\x00-\x1f]', '', prompt)
        
        return prompt
    
    def _generate_image(self, workflow: Dict[str, Any], 
                       image_count: int = 1,
                       seed: Optional[int] = None) -> list:
        """
        Generate image(s) using ComfyBridge.
        
        Args:
            workflow: Processed workflow dictionary
            image_count: Number of images to generate
            seed: Random seed (None for random)
            
        Returns:
            List of image file paths
        """
        if not self.comfy_bridge:
            raise RuntimeError("ComfyBridge not available. Cannot generate images.")
        
        # Prepare arguments for ComfyBridge
        args = {
            'workflow': workflow,
            'output_dir': self.output_dir,
            'seed': seed
        }
        
        # Add ComfyBridge-specific arguments
        if image_count > 1:
            args['batch_count'] = image_count
        else:
            args['batch_count'] = 1
        
        return self.comfy_bridge.execute(args)
    
    def _get_discord_channel(self) -> Optional[str]:
        """
        Get target Discord channel for delivery.
        
        Returns:
            Channel name or None if no channel specified
        """
        channel = self.config.get('default_channel')
        
        if channel:
            # Remove # prefix if present
            return channel.lstrip('#')
        
        return None
    
    def process(self, prompt: str, negative_prompt: Optional[str] = None,
               image_count: int = 1, seed: Optional[int] = None) -> Dict[str, Any]:
        """
        Main processing method for Discord command.
        
        Args:
            prompt: Positive prompt from command arguments
            negative_prompt: Negative prompt (optional)
            image_count: Number of images to generate
            seed: Random seed
            
        Returns:
            Dictionary with generation results
            
        Raises:
            ValueError: If prompt is invalid or empty
            FileNotFoundError: If workflow file not found
            RuntimeError: If generation fails
        """
        if not prompt:
            raise ValueError("Positive prompt cannot be empty")
        
        try:
            # Load workflow
            workflow = self._load_workflow()
            
            # Apply negative prompt if provided
            negative_key = self.config.get('negative_prompt_key', 'negative')
            if negative_prompt and negative_key in workflow:
                if isinstance(workflow[negative_key], str):
                    workflow[negative_key] = negative_prompt
                elif isinstance(workflow[negative_key], list):
                    workflow[negative_key] = [
                        negative_prompt if item == '__NEGATIVE_PROMPT__' else item
                        for item in workflow[negative_key]
                    ]
            
            # Generate images
            images = self._generate_image(
                workflow=workflow,
                image_count=image_count,
                seed=seed
            )
            
            # Prepare result
            result = {
                'success': True,
                'images': images,
                'prompt': prompt,
                'negative_prompt': negative_prompt,
                'image_count': len(images),
                'output_dir': str(self.output_dir),
                'seed': seed
            }
            
            # Add delivery information
            result['delivery'] = {
                'enabled': self.config.get('enable_auto_delivery', False),
                'channel': self._get_discord_channel()
            }
            
            return result
            
        except FileNotFoundError as e:
            logger.error(f"Workflow file not found: {e}")
            return {
                'success': False,
                'error': f"Workflow file not found: {e}",
                'suggestion': 'Please place 05_flux.json in the expected location'
            }
        except ValueError as e:
            logger.error(f"Invalid input: {e}")
            return {
                'success': False,
                'error': str(e)
            }
        except RuntimeError as e:
            logger.error(f"Generation error: {e}")
            return {
                'success': False,
                'error': str(e)
            }
        except Exception as e:
            logger.error(f"Unexpected error: {type(e).__name__}: {e}")
            return {
                'success': False,
                'error': f"Unexpected error: {type(e).__name__}: {e}"
            }
    
    def draw(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Alternative method name for compatibility.
        
        Args:
            prompt: Positive prompt
            
        Returns:
            Processing result
        """
        return self.process(prompt, **kwargs)


def main():
    """
    Standalone test script.
    """
    print("FluxPromptImage Skill")
    print("=" * 50)
    print("Usage: /fpi <positive_prompt> [negative_prompt] [options]")
    print()
    print("Examples:")
    print('  /fpi beautiful anime girl, blue eyes')
    print('  /fpi cyberpunk city --n 3')
    print('  /fpi anime landscape --seed 42')
    print()
    print("Available options:")
    print("  --n <count>    Number of images to generate (default: 1)")
    print("  --seed <num>   Random seed (optional)")
    print("  --channel <name> Target Discord channel (optional)")
    print()
    print("Files required:")
    print("  - workflows/05_flux.json (or 05_flux.json in workspace)")
    print()
    print("Press Ctrl+C to exit")
    
    # Keep running until interrupted
    try:
        while True:
            user_input = input("Enter prompt or 'quit': ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("Exiting...")
                break
            
            if not user_input:
                continue
            
            parts = user_input.split()
            if not parts:
                continue
            
            prompt = ' '.join(parts)
            
            # Parse options
            image_count = 1
            seed = None
            
            i = 0
            while i < len(parts):
                if parts[i] == '--n' and i + 1 < len(parts):
                    image_count = int(parts[i + 1])
                    i += 2
                elif parts[i] == '--seed' and i + 1 < len(parts):
                    seed = int(parts[i + 1])
                    i += 2
                else:
                    i += 1
            
            print(f"\nGenerating image with prompt: {prompt}")
            print(f"Negative prompt: (not provided)")
            print(f"Images: {image_count}")
            print(f"Seed: {seed if seed else 'random'}")
            print("-" * 50)
            
            # In a real environment, this would generate and display the image
            # For now, just show what would happen
            print(f"Would generate: [{image_count}] image(s)")
            print(f"Output would be placed in: output/")
            print(f"Delivery would be sent to Discord channel")
            print()
            
    except KeyboardInterrupt:
        print("\n\nProgram interrupted by user.")


if __name__ == "__main__":
    main()
