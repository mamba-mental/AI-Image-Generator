# AI Image Generator with Hugging Face, Replicate & Gemini API

Multi-backend AI image generator with a Python/Tkinter GUI. Supports Replicate API, Hugging Face Inference API, and Google Gemini image generation (free tier).

## Features

- **Three generation backends:** Replicate API, Hugging Face, and Google Gemini
- **Gemini integration:** Free tier with ~500 images/day per key, no credit card required
- Automatic integration with the flux-lora-uncensored LoRA (Replicate/HF)
- Support for customizing generation parameters (size, steps, guidance scale)
- Optional trigger words for uncensored models
- Command-line interface for quick generation
- GUI application with advanced features and batch processing

## Installation

1. Clone this repository:
```bash
git clone https://github.com/mamba-mental/AI-Image-Generator.git
cd AI-Image-Generator
```

2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

## Configuration

You need to provide your own API keys. Create a `.env` file in the project root:

```
REPLICATE_API_TOKEN=your_replicate_api_key_here
HUGGINGFACE_TOKEN=your_huggingface_token_here
GEMINI_API_KEY=your_gemini_api_key_here
```

**Gemini API Key (Free):** Get one at [ai.google.dev](https://ai.google.dev) -- no credit card required, ~500 free images/day.

You can also configure keys through:
- The GUI application: Use the "Configure API Keys" button in the application interface
- The command-line script: Set the environment variables above

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
- Support for multiple models and services (Replicate, Hugging Face, Gemini)
- Gemini models: gemini-2.5-flash-image (recommended), gemini-3-pro-image-preview (highest quality), gemini-3.1-flash-image-preview

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
