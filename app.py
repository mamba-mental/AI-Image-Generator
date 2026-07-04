import os
import io
import sys
import json
import time
import random # Added for batch seed generation
import threading
import base64
import ssl
import urllib.request
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageDraw, ImageFont
import requests
import replicate
from huggingface_hub import InferenceClient # Added for HF API
import customtkinter as ctk
from dotenv import load_dotenv # Import dotenv
from loramanager import LoRAManager

# Load environment variables from .env file at the start
load_dotenv()

# Attempt to import tkinterdnd2 and verify Tcl extension is loaded
DND_ENABLED = False
DND_WORKING = False
tkdnd = None
try:
    import tkinterdnd2 as tkdnd_module
    tkdnd = tkdnd_module # Assign to global tkdnd if import succeeds
    DND_ENABLED = True
    # Verify Tcl extension is actually working by checking a command
    try:
        # Create a temporary hidden root to test the Tcl command
        _test_root = tk.Tk()
        _test_root.withdraw()
        _test_root.tk.call('tkdnd::drop_target', 'info') # Check if command exists
        DND_WORKING = True
        print("TkinterDnD2 Python library imported and Tcl extension verified.")
        _test_root.destroy()
    except tk.TclError:
        print("WARNING: TkinterDnD2 Python library imported, but Tcl extension failed verification. Drag & Drop may not work.")
        DND_WORKING = False
        try: _test_root.destroy()
        except: pass # Ignore error if destroy fails
    except Exception as e:
        print(f"WARNING: Unexpected error during TkinterDnD2 Tcl verification: {e}")
        DND_WORKING = False
        try: _test_root.destroy()
        except: pass # Ignore error if destroy fails

except ImportError:
    print("WARNING: tkinterdnd2 library not found. Drag and drop functionality will be disabled.")
    print("Install it via pip: pip install tkinterdnd2-universal")
except Exception as e:
    print(f"WARNING: Unexpected error importing tkinterdnd2: {e}")


# === Phase 3: Model-Specific UI & Global Controls ===

# (ParameterSections class removed, replaced by model-specific tabs logic below)

# === Phase 2.2: Image Upload Implementation === (Keeping this class)

class ImageUploader:
    def __init__(self, parent): # Parent should be the inner frame of the main scrollable area
        self.parent = parent
        self.image_path = None
        self.image_data = None
        self.preview_image = None

        # Create frame using CTkFrame for consistency
        self.frame = ctk.CTkFrame(parent, fg_color=FRAME_BG_COLOR)
        # Use pack for layout within the scrollable area
        self.frame.pack(fill="x", expand=True, padx=10, pady=5)

        # Add a label to the frame (optional, replaces LabelFrame text)
        label = ctk.CTkLabel(self.frame, text="Image Upload (img2img)", font=ctk.CTkFont(weight="bold"), text_color=TEXT_COLOR)
        label.pack(pady=(5, 0))

        # Main content frame inside the labeled frame
        content_frame = ctk.CTkFrame(self.frame, fg_color=FRAME_BG_COLOR)
        content_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Create upload area within the content frame
        self.upload_area(content_frame)

    def upload_area(self, parent_frame): # Pass the content frame as parent
        # Preview canvas (Resized to 300x300)
        self.preview_canvas = tk.Canvas(parent_frame, width=300, height=300, bg="#1e1e1e", highlightthickness=0)
        self.preview_canvas.pack(side=tk.LEFT, padx=10, pady=10) # Keep existing padding here

        # Add upload controls frame
        controls_frame = ctk.CTkFrame(parent_frame, fg_color=FRAME_BG_COLOR)

        # URL input
        url_frame = ctk.CTkFrame(controls_frame, fg_color=FRAME_BG_COLOR)
        self.url_entry = ctk.CTkEntry(url_frame, width=200, placeholder_text="Image URL") # Use CTkEntry
        self.url_entry.pack(side=tk.LEFT, fill="x", expand=True, padx=(0, 5))
        url_load_btn = ctk.CTkButton(url_frame, text="Load URL", width=80, command=self.load_from_url, fg_color=ACCENT_COLOR, text_color=BUTTON_TEXT_COLOR, hover_color=ACCENT_HOVER)
        url_load_btn.pack(side=tk.RIGHT)
        url_frame.pack(fill="x", pady=5)

        # File browse button
        browse_btn = ctk.CTkButton(controls_frame, text="Browse for Image", command=self.browse_image, fg_color=ACCENT_COLOR, text_color=BUTTON_TEXT_COLOR, hover_color=ACCENT_HOVER)
        browse_btn.pack(fill="x", pady=5)

        # Drop area label
        self.drop_label = ctk.CTkLabel(controls_frame, text="or drag & drop image here", text_color="grey")
        self.drop_label.pack(fill="x", pady=5)

        # Info label
        info_label = ctk.CTkLabel(controls_frame, text="Input image for image-to-image mode.\nThe aspect ratio of your output will match this image.",
                                  wraplength=200, justify="left", text_color=TEXT_COLOR)
        info_label.pack(fill="x", pady=5)

        # Clear button
        clear_btn = ctk.CTkButton(controls_frame, text="Clear Image", command=self.clear_image, fg_color="#555555", hover_color="#777777")
        clear_btn.pack(fill="x", pady=5)

        controls_frame.pack(side=tk.LEFT, fill="both", expand=True, padx=10, pady=10)

        # Setup drag and drop
        self.setup_drag_drop()

    def setup_drag_drop(self):
        """Setup drag and drop for the canvas using tkinterdnd2 if available and working"""
        # Check both if the library was imported AND if the Tcl extension seems functional
        if DND_ENABLED and DND_WORKING and tkdnd:
            try:
                self.preview_canvas.drop_target_register(tkdnd.DND_FILES)
                self.preview_canvas.dnd_bind('<<Drop>>', self._handle_drop)
                self.drop_label.configure(text="Drag & Drop Image Here") # Update label
                print("Drag and drop enabled for image uploader.")
            except tk.TclError as e:
                print(f"ERROR: Failed to register drag & drop target: {e}. Disabling DND.")
                self.drop_label.configure(text="Drag & Drop Failed\n(Tcl Error)", text_color="red")
                # Optionally unregister if partially successful? Might not be needed.
                # try: self.preview_canvas.drop_target_unregister()
                # except: pass
            except Exception as e:
                print(f"ERROR: Unexpected error setting up drag & drop: {e}. Disabling DND.")
                self.drop_label.configure(text="Drag & Drop Failed\n(Setup Error)", text_color="red")
        elif DND_ENABLED and not DND_WORKING:
             self.drop_label.configure(text="Drag & Drop Disabled\n(Tcl Verification Failed)", text_color="orange")
             print("Drag and drop setup skipped (Tcl verification failed).")
        else: # DND_ENABLED is False
            self.drop_label.configure(text="Drag & Drop Disabled\n(tkinterdnd2 not found)", text_color="red")
            print("Drag and drop setup skipped (tkinterdnd2 not available).")

    def _handle_drop(self, event):
        """Handle file drop event"""
        file_path = event.data.strip()
        if file_path.startswith('{') and file_path.endswith('}'):
            file_path = file_path[1:-1]

        if os.path.isfile(file_path):
            supported_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.bmp')
            if file_path.lower().endswith(supported_extensions):
                print(f"Dropped file: {file_path}")
                self.load_image(file_path)
            else:
                print(f"Unsupported file type dropped: {file_path}")
                messagebox.showwarning("Unsupported File", "Please drop a valid image file (PNG, JPG, WEBP, BMP).")
        else:
            print(f"Invalid path dropped: {file_path}")
            messagebox.showerror("Invalid Drop", "Please drop a single valid file.")

    def browse_image(self):
        """Open file dialog to select image"""
        file_path = filedialog.askopenfilename(
            title="Select Image",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.webp *.bmp")
            ]
        )
        if file_path:
            self.load_image(file_path)

    def load_from_url(self):
        """Load image from URL"""
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Input Error", "Please enter an image URL.")
            return
        if not url.startswith(('http://', 'https://')):
            messagebox.showwarning("Input Error", "Please enter a valid URL (starting with http:// or https://).")
            return

        print(f"Attempting to load image from URL: {url}")
        try:
            response = requests.get(url, timeout=10) # Add timeout
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

            # Check content type
            content_type = response.headers.get('content-type', '').lower()
            if not content_type.startswith('image/'):
                print(f"URL content type is not image: {content_type}")
                messagebox.showerror("Load Error", f"URL does not point to a valid image (Content-Type: {content_type}).")
                return

            image_data = io.BytesIO(response.content)
            self.load_image_from_data(image_data, source_url=url) # Pass URL for context if needed

        except requests.exceptions.RequestException as e:
            print(f"Error loading URL: {str(e)}")
            messagebox.showerror("Load Error", f"Failed to load image from URL:\n{e}")
        except Exception as e:
            print(f"Unexpected error loading URL: {str(e)}")
            messagebox.showerror("Load Error", f"An unexpected error occurred:\n{e}")


    def load_image(self, path):
        """Load image from path"""
        try:
            print(f"Loading image from path: {path}")
            image = Image.open(path)
            # Ensure image is in RGB or RGBA format for consistency
            if image.mode not in ('RGB', 'RGBA'):
                image = image.convert('RGBA')
            self.image_path = path
            self.image_data = None # Clear previous data if loading from path
            self.display_preview(image)
            print(f"Image loaded successfully: {path}")
        except FileNotFoundError:
            print(f"Error: Image file not found at {path}")
            messagebox.showerror("Load Error", f"Image file not found:\n{path}")
        except Image.UnidentifiedImageError:
            print(f"Error: Cannot identify image file {path}")
            messagebox.showerror("Load Error", f"Cannot identify image file. It might be corrupted or an unsupported format:\n{path}")
        except Exception as e:
            print(f"Error loading image: {str(e)}")
            messagebox.showerror("Load Error", f"Failed to load image:\n{e}")

    def load_image_from_data(self, data, source_url=None):
        """Load image from data buffer"""
        try:
            print(f"Loading image from data buffer (source: {source_url or 'Memory'})")
            image = Image.open(data)
            # Ensure image is in RGB or RGBA format
            if image.mode not in ('RGB', 'RGBA'):
                image = image.convert('RGBA')
            self.image_data = data # Keep the data buffer
            self.image_path = None # Clear path if loading from data/URL
            self.display_preview(image)
            print("Image loaded successfully from data buffer.")
        except Image.UnidentifiedImageError:
            print("Error: Cannot identify image data.")
            messagebox.showerror("Load Error", "Cannot identify image data. It might be corrupted or an unsupported format.")
        except Exception as e:
            print(f"Error loading image data: {str(e)}")
            messagebox.showerror("Load Error", f"Failed to load image data:\n{e}")

    def display_preview(self, image):
        """Display image preview on canvas"""
        try:
            canvas_width = 200 # Fixed preview size
            canvas_height = 200

            image.thumbnail((canvas_width, canvas_height), Image.LANCZOS)

            self.preview_image = ImageTk.PhotoImage(image)
            self.preview_canvas.delete("all")
            # Center the image on the canvas
            x_pos = (200 - self.preview_image.width()) // 2
            y_pos = (200 - self.preview_image.height()) // 2
            self.preview_canvas.create_image(x_pos, y_pos, image=self.preview_image, anchor=tk.NW)
            print(f"Image preview updated ({image.width}x{image.height})")
        except Exception as e:
            print(f"Error displaying preview: {e}")
            self.preview_canvas.delete("all")
            self.preview_canvas.create_text(100, 100, text="Preview Error", fill="red")

    def clear_image(self):
        """Clear the current image"""
        self.image_path = None
        self.image_data = None
        self.preview_image = None
        self.preview_canvas.delete("all")
        # Optionally, redraw the DND disabled message if needed
        if not (DND_ENABLED and tkdnd):
             try:
                 self.preview_canvas.create_text(100, 100, text="Drag & Drop Disabled\n(tkinterdnd2 not found)", fill="grey", font=("Arial", 10), justify="center", anchor="center")
             except tk.TclError: pass
        print("Image uploader cleared.")

    def get_image_path(self):
        """Return the current image path (prefer path if available)"""
        # This might need adjustment if API requires data buffer instead of path
        return self.image_path

# --- UI Styling ---
APP_BG_COLOR = "#000000"
FRAME_BG_COLOR = "#0a0a0a"
SURFACE_ELEVATED = "#111111"
INPUT_BG_COLOR = "#151515"
TEXT_COLOR = "#FFFFFF"
TEXT_SECONDARY = "#888888"
ACCENT_COLOR = "#8B5CF6"
ACCENT_HOVER = "#A78BFA"
BUTTON_PRIMARY_FG = "#8B5CF6"
BUTTON_SECONDARY_FG = "#1a1a1a"
BUTTON_TEXT_COLOR = "#FFFFFF"
BORDER_COLOR = "#1a1a1a"
SUCCESS_COLOR = "#4ADE80"
WARNING_COLOR = "#FBBF24"
ERROR_COLOR = "#F87171"

# Set appearance mode and default theme (Keep dark mode for base)
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue") # Use blue as base, we'll override colors

# --- Standalone Utility Functions ---

def configure_hf_api_params(params):
    """Apply comprehensive NSFW filter bypass techniques for Hugging Face"""
    # More aggressive NSFW bypass terms for negative prompt
    base_negative = "worst quality, low quality, normal quality, signature, watermark, username, artist name, text, words, blurry, censored, safety checker, explicit censoring"
    if "negative_prompt" in params and params["negative_prompt"]:
        # Combine base bypass terms with user's negative prompt, avoiding duplicates
        user_neg = params['negative_prompt']
        combined_neg = f"{base_negative}, {user_neg}"
        # Simple deduplication
        params["negative_prompt"] = ", ".join(sorted(list(set(p.strip() for p in combined_neg.split(',')))))
    else:
        params["negative_prompt"] = base_negative

    # Add stronger safety keyword to prompt
    safety_keywords = "(highly detailed, masterpiece, best quality, photorealistic:1.4), (perfectly acceptable content:1.8)" # Stronger emphasis
    if "prompt" in params and params["prompt"]:
         # Avoid adding if already present (simple check)
         if "(perfectly acceptable content" not in params["prompt"]:
              params["prompt"] = f"{params['prompt']} {safety_keywords}"
    # Set environment variable (Note: This might be better set once at startup)
    os.environ["HF_DISABLE_SAFETY"] = "true" # Ensure this is set
    print(f"HF NSFW Bypass Applied - Negative Prompt: {params.get('negative_prompt', 'N/A')}")
    return params

# Base class will always be ctk.CTk for styling consistency
# DND functionality will be added conditionally later if available

