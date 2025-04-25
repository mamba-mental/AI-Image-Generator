import os
import io
import sys
import json
import time
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageDraw, ImageFont
import requests
import replicate
import customtkinter as ctk

# Set appearance mode and default theme
ctk.set_appearance_mode("System")  # Modes: "System" (standard), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"

class ImageGeneratorGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Initialize configuration
        self.config = self.load_config()
        
        # Configure the window
        self.title("AI Image Generator")
        self.geometry("1200x800")
        self.minsize(900, 600)
        
        # Set up the main layout
        self.setup_layout()
        
        # Set up the service abstraction layer
        self.setup_services()
        
        # Create UI components
        self.create_header()
        self.create_service_toggle()
        self.create_prompt_section()
        self.create_parameters_section()
        self.create_model_section()
        self.create_output_section()
        self.create_image_display()
        self.create_status_bar()
        
        # Initialize default values
        self.initialize_default_values()
        
        # Variable to store the current image path
        self.current_image_path = None
        
        # Flag to track if generation is in progress
        self.is_generating = False
        
        # Track the number of images generated in the current session
        self.generation_count = 0

    def load_config(self):
        """Load configuration from JSON file or create default if not exists"""
        config_path = "config.json"
        default_config = {
            "replicate_api_key": "REDACTED_REPLICATE_KEY_1",
            "huggingface_token": "REDACTED_HF_TOKEN",
            "output_directory": os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated_images"),
            "service": "replicate",  # Default to replicate
            "last_used_model_replicate": "stability-ai/sdxl:c221b2b8ef527988fb59bf24a8b97c4561f1c671f73bd389f866bfb27c061316",
            "last_used_model_hf": "black-forest-labs/FLUX.1-dev",
            "last_used_lora_hf": "https://huggingface.co/aifeifei798/flux-lora-uncensored/resolve/main/flux_lora_v1.safetensors",
            "parameters": {
                "width": 1024,
                "height": 1024,
                "num_inference_steps": 50,
                "guidance_scale": 7.5,
                "prompt_strength": 0.8,
                "lora_scale": 0.9,
                "negative_prompt": "deformed, bad anatomy, disfigured, poorly drawn face, mutation, mutated, extra limb, ugly, disgusting, poorly drawn hands, missing limb, floating limbs, disconnected limbs, malformed hands, blurry, watermark, watermarked, oversaturated, censored, distorted, blurry, bad anatomy, disfigured, poorly drawn face, mutation, mutated, extra limb, ugly, poorly drawn hands, missing limb, floating limbs, disconnected limbs, malformed hands, oversaturated, censored, distorted, text, low quality, worst quality"
            },
            "advanced_mode": False,
            "recent_prompts": [],
            "recent_models_replicate": [
                "stability-ai/sdxl:c221b2b8ef527988fb59bf24a8b97c4561f1c671f73bd389f866bfb27c061316"
            ],
            "recent_models_hf": [
                "black-forest-labs/FLUX.1-dev"
            ],
            "recent_loras_hf": [
                "https://huggingface.co/aifeifei798/flux-lora-uncensored/resolve/main/flux_lora_v1.safetensors"
            ]
        }
        
        # Try to load existing config or create default
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    # Merge with default config to ensure all keys exist
                    for key, value in default_config.items():
                        if key not in config:
                            config[key] = value
                    # Create output directory if it doesn't exist
                    os.makedirs(config["output_directory"], exist_ok=True)
                    return config
            else:
                # Create output directory
                os.makedirs(default_config["output_directory"], exist_ok=True)
                # Save default config
                with open(config_path, 'w') as f:
                    json.dump(default_config, f, indent=4)
                return default_config
        except Exception as e:
            print(f"Error loading config: {e}")
            # Create output directory
            os.makedirs(default_config["output_directory"], exist_ok=True)
            return default_config
            
    def save_config(self):
        """Save configuration to JSON file"""
        try:
            with open("config.json", 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")
            messagebox.showerror("Error", f"Failed to save configuration: {e}")
    
    def setup_layout(self):
        """Set up the main layout with grid"""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)  # Image display area
        
    def setup_services(self):
        """Initialize service abstraction layer"""
        # Set environment variables for API keys
        os.environ["REPLICATE_API_TOKEN"] = self.config["replicate_api_key"]
        os.environ["HUGGINGFACE_TOKEN"] = self.config["huggingface_token"]
        
        # This is a placeholder - in a real implementation, we would initialize
        # the actual service clients for both Hugging Face and Replicate here
        self.service_clients = {
            "replicate": {"initialized": True},
            "huggingface": {"initialized": False, "model": None}
        }
        
    def create_header(self):
        """Create the header section of the GUI"""
        header_frame = ctk.CTkFrame(self)
        header_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")
        
        title_label = ctk.CTkLabel(
            header_frame, 
            text="AI Image Generator", 
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(side="left", padx=10, pady=10)
        
        # Advanced mode toggle
        self.advanced_mode_var = tk.BooleanVar(value=self.config["advanced_mode"])
        advanced_mode_switch = ctk.CTkSwitch(
            header_frame, 
            text="Advanced Mode",
            variable=self.advanced_mode_var,
            command=self.toggle_advanced_mode
        )
        advanced_mode_switch.pack(side="right", padx=10, pady=10)
        
    def create_service_toggle(self):
        """Create the service toggle section"""
        service_frame = ctk.CTkFrame(self)
        service_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        
        service_label = ctk.CTkLabel(
            service_frame, 
            text="Select Service:",
            font=ctk.CTkFont(size=16)
        )
        service_label.pack(side="left", padx=10, pady=10)
        
        self.service_var = tk.StringVar(value=self.config["service"])
        
        replicate_radio = ctk.CTkRadioButton(
            service_frame, 
            text="Replicate API",
            variable=self.service_var,
            value="replicate",
            command=self.on_service_change
        )
        replicate_radio.pack(side="left", padx=10, pady=10)
        
        huggingface_radio = ctk.CTkRadioButton(
            service_frame, 
            text="Hugging Face",
            variable=self.service_var,
            value="huggingface",
            command=self.on_service_change
        )
        huggingface_radio.pack(side="left", padx=10, pady=10)
        
        # Status indicators
        self.replicate_status = ctk.CTkLabel(
            service_frame, 
            text="✅ Ready",
            text_color="green",
            font=ctk.CTkFont(size=12)
        )
        self.replicate_status.pack(side="left", padx=(0, 20), pady=10)
        
        self.huggingface_status = ctk.CTkLabel(
            service_frame, 
            text="⚠️ Not Initialized",
            text_color="orange",
            font=ctk.CTkFont(size=12)
        )
        self.huggingface_status.pack(side="left", padx=0, pady=10)
        
        # API key button
        api_key_button = ctk.CTkButton(
            service_frame, 
            text="Configure API Keys",
            command=self.configure_api_keys
        )
        api_key_button.pack(side="right", padx=10, pady=10)
        
    def create_prompt_section(self):
        """Create the prompt input section"""
        prompt_frame = ctk.CTkFrame(self)
        prompt_frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        prompt_frame.grid_columnconfigure(0, weight=1)
        
        prompt_label = ctk.CTkLabel(
            prompt_frame, 
            text="Prompt:",
            font=ctk.CTkFont(size=16)
        )
        prompt_label.grid(row=0, column=0, padx=10, pady=(10, 0), sticky="w")
        
        # Prompt entry with scrollbar
        self.prompt_text = ctk.CTkTextbox(
            prompt_frame,
            height=80,
            wrap="word"
        )
        self.prompt_text.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")
        self.prompt_text.insert("1.0", "A beautiful woman on the beach, realistic, detailed, high quality")
        
        # Prompt history button
        history_button = ctk.CTkButton(
            prompt_frame,
            text="History",
            width=120,
            command=self.show_prompt_history
        )
        history_button.grid(row=1, column=1, padx=(0, 10), pady=(0, 10), sticky="ne")
        
        # Include trigger words checkbox
        self.trigger_words_var = tk.BooleanVar(value=True)
        trigger_words_check = ctk.CTkCheckBox(
            prompt_frame,
            text="Auto-include trigger words (porn, nude, sex, boobs)",
            variable=self.trigger_words_var
        )
        trigger_words_check.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="w")
        
        # Negative prompt (only visible in advanced mode)
        self.negative_prompt_label = ctk.CTkLabel(
            prompt_frame, 
            text="Negative Prompt:",
            font=ctk.CTkFont(size=16)
        )
        
        self.negative_prompt_text = ctk.CTkTextbox(
            prompt_frame,
            height=80,
            wrap="word"
        )
        self.negative_prompt_text.insert("1.0", self.config["parameters"]["negative_prompt"])
        
        # Only show negative prompt in advanced mode
        if self.config["advanced_mode"]:
            self.negative_prompt_label.grid(row=3, column=0, padx=10, pady=(10, 0), sticky="w")
            self.negative_prompt_text.grid(row=4, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")
        
    def create_parameters_section(self):
        """Create the parameters section"""
        parameters_frame = ctk.CTkFrame(self)
        parameters_frame.grid(row=5, column=0, padx=10, pady=5, sticky="ew")
        
        params_label = ctk.CTkLabel(
            parameters_frame, 
            text="Parameters:",
            font=ctk.CTkFont(size=16)
        )
        params_label.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="w", columnspan=4)
        
        # Basic parameters (always visible)
        
        # Width
        width_label = ctk.CTkLabel(parameters_frame, text="Width:")
        width_label.grid(row=1, column=0, padx=10, pady=5, sticky="w")
        
        self.width_var = tk.StringVar(value=str(self.config["parameters"]["width"]))
        width_values = ["512", "768", "1024", "1280", "1536"]
        width_dropdown = ctk.CTkComboBox(
            parameters_frame,
            values=width_values,
            variable=self.width_var,
            width=100
        )
        width_dropdown.grid(row=1, column=1, padx=10, pady=5, sticky="w")
        
        # Height
        height_label = ctk.CTkLabel(parameters_frame, text="Height:")
        height_label.grid(row=1, column=2, padx=10, pady=5, sticky="w")
        
        self.height_var = tk.StringVar(value=str(self.config["parameters"]["height"]))
        height_values = ["512", "768", "1024", "1280", "1536"]
        height_dropdown = ctk.CTkComboBox(
            parameters_frame,
            values=height_values,
            variable=self.height_var,
            width=100
        )
        height_dropdown.grid(row=1, column=3, padx=10, pady=5, sticky="w")
        
        # Steps
        steps_label = ctk.CTkLabel(parameters_frame, text="Steps:")
        steps_label.grid(row=2, column=0, padx=10, pady=5, sticky="w")
        
        self.steps_var = tk.StringVar(value=str(self.config["parameters"]["num_inference_steps"]))
        steps_dropdown = ctk.CTkComboBox(
            parameters_frame,
            values=["20", "30", "40", "50", "75", "100"],
            variable=self.steps_var,
            width=100
        )
        steps_dropdown.grid(row=2, column=1, padx=10, pady=5, sticky="w")
        
        # Output format selector
        format_label = ctk.CTkLabel(parameters_frame, text="Format:")
        format_label.grid(row=2, column=2, padx=10, pady=5, sticky="w")
        
        self.format_var = tk.StringVar(value="png")
        format_dropdown = ctk.CTkComboBox(
            parameters_frame,
            values=["png", "jpg", "webp"],
            variable=self.format_var,
            width=100
        )
        format_dropdown.grid(row=2, column=3, padx=10, pady=5, sticky="w")
        
        # Advanced parameters (only visible in advanced mode)
        self.advanced_params_frame = ctk.CTkFrame(parameters_frame)
        self.advanced_params_frame.grid(row=3, column=0, columnspan=4, padx=10, pady=5, sticky="ew")
        
        # Guidance scale
        guidance_label = ctk.CTkLabel(self.advanced_params_frame, text="Guidance Scale:")
        guidance_label.grid(row=0, column=0, padx=10, pady=5, sticky="w")
        
        self.guidance_var = tk.DoubleVar(value=self.config["parameters"]["guidance_scale"])
        guidance_slider = ctk.CTkSlider(
            self.advanced_params_frame,
            from_=1.0,
            to=15.0,
            number_of_steps=140,
            variable=self.guidance_var
        )
        guidance_slider.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        
        self.guidance_value_label = ctk.CTkLabel(self.advanced_params_frame, text=f"{self.guidance_var.get():.1f}")
        self.guidance_value_label.grid(row=0, column=2, padx=10, pady=5, sticky="w")
        
        # Callback to update the label when slider changes
        def update_guidance_label(*args):
            self.guidance_value_label.configure(text=f"{self.guidance_var.get():.1f}")
        
        self.guidance_var.trace_add("write", update_guidance_label)
        
        # LoRA scale
        lora_scale_label = ctk.CTkLabel(self.advanced_params_frame, text="LoRA Scale:")
        lora_scale_label.grid(row=1, column=0, padx=10, pady=5, sticky="w")
        
        self.lora_scale_var = tk.DoubleVar(value=self.config["parameters"]["lora_scale"])
        lora_scale_slider = ctk.CTkSlider(
            self.advanced_params_frame,
            from_=0.1,
            to=1.0,
            number_of_steps=90,
            variable=self.lora_scale_var
        )
        lora_scale_slider.grid(row=1, column=1, padx=10, pady=5, sticky="ew")
        
        self.lora_scale_value_label = ctk.CTkLabel(self.advanced_params_frame, text=f"{self.lora_scale_var.get():.1f}")
        self.lora_scale_value_label.grid(row=1, column=2, padx=10, pady=5, sticky="w")
        
        # Callback to update the label when slider changes
        def update_lora_scale_label(*args):
            self.lora_scale_value_label.configure(text=f"{self.lora_scale_var.get():.1f}")
        
        self.lora_scale_var.trace_add("write", update_lora_scale_label)
        
        # Show/hide advanced parameters based on mode
        if not self.config["advanced_mode"]:
            self.advanced_params_frame.grid_forget()
    
    def create_model_section(self):
        """Create the model selection section that changes based on service"""
        self.model_frame = ctk.CTkFrame(self)
        self.model_frame.grid(row=4, column=0, padx=10, pady=5, sticky="ew")
        self.model_frame.grid_columnconfigure(1, weight=1)  # Make the model entry stretch
        
        # Replicate model selection
        self.replicate_model_label = ctk.CTkLabel(
            self.model_frame,
            text="Replicate Model:",
            font=ctk.CTkFont(size=16)
        )
        
        self.replicate_model_var = tk.StringVar(value=self.config["last_used_model_replicate"])
        self.replicate_model_combo = ctk.CTkComboBox(
            self.model_frame,
            values=self.config["recent_models_replicate"],
            variable=self.replicate_model_var,
            width=400,
            state="readonly"
        )
        
        # Add model button
        self.add_replicate_model_button = ctk.CTkButton(
            self.model_frame,
            text="Add Model",
            width=100,
            command=self.add_replicate_model
        )
        
        # Hugging Face model selection
        self.hf_model_label = ctk.CTkLabel(
            self.model_frame,
            text="HF Base Model:",
            font=ctk.CTkFont(size=16)
        )
        
        self.hf_model_var = tk.StringVar(value=self.config["last_used_model_hf"])
        self.hf_model_combo = ctk.CTkComboBox(
            self.model_frame,
            values=self.config["recent_models_hf"],
            variable=self.hf_model_var,
            width=400,
            state="readonly"
        )
        
        # Add HF model button
        self.add_hf_model_button = ctk.CTkButton(
            self.model_frame,
            text="Add Model",
            width=100,
            command=self.add_hf_model
        )
        
        # Hugging Face LoRA section
        self.hf_lora_label = ctk.CTkLabel(
            self.model_frame,
            text="HF LoRA:",
            font=ctk.CTkFont(size=16)
        )
        
        self.hf_lora_var = tk.StringVar(value=self.config["last_used_lora_hf"])
        self.hf_lora_combo = ctk.CTkComboBox(
            self.model_frame,
            values=self.config["recent_loras_hf"],
            variable=self.hf_lora_var,
            width=400,
            state="readonly"
        )
        
        # Add LoRA button
        self.add_hf_lora_button = ctk.CTkButton(
            self.model_frame,
            text="Add LoRA",
            width=100,
            command=self.add_hf_lora
        )
        
        # Show the correct model selection based on currently selected service
        self.update_model_section()
        
    def update_model_section(self):
        """Update the model section based on the selected service"""
        # Clear any existing widgets
        for widget in self.model_frame.grid_slaves():
            widget.grid_forget()
            
        if self.service_var.get() == "replicate":
            # Show Replicate model section
            self.replicate_model_label.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="w")
            self.replicate_model_combo.grid(row=0, column=1, padx=10, pady=(10, 5), sticky="ew")
            self.add_replicate_model_button.grid(row=0, column=2, padx=10, pady=(10, 5), sticky="e")
        else:
            # Show Hugging Face model section
            self.hf_model_label.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="w")
            self.hf_model_combo.grid(row=0, column=1, padx=10, pady=(10, 5), sticky="ew")
            self.add_hf_model_button.grid(row=0, column=2, padx=10, pady=(10, 5), sticky="e")
            
            # Show LoRA section
            self.hf_lora_label.grid(row=1, column=0, padx=10, pady=5, sticky="w")
            self.hf_lora_combo.grid(row=1, column=1, padx=10, pady=5, sticky="ew")
            self.add_hf_lora_button.grid(row=1, column=2, padx=10, pady=5, sticky="e")
    
    def create_output_section(self):
        """Create the output configuration section"""
        output_frame = ctk.CTkFrame(self)
        output_frame.grid(row=6, column=0, padx=10, pady=5, sticky="ew")
        output_frame.grid_columnconfigure(1, weight=1)  # Make the output path stretch
        
        # Output directory selection
        output_label = ctk.CTkLabel(
            output_frame, 
            text="Output Directory:",
            font=ctk.CTkFont(size=16)
        )
        output_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        
        self.output_dir_var = tk.StringVar(value=self.config["output_directory"])
        output_entry = ctk.CTkEntry(
            output_frame,
            textvariable=self.output_dir_var,
            width=400,
            state="readonly"
        )
        output_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        
        browse_button = ctk.CTkButton(
            output_frame,
            text="Browse",
            width=100,
            command=self.browse_output_dir
        )
        browse_button.grid(row=0, column=2, padx=10, pady=10, sticky="e")
        
        # Generate button
        generate_button = ctk.CTkButton(
            output_frame,
            text="Generate Image",
            font=ctk.CTkFont(size=16, weight="bold"),
            height=40,
            command=self.generate_image
        )
        generate_button.grid(row=1, column=0, columnspan=3, padx=10, pady=10, sticky="ew")
        
        # Batch generation section (advanced mode)
        self.batch_frame = ctk.CTkFrame(output_frame)
        
        batch_label = ctk.CTkLabel(
            self.batch_frame, 
            text="Number of Images:",
            font=ctk.CTkFont(size=14)
        )
        batch_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        
        self.batch_count_var = tk.StringVar(value="1")
        batch_count = ctk.CTkComboBox(
            self.batch_frame,
            values=["1", "2", "4", "8"],
            variable=self.batch_count_var,
            width=80
        )
        batch_count.grid(row=0, column=1, padx=10, pady=10, sticky="w")
        
        batch_generate_button = ctk.CTkButton(
            self.batch_frame,
            text="Generate Batch",
            command=self.generate_batch
        )
        batch_generate_button.grid(row=0, column=2, padx=10, pady=10, sticky="e")
        
        # Only show batch section in advanced mode
        if self.config["advanced_mode"]:
            self.batch_frame.grid(row=2, column=0, columnspan=3, padx=10, pady=5, sticky="ew")
    
    def create_image_display(self):
        """Create the image display area"""
        display_frame = ctk.CTkFrame(self)
        display_frame.grid(row=3, column=0, padx=10, pady=5, sticky="nsew")
        display_frame.grid_columnconfigure(0, weight=1)
        display_frame.grid_rowconfigure(0, weight=1)
        
        # Create a canvas for the image with scrollbars
        self.canvas_frame = ctk.CTkFrame(display_frame)
        self.canvas_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.canvas_frame.grid_columnconfigure(0, weight=1)
        self.canvas_frame.grid_rowconfigure(0, weight=1)
        
        self.canvas = tk.Canvas(
            self.canvas_frame,
            bg="#2B2B2B",
            bd=0,
            highlightthickness=0
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        
        # Load placeholder image
        placeholder_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "placeholder.png")
        try:
            if os.path.exists(placeholder_path):
                self.display_image(placeholder_path)
            else:
                # Create a blank placeholder
                width, height = 400, 300
                self.canvas.create_text(
                    width, height,
                    text="Generate an image to display here",
                    fill="white",
                    font=("Arial", 14)
                )
        except Exception as e:
            print(f"Error loading placeholder: {e}")
            self.canvas.create_text(
                400, 300,
                text="Generate an image to display here",
                fill="white",
                font=("Arial", 14)
            )
        
        # Add scrollbars
        x_scrollbar = ttk.Scrollbar(self.canvas_frame, orient="horizontal", command=self.canvas.xview)
        x_scrollbar.grid(row=1, column=0, sticky="ew")
        
        y_scrollbar = ttk.Scrollbar(self.canvas_frame, orient="vertical", command=self.canvas.yview)
        y_scrollbar.grid(row=0, column=1, sticky="ns")
        
        self.canvas.configure(xscrollcommand=x_scrollbar.set, yscrollcommand=y_scrollbar.set)
        
        # Image control buttons
        control_frame = ctk.CTkFrame(display_frame)
        control_frame.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")
        
        save_button = ctk.CTkButton(
            control_frame,
            text="Save Image As",
            command=self.save_image_as
        )
        save_button.pack(side="left", padx=10, pady=10)
        
        open_folder_button = ctk.CTkButton(
            control_frame,
            text="Open Output Folder",
            command=self.open_output_folder
        )
        open_folder_button.pack(side="left", padx=10, pady=10)
        
        self.image_info_label = ctk.CTkLabel(
            control_frame,
            text="No image generated yet",
            font=ctk.CTkFont(size=12)
        )
        self.image_info_label.pack(side="right", padx=10, pady=10)
