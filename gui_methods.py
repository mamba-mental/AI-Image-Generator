# This file contains the methods to be added to complete the ImageGeneratorGUI class
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

def create_status_bar(self):
    """Create the status bar at the bottom of the window"""
    status_frame = ctk.CTkFrame(self, height=25)
    status_frame.grid(row=7, column=0, padx=10, pady=(5, 10), sticky="ew")
    
    self.status_label = ctk.CTkLabel(
        status_frame,
        text="Ready",
        font=ctk.CTkFont(size=12)
    )
    self.status_label.pack(side="left", padx=10)
    
    # Service info label (right side)
    self.service_info_label = ctk.CTkLabel(
        status_frame,
        text=f"Service: {self.service_var.get().capitalize()}",
        font=ctk.CTkFont(size=12)
    )
    self.service_info_label.pack(side="right", padx=10)

def initialize_default_values(self):
    """Initialize default values and UI state"""
    # Restore any saved values from config
    pass
    
def toggle_advanced_mode(self):
    """Toggle advanced mode on/off"""
    advanced_mode = self.advanced_mode_var.get()
    self.config["advanced_mode"] = advanced_mode
    
    # Show/hide negative prompt section
    if advanced_mode:
        self.negative_prompt_label.grid(row=3, column=0, padx=10, pady=(10, 0), sticky="w")
        self.negative_prompt_text.grid(row=4, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")
        self.advanced_params_frame.grid(row=3, column=0, columnspan=4, padx=10, pady=5, sticky="ew")
        self.batch_frame.grid(row=2, column=0, columnspan=3, padx=10, pady=5, sticky="ew")
    else:
        self.negative_prompt_label.grid_forget()
        self.negative_prompt_text.grid_forget()
        self.advanced_params_frame.grid_forget()
        self.batch_frame.grid_forget()
        
    # Save config
    self.save_config()
    
def on_service_change(self):
    """Handle service change"""
    service = self.service_var.get()
    self.config["service"] = service
    
    # Update model section UI
    self.update_model_section()
    
    # Update service info label
    self.service_info_label.configure(text=f"Service: {service.capitalize()}")
    
    # Save config
    self.save_config()

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
    
def browse_output_dir(self):
    """Open a dialog to select output directory"""
    directory = filedialog.askdirectory(initialdir=self.config["output_directory"])
    if directory:
        self.output_dir_var.set(directory)
        self.config["output_directory"] = directory
        self.save_config()

def save_prompt_to_history(self, prompt):
    """Save prompt to history"""
    if prompt and prompt not in self.config["recent_prompts"]:
        # Add to the beginning of the list
        self.config["recent_prompts"].insert(0, prompt)
        
        # Keep only the 20 most recent prompts
        self.config["recent_prompts"] = self.config["recent_prompts"][:20]
        
        # Save config
        self.save_config()

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

def _generate_image_thread(self, service, prompt, parameters):
    """Thread function for image generation"""
    try:
        # Prepare output filename
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self.generation_count += 1
        output_filename = f"generated_{timestamp}_{self.generation_count}.{self.format_var.get()}"
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
    import replicate
    from replicate.prediction import Prediction
    import time
    
    # Get the model ID
    model = self.replicate_model_var.get()
    model_name = model.split(':')[0] if ':' in model else model
    model_version = model.split(':')[1] if ':' in model else None
    
    # Update UI to indicate we're starting
    self.after(100, lambda: self.progress_label.configure(
        text="Preparing request to Replicate API..."
    ))
    self.after(100, lambda: self.progress_bar.set(0.05))
    
    # Start timing for user feedback
    start_time = time.time()
    
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
        "apply_watermark": False
    }
    
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
        
        # Create prediction
        client = replicate.Client(api_token=os.environ.get("REPLICATE_API_TOKEN"))
        
        # Create the prediction using the proper pattern
        prediction = client.predictions.create(
            version=model,
            input=input_params
        )
        
        # Get the prediction ID for tracking
        prediction_id = prediction.id
        print(f"Created prediction with ID: {prediction_id}")
        
        # Update status with more details
        self.after(100, lambda: self.status_label.configure(
            text=f"Generating with Replicate: {model_name}..."
        ))
        
        # Poll for completion
        is_completed = False
        elapsed_time = 0
        last_status = ""
        polling_interval = 1.0  # Start with 1 second
        timeout = 180  # 3 minutes timeout
        
        while not is_completed and elapsed_time < timeout:
            # Sleep for polling interval
            time.sleep(polling_interval)
            
            # Get the latest prediction status
            prediction = client.predictions.get(prediction_id)
            status = prediction.status
            
            # Update time tracking
            elapsed_time = time.time() - start_time
            elapsed_str = f"{int(elapsed_time // 60):02d}:{int(elapsed_time % 60):02d}"
            
            # Update UI based on status
            if status != last_status:
                print(f"Prediction status changed to: {status}")
                last_status = status
            
            # Handle different statuses
            if status == "starting":
                progress_val = 0.15
                status_text = f"Initializing model... ({elapsed_str})"
            elif status == "processing":
                # Gradually increase from 0.2 to 0.9 based on elapsed time
                # Most generations take 20-40 seconds
                progress_val = min(0.2 + (elapsed_time / 60) * 0.7, 0.9)
                status_text = f"Generating image... ({elapsed_str})"
            elif status == "succeeded":
                progress_val = 0.95
                status_text = f"Generation complete, downloading... ({elapsed_str})"
                is_completed = True
            elif status == "failed":
                error_msg = prediction.error if hasattr(prediction, 'error') else "Unknown error"
                raise Exception(f"Prediction failed: {error_msg}")
            elif status == "canceled":
                raise Exception("Prediction was canceled")
            else:
                progress_val = 0.5
                status_text = f"Status: {status}... ({elapsed_str})"
            
            # Update UI with current status
            self.after(100, lambda t=status_text: self.progress_label.configure(text=t))
            self.after(100, lambda p=progress_val: self.progress_bar.set(p))
            
            # Adaptive polling - increase interval if taking long
            if elapsed_time > 30:
                polling_interval = 3.0
            elif elapsed_time > 10:
                polling_interval = 2.0
        
        # Check for timeout
        if not is_completed and elapsed_time >= timeout:
            raise Exception(f"Prediction timed out after {timeout} seconds")
        
        # Get the output URL(s)
        output = prediction.output
        
        # Handle different types of output
        if isinstance(output, list):
            image_url = output[0]
        elif isinstance(output, dict) and "images" in output:
            image_url = output["images"][0]
        elif isinstance(output, str):
            image_url = output
        else:
            raise Exception(f"Unexpected output format: {type(output)}")
        
        print(f"Image generated! URL: {image_url}")
        
        # Update UI for downloading
        self.after(100, lambda: self.progress_label.configure(
            text="Downloading generated image..."
        ))
        self.after(100, lambda: self.progress_bar.set(0.97))
        
        # Download and save the image
        response = requests.get(image_url)
        if response.status_code != 200:
            raise Exception(f"Failed to download image: HTTP {response.status_code}")
        
        img = Image.open(io.BytesIO(response.content))
        img.save(output_path)
        
        # Update UI for completion
        self.after(100, lambda: self.progress_label.configure(
            text=f"Generation completed in {elapsed_str}"
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
    import time
    import json
    import urllib.parse
    
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
    
    # Calculate a sanitized model name for API
    # Remove organization prefix if present
    model_name = model_id.split("/")[-1] if "/" in model_id else model_id
    
    # Update UI with model details
    self.after(100, lambda: self.status_label.configure(
        text=f"Preparing to use Hugging Face model: {model_id}"
    ))
    
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
        
        # Log what we're doing
        print(f"Using Hugging Face API endpoint: {api_url}")
        print(f"Model: {model_id}")
        print(f"Token: {'*' * (len(hf_token) - 4)}...{hf_token[-4:] if hf_token else 'Not set'}")
        
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
        
        # Show the payload for debugging
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
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
                
                # Try to parse the estimated time if available
                try:
                    error_json = response.json()
                    estimated_time = error_json.get("estimated_time", 30)
                except:
                    estimated_time = 30
                
                # Wait and poll for completion
                # We'll poll every few seconds for up to 3 minutes
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
            
            # Some models return direct image data in the JSON
            if isinstance(response_json, list) and len(response_json) > 0:
                # For models returning a list of images
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
                
                # Prepare output filename
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                self.generation_count += 1
                output_filename = f"generated_{timestamp}_{self.generation_count}.{self.format_var.get()}"
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

def display_image(self, image_path):
    """Display an image in the canvas"""
    try:
        # Open the image file
        img = Image.open(image_path)
        self.current_image_path = image_path
        
        # Convert to Tkinter compatible format
        photo = ImageTk.PhotoImage(img)
        
        # Store a reference to prevent garbage collection
        self.photo = photo
        
        # Update canvas
        self.canvas.delete("all")
        self.canvas.config(scrollregion=(0, 0, img.width, img.height))
        self.canvas.create_image(0, 0, image=photo, anchor="nw")
        
        # Center the image in the canvas
        self.center_image_in_canvas()
        
        # Update image info
        filename = os.path.basename(image_path)
        width, height = img.size
        self.image_info_label.configure(text=f"Displayed: {filename} ({width}x{height})")
        
    except Exception as e:
        print(f"Error displaying image: {e}")
        self.canvas.delete("all")
        self.canvas.create_text(
            400, 300,
            text=f"Error displaying image: {e}",
            fill="white",
            font=("Arial", 12)
        )
        
def center_image_in_canvas(self):
    """Center the image in the canvas"""
    if not hasattr(self, 'photo'):
        return
        
    # Get canvas and image dimensions
    canvas_width = self.canvas.winfo_width()
    canvas_height = self.canvas.winfo_height()
    image_width = self.photo.width()
    image_height = self.photo.height()
    
    # Calculate centering scroll positions
    x_pos = max(0, (image_width - canvas_width) // 2)
    y_pos = max(0, (image_height - canvas_height) // 2)
    
    # Update canvas view
    self.canvas.xview_moveto(x_pos / image_width if image_width > 0 else 0)
    self.canvas.yview_moveto(y_pos / image_height if image_height > 0 else 0)

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

def create_placeholder_image(path, width=512, height=512):
    """Create a placeholder image for first-time users"""
    img = Image.new('RGB', (width, height), color='#2B2B2B')
    draw = ImageDraw.Draw(img)
    
    # Add text to the image
    text = "AI Image Generator\nGenerate your first image!"
    
    # Try to load a font, or use default
    try:
        font = ImageFont.truetype("Arial", 30)
    except IOError:
        font = ImageFont.load_default()
    
    # Calculate text position (center)
    text_width, text_height = draw.textsize(text, font=font) if hasattr(draw, 'textsize') else (200, 60)
    position = ((width - text_width) // 2, (height - text_height) // 2)
    
    # Draw text
    draw.text(position, text, fill='white', font=font)
    
    # Save the image
    img.save(path)
    
    return path

# This file contains methods to be imported by the main GUI application
# It's not meant to be run directly

# Example run entry point (commented out as this file should be imported, not run)
# if __name__ == "__main__":
#     print("This file should be imported, not run directly.")