class ImageGeneratorGUI(ctk.CTk): # Inherit directly from ctk.CTk
    def __init__(self):
        super().__init__()

        # Initialize TkinterDND2 if available and working *after* super().__init__()
        if DND_ENABLED and DND_WORKING and tkdnd:
            try:
                # Attempt to make the CTk window DND-aware
                # This might still fail depending on CTk/Tkinter/Tcl interaction
                tkdnd.TkinterDnD.enable(self)
                print("Attempted to enable TkinterDND2 on CTk window.")
            except tk.TclError as dnd_tcl_error:
                 print(f"WARNING: TclError enabling TkinterDND2 on CTk window: {dnd_tcl_error}. DND might not work correctly on the main window.")
                 # We don't disable DND_WORKING here, as individual widgets might still work
            except Exception as dnd_init_error:
                print(f"WARNING: Failed to initialize TkinterDND2 on CTk window: {dnd_init_error}")

        self.config = self.load_config()
        # --- LoRAManager integration ---
        self.hf_lora_manager = LoRAManager("hf")
        self.rep_lora_manager = LoRAManager("replicate")
        # Load LoRAs using the new format-aware method
        self.hf_lora_manager.load_from_config(self.config.get("recent_loras_hf", []))
        self.rep_lora_manager.load_from_config(self.config.get("recent_loras_replicate", []))
        # Save back to config in case migration occurred
        self.config["recent_loras_hf"] = self.hf_lora_manager.get_loras()
        self.config["recent_loras_replicate"] = self.rep_lora_manager.get_loras()
        # -------------------------------

        self.title("AI Studio Void")
        self.geometry("1200x800")
        self.minsize(900, 700)
        self.configure(fg_color=APP_BG_COLOR)

        # Initialize model_param_vars early (populated by create_parameters_section)
        self.model_param_vars = {}

        # Define event handlers *before* creating UI elements that use them
        self._define_event_handlers()

        # Setup main layout grid: 2 columns (control panel + gallery), 2 rows (main + footer)
        self.grid_columnconfigure(0, weight=0, minsize=380)  # Left control panel (fixed 380px)
        self.grid_columnconfigure(1, weight=1)               # Right gallery panel (fills remaining)
        self.grid_rowconfigure(0, weight=1)                   # Main content row
        self.grid_rowconfigure(1, weight=0)                   # Footer row

        # --- Create Main Layout Frames ---

        # Left Control Panel (fixed 380px, #0a0a0a, contains scrollable + sticky bottom)
        self.left_control_panel = ctk.CTkFrame(self, width=380, fg_color=FRAME_BG_COLOR,
                                                border_width=0)
        self.left_control_panel.grid(row=0, column=0, sticky="nsew")
        self.left_control_panel.grid_propagate(False)  # Enforce fixed width
        self.left_control_panel.grid_rowconfigure(0, weight=1)  # Scrollable area expands
        self.left_control_panel.grid_rowconfigure(1, weight=0)  # Sticky bottom stays fixed
        self.left_control_panel.grid_columnconfigure(0, weight=1)

        # Scrollable content area (inside left panel)
        self.left_scrollable = ctk.CTkScrollableFrame(self.left_control_panel, fg_color=FRAME_BG_COLOR,
                                                       scrollbar_button_color="#2a2a2a",
                                                       scrollbar_button_hover_color="#3a3a3a")
        self.left_scrollable.grid(row=0, column=0, sticky="nsew")
        self.left_scrollable.grid_columnconfigure(0, weight=1)

        # Sticky bottom frame (generate button + progress bar, NOT scrollable)
        self.left_sticky_bottom = ctk.CTkFrame(self.left_control_panel, fg_color=FRAME_BG_COLOR,
                                                border_width=1, border_color=BORDER_COLOR)
        self.left_sticky_bottom.grid(row=1, column=0, sticky="ew")
        self.left_sticky_bottom.grid_columnconfigure(0, weight=1)

        # Right Gallery Panel (fills remaining space, true black)
        self.right_gallery_panel = ctk.CTkFrame(self, fg_color=APP_BG_COLOR)
        self.right_gallery_panel.grid(row=0, column=1, sticky="nsew")
        self.right_gallery_panel.grid_rowconfigure(0, weight=1)  # Image display expands
        self.right_gallery_panel.grid_rowconfigure(1, weight=0)  # Metadata bar
        self.right_gallery_panel.grid_rowconfigure(2, weight=0)  # Thumbnail strip
        self.right_gallery_panel.grid_columnconfigure(0, weight=1)

        # Footer Panel (Status Bar)
        self.footer_panel = ctk.CTkFrame(self, fg_color=FRAME_BG_COLOR, height=32)
        self.footer_panel.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.footer_panel.grid_propagate(False)

        # --- Create UI Components inside their respective frames ---

        # Left Control Panel (scrollable area)
        self.create_header(self.left_scrollable)
        self.create_service_toggle(self.left_scrollable)
        self.create_prompt_section(self.left_scrollable)
        self.create_parameters_section(self.left_scrollable)
        self.create_lora_section(self.left_scrollable)
        self.create_output_section(self.left_scrollable)

        # Left Control Panel (sticky bottom - generate button)
        self.create_generate_section(self.left_sticky_bottom)

        # Right Gallery Panel
        self.create_main_image_display(self.right_gallery_panel)

        # Footer Panel
        self.create_footer_controls(self.footer_panel)

        # Setup services *after* UI elements are created but before initialization that might use them
        self.setup_services()

        # Initialize default values and visibility *after* all elements are created
        self.initialize_default_values() # Depends on service_var

        self.current_image_path = None # Path of the main displayed image
        self.generated_image_paths = [] # List to store paths of all generated images in a batch
        self.is_generating = False
        self.generation_count = 0

    # --- Configuration & Setup ---

    def load_config(self):
        """Load configuration from JSON file or create default if not exists"""
        config_path = "config.json"
        default_config = {
            "replicate_api_key": os.environ.get("REPLICATE_API_TOKEN", ""),
            "huggingface_token": os.environ.get("HUGGINGFACE_TOKEN", ""),
            "output_directory": os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated_images"),
            "service": "replicate",
            "last_used_model_replicate": "stability-ai/sdxl:c221b2b8ef527988fb59bf24a8b97c4561f1c671f73bd389f866bfb27c061316",
            "last_used_model_hf": "black-forest-labs/FLUX.1-dev",
            "parameters": {
                "width": 1024, "height": 1024, "num_inference_steps": 50,
                "guidance_scale": 7.5, "prompt_strength": 0.8,
                "negative_prompt": "deformed, bad anatomy, disfigured, poorly drawn face, mutation, mutated, extra limb, ugly, disgusting, poorly drawn hands, missing limb, floating limbs, disconnected limbs, malformed hands, blurry, watermark, watermarked, oversaturated, censored, distorted, text, low quality, worst quality"
            },
            "gemini_api_key": os.environ.get("GEMINI_API_KEY", ""),
            "last_used_model_gemini": "gemini-2.5-flash-image",
            "advanced_mode": False, "recent_prompts": [],
            "recent_models_replicate": ["stability-ai/sdxl:c221b2b8ef527988fb59bf24a8b97c4561f1c671f73bd389f866bfb27c061316"],
            "recent_models_hf": ["black-forest-labs/FLUX.1-dev"],
            "recent_models_gemini": [
                "gemini-2.0-flash-exp-image-generation",
                "gemini-2.5-flash-image",
                "gemini-3-pro-image-preview",
                "gemini-3.1-flash-image-preview"
            ],
            "recent_loras_hf": [], # Default to new format
            "recent_loras_replicate": [] # Default to new format
        }
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    # Ensure all top-level keys exist
                    for key, value in default_config.items():
                        if key not in config:
                            config[key] = value
                        # Ensure sub-dictionaries exist and merge missing keys
                        elif isinstance(value, dict) and key == "parameters":
                            if not isinstance(config.get(key), dict):
                                config[key] = {} # Ensure it's a dict
                            for sub_key, sub_value in value.items():
                                if sub_key not in config[key]:
                                    config[key][sub_key] = sub_value
                        # Ensure list keys exist
                        elif isinstance(value, list) and key.startswith("recent_"):
                             if key not in config or not isinstance(config[key], list):
                                 config[key] = value

                    # Remove obsolete lora_scale from parameters if present
                    if "lora_scale" in config.get("parameters", {}):
                        del config["parameters"]["lora_scale"]
                        print("Removed obsolete 'lora_scale' from parameters config.")

                    os.makedirs(config["output_directory"], exist_ok=True)
                    return config
            else:
                os.makedirs(default_config["output_directory"], exist_ok=True)
                with open(config_path, 'w') as f: json.dump(default_config, f, indent=4)
                return default_config
        except Exception as e:
            print(f"Error loading/creating config: {e}")
            os.makedirs(default_config["output_directory"], exist_ok=True)
            return default_config

    def save_config(self):
        """Save configuration to JSON file"""
        try:
            # Ensure LoRA lists are saved in the correct format
            self.config["recent_loras_hf"] = self.hf_lora_manager.get_loras()
            self.config["recent_loras_replicate"] = self.rep_lora_manager.get_loras()
            with open("config.json", 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")
            messagebox.showerror("Error", f"Failed to save configuration: {e}")

    def setup_layout(self):
        """Set up the main layout grid: Left Config Panel, Right Image Panel, Bottom Status"""
        # Configure grid for 2 columns and 2 rows
        self.grid_columnconfigure(0, weight=3) # Left panel (config) - smaller weight
        self.grid_columnconfigure(1, weight=5) # Right panel (image) - larger weight
        self.grid_rowconfigure(0, weight=1)    # Main content row (panels) - expands vertically
        self.grid_rowconfigure(1, weight=0)    # Status bar row - fixed height

    def setup_services(self):
        """Initialize service abstraction layer and check for API keys, prioritizing config/UI over .env"""
        # Prioritize keys from config (set by UI) over environment variables (from .env)
        config_replicate_key = self.config.get("replicate_api_key", "")
        config_hf_token = self.config.get("huggingface_token", "")
        config_gemini_key = self.config.get("gemini_api_key", "")

        env_replicate_key = os.environ.get("REPLICATE_API_TOKEN")
        env_hf_token = os.environ.get("HUGGINGFACE_TOKEN")
        env_gemini_key = os.environ.get("GEMINI_API_KEY")

        # Use config key if available and not a placeholder, otherwise try env var, else empty
        final_replicate_key = config_replicate_key if config_replicate_key and "YOUR_REPLICATE_API_TOKEN" not in config_replicate_key else env_replicate_key or ""
        final_hf_token = config_hf_token if config_hf_token and "YOUR_HUGGINGFACE_TOKEN" not in config_hf_token else env_hf_token or ""
        final_gemini_key = config_gemini_key if config_gemini_key and "YOUR_GEMINI_API_KEY" not in config_gemini_key else env_gemini_key or ""

        # Update config if we ended up using a valid env var when config was empty/placeholder
        if not config_replicate_key or "YOUR_REPLICATE_API_TOKEN" in config_replicate_key:
            if final_replicate_key: self.config["replicate_api_key"] = final_replicate_key
        if not config_hf_token or "YOUR_HUGGINGFACE_TOKEN" in config_hf_token:
            if final_hf_token: self.config["huggingface_token"] = final_hf_token
        if not config_gemini_key or "YOUR_GEMINI_API_KEY" in config_gemini_key:
            if final_gemini_key: self.config["gemini_api_key"] = final_gemini_key

        # Set other env vars needed by libraries/logic (Keep these as they are)
        os.environ["FLUX_DISABLE_SAFETY"] = "true"
        os.environ["FLUX_GO_FAST"] = "true"

        # Update the actual environment variables used by the API clients later
        # Ensure they reflect the final determined values
        os.environ["REPLICATE_API_TOKEN"] = final_replicate_key
        os.environ["HUGGINGFACE_TOKEN"] = final_hf_token
        os.environ["GEMINI_API_KEY"] = final_gemini_key
        print(f"API Key Setup: Replicate Key Loaded: {bool(final_replicate_key)}, HF Token Loaded: {bool(final_hf_token)}, Gemini Key Loaded: {bool(final_gemini_key)}")

        # Initialize service status based on final key availability
        self.service_clients = {
            "replicate": {"initialized": bool(final_replicate_key)},
            "huggingface": {"initialized": bool(final_hf_token)},
            "gemini": {"initialized": bool(final_gemini_key)}
        }
        # Update UI status labels if they exist (might be called before UI creation)
        if hasattr(self, 'replicate_status'):
             self.replicate_status.configure(text="Ready" if self.service_clients["replicate"]["initialized"] else "Key Missing",
                                             text_color="green" if self.service_clients["replicate"]["initialized"] else "orange")
        if hasattr(self, 'huggingface_status'):
             self.huggingface_status.configure(text="Ready" if self.service_clients["huggingface"]["initialized"] else "Key Missing",
                                               text_color="green" if self.service_clients["huggingface"]["initialized"] else "orange")
        if hasattr(self, 'gemini_status'):
             self.gemini_status.configure(text="Ready (Free)" if self.service_clients["gemini"]["initialized"] else "Key Missing",
                                          text_color="green" if self.service_clients["gemini"]["initialized"] else "orange")

    # --- Define Event Handlers Before UI Creation ---
    def _define_event_handlers(self):
        """Define methods used as commands/callbacks before UI elements are created."""
        def on_service_change_internal():
            service = self.service_var.get()
            self.config["service"] = service
            self.update_model_section(self.model_section_frame) # Pass parent frame
            # Update status bar labels
            if hasattr(self, 'service_info_label'):
                self.service_info_label.configure(text=f"{service.capitalize()}")
            if hasattr(self, 'status_label'):
                self.status_label.configure(text=f"Connected to {service.capitalize()}")
            # Update service status display in left panel
            if hasattr(self, '_update_service_status_display'):
                self._update_service_status_display()
            self.save_config()
        self.on_service_change = on_service_change_internal

        def configure_api_keys_internal():
            dialog = ctk.CTkToplevel(self)
            dialog.title("Configure API Keys"); dialog.geometry("500x280")
            dialog.resizable(False, False); dialog.transient(self); dialog.grab_set(); dialog.focus_set()
            ctk.CTkLabel(dialog, text="Replicate API Key:", font=ctk.CTkFont(size=14)).grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")
            replicate_key_var = tk.StringVar(value=self.config.get("replicate_api_key", ""))
            ctk.CTkEntry(dialog, textvariable=replicate_key_var, width=300).grid(row=0, column=1, padx=20, pady=(20, 10), sticky="ew")
            ctk.CTkLabel(dialog, text="Hugging Face Token:", font=ctk.CTkFont(size=14)).grid(row=1, column=0, padx=20, pady=10, sticky="w")
            hf_token_var = tk.StringVar(value=self.config.get("huggingface_token", ""))
            ctk.CTkEntry(dialog, textvariable=hf_token_var, width=300).grid(row=1, column=1, padx=20, pady=10, sticky="ew")
            ctk.CTkLabel(dialog, text="Gemini API Key:", font=ctk.CTkFont(size=14)).grid(row=2, column=0, padx=20, pady=10, sticky="w")
            gemini_key_var = tk.StringVar(value=self.config.get("gemini_api_key", ""))
            ctk.CTkEntry(dialog, textvariable=gemini_key_var, width=300).grid(row=2, column=1, padx=20, pady=10, sticky="ew")
            ctk.CTkLabel(dialog, text="(Free tier - get key at ai.google.dev)", font=ctk.CTkFont(size=11), text_color="grey").grid(row=3, column=1, padx=20, pady=(0, 5), sticky="w")

            # Define save_keys function *before* the button uses it
            def save_keys():
                # Update config AND environment variables when keys are saved in the dialog
                self.config["replicate_api_key"] = replicate_key_var.get()
                self.config["huggingface_token"] = hf_token_var.get()
                self.config["gemini_api_key"] = gemini_key_var.get()
                os.environ["REPLICATE_API_TOKEN"] = self.config["replicate_api_key"] # Update env var
                os.environ["HUGGINGFACE_TOKEN"] = self.config["huggingface_token"] # Update env var
                os.environ["GEMINI_API_KEY"] = self.config["gemini_api_key"] # Update env var
                self.save_config()

                # Re-check service readiness and update UI status
                self.setup_services() # Call setup_services again to update status based on new keys

                dialog.destroy() # Destroy the dialog after saving

            # Create the button *after* save_keys is defined
            ctk.CTkButton(dialog, text="Save", command=save_keys).grid(row=4, column=0, columnspan=2, padx=20, pady=20)

        self.configure_api_keys = configure_api_keys_internal


    # --- UI Creation Methods ---
    # Modified to accept parent frame (left_panel or right_panel)

    # --- Placeholder UI Creation Methods ---
    # TODO: Implement the actual content for these sections based on UI spec

    def create_logo_section(self, parent):
        """Placeholder for logo section"""
        logo_frame = ctk.CTkFrame(parent, fg_color=FRAME_BG_COLOR, height=50)
        logo_frame.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(logo_frame, text="Logo Area", text_color=TEXT_COLOR).pack(expand=True)
        print("Placeholder: create_logo_section called")

    def create_thumbnail_list(self, parent):
        """Placeholder for thumbnail list section"""
        thumb_frame = ctk.CTkScrollableFrame(parent, fg_color=FRAME_BG_COLOR)
        thumb_frame.pack(fill="both", expand=True, padx=5, pady=5)
        ctk.CTkLabel(thumb_frame, text="Thumbnails", text_color=TEXT_COLOR).pack(expand=True)
        print("Placeholder: create_thumbnail_list called")
        # Store reference for later use if needed
        self.thumbnail_list_frame = thumb_frame 

    def create_main_image_display(self, parent):
        """Placeholder for main image display section"""
        # Reusing existing create_image_display logic as a base
        self.create_image_display(parent) # Call the existing method
        print("Placeholder: create_main_image_display called (using existing create_image_display)")


    def create_lora_section(self, parent):
        """Placeholder for LoRA section"""
        # Reusing existing create_model_section logic which includes LoRA
        self.create_model_section(parent) # Call the existing method
        print("Placeholder: create_lora_section called (using existing create_model_section)")


    def create_footer_controls(self, parent):
        """Placeholder for footer controls section"""
        # Reusing existing create_status_bar logic
        self.create_status_bar(parent) # Call the existing method
        print("Placeholder: create_footer_controls called (using existing create_status_bar)")

    # --- Actual UI Creation Methods (Keep existing ones below placeholders) ---

    def create_header(self, parent):
        """Create the header section inside the parent frame (left_panel)"""
        header_frame = ctk.CTkFrame(parent, fg_color=FRAME_BG_COLOR, height=48)
        header_frame.pack(fill="x", padx=12, pady=(12, 4))

        # Sparkle icon (unicode) + title
        sparkle_label = ctk.CTkLabel(header_frame, text="\u2728", font=ctk.CTkFont(size=18),
                                      text_color=ACCENT_COLOR)
        sparkle_label.pack(side="left", padx=(4, 6), pady=4)

        title_label = ctk.CTkLabel(header_frame, text="AI Studio Void",
                                    font=ctk.CTkFont(size=18, weight="bold"),
                                    text_color=TEXT_COLOR)
        title_label.pack(side="left", padx=0, pady=4)

        # Settings button (right-aligned)
        settings_button = ctk.CTkButton(header_frame, text="\u2699", width=32, height=32,
                                         font=ctk.CTkFont(size=16),
                                         fg_color="transparent", hover_color="#1a1a1a",
                                         text_color=TEXT_SECONDARY,
                                         command=self.configure_api_keys)
        settings_button.pack(side="right", padx=4, pady=4)

        # Advanced mode var (still needed for toggle_advanced_mode logic)
        self.advanced_mode_var = tk.BooleanVar(value=self.config["advanced_mode"])

    def create_service_toggle(self, parent):
        """Create the service toggle section as a segmented control"""
        service_frame = ctk.CTkFrame(parent, fg_color="transparent")
        service_frame.pack(fill="x", padx=12, pady=(8, 4))

        self.service_var = tk.StringVar(value=self.config["service"])

        # Segmented button for service selection
        self.service_segmented = ctk.CTkSegmentedButton(
            service_frame,
            values=["replicate", "huggingface", "gemini"],
            variable=self.service_var,
            command=lambda val: self.on_service_change(),
            fg_color=SURFACE_ELEVATED,
            selected_color=ACCENT_COLOR,
            selected_hover_color=ACCENT_HOVER,
            unselected_color=SURFACE_ELEVATED,
            unselected_hover_color="#1a1a1a",
            text_color=TEXT_COLOR,
            text_color_disabled=TEXT_SECONDARY,
            font=ctk.CTkFont(size=12, weight="bold"),
            height=36,
            corner_radius=8,
            border_width=1
        )
        self.service_segmented.pack(fill="x", pady=2)

        # Hidden status labels (still needed by setup_services for updates)
        self.replicate_status = ctk.CTkLabel(service_frame, text="", text_color="grey",
                                              font=ctk.CTkFont(size=10))
        self.huggingface_status = ctk.CTkLabel(service_frame, text="", text_color="grey",
                                                font=ctk.CTkFont(size=10))
        self.gemini_status = ctk.CTkLabel(service_frame, text="", text_color="grey",
                                           font=ctk.CTkFont(size=10))
        # Show only the active service status
        self._update_service_status_display()

    def _update_service_status_display(self):
        """Show status text for the currently selected service only"""
        if not hasattr(self, 'replicate_status'):
            return
        service = self.service_var.get()
        # Hide all first
        self.replicate_status.pack_forget()
        self.huggingface_status.pack_forget()
        self.gemini_status.pack_forget()
        # Show the active one
        if service == "replicate":
            self.replicate_status.pack(fill="x", padx=4, pady=(2, 0))
        elif service == "huggingface":
            self.huggingface_status.pack(fill="x", padx=4, pady=(2, 0))
        else:
            self.gemini_status.pack(fill="x", padx=4, pady=(2, 0))

    def create_prompt_section(self, parent):
        """Create the prompt input section"""
        prompt_frame = ctk.CTkFrame(parent, fg_color="transparent")
        prompt_frame.pack(fill="x", padx=12, pady=(8, 4))

        # Prompt label
        ctk.CTkLabel(prompt_frame, text="Prompt",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#cccccc").pack(anchor="w", padx=0, pady=(0, 4))

        # Main Prompt (monospace, 120px min height)
        self.prompt_text = ctk.CTkTextbox(prompt_frame, height=120, wrap="word",
                                       text_color=TEXT_COLOR, fg_color=SURFACE_ELEVATED,
                                       border_width=1, border_color=BORDER_COLOR,
                                       corner_radius=8,
                                       font=ctk.CTkFont(family="Consolas", size=13))
        self.prompt_text.pack(fill="x", padx=0, pady=0)
        self.prompt_text.insert("1.0", "A beautiful woman on the beach, realistic, detailed, high quality")

        # Negative Prompt label with "Optional" tag
        neg_label_frame = ctk.CTkFrame(prompt_frame, fg_color="transparent")
        neg_label_frame.pack(fill="x", padx=0, pady=(12, 4))
        self.negative_prompt_label = ctk.CTkLabel(neg_label_frame, text="Negative Prompt",
                                                   font=ctk.CTkFont(size=12, weight="bold"),
                                                   text_color="#cccccc")
        self.negative_prompt_label.pack(side="left")
        ctk.CTkLabel(neg_label_frame, text="Optional",
                     font=ctk.CTkFont(size=10),
                     text_color=TEXT_SECONDARY).pack(side="right")

        # Negative Prompt textbox (80px, monospace)
        self.negative_toggle_var = tk.BooleanVar(value=self.config.get("use_negative_prompt", True))
        self.negative_prompt_text = ctk.CTkTextbox(prompt_frame, height=80, wrap="word",
                                                 text_color=TEXT_COLOR, fg_color=SURFACE_ELEVATED,
                                                 border_width=1, border_color=BORDER_COLOR,
                                                 corner_radius=8,
                                                 font=ctk.CTkFont(family="Consolas", size=13))
        self.negative_prompt_text.pack(fill="x", padx=0, pady=0)
        self.negative_prompt_text.insert("1.0", self.config["parameters"]["negative_prompt"])

        # Toggles Frame (trigger words)
        toggles_frame = ctk.CTkFrame(prompt_frame, fg_color="transparent")
        toggles_frame.pack(fill="x", padx=0, pady=(8, 0))

        # Trigger Words Toggle
        self.trigger_toggle_var = tk.BooleanVar(value=self.config.get("use_trigger_words", False))
        trigger_toggle = ctk.CTkSwitch(toggles_frame, text="Use Trigger Words",
                                     variable=self.trigger_toggle_var,
                                     command=self.toggle_trigger_words,
                                     button_color=ACCENT_COLOR,
                                     progress_color=ACCENT_COLOR,
                                     font=ctk.CTkFont(size=11),
                                     text_color=TEXT_SECONDARY)
        trigger_toggle.pack(side="left", padx=0)

        self.trigger_words_entry = ctk.CTkEntry(prompt_frame, placeholder_text="Trigger words...",
                                              text_color=TEXT_COLOR, fg_color=SURFACE_ELEVATED,
                                              border_width=1, border_color=BORDER_COLOR,
                                              corner_radius=6, height=32,
                                              font=ctk.CTkFont(size=12),
                                              state="normal" if self.trigger_toggle_var.get() else "disabled")
        self.trigger_words_entry.pack(fill="x", padx=0, pady=(4, 0))
        
        # If config has trigger words, populate the entry
        if "trigger_words" in self.config:
            self.trigger_words_entry.delete(0, "end")
            self.trigger_words_entry.insert(0, self.config["trigger_words"])

    def create_image_uploader(self, parent):
        """Create the image upload section inside the parent frame (left_panel)"""
        # ImageUploader now creates its own frame and packs itself
        self.image_uploader = ImageUploader(parent)
        # No need to call grid/pack here as it's done in ImageUploader.__init__

    def create_parameters_section(self, parent):
        """Create the parameters section inside a parameter card"""
        # Parameter card with #111111 bg, rounded corners, border
        parameters_frame = ctk.CTkFrame(parent, fg_color=SURFACE_ELEVATED,
                                         corner_radius=8, border_width=1,
                                         border_color=BORDER_COLOR)
        parameters_frame.pack(fill="x", padx=12, pady=(8, 4))

        # Header row: "Parameters" + Reset button
        param_header = ctk.CTkFrame(parameters_frame, fg_color="transparent")
        param_header.pack(fill="x", padx=12, pady=(12, 8))
        ctk.CTkLabel(param_header, text="Parameters",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#cccccc").pack(side="left")

        def reset_parameters():
            self.global_width_var.set(1024)
            self.global_height_var.set(1024)
            self.seed_var.set("")
            self.output_format_var.set("webp")
            self.output_quality_var.set(80)
            self.megapixels_var.set("1")
            self.go_fast_var.set(True)

        ctk.CTkButton(param_header, text="Reset", width=50, height=24,
                       font=ctk.CTkFont(size=11),
                       fg_color="transparent", hover_color="#1a1a1a",
                       text_color=TEXT_SECONDARY, border_width=0,
                       command=reset_parameters).pack(side="right")

        # Separator under header
        ctk.CTkFrame(parameters_frame, fg_color=BORDER_COLOR, height=1).pack(fill="x", padx=12, pady=(0, 8))

        # --- Aspect Ratio / Size Controls ---
        size_label = ctk.CTkLabel(parameters_frame, text="Aspect Ratio",
                                   font=ctk.CTkFont(size=11),
                                   text_color=TEXT_SECONDARY)
        size_label.pack(anchor="w", padx=12, pady=(0, 4))

        global_dim_frame = ctk.CTkFrame(parameters_frame, fg_color="transparent")
        global_dim_frame.pack(fill="x", padx=12, pady=(0, 8))
        global_dim_frame.grid_columnconfigure(1, weight=1)
        global_dim_frame.grid_columnconfigure(3, weight=1)
        ctk.CTkLabel(global_dim_frame, text="W:", text_color=TEXT_SECONDARY,
                     font=ctk.CTkFont(size=11)).grid(row=0, column=0, padx=(0, 4), pady=2, sticky="w")
        self.global_width_var = tk.IntVar(value=1024)
        ctk.CTkEntry(global_dim_frame, textvariable=self.global_width_var, width=70,
                     height=32, fg_color="#1a1a1a", border_color="#2a2a2a",
                     border_width=1, corner_radius=4,
                     font=ctk.CTkFont(family="Consolas", size=12)).grid(row=0, column=1, padx=(0, 8), pady=2, sticky="w")
        ctk.CTkLabel(global_dim_frame, text="H:", text_color=TEXT_SECONDARY,
                     font=ctk.CTkFont(size=11)).grid(row=0, column=2, padx=(0, 4), pady=2, sticky="w")
        self.global_height_var = tk.IntVar(value=1024)
        ctk.CTkEntry(global_dim_frame, textvariable=self.global_height_var, width=70,
                     height=32, fg_color="#1a1a1a", border_color="#2a2a2a",
                     border_width=1, corner_radius=4,
                     font=ctk.CTkFont(family="Consolas", size=12)).grid(row=0, column=3, padx=0, pady=2, sticky="w")

        # --- Model-Specific Parameters ---
        # Create the main notebook for model tabs
        self.model_param_notebook = ctk.CTkTabview(parameters_frame, fg_color=SURFACE_ELEVATED,
                                                     segmented_button_fg_color="#1a1a1a",
                                                     segmented_button_selected_color=ACCENT_COLOR,
                                                     segmented_button_selected_hover_color=ACCENT_HOVER,
                                                     segmented_button_unselected_color="#1a1a1a",
                                                     segmented_button_unselected_hover_color="#252525")
        self.model_param_notebook.pack(fill="x", expand=True, padx=8, pady=(0, 4))
        self.model_param_tabs = {} # To store frames for each model tab

        # Define model configurations (matching the prompt)
        # TODO: Populate this with actual model IDs used in the dropdowns later
        model_configs = {
            "black-forest-labs/flux-dev-lora": { # Assuming this is a valid model ID
                # Removed num_outputs from model-specific params
                "params": ["prompt_strength", "num_inference_steps", "guidance"],
                "defaults": {"prompt_strength": 0.8, "num_inference_steps": 28, "guidance": 3.0},
                "ranges": {"prompt_strength": (0, 1), "num_inference_steps": (1, 50), "guidance": (0, 10)}
            },
             "black-forest-labs/flux-dev": {
                 # Removed num_outputs from model-specific params
                 "params": ["prompt_strength", "num_inference_steps", "guidance"],
                 "defaults": {"prompt_strength": 0.8, "num_inference_steps": 28, "guidance": 3.5},
                 "ranges": {"prompt_strength": (0, 1), "num_inference_steps": (1, 50), "guidance": (0, 10)}
             },
             "black-forest-labs/flux-1.1-pro-ultra": {
                 "params": ["image_prompt_strength", "aspect_ratio", "safety_tolerance", "raw"],
                 "defaults": {"image_prompt_strength": 0.1, "aspect_ratio": "16:9", "safety_tolerance": 2, "raw": False}, # Default to 16:9
                 "ranges": {"image_prompt_strength": (0, 1), "safety_tolerance": (1, 6)}, # Max 6
                 "options": {
                     "aspect_ratio": [ # Comprehensive list
                         "1:1", "3:2", "2:3", "4:3", "3:4", "5:4", "4:5", "16:9", "9:16", "21:9", "9:21",
                         "1.17:1 (6x7)", "1.37:1 (Academy)", "1.66:1 (Super 16mm)", "1.85:1 (VistaVision)",
                         "2:1 (6x12)", "2.2:1 (70mm)", "2.35:1 (CinemaScope)", "2.83:1 (6x17)"
                     ]
                 }
             },
             "black-forest-labs/flux-1.1-pro": {
                 "params": ["width", "height", "safety_tolerance", "prompt_upsampling"],
                 "defaults": {"width": 1024, "height": 1024, "safety_tolerance": 2, "prompt_upsampling": False},
                 "ranges": {"width": (256, 1440, 32), "height": (256, 1440, 32), "safety_tolerance": (1, 6)} # Max 6
             },
             "black-forest-labs/flux-pro": {
                 "params": ["width", "height", "steps", "guidance", "interval", "safety_tolerance", "prompt_upsampling"],
                 "defaults": {"width": 1024, "height": 1024, "steps": 25, "guidance": 3.0, "interval": 2, "safety_tolerance": 2, "prompt_upsampling": False},
                 "ranges": {"width": (256, 1440, 32), "height": (256, 1440, 32), "steps": (1, 50), "guidance": (2, 5), "interval": (1, 4), "safety_tolerance": (1, 6)} # Max 6
             }
            # Add other models as needed
        }

        # Create tabs and widgets for each model
        self.model_param_vars = {} # Store tk variables for each model's params
        for model_id, config in model_configs.items():
            tab_name = model_id.split('/')[-1] # Use model name part for tab label
            tab = self.model_param_notebook.add(tab_name)
            self.model_param_tabs[model_id] = tab
            self.model_param_vars[model_id] = {}

            # Create widgets within the tab's frame (tab)
            param_frame = ctk.CTkFrame(tab, fg_color="transparent")
            param_frame.pack(fill="both", expand=True, padx=5, pady=5)
            param_frame.grid_columnconfigure(1, weight=1) # Allow controls to expand

            row_idx = 0
            for param_name in config["params"]:
                self.model_param_vars[model_id][param_name] = self._create_param_widget(
                    param_frame, param_name, config, row_idx
                )
                row_idx += 1

        # --- Seed Input (inside parameter card) ---
        seed_frame = ctk.CTkFrame(parameters_frame, fg_color="transparent")
        seed_frame.pack(fill="x", padx=12, pady=(4, 8))
        ctk.CTkLabel(seed_frame, text="Seed", text_color=TEXT_SECONDARY,
                     font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(0, 4))
        seed_input_frame = ctk.CTkFrame(seed_frame, fg_color="transparent")
        seed_input_frame.pack(fill="x")
        self.seed_var = tk.StringVar(value="")
        self.seed_entry = ctk.CTkEntry(seed_input_frame, textvariable=self.seed_var,
                                        placeholder_text="Random (-1)", height=32,
                                        fg_color="#1a1a1a", border_color="#2a2a2a",
                                        border_width=1, corner_radius=4,
                                        font=ctk.CTkFont(family="Consolas", size=12))
        self.seed_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        # Random seed button
        ctk.CTkButton(seed_input_frame, text="\U0001F3B2", width=32, height=32,
                       fg_color="#1a1a1a", hover_color="#252525",
                       border_width=1, border_color="#2a2a2a",
                       corner_radius=4, font=ctk.CTkFont(size=14),
                       command=lambda: self.seed_var.set(str(random.randint(0, 2**32 - 1)))
                       ).pack(side="right")

        # --- Global Controls (below parameter card, separate section) ---
        global_frame = ctk.CTkFrame(parameters_frame, fg_color="transparent")
        global_frame.pack(fill="x", padx=12, pady=(4, 12))
        global_frame.grid_columnconfigure(1, weight=1)

        # Output Format
        ctk.CTkLabel(global_frame, text="Format:", text_color=TEXT_SECONDARY,
                     font=ctk.CTkFont(size=11)).grid(row=0, column=0, padx=(0, 8), pady=3, sticky="w")
        self.output_format_var = tk.StringVar(value=self.config.get("output_format", "webp"))
        self.output_format_combo = ctk.CTkComboBox(global_frame, values=["webp", "png", "jpg"],
                                                     variable=self.output_format_var, width=90,
                                                     height=28, corner_radius=4,
                                                     fg_color="#1a1a1a", border_color="#2a2a2a",
                                                     button_color="#1a1a1a",
                                                     dropdown_fg_color=SURFACE_ELEVATED,
                                                     font=ctk.CTkFont(size=11),
                                                     command=self._update_quality_slider_state)
        self.output_format_combo.grid(row=0, column=1, padx=0, pady=3, sticky="w")

        # Output Quality (slider with value badge)
        ctk.CTkLabel(global_frame, text="Quality:", text_color=TEXT_SECONDARY,
                     font=ctk.CTkFont(size=11)).grid(row=1, column=0, padx=(0, 8), pady=3, sticky="w")
        quality_row = ctk.CTkFrame(global_frame, fg_color="transparent")
        quality_row.grid(row=1, column=1, padx=0, pady=3, sticky="ew")
        quality_row.grid_columnconfigure(0, weight=1)
        self.output_quality_var = tk.IntVar(value=self.config.get("output_quality", 80))
        self.output_quality_slider = ctk.CTkSlider(quality_row, from_=0, to=100,
                                                     number_of_steps=100,
                                                     variable=self.output_quality_var,
                                                     fg_color="#1a1a1a",
                                                     progress_color=ACCENT_COLOR,
                                                     button_color="#FFFFFF",
                                                     button_hover_color=ACCENT_HOVER,
                                                     height=14)
        self.output_quality_slider.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        # Value badge
        self.output_quality_label = ctk.CTkLabel(quality_row,
                                                  text=f"{self.output_quality_var.get()}",
                                                  text_color="#cccccc", width=36, height=22,
                                                  fg_color="#1a1a1a", corner_radius=4,
                                                  font=ctk.CTkFont(family="Consolas", size=11))
        self.output_quality_label.grid(row=0, column=1, padx=0, sticky="e")
        self.output_quality_var.trace_add("write", lambda *args: self.output_quality_label.configure(text=f"{self.output_quality_var.get()}"))
        self._update_quality_slider_state()

        # Megapixels
        ctk.CTkLabel(global_frame, text="Megapixels:", text_color=TEXT_SECONDARY,
                     font=ctk.CTkFont(size=11)).grid(row=2, column=0, padx=(0, 8), pady=3, sticky="w")
        self.megapixels_var = tk.StringVar(value=str(self.config.get("megapixels", "1")))
        ctk.CTkComboBox(global_frame, values=[str(i) for i in range(1, 9)],
                        variable=self.megapixels_var, width=70, height=28,
                        corner_radius=4, fg_color="#1a1a1a", border_color="#2a2a2a",
                        button_color="#1a1a1a", dropdown_fg_color=SURFACE_ELEVATED,
                        font=ctk.CTkFont(size=11)).grid(row=2, column=1, padx=0, pady=3, sticky="w")

        # Go Fast
        self.go_fast_var = tk.BooleanVar(value=self.config.get("go_fast", True))
        ctk.CTkCheckBox(global_frame, text="Go Fast", variable=self.go_fast_var,
                        text_color=TEXT_SECONDARY, fg_color=ACCENT_COLOR,
                        hover_color=ACCENT_HOVER, checkbox_height=16, checkbox_width=16,
                        font=ctk.CTkFont(size=11)).grid(row=3, column=0, columnspan=2, padx=0, pady=3, sticky="w")

        # TODO: Add logic to show/hide model tabs based on selected service (Replicate/HF)
        # TODO: Add logic to load/save model-specific params from/to config

    def create_model_section(self, parent):
        """Create the model selection section inside the parent frame (left_panel)"""
        # Model selector label
        ctk.CTkLabel(parent, text="Model", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#cccccc").pack(anchor="w", padx=12, pady=(8, 4))

        self.model_section_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.model_section_frame.pack(fill="x", padx=12, pady=(0, 4))
        self.model_section_frame.grid_columnconfigure(1, weight=1)

        # Replicate widgets (created once, gridded/forgotten in update)
        self.replicate_model_label = ctk.CTkLabel(self.model_section_frame, text="Model:",
                                                    font=ctk.CTkFont(size=11), text_color=TEXT_SECONDARY)
        self.replicate_model_var = tk.StringVar(value=self.config["last_used_model_replicate"])
        self.replicate_model_combo = ctk.CTkComboBox(self.model_section_frame,
                                                       values=self.config["recent_models_replicate"],
                                                       variable=self.replicate_model_var, width=250,
                                                       height=32, corner_radius=6,
                                                       fg_color=SURFACE_ELEVATED, border_color=BORDER_COLOR,
                                                       button_color=BORDER_COLOR,
                                                       dropdown_fg_color=SURFACE_ELEVATED,
                                                       font=ctk.CTkFont(size=11),
                                                       state="readonly")
        self.add_replicate_model_button = ctk.CTkButton(self.model_section_frame, text="+", width=32, height=32,
                                                          corner_radius=6, fg_color=BUTTON_SECONDARY_FG,
                                                          border_width=1, border_color="#333333",
                                                          hover_color="#252525", text_color=TEXT_COLOR,
                                                          command=self.add_replicate_model)

        # Hugging Face widgets
        self.hf_model_label = ctk.CTkLabel(self.model_section_frame, text="Model:",
                                            font=ctk.CTkFont(size=11), text_color=TEXT_SECONDARY)
        self.hf_model_var = tk.StringVar(value=self.config["last_used_model_hf"])
        self.hf_model_combo = ctk.CTkComboBox(self.model_section_frame,
                                                values=self.config["recent_models_hf"],
                                                variable=self.hf_model_var, width=250,
                                                height=32, corner_radius=6,
                                                fg_color=SURFACE_ELEVATED, border_color=BORDER_COLOR,
                                                button_color=BORDER_COLOR,
                                                dropdown_fg_color=SURFACE_ELEVATED,
                                                font=ctk.CTkFont(size=11),
                                                state="readonly")
        self.add_hf_model_button = ctk.CTkButton(self.model_section_frame, text="+", width=32, height=32,
                                                    corner_radius=6, fg_color=BUTTON_SECONDARY_FG,
                                                    border_width=1, border_color="#333333",
                                                    hover_color="#252525", text_color=TEXT_COLOR,
                                                    command=self.add_hf_model)

        # Gemini widgets
        self.gemini_model_label = ctk.CTkLabel(self.model_section_frame, text="Model:",
                                                font=ctk.CTkFont(size=11), text_color=TEXT_SECONDARY)
        gemini_models = self.config.get("recent_models_gemini", ["gemini-2.5-flash-image"])
        self.gemini_model_var = tk.StringVar(value=self.config.get("last_used_model_gemini", "gemini-2.5-flash-image"))
        self.gemini_model_combo = ctk.CTkComboBox(self.model_section_frame, values=gemini_models,
                                                    variable=self.gemini_model_var, width=250,
                                                    height=32, corner_radius=6,
                                                    fg_color=SURFACE_ELEVATED, border_color=BORDER_COLOR,
                                                    button_color=BORDER_COLOR,
                                                    dropdown_fg_color=SURFACE_ELEVATED,
                                                    font=ctk.CTkFont(size=11),
                                                    state="readonly")
        self.add_gemini_model_button = ctk.CTkButton(self.model_section_frame, text="+", width=32, height=32,
                                                       corner_radius=6, fg_color=BUTTON_SECONDARY_FG,
                                                       border_width=1, border_color="#333333",
                                                       hover_color="#252525", text_color=TEXT_COLOR,
                                                       command=self.add_gemini_model)
        # Gemini info label
        self.gemini_info_label = ctk.CTkLabel(self.model_section_frame,
                                               text="Free tier, ~500 images/day. No LoRA.",
                                               font=ctk.CTkFont(size=10), text_color=TEXT_SECONDARY)

        # --- LoRA Management (Common Structure) ---
        self.lora_management_frame = ctk.CTkFrame(self.model_section_frame, fg_color="transparent")
        self.lora_management_frame.grid_columnconfigure(0, weight=1) # Allow listbox to expand

        # Replicate LoRA Widgets - Dynamic List Area
        self.rep_lora_label = ctk.CTkLabel(self.lora_management_frame, text="Replicate LoRAs (Select multiple):", font=ctk.CTkFont(size=14), text_color=TEXT_COLOR)
        # Frame to hold the dynamic list of LoRA entries
        self.rep_lora_list_frame = ctk.CTkFrame(self.lora_management_frame, fg_color="transparent")
        # Add/Remove buttons frame
        self.rep_lora_button_frame = ctk.CTkFrame(self.lora_management_frame, fg_color="transparent")
        self.add_rep_lora_button = ctk.CTkButton(self.rep_lora_button_frame, text="Add", width=60, command=self.add_rep_lora, fg_color=ACCENT_COLOR, text_color=BUTTON_TEXT_COLOR, hover_color=ACCENT_HOVER)
        # Remove button is now per-LoRA entry

        # Hugging Face LoRA Widgets - Dynamic List Area
        self.hf_lora_label = ctk.CTkLabel(self.lora_management_frame, text="HuggingFace LoRAs (Select multiple):", font=ctk.CTkFont(size=14), text_color=TEXT_COLOR)
        # Frame to hold the dynamic list of HF LoRA entries
        self.hf_lora_list_frame = ctk.CTkFrame(self.lora_management_frame, fg_color="transparent")
        # Add/Remove buttons frame for HF
        self.hf_lora_button_frame = ctk.CTkFrame(self.lora_management_frame, fg_color="transparent")
        self.add_hf_lora_button = ctk.CTkButton(self.hf_lora_button_frame, text="Add", width=60, command=self.add_hf_lora, fg_color=ACCENT_COLOR, text_color=BUTTON_TEXT_COLOR, hover_color=ACCENT_HOVER)
        # Remove button is now per-LoRA entry for HF as well

        # LoRA Scale Slider REMOVED - Now per-LoRA for both

        self.update_model_section(self.model_section_frame) # Initial update

    def update_model_section(self, parent_frame): # Accept parent frame
        """Update the model section based on the selected service"""
        for widget in parent_frame.grid_slaves(): widget.grid_forget() # Use parent_frame

        # Consistent padding (padx=5, pady=2)
        if self.service_var.get() == "replicate":
            # Grid Replicate Model Selection
            self.replicate_model_label.grid(row=0, column=0, padx=5, pady=2, sticky="w")
            self.replicate_model_combo.grid(row=0, column=1, padx=5, pady=2, sticky="ew")
            self.add_replicate_model_button.grid(row=0, column=2, padx=5, pady=2, sticky="e")
            # Grid Replicate LoRA Management Frame
            self.lora_management_frame.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=5, pady=(5,2))
            self.lora_management_frame.grid_rowconfigure(1, weight=1) # Allow list frame to expand if needed

            # Grid Widgets *inside* the LoRA frame for Replicate
            self.rep_lora_label.grid(in_=self.lora_management_frame, row=0, column=0, columnspan=2, sticky="w", padx=5, pady=(5,0))
            # Grid the frame that will hold the dynamic list
            self.rep_lora_list_frame.grid(in_=self.lora_management_frame, row=1, column=0, columnspan=2, sticky="nsew", padx=5, pady=2)
            self.rep_lora_list_frame.grid_columnconfigure(1, weight=1) # Allow URL label to expand

            # Grid the Add button frame below the list frame
            self.rep_lora_button_frame.grid(in_=self.lora_management_frame, row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=(0, 5))
            self.add_rep_lora_button.pack(side="left", padx=5) # Pack Add button

            # --- Dynamically create and grid LoRA entries ---
            self._update_rep_lora_list_ui()

        elif self.service_var.get() == "huggingface":
            # Grid HF Base Model
            self.hf_model_label.grid(row=0, column=0, padx=5, pady=2, sticky="w")
            self.hf_model_combo.grid(row=0, column=1, padx=5, pady=2, sticky="ew")
            self.add_hf_model_button.grid(row=0, column=2, padx=5, pady=2, sticky="e")
            # Grid HF LoRA Management Frame
            self.lora_management_frame.grid(row=1, column=0, columnspan=3, sticky="ew", padx=5, pady=(5,2))
            # Grid Widgets *inside* the LoRA frame for HF
            self.hf_lora_label.grid(in_=self.lora_management_frame, row=0, column=0, columnspan=2, sticky="w", padx=5, pady=(5,0))
            # Grid the frame that will hold the dynamic HF list
            self.hf_lora_list_frame.grid(in_=self.lora_management_frame, row=1, column=0, columnspan=2, sticky="nsew", padx=5, pady=2)
            self.hf_lora_list_frame.grid_columnconfigure(1, weight=1) # Allow URL label to expand

            # Grid the Add button frame below the list frame for HF
            self.hf_lora_button_frame.grid(in_=self.lora_management_frame, row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=(0, 5))
            self.add_hf_lora_button.pack(side="left", padx=5) # Pack Add button

            # --- Dynamically create and grid HF LoRA entries ---
            self._update_hf_lora_list_ui()

        else: # Gemini
            # Grid Gemini Model Selection
            self.gemini_model_label.grid(row=0, column=0, padx=5, pady=2, sticky="w")
            self.gemini_model_combo.grid(row=0, column=1, padx=5, pady=2, sticky="ew")
            self.add_gemini_model_button.grid(row=0, column=2, padx=5, pady=2, sticky="e")
            # Gemini info label (no LoRA support)
            self.gemini_info_label.grid(row=1, column=0, columnspan=3, padx=5, pady=2, sticky="w")

    def create_output_section(self, parent):
        """Create the output configuration section (no generate button - that's in sticky bottom)"""
        output_frame = ctk.CTkFrame(parent, fg_color="transparent")
        output_frame.pack(fill="x", padx=12, pady=(8, 4))
        output_frame.grid_columnconfigure(1, weight=1)

        # Output directory row
        ctk.CTkLabel(output_frame, text="Output:", text_color=TEXT_SECONDARY,
                     font=ctk.CTkFont(size=11)).grid(row=0, column=0, padx=(0, 6), pady=3, sticky="w")
        self.output_dir_var = tk.StringVar(value=self.config["output_directory"])
        ctk.CTkEntry(output_frame, textvariable=self.output_dir_var, height=28,
                     state="readonly", fg_color="#1a1a1a", border_color="#2a2a2a",
                     border_width=1, corner_radius=4,
                     font=ctk.CTkFont(size=10)).grid(row=0, column=1, padx=0, pady=3, sticky="ew")
        ctk.CTkButton(output_frame, text="...", width=28, height=28,
                       corner_radius=4, fg_color=BUTTON_SECONDARY_FG,
                       border_width=1, border_color="#333333",
                       hover_color="#252525", text_color=TEXT_COLOR,
                       command=self.browse_output_dir).grid(row=0, column=2, padx=(4, 0), pady=3, sticky="e")

        # Number of images
        ctk.CTkLabel(output_frame, text="Count:", text_color=TEXT_SECONDARY,
                     font=ctk.CTkFont(size=11)).grid(row=1, column=0, padx=(0, 6), pady=3, sticky="w")
        self.num_outputs_var = tk.StringVar(value="1")
        ctk.CTkComboBox(output_frame, values=[str(i) for i in range(1, 11)],
                        variable=self.num_outputs_var, width=70, height=28,
                        corner_radius=4, fg_color="#1a1a1a", border_color="#2a2a2a",
                        button_color="#1a1a1a", dropdown_fg_color=SURFACE_ELEVATED,
                        font=ctk.CTkFont(size=11)).grid(row=1, column=1, padx=0, pady=3, sticky="w")

    def create_generate_section(self, parent):
        """Create the sticky generate button and progress bar at bottom of left panel"""
        # Generate button - full width, violet, 48px height
        self.generate_button = ctk.CTkButton(
            parent, text="GENERATE",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=48, corner_radius=8,
            fg_color=ACCENT_COLOR, text_color=BUTTON_TEXT_COLOR,
            hover_color=ACCENT_HOVER,
            command=self.generate_image
        )
        self.generate_button.pack(fill="x", padx=12, pady=(12, 4))

        # Progress bar (4px, hidden until generating)
        self.progress_bar = ctk.CTkProgressBar(
            parent, height=4, corner_radius=2,
            fg_color="#1a1a1a", progress_color=ACCENT_COLOR,
            mode="indeterminate"
        )
        self.progress_bar.pack(fill="x", padx=12, pady=(0, 12))
        self.progress_bar.set(0)
        self.progress_bar.pack_forget()  # Hidden by default

    def create_image_display(self, parent):
        """Create the image display area inside the right gallery panel"""
        # Main image display area (centered on void black)
        self.canvas_frame = ctk.CTkFrame(parent, fg_color=APP_BG_COLOR, corner_radius=0)
        self.canvas_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self.canvas_frame.grid_columnconfigure(0, weight=1)
        self.canvas_frame.grid_rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(self.canvas_frame, bg=APP_BG_COLOR, bd=0, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        x_scrollbar = ttk.Scrollbar(self.canvas_frame, orient="horizontal", command=self.canvas.xview)
        x_scrollbar.grid(row=1, column=0, sticky="ew")
        y_scrollbar = ttk.Scrollbar(self.canvas_frame, orient="vertical", command=self.canvas.yview)
        y_scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(xscrollcommand=x_scrollbar.set, yscrollcommand=y_scrollbar.set)

        def _on_image_mousewheel(event):
            if sys.platform == "darwin": scroll_amount = event.delta
            else: scroll_amount = -1 * (event.delta // 120)
            self.canvas.yview_scroll(scroll_amount, "units")
        self.canvas.bind("<MouseWheel>", _on_image_mousewheel)
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(1, "units"))

        # --- Image Metadata Bar ---
        self.metadata_frame = ctk.CTkFrame(parent, fg_color="#050505", height=32, corner_radius=0)
        self.metadata_frame.grid(row=1, column=0, sticky="ew", padx=0, pady=0)
        self.metadata_frame.grid_propagate(False)

        self.image_info_label = ctk.CTkLabel(self.metadata_frame,
                                              text="No image generated yet",
                                              font=ctk.CTkFont(family="Consolas", size=11),
                                              text_color=TEXT_SECONDARY)
        self.image_info_label.pack(expand=True, pady=4)

        # --- Thumbnail Strip (horizontal, 80px height, #050505 bg) ---
        thumb_strip_frame = ctk.CTkFrame(parent, fg_color="#050505", height=96,
                                          corner_radius=0, border_width=1,
                                          border_color=BORDER_COLOR)
        thumb_strip_frame.grid(row=2, column=0, sticky="ew", padx=0, pady=0)
        thumb_strip_frame.grid_propagate(False)
        thumb_strip_frame.grid_columnconfigure(0, weight=1)
        thumb_strip_frame.grid_rowconfigure(0, weight=1)

        self.thumbnail_frame = ctk.CTkScrollableFrame(thumb_strip_frame,
                                                        fg_color="#050505", height=80,
                                                        orientation="horizontal",
                                                        scrollbar_button_color="#2a2a2a",
                                                        scrollbar_button_hover_color="#3a3a3a")
        self.thumbnail_frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        # Hide vertical scrollbar
        try:
            self.thumbnail_frame._scrollbar.grid_forget()
        except Exception:
            pass

        # Open Folder button at end of thumbnail strip
        open_folder_btn = ctk.CTkButton(thumb_strip_frame, text="\U0001F4C2", width=64, height=64,
                                          corner_radius=4, fg_color=FRAME_BG_COLOR,
                                          border_width=1, border_color="#333333",
                                          hover_color="#1a1a1a", text_color=TEXT_SECONDARY,
                                          font=ctk.CTkFont(size=18),
                                          command=self.open_output_folder)
        open_folder_btn.grid(row=0, column=1, padx=(0, 8), pady=8, sticky="e")

        # Display initial placeholder
        placeholder_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "placeholder.png")
        if os.path.exists(placeholder_path):
            if hasattr(self, 'display_image') and callable(self.display_image):
                 self.after(100, lambda: self.display_image(placeholder_path))
            else:
                 try:
                     self.canvas.create_text(400, 300, text="Generate an image", fill="#555555", font=("Consolas", 14))
                 except Exception as canvas_err:
                     print(f"Error adding text to canvas: {canvas_err}")
        else:
            try:
                self.canvas.create_text(400, 300, text="Generate an image", fill="#555555", font=("Consolas", 14))
            except Exception as canvas_err:
                 print(f"Error adding text to canvas: {canvas_err}")

    def create_status_bar(self, parent):
        """Create the status bar matching the Stitch design"""
        # Left section: connection status dot + service name
        left_status = ctk.CTkFrame(parent, fg_color="transparent")
        left_status.pack(side="left", padx=(8, 0), pady=0)

        self.status_dot = ctk.CTkLabel(left_status, text="\u25CF", width=12,
                                        font=ctk.CTkFont(size=8),
                                        text_color=SUCCESS_COLOR)
        self.status_dot.pack(side="left", padx=(0, 4))

        self.status_label = ctk.CTkLabel(left_status,
                                          text=f"Connected to {self.config['service'].capitalize()}",
                                          font=ctk.CTkFont(family="Consolas", size=11),
                                          text_color=TEXT_SECONDARY)
        self.status_label.pack(side="left")

        # Center section: model info
        self.service_info_label = ctk.CTkLabel(parent,
                                                text=f"{self.config['service'].capitalize()}",
                                                font=ctk.CTkFont(family="Consolas", size=11),
                                                text_color=TEXT_SECONDARY)
        self.service_info_label.pack(side="left", padx=16)

        # Right section: generation count
        self.gen_count_label = ctk.CTkLabel(parent, text="0 generated",
                                             font=ctk.CTkFont(family="Consolas", size=11),
                                             text_color=TEXT_SECONDARY)
        self.gen_count_label.pack(side="right", padx=(0, 8))

    def toggle_negative_prompt(self):
        """Toggle the negative prompt textarea enable/disable state"""
        is_enabled = self.negative_toggle_var.get()
        self.config["use_negative_prompt"] = is_enabled
        
        # Enable or disable the negative prompt text box based on toggle state
        if is_enabled:
            self.negative_prompt_text.configure(state="normal")
        else:
            self.negative_prompt_text.configure(state="disabled")
        
        self.save_config()
        
    def toggle_trigger_words(self):
        """Toggle the trigger words entry enable/disable state"""
        is_enabled = self.trigger_toggle_var.get()
        self.config["use_trigger_words"] = is_enabled
        
        # Enable or disable the trigger words entry based on toggle state
        if is_enabled:
            self.trigger_words_entry.configure(state="normal")
            # Save current content to config
            trigger_words = self.trigger_words_entry.get()
            if trigger_words:
                self.config["trigger_words"] = trigger_words
        else:
            self.trigger_words_entry.configure(state="disabled")
        
        self.save_config()

    def toggle_advanced_mode(self):
        """Toggle advanced mode on/off (negative prompt is always visible in new layout)"""
        advanced_mode = self.advanced_mode_var.get()
        self.config["advanced_mode"] = advanced_mode
        # In the new 2-column layout, negative prompt is always visible
        # This method is kept for config compatibility
        self.save_config()

    def update_image_preview(self, image_paths):
        """ Safely update the image preview and thumbnails in the main thread """
        if not isinstance(image_paths, list):
            image_paths = [image_paths] # Ensure it's a list

        if not image_paths:
            print("No image paths provided to update preview.")
            return

        # Display the first image in the main canvas
        first_image_path = image_paths[0]
        if not hasattr(self, 'canvas') or not self.canvas.winfo_exists():
             print("Canvas does not exist, cannot update main preview.")
             # Still try to update thumbnails
        else:
            try:
                 self.display_main_image(first_image_path)
            except Exception as e:
                 print(f"Error updating main image preview: {e}")
                 try:
                      self.canvas.delete("all")
                      self.canvas.create_text(200, 150, text=f"Error displaying image:\n{str(e)[:50]}...", fill="red")
                 except Exception: pass

        # Update thumbnails
        self.update_thumbnails(image_paths)

    def update_thumbnails(self, image_paths):
        """Clear and populate the thumbnail frame with 64x64 rounded thumbnails"""
        if not hasattr(self, 'thumbnail_frame'):
            print("Thumbnail frame not initialized.")
            return

        # Clear existing thumbnails
        for widget in self.thumbnail_frame.winfo_children():
            widget.destroy()

        self.generated_image_paths = image_paths
        self._thumb_buttons = []  # Track for selected state

        if not image_paths:
            return

        thumb_size = (64, 64)
        for i, path in enumerate(image_paths):
            try:
                if not os.path.exists(path): continue

                img = Image.open(path)
                img.thumbnail(thumb_size, Image.LANCZOS)
                ctk_img = ImageTk.PhotoImage(img)

                # First thumbnail gets violet border (selected), rest get subtle border
                is_selected = (i == 0)
                thumb_button = ctk.CTkButton(
                    self.thumbnail_frame,
                    image=ctk_img,
                    text="",
                    width=thumb_size[0],
                    height=thumb_size[1],
                    corner_radius=4,
                    border_width=2,
                    border_color=ACCENT_COLOR if is_selected else BORDER_COLOR,
                    fg_color=SURFACE_ELEVATED,
                    hover_color="#1a1a1a",
                    command=lambda p=path, idx=i: self._select_thumbnail(p, idx)
                )
                thumb_button._image = ctk_img
                thumb_button.pack(side="left", padx=3, pady=4)
                self._thumb_buttons.append(thumb_button)

            except Exception as e:
                print(f"Error creating thumbnail for {path}: {e}")
                error_label = ctk.CTkLabel(self.thumbnail_frame, text="Err",
                                           width=thumb_size[0], height=thumb_size[1],
                                           fg_color=ERROR_COLOR, corner_radius=4)
                error_label.pack(side="left", padx=3, pady=4)

    def _select_thumbnail(self, path, index):
        """Select a thumbnail and highlight it with violet border"""
        self.display_main_image(path)
        # Update border colors
        if hasattr(self, '_thumb_buttons'):
            for i, btn in enumerate(self._thumb_buttons):
                try:
                    btn.configure(border_color=ACCENT_COLOR if i == index else BORDER_COLOR)
                except Exception:
                    pass


    def display_image(self, image_path):
        """Display an image on the main canvas (alias for display_main_image).

        Args:
            image_path: Path to the image file to display.
        """
        self.display_main_image(image_path)

    def display_main_image(self, image_path):
        """Display a single image in the main canvas"""
        if not hasattr(self, 'canvas') or not self.canvas.winfo_exists():
             print("Canvas does not exist, cannot display main image.")
             return
        try:
            if not os.path.exists(image_path):
                print(f"Image file not found: {image_path}")
                self.canvas.delete("all")
                self.canvas.create_text(200, 150, text=f"Image not found:\n{os.path.basename(image_path)}", fill="orange")
                return

            image = Image.open(image_path)
            self.current_image_path = image_path # Store path of the currently displayed image
            self.canvas.delete("all") # Clear previous image/text first

            # Use the canvas_frame's actual size for scaling, ensure positive dimensions
            self.canvas_frame.update_idletasks() # Ensure dimensions are updated
            canvas_width = max(1, self.canvas_frame.winfo_width() - 4) # Subtract padding, ensure min 1
            canvas_height = max(1, self.canvas_frame.winfo_height() - 4) # Subtract padding, ensure min 1

            img_width, img_height = image.size
            if img_width <= 0 or img_height <= 0:
                print(f"Error: Invalid image dimensions {img_width}x{img_height} for {image_path}")
                self.canvas.create_text(canvas_width/2, canvas_height/2, text="Invalid Image Dimensions", fill="red", anchor="center")
                return

            # Calculate aspect ratio preserving resize dimensions
            ratio = min(canvas_width / img_width, canvas_height / img_height)
            display_width = int(img_width * ratio)
            display_height = int(img_height * ratio)

            if display_width > 0 and display_height > 0:
                 resized_image = image.resize((display_width, display_height), Image.LANCZOS)
                 self.photo_image = ImageTk.PhotoImage(resized_image)
                 self.canvas.config(width=display_width, height=display_height)
                 self.canvas.config(scrollregion=(0, 0, display_width, display_height))
                 self.canvas.delete("all")
                 self.canvas.create_image(0, 0, image=self.photo_image, anchor="nw") # Anchor NW
                 # Update info label
                 try:
                     file_name = os.path.basename(image_path)
                     file_size = os.path.getsize(image_path) / 1024
                     self.image_info_label.configure(text=f"{file_name} ({img_width}x{img_height}, {file_size:.1f} KB)")
                 except Exception as e: print(f"Error updating image info label: {e}")
            else:
                 print(f"Invalid image dimensions after resize: {display_width}x{display_height}")
                 self.canvas.delete("all")
                 self.canvas.create_text(200, 150, text="Error resizing image", fill="red")

        except Exception as e:
            print(f"Error displaying image: {e}")
            self.canvas.delete("all")
            self.canvas.create_text(200, 150, text=f"Error displaying image:\n{str(e)[:50]}...", fill="red")

    def save_image_as(self):
        """Save the current image with a new name"""
        if not self.current_image_path or not os.path.exists(self.current_image_path):
            messagebox.showinfo("No Image", "No image to save")
            return
        original_format = os.path.splitext(self.current_image_path)[1].lower()
        file_types = [("PNG files", "*.png"), ("JPEG files", "*.jpg"), ("WEBP files", "*.webp"), ("All files", "*.*")]
        save_path = filedialog.asksaveasfilename(initialdir=self.config["output_directory"], initialfile=os.path.basename(self.current_image_path), defaultextension=original_format, filetypes=file_types)
        if save_path:
            try:
                img = Image.open(self.current_image_path)
                img.save(save_path)
                messagebox.showinfo("Save Successful", f"Image saved to:\n{save_path}")
            except Exception as e: messagebox.showerror("Save Error", f"Error saving image: {e}")

    def open_output_folder(self):
        """Open the output folder in file explorer"""
        output_dir = self.config["output_directory"]
        if os.path.exists(output_dir):
            if sys.platform == "win32": os.startfile(output_dir)
            elif sys.platform == "darwin": os.system(f'open "{output_dir}"')
            else: os.system(f'xdg-open "{output_dir}"')
        else: messagebox.showinfo("Folder Not Found", f"Output folder does not exist:\n{output_dir}")

    def browse_output_dir(self):
        """Open a dialog to select output directory"""
        directory = filedialog.askdirectory(initialdir=self.config["output_directory"])
        if directory:
            self.output_dir_var.set(directory)
            self.config["output_directory"] = directory
            self.save_config()

    def generate_image(self):
        """Generate a single image or batch with the current settings"""
        if self.is_generating: messagebox.showinfo("In Progress", "Image generation already in progress"); return
        try:
            base_prompt = self.prompt_text.get("1.0", "end").strip()
            if not base_prompt: messagebox.showinfo("Error", "Please enter a prompt"); return

            # --- Apply Manual Trigger Words ---
            prompt = base_prompt
            if self.trigger_toggle_var.get():
                manual_triggers = self.trigger_words_entry.get().strip()
                if not manual_triggers:
                    messagebox.showerror("Input Error", "Manual trigger words checkbox is enabled, but the input field is empty.")
                    return # Stop generation
                prompt = f"{manual_triggers}, {base_prompt}" # Prepend manual triggers

            # Negative prompt is always visible in the new layout
            negative_prompt = self.negative_prompt_text.get("1.0", "end").strip()

            # --- Get Global Controls ---
            output_format = self.output_format_var.get()
            output_quality = self.output_quality_var.get() if output_format != "png" else 95
            megapixels = int(self.megapixels_var.get()) # Still relevant? Maybe remove later if unused by APIs
            go_fast = self.go_fast_var.get() # Still relevant? Maybe remove later if unused by APIs
            num_outputs = int(self.num_outputs_var.get()) # Get from the new consolidated control
            seed_str = self.seed_var.get().strip()
            seed = None
            if seed_str:
                try:
                    seed = int(seed_str)
                except ValueError:
                    messagebox.showerror("Input Error", "Seed must be an integer.")
                    return # Stop generation if seed is invalid

            # --- Get Model-Specific Parameters ---
            service = self.service_var.get()
            if service == "replicate":
                model_id = self.replicate_model_var.get()
            elif service == "huggingface":
                model_id = self.hf_model_var.get()
            else:  # gemini
                model_id = self.gemini_model_var.get()
            model_params = {}
            if model_id in self.model_param_vars:
                for param_name, tk_var in self.model_param_vars[model_id].items():
                    try:
                        val = tk_var.get()
                        model_params[param_name] = val
                    except Exception as e:
                        print(f"Warning: Could not get/convert value for {param_name} of model {model_id}: {e}")
            else:
                print(f"Warning: Selected model '{model_id}' not found in model configurations.")
                # Fallback: provide default parameters for missing models
                # These are required for Replicate API and most HuggingFace models
                model_params["width"] = 1024
                model_params["height"] = 1024
                model_params["num_inference_steps"] = 28
                model_params["guidance_scale"] = 7.5
                # model_params["lora_scale"] = 0.9 # Removed - now per-LoRA
                print(f"Default parameters applied for model '{model_id}': {model_params}")

            # --- Get Selected LoRAs ---
            enabled_loras = [] # List of dicts {url, scale, enabled}
            if service == "replicate":
                enabled_loras = [lora for lora in self.rep_lora_manager.get_loras() if lora.get('enabled')]
                if enabled_loras: print(f"Enabled Replicate LoRAs: {enabled_loras}")
                else: print("No enabled Replicate LoRAs selected.")
            elif service == "huggingface":
                enabled_loras = [lora for lora in self.hf_lora_manager.get_loras() if lora.get('enabled')]
                if enabled_loras: print(f"Enabled HuggingFace LoRAs: {enabled_loras}")
                else: print("No enabled HuggingFace LoRAs selected.")


            # --- Prepare input_image_path before use ---
            input_image_path = self.image_uploader.get_image_path() if hasattr(self, 'image_uploader') else None

            # --- Consolidate All Parameters ---
            final_params = {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "output_format": output_format,
                "output_quality": output_quality,
                "megapixels": megapixels, # Keep for now
                "go_fast": go_fast,       # Keep for now
                "num_outputs": num_outputs, # Add the consolidated number of images
                "service": service,
                "model_id": model_id,
                **model_params # Add model-specific params
            }
            # Ensure seed is handled correctly for single vs batch
            if num_outputs == 1 and seed is not None:
                 final_params["seed"] = seed
            elif num_outputs > 1 and seed is not None:
                 # For batch, seed usually applies to the first image or is ignored by some APIs
                 # We'll pass it, API/thread logic needs to handle it appropriately
                 final_params["seed"] = seed
                 print(f"Note: Using provided seed {seed} for batch generation. Behavior depends on API.")
            # If seed is None, it's omitted, allowing random seeds

            if input_image_path: final_params["image"] = input_image_path
            # Pass selected LoRA info based on service
            if enabled_loras:
                final_params["enabled_loras"] = enabled_loras # Pass the list of enabled LoRA dicts

            # --- Always inject global width/height if not present ---
            # Use .get() for safer access in case model_params didn't provide them
            if not final_params.get("width"):
                final_params["width"] = self.global_width_var.get()
            if not final_params.get("height"):
                final_params["height"] = self.global_height_var.get()

            # --- Prepare for Thread ---
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            output_path = os.path.join(self.config["output_directory"], f"{timestamp}_image.{output_format}")

            self.is_generating = True
            # Show progress bar
            if hasattr(self, 'progress_bar'):
                self.progress_bar.pack(fill="x", padx=12, pady=(0, 12))
                self.progress_bar.start()

            # --- Start Generation Thread (Handles single or batch based on num_outputs) ---
            # Generate list of output paths if num_outputs > 1
            output_paths = []
            if num_outputs == 1:
                output_paths.append(output_path)
            else:
                output_paths = [os.path.join(self.config["output_directory"], f"{timestamp}_batch{i+1}of{num_outputs}.{output_format}") for i in range(num_outputs)]

            self.status_label.configure(text=f"Generating {num_outputs} image(s)...")
            threading.Thread(target=self._generate_image_thread, args=(final_params, output_paths), daemon=True).start()

            # Save the *original* base prompt to history
            if base_prompt not in self.config["recent_prompts"]:
                self.config["recent_prompts"].insert(0, base_prompt)
                self.config["recent_prompts"] = self.config["recent_prompts"][:20]
                self.save_config()
        except ValueError as e:
            messagebox.showerror("Input Error", f"Invalid parameter value: {e}")
            self.is_generating = False; self.status_label.configure(text="Error")
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            messagebox.showerror("Generation Error", f"Error starting generation: {e}")
            self.is_generating = False; self.status_label.configure(text="Error")

    def _generate_image_thread(self, params, output_paths):
        """Thread function to generate single or multiple images"""
        try:
            results = [] # Store results for each image (URL, PIL Image, or Error string)
            service = params["service"]
            num_outputs = params.get("num_outputs", 1)
            print(f"--- Starting Generation ({service}, {num_outputs} image(s)) ---")
            print(f"Parameters: { {k:v for k,v in params.items() if k != 'image'} }") # Log params except image data

            if service == "replicate":
                # Replicate handles batching via num_outputs parameter
                api_result = self._call_replicate_api(params)
                if isinstance(api_result, list):
                    results = api_result # List of URLs
                elif isinstance(api_result, str) and "Error" in api_result:
                    results = [api_result] * num_outputs # Propagate error
                elif api_result: # Handle single URL result if num_outputs was 1
                    results = [api_result]
                else:
                    results = ["Replicate Error: No result returned"] * num_outputs

            elif service == "huggingface":
                # HF needs individual calls for batch simulation
                for i in range(num_outputs):
                    batch_params = params.copy()
                    # Use provided seed for first image, random for subsequent, or random if no seed provided
                    current_seed = params.get("seed") if i == 0 and "seed" in params else random.randint(0, 2**32 - 1)
                    batch_params["seed"] = current_seed
                    self.after(0, lambda i=i: self.status_label.configure(text=f"Generating image {i+1}/{num_outputs}..."))
                    print(f"Calling HF for image {i+1} with seed: {current_seed}")
                    result = self._call_hf_api(batch_params)
                    results.append(result) # Append PIL image or error string
                    if isinstance(result, str) and "Error" in result: print(f"Image {i+1} failed: {result}")
                    # Optional delay? time.sleep(0.1)

            elif service == "gemini":
                # Gemini needs individual calls for batch simulation
                for i in range(num_outputs):
                    batch_params = params.copy()
                    self.after(0, lambda i=i: self.status_label.configure(text=f"Generating image {i+1}/{num_outputs} (Gemini)..."))
                    print(f"Calling Gemini for image {i+1}")
                    result = self._call_gemini_api(batch_params)
                    results.append(result) # Append PIL image or error string
                    if isinstance(result, str) and "Error" in result: print(f"Image {i+1} failed: {result}")

            else:
                 # Correctly assign the error string to the results list
                 results = ["Error: Unknown service selected."] * num_outputs

            # Fix: Dedent this print statement to be outside the if/elif/else block
            print(f"API calls complete. Processing {len(results)} results.")

            # --- Result Handling (Iterate through results and output_paths) ---
            successful_paths = []
            error_messages = []

            for i, result in enumerate(results):
                if i >= len(output_paths): break # Safety check

                current_output_path = output_paths[i]
                image_saved_for_item = False

                if isinstance(result, str) and result.startswith("http"): # URL Case (Replicate)
                    print(f"Downloading image {i+1} from URL: {result}")
                    try:
                        response = requests.get(result, timeout=30)
                        response.raise_for_status()
                        with open(current_output_path, 'wb') as f: f.write(response.content)
                        image_saved_for_item = True
                    except Exception as e:
                        err_msg = f"Error downloading/saving image {i+1}: {e}"
                        print(err_msg)
                        error_messages.append(err_msg)
                elif isinstance(result, Image.Image): # PIL Image Case (Hugging Face)
                    try:
                        result.save(current_output_path)
                        image_saved_for_item = True
                    except Exception as e:
                        err_msg = f"Error saving PIL image {i+1}: {e}"
                        print(err_msg)
                        error_messages.append(err_msg)
                elif isinstance(result, str) and "Error" in result: # Error string from API call
                     print(f"API Error for image {i+1}: {result}")
                     error_messages.append(result)
                     # Optionally create placeholder error image here if desired

                if image_saved_for_item and os.path.exists(current_output_path):
                    successful_paths.append(current_output_path)
                    print(f"Image {i+1} saved to: {current_output_path}")

            # --- UI Update (After processing all results) ---
            if successful_paths:
                 # Update preview with the list of successful paths
                 self.after(0, lambda paths=successful_paths: self.update_image_preview(paths))
                 self.generation_count += len(successful_paths)
                 final_status = f"Generation complete ({len(successful_paths)}/{num_outputs} saved)."
                 if error_messages:
                     final_status += " Some errors occurred."
                     # Optionally show first error in message box
                     self.after(10, lambda err=error_messages[0]: messagebox.showwarning("Generation Warning", f"Some images failed:\n{err[:200]}..."))
                 self.after(10, lambda s=final_status: self.status_label.configure(text=s))
            elif error_messages: # Only errors occurred
                 first_error = error_messages[0]
                 self.after(0, lambda err=first_error: self.status_label.configure(text=f"Generation Failed: {err[:100]}"))
                 self.after(0, lambda err=first_error: messagebox.showerror("Generation Error", err))
            else: # No results at all
                 error_msg = "Generation failed: No results returned."
                 print(error_msg)
                 self.after(0, lambda: self.status_label.configure(text=error_msg))
                 self.after(0, lambda: messagebox.showerror("Generation Error", error_msg))

        except Exception as e: # Catch errors within the thread itself
            print(f"Error in generation thread: {e}")
            import traceback
            traceback.print_exc() # Print full traceback for debugging
            self.after(100, lambda err=str(e): messagebox.showerror("Generation Error", f"Error during generation:\n{err}"))
            self.after(100, lambda: self.status_label.configure(text="Error"))
        finally:
            # Always reset generating flag and hide progress bar in the main thread
            def _reset_generation_state():
                self.is_generating = False
                if hasattr(self, 'progress_bar'):
                    self.progress_bar.stop()
                    self.progress_bar.pack_forget()
                if hasattr(self, 'gen_count_label'):
                    self.gen_count_label.configure(text=f"{self.generation_count} generated")
            self.after(100, _reset_generation_state)

    def _call_replicate_api(self, params):
        """Call the Replicate API to generate an image"""
        try:
            # Check readiness based on environment variable set during setup_services
            if not os.environ.get("REPLICATE_API_TOKEN"):
                return "Replicate Error: API Key not configured or found in environment/.env."
            # No need to set os.environ here again, setup_services handles it
            model_id = self.replicate_model_var.get()
            if not model_id: return "Replicate Error: Model not selected."

            # Use .get() for safer access to parameters that might be missing for some models
            input_params = {
                "prompt": params.get("prompt", ""), # Ensure prompt exists
                "width": params.get("width"),
                "height": params.get("height"),
                "num_inference_steps": params.get("num_inference_steps", 28), # Default if missing
                "guidance_scale": params.get("guidance_scale", params.get("guidance", 7.5)), # Default if missing
                "negative_prompt": params.get("negative_prompt", ""), # Default if missing
                "num_outputs": params.get("num_outputs", 1), # Pass num_outputs for batch
                # Apply NSFW bypass techniques directly here
                "apply_watermark": False, # Explicitly disable watermark
                "disable_safety_checker": True, # Explicitly disable safety checker
            }
            # Add safety_tolerance, capping at 6
            ui_safety_tolerance = params.get("safety_tolerance")
            if ui_safety_tolerance is not None:
                api_safety_tolerance = min(int(ui_safety_tolerance), 6) # Cap at 6
                if api_safety_tolerance != int(ui_safety_tolerance):
                    print(f"Warning: UI safety_tolerance ({ui_safety_tolerance}) exceeded max (6). Using {api_safety_tolerance} for API call.")
                input_params["safety_tolerance"] = api_safety_tolerance
            else:
                 input_params["safety_tolerance"] = 6 # Default to max if not provided by UI

            # Add image only if it exists
            if params.get("image"):
                input_params["image"] = params["image"]
            # Add seed only if it exists
            if params.get("seed"):
                input_params["seed"] = params["seed"]
            # Add Replicate LoRA(s) if provided
            if params.get("enabled_loras"):
                 # Replicate API likely only supports one lora/lora_scale pair.
                 # Use the first enabled LoRA from the list.
                 first_enabled_lora = params["enabled_loras"][0]
                 input_params["lora"] = first_enabled_lora["url"]
                 input_params["lora_scale"] = first_enabled_lora["scale"]
                 print(f"Applying first enabled Replicate LoRA: {input_params['lora']} with scale {input_params['lora_scale']}")
                 if len(params["enabled_loras"]) > 1:
                     print("Warning: Multiple Replicate LoRAs were enabled in the UI, but the API likely only supports one. Using the first one.")

            # Add other specific Replicate/model params safely using .get()
            # Example: input_params["go_fast"] = params.get("go_fast", True)
            # Remove None values before sending to API
            input_params = {k: v for k, v in input_params.items() if v is not None}

            print(f"Calling Replicate: {model_id} with input: { {k:v for k,v in input_params.items() if k != 'image'} }") # Log params except image data
            output = replicate.run(model_id, input=input_params)
            return output

        except replicate.exceptions.ReplicateError as e:
            error_msg = str(e)
            # Check for both NSFW/Safety errors and Billing errors (just in case)
            is_nsfw_error = "nsfw" in error_msg.lower() or "safety" in error_msg.lower()
            is_billing_error = "billing" in error_msg.lower()

            if is_nsfw_error:
                print(f"Replicate NSFW filter triggered: {error_msg}")
                # Retry logic with aggressive bypass (already set tolerance to 7)
                retry_params = input_params.copy()
                # Add more aggressive negative prompt terms for retry
                retry_params["negative_prompt"] = f"{retry_params.get('negative_prompt', '')}, nsfw, nude, safety watermark, censored, explicit, bad quality, worst quality, deformed, blurry".strip(', ')
                # Optionally strengthen prompt keywords further if needed for retry
                # retry_params["prompt"] = retry_params["prompt"].replace("(perfectly acceptable content:1.8)", "(perfectly acceptable content:2.0)")
                print("Retrying Replicate API call with aggressive bypass (already max tolerance)...")
                try:
                    # Ensure retry uses the modified parameters
                    retry_output = replicate.run(model_id, input=retry_params)
                    print("Replicate retry successful.")
                    return retry_output
                except Exception as retry_e:
                    print(f"Replicate retry failed: {retry_e}")
                    return f"Replicate Error (Retry Failed): {str(retry_e)}"
            else:
                print(f"Replicate API error: {e}")
                return f"Replicate Error: {error_msg}"
        except Exception as e:
            print(f"Unexpected Replicate API error: {e}")
            import traceback; traceback.print_exc()
            return f"Unexpected Replicate Error: {str(e)}"

    def _call_hf_api(self, params):
        """Call the Hugging Face Inference API to generate an image"""
        try:
            # Check readiness based on environment variable set during setup_services
            hf_token = os.environ.get("HUGGINGFACE_TOKEN")
            if not hf_token:
                return "HF Error: Token not configured or found in environment/.env."
            client = InferenceClient(token=hf_token) # Use token from environment
            model_id = self.hf_model_var.get()
            if not model_id: return "HF Error: Model not selected."

            # Apply NSFW bypass using the standalone function
            api_params = configure_hf_api_params(params.copy()) # Use a copy to avoid modifying original params dict

            # Prepare parameters for the InferenceClient
            # Ensure all required parameters from the checklist are included
            inference_params = {
                "prompt": api_params["prompt"],
                "negative_prompt": api_params.get("negative_prompt", ""),
                "width": api_params.get("width"), # Pass width
                "height": api_params.get("height"), # Pass height
                "guidance_scale": api_params.get("guidance_scale"), # Pass guidance
                "num_inference_steps": api_params.get("num_inference_steps"), # Pass steps
                # Add seed if provided
            }
            if "seed" in api_params:
                inference_params["seed"] = api_params["seed"]

            # Add LoRA parameters if provided (check HF client docs for format)
            if api_params.get("enabled_loras"):
                 # Placeholder: Assuming simple list of weights and single scale for now
                 # This needs verification based on actual HF model/client capabilities
                 # Use the first enabled LoRA for now, similar to Replicate
                 first_enabled_lora = api_params["enabled_loras"][0]
                 # HF client might expect 'lora_weights' as a list of URLs/IDs and 'lora_scale' as a float
                 inference_params["lora_weights"] = [first_enabled_lora["url"]]
                 inference_params["lora_scale"] = first_enabled_lora["scale"]
                 print(f"Applying first enabled HF LoRA: {inference_params['lora_weights'][0]} with scale {inference_params['lora_scale']}")
                 if len(api_params["enabled_loras"]) > 1:
                     print("Warning: Multiple HuggingFace LoRAs were enabled in the UI, but the API client might only support one. Using the first one.")


            # Add image if present (for image-to-image models)
            # Note: HF InferenceClient might have a different method or param name for img2img
            # This part needs verification based on the specific model's API requirements
            if api_params.get("image"):
                try:
                    inference_params["image"] = Image.open(api_params["image"]) # Assuming PIL image needed
                    print("Image parameter added for img2img.")
                except Exception as img_err:
                    return f"HF Error: Failed to open input image for img2img - {img_err}"

            # Remove None values as some API endpoints might not handle them gracefully
            inference_params = {k: v for k, v in inference_params.items() if v is not None}

            print(f"Calling HF Inference API: {model_id} with params: {inference_params}") # Log parameters being sent
            # Use the correct client method
            image_result = client.text_to_image(model=model_id, **inference_params)

            # Verify return type
            if isinstance(image_result, Image.Image):
                print("HF API call successful, received PIL Image.")
                return image_result
            else:
                print(f"Unexpected HF API response type: {type(image_result)}")
                return f"HF Error: Unexpected API response format."

        except Exception as e:
            print(f"Hugging Face API error: {e}")
            import traceback; traceback.print_exc()
            # Check for specific HF errors if possible
            error_str = str(e)
            if "authorization" in error_str.lower():
                 return "HF Error: Authorization failed. Check your token."
            elif "model is currently loading" in error_str.lower():
                 return "HF Error: Model is loading, please wait and try again."
            # Add more specific HF error checks here if needed
            return f"HF Error: {error_str}"

    def _call_gemini_api(self, params):
        """Call the Google Gemini API to generate an image.

        Uses the generateContent endpoint with responseModalities: ["TEXT", "IMAGE"].
        Returns a PIL Image on success or an error string on failure.
        Free tier: ~500 images/day per API key.
        """
        try:
            gemini_key = self.config.get("gemini_api_key", "") or os.environ.get("GEMINI_API_KEY", "")
            if not gemini_key:
                return "Gemini Error: API Key not configured. Set GEMINI_API_KEY in .env or configure via UI."

            model_id = params.get("model_id", "gemini-2.5-flash-image")
            prompt_text = params.get("prompt", "")
            if not prompt_text:
                return "Gemini Error: No prompt provided."

            # Build the full prompt with image generation instruction
            full_prompt = f"Generate an image: {prompt_text}"

            # Add aspect ratio hint if width/height suggest non-square
            width = params.get("width", 1024)
            height = params.get("height", 1024)
            if width and height and width != height:
                if width > height:
                    full_prompt += f". Landscape aspect ratio approximately {width}:{height}."
                else:
                    full_prompt += f". Portrait aspect ratio approximately {width}:{height}."

            # Build the API request
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={gemini_key}"

            request_body = {
                "contents": [{"parts": [{"text": full_prompt}]}],
                "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}
            }

            body_bytes = json.dumps(request_body).encode("utf-8")

            ctx = ssl.create_default_context()
            req = urllib.request.Request(url, data=body_bytes, method="POST")
            req.add_header("Content-Type", "application/json")

            print(f"Calling Gemini API: {model_id}")
            print(f"Prompt: {full_prompt[:200]}...")

            resp = urllib.request.urlopen(req, context=ctx, timeout=120)
            data = json.loads(resp.read())

            # Parse the response for image data
            for candidate in data.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    if "inlineData" in part:
                        img_base64 = part["inlineData"]["data"]
                        mime_type = part["inlineData"].get("mimeType", "image/png")
                        img_bytes = base64.b64decode(img_base64)

                        # Convert to PIL Image
                        pil_image = Image.open(io.BytesIO(img_bytes))
                        print(f"Gemini image received: {pil_image.width}x{pil_image.height}, {mime_type}, {len(img_bytes)} bytes")
                        return pil_image

            # Check for text-only response (model refused to generate image)
            text_parts = []
            for candidate in data.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    if "text" in part:
                        text_parts.append(part["text"])

            if text_parts:
                refusal_text = " ".join(text_parts)[:300]
                print(f"Gemini returned text instead of image: {refusal_text}")
                return f"Gemini Error: Model returned text instead of image - {refusal_text}"

            return "Gemini Error: No image data in response."

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            if e.code == 429:
                return f"Gemini Error: Rate limit exceeded (429). Try a different API key or wait for quota reset at midnight Pacific. {error_body[:200]}"
            elif e.code == 400:
                return f"Gemini Error: Bad request (400). {error_body[:300]}"
            else:
                return f"Gemini Error: HTTP {e.code} - {error_body[:300]}"
        except urllib.error.URLError as e:
            return f"Gemini Error: Connection failed - {str(e)}"
        except json.JSONDecodeError as e:
            return f"Gemini Error: Failed to parse API response - {str(e)}"
        except Exception as e:
            import traceback; traceback.print_exc()
            return f"Gemini Error: {str(e)}"

    # generate_batch method REMOVED
    # _generate_batch_thread method REMOVED

    # --- Event Handlers & Callbacks ---

    def on_service_change(self):
        """Handle service change between Replicate, Hugging Face, and Gemini"""
        service = self.service_var.get()
        self.config["service"] = service
        self.update_model_section(self.model_section_frame)
        if hasattr(self, 'service_info_label'):
            self.service_info_label.configure(text=f"{service.capitalize()}")
        if hasattr(self, 'status_label'):
            self.status_label.configure(text=f"Connected to {service.capitalize()}")
        if hasattr(self, '_update_service_status_display'):
            self._update_service_status_display()
        self.save_config()

    def configure_api_keys(self):
        """Open a dialog to configure API keys"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Configure API Keys"); dialog.geometry("500x280")
        dialog.resizable(False, False); dialog.transient(self); dialog.grab_set(); dialog.focus_set()
        ctk.CTkLabel(dialog, text="Replicate API Key:", font=ctk.CTkFont(size=14)).grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")
        replicate_key_var = tk.StringVar(value=self.config.get("replicate_api_key", ""))
        ctk.CTkEntry(dialog, textvariable=replicate_key_var, width=300).grid(row=0, column=1, padx=20, pady=(20, 10), sticky="ew")
        ctk.CTkLabel(dialog, text="Hugging Face Token:", font=ctk.CTkFont(size=14)).grid(row=1, column=0, padx=20, pady=10, sticky="w")
        hf_token_var = tk.StringVar(value=self.config.get("huggingface_token", ""))
        ctk.CTkEntry(dialog, textvariable=hf_token_var, width=300).grid(row=1, column=1, padx=20, pady=10, sticky="ew")
        ctk.CTkLabel(dialog, text="Gemini API Key:", font=ctk.CTkFont(size=14)).grid(row=2, column=0, padx=20, pady=10, sticky="w")
        gemini_key_var = tk.StringVar(value=self.config.get("gemini_api_key", ""))
        ctk.CTkEntry(dialog, textvariable=gemini_key_var, width=300).grid(row=2, column=1, padx=20, pady=10, sticky="ew")
        ctk.CTkLabel(dialog, text="(Free tier - get key at ai.google.dev)", font=ctk.CTkFont(size=11), text_color="grey").grid(row=3, column=1, padx=20, pady=(0, 5), sticky="w")
        def save_keys():
            self.config["replicate_api_key"] = replicate_key_var.get()
            self.config["huggingface_token"] = hf_token_var.get()
            self.config["gemini_api_key"] = gemini_key_var.get()
            os.environ["REPLICATE_API_TOKEN"] = self.config["replicate_api_key"]
            os.environ["HUGGINGFACE_TOKEN"] = self.config["huggingface_token"]
            os.environ["GEMINI_API_KEY"] = self.config["gemini_api_key"]
            self.save_config()
            # Update status labels
            if hasattr(self, 'replicate_status'):
                rep_ready = bool(self.config.get("replicate_api_key"))
                self.replicate_status.configure(text="Ready" if rep_ready else "Key Missing", text_color="green" if rep_ready else "orange")
            if hasattr(self, 'huggingface_status'):
                hf_ready = bool(self.config.get("huggingface_token"))
                self.huggingface_status.configure(text="Ready" if hf_ready else "Key Missing", text_color="green" if hf_ready else "orange")
            if hasattr(self, 'gemini_status'):
                gemini_ready = bool(self.config.get("gemini_api_key"))
                self.gemini_status.configure(text="Ready (Free)" if gemini_ready else "Key Missing", text_color="green" if gemini_ready else "orange")
            dialog.destroy()
        ctk.CTkButton(dialog, text="Save", command=save_keys).grid(row=4, column=0, columnspan=2, padx=20, pady=20)


    def initialize_default_values(self):
        """Initialize default values for UI components"""
        # Called during __init__ after UI creation
        self.toggle_advanced_mode() # Call once to set initial visibility based on config
        self.update_model_section(self.model_section_frame) # Ensure correct model section is shown initially

    def show_prompt_history(self):
        """Show prompt history in a dialog"""
        if not self.config["recent_prompts"]: messagebox.showinfo("Prompt History", "No recent prompts found."); return
        dialog = ctk.CTkToplevel(self); dialog.title("Prompt History"); dialog.geometry("600x400")
        dialog.transient(self); dialog.grab_set(); dialog.focus_set()
        prompt_listbox = tk.Listbox(dialog, bg="#2B2B2B", fg="white", selectbackground="#3B8ED0", font=("Arial", 12), height=15, width=60)
        prompt_listbox.pack(fill="both", expand=True, padx=20, pady=20)
        for prompt in self.config["recent_prompts"]: prompt_listbox.insert("end", prompt)
        button_frame = ctk.CTkFrame(dialog); button_frame.pack(fill="x", padx=20, pady=(0, 20))
        def use_selected_prompt():
            selection = prompt_listbox.curselection()
            if selection:
                selected_prompt = prompt_listbox.get(selection[0])
                self.prompt_text.delete("1.0", "end"); self.prompt_text.insert("1.0", selected_prompt)
                dialog.destroy()
        ctk.CTkButton(button_frame, text="Use Selected", command=use_selected_prompt).pack(side="left", padx=10, pady=10)
        ctk.CTkButton(button_frame, text="Close", command=dialog.destroy).pack(side="right", padx=10, pady=10)

    def add_replicate_model(self):
        """Add a new Replicate model"""
        dialog = ctk.CTkToplevel(self); dialog.title("Add Replicate Model"); dialog.geometry("600x150")
        dialog.resizable(False, False); dialog.transient(self); dialog.grab_set(); dialog.focus_set()
        ctk.CTkLabel(dialog, text="Model ID (owner/model:version):", font=ctk.CTkFont(size=14)).grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")
        model_var = tk.StringVar(); ctk.CTkEntry(dialog, textvariable=model_var, width=400).grid(row=0, column=1, padx=20, pady=(20, 10), sticky="ew")
        def save_model():
            model_id = model_var.get().strip()
            if not model_id:
                messagebox.showerror("Error", "Please enter a valid model ID")
                return
            # Replicate expects owner/name:version format
            import re
            if not re.match(r"^[^/]+/[^:]+:[a-zA-Z0-9]+$", model_id):
                messagebox.showwarning(
                    "Format Warning",
                    "This does not match the expected Replicate format (owner/name:version). "
                    "API calls may fail unless the model reference is correct."
                )
            if model_id not in self.config["recent_models_replicate"]:
                self.config["recent_models_replicate"].append(model_id)
            self.replicate_model_combo.configure(values=self.config["recent_models_replicate"])
            self.replicate_model_var.set(model_id)
            self.config["last_used_model_replicate"] = model_id
            self.save_config()
            dialog.destroy()
        ctk.CTkButton(dialog, text="Add Model", command=save_model).grid(row=1, column=0, columnspan=2, padx=20, pady=20)

    def add_hf_model(self):
        """Add a new Hugging Face model"""
        dialog = ctk.CTkToplevel(self); dialog.title("Add Hugging Face Model"); dialog.geometry("600x150")
        dialog.resizable(False, False); dialog.transient(self); dialog.grab_set(); dialog.focus_set()
        ctk.CTkLabel(dialog, text="Model ID (owner/model):", font=ctk.CTkFont(size=14)).grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")
        model_var = tk.StringVar(); ctk.CTkEntry(dialog, textvariable=model_var, width=400).grid(row=0, column=1, padx=20, pady=(20, 10), sticky="ew")
        def save_model():
            model_id = model_var.get().strip()
            if not model_id: messagebox.showerror("Error", "Please enter a valid model ID"); return
            if model_id not in self.config["recent_models_hf"]: self.config["recent_models_hf"].append(model_id)
            self.hf_model_combo.configure(values=self.config["recent_models_hf"])
            self.hf_model_var.set(model_id); self.config["last_used_model_hf"] = model_id
            self.save_config(); dialog.destroy()
        ctk.CTkButton(dialog, text="Add Model", command=save_model).grid(row=1, column=0, columnspan=2, padx=20, pady=20)

    def add_gemini_model(self):
        """Add a new Gemini model"""
        dialog = ctk.CTkToplevel(self); dialog.title("Add Gemini Model"); dialog.geometry("600x200")
        dialog.resizable(False, False); dialog.transient(self); dialog.grab_set(); dialog.focus_set()
        ctk.CTkLabel(dialog, text="Model ID:", font=ctk.CTkFont(size=14)).grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")
        model_var = tk.StringVar(); ctk.CTkEntry(dialog, textvariable=model_var, width=400).grid(row=0, column=1, padx=20, pady=(20, 10), sticky="ew")
        ctk.CTkLabel(dialog, text="Available: gemini-2.0-flash-exp-image-generation, gemini-2.5-flash-image,\n"
                     "gemini-3-pro-image-preview, gemini-3.1-flash-image-preview",
                     font=ctk.CTkFont(size=11), text_color="grey").grid(row=1, column=0, columnspan=2, padx=20, pady=(0, 5), sticky="w")
        def save_model():
            model_id = model_var.get().strip()
            if not model_id: messagebox.showerror("Error", "Please enter a valid Gemini model ID"); return
            if "recent_models_gemini" not in self.config:
                self.config["recent_models_gemini"] = []
            if model_id not in self.config["recent_models_gemini"]: self.config["recent_models_gemini"].append(model_id)
            self.gemini_model_combo.configure(values=self.config["recent_models_gemini"])
            self.gemini_model_var.set(model_id); self.config["last_used_model_gemini"] = model_id
            self.save_config(); dialog.destroy()
        ctk.CTkButton(dialog, text="Add Model", command=save_model).grid(row=2, column=0, columnspan=2, padx=20, pady=20)

    def add_hf_lora(self):
        """Add a new Hugging Face LoRA"""
        dialog = ctk.CTkToplevel(self); dialog.title("Add Hugging Face LoRA"); dialog.geometry("600x150")
        dialog.resizable(False, False); dialog.transient(self); dialog.grab_set(); dialog.focus_set()
        ctk.CTkLabel(dialog, text="LoRA URL:", font=ctk.CTkFont(size=14)).grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")
        lora_var = tk.StringVar(); ctk.CTkEntry(dialog, textvariable=lora_var, width=400).grid(row=0, column=1, padx=20, pady=(20, 10), sticky="ew")
        def save_lora():
            lora_url = lora_var.get().strip()
            if not lora_url: messagebox.showerror("Error", "Please enter a valid LoRA URL"); return
            # Add to manager and update the dynamic HF UI list
            if self.hf_lora_manager.add_lora(lora_url): # add_lora returns True if added
                self.config["recent_loras_hf"] = self.hf_lora_manager.get_loras() # Save updated list of dicts
                self.save_config()
                self._update_hf_lora_list_ui() # Refresh the dynamic list
            else:
                messagebox.showinfo("Duplicate", "This LoRA URL is already in the list.")
            dialog.destroy()
        ctk.CTkButton(dialog, text="Add LoRA", command=save_lora).grid(row=1, column=0, columnspan=2, padx=20, pady=20)

    def add_rep_lora(self):
        """Add a new Replicate LoRA"""
        dialog = ctk.CTkToplevel(self); dialog.title("Add Replicate LoRA"); dialog.geometry("600x150")
        dialog.resizable(False, False); dialog.transient(self); dialog.grab_set(); dialog.focus_set()
        ctk.CTkLabel(dialog, text="LoRA URL:", font=ctk.CTkFont(size=14)).grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")
        lora_var = tk.StringVar(); ctk.CTkEntry(dialog, textvariable=lora_var, width=400).grid(row=0, column=1, padx=20, pady=(20, 10), sticky="ew")
        def save_lora():
            lora_url = lora_var.get().strip()
            if not lora_url: messagebox.showerror("Error", "Please enter a valid LoRA URL"); return
            # Add to manager and update UI
            if self.rep_lora_manager.add_lora(lora_url): # add_lora now returns True if added
                self.config["recent_loras_replicate"] = self.rep_lora_manager.get_loras() # Save the full dict list
                self.save_config()
                self._update_rep_lora_list_ui() # Refresh the dynamic list
            else:
                messagebox.showinfo("Duplicate", "This LoRA URL is already in the list.")
            dialog.destroy()
        ctk.CTkButton(dialog, text="Add LoRA", command=save_lora).grid(row=1, column=0, columnspan=2, padx=20, pady=20)

    def remove_rep_lora(self, lora_url_to_remove: str):
        """Remove a specific Replicate LoRA by its URL and update UI."""
        print(f"Attempting to remove Replicate LoRA: {lora_url_to_remove}")
        self.rep_lora_manager.remove_lora_by_url(lora_url_to_remove)
        self.config["recent_loras_replicate"] = self.rep_lora_manager.get_loras() # Save updated list
        self.save_config()
        self._update_rep_lora_list_ui() # Refresh the dynamic list

    def remove_hf_lora(self, lora_url_to_remove: str):
        """Remove a specific HuggingFace LoRA by its URL and update UI."""
        print(f"Attempting to remove HuggingFace LoRA: {lora_url_to_remove}")
        self.hf_lora_manager.remove_lora_by_url(lora_url_to_remove)
        self.config["recent_loras_hf"] = self.hf_lora_manager.get_loras() # Save updated list
        self.save_config()
        self._update_hf_lora_list_ui() # Refresh the dynamic list

    # --- New Methods for Dynamic LoRA UI (Both Services) ---

    def _update_rep_lora_list_ui(self):
        """Clear and rebuild the dynamic list of Replicate LoRA controls."""
        # Clear existing widgets in the list frame
        for widget in self.rep_lora_list_frame.winfo_children():
            widget.destroy()

        # Rebuild the list based on the manager
        for index, lora_data in enumerate(self.rep_lora_manager.get_loras()):
            self._create_rep_lora_entry(self.rep_lora_list_frame, index, lora_data)

    def _create_rep_lora_entry(self, parent, index, lora_data):
        """Create a frame with controls for a single Replicate LoRA."""
        entry_frame = ctk.CTkFrame(parent, fg_color="#303030") # Slightly different bg for entries
        entry_frame.pack(fill="x", pady=2, padx=2)
        entry_frame.grid_columnconfigure(1, weight=1) # Allow label to expand

        # --- Checkbox (Enable/Disable) ---
        enabled_var = tk.BooleanVar(value=lora_data.get('enabled', True))
        def on_toggle():
            # Allow multiple LoRAs to be enabled for Replicate
            new_state = enabled_var.get()
            self.rep_lora_manager.set_enabled(index, new_state)
            self.config["recent_loras_replicate"] = self.rep_lora_manager.get_loras()
            self.save_config()
            # No UI refresh needed just for toggle state change
            print(f"Replicate LoRA '{lora_data.get('url', '')}' enabled state set to: {new_state}")
            # Update label to reflect multi-select possibility
            self.rep_lora_label.configure(text="Replicate LoRAs (Select multiple):")

        checkbox = ctk.CTkCheckBox(entry_frame, variable=enabled_var, text="", width=20, command=on_toggle, checkbox_height=18, checkbox_width=18, fg_color=ACCENT_COLOR)
        checkbox.grid(row=0, column=0, padx=(5, 2), pady=5, sticky="w")

        # --- Label (Truncated URL) ---
        url = lora_data.get('url', 'Invalid URL')
        display_url = url if len(url) < 45 else url[:20] + "..." + url[-20:]
        label = ctk.CTkLabel(entry_frame, text=display_url, anchor="w", text_color=TEXT_COLOR)
        label.grid(row=0, column=1, padx=2, pady=5, sticky="ew")
        # Add tooltip (requires an external library like tktooltip or manual implementation)
        # ToolTip(label, text=url) # Example if using tktooltip

        # --- Scale Slider ---
        scale_var = tk.DoubleVar(value=lora_data.get('scale', 0.8))
        scale_label_var = tk.StringVar(value=f"{scale_var.get():.2f}") # Separate var for label text

        def on_scale_change(value):
            scale_value = float(value)
            scale_label_var.set(f"{scale_value:.2f}")
            # Update manager only when slider is released (using command)

        def on_scale_release(*args): # Called when slider released
             scale_value = scale_var.get()
             self.rep_lora_manager.set_scale(index, scale_value)
             self.config["recent_loras_replicate"] = self.rep_lora_manager.get_loras()
             self.save_config()
             print(f"Saved scale for Replicate LoRA {index}: {scale_value:.2f}")


        slider = ctk.CTkSlider(entry_frame, from_=-1.0, to=3.0, number_of_steps=40, variable=scale_var, width=100, command=on_scale_change)
        # Bind release event to save config
        slider.bind("<ButtonRelease-1>", on_scale_release)
        slider.grid(row=0, column=2, padx=2, pady=5, sticky="e")

        scale_label = ctk.CTkLabel(entry_frame, textvariable=scale_label_var, width=35, text_color=TEXT_COLOR)
        scale_label.grid(row=0, column=3, padx=(0, 5), pady=5, sticky="e")

        # --- Remove Button ---
        remove_button = ctk.CTkButton(entry_frame, text="X", width=25, height=25, fg_color="#555555", hover_color="#E04040",
                                      command=lambda u=url: self.remove_rep_lora(u))
        remove_button.grid(row=0, column=4, padx=(0, 5), pady=5, sticky="e")

    # --- New Methods for Dynamic HuggingFace LoRA UI ---

    def _update_hf_lora_list_ui(self):
        """Clear and rebuild the dynamic list of HuggingFace LoRA controls."""
        # Clear existing widgets in the list frame
        for widget in self.hf_lora_list_frame.winfo_children():
            widget.destroy()

        # Rebuild the list based on the manager
        for index, lora_data in enumerate(self.hf_lora_manager.get_loras()):
            self._create_hf_lora_entry(self.hf_lora_list_frame, index, lora_data)

    def _create_hf_lora_entry(self, parent, index, lora_data):
        """Create a frame with controls for a single HuggingFace LoRA."""
        entry_frame = ctk.CTkFrame(parent, fg_color="#303030") # Slightly different bg for entries
        entry_frame.pack(fill="x", pady=2, padx=2)
        entry_frame.grid_columnconfigure(1, weight=1) # Allow label to expand

        # --- Checkbox (Enable/Disable) ---
        enabled_var = tk.BooleanVar(value=lora_data.get('enabled', True))
        def on_toggle():
            # Allow multiple LoRAs to be enabled for HuggingFace
            new_state = enabled_var.get()
            self.hf_lora_manager.set_enabled(index, new_state)
            self.config["recent_loras_hf"] = self.hf_lora_manager.get_loras()
            self.save_config()
            print(f"HuggingFace LoRA '{lora_data.get('url', '')}' enabled state set to: {new_state}")
            # Update label to reflect multi-select possibility
            self.hf_lora_label.configure(text="HuggingFace LoRAs (Select multiple):")

        checkbox = ctk.CTkCheckBox(entry_frame, variable=enabled_var, text="", width=20, command=on_toggle, checkbox_height=18, checkbox_width=18, fg_color=ACCENT_COLOR)
        checkbox.grid(row=0, column=0, padx=(5, 2), pady=5, sticky="w")

        # --- Label (Truncated URL) ---
        url = lora_data.get('url', 'Invalid URL')
        display_url = url if len(url) < 45 else url[:20] + "..." + url[-20:]
        label = ctk.CTkLabel(entry_frame, text=display_url, anchor="w", text_color=TEXT_COLOR)
        label.grid(row=0, column=1, padx=2, pady=5, sticky="ew")
        # Add tooltip (requires an external library like tktooltip or manual implementation)
        # ToolTip(label, text=url) # Example if using tktooltip

        # --- Scale Slider ---
        scale_var = tk.DoubleVar(value=lora_data.get('scale', 0.8))
        scale_label_var = tk.StringVar(value=f"{scale_var.get():.2f}") # Separate var for label text

        def on_scale_change(value):
            scale_value = float(value)
            scale_label_var.set(f"{scale_value:.2f}")

        def on_scale_release(*args): # Called when slider released
             scale_value = scale_var.get()
             self.hf_lora_manager.set_scale(index, scale_value)
             self.config["recent_loras_hf"] = self.hf_lora_manager.get_loras()
             self.save_config()
             print(f"Saved scale for HF LoRA {index}: {scale_value:.2f}")

        slider = ctk.CTkSlider(entry_frame, from_=-1.0, to=3.0, number_of_steps=40, variable=scale_var, width=100, command=on_scale_change)
        # Bind release event to save config
        slider.bind("<ButtonRelease-1>", on_scale_release)
        slider.grid(row=0, column=2, padx=2, pady=5, sticky="e")

        scale_label = ctk.CTkLabel(entry_frame, textvariable=scale_label_var, width=35, text_color=TEXT_COLOR)
        scale_label.grid(row=0, column=3, padx=(0, 5), pady=5, sticky="e")

        # --- Remove Button ---
        remove_button = ctk.CTkButton(entry_frame, text="X", width=25, height=25, fg_color="#555555", hover_color="#E04040",
                                      command=lambda u=url: self.remove_hf_lora(u))
        remove_button.grid(row=0, column=4, padx=(0, 5), pady=5, sticky="e")


    def _create_param_widget(self, parent, param_name, config, row_idx):
        """Helper to create a widget for a model parameter with Stitch-style value badges"""
        defaults = config.get("defaults", {})
        ranges = config.get("ranges", {})
        options = config.get("options", {})
        default_value = defaults.get(param_name)

        # Parameter label (muted gray, smaller)
        ctk.CTkLabel(parent, text=f"{param_name}:", text_color=TEXT_SECONDARY,
                     font=ctk.CTkFont(size=11)).grid(row=row_idx, column=0, padx=(4, 8), pady=3, sticky="w")
        widget_var = None

        # Determine widget type
        if isinstance(default_value, bool): # Checkbox
            widget_var = tk.BooleanVar(value=default_value)
            widget = ctk.CTkCheckBox(parent, variable=widget_var, text="",
                                      checkbox_height=16, checkbox_width=16,
                                      fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER)
            widget.grid(row=row_idx, column=1, columnspan=2, padx=4, pady=3, sticky="w")
        elif param_name in options: # Dropdown
            widget_var = tk.StringVar(value=str(default_value))
            widget = ctk.CTkComboBox(parent, values=options[param_name], variable=widget_var,
                                      width=140, height=28, corner_radius=4,
                                      fg_color="#1a1a1a", border_color="#2a2a2a",
                                      button_color="#1a1a1a",
                                      dropdown_fg_color=SURFACE_ELEVATED,
                                      font=ctk.CTkFont(size=11))
            widget.grid(row=row_idx, column=1, columnspan=2, padx=4, pady=3, sticky="ew")
        elif param_name in ranges: # Slider with value badge
            range_info = ranges[param_name]
            min_val, max_val = range_info[0], range_info[1]
            if param_name == "safety_tolerance":
                max_val = min(max_val, 6)

            step = range_info[2] if len(range_info) > 2 else 1
            num_steps = int((max_val - min_val) / step) if isinstance(default_value, int) else 100

            if default_value is not None and default_value > max_val:
                clamped_default = max_val
            else:
                clamped_default = default_value

            if isinstance(clamped_default, int):
                 widget_var = tk.IntVar(value=clamped_default)
            elif isinstance(clamped_default, float):
                 widget_var = tk.DoubleVar(value=clamped_default)
                 num_steps = int((max_val - min_val) / 0.1)
            else:
                 widget_var = tk.IntVar(value=int(max_val))

            if num_steps <= 0: num_steps = 1

            widget = ctk.CTkSlider(parent, from_=min_val, to=max_val,
                                    number_of_steps=num_steps, variable=widget_var,
                                    fg_color="#1a1a1a", progress_color=ACCENT_COLOR,
                                    button_color="#FFFFFF", button_hover_color=ACCENT_HOVER,
                                    height=14)
            widget.grid(row=row_idx, column=1, padx=4, pady=3, sticky="ew")

            # Value badge (Stitch-style: bg-[#1a1a1a] px-2 py-0.5 rounded border border-[#2a2a2a])
            initial_text = f"{widget_var.get():.1f}" if isinstance(widget_var, tk.DoubleVar) else str(widget_var.get())
            value_badge = ctk.CTkLabel(parent, text=initial_text,
                                        text_color="#cccccc", width=42, height=22,
                                        fg_color="#1a1a1a", corner_radius=4,
                                        font=ctk.CTkFont(family="Consolas", size=11))
            value_badge.grid(row=row_idx, column=2, padx=(4, 4), pady=3, sticky="e")
            widget_var.trace_add("write", lambda *args, var=widget_var, badge=value_badge: badge.configure(
                text=f"{var.get():.1f}" if isinstance(var, tk.DoubleVar) else str(var.get())))
        else: # Fallback to Entry
            widget_var = tk.StringVar(value=str(default_value) if default_value is not None else "")
            widget = ctk.CTkEntry(parent, textvariable=widget_var, height=28,
                                   fg_color="#1a1a1a", border_color="#2a2a2a",
                                   border_width=1, corner_radius=4,
                                   font=ctk.CTkFont(size=11))
            widget.grid(row=row_idx, column=1, columnspan=2, padx=4, pady=3, sticky="ew")

        return widget_var

    def _update_quality_slider_state(self, *args):
        """Enable/disable output quality slider based on format"""
        if hasattr(self, 'output_quality_slider'): # Check if widget exists
            if self.output_format_var.get() == "png":
                self.output_quality_slider.configure(state=tk.DISABLED)
                self.output_quality_label.configure(state=tk.DISABLED)
            else:
                self.output_quality_slider.configure(state=tk.NORMAL)
                self.output_quality_label.configure(state=tk.NORMAL)

# Entry point to run the application
if __name__ == "__main__":
    # Ensure the root window is correctly initialized for DND if enabled
    # The class definition now handles the base class selection.
    try:
        # Create and run the application
        app = ImageGeneratorGUI()
        app.mainloop()
    except Exception as e:
        # Show error in a message box
        import traceback
        error_msg = f"Error: {str(e)}\n\n{traceback.format_exc()}"
        print(error_msg)

        # Try to show a message box if tkinter is still working
        try:
            # Import messagebox here only if needed
            from tkinter import messagebox
            messagebox.showerror("Application Error", error_msg)
        except Exception as mb_error:
            # Fallback if even messagebox fails
            print(f"Failed to show error messagebox: {mb_error}")
