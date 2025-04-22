# AI Image Generator Launcher Instructions

This application comes with two launcher options to fit different user preferences:

## Option 1: `run_image_generator.bat` (With Console)

**Recommended for first-time use and troubleshooting**

This launcher shows a command console window with detailed debugging information. It's helpful when:
- You're running the application for the first time
- You encounter issues and need to see error messages
- You want to see what's happening behind the scenes

Simply double-click `run_image_generator.bat` to start the application with the console visible.

## Option 2: `run_image_generator_hidden.vbs` (No Console)

**Recommended for regular use after confirming everything works**

This launcher runs the application without showing any command console window, providing a cleaner experience. It's ideal for:
- Regular daily use after you've confirmed everything works
- A cleaner desktop experience without extra windows
- Creating shortcuts on your desktop or start menu

Simply double-click `run_image_generator_hidden.vbs` to start the application without any console window.

## Troubleshooting

If you encounter any issues with the application:

1. Always try the `run_image_generator.bat` launcher first to see error messages
2. Check the `app_debug.log` file for detailed error information
3. If using the hidden launcher and it fails, check `vbs_launcher_error.log`

## First-Time Setup

When running for the first time:

1. The launcher will check if all required packages are installed, and install them if needed
2. It will create the output directory (`generated_images`) if it doesn't exist
3. A placeholder image will be created for display until you generate your first image
4. The configuration file will be created with default settings
5. You'll need to use your own API keys for the services:
   - Replicate API key (get from replicate.com)
   - HuggingFace token (get from huggingface.co)

## Using Hugging Face Models (Including Flux)

When using Hugging Face for the first time:
1. Select "Hugging Face" in the service selector
2. Select your model (Flux models are pre-configured)
3. Select your LoRA if desired
4. Wait for the model to download (this may take some time on first run)
5. Once downloaded, the model will be ready to use

Note: Using Hugging Face models requires more RAM and disk space. A GPU is highly recommended for acceptable performance.
