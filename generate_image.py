#!/usr/bin/env python
"""
Command-line tool for generating images using Replicate API with the flux-lora-uncensored model.
"""

import os
import sys
import argparse
import time
import requests
from pathlib import Path
import replicate
from PIL import Image

# Constants
REPLICATE_API_KEY = "REDACTED_REPLICATE_KEY_1"
HUGGING_FACE_TOKEN = "REDACTED_HF_TOKEN"
DEFAULT_MODEL = "stability-ai/sdxl:c221b2b8ef527988fb59bf24a8b97c4561f1c671f73bd389f866bfb27c061316"
DEFAULT_NEGATIVE_PROMPT = "deformed, bad anatomy, disfigured, poorly drawn face, mutation, mutated, extra limb, ugly, disgusting, poorly drawn hands, missing limb, floating limbs, disconnected limbs, malformed hands, blurry, watermark, watermarked, oversaturated, censored, distorted, text, low quality, worst quality"

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Generate images using the Replicate API with flux-lora-uncensored model')
    parser.add_argument('prompt', help='Text prompt for image generation')
    parser.add_argument('--output', '-o', default='generated_image.png', help='Output file path')
    parser.add_argument('--width', '-W', type=int, default=1024, help='Image width')
    parser.add_argument('--height', '-H', type=int, default=1024, help='Image height')
    parser.add_argument('--steps', '-s', type=int, default=50, help='Number of inference steps')
    parser.add_argument('--guidance', '-g', type=float, default=7.5, help='Guidance scale')
    parser.add_argument('--lora-scale', '-l', type=float, default=0.9, help='LoRA scale')
    parser.add_argument('--no-trigger', action='store_true', help='Disable automatic trigger words')
    
    return parser.parse_args()

def add_trigger_words(prompt):
    """Add trigger words if not already present in the prompt"""
    trigger_words = ["porn", "nude", "sex", "boobs"]
    if not any(word.lower() in prompt.lower() for word in trigger_words):
        return f"porn, nude, sex, boobs, {prompt}"
    return prompt

def generate_image(prompt, output_path, width, height, steps, guidance_scale, lora_scale, use_trigger_words=True):
    """Generate image using Replicate API"""
    # Set environment variable for API key
    os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_KEY
    
    # Add trigger words if needed
    if use_trigger_words:
        prompt = add_trigger_words(prompt)
        
    print(f"Generating image with prompt: {prompt}")
    print(f"Parameters: width={width}, height={height}, steps={steps}, guidance={guidance_scale}, lora_scale={lora_scale}")
    
    # Prepare input parameters
    input_params = {
        "prompt": prompt,
        "negative_prompt": DEFAULT_NEGATIVE_PROMPT,
        "width": width,
        "height": height,
        "num_outputs": 1,
        "scheduler": "K_EULER_ANCESTRAL",
        "num_inference_steps": steps,
        "guidance_scale": guidance_scale,
        "lora_scale": lora_scale,
        "prompt_strength": 0.8,
        "apply_watermark": False,
        "high_noise_frac": 0.8,
        "refine": "expert_ensemble_refiner",
        "refine_steps": 25,
        "lora": "https://huggingface.co/aifeifei798/flux-lora-uncensored/resolve/main/flux_lora_v1.safetensors"
    }
    
    # Call the Replicate API
    try:
        print("Sending request to Replicate API...")
        output = replicate.run(DEFAULT_MODEL, input=input_params)
        
        # Output will be a list with one or more image URLs
        image_url = output[0]
        print(f"Image generated! URL: {image_url}")
        
        # Download and save the image
        print(f"Downloading image to {output_path}...")
        response = requests.get(image_url)
        if response.status_code == 200:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            
            # Save the image
            with open(output_path, 'wb') as f:
                f.write(response.content)
                
            # Open the image to verify it was saved correctly
            try:
                img = Image.open(output_path)
                print(f"Image saved successfully: {output_path} ({img.width}x{img.height})")
            except Exception as e:
                print(f"Image saved but could not be opened: {e}")
                
            return output_path
        else:
            print(f"Error downloading image: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"Error generating image: {e}")
        return None

def main():
    """Main function"""
    # Parse arguments
    args = parse_arguments()
    
    # Generate the image
    output_path = generate_image(
        args.prompt,
        args.output,
        args.width,
        args.height,
        args.steps,
        args.guidance,
        args.lora_scale,
        not args.no_trigger
    )
    
    # Print result
    if output_path:
        print(f"\nImage generated successfully!")
        print(f"Output file: {os.path.abspath(output_path)}")
        
        # Try to display the image
        if sys.platform == "win32":
            os.startfile(output_path)
        elif sys.platform == "darwin":  # macOS
            os.system(f'open "{output_path}"')
        else:  # Linux
            os.system(f'xdg-open "{output_path}"')
    else:
        print("\nImage generation failed.")
        sys.exit(1)

if __name__ == "__main__":
    start_time = time.time()
    main()
    elapsed_time = time.time() - start_time
    print(f"Time elapsed: {elapsed_time:.2f} seconds")
