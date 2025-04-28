from typing import List, Dict, Optional, Tuple

class LoRAManager:
    """
    Manages a list of LoRAs, each with a URL, scale, and enabled state.
    Provides add, remove, move, scale, and enable/disable operations.
    Designed for integration with UI elements.
    """

    def __init__(self, backend: str):
        """
        Initialize the LoRAManager.

        :param backend: 'hf' for HuggingFace or 'replicate' for Replicate (currently unused, but kept for potential future differentiation)
        """
        self.backend = backend
        # Store LoRAs as a list of dictionaries
        self.loras: List[Dict[str, any]] = []

    def add_lora(self, url: str, scale: float = 0.8, enabled: bool = True) -> bool:
        """
        Add a LoRA URL with an optional scale and enabled state.
        Returns True if added, False if it already exists.

        :param url: LoRA URL
        :param scale: LoRA scale (default 0.8)
        :param enabled: Initial enabled state (default True)
        :return: bool indicating if the LoRA was added
        """
        if any(lora['url'] == url for lora in self.loras):
            print(f"LoRA URL already exists: {url}")
            return False # Indicate it wasn't added because it exists

        new_lora = {
            "url": url,
            "scale": float(f"{scale:.2f}"), # Store scale formatted to 2 decimal places
            "enabled": enabled
        }
        self.loras.append(new_lora)
        print(f"Added LoRA: {new_lora}")
        return True

    def remove_lora(self, index: int) -> None:
        """
        Remove a LoRA by index.

        :param index: Index in the loras list
        """
        if 0 <= index < len(self.loras):
            removed_lora = self.loras.pop(index)
            print(f"Removed LoRA: {removed_lora}")
        else:
            print(f"Error removing LoRA: Index {index} out of bounds.")

    def remove_lora_by_url(self, url: str) -> None:
        """Remove a LoRA by its URL."""
        initial_len = len(self.loras)
        self.loras = [lora for lora in self.loras if lora['url'] != url]
        if len(self.loras) < initial_len:
            print(f"Removed LoRA by URL: {url}")
        else:
            print(f"LoRA URL not found for removal: {url}")


    def move_lora(self, from_index: int, to_index: int) -> None:
        """
        Move a LoRA from one position to another.

        :param from_index: Current index
        :param to_index: Target index
        """
        if 0 <= from_index < len(self.loras) and 0 <= to_index < len(self.loras):
            lora_to_move = self.loras.pop(from_index)
            self.loras.insert(to_index, lora_to_move)
            print(f"Moved LoRA from index {from_index} to {to_index}")
        else:
             print(f"Error moving LoRA: Index out of bounds (from={from_index}, to={to_index}, len={len(self.loras)})")

    def set_scale(self, index: int, scale: float) -> None:
        """
        Set the scale for a LoRA at a given index.

        :param index: Index in the loras list
        :param scale: New scale value
        """
        if 0 <= index < len(self.loras):
            self.loras[index]['scale'] = float(f"{scale:.2f}") # Format scale
            # print(f"Set scale for LoRA at index {index} to {self.loras[index]['scale']}") # Reduce log noise
        else:
            print(f"Error setting scale: Index {index} out of bounds.")

    def set_enabled(self, index: int, enabled: bool) -> None:
        """
        Set the enabled state for a LoRA at a given index.

        :param index: Index in the loras list
        :param enabled: New enabled state (True or False)
        """
        if 0 <= index < len(self.loras):
            self.loras[index]['enabled'] = enabled
            # print(f"Set enabled state for LoRA at index {index} to {enabled}") # Reduce log noise
        else:
            print(f"Error setting enabled state: Index {index} out of bounds.")

    def get_loras(self) -> List[Dict[str, any]]:
        """
        Get the list of LoRA dictionaries.

        :return: List of {'url': str, 'scale': float, 'enabled': bool}
        """
        return self.loras

    def get_lora_by_index(self, index: int) -> Optional[Dict[str, any]]:
        """Get a specific LoRA dictionary by index."""
        if 0 <= index < len(self.loras):
            return self.loras[index]
        return None

    def get_first_enabled_lora(self) -> Optional[Dict[str, any]]:
        """
        Get the first enabled LoRA dictionary from the list.
        Useful for APIs that only support one LoRA.

        :return: Dictionary of the first enabled LoRA or None if none are enabled.
        """
        for lora in self.loras:
            if lora.get('enabled', False): # Check if 'enabled' key exists and is True
                return lora
        return None

    def clear(self) -> None:
        """
        Remove all LoRAs.
        """
        self.loras.clear()
        print("Cleared all LoRAs.")

    def load_from_config(self, config_list: List[Dict[str, any]]) -> None:
        """
        Load LoRAs from a configuration list (e.g., from config.json).
        Ensures required keys exist and have correct types.

        :param config_list: A list of dictionaries, ideally matching the internal format.
        """
        self.clear()
        if not isinstance(config_list, list):
            print("Warning: Invalid LoRA config format (expected list), skipping load.")
            return

        for item in config_list:
            if isinstance(item, dict) and 'url' in item:
                url = item['url']
                # Provide defaults if keys are missing
                scale = float(f"{item.get('scale', 0.8):.2f}") # Default 0.8, format
                enabled = item.get('enabled', True) # Default True
                self.add_lora(url, scale, enabled)
            elif isinstance(item, str): # Handle old format (list of URLs)
                 print(f"Migrating old LoRA format (URL string): {item}")
                 self.add_lora(item) # Add with default scale/enabled
            else:
                print(f"Warning: Skipping invalid LoRA item in config: {item}")
        print(f"Loaded {len(self.loras)} LoRAs from config.")
