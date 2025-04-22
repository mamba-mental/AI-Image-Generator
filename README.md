# AI Image Generator with Hugging Face & Replicate API

This project provides tools to generate images using Stability AI's SDXL model with the flux-lora-uncensored LoRA via the Replicate API. The implementation offers both a simple command-line interface and a more feature-rich GUI application.

## Features

- Generate high-quality images using the Replicate API
- Automatic integration with the flux-lora-uncensored LoRA
- Support for customizing generation parameters (size, steps, guidance scale)
- Optional trigger words for the uncensored model
- Command-line interface for quick generation
- GUI application with advanced features and batch processing

## Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/ai-image-generator.git
cd ai-image-generator
```

2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

## Configuration

The application comes pre-configured with the provided API keys:

- Replicate API Key: `REDACTED_REPLICATE_KEY_1`
- Hugging Face Token: `REDACTED_HF_TOKEN`

If you need to use different API keys, you can modify them in:
- The command-line script: Edit the constants at the top of `generate_image.py`
- The GUI application: Use the "Configure API Keys" button in the application interface

## Usage

### Command-Line Interface

The `generate_image.py` script provides a simple command-line interface:

```bash
python generate_image.py "your prompt here"
```

#### Options:

- `--output`, `-o`: Output file path (default: generated_image.png)
- `--width`, `-W`: Image width (default: 1024)
- `--height`, `-H`: Image height (default: 1024)
- `--steps`, `-s`: Number of inference steps (default: 50)
- `--guidance`, `-g`: Guidance scale (default: 7.5)
- `--lora-scale`, `-l`: LoRA scale (default: 0.9)
- `--no-trigger`: Disable automatic trigger words

#### Example:

```bash
python generate_image.py "a beautiful woman in a red dress on the beach" --width 768 --height 1024 --steps 30
```

### GUI Application

For a more user-friendly experience, run the GUI application:

```bash
python app.py
```

The GUI application offers additional features:
- Custom parameter adjustment with sliders
- Negative prompt customization
- Batch image generation
- Image saving and history tracking
- Support for multiple models and services

## Working with Uncensored Models

When working with the flux-lora-uncensored model, certain trigger words help produce the desired output. By default, the application adds these trigger words (porn, nude, sex, boobs) to your prompt if they're not already present.

For best results:
- Include explicit descriptions in your prompt
- Adjust the LoRA scale (0.7-1.0 works best)
- Experiment with guidance scales (7-9 for balanced results)
- Use longer generation steps (50+) for higher quality

To disable the automatic inclusion of trigger words, use the `--no-trigger` flag for the command-line tool or uncheck the "Auto-include trigger words" option in the GUI.

## Generated Images

All generated images are saved to the `generated_images` directory by default. You can change this location in the GUI application.

## Limitations

- The Replicate API requires internet connectivity and consumes API credits
- Image generation may take 15-60 seconds depending on parameters
- The implemented Hugging Face integration is not fully functional yet

## Legal Disclaimer

Users are responsible for ensuring they have proper permissions and rights to generate any content. Please adhere to legal and ethical standards when using this tool.

## Credits

This project uses:
- [Stability AI's SDXL model](https://stability.ai/stablediffusion) via Replicate API
- [flux-lora-uncensored](https://huggingface.co/aifeifei798/flux-lora-uncensored) by aifeifei798
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) for the GUI interface
