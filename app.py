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
ctk.set_default_color_theme("dark-blue")  # Themes: "blue" (standard), "green", "dark-blue"

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
        
        # Set environment variables to disable safety checkers
        os.environ["FLUX_DISABLE_SAFETY"] = "true"
        os.environ["FLUX_GO_FAST"] = "true"
        
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
        
        # Load placeholder image after all UI components are created
        placeholder_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "placeholder.png")
        try:
            if os.path.exists(placeholder_path):
                # Use after() to ensure all widgets are fully initialized
                self.after(100, lambda: self.display_image(placeholder_path))
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
            print(f"Error setting up placeholder: {e}")
            self.canvas.create_text(
                400, 300,
                text="Generate an image to display here",
                fill="white",
                font=("Arial", 14)
            )
        
    def create_status_bar(self):
        """Create the status bar at the bottom of the window"""
        status_frame = ctk.CTkFrame(self)
        status_frame.grid(row=7, column=0, padx=10, pady=(5, 10), sticky="ew")
        
        self.status_label = ctk.CTkLabel(status_frame, text="Ready", font=ctk.CTkFont(size=12))
        self.status_label.pack(side="left", padx=10)
        
        self.service_info_label = ctk.CTkLabel(status_frame, text=f"Service: {self.config['service'].capitalize()}", font=ctk.CTkFont(size=12))
        self.service_info_label.pack(side="right", padx=10)
        
    def toggle_advanced_mode(self):
        """Toggle advanced mode on/off"""
        advanced_mode = self.advanced_mode_var.get()
        self.config["advanced_mode"] = advanced_mode
        
        # Update UI components that depend on advanced mode
        if advanced_mode:
            # Show negative prompt
            self.negative_prompt_label.grid(row=3, column=0, padx=10, pady=(10, 0), sticky="w")
            self.negative_prompt_text.grid(row=4, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")
            # Show advanced parameters
            self.advanced_params_frame.grid(row=3, column=0, columnspan=4, padx=10, pady=5, sticky="ew")
            # Show batch frame
            self.batch_frame.grid(row=2, column=0, columnspan=3, padx=10, pady=5, sticky="ew")
        else:
            # Hide negative prompt
            self.negative_prompt_label.grid_forget()
            self.negative_prompt_text.grid_forget()
            # Hide advanced parameters
            self.advanced_params_frame.grid_forget()
            # Hide batch frame
            self.batch_frame.grid_forget()
        
        # Save config changes
        self.save_config()
    
    def initialize_default_values(self):
        """Initialize default values for UI components"""
        # Nothing to do here - values are set during UI creation
        pass
        
    def on_service_change(self):
        """Handle service change between Replicate and Hugging Face"""
        service = self.service_var.get()
        self.config["service"] = service
        
        # Update UI based on selected service
        self.update_model_section()
        
        # Update status label
        self.service_info_label.configure(text=f"Service: {service.capitalize()}")
        
        # Save config changes
        self.save_config()
    
    def display_image(self, image_path):
        """Display an image in the canvas"""
        try:
            if not os.path.exists(image_path):
                print(f"Image file not found: {image_path}")
                return
                
            # Load and display the image
            image = Image.open(image_path)
            
            # Store the current image path
            self.current_image_path = image_path
            
            # Calculate dimensions while preserving aspect ratio
            canvas_width = self.canvas_frame.winfo_width() - 20  # Padding
            canvas_height = self.canvas_frame.winfo_height() - 20  # Padding
            
            if canvas_width <= 1 or canvas_height <= 1:
                # Canvas not yet sized properly, use default size
                canvas_width = 800
                canvas_height = 600
                
            # Preserve aspect ratio
            img_width, img_height = image.size
            ratio = min(canvas_width/img_width, canvas_height/img_height)
            
            # Resize image if needed
            if ratio < 1:
                display_width = int(img_width * ratio)
                display_height = int(img_height * ratio)
                resized_image = image.resize((display_width, display_height), Image.LANCZOS)
            else:
                display_width = img_width
                display_height = img_height
                resized_image = image
                
            # Convert to Tkinter PhotoImage
            self.photo_image = ImageTk.PhotoImage(resized_image)
            
            # Clear existing canvas content
            if hasattr(self, 'canvas') and self.canvas:
                self.canvas.delete("all")
                
                # Configure canvas size and scrollregion
                self.canvas.config(width=display_width, height=display_height)
                self.canvas.config(scrollregion=(0, 0, display_width, display_height))
                
                # Display image at center of canvas
                self.canvas.create_image(display_width/2, display_height/2, image=self.photo_image, anchor="center")
            
            # Update info label if it exists
            if hasattr(self, 'image_info_label') and self.image_info_label:
                try:
                    file_name = os.path.basename(image_path)
                    file_size = os.path.getsize(image_path) / 1024  # KB
                    self.image_info_label.configure(text=f"{file_name} ({img_width}x{img_height}, {file_size:.1f} KB)")
                except Exception as e:
                    print(f"Error updating image info label: {e}")
            
        except Exception as e:
            print(f"Error displaying image: {e}")
            if hasattr(self, 'canvas') and self.canvas:
                self.canvas.delete("all")
                self.canvas.create_text(200, 150, text=f"Error displaying image: {str(e)[:50]}...", fill="white")
    
    def configure_api_keys(self):
        """Open a dialog to configure API keys"""
        # Create a modal dialog
        dialog = ctk.CTkToplevel(self)
        dialog.title("Configure API Keys")
        dialog.geometry("500x200")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        
        # Make it a modal dialog
        dialog.focus_set()
        
        # Replicate API key
        replicate_label = ctk.CTkLabel(
            dialog,
            text="Replicate API Key:",
            font=ctk.CTkFont(size=14)
        )
        replicate_label.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")
        
        replicate_key_var = tk.StringVar(value=self.config["replicate_api_key"])
        replicate_entry = ctk.CTkEntry(
            dialog,
            textvariable=replicate_key_var,
            width=300
        )
        replicate_entry.grid(row=0, column=1, padx=20, pady=(20, 10), sticky="ew")
        
        # Hugging Face token
        hf_label = ctk.CTkLabel(
            dialog,
            text="Hugging Face Token:",
            font=ctk.CTkFont(size=14)
        )
        hf_label.grid(row=1, column=0, padx=20, pady=10, sticky="w")
        
        hf_token_var = tk.StringVar(value=self.config["huggingface_token"])
        hf_entry = ctk.CTkEntry(
            dialog,
            textvariable=hf_token_var,
            width=300
        )
        hf_entry.grid(row=1, column=1, padx=20, pady=10, sticky="ew")
        
        # Save button
        def save_keys():
            self.config["replicate_api_key"] = replicate_key_var.get()
            self.config["huggingface_token"] = hf_token_var.get()
            
            # Set environment variables
            os.environ["REPLICATE_API_TOKEN"] = self.config["replicate_api_key"]
            os.environ["HUGGINGFACE_TOKEN"] = self.config["huggingface_token"]
            
            # Save config
            self.save_config()
            dialog.destroy()
        
        save_button = ctk.CTkButton(
            dialog,
            text="Save",
            command=save_keys
        )
        save_button.grid(row=2, column=0, columnspan=2, padx=20, pady=20)
    
    def save_image_as(self):
        """Save the current image with a new name"""
        if not self.current_image_path or not os.path.exists(self.current_image_path):
            messagebox.showinfo("No Image", "No image to save")
            return
            
        # Get original image format
        original_format = os.path.splitext(self.current_image_path)[1].lower()
        
        # Show save dialog
        file_types = [
            ("PNG files", "*.png"), 
            ("JPEG files", "*.jpg"), 
            ("WEBP files", "*.webp"), 
            ("All files", "*.*")
        ]
        
        save_path = filedialog.asksaveasfilename(
            initialdir=self.config["output_directory"],
            initialfile=os.path.basename(self.current_image_path),
            defaultextension=original_format,
            filetypes=file_types
        )
        
        if save_path:
            try:
                # Open the original image
                img = Image.open(self.current_image_path)
                
                # Save to the new path
                img.save(save_path)
                
                messagebox.showinfo("Save Successful", f"Image saved to:\n{save_path}")
            except Exception as e:
                messagebox.showerror("Save Error", f"Error saving image: {e}")
    
    def open_output_folder(self):
        """Open the output folder in file explorer"""
        output_dir = self.config["output_directory"]
        if os.path.exists(output_dir):
            # Use the appropriate command for the OS
            if sys.platform == "win32":
                os.startfile(output_dir)
            elif sys.platform == "darwin":  # macOS
                os.system(f'open "{output_dir}"')
            else:  # Linux
                os.system(f'xdg-open "{output_dir}"')
        else:
            messagebox.showinfo("Folder Not Found", f"Output folder does not exist:\n{output_dir}")
    
    def browse_output_dir(self):
        """Open a dialog to select output directory"""
        directory = filedialog.askdirectory(initialdir=self.config["output_directory"])
        if directory:
            self.output_dir_var.set(directory)
            self.config["output_directory"] = directory
            self.save_config()
    
    def show_prompt_history(self):
        """Show prompt history in a dialog"""
        if not self.config["recent_prompts"]:
            messagebox.showinfo("Prompt History", "No recent prompts found.")
            return
        
        # Create a dialog
        dialog = ctk.CTkToplevel(self)
        dialog.title("Prompt History")
        dialog.geometry("600x400")
        dialog.transient(self)
        dialog.grab_set()
        
        # Make it a modal dialog
        dialog.focus_set()
        
        # List of prompts
        prompt_listbox = tk.Listbox(
            dialog,
            bg="#2B2B2B",
            fg="white",
            selectbackground="#3B8ED0",
            font=("Arial", 12),
            height=15,
            width=60
        )
        prompt_listbox.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Add prompts to listbox
        for prompt in self.config["recent_prompts"]:
            prompt_listbox.insert("end", prompt)
        
        # Button frame
        button_frame = ctk.CTkFrame(dialog)
        button_frame.pack(fill="x", padx=20, pady=(0, 20))
        
        # Use selected prompt
        def use_selected_prompt():
            selection = prompt_listbox.curselection()
            if selection:
                selected_prompt = prompt_listbox.get(selection[0])
                self.prompt_text.delete("1.0", "end")
                self.prompt_text.insert("1.0", selected_prompt)
                dialog.destroy()
        
        use_button = ctk.CTkButton(
            button_frame,
            text="Use Selected",
            command=use_selected_prompt
        )
        use_button.pack(side="left", padx=10, pady=10)
        
        # Close button
        close_button = ctk.CTkButton(
            button_frame,
            text="Close",
            command=dialog.destroy
        )
        close_button.pack(side="right", padx=10, pady=10)
    
    def add_replicate_model(self):
        """Add a new Replicate model"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Add Replicate Model")
        dialog.geometry("600x150")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        
        # Make it a modal dialog
        dialog.focus_set()
        
        # Model entry
        model_label = ctk.CTkLabel(
            dialog,
            text="Model ID (owner/model:version):",
            font=ctk.CTkFont(size=14)
        )
        model_label.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")
        
        model_var = tk.StringVar()
        model_entry = ctk.CTkEntry(
            dialog,
            textvariable=model_var,
            width=400
        )
        model_entry.grid(row=0, column=1, padx=20, pady=(20, 10), sticky="ew")
        
        # Save button
        def save_model():
            model_id = model_var.get().strip()
            if not model_id:
                messagebox.showerror("Error", "Please enter a valid model ID")
                return
                
            # Add to recent models if not already there
            if model_id not in self.config["recent_models_replicate"]:
                self.config["recent_models_replicate"].append(model_id)
                
            # Update the combobox
            self.replicate_model_combo.configure(values=self.config["recent_models_replicate"])
            self.replicate_model_var.set(model_id)
            self.config["last_used_model_replicate"] = model_id
            
            # Save config
            self.save_config()
            dialog.destroy()
        
        save_button = ctk.CTkButton(
            dialog,
            text="Add Model",
            command=save_model
        )
        save_button.grid(row=1, column=0, columnspan=2, padx=20, pady=20)
    
    def add_hf_model(self):
        """Add a new Hugging Face model"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Add Hugging Face Model")
        dialog.geometry("600x150")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        
        # Make it a modal dialog
        dialog.focus_set()
        
        # Model entry
        model_label = ctk.CTkLabel(
            dialog,
            text="Model ID (owner/model):",
            font=ctk.CTkFont(size=14)
        )
        model_label.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")
        
        model_var = tk.StringVar()
        model_entry = ctk.CTkEntry(
            dialog,
            textvariable=model_var,
            width=400
        )
        model_entry.grid(row=0, column=1, padx=20, pady=(20, 10), sticky="ew")
        
        # Save button
        def save_model():
            model_id = model_var.get().strip()
            if not model_id:
                messagebox.showerror("Error", "Please enter a valid model ID")
                return
                
            # Add to recent models if not already there
            if model_id not in self.config["recent_models_hf"]:
                self.config["recent_models_hf"].append(model_id)
                
            # Update the combobox
            self.hf_model_combo.configure(values=self.config["recent_models_hf"])
            self.hf_model_var.set(model_id)
            self.config["last_used_model_hf"] = model_id
            
            # Save config
            self.save_config()
            dialog.destroy()
        
        save_button = ctk.CTkButton(
            dialog,
            text="Add Model",
            command=save_model
        )
        save_button.grid(row=1, column=0, columnspan=2, padx=20, pady=20)
    
    def add_hf_lora(self):
        """Add a new Hugging Face LoRA"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Add Hugging Face LoRA")
        dialog.geometry("600x150")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        
        # Make it a modal dialog
        dialog.focus_set()
        
        # LoRA entry
        lora_label = ctk.CTkLabel(
            dialog,
            text="LoRA URL:",
            font=ctk.CTkFont(size=14)
        )
        lora_label.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")
        
        lora_var = tk.StringVar()
        lora_entry = ctk.CTkEntry(
            dialog,
            textvariable=lora_var,
            width=400
        )
        lora_entry.grid(row=0, column=1, padx=20, pady=(20, 10), sticky="ew")
        
        # Save button
        def save_lora():
            lora_url = lora_var.get().strip()
            if not lora_url:
                messagebox.showerror("Error", "Please enter a valid LoRA URL")
                return
                
            # Add to recent LoRAs if not already there
            if lora_url not in self.config["recent_loras_hf"]:
                self.config["recent_loras_hf"].append(lora_url)
                
            # Update the combobox
            self.hf_lora_combo.configure(values=self.config["recent_loras_hf"])
            self.hf_lora_var.set(lora_url)
            self.config["last_used_lora_hf"] = lora_url
            
            # Save config
            self.save_config()
            dialog.destroy()
        
        save_button = ctk.CTkButton(
            dialog,
            text="Add LoRA",
            command=save_lora
        )
        save_button.grid(row=1, column=0, columnspan=2, padx=20, pady=20)
    
    def create_progress_ui(self):
        """Create progress UI elements"""
        # Create progress frame
        self.progress_frame = ctk.CTkFrame(self)
        self.progress_frame.grid(row=8, column=0, padx=10, pady=5, sticky="ew")
        self.progress_frame.grid_columnconfigure(0, weight=1)
        
        # Progress label
        self.progress_label = ctk.CTkLabel(
            self.progress_frame,
            text="Generating image...",
            font=ctk.CTkFont(size=12)
        )
        self.progress_label.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="w")
        
        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(
            self.progress_frame,
            mode="determinate"
        )
        self.progress_bar.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")
        self.progress_bar.set(0)
        
        # Cancel button
        self.cancel_button = ctk.CTkButton(
            self.progress_frame,
            text="Cancel",
            width=100,
            command=self.cancel_generation
        )
        self.cancel_button.grid(row=1, column=1, padx=10, pady=(0, 10), sticky="e")
        
        # Initially hide the progress frame
        self.progress_frame.grid_remove()

    def show_progress_ui(self):
        """Show progress UI"""
        self.progress_frame.grid()

    def hide_progress_ui(self):
        """Hide progress UI"""
        self.progress_frame.grid_remove()

    def cancel_generation(self):
        """Cancel the current generation"""
        if self.is_generating:
            self.is_generating = False
            self.after(100, lambda: self.status_label.configure(text="Generation cancelled"))
            self.after(100, lambda: self.hide_progress_ui())

    def get_parameters(self):
        """Get current parameters from UI"""
        # Get basic parameters
        parameters = {
            "width": int(self.width_var.get()),
            "height": int(self.height_var.get()),
            "num_inference_steps": int(self.steps_var.get())
        }
        
        # Get advanced parameters if in advanced mode
        if self.advanced_mode_var.get():
            parameters.update({
                "guidance_scale": self.guidance_var.get(),
                "lora_scale": self.lora_scale_var.get(),
                "negative_prompt": self.negative_prompt_text.get("1.0", "end-1c")
            })
        else:
            # Use defaults from config
            parameters.update({
                "guidance_scale": self.config["parameters"]["guidance_scale"],
                "lora_scale": self.config["parameters"]["lora_scale"],
                "negative_prompt": self.config["parameters"]["negative_prompt"]
            })
        
        return parameters

    def get_prompt(self):
        """Get prompt with optional trigger words"""
        prompt = self.prompt_text.get("1.0", "end-1c").strip()
        
        # Add trigger words if enabled and not already in prompt
        if self.trigger_words_var.get():
            trigger_words = ["porn", "nude", "sex", "boobs"]
            if not any(word.lower() in prompt.lower() for word in trigger_words):
                prompt = f"porn, nude, sex, boobs, {prompt}"
                
        return prompt

    def save_prompt_to_history(self, prompt):
        """Save prompt to history"""
        if prompt and prompt not in self.config["recent_prompts"]:
            # Add to the beginning of the list
            self.config["recent_prompts"].insert(0, prompt)
            
            # Keep only the 20 most recent prompts
            self.config["recent_prompts"] = self.config["recent_prompts"][:20]
            
            # Save config
            self.save_config()

    def generate_image(self):
        """Generate a single image"""
        print("DEBUG: generate_image function called") # Add this line for debugging
        if self.is_generating:
            print("DEBUG: Generation already in progress, returning.") # Add this line
            messagebox.showinfo("Generation in Progress", "Please wait for the current generation to complete.")
            return
        
        # Get current parameters
        service = self.service_var.get()
        prompt = self.get_prompt()
        
        # Check if prompt is empty
        if not prompt.strip():
            messagebox.showerror("Empty Prompt", "Please enter a prompt to generate an image.")
            return
            
        parameters = self.get_parameters()
        
        # Create progress frame if it doesn't exist
        if not hasattr(self, 'progress_frame'):
            self.create_progress_ui()
        
        # Show progress UI
        self.show_progress_ui()
        
        # Save prompt to history
        self.save_prompt_to_history(prompt)
        
        # Set generating flag
        self.is_generating = True
        
        # Update UI status
        self.status_label.configure(text="Initializing image generation...")
        self.progress_label.configure(text="Preparing to generate image...")
        self.progress_bar.set(0.1)  # Show initial progress
        
        # Start generation in a separate thread
        print("DEBUG: Starting generation thread...") # Add this line
        thread = threading.Thread(target=self._generate_image_thread, args=(service, prompt, parameters))
        thread.daemon = True
        thread.start()
        print("DEBUG: Generation thread started.") # Add this line
    
    def _generate_image_thread(self, service, prompt, parameters):
        """Thread function for image generation"""
        try:
            # Prepare output filename
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            self.generation_count += 1
            output_filename = f"{timestamp}_image.{self.format_var.get()}"
            output_path = os.path.join(self.config["output_directory"], output_filename)
            
            # Generate based on selected service
            if service == "replicate":
                image_path = self._generate_with_replicate(prompt, parameters, output_path)
            else:
                image_path = self._generate_with_huggingface(prompt, parameters, output_path)
                
            # Display the image
            self.after(100, lambda: self.display_image(image_path))
            
            # Update status
            self.after(100, lambda: self.status_label.configure(text="Image generated successfully"))
            self.after(100, lambda: self.image_info_label.configure(
                text=f"Generated: {output_filename} ({parameters['width']}x{parameters['height']})"
            ))
        except Exception as e:
            error_msg = str(e)
            print(f"Error generating image: {error_msg}")
            self.after(100, lambda: messagebox.showerror("Generation Error", f"Failed to generate image: {error_msg}"))
            self.after(100, lambda: self.status_label.configure(text="Error generating image"))
        finally:
            # Ensure the generating flag is always reset
            self.after(100, lambda: setattr(self, 'is_generating', False))
            # Ensure the progress UI is hidden
            self.after(100, lambda: self.hide_progress_ui())

    def _generate_with_replicate(self, prompt, parameters, output_path):
        """Generate image using Replicate API"""
        # Update UI to indicate we're starting
        self.after(100, lambda: self.progress_label.configure(
            text="Preparing request to Replicate API..."
        ))
        self.after(100, lambda: self.progress_bar.set(0.05))
        
        # Start timing for user feedback
        start_time = time.time()
        
        # Get the model ID
        model = self.replicate_model_var.get()
        model_name = model.split(':')[0] if ':' in model else model
        model_version = model.split(':')[1] if ':' in model else None
        
        # Prepare the input parameters for replicate
        input_params = {
            "prompt": prompt,
            "negative_prompt": parameters["negative_prompt"],
            "width": parameters["width"],
            "height": parameters["height"],
            "num_outputs": 1,
            "scheduler": "K_EULER_ANCESTRAL",
            "num_inference_steps": parameters["num_inference_steps"],
            "guidance_scale": parameters["guidance_scale"],
            "prompt_strength": 0.8,
            "apply_watermark": False,
            # Add safety checker bypass parameters
            "disable_safety_checker": True,
            "safety_checker": None,
            "safety_tolerance": 6,  # Maximum tolerance (most permissive)
            "requires_safety_checker": False
        }
        
        # Reinforce the environment variables for disabling safety checks
        os.environ["FLUX_DISABLE_SAFETY"] = "true"
        os.environ["FLUX_GO_FAST"] = "true"
        
        # Add LoRA scale if using flux-lora-uncensored
        if "flux-lora" in model.lower() or "lora_scale" in parameters:
            input_params["lora_scale"] = parameters["lora_scale"]
        
        # If using SDXL, add these params
        if "sdxl" in model.lower():
            input_params.update({
                "high_noise_frac": 0.8,
                "refine": "expert_ensemble_refiner",
                "refine_steps": 25
            })
            
            # If using a base model that supports LoRA, add the URL
            if "stability-ai/sdxl" in model:
                input_params["lora"] = "https://huggingface.co/aifeifei798/flux-lora-uncensored/resolve/main/flux_lora_v1.safetensors"
        
        # Update the user about API details
        print(f"Starting generation with Replicate model: {model}")
        print(f"Parameters: {input_params}")
        print(f"API Key: {'*' * (len(os.environ.get('REPLICATE_API_TOKEN', '')) - 4)}...{os.environ.get('REPLICATE_API_TOKEN', '')[-4:] if os.environ.get('REPLICATE_API_TOKEN') else 'Not set'}")
        
        try:
            # Verify API key is set
            if not os.environ.get("REPLICATE_API_TOKEN"):
                raise Exception("Replicate API token is not set. Click 'Configure API Keys' to set it.")
                
            # Update UI to show we're creating the prediction
            self.after(100, lambda: self.progress_label.configure(
                text="Creating Replicate prediction..."
            ))
            self.after(100, lambda: self.progress_bar.set(0.1))
            
            # Run the model
            output = replicate.run(
                model,
                input=input_params
            )
            
            # Update status to downloading
            elapsed_time = time.time() - start_time
            elapsed_str = f"{int(elapsed_time // 60):02d}:{int(elapsed_time % 60):02d}"
            self.after(100, lambda: self.progress_label.configure(
                text=f"Generation complete, downloading... ({elapsed_str})"
            ))
            self.after(100, lambda: self.progress_bar.set(0.9))
            
            # Get the output URL
            if isinstance(output, list):
                image_url = output[0]
            else:
                image_url = output
            
            print(f"Image generated! URL: {image_url}")
            
            # Download the image
            response = requests.get(image_url)
            if response.status_code != 200:
                raise Exception(f"Failed to download image: HTTP {response.status_code}")
            
            # Save the image
            with open(output_path, "wb") as f:
                f.write(response.content)
            
            # Final update
            elapsed_time = time.time() - start_time
            elapsed_str = f"{int(elapsed_time // 60):02d}:{int(elapsed_time % 60):02d}"
            self.after(100, lambda: self.progress_label.configure(
                text=f"Image generation completed in {elapsed_str}"
            ))
            self.after(100, lambda: self.progress_bar.set(1.0))
            
            return output_path
            
        except Exception as e:
            error_msg = str(e)
            print(f"Error in Replicate generation: {error_msg}")
            
            # Handle common API errors more gracefully
            if "API key" in error_msg.lower() or "authentication" in error_msg.lower():
                error_msg = "Invalid or missing Replicate API key. Click 'Configure API Keys' to set a valid key."
            elif "quota" in error_msg.lower() or "limit" in error_msg.lower():
                error_msg = "API quota exceeded. Please try again later or check your Replicate account."
            elif "not found" in error_msg.lower() and "model" in error_msg.lower():
                error_msg = f"Model {model_name} not found. Please check the model ID and version."
            
            raise Exception(f"Replicate API error: {error_msg}")
    
    def _generate_with_huggingface(self, prompt, parameters, output_path):
        """Generate image using Hugging Face Inference API"""
        import json
        
        # Start timing for user feedback
        start_time = time.time()
        
        # Update UI to indicate we're starting
        self.after(100, lambda: self.progress_label.configure(
            text="Preparing request to Hugging Face API..."
        ))
        self.after(100, lambda: self.progress_bar.set(0.05))
        
        # Get model ID and LoRA URL
        model_id = self.hf_model_var.get()
        lora_url = self.hf_lora_var.get() if hasattr(self, 'hf_lora_var') else None
        
        # Get HuggingFace token
        hf_token = os.environ.get("HUGGINGFACE_TOKEN")
        if not hf_token:
            hf_token = self.config.get("huggingface_token", "")
            if hf_token:
                os.environ["HUGGINGFACE_TOKEN"] = hf_token
        
        # Check token first
        if not hf_token:
            raise Exception("Hugging Face token not set. Click 'Configure API Keys' to set it.")
        
        try:
            # Update progress UI
            self.after(100, lambda: self.progress_label.configure(
                text="Constructing API request..."
            ))
            self.after(100, lambda: self.progress_bar.set(0.1))
            
            # Determine which API endpoint to use based on the model
            if "FLUX" in model_id:
                is_flux = True
                # Flux models should use the official text-to-image endpoint
                api_url = f"https://api-inference.huggingface.co/models/{model_id}"
            else:
                is_flux = False
                # Other models use the standard text-to-image endpoint
                api_url = f"https://api-inference.huggingface.co/models/{model_id}"
            
            # Prepare headers for the API request
            headers = {
                "Authorization": f"Bearer {hf_token}",
                "Content-Type": "application/json"
            }
            
            # Prepare the payload for the API request
            payload = {
                "inputs": prompt,
                "parameters": {
                    "negative_prompt": parameters["negative_prompt"],
                    "width": parameters["width"],
                    "height": parameters["height"],
                    "num_inference_steps": parameters["num_inference_steps"],
                    "guidance_scale": parameters["guidance_scale"],
                    # Add safety checker bypass parameters
                    "disable_safety_checker": True,
                    "safety_checker": None,
                    "requires_safety_checker": False,
                    "safety_tolerance": 6  # Maximum tolerance (most permissive)
                }
            }
            
            # Add additional parameters for Flux models
            if is_flux and lora_url and lora_url.strip():
                lora_filename = os.path.basename(lora_url)
                print(f"Using LoRA: {lora_filename}")
                
                # Add LoRA parameters
                payload["parameters"]["cross_attention_kwargs"] = {
                    "scale": parameters.get("lora_scale", 0.9)
                }
                
                # For some models, we need to specify the LoRA directly
                if "lora" not in payload["parameters"]:
                    payload["parameters"]["lora"] = lora_url
            
            # Update UI for sending request
            self.after(100, lambda: self.progress_label.configure(
                text="Sending request to Hugging Face API..."
            ))
            self.after(100, lambda: self.progress_bar.set(0.15))
            
            # Send the request (non-streaming)
            response = requests.post(
                api_url,
                headers=headers,
                json=payload
            )
            
            # Check if the response is an error
            if response.status_code != 200:
                # Handle 503 specially - this means the model is loading
                if response.status_code == 503:
                    print("Model is loading, waiting...")
                    self.after(100, lambda: self.progress_label.configure(
                        text="Model is loading on Hugging Face servers..."
                    ))
                    self.after(100, lambda: self.progress_bar.set(0.2))
                    
                    # Wait and poll for completion
                    max_retries = 20
                    retry_count = 0
                    retry_delay = 5  # seconds
                    
                    while retry_count < max_retries:
                        # Update UI with retry count
                        elapsed_time = time.time() - start_time
                        elapsed_str = f"{int(elapsed_time // 60):02d}:{int(elapsed_time % 60):02d}"
                        
                        # Calculate progress based on retries (move from 0.2 to 0.7)
                        progress = 0.2 + (0.5 * (retry_count / max_retries))
                        
                        # Update UI
                        self.after(100, lambda t=f"Waiting for model to load... ({elapsed_str})": 
                                  self.progress_label.configure(text=t))
                        self.after(100, lambda p=progress: self.progress_bar.set(p))
                        
                        # Sleep before retrying
                        time.sleep(retry_delay)
                        
                        # Try again
                        response = requests.post(
                            api_url,
                            headers=headers,
                            json=payload
                        )
                        
                        # If successful, break out of the loop
                        if response.status_code == 200:
                            break
                        
                        retry_count += 1
                    
                    # If we still couldn't get a valid response after retries, raise an error
                    if response.status_code != 200:
                        try:
                            error_json = response.json()
                            error_msg = error_json.get("error", "Unknown error")
                        except:
                            error_msg = f"HTTP Status: {response.status_code}"
                        
                        raise Exception(f"Failed to generate image after waiting: {error_msg}")
                else:
                    # Handle other HTTP error codes
                    try:
                        error_json = response.json()
                        error_msg = error_json.get("error", "Unknown error")
                    except:
                        error_msg = f"HTTP Status: {response.status_code}"
                    
                    raise Exception(f"Hugging Face API error: {error_msg}")
            
            # Update UI for downloading
            self.after(100, lambda: self.progress_label.configure(
                text="Processing generated image..."
            ))
            self.after(100, lambda: self.progress_bar.set(0.8))
            
            # Get the content type
            content_type = response.headers.get("Content-Type", "")
            
            # Process the response based on content type
            if "image" in content_type:
                # Direct image response
                image_data = response.content
                with open(output_path, "wb") as f:
                    f.write(image_data)
                
                # Calculate time elapsed
                elapsed_time = time.time() - start_time
                elapsed_str = f"{int(elapsed_time // 60):02d}:{int(elapsed_time % 60):02d}"
                
                # Update UI for completion
                self.after(100, lambda: self.progress_label.configure(
                    text=f"Generation completed in {elapsed_str}"
                ))
                self.after(100, lambda: self.progress_bar.set(1.0))
                
                # Return the saved image path
                return output_path
                
            elif "application/json" in content_type:
                # Check if we got a JSON response with image data
                response_json = response.json()
                
                # For models returning a list of images
                if isinstance(response_json, list) and len(response_json) > 0:
                    image_data = response_json[0]
                    
                    # Check if it's a base64 string
                    if isinstance(image_data, str) and image_data.startswith("data:image"):
                        # It's a data URL, extract the base64 part
                        import base64
                        image_data = image_data.split(",")[1]
                        image_bytes = base64.b64decode(image_data)
                        
                        with open(output_path, "wb") as f:
                            f.write(image_bytes)
                        
                        # Update UI
                        elapsed_time = time.time() - start_time
                        elapsed_str = f"{int(elapsed_time // 60):02d}:{int(elapsed_time % 60):02d}"
                        self.after(100, lambda: self.progress_label.configure(
                            text=f"Generation completed in {elapsed_str}"
                        ))
                        self.after(100, lambda: self.progress_bar.set(1.0))
                        
                        return output_path
                        
                # If it has an image URL
                if isinstance(response_json, dict) and "image_url" in response_json:
                    image_url = response_json["image_url"]
                    # Download the image
                    img_response = requests.get(image_url)
                    with open(output_path, "wb") as f:
                        f.write(img_response.content)
                    
                    # Update UI
                    elapsed_time = time.time() - start_time
                    elapsed_str = f"{int(elapsed_time // 60):02d}:{int(elapsed_time % 60):02d}"
                    self.after(100, lambda: self.progress_label.configure(
                        text=f"Generation completed in {elapsed_str}"
                    ))
                    self.after(100, lambda: self.progress_bar.set(1.0))
                    
                    return output_path
                
                # Unexpected JSON response
                raise Exception(f"Unexpected API response: {response_json}")
            else:
                # Unknown response type
                raise Exception(f"Unexpected response content type: {content_type}")
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Error in HuggingFace generation: {e}\n{error_details}")
            
            # Provide user-friendly error messages
            error_msg = str(e)
            
            # Check for common error types
            if "token" in error_msg.lower() or "authorization" in error_msg.lower():
                error_msg = "Invalid or missing Hugging Face token. Click 'Configure API Keys' to set a valid token."
            elif "model" in error_msg.lower() and "not found" in error_msg.lower():
                error_msg = f"Model '{model_id}' not found on Hugging Face. Please check the model ID."
            elif "cuda" in error_msg.lower():
                error_msg = "CUDA error. Try reducing the image size or using a lighter model."
            
            # Raise the exception with the user-friendly message
            raise Exception(f"Hugging Face API error: {error_msg}")

    def generate_batch(self):
        """Generate multiple images in batch"""
        if self.is_generating:
            messagebox.showinfo("Generation in Progress", "Please wait for the current generation to complete.")
            return
        
        try:
            batch_count = int(self.batch_count_var.get())
        except ValueError:
            messagebox.showerror("Invalid Value", "Please enter a valid number for batch count")
            return
            
        if batch_count < 1:
            messagebox.showerror("Invalid Value", "Batch count must be at least 1")
            return
            
        # Confirm batch generation
        if batch_count > 1 and not messagebox.askyesno(
            "Confirm Batch Generation",
            f"Generate {batch_count} images with the current settings?\n\n"
            f"This will use {batch_count} API calls and may take some time."
        ):
            return
            
        # Start batch generation
        self.is_generating = True
        self.status_label.configure(text=f"Generating batch of {batch_count} images...")
        
        # Get current parameters
        service = self.service_var.get()
        prompt = self.get_prompt()
        parameters = self.get_parameters()
        
        # Create progress frame if it doesn't exist
        if not hasattr(self, 'progress_frame'):
            self.create_progress_ui()
        
        # Show progress UI
        self.show_progress_ui()
        
        # Save prompt to history
        self.save_prompt_to_history(prompt)
        
        # Start generation in a separate thread
        thread = threading.Thread(target=self._generate_batch_thread, args=(service, prompt, parameters, batch_count))
        thread.daemon = True
        thread.start()

    def _generate_batch_thread(self, service, prompt, parameters, batch_count):
        """Thread function for batch image generation"""
        all_paths = []
        failed_count = 0
        
        try:
            for i in range(batch_count):
                if not self.is_generating:  # Check if cancelled
                    break
                    
                try:
                    # Update status
                    self.after(100, lambda idx=i+1: self.status_label.configure(
                        text=f"Generating image {idx}/{batch_count}..."
                    ))
                    self.after(100, lambda idx=i+1, cnt=batch_count: self.progress_label.configure(
                        text=f"Generating image {idx} of {cnt}..."
                    ))
                    self.after(100, lambda idx=i+1, cnt=batch_count: self.progress_bar.set(idx/cnt))
                    
                    # Prepare output filename
                    timestamp = time.strftime("%Y%m%d-%H%M%S")
                    self.generation_count += 1
                    output_filename = f"{timestamp}_batch{i+1}of{batch_count}.{self.format_var.get()}"
                    output_path = os.path.join(self.config["output_directory"], output_filename)
                    
                    # Generate based on selected service
                    if service == "replicate":
                        image_path = self._generate_with_replicate(prompt, parameters, output_path)
                    else:
                        image_path = self._generate_with_huggingface(prompt, parameters, output_path)
                        
                    all_paths.append(image_path)
                    
                    # Display the latest image
                    if image_path:
                        self.after(100, lambda path=image_path: self.display_image(path))
                        
                except Exception as e:
                    print(f"Error generating image {i+1}: {e}")
                    failed_count += 1
                    
            # Update status when done
            if all_paths:
                self.after(100, lambda: self.status_label.configure(
                    text=f"Batch generation complete: {len(all_paths)} images generated, {failed_count} failed"
                ))
                
                # Update info label with the latest image
                if all_paths:
                    latest_path = all_paths[-1]
                    filename = os.path.basename(latest_path)
                    self.after(100, lambda: self.image_info_label.configure(
                        text=f"Latest: {filename} ({parameters['width']}x{parameters['height']})"
                    ))
            else:
                self.after(100, lambda: self.status_label.configure(text="Batch generation failed"))
                
        except Exception as e:
            print(f"Error in batch generation: {e}")
            self.after(100, lambda: messagebox.showerror("Batch Error", f"Error in batch generation: {e}"))
            self.after(100, lambda: self.status_label.configure(text="Batch generation error"))
        finally:
            # Ensure the generating flag is always reset
            self.after(100, lambda: setattr(self, 'is_generating', False))
            # Ensure the progress UI is hidden
            self.after(100, lambda: self.hide_progress_ui())

# Main entry point
if __name__ == "__main__":
    app = ImageGeneratorGUI()
    app.mainloop()
