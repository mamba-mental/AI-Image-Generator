from PIL import Image, ImageDraw, ImageFont
import os

def create_placeholder_image(width=512, height=512):
    """Create a placeholder image for first-time users"""
    img = Image.new('RGB', (width, height), color='#2B2B2B')
    draw = ImageDraw.Draw(img)
    
    # Add text to the image
    text = "AI Image Generator\nClick 'Generate Image'\nto start"
    
    # Try to load a font, or use default
    try:
        # Try to use a built-in font
        font = ImageFont.load_default()
        font_size = 30
    except Exception:
        pass  # Will use default drawing without specific font
    
    # Calculate text position (center)
    text_width, text_height = 200, 60  # Approximate size
    position = ((width - text_width) // 2, (height - text_height) // 2)
    
    # Draw text
    draw.text(position, text, fill='white')
    
    # Save the image
    output_path = "placeholder.png"
    img.save(output_path)
    
    print(f"Placeholder image created at: {output_path}")
    return output_path

if __name__ == "__main__":
    create_placeholder_image()
